"""The newsletter tools' answers from the pulled files (design doc v2/14 sections 3.5 and 3.7): a day's issues with their section names, narrowed
to one newsletter or to the sections that mention a topic, the text of one issue or section for the model to summarize, and one part to read aloud.

Every failure is one sentence telling the model what to do next, never an exception, as the other tools do. When the last pull failed, a note says so,
since newer issues may be missing.
"""

import re
from collections.abc import Callable
from datetime import date, datetime, timedelta

from newsletters_mcp.conversion import OPENING_SECTION
from newsletters_mcp.issue import Issue, Section
from newsletters_mcp.mailbox import NotSetUp
from newsletters_mcp.reading import PartPosition, ReadCursor, next_position, read_cursor, reading_text, write_cursor
from newsletters_mcp.settings import NewslettersSettings
from newsletters_mcp.store import PullStatus, read_issues, read_status
from utils.text_utils import spoken_month_day
from utils.title_matching_utils import TitleMatcher

UNREADABLE_DATE_MESSAGE = 'Cannot read "{asked}" as a day. Call again with date "today", "yesterday", or a date such as 2026-11-16.'
NO_ISSUES_MESSAGE = "No newsletters arrived on {day}."
NOT_SET_UP_MESSAGE = "Newsletters are not set up yet: no Gmail app password is stored on the Mac. Tell the user."
NO_NEWSLETTER_MESSAGE = 'No newsletter matching "{asked}" on {day}. That day\'s newsletters are: {publications}.'
SEVERAL_NEWSLETTERS_MESSAGE = 'Several newsletters on {day} match "{asked}": {publications}. Ask the user which one.'
NO_SECTION_MESSAGE = 'No section matching "{asked}" in {publication}. Its sections are: {titles}.'
NO_TOPIC_MESSAGE = 'No section of {scope} on {day} mentions "{topic}".'
PULL_FAILED_NOTE = "The last newsletter pull failed at {time} ({kind}), so newer issues may be missing."
NOTHING_TO_CONTINUE_MESSAGE = "Nothing has been read aloud lately. Ask the user which newsletter to read, or call newsletters_list."
FINISHED_MESSAGE = "The last reading reached the end of {publication}. Ask the user what to read next."
CONTINUE_SECTION = "next"
LEFT_OUT_NOTE = "Left out for length: {titles}. Ask for one of them by name."
WORDS_AROUND_A_PUBLICATION = frozenset({"the", "newsletter", "newsletters", "issue", "todays", "wsj", "nyt", "bloomberg"})
SPOKEN_TIMES = re.compile(r"\b([ap])\.\s?m\.?", re.IGNORECASE)  # "A.M." and "a.m." match "am" as said aloud
SECTION_SEPARATOR = "; "
IssuesAnswer = Callable[[date, list[Issue]], str]


