"""The hourly newsletters pull (design doc v2/14 sections 3.2 to 3.4): the sender check, the converter's cleanup rules, the dated files, and the pull's
outcomes against a stand-in for Gmail. The fixtures are made-up emails shaped like each publisher's HTML; no real newsletter or address is used."""

import imaplib
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from newsletters_mcp import pull
from newsletters_mcp.conversion import SkippedMessage, issue_from_email
from newsletters_mcp.issue import Issue
from newsletters_mcp.mailbox import Credentials, NetworkFailure
from newsletters_mcp.settings import NewslettersSettings
from newsletters_mcp.store import PullStatus, prune_old_days, read_issue, read_issues, read_status, save_issue, write_status
from ops import health
from utils.keychain_utils import account_from_attributes

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "newsletters"
RECEIVED = datetime(2026, 11, 16, 21, 40, tzinfo=UTC)
TODAY = date(2026, 11, 16)
INTERNALDATES = {"markets_pm": "16-Nov-2026 16:40:36 -0500", "money_stuff": "16-Nov-2026 19:38:35 +0000", "the_morning": "16-Nov-2026 06:35:42 -0500"}


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / f"{name}.eml").read_bytes()


def converted(name: str) -> Issue:
    return issue_from_email(fixture_bytes(name), RECEIVED)


def all_text(issue: Issue) -> str:
    return "\n".join([issue.subject, issue.headline, *(section.title for section in issue.sections), *(p for s in issue.sections for p in s.paragraphs)])


def section_texts(issue: Issue) -> dict[str, list[str]]:
    return {section.title: section.paragraphs for section in issue.sections}


class FakeGmail:
    """Stands in for imaplib.IMAP4_SSL: holds raw messages and records the commands sent, failing where a test asks it to."""

    def __init__(self, messages: dict[str, bytes], login_error: Exception | None = None, select_status: str = "OK", fetch_error: Exception | None = None) -> None:
        self.messages = list(messages.items())
        self.login_error = login_error
        self.select_status = select_status
        self.fetch_error = fetch_error
        self.commands: list[tuple] = []

    def login(self, user: str, password: str) -> tuple[str, list]:
        self.commands.append(("login", user))
        if self.login_error:
            raise self.login_error
        return "OK", [b"logged in"]

    def select(self, mailbox: str = "INBOX", readonly: bool = False) -> tuple[str, list]:
        self.commands.append(("select", mailbox, readonly))
        return self.select_status, [b"1"]

    def search(self, charset: str | None, *criteria: str) -> tuple[str, list]:
        self.commands.append(("search", *criteria))
        return "OK", [" ".join(str(number) for number in range(1, len(self.messages) + 1)).encode()]

    def fetch(self, message_set: str, message_parts: str) -> tuple[str, list]:
        self.commands.append(("fetch", message_set, message_parts))
        if self.fetch_error:
            raise self.fetch_error
        name, raw = self.messages[int(message_set) - 1]
        envelope = f'{message_set} (INTERNALDATE "{INTERNALDATES.get(name, INTERNALDATES["markets_pm"])}" BODY[] {{{len(raw)}}}'.encode()
        return "OK", [(envelope, raw), b")"]

    def logout(self) -> tuple[str, list]:
        self.commands.append(("logout",))
        return "BYE", [b"bye"]


@pytest.fixture
def settings(tmp_path: Path) -> NewslettersSettings:
    return NewslettersSettings(dir=tmp_path / "newsletters")


@pytest.fixture
def stored_app_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pull, "stored_credentials", lambda service: Credentials("reader@example.com", "app-password"))


def connect_to(gmail: FakeGmail) -> pull.Connect:
    return lambda host, timeout: gmail


def day_files(settings: NewslettersSettings, day: date) -> list[str]:
    return sorted(path.name for path in (settings.dir / day.isoformat()).glob("*"))


# ---------------------------------------------------------------- the sender check


@pytest.mark.parametrize(
    "authentication_results",
    [
        "mx.google.com; dkim=pass; spf=pass; dmarc=fail (p=REJECT) header.from=markets.example.com",
        "mail.markets.example.com; dmarc=pass header.from=markets.example.com",
    ],
)
def test_a_message_without_dmarc_pass_from_gmail_is_skipped(authentication_results: str) -> None:
    raw = fixture_bytes("markets_pm")
    raw = f"Authentication-Results: {authentication_results}\n".encode() + raw[raw.index(b"From:") :]
    with pytest.raises(SkippedMessage, match="markets.example.com"):
        issue_from_email(raw, RECEIVED)


