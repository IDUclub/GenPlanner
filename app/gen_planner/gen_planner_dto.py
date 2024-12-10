import json

from typing import Literal
from pydantic import BaseModel, Field

from app.common.geometries import Geometry

with open("app/common/example_geometry.json") as et:
    example_territory =json.load(et)


class GenPlannerDTO(BaseModel):

    territory: Geometry = Field(..., examples=[example_territory], description="The territory polygon")


class GenPlannerFuncZonesDTO(GenPlannerDTO):

    scenario: Literal[
        "Профиль: Базовый",
        "Профиль: Жилая зона",
        "Профиль: Промышленная зона",
        "Профиль: Общественно-деловая зона",
        "Профиль: Рекреационная зона",
        "Профиль: Транспортная зона",
        "Профиль: Сельскохозяйственная зона",
        "Профиль: Особого назначения"
    ] = Field(..., examples=["Профиль: Базовый"], description="Scenario func zone type")


class GenPlannerTerZonesDTO(GenPlannerDTO):
    scenario: Literal[
        "Профиль: Жилая зона",
        "Профиль: Промышленная зона",
        "Профиль: Общественно-деловая зона",
        "Профиль: Рекреационная зона",
        "Профиль: Транспортная зона",
        "Профиль: Сельскохозяйственная зона",
        "Профиль: Особого назначения"
] = Field(..., examples=["Профиль: Жилая зона"], description="Scenario ter zone type")
