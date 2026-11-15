"""Pronunciation dictionaries: words a text-to-speech voice says wrong, and what to give it instead, one dictionary per (model, voice).

Each dictionary has three copies:
  - the live copy, which the exchange dashboard edits and the voice's server reads (outside the git checkout, so edits never dirty it);
  - its last ten versions, written beside it on every save, to undo an edit and to restore a lost live copy;
  - the versioned copy in config/pronunciations/, which changes only through a pull request made from the live copy.

Changes flow one way, from the live copy to git. Nothing ever writes git's copy over the live one, so an entry deleted in the dashboard cannot come
back from an older copy; git's copy is read only when there is no live copy and no history at all (a new Mac), and that start is logged.
"""

import json
import logging
import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from utils.snapshot_utils import SnapshotMissing, read_snapshot, write_snapshot

PROJECT_DIR = Path(__file__).resolve().parent.parent
VERSIONED_DIR = PROJECT_DIR / "config" / "pronunciations"
LIVE_DIR = Path.home() / "Library" / "Application Support" / "studio-assistant" / "pronunciations"
HISTORY_VERSIONS_KEPT = 10
# A say-as form written between slashes is phonemes, handed to the voice as they are; Kokoro reads them in its "[word](/phonemes/)" form.
PHONEMES = re.compile(r"^/.+/$")
# The Wyoming speaker name that asks a voice's server to read the text as sent, unrespelled: the dashboard's previews respell the text themselves,
# so "before" is heard without the dictionary and "after" with an entry not saved yet.
VERBATIM_SPEAKER = "verbatim"
HISTORY_NAME = re.compile(r"^r(\d+)-(\d{8}T\d{6})\.json$")

_LOGGER = logging.getLogger(__name__)


class Pronunciation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    written: str = Field(min_length=1)
    say_as: str = Field(min_length=1)

    @property
    def is_phonemes(self) -> bool:
        return bool(PHONEMES.match(self.say_as))


class PronunciationDictionary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    voice: str
    revision: int = Field(ge=0)  # raised by one on every save, so two copies show which is newer
    entries: list[Pronunciation]

    @model_validator(mode="after")
    def check_each_word_appears_once(self) -> "PronunciationDictionary":
        keys = [matching_key(entry.written) for entry in self.entries]
        repeated = sorted({key for key in keys if keys.count(key) > 1})
        if repeated:
            raise ValueError(f"each written form may appear once; repeated: {repeated}")
        return self


def versioned_json(dictionary: PronunciationDictionary) -> str:
    """Git's layout: one entry per line, so a pull request's diff shows each added, changed or removed word as one line."""
    lines = [f"    {json.dumps(entry.model_dump(), ensure_ascii=False)}" for entry in dictionary.entries]
    entries = "[\n" + ",\n".join(lines) + "\n  ]" if lines else "[]"
    return f'{{\n  "model": {json.dumps(dictionary.model)},\n  "voice": {json.dumps(dictionary.voice)},\n  "revision": {dictionary.revision},\n  "entries": {entries}\n}}\n'


def matching_key(written: str) -> str:
    return " ".join(matching_form(written).split())


def matching_form(text: str) -> str:
    """Lowercase without accents, one character for each character of the text, so a match found here sits at the same place in the original."""
    return "".join(plain_character(character) for character in text)


def plain_character(character: str) -> str:
    base = "".join(part for part in unicodedata.normalize("NFKD", character) if not unicodedata.combining(part))
    return (base or character).lower()[0]


class PronunciationMatcher:
    """Replaces every written form in a sentence with its say-as form: whole words only, ignoring case and accents, the longest phrase first, so an
    entry for "Xi Jinping" wins over one for "Xi" and neither touches "Xiaomi"."""

    def __init__(self, entries: Iterable[Pronunciation]) -> None:
        self._entries = {matching_key(entry.written): entry for entry in entries}
        phrases = sorted(self._entries, key=len, reverse=True)
        alternatives = "|".join(r"\s+".join(map(re.escape, phrase.split())) for phrase in phrases)
        self._pattern = re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)") if phrases else None

    def respelled(self, sentence: str) -> str:
        if self._pattern is None:
            return sentence
        pieces, end_of_last_match = [], 0
        for match in self._pattern.finditer(matching_form(sentence)):
            entry = self._entries[" ".join(match.group().split())]
            pieces += [sentence[end_of_last_match : match.start()], spoken_form(entry, sentence[match.start() : match.end()])]
            end_of_last_match = match.end()
        return "".join(pieces) + sentence[end_of_last_match:]