def test_a_dmarc_pass_planted_below_gmails_own_header_does_not_count() -> None:
    raw = fixture_bytes("markets_pm")
    planted = b"Authentication-Results: mx.google.com; dmarc=fail header.from=markets.example.com\n"
    raw = planted + raw  # Gmail writes its header on top, so the fixture's dmarc=pass now sits below it, where a sender could have put it
    with pytest.raises(SkippedMessage):
        issue_from_email(raw, RECEIVED)


def test_a_skipped_message_is_named_by_its_sender_domain_never_an_address() -> None:
    raw = fixture_bytes("markets_pm").replace(b"dmarc=pass", b"dmarc=fail")
    with pytest.raises(SkippedMessage) as skipped:
        issue_from_email(raw, RECEIVED)
    assert "@" not in str(skipped.value)


# ---------------------------------------------------------------- publication names


def test_the_display_name_names_a_publication_whose_subject_has_no_prefix() -> None:
    issue = converted("markets_pm")
    assert (issue.publication, issue.headline) == ("WSJ Markets P.M.", "Chip Stocks Take a Breather")


def test_a_subject_prefix_names_the_publication_when_the_list_id_confirms_it() -> None:
    issue = converted("the_morning")
    assert (issue.publication, issue.headline) == ("The Morning", "Taking stock")


def test_a_subject_prefix_names_the_publication_when_the_email_calls_itself_that_newsletter() -> None:
    issue = converted("money_stuff")
    assert (issue.publication, issue.headline) == ("Money Stuff", "Hypothetical Widgets")


def test_a_headline_with_a_colon_keeps_the_display_name() -> None:
    raw = fixture_bytes("markets_pm").replace(b"=?UTF-8?B?4pqW77iPIENoaXAgU3RvY2tzIFRha2UgYSBCcmVhdGhlcg==?=", b"Widgetron: A Breather Day")
    issue = issue_from_email(raw, RECEIVED)
    assert (issue.publication, issue.headline) == ("WSJ Markets P.M.", "Widgetron: A Breather Day")


# ---------------------------------------------------------------- sections and cleanup


def test_each_heading_starts_a_section_and_the_html_part_is_read() -> None:
    issue = converted("money_stuff")
    assert [section.title for section in issue.sections] == ["Hypothetical widgets", "Procurement", "Things happen"]
    assert "plain-text copy" not in all_text(issue)


def test_text_before_the_first_heading_is_the_opening_section() -> None:
    opening = section_texts(converted("markets_pm"))["Opening"]
    assert opening[:3] == ["Chip Stocks Take a Breather", "Plus, the widget index climbs for a third day", "By Market Desk Staff"]


def test_ads_captions_previews_and_footers_are_left_out() -> None:
    text = all_text(converted("markets_pm")) + all_text(converted("the_morning"))
    for left_out in ("Pretend Fund", "CONTENT FROM", "INVENTED PHOTOGRAPHER", "A widget factory", "preview line", "View in browser", "Sponsored by", "sign up for", "About Us", "Unsubscribe", "Host:"):
        assert left_out not in text


def test_no_email_address_survives() -> None:
    for name in ("markets_pm", "the_morning", "money_stuff"):
        assert "@" not in all_text(converted(name))


def test_emoji_and_hidden_characters_are_removed() -> None:
    text = all_text(converted("markets_pm")) + all_text(converted("money_stuff"))
    assert not any(character in text for character in ("⚖", "️", "\U0001f642", "​", "‌"))


def test_quotations_and_list_items_keep_their_marks() -> None:
    paragraphs = section_texts(converted("money_stuff"))["Hypothetical widgets"]
    assert "- The board would meet." in paragraphs
    assert any(paragraph.startswith("> Widget Corp. said") for paragraph in paragraphs)


def test_inline_links_and_bold_run_on_without_extra_spaces() -> None:
    text = all_text(converted("the_morning")) + all_text(converted("markets_pm"))
    assert "today’s Spelling Bee. Yesterday’s pangram was logotype." in text
    assert "The Federal Widget Board held rates steady" in text


