import pytest

from app.common.llm.factory import build_chat_client
from app.common.llm.ollama_chat_client import OllamaChatClient
from app.common.llm.vllm_chat_client import VllmChatClient
from tests.llm.conftest import FakeConfig

VLLM_ENV = {"VLLM_BASE_URL": "http://vllm-test:8001", "CHAT_MODEL": "gpt-oss-20b"}
OLLAMA_ENV = {"OLLAMA_BASE_URL": "http://ollama-test:11434", "CHAT_MODEL": "gpt-oss:20b"}


def test_defaults_to_vllm_when_provider_not_set():
    client = build_chat_client(FakeConfig(VLLM_ENV))

    assert isinstance(client, VllmChatClient)
    assert client.base_url == "http://vllm-test:8001"
    assert client.default_model == "gpt-oss-20b"


@pytest.mark.parametrize("provider", ["vllm", " VLLM "])
def test_builds_vllm_client_for_vllm_provider(provider):
    assert isinstance(build_chat_client(FakeConfig({**VLLM_ENV, "LLM_PROVIDER": provider})), VllmChatClient)


@pytest.mark.parametrize("provider", ["ollama", " Ollama "])
def test_builds_ollama_client_for_ollama_provider(provider):
    client = build_chat_client(FakeConfig({**OLLAMA_ENV, "LLM_PROVIDER": provider}))

    assert isinstance(client, OllamaChatClient)
    assert client.base_url == "http://ollama-test:11434"


def test_falls_back_to_generate_model_when_chat_model_missing():
    config = FakeConfig({"VLLM_BASE_URL": "http://vllm-test:8001", "GENERATE_MODEL": "gpt-oss-20b"})

    assert build_chat_client(config).default_model == "gpt-oss-20b"


@pytest.mark.parametrize(
    "values",
    [
        {"CHAT_MODEL": "gpt-oss-20b"},
        {"VLLM_BASE_URL": "http://vllm-test:8001"},
        {"LLM_PROVIDER": "ollama", "CHAT_MODEL": "gpt-oss:20b"},
    ],
)
def test_returns_none_when_provider_is_not_fully_configured(values):
    assert build_chat_client(FakeConfig(values)) is None


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        build_chat_client(FakeConfig({**VLLM_ENV, "LLM_PROVIDER": "openai"}))
