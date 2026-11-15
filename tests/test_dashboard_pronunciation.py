from pathlib import Path
from urllib.parse import unquote

import httpx

from assistant_service.exchange_log import ExchangeLog, TraceLog
from dashboard.app import build_app
from dashboard.exchange_views import ExchangeStore
from dashboard.pronunciation_views import PronunciationAccess
from ops.pipeline_runs import PipelineRunLog
from utils.pronunciation_utils import Pronunciation, PronunciationDictionary, PronunciationStore

DICTIONARY = "/api/pronunciations/kokoro/bm_fable"
SAME_SITE = {"origin": "http://mac.lan:8775"}
GIT_ENTRIES = [Pronunciation(written="Jokic", say_as="Yo-Kich"), Pronunciation(written="Nvidia", say_as="N-Vidia")]


class FakeKokoro:
    def __init__(self) -> None:
        self.heard: list[tuple[str, str]] = []

    async def speak(self, text: str, voice: str) -> bytes:
        self.heard.append((text, voice))
        return b"RIFF-fake-wav"


def access_in(tmp_path: Path, kokoro: FakeKokoro) -> PronunciationAccess:
    versioned = PronunciationStore("kokoro", "bm_fable", live_dir=tmp_path / "live", versioned_dir=tmp_path / "git").versioned_path
    versioned.parent.mkdir(parents=True)
    versioned.write_text(PronunciationDictionary(model="kokoro", voice="bm_fable", revision=1, entries=GIT_ENTRIES).model_dump_json())
    return PronunciationAccess(speakers={"kokoro": kokoro.speak}, live_dir=tmp_path / "live", versioned_dir=tmp_path / "git")


def client_for(tmp_path: Path, kokoro: FakeKokoro) -> httpx.AsyncClient:
    store = ExchangeStore(ExchangeLog(tmp_path / "exchanges"), TraceLog(tmp_path / "traces"), PipelineRunLog(tmp_path / "pipeline_runs"))
    app = build_app(store, ["mac.lan:8775"], pronunciations=access_in(tmp_path, kokoro))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mac.lan:8775", headers=SAME_SITE)


def said_as(view: dict) -> dict[str, str]:
    return {entry["written"]: entry["say_as"] for entry in view["entries"]}


async def test_the_page_lists_each_voice_and_reads_gits_copy_until_the_first_save(tmp_path: Path) -> None:
    async with client_for(tmp_path, FakeKokoro()) as client:
        voices = (await client.get("/api/pronunciations")).json()
        view = (await client.get(DICTIONARY)).json()
        unknown = await client.get("/api/pronunciations/kokoro/af_heart")

    assert voices == [{"model": "kokoro", "voice": "bm_fable"}]
    assert (view["revision"], view["source"], view["in_git"], view["git_revision"]) == (1, "git", True, 1)
    assert said_as(view) == {"Jokic": "Yo-Kich", "Nvidia": "N-Vidia"}
    assert unknown.status_code == 404


async def test_adding_editing_and_deleting_words_each_save_a_new_revision_that_git_does_not_have_yet(tmp_path: Path) -> None:
    async with client_for(tmp_path, FakeKokoro()) as client:
        added = (await client.put(f"{DICTIONARY}/entries", json={"revision": 1, "written": "Xi Jinping", "say_as": "She Jin Ping"})).json()
        edited = (await client.put(f"{DICTIONARY}/entries", json={"revision": 2, "written": "Jokić", "say_as": "Yo-Kitch", "replaces": "Jokic"})).json()
        deleted = (await client.request("DELETE", f"{DICTIONARY}/entries", json={"revision": 3, "written": "nvidia"})).json()

    assert said_as(added) == {"Jokic": "Yo-Kich", "Nvidia": "N-Vidia", "Xi Jinping": "She Jin Ping"}
    assert said_as(edited) == {"Jokić": "Yo-Kitch", "Nvidia": "N-Vidia", "Xi Jinping": "She Jin Ping"}
    assert said_as(deleted) == {"Jokić": "Yo-Kitch", "Xi Jinping": "She Jin Ping"}
    assert (deleted["revision"], deleted["source"], deleted["in_git"], deleted["git_revision"]) == (4, "live", False, 1)
    assert [version["revision"] for version in deleted["history"]] == [4, 3, 2]
    assert deleted["history"][0]["changes"] == ["− Nvidia → N-Vidia"]
    assert deleted["history"][1]["changes"] == ["− Jokic → Yo-Kich", "+ Jokić → Yo-Kitch"]


