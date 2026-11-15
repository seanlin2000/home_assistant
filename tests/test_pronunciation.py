import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ops.deploy import plan_actions
from utils.pronunciation_utils import (
    HISTORY_VERSIONS_KEPT,
    VERSIONED_DIR,
    LivePronunciations,
    Pronunciation,
    PronunciationDictionary,
    PronunciationMatcher,
    PronunciationStore,
)

ENTRIES = [
    Pronunciation(written="Xi Jinping", say_as="She Jin Ping"),
    Pronunciation(written="Xi", say_as="She"),
    Pronunciation(written="Jokic", say_as="Yo-Kic"),
    Pronunciation(written="Nvidia", say_as="N-Vidia"),
]


def store_in(tmp_path: Path) -> PronunciationStore:
    return PronunciationStore("kokoro", "bm_fable", live_dir=tmp_path / "live", versioned_dir=tmp_path / "git")


def write_versioned(store: PronunciationStore, revision: int, entries: list[Pronunciation]) -> None:
    store.versioned_path.parent.mkdir(parents=True, exist_ok=True)
    store.versioned_path.write_text(PronunciationDictionary(model="kokoro", voice="bm_fable", revision=revision, entries=entries).model_dump_json())


def test_whole_words_are_respelled_whatever_their_case_or_accents() -> None:
    matcher = PronunciationMatcher(ENTRIES)

    assert matcher.respelled("NVIDIA and nvidia beat Jokić's Nuggets.") == "N-Vidia and N-Vidia beat Yo-Kic's Nuggets."


def test_the_longest_phrase_wins_and_words_inside_other_words_are_left_alone() -> None:
    matcher = PronunciationMatcher(ENTRIES)

    assert matcher.respelled("Xi  Jinping met Xi Mingze at Xiaomi.") == "She Jin Ping met She Mingze at Xiaomi."


def test_a_say_as_form_between_slashes_is_handed_to_kokoro_as_phonemes() -> None:
    matcher = PronunciationMatcher([Pronunciation(written="Jokic", say_as="/jˈOkɪʧ/")])

    assert matcher.respelled("Jokic scored.") == "[Jokic](/jˈOkɪʧ/) scored."


def test_an_empty_dictionary_leaves_the_sentence_alone() -> None:
    assert PronunciationMatcher([]).respelled("Jokic scored.") == "Jokic scored."


def test_a_written_form_may_appear_only_once() -> None:
    with pytest.raises(ValidationError, match="repeated"):
        PronunciationDictionary(model="kokoro", voice="bm_fable", revision=1, entries=[*ENTRIES, Pronunciation(written="jokić", say_as="Joe-kitch")])


def test_each_save_is_the_next_revision_and_only_the_newest_ten_versions_are_kept(tmp_path: Path) -> None:
    store = store_in(tmp_path)
    for count in range(1, 13):
        store.save(ENTRIES[: count % 4 + 1])

    assert store.load().revision == 12
    assert [path.name[:7] for path in store.history_paths()] == [f"r{revision:06d}" for revision in range(3, 13)]
    assert len(store.history_paths()) == HISTORY_VERSIONS_KEPT


def test_the_live_copy_is_read_first_then_its_newest_version_then_gits(tmp_path: Path) -> None:
    store = store_in(tmp_path)
    assert store.load().revision == 0
    write_versioned(store, revision=1, entries=ENTRIES)
    assert store.load().revision == 1

    store.save(ENTRIES[:2])
    store.save(ENTRIES[:3])
    assert (store.load().revision, len(store.load().entries)) == (3, 3)

    store.live_path.unlink()
    assert (store.load().revision, len(store.load().entries)) == (3, 3)


def test_a_deleted_entry_never_comes_back_from_gits_older_copy(tmp_path: Path) -> None:
    store = store_in(tmp_path)
    write_versioned(store, revision=1, entries=ENTRIES)
    store.save([entry for entry in store.load().entries if entry.written != "Jokic"])
    store.live_path.unlink()

    assert "Jokic" not in [entry.written for entry in store.load().entries]


def test_the_voice_hears_a_save_from_the_next_sentence_and_keeps_its_matcher_when_the_file_breaks(tmp_path: Path) -> None:
    store = store_in(tmp_path)
    pronunciations = LivePronunciations(store)
    store.save(ENTRIES[2:3])
    pronunciations.refresh()
    assert pronunciations.matcher.respelled("Jokic and Nvidia.") == "Yo-Kic and Nvidia."

    store.save(ENTRIES[2:4])
    pronunciations.refresh()
    assert pronunciations.matcher.respelled("Jokic and Nvidia.") == "Yo-Kic and N-Vidia."

    store.live_path.write_text("{not json")
    pronunciations.refresh()
    assert pronunciations.matcher.respelled("Jokic and Nvidia.") == "Yo-Kic and N-Vidia."


def test_the_checked_in_dictionary_reads_and_starts_with_the_three_known_words() -> None:
    dictionary = PronunciationDictionary.model_validate(json.loads((VERSIONED_DIR / "kokoro" / "bm_fable.json").read_text()))

    assert {entry.written: entry.say_as for entry in dictionary.entries} == {"Jokic": "Yo-Kic", "Nvidia": "N-Vidia", "Xi Jinping": "She Jin Ping"}


def test_a_deploy_restarts_kokoro_for_the_dictionary_code_but_never_touches_the_dictionary() -> None:
    assert plan_actions(["config/pronunciations/kokoro/bm_fable.json"]).actions == []
    assert "restart:kokoro" in plan_actions(["utils/pronunciation_utils.py"]).actions
