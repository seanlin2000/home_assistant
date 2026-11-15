import json
from pathlib import Path

import httpx
import pytest

from dashboard.pronunciation_views import DictionaryView
from ops.pronunciations import DictionaryPull, PullRefused, Skip, WordChange, dictionaries_from, diff_of, pull_decision, pull_request_body
from pr_references.lint import lint
from pr_references.references import find_references, mismatches
from utils.pronunciation_utils import Pronunciation, PronunciationDictionary, versioned_json

GIT_ENTRIES = [Pronunciation(written="Jokic", say_as="Yo-Kic"), Pronunciation(written="Nvidia", say_as="N-Vidia"), Pronunciation(written="Xi Jinping", say_as="She Jin Ping")]
LIVE_ENTRIES = [Pronunciation(written="Embiid", say_as="Em-beed"), Pronunciation(written="Jokic", say_as="Yo-Kich"), Pronunciation(written="Xi Jinping", say_as="She Jin Ping")]


def in_git(revision: int, entries: list[Pronunciation]) -> PronunciationDictionary:
    return PronunciationDictionary(model="kokoro", voice="bm_fable", revision=revision, entries=entries)


def studio_view(revision: int, entries: list[Pronunciation], source: str = "live") -> DictionaryView:
    return DictionaryView(model="kokoro", voice="bm_fable", revision=revision, source=source, entries=entries, git_revision=None, in_git=False, history=[])


def test_only_a_live_copy_with_words_git_lacks_is_pulled() -> None:
    assert isinstance(pull_decision(studio_view(2, GIT_ENTRIES, source="git"), in_git(2, GIT_ENTRIES)), Skip)
    assert isinstance(pull_decision(studio_view(5, GIT_ENTRIES), in_git(2, GIT_ENTRIES)), Skip)
    assert isinstance(pull_decision(studio_view(5, LIVE_ENTRIES), in_git(2, GIT_ENTRIES)), DictionaryPull)
    assert isinstance(pull_decision(studio_view(1, LIVE_ENTRIES, source="history"), None), DictionaryPull)


def test_git_changed_directly_at_or_past_the_live_revision_is_refused_so_the_pull_never_undoes_it() -> None:
    with pytest.raises(PullRefused, match="git's copy is at revision 3 .* live revision 3"):
        pull_decision(studio_view(3, LIVE_ENTRIES), in_git(3, GIT_ENTRIES))
    with pytest.raises(PullRefused, match="revision 4"):
        pull_decision(studio_view(3, LIVE_ENTRIES), in_git(4, GIT_ENTRIES))


def test_each_word_is_listed_once_as_added_changed_or_removed() -> None:
    pulled = DictionaryPull(live=in_git(5, LIVE_ENTRIES), in_git=in_git(2, GIT_ENTRIES))

    assert pulled.word_changes() == [
        WordChange("Embiid", "Em-beed", None),
        WordChange("Jokic", "Yo-Kich", "Yo-Kic"),
        WordChange("Nvidia", "N-Vidia", "N-Vidia", removed=True),
    ]
    assert diff_of([pulled]).splitlines()[:2] == ["--- a/config/pronunciations/kokoro/bm_fable.json", "+++ b/config/pronunciations/kokoro/bm_fable.json"]
    assert '-    {"written": "Nvidia", "say_as": "N-Vidia"},' in diff_of([pulled]).splitlines()


def test_the_pull_request_body_passes_pr_refs_check_and_lint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pulled = DictionaryPull(live=in_git(5, [*LIVE_ENTRIES, Pronunciation(written='The "Joker"', say_as="Yo-Kich")]), in_git=in_git(2, GIT_ENTRIES))
    (tmp_path / pulled.path).parent.mkdir(parents=True)
    (tmp_path / pulled.path).write_text(versioned_json(pulled.live))
    monkeypatch.chdir(tmp_path)

    body = pull_request_body([pulled], "192.168.1.162", tmp_path)

    assert lint(body) == []
    assert len(find_references(body)) == 4 and mismatches(find_references(body)) == []
    assert "## Kokoro · bm_fable (revision 2 to 5)" in body
    assert '**Changed Jokic.** Said as "Yo-Kich", was "Yo-Kic".' in body


def test_the_studio_dashboard_is_read_for_every_dictionary_it_lists() -> None:
    def studio(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/pronunciations":
            return httpx.Response(200, json=[{"model": "kokoro", "voice": "bm_fable"}])
        return httpx.Response(200, text=studio_view(5, LIVE_ENTRIES).model_dump_json())

    with httpx.Client(transport=httpx.MockTransport(studio), base_url="http://192.168.1.162:8775") as client:
        views = dictionaries_from(client)

    assert [(view.revision, len(view.entries)) for view in views] == [(5, 3)]
    assert json.loads(views[0].model_dump_json())["source"] == "live"