async def test_a_change_from_a_page_that_missed_another_tabs_save_is_refused(tmp_path: Path) -> None:
    async with client_for(tmp_path, FakeKokoro()) as client:
        await client.put(f"{DICTIONARY}/entries", json={"revision": 1, "written": "Xi Jinping", "say_as": "She Jin Ping"})
        stale = await client.request("DELETE", f"{DICTIONARY}/entries", json={"revision": 1, "written": "Jokic"})
        view = (await client.get(DICTIONARY)).json()

    assert stale.status_code == 409 and "now revision 2" in stale.json()["error"]
    assert "Jokic" in said_as(view)


async def test_a_word_already_in_the_dictionary_or_missing_from_it_is_refused_with_a_reason(tmp_path: Path) -> None:
    async with client_for(tmp_path, FakeKokoro()) as client:
        repeated = await client.put(f"{DICTIONARY}/entries", json={"revision": 1, "written": "JOKIC", "say_as": "Joe-kitch"})
        missing = await client.request("DELETE", f"{DICTIONARY}/entries", json={"revision": 1, "written": "Embiid"})
        blank = await client.put(f"{DICTIONARY}/entries", json={"revision": 1, "written": "Embiid", "say_as": ""})

    assert (repeated.status_code, repeated.json()["error"]) == (422, "“JOKIC” is already in the dictionary; edit that entry instead")
    assert missing.status_code == 404
    assert blank.status_code == 422 and blank.json()["error"].startswith("say_as:")


async def test_restoring_a_version_saves_it_again_as_the_newest_revision(tmp_path: Path) -> None:
    async with client_for(tmp_path, FakeKokoro()) as client:
        await client.put(f"{DICTIONARY}/entries", json={"revision": 1, "written": "Xi Jinping", "say_as": "She Jin Ping"})
        await client.request("DELETE", f"{DICTIONARY}/entries", json={"revision": 2, "written": "Jokic"})
        restored = (await client.post(f"{DICTIONARY}/restore", json={"revision": 3, "version": 2})).json()
        gone = await client.post(f"{DICTIONARY}/restore", json={"revision": 4, "version": 1})

    assert restored["revision"] == 4
    assert said_as(restored) == {"Jokic": "Yo-Kich", "Nvidia": "N-Vidia", "Xi Jinping": "She Jin Ping"}
    assert restored["history"][0]["changes"] == ["+ Jokic → Yo-Kich"]
    assert gone.status_code == 404


async def test_a_word_is_heard_as_typed_before_and_respelled_with_the_unsaved_entry_after(tmp_path: Path) -> None:
    kokoro = FakeKokoro()
    async with client_for(tmp_path, kokoro) as client:
        before = await client.post(f"{DICTIONARY}/preview", json={"text": "Xi Jinping met Jokic.", "respell": False})
        candidate = {"revision": 1, "written": "Xi Jinping", "say_as": "She Jin Ping"}
        after = await client.post(f"{DICTIONARY}/preview", json={"text": "Xi Jinping met Jokic.", "respell": True, "candidate": candidate})
        view = (await client.get(DICTIONARY)).json()

    assert (before.status_code, before.headers["content-type"], before.content) == (200, "audio/wav", b"RIFF-fake-wav")
    assert kokoro.heard == [("Xi Jinping met Jokic.", "bm_fable"), ("She Jin Ping met Yo-Kich.", "bm_fable")]
    assert unquote(after.headers["x-spoken-text"]) == "She Jin Ping met Yo-Kich."
    assert view["revision"] == 1 and "Xi Jinping" not in said_as(view)


async def test_a_preview_says_why_when_the_voice_server_is_down(tmp_path: Path) -> None:
    async def refuses(_text: str, _voice: str) -> bytes:
        raise ConnectionRefusedError("Connect call failed ('127.0.0.1', 10210)")

    store = ExchangeStore(ExchangeLog(tmp_path / "exchanges"), TraceLog(tmp_path / "traces"), PipelineRunLog(tmp_path / "pipeline_runs"))
    access = access_in(tmp_path, FakeKokoro())
    app = build_app(store, ["mac.lan:8775"], pronunciations=PronunciationAccess(speakers={"kokoro": refuses}, live_dir=access.live_dir, versioned_dir=access.versioned_dir))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mac.lan:8775", headers=SAME_SITE) as client:
        down = await client.post(f"{DICTIONARY}/preview", json={"text": "Jokic", "respell": True})

    assert down.status_code == 503 and down.json()["error"].startswith("kokoro did not answer on this Mac: ConnectionRefusedError")


async def test_another_site_cannot_change_the_dictionary(tmp_path: Path) -> None:
    async with client_for(tmp_path, FakeKokoro()) as client:
        refused = await client.put(f"{DICTIONARY}/entries", json={"revision": 1, "written": "Xi", "say_as": "She"}, headers={"origin": "http://evil.example"})
        view = (await client.get(DICTIONARY)).json()

    assert refused.status_code == 421
    assert view["revision"] == 1
