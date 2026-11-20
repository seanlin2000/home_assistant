"""Constants shared by the config flow and the conversation entity."""

DOMAIN = "studio_assistant"

CONF_HARNESS_URL = "harness_url"
CONF_HARNESS_API_KEY = "harness_api_key"
CONF_CONTINUE_CONVERSATION = "continue_conversation"
CONF_MAX_FOLLOW_UPS = "max_follow_ups"

DEFAULT_HARNESS_URL = "http://192.168.1.152:8770"
DEFAULT_CONTINUE_CONVERSATION = True
DEFAULT_MAX_FOLLOW_UPS = 2  # follow-ups heard without the wake word before it is needed again
