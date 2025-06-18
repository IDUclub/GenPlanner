import asyncio
import json
from typing import Annotated, Literal

import geopandas as gpd
import pandas as pd
from fastapi import APIRouter, Depends
from loguru import logger
from shapely import buffer

from app.gen_planner.python.src.genplanner import GenPlanner
from app.gen_planner.python.src.zoning import FuncZone, TerritoryZone

from .api_constants import scenario_func_zones_map, scenario_ter_zones_map
from .gen_planner_api_service import gen_planner_api_service
from .gen_planner_dto import GenPlannerFuncZonesDTO, GenPlannerTerZonesDTO
from .gen_planner_schema import GenPlannerResultSchema

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
        exclude: gpd.GeoDataFrame | None,
        project_roads: gpd.GeoDataFrame | None = None,
) -> tuple[gpd.GeoDataFrame]:
    """
    Function generates gen plan
    :param scenario: scenario to generate from
    :param func_type:  func type to generate by. Can be ter or zone
    :param territory: territory gdf to generate on
    :param project_roads: roads gdf to generate on
    :param exclude: exclude gdf to generate on
    :return: tuple[gpd.GeoDataFrame] with zones and roads
    """

    gen_planner = GenPlanner(territory, project_roads, exclude, dev_mode=True)
    if func_type == "zone":
        for i in range(15):
            try:
                zones, roads = gen_planner.features2terr_zones2blocks(scenario)
                if roads.empty:
                    return zones, gpd.GeoDataFrame()
                return zones, roads
            except Exception as e:
                logger.warning(e.__str__())
                continue
    elif func_type == "ter":
        for i in range(20):
            # try:
            zones, roads = gen_planner.features2blocks(scenario)
            if roads.empty:
                return zones, gpd.GeoDataFrame()
            return zones, roads
            # except Exception as e:
            #     logger.warning(e.__str__())
            #     continue
        return None
    return None


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
    if not params.scenario_id:
        proj_data = await gen_planner_api_service.get_project_info_by_project_id(params.project_id)
        params.scenario_id = proj_data["base_scenario"]["id"]
    if params.territory:
        territory = gpd.GeoDataFrame.from_features(params.territory.as_geo_dict(), crs=4326)
    else:
        territory = await gen_planner_api_service.get_territory_geom_by_project_id(params.project_id)
    roads = await gen_planner_api_service.get_physical_objects_for_scenario(params.scenario_id, [50, 51, 52])
    water = await gen_planner_api_service.get_physical_objects_for_scenario(params.scenario_id, [2, 44, 45, 54, 55])
    context_water = await gen_planner_api_service.get_physical_objects_for_context(params.project_id,
                                                                                   [2, 44, 45, 54, 55])
    if not water is None:
        water = water[water.geometry.geom_type.isin(["MultiPolygon", "Polygon", "MultiLineString", "LineString"])]
        water.to_crs(water.estimate_utm_crs(), inplace=True)
        water.geometry = water.geometry.apply(
            lambda x: buffer(x, 2.5) if x.geom_type in ["MultiLineString", "LineString"] else x
        )
        water.to_crs(4326, inplace=True)
        if not context_water is None:
            context_water = context_water[
                context_water.geometry.geom_type.isin(["MultiPolygon", "Polygon", "MultiLineString", "LineString"])]
            context_water.to_crs(context_water.estimate_utm_crs(), inplace=True)
            context_water.geometry = context_water.geometry.apply(
                lambda x: buffer(x, 2.5) if x.geom_type in ["MultiLineString", "LineString"] else x
            )
            context_water.to_crs(4326, inplace=True)
            water = pd.concat([water, context_water])
    zones, roads = await asyncio.to_thread(
        generate,
        scenario=scenario,
        func_type="ter",
        territory=territory,
        exclude=water,
        project_roads=roads,
    )
    zones["territory_zone"] = zones["territory_zone"].apply(lambda x: x.name if x else None)
    result_dict = {"zones": json.loads(zones.to_json()), "roads": json.loads(roads.to_json())}
    result = GenPlannerResultSchema(**result_dict)
    return result


@gen_planner_router.post("/run_func_generation", response_model=GenPlannerResultSchema)
async def run_func_territory_zones_generation(
        params: Annotated[GenPlannerFuncZonesDTO, Depends(GenPlannerFuncZonesDTO)]
) -> GenPlannerResultSchema:
    scenario = scenario_func_zones_map.get(params.profile_scenario)
    if not params.scenario_id:
        proj_data = await gen_planner_api_service.get_project_info_by_project_id(params.project_id)
        params.scenario_id = proj_data["base_scenario"]["id"]
    if params.territory:
        territory = gpd.GeoDataFrame.from_features(params.territory.as_geo_dict(), crs=4326)
    else:
        territory = await gen_planner_api_service.get_territory_geom_by_project_id(params.project_id)
    roads = await gen_planner_api_service.get_physical_objects_for_scenario(params.scenario_id, [50, 51, 52])
    water = await gen_planner_api_service.get_physical_objects_for_scenario(params.scenario_id, [2, 44, 45, 54, 55])
    context_water = await gen_planner_api_service.get_physical_objects_for_context(params.project_id,
                                                                                   [2, 44, 45, 54, 55])
    if not water is None:
        water = water[water.geometry.geom_type.isin(["MultiPolygon", "Polygon", "MultiLineString", "LineString"])]
        water.to_crs(water.estimate_utm_crs(), inplace=True)
        water.geometry = water.geometry.apply(
            lambda x: buffer(x, 2.5) if x.geom_type in ["MultiLineString", "LineString"] else x
        )
        water.to_crs(4326, inplace=True)
        if not context_water is None:
            context_water = context_water[
                context_water.geometry.geom_type.isin(["MultiPolygon", "Polygon", "MultiLineString", "LineString"])]
            context_water.to_crs(context_water.estimate_utm_crs(), inplace=True)
            context_water.geometry = context_water.geometry.apply(
                lambda x: buffer(x, 2.5) if x.geom_type in ["MultiLineString", "LineString"] else x
            )
            context_water.to_crs(4326, inplace=True)
            water = pd.concat([water, context_water])
    zones, roads = await asyncio.to_thread(
        generate,
        scenario=scenario,
        func_type="zone",
        territory=territory,
        exclude=water,
        project_roads=roads,
    )
    zones["func_zone"] = zones["func_zone"].apply(lambda x: x.name if x else None)
    zones["terr_zone"] = zones["territory_zone"].apply(lambda x: x.name if x else None)
    zones.drop(columns=["territory_zone"], inplace=True)
    result_dict = {"zones": json.loads(zones.to_json()), "roads": json.loads(roads.to_json())}
    result = GenPlannerResultSchema(**result_dict)
    return result
