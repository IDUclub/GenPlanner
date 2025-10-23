from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sklearn.externals.array_api_extra import apply_where

from app.common.auth.bearer import verify_bearer_token
from app.common.constants.api_constants import scenario_func_zones_map, scenario_ter_zones_map
from app.dependencies import get_genplanner_service
from app.gen_planner.dto.gen_planner_custom_dto import GenPlannerCustomDTO
from app.gen_planner.dto.gen_planner_func_dto import GenPlannerFuncZonesDTO
from app.gen_planner.schema.gen_planner_schema import GenPlannerResultSchema

from .dto.examples import gen_planner_func_zone_dto_example
from .gen_planner_service import GenPlannerService

gen_planner_router = APIRouter(tags=["gen_planner"])


@gen_planner_router.get("/gen_planner/zones_list", response_model=list[int])
async def get_available_zones_profiles():
    """
    :return: list of available func zones to run in genplanner by ids
    """

    return [i for i in scenario_func_zones_map]


@gen_planner_router.post(
    "/run_func_generation", response_model=GenPlannerResultSchema, openapi_extra=gen_planner_func_zone_dto_example
)
async def run_func_territory_zones_generation(
    params: Annotated[GenPlannerFuncZonesDTO, Depends(GenPlannerFuncZonesDTO)],
    token: str = Depends(verify_bearer_token),
    genplanner_service: GenPlannerService = Depends(get_genplanner_service),
) -> GenPlannerResultSchema:

    return await genplanner_service.run_func_generation(params, token)


@gen_planner_router.post("/custom/run_func_generation", response_model=GenPlannerResultSchema)
async def run_custom_territory_zones_generation(
    params: Annotated[GenPlannerCustomDTO, Depends(GenPlannerCustomDTO)],
    genplanner_service: GenPlannerService = Depends(get_genplanner_service),
) -> GenPlannerResultSchema:

    return await genplanner_service.run_custom_func_generation(params)


@gen_planner_router.get("/default/func_ratio", response_model=dict[int, float])
async def get_func_zone_ratio(
    zone: int,
    genplanner_service: GenPlannerService = Depends(get_genplanner_service),
) -> dict[int, float]:

    return await genplanner_service.get_func_zone_ratio(zone)