def test_a_market_row_keeps_its_cells_on_one_line() -> None:
    assert "↓ DJIA Futures | 51,000.00 | -1.20%" in section_texts(converted("markets_pm"))["Markets at a Glance"]


def test_a_heading_with_nothing_under_it_joins_the_next() -> None:
    assert "TODAY’S NUMBER: 5,000" in section_texts(converted("the_morning"))


def test_footnotes_move_to_the_section_that_cites_them() -> None:
    sections = section_texts(converted("money_stuff"))
    assert sections["Hypothetical widgets"][-1] == "[1] Not formally, but informally, sure."
    assert sections["Procurement"][-1] == "[2] Disclosure, I used to work at a pretend bank."
    assert not any(paragraph.startswith("[") for paragraph in sections["Things happen"])


# ---------------------------------------------------------------- files on disk


def test_an_issue_reads_back_as_it_was_saved(settings: NewslettersSettings) -> None:
    issue = converted("money_stuff")
    path = save_issue(settings.dir, issue, fixture_bytes("money_stuff"))
    assert read_issue(path) == issue
    assert path.with_suffix(".eml").read_bytes() == fixture_bytes("money_stuff")


def test_the_folder_and_file_name_come_from_the_local_receipt_time(settings: NewslettersSettings) -> None:
    late_evening = datetime(2026, 11, 16, 23, 50).astimezone()
    issue = issue_from_email(fixture_bytes("money_stuff"), late_evening)
    path = save_issue(settings.dir, issue, b"raw")
    assert path.parent.name == "2026-11-16"
    assert path.name.startswith("2350-money-stuff-") and path.suffix == ".md"


def test_a_correction_replaces_the_earlier_copy_and_a_later_pull_keeps_it(settings: NewslettersSettings) -> None:
    original = converted("money_stuff")
    correction = original.model_copy(update={"message_id": "<correction@example.com>", "received": original.received + timedelta(minutes=20)})
    save_issue(settings.dir, original, b"original")
    save_issue(settings.dir, correction, b"correction")
    assert save_issue(settings.dir, original, b"original") is None
    issues = read_issues(settings.dir, original.received.date())
    assert [issue.message_id for issue in issues] == ["<correction@example.com>"]


def test_only_date_folders_past_the_keep_days_are_deleted(settings: NewslettersSettings) -> None:
    for name in ("2026-10-16", "2026-10-17", "2026-11-16", "notes"):
        (settings.dir / name).mkdir(parents=True)
    deleted = prune_old_days(settings.dir, TODAY, keep_days=30)
    assert [folder.name for folder in deleted] == ["2026-10-16"]
    assert sorted(path.name for path in settings.dir.iterdir()) == ["2026-10-17", "2026-11-16", "notes"]


# ---------------------------------------------------------------- the pull against a stand-in for Gmail


def test_a_pull_opens_the_label_read_only_and_saves_each_issue(settings: NewslettersSettings, stored_app_password: None) -> None:
    gmail = FakeGmail({"markets_pm": fixture_bytes("markets_pm"), "money_stuff": fixture_bytes("money_stuff")})
    assert pull.pull_succeeded(settings, datetime(2026, 11, 16, 22, 0).astimezone(), connect_to(gmail))
    assert ("select", '"Newsletters"', True) in gmail.commands
    assert ("search", "SINCE", "14-Nov-2026") in gmail.commands
    assert all(command[2] == "(INTERNALDATE BODY.PEEK[])" for command in gmail.commands if command[0] == "fetch")
    assert gmail.commands[-1] == ("logout",)
    assert len([name for day in (date(2026, 11, 16), date(2026, 11, 17)) for name in day_files(settings, day) if name.endswith(".md")]) == 2


def test_a_second_pull_over_the_same_days_changes_nothing(settings: NewslettersSettings, stored_app_password: None) -> None:
    gmail = FakeGmail({"money_stuff": fixture_bytes("money_stuff")})
    now = datetime(2026, 11, 16, 22, 0).astimezone()
    pull.pull_succeeded(settings, now, connect_to(gmail))
    first = {path: path.stat().st_mtime_ns for path in settings.dir.rglob("*.md")}
    pull.pull_succeeded(settings, now, connect_to(gmail))
    assert {path: path.stat().st_mtime_ns for path in settings.dir.rglob("*.md")} == first


