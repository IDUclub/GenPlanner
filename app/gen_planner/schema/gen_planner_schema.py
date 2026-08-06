from pydantic import BaseModel, field_validator

from app.common.geometries_dto.geometries import LineStringFeatureCollection, PolygonalFeatureCollection


class GenPlannerStartSchema(BaseModel):
    task_id: str


class GenPlannerResultSchema(BaseModel):
    zones: PolygonalFeatureCollection
    roads: LineStringFeatureCollection


class AvailableZoneSchema(BaseModel):
    """One generatable territorial zone: the id to use plus what it means."""

    id: int
    kind: str | None = None
    name: str
    profile: str | None = None
