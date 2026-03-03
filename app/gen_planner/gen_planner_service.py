import asyncio
import json
from typing import Literal

import geopandas as gpd
import pandas as pd
from genplanner import GenPlanner, TerritoryZone
from genplanner.zone_relations.relation_matrix import ZoneRelationMatrix, Relation
from genplanner.zone_relations.forbidden_terr_kind import FORBIDDEN_NEIGHBORHOOD
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
    ) -> dict[Literal["exclude_gdf"], gpd.GeoDataFrame]:
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
        return {"exclude_gdf": pd.concat([water, slope_polygons])}

    async def form_roads(self, scenario_id: int, token: str) -> dict[Literal["roads_gdf"], gpd.GeoDataFrame]:
        """
        Function retrieves roads objects from scenario.
        Args:
            scenario_id (int): ID of the scenario.
            token (str): User bearer access token.
        Returns:
            dict[Literal["roads"], gpd.GeoDataFrame]: Roads objects as dict with gdf.
        """

        roads = await self.urban_api_client.get_physical_objects_for_scenario(scenario_id, ROADS_OBJECTS_IDS, token)
        return {"roads_gdf": roads}

    async def get_all_physical_objects(
        self, project_id: int, scenario_id: int, angle: int | None, token: str
    ) -> dict[Literal["exclude_gdf", "roads_gdf"], gpd.GeoDataFrame]:
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
            fixed_ids = params.functional_zones.fixed_functional_zones_ids or []
            if only_on_zones:
                if fixed_ids:
                    params._initial_zones_to_add = func_zones[~func_zones["functional_zone_id"].isin(fixed_ids)]
                else:
                    params._initial_zones_to_add = func_zones
                params._territory_gdf = func_zones.copy()

            if fixed_ids:
                func_zones = func_zones[func_zones["functional_zone_id"].isin(fixed_ids)]
                if func_zones.empty:
                    func_zones = None
        else:
            func_zones = None
        logger.info(f"func_zones: {type(func_zones)}")
        if isinstance(func_zones, gpd.GeoDataFrame):
            logger.info(f"func_zones ids: {func_zones['functional_zone_id']}")
            logger.info(f"Only on zones: {only_on_zones}")

        exclude_gdf = objects.get("exclude_gdf")
        roads_gdf = objects.get("roads_gdf")


        #TODO fix
        # shapely.errors.GEOSException: TopologyException: side location conflict at 389422.28961780888 6643244.4901334196
        # for scenario 109 2024 OSM in utm_crs
        return GenPlanner(
            features_gdf=params._territory_gdf,
            roads_gdf=roads_gdf,
            exclude_gdf=exclude_gdf,
            existing_terr_zones=None if only_on_zones else func_zones,
            # parallel=False if config.get("APP_ENV") == "development" else True,
            parallel=True
        )

        # return GenPlanner(
        #     params._territory_gdf,
        #     **objects,
        #     existing_terr_zones=None if only_on_zones else func_zones,
        #     simplify_geometry_value=10,
        #     parallel=False if config.get("APP_ENV") == "development" else True,
        # )

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

        zones = zones.copy()
        roads = roads.copy()

        if "territory_zone" in zones.columns:
            zones["territory_zone"] = zones["territory_zone"].apply(
                lambda x: getattr(x, "name", x) if x is not None and not pd.isna(x) else None
            )

        for col in ("func_zone", "funczone", "functional_zone", "zones_ratio", "__func_zone__"):
            if col in zones.columns:
                zones.drop(columns=[col], inplace=True)

        def _is_json_safe_value(v) -> bool:
            return v is None or isinstance(v, (str, int, float, bool))

        bad_cols = []
        for col in zones.columns:
            if col == "geometry":
                continue
            s = zones[col].dropna()
            if not s.empty and not s.map(_is_json_safe_value).all():
                bad_cols.append(col)

        if bad_cols:
            zones.drop(columns=bad_cols, inplace=True)

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

    def _build_relation_matrix_arg(self, params: GenPlannerFuncZonesDTO) -> str | ZoneRelationMatrix:
        """
        Build relation_matrix arg for GenPlanner based on request params.

        Returns:
            - "default" if no custom relations requested
            - ZoneRelationMatrix instance otherwise
        """
        has_custom = bool(params.neighbour_pairs or params.forbidden_pairs or params.ignore_default_relations)
        if not has_custom:
            return "default"

        zone_map: dict[int, TerritoryZone] = params._custom_id_ter_zone_map or {}
        zones_for_matrix = list(zone_map.values())

        if not zones_for_matrix:
            return "empty" if params.ignore_default_relations else "default"

        if params.ignore_default_relations:
            matrix = ZoneRelationMatrix.empty(zones_for_matrix)
        else:
            matrix = ZoneRelationMatrix.from_kind_forbidden(
                zones=zones_for_matrix,
                kind_forbidden=FORBIDDEN_NEIGHBORHOOD,
            )

        def _pairs_to_zones(pairs: list[tuple[int, int]] | None, rel_name: str) -> list[
            tuple[TerritoryZone, TerritoryZone]]:
            out: list[tuple[TerritoryZone, TerritoryZone]] = []
            if not pairs:
                return out
            for a_id, b_id in pairs:
                a = zone_map.get(a_id)
                b = zone_map.get(b_id)
                if not a or not b:
                    logger.warning(f"Skipping {rel_name} pair ({a_id}, {b_id}) because zone id is unknown.")
                    continue
                out.append((a, b))
            return out

        neigh_pairs = _pairs_to_zones(params.neighbour_pairs, "neighbor")
        if neigh_pairs:
            matrix = matrix.with_pairs(neigh_pairs, Relation.NEIGHBOR)

        forb_pairs = _pairs_to_zones(params.forbidden_pairs, "forbidden")
        if forb_pairs:
            matrix = matrix.with_pairs(forb_pairs, Relation.FORBIDDEN)

        return matrix

    async def run_func_generation(
            self,
            params: GenPlannerFuncZonesDTO,
            token: str,
            config: Config,
            on_zones_only: bool = False,
    ) -> GenPlannerResultSchema:
        await self.log_request_params(params, True)

        genplanner = await self.form_genplanner(params, token, config, on_zones_only)

        relation_matrix_arg = self._build_relation_matrix_arg(params)

        zones, roads = await asyncio.to_thread(
            genplanner.features2terr_zones2blocks,
            funczone=params._custom_func_zone,
            relation_matrix=relation_matrix_arg,
            terr_zones_fix_points=params.fix_zones,
        )

        if on_zones_only and params._initial_zones_to_add is not None:
            zones = pd.concat([zones, params._initial_zones_to_add], ignore_index=True)

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
