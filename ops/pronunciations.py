"""Bring the Studio's pronunciation dictionaries into git, from the laptop: uv run pronunciations pull.

The dashboard edits the live copy on the Studio, and deploys never write it, so changes travel one way: live to git, through this command. It
reads the Studio dashboard's API over the home network (no SSH), compares each live dictionary with git's copy on origin/main, shows the
diff, and on a yes writes the changed files on a new branch in its own worktree, commits through the pre-commit hook, and opens a pull request.
Nothing on the Studio changes.

    uv run pronunciations pull --studio 192.168.1.162     # or set STUDIO_HOST in .env and leave --studio out
"""

import argparse
import difflib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import httpx
from dotenv import load_dotenv

from dashboard.pronunciation_views import DictionaryView
from dashboard.settings import DASHBOARD_PORT
from pr_references.references import Reference, TextAnchor
from utils.pronunciation_utils import PronunciationDictionary, matching_key, versioned_json

PROJECT_DIR = Path(__file__).resolve().parent.parent
STUDIO_HOST_VARIABLE = "STUDIO_HOST"
REQUEST_TIMEOUT_SECONDS = 10.0
LIVE_SOURCES = frozenset({"live", "history"})  # the copies only the Studio has; "git" and "empty" mean the voice reads git's own copy
VERSIONED_FOLDER = Path("config") / "pronunciations"
REVISION_LINE_TEXT = "revision"
BASE = "origin/main"


class PullRefused(Exception):
    pass


class Skip(NamedTuple):
    reason: str


class WordChange(NamedTuple):
    written: str
    say_as: str
    was: str | None  # git's say-as before; None for a new word
    removed: bool = False


@dataclass(frozen=True)
class DictionaryPull:
    live: PronunciationDictionary
    in_git: PronunciationDictionary | None

    @property
    def path(self) -> Path:
        return VERSIONED_FOLDER / self.live.model / f"{self.live.voice}.json"

    @property
    def name(self) -> str:
        return f"{self.live.model.capitalize()} · {self.live.voice}"

    def word_changes(self) -> list[WordChange]:
        before = {matching_key(entry.written): entry for entry in self.in_git.entries} if self.in_git else {}
        after = {matching_key(entry.written): entry for entry in self.live.entries}
        added_or_changed = [WordChange(entry.written, entry.say_as, before[key].say_as if key in before else None) for key, entry in after.items() if before.get(key) != entry]
        removed = [WordChange(entry.written, entry.say_as, entry.say_as, removed=True) for key, entry in before.items() if key not in after]
        return sorted(added_or_changed + removed, key=lambda change: matching_key(change.written))


def main() -> None:
    arguments = parse_args()
    load_dotenv(PROJECT_DIR / ".env")
    studio_host = arguments.studio or os.environ.get(STUDIO_HOST_VARIABLE)
    if not studio_host:
        sys.exit(f"pronunciations: name the Studio with --studio, such as --studio 192.168.1.162, or set {STUDIO_HOST_VARIABLE} in .env")
    try:
        pull(studio_host, arguments.yes)
    except PullRefused as refusal:
        sys.exit(f"pronunciations: {refusal}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pronunciations", description="Bring the Studio's live pronunciation dictionaries into git.")
    commands = parser.add_subparsers(dest="command", required=True)
    pull_command = commands.add_parser("pull", help="open a pull request that makes git's copies match the Studio's live ones")
    pull_command.add_argument("--studio", help=f"the Studio's address or name (default: {STUDIO_HOST_VARIABLE} from .env)")
    pull_command.add_argument("--yes", action="store_true", help="open the pull request without asking after the diff")
    return parser.parse_args()


def pull(studio_host: str, assume_yes: bool) -> None:
    git_in(PROJECT_DIR, "fetch", "--quiet", "origin")
    pulls = [decision for decision in map(decision_against_main, studio_dictionaries(studio_host)) if isinstance(decision, DictionaryPull)]
    if not pulls:
        print("Git already has every live dictionary; nothing to pull.")
        return
    print(diff_of(pulls))
    if not assume_yes and input("Open a pull request with these changes? [y/N] ").strip().lower() != "y":
        print("Nothing written.")
        return
    print(f"Opened {open_pull_request(pulls, studio_host)}")


