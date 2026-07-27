import pytest

from app.mcp_server.api_client import GenPlannerApiClient, GenPlannerApiError
from tests.mcp_server.conftest import FakeResponse


@pytest.fixture
def client():
    return GenPlannerApiClient("http://genplanner-test:80")


async def test_get_builds_url_and_returns_json(client, patch_client_session):
    session = patch_client_session(FakeResponse(200, json_body={"1": 0.5}))

    result = await client.get("/genplanner/default/func_ratio", params={"zone": 1})

    assert result == {"1": 0.5}
    call = session.request_calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "http://genplanner-test:80/genplanner/default/func_ratio"
    assert call["params"] == {"zone": 1}


async def test_post_sends_params_and_json_body(client, patch_client_session):
    session = patch_client_session(FakeResponse(200, json_body={"zones": {}, "roads": {}}))

    result = await client.post(
        "/genplanner/run_func_generation",
        params={"project_id": 1, "scenario_id": 2},
        json_body={"territory_balance": {1: 0.5, 2: 0.5}},
        headers={"Authorization": "Bearer token"},
    )

    assert result == {"zones": {}, "roads": {}}
    call = session.request_calls[0]
    assert call["method"] == "POST"
    assert call["params"] == {"project_id": 1, "scenario_id": 2}
    assert call["json"] == {"territory_balance": {1: 0.5, 2: 0.5}}
    assert call["headers"] == {"Authorization": "Bearer token"}


async def test_post_stringifies_bool_query_params_for_aiohttp(client, patch_client_session):
    session = patch_client_session(FakeResponse(200, json_body={}))

    await client.post(
        "/genplanner/run_func_generation",
        params={"project_id": 1, "ignore_default_relations": False, "test": True},
        json_body={"territory_balance": {1: 1.0}},
    )

    call = session.request_calls[0]
    assert call["params"] == {"project_id": 1, "ignore_default_relations": "false", "test": "true"}


async def test_non_2xx_raises_genplanner_api_error_with_json_body(client, patch_client_session):
    patch_client_session(FakeResponse(422, json_body={"msg": "bad zone id", "input": {}, "detail": None}))

    with pytest.raises(GenPlannerApiError) as exc_info:
        await client.get("/genplanner/gen_planner/zones_list")

    assert exc_info.value.status == 422
    assert exc_info.value.body == {"msg": "bad zone id", "input": {}, "detail": None}


async def test_non_2xx_falls_back_to_text_body_on_bad_content_type(client, patch_client_session):
    patch_client_session(FakeResponse(500, text_body="internal error", bad_content_type=True))

    with pytest.raises(GenPlannerApiError) as exc_info:
        await client.get("/genplanner/default_matrix")

    assert exc_info.value.status == 500
    assert exc_info.value.body == "internal error"
