"""The hourly newsletters pull (design doc v2/14 section 3.2): copies the Gmail label's recent messages into dated markdown files, then deletes date
folders older than a month.

launchd runs it every hour, and once when the agent is loaded (scripts/services.sh installs it as "newsletters"). Start a pull by hand with
`launchctl kickstart gui/$UID/com.studio-assistant.newsletters`: a run started over SSH cannot read the Keychain. Each issue saved or skipped is one
line in ~/Library/Logs/studio-assistant/newsletters.log. A failed pull keeps the files already saved, records why in status.json, and exits 1 so the
failure shows in launchd's record.
"""

import logging
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta

from newsletters_mcp.conversion import SkippedMessage, issue_from_email
from newsletters_mcp.mailbox import FetchedMessage, ImapClient, MailboxUnavailable, connect_to_gmail, fetch_messages_since, stored_credentials
from newsletters_mcp.settings import NewslettersSettings, newsletters_settings_from_environment
from newsletters_mcp.store import PullStatus, prune_old_days, read_status, save_issue, saved_message_ids, write_status

_LOGGER = logging.getLogger("newsletters_pull")
Connect = Callable[[str, float], ImapClient]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    succeeded = pull_succeeded(newsletters_settings_from_environment(), datetime.now().astimezone(), connect_to_gmail)
    sys.exit(0 if succeeded else 1)


def pull_succeeded(settings: NewslettersSettings, now: datetime, connect: Connect) -> bool:
    for folder in prune_old_days(settings.dir, now.date(), settings.keep_days):
        _LOGGER.info("deleted %s, older than %d days", folder.name, settings.keep_days)
    try:
        pull_newsletters(settings, now.date(), connect)
    except MailboxUnavailable as error:
        _LOGGER.error("pull failed (%s), the saved newsletters stay: %s", error.kind, error)
        write_status(settings.dir, failed_status(settings, now, error))
        return False
    write_status(settings.dir, succeeded_status(settings, now))
    return True


def pull_newsletters(settings: NewslettersSettings, today: date, connect: Connect) -> None:
    since = today - timedelta(days=settings.look_back_days)
    credentials = stored_credentials(settings.keychain_service)
    messages = fetch_messages_since(connect(settings.imap_host, settings.imap_timeout_seconds), credentials, settings.mailbox, since)
    known_message_ids = saved_message_ids(settings.dir, [since + timedelta(days=offset) for offset in range(settings.look_back_days + 2)])
    for message in messages:
        save_message(settings, message, known_message_ids)
    _LOGGER.info("%d messages in %s since %s", len(messages), settings.mailbox, since)


def save_message(settings: NewslettersSettings, message: FetchedMessage, known_message_ids: set[str]) -> None:
    """A message that cannot be read is logged and passed over, so one malformed email never holds back the rest of the day's."""
    try:
        issue = issue_from_email(message.raw, message.received)
    except SkippedMessage as reason:
        _LOGGER.warning("skipped a message: %s", reason)
        return
    except (ValueError, LookupError, TypeError) as error:
        _LOGGER.error("could not convert a message received %s: %s: %s", message.received, type(error).__name__, error)
        return
    if issue.message_id in known_message_ids:
        return
    path = save_issue(settings.dir, issue, message.raw)
    if path is not None:
        _LOGGER.info("saved %s/%s (%s, %d words, %d sections)", path.parent.name, path.name, issue.publication, issue.words, len(issue.sections))


def failed_status(settings: NewslettersSettings, now: datetime, error: MailboxUnavailable) -> PullStatus:
    earlier = read_status(settings.dir) or PullStatus()
    return PullStatus(last_success=earlier.last_success, last_failure=now, failure_kind=error.kind, failure_reason=str(error))


def succeeded_status(settings: NewslettersSettings, now: datetime) -> PullStatus:
    earlier = read_status(settings.dir) or PullStatus()
    return earlier.model_copy(update={"last_success": now})


if __name__ == "__main__":
    main()
