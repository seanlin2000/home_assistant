"""The newsletters on disk (design doc v2/14 section 3.4): one folder per local date, holding each issue as markdown with YAML front matter beside the
raw email it came from, plus the pull's status file. Files are written beside their final name and renamed over it, so a tool reading while the pull
runs sees the old file or the new one, never half of either.
"""

import hashlib
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel

from newsletters_mcp.issue import Issue, Section
from utils.snapshot_utils import write_file_atomically

STATUS_FILE = "status.json"
DAY_FOLDER = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
SECTION_HEADING = "## "
MESSAGE_ID_HASH_CHARACTERS = 6  # enough that two issues in one minute never share a name


class PullStatus(BaseModel):
    last_success: datetime | None = None
    last_failure: datetime | None = None
    failure_kind: str = ""  # "sign-in refused", "label not found", "network", "not set up"
    failure_reason: str = ""


def save_issue(root: Path, issue: Issue, raw: bytes) -> Path | None:
    """The markdown file written, or None when a later copy of the same issue is already saved. A correction re-sent under a new Message-ID, with the
    same publication and subject that day, replaces the earlier copy; keeping the latest one makes a second pull over the same days change nothing."""
    same_issue = [path for path in day_folder(root, issue.received.date()).glob("*.md") if is_same_issue(read_issue(path), issue)]
    if any(read_issue(path).received >= issue.received for path in same_issue):
        return None
    for path in same_issue:
        delete_issue_files(path)
    path = issue_path(root, issue)
    write_file_atomically(path.with_suffix(".eml"), raw)
    write_file_atomically(path, issue_markdown(issue).encode("utf-8"))
    return path


def is_same_issue(saved: Issue, issue: Issue) -> bool:
    return saved.publication == issue.publication and saved.subject == issue.subject


def issue_path(root: Path, issue: Issue) -> Path:
    short_hash = hashlib.sha256(issue.message_id.encode()).hexdigest()[:MESSAGE_ID_HASH_CHARACTERS]
    return day_folder(root, issue.received.date()) / f"{issue.received:%H%M}-{slug(issue.publication)}-{short_hash}.md"


def day_folder(root: Path, day: date) -> Path:
    return root / day.isoformat()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "newsletter"


def issue_markdown(issue: Issue) -> str:
    front_matter = {
        "publication": issue.publication,
        "subject": issue.subject,
        "headline": issue.headline,
        "received": issue.received.isoformat(),
        "message_id": issue.message_id,
        "words": issue.words,
        "sections": [section.title for section in issue.sections],
    }
    body = "\n\n".join(f"{SECTION_HEADING}{section.title}\n\n" + "\n\n".join(section.paragraphs) for section in issue.sections)
    return f"---\n{yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=True, width=1_000)}---\n\n{body}\n"


def read_issue(path: Path) -> Issue:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER.match(text)
    if match is None:
        raise ValueError(f"{path} has no front matter")
    facts = yaml.safe_load(match.group(1))
    return Issue(
        publication=facts["publication"],
        subject=facts["subject"],
        headline=facts["headline"],
        received=datetime.fromisoformat(facts["received"]),
        message_id=facts["message_id"],
        sections=sections_from_markdown(text[match.end() :]),
    )


def sections_from_markdown(body: str) -> list[Section]:
    sections: list[Section] = []
    for chunk in (chunk.strip() for chunk in body.split("\n\n")):
        if chunk.startswith(SECTION_HEADING):
            sections.append(Section(title=chunk.removeprefix(SECTION_HEADING), paragraphs=[]))
        elif chunk and sections:
            sections[-1].paragraphs.append(chunk)
    return sections


def read_issues(root: Path, day: date) -> list[Issue]:
    """That day's issues, earliest first."""
    return sorted((read_issue(path) for path in day_folder(root, day).glob("*.md")), key=lambda issue: issue.received)


def saved_message_ids(root: Path, days: list[date]) -> set[str]:
    return {issue.message_id for day in days for issue in read_issues(root, day)}


def delete_issue_files(path: Path) -> None:
    path.unlink(missing_ok=True)
    path.with_suffix(".eml").unlink(missing_ok=True)


def prune_old_days(root: Path, today: date, keep_days: int) -> list[Path]:
    """Only folders named as dates are ever deleted, so nothing else that comes to live in the folder can be lost."""
    oldest_kept = today - timedelta(days=keep_days)
    old_folders = [folder for folder in root.glob("*") if folder.is_dir() and DAY_FOLDER.match(folder.name) and date.fromisoformat(folder.name) < oldest_kept]
    for folder in old_folders:
        shutil.rmtree(folder)
    return old_folders


def read_status(root: Path) -> PullStatus | None:
    path = root / STATUS_FILE
    return PullStatus.model_validate_json(path.read_bytes()) if path.exists() else None


def write_status(root: Path, status: PullStatus) -> None:
    write_file_atomically(root / STATUS_FILE, status.model_dump_json(indent=2).encode("utf-8"))
