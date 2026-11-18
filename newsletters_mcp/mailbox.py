"""Reads the newsletters label from Gmail over IMAP, read-only (design doc v2/14 section 3.2).

The label is opened with EXAMINE, and messages are fetched with BODY.PEEK, so nothing in the mailbox is marked, moved, or deleted. The address and app
password come from the Keychain, so neither appears in the repository or the logs.
"""

import imaplib
import re
from datetime import date, datetime
from typing import NamedTuple, Protocol

from utils.keychain_utils import keychain_account, keychain_secret

INTERNALDATE = re.compile(rb'INTERNALDATE "([^"]+)"')
IMAP_DATE_FORMAT = "%d-%b-%Y"
INTERNALDATE_FORMAT = "%d-%b-%Y %H:%M:%S %z"


class MailboxUnavailable(RuntimeError):
    """The pull could not read the label; the files already saved stay."""

    kind = "mailbox unavailable"


class NotSetUp(MailboxUnavailable):
    kind = "not set up"


class SignInRefused(MailboxUnavailable):
    kind = "sign-in refused"


class LabelNotFound(MailboxUnavailable):
    kind = "label not found"


class NetworkFailure(MailboxUnavailable):
    kind = "network"


class Credentials(NamedTuple):
    address: str
    app_password: str


class FetchedMessage(NamedTuple):
    raw: bytes
    received: datetime  # when Gmail received it (INTERNALDATE), which no sender can set


class ImapClient(Protocol):
    """The part of imaplib.IMAP4_SSL the pull uses, so tests can stand in for Gmail."""

    def login(self, user: str, password: str) -> tuple[str, list]: ...

    def select(self, mailbox: str = "INBOX", readonly: bool = False) -> tuple[str, list]: ...

    def search(self, charset: str | None, *criteria: str) -> tuple[str, list]: ...

    def fetch(self, message_set: str, message_parts: str) -> tuple[str, list]: ...

    def logout(self) -> tuple[str, list]: ...


def stored_credentials(keychain_service: str) -> Credentials:
    address = keychain_account(keychain_service)
    app_password = keychain_secret(keychain_service, address) if address else None
    if not address or not app_password:
        raise NotSetUp(f"no Gmail app password in the Keychain item {keychain_service} (design doc v2/14 section 3.1)")
    return Credentials(address, app_password)


def connect_to_gmail(host: str, timeout_seconds: float) -> ImapClient:
    try:
        return imaplib.IMAP4_SSL(host, timeout=timeout_seconds)
    except OSError as error:
        raise NetworkFailure(f"cannot reach {host}: {error}") from error


def fetch_messages_since(client: ImapClient, credentials: Credentials, mailbox: str, since: date) -> list[FetchedMessage]:
    try:
        sign_in(client, credentials)
        open_read_only(client, mailbox)
        return [fetch_message(client, number) for number in message_numbers_since(client, since)]
    except (imaplib.IMAP4.abort, OSError) as error:
        raise NetworkFailure(f"the connection to Gmail broke: {error}") from error
    except imaplib.IMAP4.error as error:
        raise MailboxUnavailable(f"Gmail answered with an error: {error}") from error
    finally:
        log_out_quietly(client)


def sign_in(client: ImapClient, credentials: Credentials) -> None:
    try:
        client.login(credentials.address, credentials.app_password)
    except imaplib.IMAP4.abort:
        raise
    except imaplib.IMAP4.error as error:
        raise SignInRefused(f"Gmail refused the sign-in ({error}); the app password may have been revoked") from error


def open_read_only(client: ImapClient, mailbox: str) -> None:
    status, _ = client.select(f'"{mailbox}"', readonly=True)
    if status != "OK":
        raise LabelNotFound(f"Gmail has no IMAP folder {mailbox!r}: check the label's name and that Show in IMAP is ticked")


def message_numbers_since(client: ImapClient, since: date) -> list[str]:
    _, data = client.search(None, "SINCE", since.strftime(IMAP_DATE_FORMAT))
    return data[0].decode().split() if data and data[0] else []


def fetch_message(client: ImapClient, number: str) -> FetchedMessage:
    _, data = client.fetch(number, "(INTERNALDATE BODY.PEEK[])")
    envelope, raw = next(part for part in data if isinstance(part, tuple))
    return FetchedMessage(raw=raw, received=received_time(envelope))


def received_time(envelope: bytes) -> datetime:
    match = INTERNALDATE.search(envelope)
    if match is None:
        raise ValueError(f"no INTERNALDATE in {envelope[:80]!r}")
    return datetime.strptime(match.group(1).decode().strip(), INTERNALDATE_FORMAT)


def log_out_quietly(client: ImapClient) -> None:
    try:
        client.logout()
    except (imaplib.IMAP4.error, OSError):
        pass
