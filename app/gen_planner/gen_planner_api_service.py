from app.common.config.config import config
from app.common.api_handlers.api_handler import urban_api_handler

import geopandas as gpd
from shapely.geometry import shape

class GenPlannerApiService:

    def __init__(self):
        self.headers = {"Authorization": f"Bearer {config.get('ACCESS_TOKEN')}"}
        self.urban_extractor = urban_api_handler
        self.v1 = "/api/v1"
        self.projects = "/projects"

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


gen_planner_api_service = GenPlannerApiService()
