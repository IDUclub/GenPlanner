from iduconfig import Config

from app.common.config_utils import get_optional_config
from app.common.llm.chat_client import ChatClient
from app.common.llm.ollama_chat_client import build_ollama_chat_client
from app.common.llm.vllm_chat_client import build_vllm_chat_client

PROVIDER_VLLM = "vllm"
PROVIDER_OLLAMA = "ollama"
DEFAULT_PROVIDER = PROVIDER_VLLM


def build_chat_client(config: Config) -> ChatClient | None:
    """
    Build the chat-completions client for the provider named by LLM_PROVIDER
    (`vllm` by default, `ollama` for the legacy backend).

    Returns None when the selected provider's base URL or model name is missing, which
    keeps the chat feature disabled instead of failing startup. An unknown provider name
    is a configuration error and raises, so a typo doesn't silently disable chat.
    """

    provider = (get_optional_config(config, "LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()

    if provider == PROVIDER_VLLM:
        return build_vllm_chat_client(config)
    if provider == PROVIDER_OLLAMA:
        return build_ollama_chat_client(config)

    raise ValueError(f"Unsupported LLM_PROVIDER {provider!r}, expected one of: {PROVIDER_VLLM}, {PROVIDER_OLLAMA}")
