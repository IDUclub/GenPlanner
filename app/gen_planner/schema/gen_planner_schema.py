# from typing import Optional

from pydantic import BaseModel, field_validator

from app.common.exceptions.http_exception import http_exception
from app.gen_planner.dto.gen_planner_dto import PolygonalFeatureCollection


class GenPlannerStartSchema(BaseModel):
    task_id: str


class GenPlannerResultSchema(BaseModel):
    zones: PolygonalFeatureCollection | dict
    roads: FeatureCollection | dict

    @field_validator("zones", mode="after")
    @classmethod
    def validate_properties(cls, zones: FeatureCollection) -> FeatureCollection:
        """
        Function validates terr_zone is in FeatureCollection properties
        Args:
            zones: FeatureCollection properties
        Return:
            FeatureCollection
        Raises:
            500, if terr_zone was not in FeatureCollection properties
        """

        # ToDo add more checkers
        for feature in zones["features"]:
            if "terr_zone" not in feature["properties"]:
                raise http_exception(
                    500,
                    "The territory zone is missing from the feature in response. Check beck-end logic",
                    _input=zones,
                    _detail=None,
                )
        return zones


# class GenPlannerSchema(BaseModel):
#     status: str
#     progress: int
#     geojson: Optional[list[GenPlannerResultSchema]] = None
#     errors: Optional[dict] = None
