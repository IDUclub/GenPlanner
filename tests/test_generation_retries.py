import pytest
from fastapi import HTTPException

from app.gen_planner.gen_planner_service import TERRITORY_TOO_SMALL_MSG, GenPlannerService


class RaisingGenPlanner:
    def __init__(self, error: Exception):
        self._error = error
        self.calls = 0

    def features2terr_zones2blocks(self, **kwargs):
        self.calls += 1
        raise self._error


@pytest.mark.asyncio
async def test_no_roads_generated_is_not_retried_and_reported_as_too_small():
    genplanner = RaisingGenPlanner(AttributeError("'DataFrame' object has no attribute 'to_crs'"))

    with pytest.raises(HTTPException) as exc_info:
        await GenPlannerService._run_features_generation_with_retries(
            genplanner=genplanner, funczone="recreation", attempts=3, delay_seconds=0
        )

    assert genplanner.calls == 1
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["msg"] == TERRITORY_TOO_SMALL_MSG


@pytest.mark.asyncio
async def test_other_failures_are_still_retried():
    genplanner = RaisingGenPlanner(RuntimeError("core panicked"))

    with pytest.raises(RuntimeError):
        await GenPlannerService._run_features_generation_with_retries(
            genplanner=genplanner, funczone="recreation", attempts=3, delay_seconds=0
        )

    assert genplanner.calls == 3