def studio_dictionaries(studio_host: str) -> list[DictionaryView]:
    base = f"http://{studio_host}:{DASHBOARD_PORT}"
    try:
        with httpx.Client(base_url=base, timeout=REQUEST_TIMEOUT_SECONDS) as client:
            return dictionaries_from(client)
    except httpx.HTTPError as error:
        raise PullRefused(f"the Studio's dashboard did not answer at {base}: {type(error).__name__}: {error}") from error


def dictionaries_from(client: httpx.Client) -> list[DictionaryView]:
    keys = studio_json(client, "/api/pronunciations")
    return [DictionaryView.model_validate(studio_json(client, f"/api/pronunciations/{key['model']}/{key['voice']}")) for key in keys]


def studio_json(client: httpx.Client, path: str) -> list | dict:
    response = client.get(path)
    response.raise_for_status()
    return response.json()


def decision_against_main(view: DictionaryView) -> DictionaryPull | Skip:
    decision = pull_decision(view, dictionary_on_main(view.model, view.voice))
    if isinstance(decision, Skip):
        print(f"{view.model}/{view.voice}: {decision.reason}")
    return decision


def dictionary_on_main(model: str, voice: str) -> PronunciationDictionary | None:
    shown = subprocess.run(["git", "-C", str(PROJECT_DIR), "show", f"origin/main:{VERSIONED_FOLDER / model / voice}.json"], capture_output=True, text=True)
    return PronunciationDictionary.model_validate(json.loads(shown.stdout)) if shown.returncode == 0 else None


def pull_decision(view: DictionaryView, in_git: PronunciationDictionary | None) -> DictionaryPull | Skip:
    """Pull only what the Studio alone has. Git's copy at the live revision or later, with other words, was changed in git directly: refused,
    because pulling would quietly undo that change. Put those words in through the dashboard, then pull again."""
    if view.source not in LIVE_SOURCES:
        return Skip(f"the Studio has no live copy and reads git's (revision {view.revision}); nothing to pull")
    live = PronunciationDictionary(model=view.model, voice=view.voice, revision=view.revision, entries=view.entries)
    if in_git is not None and entry_pairs(in_git) == entry_pairs(live):
        return Skip(f"git already has these words (live revision {live.revision}, git revision {in_git.revision})")
    if in_git is not None and in_git.revision >= live.revision:
        raise PullRefused(
            f"{view.model}/{view.voice}: git's copy is at revision {in_git.revision} with other words than the Studio's live revision {live.revision}, "
            "so it was changed in git directly; add those words in the dashboard's Pronunciation tab, then pull again"
        )
    return DictionaryPull(live=live, in_git=in_git)


def entry_pairs(dictionary: PronunciationDictionary) -> set[tuple[str, str]]:
    return {(entry.written, entry.say_as) for entry in dictionary.entries}


def diff_of(pulls: list[DictionaryPull]) -> str:
    return "".join(file_diff(pull) for pull in pulls)


def file_diff(pull: DictionaryPull) -> str:
    before = versioned_json(pull.in_git).splitlines(keepends=True) if pull.in_git else []
    return "".join(difflib.unified_diff(before, versioned_json(pull.live).splitlines(keepends=True), f"a/{pull.path}", f"b/{pull.path}"))


def open_pull_request(pulls: list[DictionaryPull], studio_host: str) -> str:
    branch = f"pronunciations-{datetime.now():%Y%m%d-%H%M%S}"
    worktree = worktrees_dir() / branch
    git_in(PROJECT_DIR, "worktree", "add", "--quiet", "-b", branch, str(worktree), BASE)
    try:
        url = commit_and_publish(pulls, studio_host, worktree, branch)
    except subprocess.CalledProcessError as error:
        raise PullRefused(f"{' '.join(error.cmd[:4])} failed (above); the change is left in {worktree} on branch {branch} to fix or delete") from error
    git_in(PROJECT_DIR, "worktree", "remove", str(worktree))
    return url


def commit_and_publish(pulls: list[DictionaryPull], studio_host: str, worktree: Path, branch: str) -> str:
    subprocess.run([str(worktree / "scripts" / "dev_setup.sh")], cwd=worktree, check=True)
    for each in pulls:
        (worktree / each.path).parent.mkdir(parents=True, exist_ok=True)
        (worktree / each.path).write_text(versioned_json(each.live))
    git_in(worktree, "add", *(str(each.path) for each in pulls))
    subprocess.run(["git", "-C", str(worktree), "commit", "--quiet", "-m", commit_message(pulls)], check=True)
    return publish(worktree, branch, pull_request_body(pulls, studio_host, worktree), pull_request_title(pulls))