class NewsletterAnswers:
    def __init__(self, settings: NewslettersSettings) -> None:
        self.settings = settings
        self.publication_matcher = TitleMatcher(WORDS_AROUND_A_PUBLICATION)
        self.section_matcher = TitleMatcher(frozenset({"the", "section"}))

    def listing(self, asked_date: str, newsletter: str, topic: str) -> str:
        return self.answered(asked_date, lambda day, issues: self.list_issues(day, issues, newsletter, topic))

    def text(self, newsletter: str, asked_date: str, section: str) -> str:
        return self.answered(asked_date, lambda day, issues: self.issue_text(day, issues, newsletter, section))

    def reading(self, newsletter: str, asked_date: str, section: str) -> str:
        """A blank newsletter, or the section "next", continues the last reading. A reading carries no note about a failed pull, as it is spoken
        as it is; the note is for the model."""
        if section.strip().lower() == CONTINUE_SECTION or not newsletter.strip():
            return self.continued_reading()
        return self.answer_for_day(asked_date, lambda day, issues: self.first_part(day, issues, newsletter, section))

    def answered(self, asked_date: str, answer: IssuesAnswer) -> str:
        return with_note(self.answer_for_day(asked_date, answer), pull_failed_note(read_status(self.settings.dir)))

    def answer_for_day(self, asked_date: str, answer: IssuesAnswer) -> str:
        day = day_asked(asked_date, self.today)
        if day is None:
            return UNREADABLE_DATE_MESSAGE.format(asked=asked_date)
        issues = read_issues(self.settings.dir, day)
        if not issues and never_set_up(read_status(self.settings.dir)):
            return NOT_SET_UP_MESSAGE
        return answer(day, issues) if issues else NO_ISSUES_MESSAGE.format(day=self.spoken_day(day))

    def list_issues(self, day: date, issues: list[Issue], newsletter: str, topic: str) -> str:
        chosen = self.issues_named(issues, newsletter) if newsletter.strip() else issues
        if not chosen:
            return self.no_newsletter(day, issues, newsletter)
        listed = [(issue, sections_mentioning(issue, topic)) for issue in chosen]
        if topic.strip() and not any(sections for _, sections in listed):
            return NO_TOPIC_MESSAGE.format(scope=chosen[0].publication if newsletter.strip() else "the newsletters", day=self.spoken_day(day), topic=topic)
        lines = [issue_line(issue, sections) for issue, sections in listed if sections or not topic.strip()]
        return "\n".join([f"Newsletters for {self.spoken_day(day)}:", *lines])

    def issue_text(self, day: date, issues: list[Issue], newsletter: str, section: str) -> str:
        chosen = self.issues_named(issues, newsletter)
        if len(chosen) != 1:
            return self.several_newsletters(day, chosen, newsletter) if chosen else self.no_newsletter(day, issues, newsletter)
        issue = chosen[0]
        sections = self.sections_named(issue, section) if section.strip() else issue.sections
        if not sections:
            return NO_SECTION_MESSAGE.format(asked=section, publication=issue.publication, titles=SECTION_SEPARATOR.join(listed_titles(issue.sections)))
        return issue_text(issue, sections, self.settings.summary_max_words)

    def first_part(self, day: date, issues: list[Issue], newsletter: str, section: str) -> str:
        chosen = self.issues_named(issues, newsletter)
        if len(chosen) != 1:
            return self.several_newsletters(day, chosen, newsletter) if chosen else self.no_newsletter(day, issues, newsletter)
        issue = chosen[0]
        sections = self.sections_named(issue, section) if section.strip() else issue.sections[:1]
        if not sections:
            return NO_SECTION_MESSAGE.format(asked=section, publication=issue.publication, titles=SECTION_SEPARATOR.join(listed_titles(issue.sections)))
        return self.read_part_moving_cursor(day, issue, PartPosition(start_section_index=issue.sections.index(sections[0]), part_index=0))

    def continued_reading(self) -> str:
        cursor = read_cursor(self.settings.dir)
        issue = cursor and next((issue for issue in read_issues(self.settings.dir, cursor.day) if issue.message_id == cursor.message_id), None)
        if issue is None:
            return NOTHING_TO_CONTINUE_MESSAGE
        following = next_position(issue, cursor.position, self.settings.reading_words)
        if following is None:
            return FINISHED_MESSAGE.format(publication=issue.publication)
        return self.read_part_moving_cursor(cursor.day, issue, following)

    def read_part_moving_cursor(self, day: date, issue: Issue, position: PartPosition) -> str:
        write_cursor(self.settings.dir, ReadCursor(day=day, message_id=issue.message_id, position=position))
        return reading_text(issue, position, self.settings.reading_words)

    def issues_named(self, issues: list[Issue], asked: str) -> list[Issue]:
        """Matched on the publication or the headline, as the user may name either; earliest first, as the list gives them."""
        names = [spoken(name) for issue in issues for name in (issue.publication, issue.headline)]
        matched = set(self.publication_matcher.matches(spoken(asked), names).titles)
        return [issue for issue in issues if {spoken(issue.publication), spoken(issue.headline)} & matched]

    def sections_named(self, issue: Issue, asked: str) -> list[Section]:
        matched = self.section_matcher.matches(asked, [section.title for section in issue.sections]).titles
        return [section for section in issue.sections if section.title in matched[:1]]

    def no_newsletter(self, day: date, issues: list[Issue], asked: str) -> str:
        return NO_NEWSLETTER_MESSAGE.format(asked=asked, day=self.spoken_day(day), publications=", ".join(issue.publication for issue in issues))

    def several_newsletters(self, day: date, issues: list[Issue], asked: str) -> str:
        return SEVERAL_NEWSLETTERS_MESSAGE.format(day=self.spoken_day(day), asked=asked, publications=", ".join(issue.publication for issue in issues))

    @property
    def today(self) -> date:
        return self.settings.today or date.today()

    def spoken_day(self, day: date) -> str:
        return f"{day:%A}, {spoken_month_day(day, self.today)}"


def day_asked(asked: str, today: date) -> date | None:
    words = asked.strip().lower()
    if words in ("", "today"):
        return today
    if words == "yesterday":
        return today - timedelta(days=1)
    try:
        return date.fromisoformat(words)
    except ValueError:
        return None


def never_set_up(status: PullStatus | None) -> bool:
    return status is not None and status.last_success is None and status.failure_kind == NotSetUp.kind


def pull_failed_note(status: PullStatus | None) -> str:
    if status is None or status.last_failure is None or (status.last_success and status.last_success > status.last_failure):
        return ""
    return PULL_FAILED_NOTE.format(time=spoken_time(status.last_failure), kind=status.failure_kind)


def spoken(name: str) -> str:
    return SPOKEN_TIMES.sub(r"\1m", name)


def sections_mentioning(issue: Issue, topic: str) -> list[Section]:
    """Every section, or with a topic, those whose title or text names it as a whole word or phrase."""
    if not topic.strip():
        return issue.sections
    pattern = re.compile(rf"(?<!\w){re.escape(topic.strip())}(?!\w)", re.IGNORECASE)  # not \b, which never matches after "401(k)"
    return [section for section in issue.sections if pattern.search(section.title) or any(pattern.search(paragraph) for paragraph in section.paragraphs)]


def issue_line(issue: Issue, sections: list[Section]) -> str:
    titles = SECTION_SEPARATOR.join(listed_titles(sections)) or "no sections"
    return f'- {spoken_time(issue.received)}: {issue.publication}, "{issue.headline}", about {issue.words:,} words. Sections: {titles}.'


def listed_titles(sections: list[Section]) -> list[str]:
    """The opening before the first heading is a section to read, but not one with a name to list."""
    return [section.title for section in sections if section.title != OPENING_SECTION]


def issue_text(issue: Issue, sections: list[Section], max_words: int) -> str:
    """Whole sections only, so nothing is cut mid-argument; the sections that did not fit are named."""
    kept, words = [], 0
    for section in sections:
        if kept and words + section.words > max_words:
            break
        kept.append(section)
        words += section.words
    heading = f'{issue.publication}, "{issue.headline}", received at {spoken_time(issue.received)}.'
    body = "\n\n".join(f"## {section.title}\n" + "\n".join(section.paragraphs) for section in kept)
    left_out = listed_titles(sections[len(kept) :])
    return with_note(f"{heading}\n\n{body}", LEFT_OUT_NOTE.format(titles=SECTION_SEPARATOR.join(left_out)) if left_out else "")


def spoken_time(moment: datetime) -> str:
    return f"{moment.astimezone():%-I:%M %p}"


def with_note(text: str, note: str) -> str:
    return f"{text}\n{note}" if note else text
