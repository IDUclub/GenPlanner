import asyncio
import json
from typing import Annotated, Literal

import pandas as pd
from loguru import logger

from app.gen_planner.python.src.genplanner import GenPlanner

from fastapi import APIRouter, Depends
import geopandas as gpd
from shapely.geometry import shape
from geojson_pydantic import FeatureCollection

from .api_constants import scenario_func_zones_map, scenario_ter_zones_map
from app.gen_planner.python.src.zoning import FuncZone, TerritoryZone
from .gen_planner_dto import GenPlannerFuncZonesDTO, GenPlannerTerZonesDTO
from .gen_planner_schema import GenPlannerResultSchema
from .gen_planner_api_service import gen_planner_api_service
# from .gen_planner_service import gen_planner_service


gen_planner_router = APIRouter(tags=["gen_planner"])


# @gen_planner_router.post("/run_generation")
# async def run_generation(params: GenPlannerDTO):
#     result = await gen_planner_service.add_task_to_queue(params)
#     return result
#
# @gen_planner_router.get("/check_generation")
# async def check_generation(task_id: str):
#     result = await gen_planner_service.get_task_status(task_id)
#     return result

def generate(
        scenario: FuncZone | TerritoryZone,
        func_type: Literal["ter", "zone"],
        territory: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame]:
    """
    Function generates gen plan
    :param scenario: scenario to generate from
    :param func_type:  func type to generate by. Can be ter or zone
    :param territory: territory gdf to generate on
    :return: tuple[gpd.GeoDataFrame] with zones and roads
    """

    gen_planner = GenPlanner(territory)
    if func_type == "zone":
        for i in range(15):
            try:
                zones, roads = gen_planner.poly2terr2block(scenario)
                zones.to_crs(4326, inplace=True)
                if roads.empty:
                    return zones, gpd.GeoDataFrame()
                roads.to_crs(4326, inplace=True)
                return zones, roads
            except Exception as e:
                logger.warning(e.__str__())
                continue
    elif func_type == "ter":
        for i in range(20):
            try:
                zones, roads = gen_planner.poly2block(scenario)
                zones.to_crs(4326, inplace=True)
                if roads.empty:
                    return zones, gpd.GeoDataFrame()
                roads.to_crs(4326, inplace=True)
                return zones, roads
            except Exception as e:
                logger.warning(e.__str__())
                continue

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
        params: Annotated[GenPlannerTerZonesDTO, Depends(GenPlannerTerZonesDTO)]
) -> GenPlannerResultSchema:

    scenario = scenario_ter_zones_map.get(params.profile_scenario)
    if params.territory:
        territory = gpd.GeoDataFrame.from_features(params.territory.as_geo_dict(), crs=4326)
    else:
        territory = await gen_planner_api_service.get_territory_geom_by_project_id(params.project_id)
    territory = territory.explode()
    result_zones, result_roads = [], []
    for geometry in territory.geometry:
        current_geometry = gpd.GeoDataFrame(geometry=[geometry], crs=4326)
        zones, roads = await asyncio.to_thread(
            generate,
            scenario=scenario,
            func_type="ter",
            territory=current_geometry,
        )
        result_zones.append(zones)
        result_roads.append(roads)
    result_dict = {
        "zones": json.loads(pd.concat(result_zones).to_json()),
        "roads": json.loads(pd.concat(result_roads).to_json())
    }
    result = GenPlannerResultSchema(**result_dict)
    return result

@gen_planner_router.post("/run_func_generation", response_model=GenPlannerResultSchema)
async def run_func_territory_zones_generation(
        params: Annotated[GenPlannerFuncZonesDTO, Depends(GenPlannerFuncZonesDTO)]
) -> GenPlannerResultSchema:

    scenario = scenario_func_zones_map.get(params.profile_scenario)
    if params.territory:
        territory = gpd.GeoDataFrame.from_features(params.territory.as_geo_dict(), crs=4326)
    else:
        territory = await gen_planner_api_service.get_territory_geom_by_project_id(params.project_id)
    territory = territory.explode()
    result_zones, result_roads = [], []
    for geometry in territory.geometry:
        current_geometry = gpd.GeoDataFrame(geometry=[geometry], crs=4326)
        zones, roads = await asyncio.to_thread(
            generate,
            scenario=scenario,
            func_type="zone",
            territory=current_geometry,
        )
        result_zones.append(zones)
        result_roads.append(roads)
    result_dict = {
        "zones": json.loads(pd.concat(result_zones).to_json()),
        "roads": json.loads(pd.concat(result_roads).to_json())
    }
    result = GenPlannerResultSchema(**result_dict)
    return result
