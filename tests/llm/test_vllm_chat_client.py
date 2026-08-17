import json

import pytest

from app.common.llm.chat_client import LLMChatError
from app.common.llm.vllm_chat_client import VllmChatClient, VllmChatError
from tests.llm.conftest import FakeResponse

SCHEMA = {"type": "object", "properties": {"action": {"type": "string"}}, "required": ["action"]}


def _message_response(content: str, **extra) -> FakeResponse:
    return FakeResponse(200, json_body={"choices": [{"message": {"role": "assistant", "content": content, **extra}}]})


def _sse(chunk: dict) -> bytes:
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n".encode()


@pytest.fixture
def client():
    return VllmChatClient("http://vllm-test:8001", "gpt-oss-20b")


@pytest.mark.parametrize(
    "base_url",
    ["http://vllm-test:8001", "http://vllm-test:8001/", "http://vllm-test:8001/v1", "http://vllm-test:8001/v1/"],
)
async def test_complete_json_targets_openai_path_regardless_of_v1_suffix(base_url, patch_client_session):
    session = patch_client_session(_message_response('{"action": "chat"}'))

    await VllmChatClient(base_url, "gpt-oss-20b").complete_json([{"role": "user", "content": "hi"}], schema=SCHEMA)

    assert session.post_calls[0]["url"] == "http://vllm-test:8001/v1/chat/completions"


async def test_complete_json_constrains_output_with_response_format(client, patch_client_session):
    session = patch_client_session(_message_response('{"action": "chat"}'))

    result = await client.complete_json([{"role": "user", "content": "hi"}], schema=SCHEMA, temperature=0.2)

    assert result == {"action": "chat"}
    payload = session.post_calls[0]["json"]
    assert payload["model"] == "gpt-oss-20b"
    assert payload["messages"] == [{"role": "user", "content": "hi"}]
    assert payload["stream"] is False
    assert payload["temperature"] == 0.2
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "response", "schema": SCHEMA},
    }


async def test_complete_json_omits_temperature_when_not_given(client, patch_client_session):
    session = patch_client_session(_message_response('{"action": "chat"}'))

    await client.complete_json([{"role": "user", "content": "hi"}], schema=SCHEMA)

    assert "temperature" not in session.post_calls[0]["json"]


async def test_complete_json_overrides_default_model(client, patch_client_session):
    session = patch_client_session(_message_response('{"action": "chat"}'))

    await client.complete_json([{"role": "user", "content": "hi"}], schema=SCHEMA, model="other-model")

    assert session.post_calls[0]["json"]["model"] == "other-model"


async def test_complete_json_recovers_object_wrapped_in_reasoning_text(client, patch_client_session):
    patch_client_session(_message_response('Let me think...\n```json\n{"action": "chat"}\n```\ndone'))

    assert await client.complete_json([{"role": "user", "content": "hi"}], schema=SCHEMA) == {"action": "chat"}


async def test_complete_json_raises_on_non_200(client, patch_client_session):
    patch_client_session(FakeResponse(400, text_body="no such model"))

    with pytest.raises(VllmChatError, match="returned 400"):
        await client.complete_json([{"role": "user", "content": "hi"}], schema=SCHEMA)


async def test_complete_json_raises_on_error_payload(client, patch_client_session):
    patch_client_session(FakeResponse(200, json_body={"error": {"message": "guided decoding failed"}}))

    with pytest.raises(VllmChatError, match="guided decoding failed"):
        await client.complete_json([{"role": "user", "content": "hi"}], schema=SCHEMA)


async def test_complete_json_raises_when_only_reasoning_content_returned(client, patch_client_session):
    patch_client_session(_message_response("", reasoning_content="thinking out loud"))

    with pytest.raises(VllmChatError, match="no message content"):
        await client.complete_json([{"role": "user", "content": "hi"}], schema=SCHEMA)


async def test_complete_json_error_is_catchable_as_llm_chat_error(client, patch_client_session):
    patch_client_session(_message_response("not json at all"))

    with pytest.raises(LLMChatError):
        await client.complete_json([{"role": "user", "content": "hi"}], schema=SCHEMA)


async def test_stream_chat_yields_content_deltas_only(client, patch_client_session):
    session = patch_client_session(
        FakeResponse(
            200,
            stream_lines=[
                b"\n",
                b": ping\n",
                _sse({"choices": [{"delta": {"role": "assistant"}}]}),
                _sse({"choices": [{"delta": {"content": "При"}}]}),
                _sse({"choices": [{"delta": {"reasoning_content": "thinking"}}]}),
                _sse({"choices": [{"delta": {"content": "вет"}}]}),
                b"data: {not json}\n",
                _sse({"choices": []}),
                b"data: [DONE]\n",
                _sse({"choices": [{"delta": {"content": "after done"}}]}),
            ],
        )
    )

    assert [piece async for piece in client.stream_chat([{"role": "user", "content": "hi"}])] == ["При", "вет"]
    assert session.post_calls[0]["json"]["stream"] is True


async def test_stream_chat_raises_on_error_chunk(client, patch_client_session):
    patch_client_session(FakeResponse(200, stream_lines=[_sse({"error": {"message": "engine died"}})]))

    with pytest.raises(VllmChatError, match="engine died"):
        async for _ in client.stream_chat([{"role": "user", "content": "hi"}]):
            pass


async def test_stream_chat_raises_on_non_200(client, patch_client_session):
    patch_client_session(FakeResponse(503, text_body="server overloaded"))

    with pytest.raises(VllmChatError, match="returned 503"):
        async for _ in client.stream_chat([{"role": "user", "content": "hi"}]):
            pass
