"""The pronunciation tab's API: one (model, voice) dictionary read, added to, edited, deleted from and restored, and a word heard before and after.

Every change names the revision the page last read. A change made against an older revision (another tab saved in between) is refused with 409, so
one tab can never quietly undo another's edit; the page reloads and shows the newer dictionary.
"""

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from utils.pronunciation_utils import (
    HISTORY_NAME,
    LIVE_DIR,
    VERSIONED_DIR,
    Pronunciation,
    PronunciationDictionary,
    PronunciationMatcher,
    PronunciationStore,
    SnapshotMissing,
    matching_key,
)

Speak = Callable[[str, str], Awaitable[bytes]]  # (text, voice) -> WAV bytes
NAME = re.compile(r"^[a-z0-9_]+$")
PREVIEW_CHARACTERS = 500


@dataclass(frozen=True)
class PronunciationAccess:
    speakers: Mapping[str, Speak]  # by model: how to hear text in one of its voices
    live_dir: Path = LIVE_DIR
    versioned_dir: Path = VERSIONED_DIR

    def dictionaries(self) -> list[tuple[str, str]]:
        """Every (model, voice) with a copy in git or a live copy, so a voice appears as soon as either exists."""
        found = {(path.parent.name, path.stem) for folder in (self.versioned_dir, self.live_dir) for path in folder.glob("*/*.json")}
        return sorted(found)

    def store_for(self, request: Request) -> PronunciationStore | None:
        key = (request.path_params["model"], request.path_params["voice"])
        return PronunciationStore(*key, live_dir=self.live_dir, versioned_dir=self.versioned_dir) if key in self.dictionaries() else None


class EntryChange(BaseModel):
    revision: int
    written: str = Field(min_length=1)
    say_as: str = Field(min_length=1)
    replaces: str | None = None  # the written form of the entry being edited; None adds a new entry


class EntryRemoval(BaseModel):
    revision: int
    written: str


class VersionRestore(BaseModel):
    revision: int
    version: int


class PreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=PREVIEW_CHARACTERS)
    respell: bool
    candidate: EntryChange | None = None  # an entry not saved yet, heard as if it were


class SavedVersion(BaseModel):
    revision: int
    saved_at: str
    entries: int
    changes: list[str]  # what this version changed from the one before it, e.g. "+ Jokic → Yo-Kich"


class DictionaryView(BaseModel):
    model: str
    voice: str
    revision: int
    source: str  # live | history | git | empty: which copy the voice is reading now
    entries: list[Pronunciation]
    git_revision: int | None
    in_git: bool  # git's copy has the same entries as the live one
    history: list[SavedVersion]


