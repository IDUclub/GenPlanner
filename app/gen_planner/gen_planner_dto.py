import json

from pydantic import BaseModel, Field

from app.common.geometries import Geometry

with open("app/common/example_geometry.json") as et:
    example_territory =json.load(et)


class GenPlannerDTO(BaseModel):

    territory: Geometry = Field(..., examples=[example_territory], description="The territory polygon")
