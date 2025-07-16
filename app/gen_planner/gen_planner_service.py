import asyncio
import json
from typing import Literal

import geopandas as gpd
import pandas as pd
from loguru import logger
from shapely import buffer

from app.common.constants.api_constants import scenario_func_zones_map, scenario_ter_zones_map
from app.dependencies import urban_api_gateway
from app.gateways.urban_api_gateway import UrbanApiGateway

from .dto.gen_planner_dto import GenPlannerFuncZonesDTO, GenPlannerTerZonesDTO
from .python.src.genplanner import GenPlanner
from .schema.gen_planner_schema import GenPlannerResultSchema

ROADS_OBJECTS_IDS = [50, 51, 52]
WATER_OBJECTS_IDS = [2, 44, 45, 54, 55]


class GenPlannerService:
    """
    Service for handling GenPlanner operations, including retrieving physical objects,
    restoring parameters, and running generation tasks.
    This service interacts with the UrbanApiGateway to fetch necessary data and
    processes it to form the GenPlanner object for generating territorial or functional zones.
    Attributes:
        urban_api_gateway (UrbanApiGateway): Gateway for accessing urban API services.
    """

    def __init__(self, urban_api: UrbanApiGateway):
        """
        Initializes the GenPlannerService with the provided UrbanApiGateway instance.
        Args:
            urban_api (UrbanApiGateway): An instance of UrbanApiGateway to interact with urban API services.
        """

        self.urban_api_gateway: UrbanApiGateway = urban_api

    async def form_exclude_to_cut(
        self, project_id: int, scenario_id: int, token: str
    ) -> dict[Literal["exclude_features"], gpd.GeoDataFrame]:
        """
        Function retrieves water objects to cut from scenario and context.
        Args:
            project_id (int): ID of the project.
            scenario_id (int): ID of the scenario.
            token (str): User bearer access token.
        Returns:
            dict[Literal["exclude_features"], gpd.GeoDataFrame]: Water objects to cut as dict with gdf.
        """

        water, context_water = await asyncio.gather(
            self.urban_api_gateway.get_physical_objects_for_scenario(scenario_id, WATER_OBJECTS_IDS, token),
            self.urban_api_gateway.get_physical_objects_for_context(project_id, WATER_OBJECTS_IDS, token),
        )
        if not context_water is None:
            context_water = context_water[
                context_water.geometry.geom_type.isin(["MultiPolygon", "Polygon", "MultiLineString", "LineString"])
            ]
            context_water.to_crs(context_water.estimate_utm_crs(), inplace=True)
            context_water.geometry = context_water.geometry.apply(
                lambda x: buffer(x, 2.5) if x.geom_type in ["MultiLineString", "LineString"] else x
            )
            context_water.to_crs(4326, inplace=True)
            water = pd.concat([water, context_water])
        return {"exclude_features": water}

    async def form_roads(self, scenario_id: int, token: str) -> dict[Literal["roads"], gpd.GeoDataFrame]:
        """
        Function retrieves roads objects from scenario.
        Args:
            scenario_id (int): ID of the scenario.
            token (str): User bearer access token.
        Returns:
            dict[Literal["roads"], gpd.GeoDataFrame]: Roads objects as dict with gdf.
        """

        roads = await self.urban_api_gateway.get_physical_objects_for_scenario(scenario_id, ROADS_OBJECTS_IDS, token)
        return {"roads": roads}

    async def get_all_physical_objects(
        self, project_id: int, scenario_id: int, token: str
    ) -> dict[Literal["exclude_features", "roads"], gpd.GeoDataFrame]:
        """
        Function retrieves all physical objects for the given project and scenario.
        Args:
            project_id (int): ID of the project.
            scenario_id (int): ID of the scenario.
            token (str): User bearer access token.
        Returns:
            dict[Literal["exclude_features", "roads"], gpd.GeoDataFrame]: Dictionary containing water and roads GeoDataFrames.
        """

        objects = await asyncio.gather(
            *[self.form_exclude_to_cut(project_id, scenario_id, token), self.form_roads(scenario_id, token)]
        )
        return {k: v for d in objects for k, v in d.items()}

    async def restore_params(
        self, params: GenPlannerTerZonesDTO | GenPlannerFuncZonesDTO, token: str
    ) -> GenPlannerTerZonesDTO | GenPlannerFuncZonesDTO:
        """
        Function restores parameters for the generation.
        Args:
            params (GenPlannerTerZonesDTO | GenPlannerFuncZonesDTO): Parameters for the generation.
            token (str): User bearer access token.
        Returns:
            GenPlannerTerZonesDTO | GenPlannerFuncZonesDTO: Restored parameters for the generation.
        """

        if not params.scenario_id and params.project_id:
            proj_data = await self.urban_api_gateway.get_project_info_by_project_id(params.project_id, token)
            params.scenario_id = proj_data["base_scenario"]["id"]
        if params.territory:
            params.territory = params.territory.as_gdf()
        else:
            params.territory = await self.urban_api_gateway.get_territory_geom_by_project_id(params.project_id, token)
        if params.fix_zones:
            params.fix_zones = params.fix_zones.as_gdf()
        return params

    async def form_genplanner(self, params: GenPlannerTerZonesDTO | GenPlannerFuncZonesDTO, token: str) -> GenPlanner:
        """
        Function forms GenPlanner object with the given parameters.
        Args:
            params (GenPlannerTerZonesDTO | GenPlannerFuncZonesDTO): Parameters for the generation.
            token (str): User bearer access token.
        Returns:
            GenPlanner: GenPlanner object with the given parameters.
        """

        params = await self.restore_params(params, token)
        if params.project_id and params.scenario_id:
            objects = await self.get_all_physical_objects(params.project_id, params.scenario_id, token)
            return GenPlanner(params.territory, **objects, dev_mode=True)
        return GenPlanner(params.territory, dev_mode=True)

    @staticmethod
    async def form_genplanner_response(
        zones: gpd.GeoDataFrame, roads: gpd.GeoDataFrame
    ) -> dict[Literal["zones", "roads"], dict]:
        """
        Function forms GenPlannerResultSchema from the given roads and zones GeoDataFrames.
        Args:
            roads (gpd.GeoDataFrame): Roads GeoDataFrame.
            zones (gpd.GeoDataFrame): Zones GeoDataFrame.
        Returns:
            GenPlannerResultSchema: GenPlanner result schema with the given roads and zones.
        """

        if "territory_zone" in zones.columns:
            zones["territory_zone"] = zones["territory_zone"].apply(lambda x: x.name if x else None)
        zones.drop(columns="func_zone", inplace=True)
        return {"zones": json.loads(zones.to_json()), "roads": json.loads(roads.to_json())}

    @staticmethod
    async def log_request_params(params: GenPlannerTerZonesDTO | GenPlannerFuncZonesDTO, start: bool) -> None:
        """
        Function logs the request parameters for the generation.
        Args:
            params (GenPlannerTerZonesDTO | GenPlannerFuncZonesDTO): Parameters for the generation.
            start (bool): Flag indicating whether the generation is starting or completed.
        Returns:
            None
        """

        if start:
            action = "Starting"
        else:
            action = "Completed"
        logger.info(
            f"""
                    {action} generation for scenario: {params.scenario_id}, profile_scenario: {params.profile_scenario},
                    {"project_id" if params.project_id else "user territory"}
                    """
        )

    async def run_ter_generation(self, params: GenPlannerTerZonesDTO, token: str) -> GenPlannerResultSchema:
        """
        Function runs the territorial generation with the given parameters.
        Args:
            params (GenPlannerTerZonesDTO): Parameters for the territorial generation.
            token (str): User bearer access token.
        Returns:
            GenPlannerResultSchema: Result of the territorial generation.
        """

        await self.log_request_params(params, True)
        genplanner = await self.form_genplanner(params, token)
        terr_zone = scenario_ter_zones_map.get(params.profile_scenario)
        zones, roads = await asyncio.to_thread(genplanner.features2blocks, terr_zone=terr_zone)
        res = await self.form_genplanner_response(zones, roads)
        await self.log_request_params(params, False)
        return GenPlannerResultSchema(**res)

    async def run_func_generation(self, params: GenPlannerFuncZonesDTO, token: str) -> GenPlannerResultSchema:
        """
        Function runs the functional generation with the given parameters.
        Args:
            params (GenPlannerFuncZonesDTO): Parameters for the functional generation.
            token (str): User bearer access token.
        Returns:
            GenPlannerResultSchema: Result of the functional generation.
        """

        await self.log_request_params(params, True)
        genplanner = await self.form_genplanner(params, token)
        if params.territory_balance:
            funczone = params.get_territory_balance()
        else:
            funczone = scenario_func_zones_map.get(params.profile_scenario)
        zones, roads = await asyncio.to_thread(
            genplanner.features2terr_zones2blocks,
            funczone=funczone,
            fixed_terr_zones=params.fix_zones,
        )
        res = await self.form_genplanner_response(zones, roads)
        await self.log_request_params(params, False)
        return GenPlannerResultSchema(**res)


gen_planner_service = GenPlannerService(urban_api_gateway)