def publish(worktree: Path, branch: str, body: str, title: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as body_file:
        body_file.write(body)
    for check in ("check", "lint"):
        subprocess.run(["uv", "run", "pr-refs", check, body_file.name], cwd=worktree, check=True)
    git_in(worktree, "push", "--quiet", "-u", "origin", branch)
    created = subprocess.run(["gh", "pr", "create", "--base", "main", "--head", branch, "--title", title, "--body-file", body_file.name], cwd=worktree, check=True, capture_output=True, text=True)
    return created.stdout.strip()


def worktrees_dir() -> Path:
    """Beside the main checkout, wherever this command runs from: ~/code/home_assistant-worktrees for ~/code/home_assistant."""
    main_checkout = Path(git_in(PROJECT_DIR, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent
    return main_checkout.parent / f"{main_checkout.name}-worktrees"


def git_in(directory: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True, text=True).stdout.strip()


def pull_request_title(pulls: list[DictionaryPull]) -> str:
    return "Pull pronunciations from the Studio: " + ", ".join(f"{each.live.model}/{each.live.voice} revision {each.live.revision}" for each in pulls)


def commit_message(pulls: list[DictionaryPull]) -> str:
    lines = [f"{each.live.model}/{each.live.voice}: {change_line(change)}" for each in pulls for change in each.word_changes()]
    return pull_request_title(pulls) + "\n\n" + "\n".join(lines) + "\n"


def change_line(change: WordChange) -> str:
    if change.removed:
        return f"removed {change.written} (was said as {change.was})"
    if change.was is None:
        return f"added {change.written} as {change.say_as}"
    return f"{change.written} is said as {change.say_as}, not {change.was}"


def pull_request_body(pulls: list[DictionaryPull], studio_host: str, checkout: Path) -> str:
    """In the template's shape, with each reference pointing at the word's own line in the written file, so pr-refs check and lint pass."""
    summary = (
        f"Brings git's copy of the pronunciation dictionaries up to the Studio's live copy, read from its dashboard at {studio_host}:{DASHBOARD_PORT} on "
        f"{datetime.now():%Y-%m-%d %H:%M}. Merging changes nothing the voice hears, because the Studio already reads its live copy. After the next deploy, "
        'the Pronunciation tab\'s "Not in git yet" banner goes away.'
    )
    sections = [dictionary_section(each, read_lines(checkout / each.path)) for each in pulls]
    verify = "```\nuv run pytest tests/test_pronunciation.py -q\n```"
    notes = "Written by `uv run pronunciations pull`. The words come from the Studio: to change one, edit it in the dashboard and pull again, rather than editing this file."
    return "\n\n".join(["## Summary", summary, *sections, "## How to verify", verify, "## Review notes", notes]) + "\n"


def dictionary_section(pull: DictionaryPull, lines: list[str]) -> str:
    since = f"revision {pull.in_git.revision} to {pull.live.revision}" if pull.in_git else f"new, revision {pull.live.revision}"
    bullets = [change_bullet(pull.path, change, lines) for change in pull.word_changes()]
    return f"## {pull.name} ({since})\n\n" + "\n".join(bullets)


def change_bullet(path: Path, change: WordChange, lines: list[str]) -> str:
    if change.removed:
        return f'- {line_reference(path, REVISION_LINE_TEXT, lines)} **Removed {change.written}.** It was said as "{change.was}"; the voice reads the word its own way again.'
    if change.was is None:
        return f'- {word_reference(path, change.written, lines)} **Added {change.written}.** Said as "{change.say_as}".'
    return f'- {word_reference(path, change.written, lines)} **Changed {change.written}.** Said as "{change.say_as}", was "{change.was}".'


def word_reference(path: Path, written: str, lines: list[str]) -> str:
    """The word's own entry line. A reference quotes its text between double quotes, so a word containing one is cited by the revision line."""
    if '"' in written:
        return line_reference(path, REVISION_LINE_TEXT, lines)
    entry_start = f'"written": {json.dumps(written, ensure_ascii=False)}'
    line_number = next(number for number, line in enumerate(lines, start=1) if entry_start in line)
    return Reference(TextAnchor(path, written), line_number, line_number).render()


def line_reference(path: Path, text: str, lines: list[str]) -> str:
    line_number = next(number for number, line in enumerate(lines, start=1) if text in line)
    return Reference(TextAnchor(path, text), line_number, line_number).render()


def read_lines(path: Path) -> list[str]:
    return path.read_text().splitlines()


if __name__ == "__main__":
    main()
