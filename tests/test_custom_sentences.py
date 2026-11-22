"""The custom sentences studio_assistant installs, matched the way Home Assistant 2026.9.1's default agent matches them: its built-in English
sentences with ours merged in, ours marked as custom, and the strict best match that prefers custom sentences (design doc v2/04 section 3.8)."""

from pathlib import Path

import home_assistant_intents
import pytest
import yaml
from hassil import Intents, recognize_best
from hassil.intents import TextSlotList
from hassil.util import merge_dict

from assistant_service.settings import load_harness_config
from scripts.deploy_component import CUSTOM_SENTENCES, install_custom_sentences
from utils.module_utils import module_from_file

SENTENCES_FILE = CUSTOM_SENTENCES / "en" / "studio_assistant.yaml"
CONST_PATH = Path(__file__).resolve().parent.parent / "custom_components" / "studio_assistant" / "const.py"
# Home Assistant's conversation/const.py: the metadata key it adds to every custom sentence, and the key recognize_best prefers
METADATA_CUSTOM_SENTENCE = "hass_custom_sentence"
SLOT_LISTS = {
    "name": TextSlotList.from_tuples([("Kitchen Light", "light.kitchen", {"domain": "light"}), ("Sean", "person.sean", {"domain": "person"})]),
    "area": TextSlotList.from_strings(["Kitchen", "Studio"]),
    "floor": TextSlotList.from_strings([]),
}


def load_const() -> object:
    return module_from_file("studio_assistant_const", CONST_PATH)


def intents_with_custom_sentences(custom: dict | None) -> Intents:
    """default_agent's async_get_or_load_intents: built-in sentences, then each custom file merged in with every data block marked as custom."""
    intents_dict = home_assistant_intents.get_intents("en")
    if custom:
        for intent in custom["intents"].values():
            for block in intent["data"]:
                block.setdefault("metadata", {})[METADATA_CUSTOM_SENTENCE] = True
        merge_dict(intents_dict, custom)
    return Intents.from_dict(intents_dict)


def matched_intent(intents: Intents, text: str) -> tuple[str, bool]:
    """default_agent's _recognize_strict: the intent name, and whether a custom sentence matched."""
    result = recognize_best(text, intents, slot_lists=SLOT_LISTS, language="en", best_metadata_key=METADATA_CUSTOM_SENTENCE, best_slot_name="name")
    return result.intent.name, bool((result.intent_metadata or {}).get(METADATA_CUSTOM_SENTENCE))


@pytest.fixture(scope="module")
def installed() -> Intents:
    return intents_with_custom_sentences(yaml.safe_load(SENTENCES_FILE.read_text()))


def test_without_our_sentences_home_assistant_takes_any_who_is_question_as_a_place() -> None:
    """The 2026-11-20 run: "Who is Hanashiro Anzu? Search the web." was answered "Not any" and never reached the agent."""
    assert matched_intent(intents_with_custom_sentences(None), "Who is Hanashiro Anzu? Search the web.") == ("HassGetState", False)


@pytest.mark.parametrize("question", ["Who is Hanashiro Anzu? Search the web.", "who is the president of France", "who is in the kitchen"])
def test_every_other_who_is_question_goes_to_the_agent(installed: Intents, question: str) -> None:
    assert matched_intent(installed, question) == (load_const().ASK_AGENT_INTENT, True)


@pytest.mark.parametrize("question", ["who is home", "who is at home"])
def test_who_is_home_keeps_home_assistants_own_answer(installed: Intents, question: str) -> None:
    assert matched_intent(installed, question) == ("HassGetState", True)


@pytest.mark.parametrize(
    ("question", "intent_name"),
    [("is the kitchen light on", "HassGetState"), ("turn on the kitchen light", "HassTurnOn"), ("where is Sean", "HassGetState")],
)
def test_device_questions_still_match_home_assistants_built_in_sentences(installed: Intents, question: str, intent_name: str) -> None:
    assert matched_intent(installed, question) == (intent_name, False)


def test_the_deploy_installs_the_sentences_where_home_assistant_reads_them(tmp_path: Path) -> None:
    assert install_custom_sentences(tmp_path) == [Path("custom_sentences/en/studio_assistant.yaml")]
    assert (tmp_path / "custom_sentences" / "en" / "studio_assistant.yaml").read_text() == SENTENCES_FILE.read_text()


@pytest.mark.parametrize("phrase", load_harness_config().answer.stop_phrases)
def test_every_stop_phrase_reaches_the_agent_rather_than_a_built_in_sentence(installed: Intents, phrase: str) -> None:
    """The harness answers these with silence (section 3.9); a built-in sentence catching one first would answer it instead."""
    assert recognize_best(phrase, installed, slot_lists=SLOT_LISTS, language="en", best_metadata_key=METADATA_CUSTOM_SENTENCE, best_slot_name="name") is None
