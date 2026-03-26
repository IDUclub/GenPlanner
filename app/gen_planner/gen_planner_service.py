import asyncio
import json
from typing import Literal

import geopandas as gpd
import pandas as pd
from genplanner import GenPlanner, TerritoryZone
from genplanner.zones import TerritoryZoneKind
from iduconfig import Config
from loguru import logger
from shapely import buffer

from genplanner.zone_relations.relation_matrix import Relation, ZoneRelationMatrix
from genplanner.zone_relations.forbidden_terr_kind import FORBIDDEN_NEIGHBORHOOD

from app.clients.ecodonat_api_client import EcodonutApiClient
from app.clients.urban_api_client import UrbanApiClient
from app.common.constants.api_constants import scenario_func_zones_map, default_terr_zones_map

from .dto.gen_planner_custom_dto import GenPlannerCustomDTO
from .dto.gen_planner_func_dto import GenPlannerFuncZonesDTO
from .schema.gen_planner_schema import GenPlannerResultSchema
from ..common.exceptions.http_exception import http_exception

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
            dict[Literal["exclude_gdf"], gpd.GeoDataFrame]: Water objects to cut as dict with gdf.
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
            dict[Literal["roads_gdf"], gpd.GeoDataFrame]: Roads objects as dict with gdf.
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
            dict[Literal["exclude_gdf", "roads_gdf"], gpd.GeoDataFrame]: Dictionary containing water and roads GeoDataFrames.
        """

        objects = await asyncio.gather(
            *[
                self.form_exclude_to_cut(scenario_id, project_id, angle, token),
                self.form_roads(scenario_id, token),
            ]
        )
        return {k: v for d in objects for k, v in d.items()}

    async def restore_params(self, params, token: str):
        """
        Function restores parameters for the generation.
        Args:
            params: Parameters for the generation.
            token (str): User bearer access token.
        Returns:
            Restored parameters for the generation.
        """

        project_id = getattr(params, "project_id", None)

        if project_id is None:
            scenario_info = await self.urban_api_client.get_scenario_info(params.scenario_id, token)
            project_id = (scenario_info.get("project") or {}).get("project_id")

            if project_id is None:
                raise http_exception(
                    404,
                    "Project ID cannot be resolved from scenario info",
                    _input={"scenario_id": params.scenario_id},
                    _detail={"scenario_info": scenario_info},
                )

            setattr(params, "project_id", project_id)

        params._territory_gdf = await self.urban_api_client.get_territory_geom_by_project_id(project_id, token)
        return params

    def _build_relation_matrix_arg(self, params: GenPlannerFuncZonesDTO) -> str | ZoneRelationMatrix:
        """Build relation_matrix argument for GenPlanner from request fields.

        Returns:
            "default" if no custom relations were provided.
            "empty" if ignore_default_relations=True and no zones mapping available.
            ZoneRelationMatrix instance otherwise.
        """

        has_custom = bool(params.neighbour_pairs or params.forbidden_pairs or params.ignore_default_relations)
        if not has_custom:
            return "default"

        zone_map: dict[int, TerritoryZone] = params._custom_id_ter_zone_map or {}
        zones = list(zone_map.values())
        if not zones:
            return "empty" if params.ignore_default_relations else "default"
        else:
            matrix = ZoneRelationMatrix.from_kind_forbidden(zones=zones, kind_forbidden=FORBIDDEN_NEIGHBORHOOD)

        def _pairs(pairs: list[tuple[int, int]] | None) -> list[tuple[TerritoryZone, TerritoryZone]]:
            out: list[tuple[TerritoryZone, TerritoryZone]] = []
            if not pairs:
                return out
            for a_id, b_id in pairs:
                a = zone_map.get(int(a_id))
                b = zone_map.get(int(b_id))
                if not a or not b:
                    logger.warning(f"Skipping relation pair ({a_id}, {b_id}) because zone id is not in territory_balance")
                    continue
                out.append((a, b))
            return out

        n_pairs = _pairs(params.neighbour_pairs)
        if n_pairs:
            matrix = matrix.with_pairs(n_pairs, Relation.NEIGHBOR)

        f_pairs = _pairs(params.forbidden_pairs)
        if f_pairs:
            matrix = matrix.with_pairs(f_pairs, Relation.FORBIDDEN)

        return matrix

    def _split_functional_zones_by_fixed_ids(
            self,
            func_zones: gpd.GeoDataFrame,
            fixed_ids: list[int],
            scenario_id: int,
            project_id: int,
    ) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
        """
        Split functional zones into fixed and remaining subsets.
        """
        if not fixed_ids:
            return gpd.GeoDataFrame(columns=func_zones.columns), func_zones.copy()

        found_ids = set(func_zones["functional_zone_id"].tolist())
        missing_ids = sorted(set(fixed_ids) - found_ids)
        if missing_ids:
            raise http_exception(
                status_code=422,
                msg="Selected functional zone ids not found",
                _detail={"fixed_functional_zones_ids": missing_ids},
                _input={"scenario_id": scenario_id, "project_id": project_id},
            )

        fixed_mask = func_zones["functional_zone_id"].isin(fixed_ids)
        fixed_zones = func_zones[fixed_mask].copy()
        remaining_zones = func_zones[~fixed_mask].copy()
        return fixed_zones, remaining_zones

    async def form_genplanner(
            self, params: GenPlannerFuncZonesDTO, token: str, config: Config, only_on_zones: bool = False
    ) -> GenPlanner:
        """
        Function forms GenPlanner object with the given parameters.
        """
        params = await self.restore_params(params, token)

        elevation_angle = getattr(params, "elevation_angle", None)
        functional_zones = getattr(params, "functional_zones", None)

        objects = await self.get_all_physical_objects(
            params.project_id,
            params.scenario_id,
            elevation_angle,
            token,
        )

        existing_func_zones = None

        if functional_zones is not None:
            func_zones = await self.urban_api_client.get_functional_zones(
                token,
                params.scenario_id,
                year=functional_zones.year,
                source=functional_zones.source,
            )
            func_zones["functional_zone_type_id"] = func_zones["functional_zone_type"].map(lambda x: x["id"])
            func_zones["territory_zone"] = (
                func_zones["functional_zone_type_id"].astype(str).map(default_terr_zones_map)
            )

            fixed_ids = params.functional_zones.fixed_functional_zones_ids or []

            fixed_zones, remaining_zones = self._split_functional_zones_by_fixed_ids(
                func_zones=func_zones,
                fixed_ids=fixed_ids,
                scenario_id=params.scenario_id,
                project_id=params.project_id,
            )

            if only_on_zones:
                if fixed_ids:
                    params._initial_zones_to_add = remaining_zones
                    params._territory_gdf = fixed_zones
                existing_func_zones = None
            else:
                existing_func_zones = fixed_zones if fixed_ids else None
        else:
            existing_func_zones = None

        roads_extend_distance = (
            params.roads_extend_distance
            if getattr(params, "roads_extend_distance", None) is not None
            else 5
        )

        return GenPlanner(
            params._territory_gdf,
            **objects,
            existing_terr_zones=existing_func_zones,
            roads_extend_distance=roads_extend_distance,
            simplify_geometry_value=0.01,
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

        return GenPlanner(params._territory_gdf, simplify_geometry_value=0.01)

    @staticmethod
    async def form_genplanner_response(
            zones: gpd.GeoDataFrame,
            roads: gpd.GeoDataFrame,
            compact: bool = False,
    ) -> dict[Literal["zones", "roads"], dict]:
        """
        Function forms GenPlannerResultSchema from the given roads and zones GeoDataFrames.

        Args:
            roads (gpd.GeoDataFrame): Roads GeoDataFrame.
            zones (gpd.GeoDataFrame): Zones GeoDataFrame.
            compact (bool): Whether to keep only compact zone properties.

        Returns:
            dict[Literal["zones", "roads"], dict]: Serialized GenPlanner result.
        """
        zones = zones.copy()

        reverse_default_zone_map: dict[TerritoryZone, int] = {
            zone: int(zone_id)
            for zone_id, zone in default_terr_zones_map.items()
        }

        kind_to_default_id: dict[TerritoryZoneKind, int] = {}
        for zone_id, zone in default_terr_zones_map.items():
            kind_to_default_id.setdefault(zone.kind, int(zone_id))

        if "functional_zone_id" not in zones.columns:
            zones["functional_zone_id"] = None

        if "functional_zone_type_id" not in zones.columns:
            zones["functional_zone_type_id"] = None

        zones["is_generated"] = zones["functional_zone_id"].isna()

        if "territory_zone" in zones.columns:
            zones["_territory_zone_obj"] = zones["territory_zone"]

            zones["territory_zone_name"] = zones["_territory_zone_obj"].apply(
                lambda x: x.kind.value if x is not None and not pd.isna(x) else None
            )

            def _resolve_territory_zone_id(row: pd.Series) -> int | None:
                """
                Resolve mapped territory zone id for output.
                """
                functional_zone_type_id = row.get("functional_zone_type_id")
                if pd.notna(functional_zone_type_id):
                    return int(functional_zone_type_id)

                territory_zone = row.get("_territory_zone_obj")
                if territory_zone is None or pd.isna(territory_zone):
                    return None

                exact_id = reverse_default_zone_map.get(territory_zone)
                if exact_id is not None:
                    return exact_id

                return kind_to_default_id.get(territory_zone.kind)

            zones["territory_zone"] = zones.apply(_resolve_territory_zone_id, axis=1)

        if "func_zone" in zones.columns:
            zones.drop(columns="func_zone", inplace=True)

        if "_territory_zone_obj" in zones.columns:
            zones.drop(columns="_territory_zone_obj", inplace=True)

        if compact:
            allowed_columns = [
                "geometry",
                "territory_zone",
                "territory_zone_name",
                "functional_zone_id",
                "is_generated",
            ]
            zones = zones[[col for col in allowed_columns if col in zones.columns]].copy()

        return {
            "zones": json.loads(zones.to_json()),
            "roads": json.loads(roads.to_json()),
        }

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

    @staticmethod
    async def _run_features_generation_with_retries(
            genplanner: GenPlanner,
            funczone,
            relation_matrix,
            terr_zones_fix_points,
            attempts: int = 3,
            delay_seconds: float = 0.5,
    ) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
        """
        Run GenPlanner generation with retries for intermittent library failures.
        """
        last_exception: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                logger.info(
                    f"Running GenPlanner generation attempt {attempt}/{attempts}"
                )
                zones, roads = await asyncio.to_thread(
                    genplanner.features2terr_zones2blocks,
                    funczone=funczone,
                    relation_matrix=relation_matrix,
                    terr_zones_fix_points=terr_zones_fix_points,
                )
                logger.info(
                    f"GenPlanner generation attempt {attempt}/{attempts} succeeded"
                )
                return zones, roads
            except Exception as exc:
                last_exception = exc
                logger.exception(
                    f"GenPlanner generation attempt {attempt}/{attempts} failed: {exc}"
                )

                if attempt < attempts:
                    await asyncio.sleep(delay_seconds)

        if last_exception is not None:
            raise last_exception

        raise RuntimeError("GenPlanner generation failed without captured exception")

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

        relation_matrix_arg = self._build_relation_matrix_arg(params)

        zones, roads = await self._run_features_generation_with_retries(
            genplanner=genplanner,
            funczone=params._custom_func_zone,
            relation_matrix=relation_matrix_arg,
            terr_zones_fix_points=params._fix_zones_gdf,
            attempts=3,
            delay_seconds=0.5,
        )

        if (
            on_zones_only
            and params.functional_zones
            and (params.functional_zones.fixed_functional_zones_ids or [])
            and params._initial_zones_to_add is not None
            and not params._initial_zones_to_add.empty
        ):
            to_add = params._initial_zones_to_add.copy()
            sel = params._territory_gdf
            if sel is not None and not sel.empty:
                mask_geom = sel.geometry
                mask_geom = mask_geom[mask_geom.notna() & ~mask_geom.is_empty]
                try:
                    mask = mask_geom.make_valid().unary_union
                except Exception:
                    mask = mask_geom.unary_union

                to_add = to_add[to_add.geometry.notna() & ~to_add.geometry.is_empty]
                to_add["geometry"] = to_add.geometry.apply(lambda g: g.difference(mask) if g else g)
                to_add = to_add[to_add.geometry.notna() & ~to_add.geometry.is_empty]
            zones = pd.concat([zones, to_add], ignore_index=True)
        res = await self.form_genplanner_response(zones, roads, on_zones_only)
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
    async def get_func_zone_ratio(zone_id: int) -> dict[int, float]:
        """
        Return functional zone ratios mapped to default territory zone ids.
        """
        func_zone = scenario_func_zones_map[zone_id]

        kind_to_default_id: dict[TerritoryZoneKind, int] = {}
        for zone_id_str, terr_zone in default_terr_zones_map.items():
            zone_int = int(zone_id_str)
            if terr_zone.kind not in kind_to_default_id:
                kind_to_default_id[terr_zone.kind] = zone_int

        return {
            kind_to_default_id[terr_zone.kind]: round(ratio, 2)
            for terr_zone, ratio in func_zone.zones_ratio.items()
            if terr_zone.kind in kind_to_default_id
        }

    async def cut_scenario_territory(self, params, config: Config, token: str):
        await self.log_request_params(params, True)
        genplanner = await self.form_genplanner(
            params,
            token,
            config,
            False,
        )
        cut_gdf = genplanner.territory_to_work_with.to_crs(4326).copy()
        cut_gdf.geometry = cut_gdf.geometry.set_precision(1e-6)

        return cut_gdf.to_geo_dict()

    async def get_default_matrix(self) -> dict[str, list[tuple[int, int]]]:
        """
        Build default forbidden neighborhood pairs mapped to territory zone ids.
        """
        kind_to_ids: dict[TerritoryZoneKind, list[int]] = {}

        for zone_id_str, zone in default_terr_zones_map.items():
            zone_id = int(zone_id_str)
            kind_to_ids.setdefault(zone.kind, []).append(zone_id)

        forbidden_pairs_set: set[tuple[int, int]] = set()

        for left_kind, right_kind in FORBIDDEN_NEIGHBORHOOD:
            left_ids = kind_to_ids.get(left_kind, [])
            right_ids = kind_to_ids.get(right_kind, [])

            for left_id in left_ids:
                for right_id in right_ids:
                    if left_id == right_id:
                        continue

                    pair = tuple(sorted((left_id, right_id)))
                    forbidden_pairs_set.add(pair)

        forbidden_pairs = sorted(forbidden_pairs_set)

        return {
            "forbidden_pairs": forbidden_pairs,
        }

