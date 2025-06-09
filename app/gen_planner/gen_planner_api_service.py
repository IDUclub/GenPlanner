import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

from app.common.api_handlers.api_handler import urban_api_handler
from app.common.config.config import config


class GenPlannerApiService:

    def __init__(self):
        self.headers = {"Authorization": f"Bearer {config.get('ACCESS_TOKEN')}"}
        self.urban_extractor = urban_api_handler
        self.v1 = "/api/v1"
        self.projects = "/projects"

    async def get_project_info_by_project_id(
        self,
        project_id: int,
    ) -> dict:
        """
        Function returns project info from urban api
        Args:
            project_id (int): project id
        Returns:
            dict: project info
        """

        url = f"{self.v1}/projects/{project_id}"
        response = await self.urban_extractor.get(url, headers=self.headers)
        return response

    async def get_territory_geom_by_project_id(
        self,
        project_id: int,
    ) -> gpd.GeoDataFrame:

        url = f"{self.v1}{self.projects}/{project_id}/territory"
        response = await self.urban_extractor.get(
            extra_url=url,
            headers=self.headers,
        )

        result = gpd.GeoDataFrame(geometry=[shape(response["geometry"])], crs=4326)
        return result

    async def get_physical_objects_for_scenario(
        self,
        scenario_id: int,
        object_ids: list[int],
    ) -> gpd.GeoDataFrame | pd.DataFrame | None:
        """
        Function to get physical objects for a scenario
        Args:s
            scenario_id (int): id of scenario
            object_ids (list[int]): list of object ids
        Returns:
            gpd.GeoDataFrame | None: gdf with physical objects with listed objects ids or none if noe objects found
        """

        url = f"{self.v1}/scenarios/{scenario_id}/physical_objects_with_geometry"

        layers = []
        for object_id in object_ids:
            response = await self.urban_extractor.get(
                extra_url=url,
                params={
                    "physical_object_type_id": object_id,
                },
                headers=self.headers,
            )
            if response["features"]:
                layers.append(gpd.GeoDataFrame.from_features(response, crs=4326))
        if layers:
            objects_layer = pd.concat(layers)
            return objects_layer
        else:
            return None


gen_planner_api_service = GenPlannerApiService()
