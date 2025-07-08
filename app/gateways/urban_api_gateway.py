import asyncio
from typing import Awaitable

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

from app.common.api_handlers.json_api_handler import AsyncJsonApiHandler
from app.common.exceptions.http_exception import http_exception


class UrbanApiGateway:
    """
    Class for retrieving data from urban api for gen planner
    This class provides methods to interact with the Urban API, specifically for retrieving project information.
    Attributes:
        urban_extractor (AsyncApiHandler): Instance of AsyncApiHandler for making API requests.
    """

    def __init__(self, urban_api_url: str, max_async_extractions: int = 40):
        """
        Function initializes the UrbanApiGateway with an AsyncJsonApiHandler instance.
        Args:
            urban_api_url (str): An instance of AsyncJsonApiHandler to handle API requests.
            max_async_extractions (int): Maximum number of asynchronous extractions allowed. Defaults to 40.
        """

        self.urban_extractor: AsyncJsonApiHandler = AsyncJsonApiHandler(urban_api_url)
        self.max_async_extractions: int = max_async_extractions

    async def extract_several_requests(
            self,
            requests: list[Awaitable],
            as_gdfs: bool = False
    ) -> list[list | dict]:
        """
        Function to extract several requests asynchronously
        Args:
            requests (list[Awaitable]): list of async request functions to be executed
            as_gdfs (bool): If True, returns gpd.GeoDataFrame objects, otherwise returns raw results.
            Supports only FeatureCollection responses parsing.
        Returns:
            list[list | dict]: list of results from executed requests
        """

        if len(requests) > self.max_async_extractions:
            results = []
            for i in range(0, len(requests), self.max_async_extractions):
                batch_requests = requests[i:i + self.max_async_extractions]
                results += await asyncio.gather(*batch_requests)
        else:
            results = await asyncio.gather(*requests)
        if as_gdfs:
            try:
                results = [
                    gpd.GeoDataFrame.from_features(result, crs=4326) for result in results
                ]
            except Exception as e:
                raise http_exception(
                    500,
                    "Error during converting results to GeoDataFrame",
                    _input={"requests": "async requests"},
                    _detail={"error": repr(e)},
                ) from e
        return results

    async def get_project_info_by_project_id(
        self,
        project_id: int,
        token: str | None = None,
    ) -> dict:
        """
        Function returns project info from urban api
        Args:
            project_id (int): project id
            token (str, optional): token to authenticate with urban api. Defaults to None.
        Returns:
            dict: project info
        """

        url = f"/api/v1/projects/{project_id}"
        response = await self.urban_extractor.get(url, headers={"Authorization": f"Bearer {token}"} if token else None)
        return response

    async def get_territory_geom_by_project_id(
        self,
        project_id: int,
        token: str | None = None,
    ) -> gpd.GeoDataFrame:
        """
        Function retrieves territory geometry by project id
        Args:
            project_id (int): id of project
            token (str, optional): token to authenticate with urban api. Defaults to None.
        Returns:
            gpd.GeoDataFrame: GeoDataFrame with territory geometry
        """

        url = f"/api/v1/projects/{project_id}/territory"
        response = await self.urban_extractor.get(
            extra_url=url,
            headers={"Authorization": f"Bearer {token}"} if token else None,
        )

        result = gpd.GeoDataFrame(geometry=[shape(response["geometry"])], crs=4326)
        return result

    async def get_physical_objects(
            self,
            url: str,
            object_ids: list[int],
            token: str | None = None,
    ) -> gpd.GeoDataFrame | pd.DataFrame:
        """
        Function asynchronously extracts physical objects from urban api.
        Args:
            url (str): URL endpoint to fetch physical objects.
            object_ids (list[int]): List of physical object type IDs to filter by.
            token (str, optional): Token to authenticate with urban api. Defaults to None.
        Returns:
            gpd.GeoDataFrame | pd.DataFrame: GeoDataFrame with physical objects or DataFrame if no geometry is present.
        Raises:
            500: Internal Server Error if there is an issue with the request or response parsing
            Any HTTP from urban api will be raised as http_exception
        """

        requests = [self.urban_extractor.get(
            extra_url=url,
            params={
                "physical_object_type_id": object_id,
            },
            headers={"Authorization": f"Bearer {token}"} if token else None,
        ) for object_id in object_ids]
        results = await self.extract_several_requests(requests, as_gdfs=True)
        if results:
            return pd.concat(results)
        else:
            return None

    async def get_physical_objects_for_context(
        self,
        project_id: int,
        object_ids: list[int],
        token: str | None = None,
    ) -> gpd.GeoDataFrame | pd.DataFrame | None:
        """
        Function to get physical objects for a project
        Args:
            project_id (int): id of project
            object_ids (list[int]): list of object ids
            token (str, optional): token to authenticate with urban api. Defaults to None.
        Returns:
            gpd.GeoDataFrame | None: gdf with physical objects with listed objects ids or none if noe objects found
        """

        url = f"/api/v1/projects/{project_id}/context/geometries_with_all_objects"
        return await self.get_physical_objects(url, object_ids, token)

    async def get_physical_objects_for_scenario(
        self,
        scenario_id: int,
        object_ids: list[int],
        token: str | None = None,
    ) -> gpd.GeoDataFrame | pd.DataFrame | None:
        """
        Function to get physical objects for a scenario
        Args:s
            scenario_id (int): id of scenario
            object_ids (list[int]): list of object ids
            token (str, optional): token to authenticate with urban api. Defaults to None.
        Returns:
            gpd.GeoDataFrame | None: gdf with physical objects with listed objects ids or none if noe objects found
        """

        url = f"/api/v1/scenarios/{scenario_id}/physical_objects_with_geometry"
        return await self.get_physical_objects(url, object_ids, token)
