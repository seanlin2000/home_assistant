"""Constants shared by the config flow and the conversation entity."""

DOMAIN = "studio_assistant"

CONF_OLLAMA_URL = "ollama_url"
CONF_MODEL = "model"
CONF_MCP_URL = "mcp_url"
CONF_TEMPERATURE = "temperature"
CONF_WORD_BUDGET = "word_budget"
CONF_MAX_TOOL_ROUNDS = "max_tool_rounds"
CONF_CONTEXT_TOKENS = "context_tokens"
CONF_MAX_OUTPUT_TOKENS = "max_output_tokens"
CONF_THINK = "think"
CONF_TOOL_TIMEOUT = "tool_timeout_seconds"
CONF_CONTINUE_CONVERSATION = "continue_conversation"

DEFAULT_OLLAMA_URL = "http://192.168.1.152:11434"
DEFAULT_MODEL = "gemma4:e4b-it-qat"
DEFAULT_MCP_URL = "http://192.168.1.152:8765/mcp"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_WORD_BUDGET = 200
DEFAULT_MAX_TOOL_ROUNDS = 4
DEFAULT_CONTEXT_TOKENS = 16384
DEFAULT_MAX_OUTPUT_TOKENS = 600
DEFAULT_THINK = False
DEFAULT_TOOL_TIMEOUT = 60.0
DEFAULT_CONTINUE_CONVERSATION = True
