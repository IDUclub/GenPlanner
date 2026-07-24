from typing import Any, Coroutine

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError

from app.mcp_server.api_client import GenPlannerApiClient, GenPlannerApiError
from app.mcp_server.auth import extract_token


async def _call(coro: Coroutine[Any, Any, Any]) -> Any:
    try:
        return await coro
    except GenPlannerApiError as exc:
        raise ToolError(str(exc.body)) from exc


def register_tools(mcp: FastMCP, client: GenPlannerApiClient) -> None:
    """Register GenPlanner tools on `mcp`, backed by HTTP calls to `client`."""

    @mcp.tool
    async def list_available_zones() -> list[int]:
        """List the territorial zone IDs GenPlanner can generate."""

        return await _call(client.get("/genplanner/gen_planner/zones_list"))

    @mcp.tool
    async def get_func_zone_ratio(zone_id: int) -> dict[str, float]:
        """Get the default functional-zone-kind ratio breakdown for a territorial zone ID."""

        return await _call(client.get("/genplanner/default/func_ratio", params={"zone": zone_id}))

    @mcp.tool
    async def get_default_forbidden_matrix() -> Any:
        """Get GenPlanner's default forbidden-neighborhood relation matrix between zones."""

        return await _call(client.get("/genplanner/default_matrix"))

    @mcp.tool
    async def run_func_generation(
        project_id: int,
        scenario_id: int,
        territory_balance: dict[int, float],
        token: str = Depends(extract_token),
        *,
        neighbour_pairs: list[tuple[int, int]] | None = None,
        forbidden_pairs: list[tuple[int, int]] | None = None,
        min_block_area: dict[int, float] | None = None,
        elevation_angle: int | None = None,
        roads_extend_distance: float | None = None,
        ignore_default_relations: bool = False,
        test: bool = False,
    ) -> Any:
        """
        Run functional zone generation for a scenario and return zones/roads GeoJSON.

        territory_balance maps territorial zone ID -> target ratio (must sum sensibly,
        e.g. {6: 0.4, 2: 0.3, 3: 0.1, 7: 0.2}). neighbour_pairs/forbidden_pairs are
        symmetric zone ID pairs overriding the default relation matrix.
        """

        headers = {"Authorization": f"Bearer {token}"}
        params: dict[str, Any] = {
            "project_id": project_id,
            "scenario_id": scenario_id,
            "ignore_default_relations": ignore_default_relations,
            "test": test,
        }
        if elevation_angle is not None:
            params["elevation_angle"] = elevation_angle
        if roads_extend_distance is not None:
            params["roads_extend_distance"] = roads_extend_distance

        json_body: dict[str, Any] = {"territory_balance": territory_balance}
        if neighbour_pairs is not None:
            json_body["neighbour_pairs"] = neighbour_pairs
        if forbidden_pairs is not None:
            json_body["forbidden_pairs"] = forbidden_pairs
        if min_block_area is not None:
            json_body["min_block_area"] = min_block_area

        return await _call(
            client.post(
                "/genplanner/run_func_generation",
                params=params,
                json_body=json_body,
                headers=headers,
            )
        )
