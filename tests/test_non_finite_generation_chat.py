# pylint: disable=protected-access,too-few-public-methods
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.chat.chat_controller import _as_sse_events
from app.chat.chat_service import stream_chat_turn
from app.chat.custom_chat_service import stream_custom_chat_turn
from app.chat.dto.chat_custom_dto import ChatCustomTurnDTO
from app.chat.dto.chat_dto import ChatTurnDTO
from app.common.geometries_dto.geometries import PolygonalFeatureCollection
from app.gen_planner.gen_planner_service import NON_FINITE_GENERATION_MSG, GenPlannerService


class NonFiniteGenPlanner:
    """Trigger the real pandas failure seen when rounding undefined building counts."""

    def __init__(self, value):
        self.value = value
        self.calls = 0

    def features2terr_zones2blocks(self, **_kwargs):
        self.calls += 1
        return pd.Series([self.value]).astype(int)


@pytest.mark.parametrize("value", [float("nan"), float("inf")], ids=["nan", "inf"])
@pytest.mark.parametrize("custom", [False, True], ids=["scenario", "custom"])
async def test_non_finite_generation_finishes_sse_with_an_actionable_message(value, custom):
    genplanner = NonFiniteGenPlanner(value)

    async def run_generation(*_args, **_kwargs):
        return await GenPlannerService._run_features_generation_with_retries(
            genplanner=genplanner, funczone="residential", delay_seconds=0
        )

    service = SimpleNamespace(
        urban_api_client=SimpleNamespace(get_scenario_info=AsyncMock(return_value={"project": {"project_id": 72}})),
        run_func_generation=run_generation,
        run_custom_func_generation=run_generation,
    )
    patch = {"profile": "жилая"} if custom else {"territory_balance": {"жилая": 1.0}}
    llm = SimpleNamespace(
        complete_json=AsyncMock(return_value={"action": "run_generation", "patch": patch, "reply": "Запускаю!"})
    )
    kwargs = {"llm_client": llm, "chat_storage_client": None, "genplanner_service": service, "user_id": None}
    if custom:
        territory = PolygonalFeatureCollection.model_validate(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[30, 59], [30.01, 59], [30.01, 59.01], [30, 59.01], [30, 59]]],
                        },
                        "properties": {},
                    }
                ],
            }
        )
        stream = stream_custom_chat_turn(
            **kwargs, territory=territory, params=ChatCustomTurnDTO(user_query="жилая, запускай")
        )
    else:
        stream = stream_chat_turn(
            **kwargs, scenario_id=123, token="token", config=None, params=ChatTurnDTO(user_query="жилая, запускай")
        )

    events = [event async for event in _as_sse_events(stream)]
    payloads = [json.loads(event["data"]) for event in events]
    warning = next(event for event in payloads if event["type"] == "warning")
    reply = "".join(event["content"] for event in payloads if event["type"] == "token")

    assert warning["stage"] == "run_generation"
    assert warning["detail"]["detail"]["reason"] == "non_finite_generation_values"
    assert NON_FINITE_GENERATION_MSG in reply
    assert "Запускаю!" not in reply
    assert not any(event["event"] in {"result", "file"} for event in events)
    assert events[-1]["event"] == "done"
    assert genplanner.calls == 1
