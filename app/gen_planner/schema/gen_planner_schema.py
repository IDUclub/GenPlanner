from pydantic import BaseModel, field_validator

from app.common.geometries_dto.geometries import LineStringFeatureCollection, PolygonalFeatureCollection


class GenPlannerStartSchema(BaseModel):
    task_id: str


class GenPlannerResultSchema(BaseModel):
    zones: PolygonalFeatureCollection
    roads: LineStringFeatureCollection
