from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from app.common.auth.bearer import verify_bearer_token
from app.common.constants.api_constants import scenario_func_zones_map, scenario_ter_zones_map
from app.gen_planner.dto.gen_planner_dto import GenPlannerFuncZonesDTO, GenPlannerTerZonesDTO
from app.gen_planner.schema.gen_planner_schema import GenPlannerResultSchema

from .gen_planner_service import gen_planner_service

gen_planner_router = APIRouter(tags=["gen_planner"])


@gen_planner_router.get("/gen_planner/territories_list", response_model=list[int])
async def get_available_territories_profiles():
    """
    :return: list of available territories zones to run in genplanner by ids
    """

    result = [i for i in scenario_ter_zones_map]
    return result


@gen_planner_router.get("/gen_planner/zones_list", response_model=list[int])
async def get_available_zones_profiles():
    """
    :return: list of available func zones to run in genplanner by ids
    """

    result = [i for i in scenario_func_zones_map]
    return result


@gen_planner_router.post("/run_ter_generation", response_model=GenPlannerResultSchema)
async def run_ter_territory_zones_generation(
    params: Annotated[GenPlannerTerZonesDTO, Depends(GenPlannerTerZonesDTO)], token: str = Depends(verify_bearer_token)
) -> GenPlannerResultSchema:

    return await gen_planner_service.run_ter_generation(params, token)


@gen_planner_router.post("/run_func_generation", response_model=GenPlannerResultSchema)
async def run_func_territory_zones_generation(
    params: Annotated[GenPlannerFuncZonesDTO, Depends(GenPlannerFuncZonesDTO)],
    token: str = Depends(verify_bearer_token),
) -> GenPlannerResultSchema:

    return await gen_planner_service.run_func_generation(params, token)
