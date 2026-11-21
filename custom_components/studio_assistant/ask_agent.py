"""The handler behind the custom "who is ..." sentence: it hands the question to the conversation agent instead of answering it (design doc v2/04
section 3.8)."""

from homeassistant.helpers import intent

from .const import ASK_AGENT_INTENT


class AskAgentIntentHandler(intent.IntentHandler):
    """Answers "no intent match" on purpose. With "prefer handling commands locally" on, Home Assistant 2026.9's async_handle_intents returns None for
    any error other than failed_to_handle or unknown, and the pipeline then sends the question to the agent with streaming and follow-ups as usual."""

    intent_type = ASK_AGENT_INTENT
    description = "Hands a question Home Assistant cannot answer to the Studio Assistant agent"

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        response = intent_obj.create_response()
        response.async_set_error(intent.IntentResponseErrorCode.NO_INTENT_MATCH, "")
        return response
