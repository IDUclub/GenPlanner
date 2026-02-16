import asyncio
import json
from typing import Literal

import geopandas as gpd
import pandas as pd
from genplanner import GenPlanner
from iduconfig import Config
from loguru import logger
from shapely import buffer

from app.clients.ecodonat_api_client import EcodonutApiClient
from app.clients.urban_api_client import UrbanApiClient
from app.common.constants.api_constants import scenario_func_zones_map, scenario_ter_zones_map

from .dto.gen_planner_custom_dto import GenPlannerCustomDTO
from .dto.gen_planner_func_dto import GenPlannerFuncZonesDTO
from .schema.gen_planner_schema import GenPlannerResultSchema

ROADS_OBJECTS_IDS = [50, 51, 52]
WATER_OBJECTS_IDS = [2, 44, 45, 54, 55]


class GenPlannerService:
    """
    Service for handling GenPlanner operations, including retrieving physical objects,
    restoring parameters, and running generation tasks.
    This service interacts with the UrbanApiClient to fetch necessary data and
    processes it to form the GenPlanner object for generating territorial or functional zones.
    Attributes:
        urban_api_client (UrbanApiClient): Client for accessing urban API services.
        ecodonut_api (EcodonutApiClient): An instance of EcodonutApiClient to interact with urban API services.
    """

    def __init__(self, urban_api: UrbanApiClient, ecodonut_api: EcodonutApiClient):
        """
        Initializes the GenPlannerService with the provided UrbanApiClient instance.
        Args:
            urban_api (UrbanApiClient): An instance of UrbanApiClient to interact with urban API services.
            ecodonut_api (EcodonutApiClient): An instance of EcodonutApiClient to interact with urban API services.
        """

        self.urban_api_client: UrbanApiClient = urban_api
        self.ecodonut_api_client: EcodonutApiClient = ecodonut_api

    async def form_exclude_to_cut(
        self, scenario_id: int, project_id: int, angle: int | None, token: str
    ) -> dict[Literal["exclude_features"], gpd.GeoDataFrame]:
        """
        Function retrieves water objects to cut from scenario and context.
        Args:
            scenario_id (int): ID of the scenario.
            project_id (int): ID of the project.
            angle (int): The relief angle.
            token (str): User bearer access token.
        Returns:
            dict[Literal["exclude_features"], gpd.GeoDataFrame]: Water objects to cut as dict with gdf.
        """

        water, context_water, slope_polygons = await asyncio.gather(
            self.urban_api_client.get_physical_objects_for_scenario(scenario_id, WATER_OBJECTS_IDS, token),
            self.urban_api_client.get_physical_objects_for_context(scenario_id, WATER_OBJECTS_IDS, token),
            self.ecodonut_api_client.get_slope_polygons(token, project_id, angle),
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
        return {"exclude_features": pd.concat([water, slope_polygons])}

    async def form_roads(self, scenario_id: int, token: str) -> dict[Literal["roads"], gpd.GeoDataFrame]:
        """
        Function retrieves roads objects from scenario.
        Args:
            scenario_id (int): ID of the scenario.
            token (str): User bearer access token.
        Returns:
            dict[Literal["roads"], gpd.GeoDataFrame]: Roads objects as dict with gdf.
        """

        roads = await self.urban_api_client.get_physical_objects_for_scenario(scenario_id, ROADS_OBJECTS_IDS, token)
        return {"roads": roads}

    async def get_all_physical_objects(
        self, project_id: int, scenario_id: int, angle: int | None, token: str
    ) -> dict[Literal["exclude_features", "roads"], gpd.GeoDataFrame]:
        """
        Function retrieves all physical objects for the given project and scenario.
        Args:
            project_id (int): ID of the project.
            scenario_id (int): ID of the scenario.
            angle (int)
            token (str): User bearer access token.
        Returns:
            dict[Literal["exclude_features", "roads"], gpd.GeoDataFrame]: Dictionary containing water and roads GeoDataFrames.
        """

        objects = await asyncio.gather(
            *[self.form_exclude_to_cut(scenario_id, project_id, angle, token), self.form_roads(scenario_id, token)]
        )
        return {k: v for d in objects for k, v in d.items()}

    async def restore_params(self, params: GenPlannerFuncZonesDTO, token: str) -> GenPlannerFuncZonesDTO:
        """
        Function restores parameters for the generation.
        Args:
            params (GenPlannerFuncZonesDTO): Parameters for the generation.
            token (str): User bearer access token.
        Returns:
            GenPlannerFuncZonesDTO: Restored parameters for the generation.
        """

        params._territory_gdf = await self.urban_api_client.get_territory_geom_by_project_id(params.project_id, token)
        return params

    async def form_genplanner(
        self, params: GenPlannerFuncZonesDTO, token: str, config: Config, only_on_zones: bool = False
    ) -> GenPlanner:
        """
        Function forms GenPlanner object with the given parameters.
        Args:
            params (GenPlannerFuncZonesDTO): Parameters for the generation.
            token (str): User bearer access token.
            only_on_zones (bool): Weather to generate only using requested zones.
        Returns:
            GenPlanner: GenPlanner object with the given parameters.
        """

        params = await self.restore_params(params, token)
        objects = await self.get_all_physical_objects(
            params.project_id, params.scenario_id, params.elevation_angle, token
        )
        # TODO revise if-else logic
        if params.functional_zones:
            func_zones = await self.urban_api_client.get_functional_zones(
                token,
                params.scenario_id,
                year=params.functional_zones.year,
                source=params.functional_zones.source,
            )
            func_zones["functional_zone_type_id"] = func_zones["functional_zone_type"].map(lambda x: x["id"])
            func_zones["territory_zone"] = func_zones["functional_zone_type_id"].map(scenario_ter_zones_map)
            if only_on_zones:
                params._initial_zones_to_add = func_zones[
                    ~func_zones["functional_zone_id"].isin(params.functional_zones.fixed_functional_zones_ids)
                ]
                params._territory_gdf = func_zones.copy()
            func_zones = func_zones[
                func_zones["functional_zone_id"].isin(params.functional_zones.fixed_functional_zones_ids)
            ]
        else:
            func_zones = None
        logger.info(f"func_zones: {type(func_zones)}")
        if isinstance(func_zones, gpd.GeoDataFrame):
            logger.info(f"func_zones ids: {func_zones['functional_zone_id']}")
            logger.info(f"Only on zones: {only_on_zones}")
        return GenPlanner(
            params._territory_gdf,
            **objects,
            existing_terr_zones=None if only_on_zones else func_zones,
            simplify_value=10,
            parallel=False if config.get("APP_ENV") == "development" else True,
        )

    @staticmethod
    async def form_custom_genplanner(params: GenPlannerCustomDTO) -> GenPlanner:
        """
        Function forms GenPlanner object with the given parameters.
        Args:
            params (GenPlannerCustomDTO): Parameters for the generation.
        Returns:
            GenPlanner: GenPlanner object with the given parameters.
        Raises:
            Any from GenPlanner initialization
        """

        return GenPlanner(params._territory_gdf, simplify_value=10)

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
            zones["territory_zone"] = zones["territory_zone"].apply(lambda x: x.name if x and not pd.isna(x) else None)
        zones.drop(columns="func_zone", inplace=True)
        return {"zones": json.loads(zones.to_json()), "roads": json.loads(roads.to_json())}

    @staticmethod
    async def log_request_params(params: GenPlannerFuncZonesDTO, start: bool) -> None:
        """
        Function logs the request parameters for the generation.
        Args:
            params (GenPlannerFuncZonesDTO): Parameters for the generation.
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
                    {action} generation for params {params.model_dump()}
                    """
        )

    async def run_func_generation(
        self,
        params: GenPlannerFuncZonesDTO,
        token: str,
        config: Config,
        on_zones_only: bool = False,
    ) -> GenPlannerResultSchema:
        """
        Function runs the functional generation with the given parameters.
        Args:
            params (GenPlannerFuncZonesDTO): Parameters for the functional generation.
            token (str): User bearer access token.
            on_zones_only
        Returns:
            GenPlannerResultSchema: Result of the functional generation.
        """

        await self.log_request_params(params, True)
        genplanner = await self.form_genplanner(
            params,
            token,
            config,
            on_zones_only,
        )
        zones, roads = await asyncio.to_thread(
            genplanner.features2terr_zones2blocks,
            funczone=params._custom_func_zone,
            fixed_terr_zones=params._fix_zones_gdf,
        )
        if on_zones_only:
            zones = pd.concat([zones, params._initial_zones_to_add])
        res = await self.form_genplanner_response(zones, roads)
        await self.log_request_params(params, False)
        return GenPlannerResultSchema(**res)

    async def run_custom_func_generation(self, params: GenPlannerCustomDTO) -> GenPlannerResultSchema:
        """
        Function runs the functional generation with the given parameters.
        Args:
            params (GenPlannerCustomDTO): Parameters for the functional generation.
        Returns:
            GenPlannerResultSchema: Result of the functional generation.
        """

        await self.log_request_params(params, True)
        genplanner = await self.form_custom_genplanner(params)
        zones, roads = await asyncio.to_thread(
            genplanner.features2terr_zones2blocks,
            funczone=params._func_zone,
        )
        res = await self.form_genplanner_response(zones, roads)
        return GenPlannerResultSchema(**res)

    # TODO revise for more convenient way later
    @staticmethod
    async def get_func_zone_ratio(zone_id: int) -> dict:

        func_zone = scenario_func_zones_map[zone_id]
        reverse_ter = {}
        for k, v in scenario_ter_zones_map.items():
            if v not in reverse_ter:
                reverse_ter[v] = k
        return {reverse_ter[k]: round(func_zone.zones_ratio[k], 2) for k in func_zone.zones_ratio.keys()}
