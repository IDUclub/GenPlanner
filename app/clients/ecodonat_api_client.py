from types import NoneType

import geopandas as gpd
from fastapi import HTTPException
from loguru import logger

from app.common.api_handlers.json_api_handler import AsyncJsonApiHandler
from app.common.exceptions.http_exception import http_exception

from .api_client import ApiClient


class EcodonutApiClient(ApiClient):
    """
    Class for retrieving data from ecodonut api for gen planner
    This class provides methods to interact with the Ecodonut API.
    Attributes:
        api_handler (AsyncApiHandler): Instance of AsyncApiHandler for making API requests.
        max_async_extractions (int): Maximum number of asynchronous extractions allowed. Defaults to 40.
    """

    def __init__(self, ecodonut_api_json_handler: AsyncJsonApiHandler, max_async_extractions: int = 40):
        """
        Function initializes the UrbanApiClient with an AsyncJsonApiHandler instance.
        Args:
            ecodonut_api_json_handler (str): An instance of AsyncJsonApiHandler to handle API requests.
            max_async_extractions (int): Maximum number of asynchronous extractions allowed. Defaults to 40.
        """

        super().__init__(ecodonut_api_json_handler, max_async_extractions)

    async def get_slope_polygons(self, token: str, project_id: int, angle: int | None = None) -> gpd.GeoDataFrame:
        """
        Function retrieves slope polygons from ecodonut api for gen planner.
        Args:
            token (str): The API auth token.
            project_id (int): Target project ID.
            angle (int | None): The angle to retrieve polygons from. Defaults to None.
        Returns:
            gpd.GeoDataFrame: A GeoDataFrame containing the slope polygons.
            If no angle (None) is provided, returns empty gpd.GeoDataFrame.
        Raises:
            HTTPException: Any HTTP exception raised by Ecodonut API   .
        """

        if isinstance(angle, NoneType):
            return gpd.GeoDataFrame()
        response = await self.api_handler.get(
            f"/ecodonut/{project_id}/slope_polygons",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            return gpd.GeoDataFrame.from_features(response, crs=4326).query(f"slope_deg <= {angle}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(e)
            raise
