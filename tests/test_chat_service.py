from typing import Any

import geopandas as gpd
import pytest
from pydantic import ValidationError
from shapely.geometry import box

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


class FakeUrbanApiClient:
    async def get_scenario_info(self, scenario_id, token):
        return {"project": {"project_id": 7}}


class FakeGenPlannerService:
    """Does what restore_params does to the dto: sets the project boundary on it."""

    def __init__(self, boundary: gpd.GeoDataFrame):
        self.urban_api_client = FakeUrbanApiClient()
        self._boundary = boundary
        self.calls: list[Any] = []

    async def run_func_generation(self, params, token, config):
        self.calls.append(params)
        params._territory_gdf = self._boundary  # pylint: disable=protected-access
        return FakeGenPlannerResult()


class FakeGenPlannerResult:
    def model_dump(self):
        empty_collection = {"type": "FeatureCollection", "features": []}
        return {"zones": empty_collection, "roads": empty_collection}


async def test_result_carries_the_project_boundary_in_wgs84():
    """The frontend draws the generation boundary from `result`, not from its own project data."""

    boundary = gpd.GeoDataFrame({"name": ["проект"]}, geometry=[box(30.0, 59.0, 30.1, 59.1)], crs=4326)
    llm = FakeChatClient([{"action": "run_generation", "patch": {"territory_balance": {"жилая": 1.0}}, "reply": "ok"}])

    events = await _collect(
        stream_chat_turn(
            llm_client=llm,
            chat_storage_client=None,
            genplanner_service=FakeGenPlannerService(boundary.to_crs(32636)),
            config=None,
            token="token",
            user_id=None,
            scenario_id=_SCENARIO_ID,
            params=ChatTurnDTO(user_query="запускай"),
        )
    )

    result = next(event for event in events if event["type"] == "result")
    territory = gpd.GeoDataFrame.from_features(result["territory"]["features"], crs=4326)
    assert len(territory) == 1
    assert territory.geometry.iloc[0].equals_exact(boundary.geometry.iloc[0], tolerance=1e-6)
    assert result["territory"]["features"][0]["properties"] == {}


class FakeChatStorageClient:
    """In-memory stand-in for ChatStorageClient, mirroring its create_chat/get_chat/add_message contract."""

    def __init__(self):
        self.chats: dict[str, dict[str, Any]] = {}

    async def create_chat(self, user_id, *, title=None, scenario_id=None, project_id=None, metadata=None):
        chat_id = f"chat-{len(self.chats) + 1}"
        self.chats[chat_id] = {"chat_id": chat_id, "messages": []}
        return {"chat_id": chat_id, "title": title}

    async def get_chat(self, user_id, chat_id):
        return self.chats[chat_id]

    async def add_message(self, user_id, chat_id, *, role, content=None, parts=None, metadata=None):
        self.chats[chat_id]["messages"].append({"role": role, "content": content, "metadata": metadata or {}})
        return {"message_id": f"msg-{len(self.chats[chat_id]['messages'])}"}


async def _stored_turn(llm_client, storage: FakeChatStorageClient, params: ChatTurnDTO) -> list[dict[str, Any]]:
    return await _collect(
        stream_chat_turn(
            llm_client=llm_client,
            chat_storage_client=storage,
            genplanner_service=None,
            config=None,
            token="token",
            user_id="user",
            scenario_id=_SCENARIO_ID,
            params=params,
        )
    )


async def test_done_carries_the_pairs_the_frontend_sent():
    """The frontend keeps its matrix in sync with the chat from `done`, not from its own last request."""

    llm = FakeChatClient([{"action": "chat", "reply": "учёл"}])

    events = await _collect(
        stream_chat_turn(
            llm_client=llm,
            chat_storage_client=None,
            genplanner_service=None,
            config=None,
            token="token",
            user_id=None,
            scenario_id=_SCENARIO_ID,
            params=ChatTurnDTO(user_query="учти матрицу", neighbour_pairs=[[1, 2]], forbidden_pairs=[[1, 6]]),
        )
    )

    done = events[-1]
    assert done["type"] == "done"
    assert done["neighbour_pairs"] == [[1, 2]]
    assert done["forbidden_pairs"] == [[1, 6]]


async def test_done_carries_empty_pairs_when_nothing_is_set():
    events = await _turn(FakeChatClient([{"action": "chat", "reply": "привет"}]), user_query="привет")

    assert events[-1]["neighbour_pairs"] == []
    assert events[-1]["forbidden_pairs"] == []


async def test_done_carries_pairs_the_model_parsed_from_text():
    """Without a matrix in the request, `done` is how the frontend learns what the text changed."""

    llm = FakeChatClient([{"action": "chat", "reply": "ок", "patch": {"forbidden_pairs": [["жилая", "промышленная"]]}}])

    events = await _turn(llm, user_query="промку подальше от жилья")

    assert events[-1]["forbidden_pairs"] == [[1, 4]]
    assert events[-1]["neighbour_pairs"] == []