class Refused(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def pronunciation_routes(access: PronunciationAccess) -> list[Route]:
    async def dictionaries(_request: Request) -> Response:
        return JSONResponse([{"model": model, "voice": voice} for model, voice in access.dictionaries()])

    async def dictionary(request: Request) -> Response:
        return await answered(request, lambda store, _body: dictionary_view(store))

    async def change_entry(request: Request) -> Response:
        return await answered(request, lambda store, body: saved(store, EntryChange.model_validate_json(body), entries_after_change))

    async def remove_entry(request: Request) -> Response:
        return await answered(request, lambda store, body: saved(store, EntryRemoval.model_validate_json(body), entries_after_removal))

    async def restore(request: Request) -> Response:
        return await answered(request, lambda store, body: saved(store, VersionRestore.model_validate_json(body), entries_of_version))

    async def preview(request: Request) -> Response:
        store = access.store_for(request)
        if store is None:
            return no_such_dictionary()
        try:
            asked = PreviewRequest.model_validate_json(await request.body())
            spoken = spoken_text(store, asked)
            audio = await speaker_for(access, store.model)(spoken, store.voice)
        except ValidationError as error:
            return JSONResponse({"error": first_problem(error)}, status_code=422)
        except Refused as refusal:
            return JSONResponse({"error": str(refusal)}, status_code=refusal.status)
        except (OSError, TimeoutError) as error:
            return JSONResponse({"error": f"{store.model} did not answer on this Mac: {type(error).__name__}: {error}"}, status_code=503)
        return Response(audio, media_type="audio/wav", headers={"X-Spoken-Text": quote(spoken)})

    async def answered(request: Request, view: Callable[[PronunciationStore, bytes], DictionaryView]) -> Response:
        store = access.store_for(request)
        if store is None:
            return no_such_dictionary()
        try:
            return Response(view(store, await request.body()).model_dump_json(), media_type="application/json")
        except ValidationError as error:
            return JSONResponse({"error": first_problem(error)}, status_code=422)
        except Refused as refusal:
            return JSONResponse({"error": str(refusal)}, status_code=refusal.status)
        except SnapshotMissing as error:
            return JSONResponse({"error": str(error)}, status_code=500)

    base = "/api/pronunciations/{model}/{voice}"
    return [
        Route("/api/pronunciations", dictionaries),
        Route(base, dictionary),
        Route(f"{base}/entries", change_entry, methods=["PUT"]),
        Route(f"{base}/entries", remove_entry, methods=["DELETE"]),
        Route(f"{base}/restore", restore, methods=["POST"]),
        Route(f"{base}/preview", preview, methods=["POST"]),
    ]


def speaker_for(access: PronunciationAccess, model: str) -> Speak:
    if model not in access.speakers:
        raise Refused(503, f"the dashboard has no way to hear {model} voices yet")
    return access.speakers[model]


def saved(store: PronunciationStore, change: EntryChange | EntryRemoval | VersionRestore, entries_after: Callable) -> DictionaryView:
    current = store.load()
    if change.revision != current.revision:
        raise Refused(409, f"the dictionary changed since this page read it (now revision {current.revision}); the page has been reloaded")
    store.save(entries_after(store, current, change))
    return dictionary_view(store)


def entries_after_change(_store: PronunciationStore, current: PronunciationDictionary, change: EntryChange) -> list[Pronunciation]:
    replaced = matching_key(change.replaces) if change.replaces else None
    kept = [entry for entry in current.entries if matching_key(entry.written) != replaced]
    if any(matching_key(entry.written) == matching_key(change.written) for entry in kept):
        raise Refused(422, f"“{change.written}” is already in the dictionary; edit that entry instead")
    return [*kept, Pronunciation(written=change.written.strip(), say_as=change.say_as.strip())]


def entries_after_removal(_store: PronunciationStore, current: PronunciationDictionary, removal: EntryRemoval) -> list[Pronunciation]:
    kept = [entry for entry in current.entries if matching_key(entry.written) != matching_key(removal.written)]
    if len(kept) == len(current.entries):
        raise Refused(404, f"“{removal.written}” is not in the dictionary")
    return kept


def entries_of_version(store: PronunciationStore, _current: PronunciationDictionary, restore: VersionRestore) -> list[Pronunciation]:
    try:
        return store.read_version(restore.version).entries
    except SnapshotMissing as error:
        raise Refused(404, str(error)) from error


def spoken_text(store: PronunciationStore, asked: PreviewRequest) -> str:
    """What the voice is given: the text as typed (before), or respelled by the saved entries plus the one being tried (after)."""
    if not asked.respell:
        return asked.text
    entries = store.load().entries
    if asked.candidate is not None:
        entries = entries_after_change(store, PronunciationDictionary(model=store.model, voice=store.voice, revision=0, entries=entries), asked.candidate)
    return PronunciationMatcher(entries).respelled(asked.text)


def dictionary_view(store: PronunciationStore) -> DictionaryView:
    dictionary = store.load()
    in_git = store.versioned()
    return DictionaryView(
        model=store.model,
        voice=store.voice,
        revision=dictionary.revision,
        source=source_name(store),
        entries=sorted(dictionary.entries, key=lambda entry: matching_key(entry.written)),
        git_revision=in_git.revision if in_git else None,
        in_git=in_git is not None and entry_pairs(in_git) == entry_pairs(dictionary),
        history=saved_versions(store),
    )


def source_name(store: PronunciationStore) -> str:
    path = store.source_path()
    if path is None:
        return "empty"
    return {store.live_path: "live", store.versioned_path: "git"}.get(path, "history")


def saved_versions(store: PronunciationStore) -> list[SavedVersion]:
    """Newest first, each with what it changed from the version before it; the oldest kept version has nothing to compare with."""
    versions = [(path, store.read_version(int(HISTORY_NAME.match(path.name).group(1)))) for path in store.history_paths()]
    described, earlier = [], None
    for path, version in versions:
        pairs = entry_pairs(version)
        described.append(SavedVersion(revision=version.revision, saved_at=saved_time(path), entries=len(version.entries), changes=changes_between(earlier, pairs)))
        earlier = pairs
    return described[::-1]


def changes_between(earlier: set[tuple[str, str]] | None, later: set[tuple[str, str]]) -> list[str]:
    if earlier is None:
        return ["the oldest version kept"]
    removed = [f"− {written} → {say_as}" for written, say_as in sorted(earlier - later)]
    added = [f"+ {written} → {say_as}" for written, say_as in sorted(later - earlier)]
    return removed + added


def entry_pairs(dictionary: PronunciationDictionary) -> set[tuple[str, str]]:
    return {(entry.written, entry.say_as) for entry in dictionary.entries}


def saved_time(path: Path) -> str:
    return datetime.strptime(HISTORY_NAME.match(path.name).group(2), "%Y%m%dT%H%M%S").isoformat()


def first_problem(error: ValidationError) -> str:
    problem = error.errors(include_url=False)[0]
    return f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}" if problem["loc"] else problem["msg"]


def no_such_dictionary() -> Response:
    return JSONResponse({"error": "no pronunciation dictionary for that model and voice"}, status_code=404)
