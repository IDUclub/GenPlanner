from typing import Any

import geopandas as gpd
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

    async def run_func_generation(self, params, token, config):
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