async def test_request_pairs_override_what_the_model_parsed_on_the_same_turn():
    llm = FakeChatClient(
        [
            {
                "action": "chat",
                "reply": "ок",
                "patch": {
                    "territory_balance": {"жилая": 1.0},
                    "forbidden_pairs": [["жилая", "промышленная"]],
                },
            }
        ]
    )

    events = await _collect(
        stream_chat_turn(
            llm_client=llm,
            chat_storage_client=None,
            genplanner_service=None,
            config=None,
            token="token",
            user_id=None,
            scenario_id=_SCENARIO_ID,
            params=ChatTurnDTO(user_query="промку подальше", forbidden_pairs=[[1, 6]]),
        )
    )

    assert events[-1]["forbidden_pairs"] == [[1, 6]]


async def test_model_sees_request_pairs_in_the_system_prompt():
    """Otherwise the model tells the user no neighbourhood is set while the matrix says otherwise."""

    llm = FakeChatClient([{"action": "chat", "reply": "ок"}])

    await _collect(
        stream_chat_turn(
            llm_client=llm,
            chat_storage_client=None,
            genplanner_service=None,
            config=None,
            token="token",
            user_id=None,
            scenario_id=_SCENARIO_ID,
            params=ChatTurnDTO(user_query="что по соседству?", neighbour_pairs=[[1, 2]]),
        )
    )

    system_prompt = llm.calls[0]["messages"][0]["content"]
    assert '"neighbour_pairs": [["жилая", "рекреационная"]]' in system_prompt


async def test_request_pairs_reach_the_generation_call():
    boundary = gpd.GeoDataFrame({"name": ["проект"]}, geometry=[box(30.0, 59.0, 30.1, 59.1)], crs=4326)
    service = FakeGenPlannerService(boundary)
    llm = FakeChatClient(
        [{"action": "run_generation", "patch": {"territory_balance": {"жилая": 0.5, "рекреационная": 0.5}}}]
    )

    await _collect(
        stream_chat_turn(
            llm_client=llm,
            chat_storage_client=None,
            genplanner_service=service,
            config=None,
            token="token",
            user_id=None,
            scenario_id=_SCENARIO_ID,
            params=ChatTurnDTO(user_query="запускай", neighbour_pairs=[[1, 2]], forbidden_pairs=[]),
        )
    )

    dto = service.calls[0]
    assert dto.neighbour_pairs == [(1, 2)]
    assert dto.forbidden_pairs == []


async def test_pairs_sent_once_are_kept_for_later_turns():
    storage = FakeChatStorageClient()
    llm = FakeChatClient([{"action": "chat", "reply": "учёл"}, {"action": "chat", "reply": "ок"}])

    first = await _stored_turn(llm, storage, ChatTurnDTO(user_query="учти матрицу", neighbour_pairs=[[1, 2]]))
    chat_id = first[-1]["chat_id"]
    second = await _stored_turn(llm, storage, ChatTurnDTO(user_query="дальше", chat_id=chat_id))

    assert second[-1]["neighbour_pairs"] == [[1, 2]]


async def test_empty_list_resets_pairs_kept_in_history():
    storage = FakeChatStorageClient()
    llm = FakeChatClient([{"action": "chat", "reply": "учёл"}, {"action": "chat", "reply": "сбросил"}])

    first = await _stored_turn(llm, storage, ChatTurnDTO(user_query="матрица", forbidden_pairs=[[1, 6]]))
    chat_id = first[-1]["chat_id"]
    second = await _stored_turn(llm, storage, ChatTurnDTO(user_query="сбрось", chat_id=chat_id, forbidden_pairs=[]))

    assert second[-1]["forbidden_pairs"] == []


async def test_pairs_survive_a_turn_where_the_model_failed():
    """The assistant reply carrying the draft is never stored when the LLM call fails."""

    storage = FakeChatStorageClient()

    first = await _stored_turn(
        FailingChatClient(LLMChatError("boom")),
        storage,
        ChatTurnDTO(user_query="учти матрицу", neighbour_pairs=[[1, 2]]),
    )
    chat_id = first[-1]["chat_id"]
    second = await _stored_turn(
        FakeChatClient([{"action": "chat", "reply": "ок"}]), storage, ChatTurnDTO(user_query="ещё раз", chat_id=chat_id)
    )

    assert first[-1]["neighbour_pairs"] == [[1, 2]]
    assert second[-1]["neighbour_pairs"] == [[1, 2]]


def test_unknown_zone_ids_in_request_pairs_are_rejected():
    with pytest.raises(ValidationError, match=r"Unknown territorial zone ids: \[999\]"):
        ChatTurnDTO(user_query="матрица", neighbour_pairs=[[1, 999]])


def test_request_without_pairs_keeps_the_old_contract():
    params = ChatTurnDTO.model_validate({"user_query": "привет", "chat_id": None, "test": False})

    assert params.neighbour_pairs is None
    assert params.forbidden_pairs is None
