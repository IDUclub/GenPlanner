from typing import Optional

from geojson_pydantic import FeatureCollection
from pydantic import BaseModel


class GenPlannerStartSchema(BaseModel):
    task_id: str


class GenPlannerResultSchema(BaseModel):
    zones: FeatureCollection
    roads: FeatureCollection


# class GenPlannerSchema(BaseModel):
#     status: str
#     progress: int
#     geojson: Optional[list[GenPlannerResultSchema]] = None
#     errors: Optional[dict] = None
