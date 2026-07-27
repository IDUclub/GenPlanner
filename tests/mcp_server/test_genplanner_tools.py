from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from app.mcp_server.api_client import GenPlannerApiError
from app.mcp_server.tools.genplanner_tools import register_tools


@pytest.fixture
def client():
    return AsyncMock(get=AsyncMock(), post=AsyncMock())


@pytest.fixture
def mcp(client):
    server = FastMCP("test")
    register_tools(server, client)
    return server


async def _tool_fn(mcp: FastMCP, name: str):
    tool = await mcp.get_tool(name)
    return tool.fn


async def test_list_available_zones_calls_zones_list_endpoint(mcp, client):
    client.get.return_value = [1, 2, 3]
    fn = await _tool_fn(mcp, "list_available_zones")

    result = await fn()

    assert result == [1, 2, 3]
    client.get.assert_awaited_once_with("/genplanner/gen_planner/zones_list")


async def test_get_func_zone_ratio_passes_zone_param(mcp, client):
    client.get.return_value = {"1": 0.5}
    fn = await _tool_fn(mcp, "get_func_zone_ratio")

    result = await fn(zone_id=1)

    assert result == {"1": 0.5}
    client.get.assert_awaited_once_with("/genplanner/default/func_ratio", params={"zone": 1})


async def test_get_default_forbidden_matrix_calls_default_matrix_endpoint(mcp, client):
    client.get.return_value = {"forbidden": []}
    fn = await _tool_fn(mcp, "get_default_forbidden_matrix")

    result = await fn()

    assert result == {"forbidden": []}
    client.get.assert_awaited_once_with("/genplanner/default_matrix")


async def test_run_func_generation_forwards_bearer_and_splits_query_and_body(mcp, client):
    client.post.return_value = {"zones": {}, "roads": {}}
    fn = await _tool_fn(mcp, "run_func_generation")

    result = await fn(
        project_id=1,
        scenario_id=2,
        territory_balance={6: 0.4, 2: 0.6},
        token="abc",
        neighbour_pairs=[(6, 2)],
        elevation_angle=5,
    )

    assert result == {"zones": {}, "roads": {}}
    client.post.assert_awaited_once_with(
        "/genplanner/run_func_generation",
        params={
            "project_id": 1,
            "scenario_id": 2,
            "ignore_default_relations": False,
            "test": False,
            "elevation_angle": 5,
        },
        json_body={"territory_balance": {6: 0.4, 2: 0.6}, "neighbour_pairs": [(6, 2)]},
        headers={"Authorization": "Bearer abc"},
    )


async def test_run_func_generation_wraps_api_error_as_tool_error(mcp, client):
    client.post.side_effect = GenPlannerApiError(422, {"msg": "unknown zone id"})
    fn = await _tool_fn(mcp, "run_func_generation")

    with pytest.raises(ToolError, match="unknown zone id"):
        await fn(project_id=1, scenario_id=2, territory_balance={1: 1.0}, token="abc")
