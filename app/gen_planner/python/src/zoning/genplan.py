from ._basic_func_zones import *
from .func_zones import FuncZone


class GenPlan:
    func_zone_ratio: dict[FuncZone, float]
    name: str
    min_zone_area: float

    def __init__(self, name, func_zone_ratio: dict[FuncZone, float]):
        self.func_zone_ratio = self._recalculate_ratio(func_zone_ratio)
        self.name = name
        self._calc_min_area()

    @staticmethod
    def _recalculate_ratio(func_zone_ratio):
        r_sum = sum(func_zone_ratio.values())
        return {zone: ratio / r_sum for zone, ratio in func_zone_ratio.items()}

    def _calc_min_area(self):
        self.min_zone_area = max([zone.min_zone_area / ratio for zone, ratio in self.func_zone_ratio.items()])


gen_plan = GenPlan(
    name="General Plan",
    func_zone_ratio={
        recreation_func_zone: 0.333,
        residential_func_zone: 0.277,
        industrial_func_zone: 0.133,
        transport_func_zone: 0.111,
        business_func_zone: 0.088,
        agricalture_func_zone: 0.033,
        special_func_zone: 0.022,
    },
)
