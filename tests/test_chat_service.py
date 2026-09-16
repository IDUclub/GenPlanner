from typing import Any

from app.chat.chat_common import DECISION_TEMPERATURE, LLM_ERROR_MESSAGE_RU
from app.chat.chat_service import stream_chat_turn
from app.chat.dto.chat_dto import ChatTurnDTO
from app.common.llm.chat_client import LLMChatError

_SCENARIO_ID = 1


class FakeChatClient:
    def __init__(self, decisions: list[dict[str, Any]]):
        self._decisions = list(decisions)
        self.calls: list[dict[str, Any]] = []

    async def complete_json(self, messages, schema, temperature=None):
        self.calls.append({"messages": messages, "schema": schema, "temperature": temperature})
        return self._decisions.pop(0)


class FailingChatClient:
    """Chat client stand-in whose decision call always fails, the way an empty vLLM answer does."""

    def __init__(self, error: LLMChatError):
        self._error = error

    async def complete_json(self, messages, schema, temperature=None):
        raise self._error


async def _collect(agen):
    return [item async for item in agen]


async def _turn(llm_client, user_query: str = "да") -> list[dict[str, Any]]:
    """One turn without ChatStorage, so nothing but the decision step is exercised."""

    return await _collect(
        stream_chat_turn(
            llm_client=llm_client,
            chat_storage_client=None,
            genplanner_service=None,
            config=None,
            token="token",
            user_id=None,
            scenario_id=_SCENARIO_ID,
            params=ChatTurnDTO(user_query=user_query),
        )
    )


async def test_decision_call_pins_the_sampling_temperature():
    """Left at the server default, the same turn gets a different action every other time."""

    llm = FakeChatClient([{"action": "chat", "reply": "привет"}])

    await _turn(llm, user_query="привет")

    assert llm.calls[0]["temperature"] == DECISION_TEMPERATURE


async def test_llm_failure_carries_a_ready_made_message_for_the_user():
    """The raw backend error used to be the only text the frontend had to show."""

    raw = "vLLM returned no message content: finish_reason='stop', reasoning='Ready.'"

    events = await _turn(FailingChatClient(LLMChatError(raw)))

    error = next(event for event in events if event["type"] == "error")
    assert error["stage"] == "llm"
    assert error["message"] == LLM_ERROR_MESSAGE_RU
    assert error["detail"] == raw
    assert events[-1]["type"] == "done"