def spoken_form(entry: Pronunciation, as_written: str) -> str:
    return f"[{as_written}]({entry.say_as})" if entry.is_phonemes else entry.say_as


class PronunciationStore:
    """Where one (model, voice) dictionary's copies live, and the order they are read in: the live copy, then its newest saved version, then git's."""

    def __init__(self, model: str, voice: str, live_dir: Path = LIVE_DIR, versioned_dir: Path = VERSIONED_DIR) -> None:
        self.model = model
        self.voice = voice
        self.live_path = live_dir / model / f"{voice}.json"
        self.history_dir = live_dir / model / "history" / voice
        self.versioned_path = versioned_dir / model / f"{voice}.json"

    def source_path(self) -> Path | None:
        candidates = (self.live_path, self.newest_history_path(), self.versioned_path)
        return next((path for path in candidates if path is not None and path.exists()), None)

    def newest_history_path(self) -> Path | None:
        versions = self.history_paths()
        return versions[-1] if versions else None

    def history_paths(self) -> list[Path]:
        """Oldest first. Names start with the zero-padded revision, so they sort in the order they were saved."""
        return sorted(path for path in self.history_dir.glob("r*.json") if HISTORY_NAME.match(path.name))

    def read_version(self, revision: int) -> PronunciationDictionary:
        path = next((path for path in self.history_paths() if int(HISTORY_NAME.match(path.name).group(1)) == revision), None)
        if path is None:
            raise SnapshotMissing(f"revision {revision} is not among the last {HISTORY_VERSIONS_KEPT} saved versions")
        return read_snapshot(path, PronunciationDictionary)

    def versioned(self) -> PronunciationDictionary | None:
        """Git's copy, to show whether the live copy has changes not yet in git; None when git has no copy."""
        return read_snapshot(self.versioned_path, PronunciationDictionary) if self.versioned_path.exists() else None

    def load(self) -> PronunciationDictionary:
        path = self.source_path()
        if path is None:
            return PronunciationDictionary(model=self.model, voice=self.voice, revision=0, entries=[])
        dictionary = read_snapshot(path, PronunciationDictionary)
        if path != self.live_path:
            _LOGGER.warning("no live %s/%s pronunciations; reading revision %d from %s", self.model, self.voice, dictionary.revision, path)
        return dictionary

    def save(self, entries: Iterable[Pronunciation]) -> None:
        """Writes the entries as the next revision, keeps a copy among the saved versions, and drops versions beyond the newest ten."""
        revision = self.load().revision + 1
        dictionary = PronunciationDictionary(model=self.model, voice=self.voice, revision=revision, entries=sorted(entries, key=lambda entry: matching_key(entry.written)))
        write_snapshot(self.live_path, dictionary)
        write_snapshot(self.history_dir / f"r{revision:06d}-{datetime.now():%Y%m%dT%H%M%S}.json", dictionary)
        for old_version in self.history_paths()[:-HISTORY_VERSIONS_KEPT]:
            old_version.unlink()


class LivePronunciations:
    """The matcher a voice's server uses, rebuilt when the file it was read from changes, so a save in the dashboard applies from the next sentence.
    A file that does not read keeps the last good matcher: a broken dictionary must never stop the voice."""

    def __init__(self, store: PronunciationStore) -> None:
        self._store = store
        self._loaded_from: tuple[Path, int] | None = None
        self.matcher = PronunciationMatcher([])

    def refresh(self) -> None:
        path = self._store.source_path()
        signature = (path, path.stat().st_mtime_ns) if path is not None else None
        if signature == self._loaded_from:
            return
        try:
            self.matcher = PronunciationMatcher(self._store.load().entries)
        except SnapshotMissing as error:
            _LOGGER.error("keeping the previous pronunciations: %s", error)
        self._loaded_from = signature
