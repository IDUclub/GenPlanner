# pylint: disable=protected-access,too-few-public-methods
import pandas as pd
import pytest
from fastapi import HTTPException

from app.gen_planner.gen_planner_service import (
    GENERATION_TIMEOUT_MSG,
    NON_FINITE_GENERATION_MSG,
    TERRITORY_TOO_SMALL_MSG,
    GenPlannerService,
)


class RaisingGenPlanner:
    """Count attempts while consistently failing generation with the given error."""

    def __init__(self, error: Exception):
        self._error = error
        self.calls = 0

    def features2terr_zones2blocks(self, **_kwargs):
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
async def test_non_finite_values_are_not_retried_and_reported_as_unprocessable():
    error = pd.errors.IntCastingNaNError("Cannot convert non-finite values (NA or inf) to integer")
    genplanner = RaisingGenPlanner(error)

    with pytest.raises(HTTPException) as exc_info:
        await GenPlannerService._run_features_generation_with_retries(
            genplanner=genplanner, funczone="residential", attempts=3, delay_seconds=0
        )

    assert genplanner.calls == 1
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["msg"] == NON_FINITE_GENERATION_MSG
    assert exc_info.value.detail["detail"] == {
        "reason": "non_finite_generation_values",
        "error": str(error),
    }
    assert exc_info.value.__cause__ is error


@pytest.mark.parametrize("error", [RuntimeError("core panicked"), ValueError("unrelated numeric error")])
@pytest.mark.asyncio
async def test_other_failures_are_still_retried(error):
    genplanner = RaisingGenPlanner(error)

    with pytest.raises(type(error)):
        await GenPlannerService._run_features_generation_with_retries(
            genplanner=genplanner, funczone="recreation", attempts=3, delay_seconds=0
        )

    assert genplanner.calls == 3


@pytest.mark.asyncio
async def test_generation_timeout_is_not_retried_and_reported():
    genplanner = RaisingGenPlanner(TimeoutError("GenPlanner generation time limit exceeded after 3 tasks"))

    with pytest.raises(HTTPException) as exc_info:
        await GenPlannerService._run_features_generation_with_retries(
            genplanner=genplanner, funczone="recreation", attempts=3, delay_seconds=0
        )

    assert genplanner.calls == 1
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["msg"] == GENERATION_TIMEOUT_MSG
    assert exc_info.value.detail["detail"]["reason"] == "generation_timeout"
