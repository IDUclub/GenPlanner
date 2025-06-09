# from typing import Optional

from pydantic import BaseModel

from .gen_planner_dto import FeatureCollection


class GenPlannerStartSchema(BaseModel):
    task_id: str


class GenPlannerResultSchema(BaseModel):
    zones: FeatureCollection | dict
    roads: FeatureCollection | dict


# class GenPlannerSchema(BaseModel):
#     status: str
#     progress: int
#     geojson: Optional[list[GenPlannerResultSchema]] = None
#     errors: Optional[dict] = None