def test_a_skipped_message_is_logged_by_domain_and_the_rest_are_saved(settings: NewslettersSettings, stored_app_password: None, caplog: pytest.LogCaptureFixture) -> None:
    gmail = FakeGmail({"markets_pm": fixture_bytes("markets_pm").replace(b"dmarc=pass", b"dmarc=fail"), "money_stuff": fixture_bytes("money_stuff")})
    with caplog.at_level(logging.INFO):
        assert pull.pull_succeeded(settings, datetime(2026, 11, 16, 22, 0).astimezone(), connect_to(gmail))
    assert "skipped a message: no dmarc=pass from mx.google.com, sent from markets.example.com" in caplog.text
    assert "reader@example.com" not in caplog.text
    assert len(list(settings.dir.rglob("*.md"))) == 1


def test_a_pull_with_no_app_password_stored_records_that_it_is_not_set_up(settings: NewslettersSettings) -> None:
    assert not pull.pull_succeeded(settings, datetime(2026, 11, 16, 22, 0).astimezone(), connect_to(FakeGmail({})))
    assert read_status(settings.dir).failure_kind == "not set up"


@pytest.mark.parametrize(
    ("gmail", "kind"),
    [
        (FakeGmail({}, login_error=imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")), "sign-in refused"),
        (FakeGmail({}, select_status="NO"), "label not found"),
        (FakeGmail({"money_stuff": b"x"}, fetch_error=TimeoutError("timed out")), "network"),
        (FakeGmail({"money_stuff": b"x"}, fetch_error=imaplib.IMAP4.abort("socket error")), "network"),
    ],
)
def test_a_failed_pull_names_why_and_keeps_the_last_success(settings: NewslettersSettings, stored_app_password: None, gmail: FakeGmail, kind: str) -> None:
    earlier_success = datetime(2026, 11, 16, 21, 0).astimezone()
    write_status(settings.dir, PullStatus(last_success=earlier_success))
    assert not pull.pull_succeeded(settings, datetime(2026, 11, 16, 22, 0).astimezone(), connect_to(gmail))
    status = read_status(settings.dir)
    assert (status.failure_kind, status.last_success) == (kind, earlier_success)
    assert gmail.commands[-1] == ("logout",)


def test_gmail_out_of_reach_is_a_network_failure(settings: NewslettersSettings, stored_app_password: None) -> None:
    def unreachable(host: str, timeout: float) -> FakeGmail:
        raise NetworkFailure(f"cannot reach {host}")

    assert not pull.pull_succeeded(settings, datetime(2026, 11, 16, 22, 0).astimezone(), unreachable)
    assert read_status(settings.dir).failure_kind == "network"


def test_the_keychain_account_is_read_from_the_items_attributes() -> None:
    attributes = 'keychain: "/Users/someone/Library/Keychains/login.keychain-db"\nattributes:\n    "acct"<blob>="reader@example.com"\n    "svce"<blob>="studio-assistant-gmail"\n'
    assert account_from_attributes(attributes) == "reader@example.com"


# ---------------------------------------------------------------- the health check


def test_the_health_check_passes_after_a_recent_pull(settings: NewslettersSettings) -> None:
    now = datetime(2026, 11, 16, 22, 0).astimezone()
    write_status(settings.dir, PullStatus(last_success=now - timedelta(hours=1)))
    assert health.check_newsletters_pull(settings, now).ok is True


def test_the_health_check_fails_once_the_last_good_pull_is_hours_old(settings: NewslettersSettings) -> None:
    now = datetime(2026, 11, 16, 22, 0).astimezone()
    write_status(settings.dir, PullStatus(last_success=now - timedelta(hours=4), last_failure=now, failure_kind="sign-in refused", failure_reason="revoked"))
    check = health.check_newsletters_pull(settings, now)
    assert check.ok is False and "sign-in refused" in check.detail


def test_the_health_check_skips_a_pull_that_was_never_set_up(settings: NewslettersSettings) -> None:
    write_status(settings.dir, PullStatus(last_failure=datetime(2026, 11, 16, 22, 0).astimezone(), failure_kind="not set up"))
    assert health.check_newsletters_pull(settings, datetime(2026, 11, 16, 22, 0).astimezone()).ok is None


def test_the_health_check_skips_when_the_agent_is_not_loaded(settings: NewslettersSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "agent_loaded", lambda name: False)
    assert health.check_newsletters_pull(settings, datetime(2026, 11, 16, 22, 0).astimezone()).ok is None
