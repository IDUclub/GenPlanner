from ._basic_terr_zones import *
from .terr_zones import TerritoryZone


class FuncZone:
    zones_ratio: dict[TerritoryZone, float]
    name: str
    min_zone_area: float
    zones_keys: dict[str, TerritoryZone]

    def __init__(self, zones_ratio, name):
        self.zones_ratio = self._recalculate_ratio(zones_ratio)
        self.zones_keys = {t.name: t for t in self.zones_ratio.keys()}
        self.name = name
        self._calc_min_area()

    def __str__(self):
        return f'Functional zone "{self.name}"'

    def __repr__(self):
        return self.__str__()

    def __hash__(self):
        return hash((self.name, self.min_zone_area))

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__hash__() == other.__hash__()
        else:
            return NotImplemented

    @staticmethod
    def _recalculate_ratio(zones_ratio):
        # remove 25% for roads
        if transport_terr in zones_ratio.keys():
            zones_ratio[transport_terr] = zones_ratio[transport_terr] * 0.75

        r_sum = sum(zones_ratio.values())
        return {zone: ratio / r_sum for zone, ratio in zones_ratio.items()}

    def _calc_min_area(self):
        self.min_zone_area = max([zone.min_block_area / ratio for zone, ratio in self.zones_ratio.items()])


basic_func_zone = FuncZone(
    {
        residential_terr: 0.25,
        industrial_terr: 0.12,
        business_terr: 0.08,
        recreation_terr: 0.3,
        transport_terr: 0.1,
        agriculture_terr: 0.03,
        special_terr: 0.02,
    },
    "basic",
)

residential_func_zone = FuncZone(
    {
        residential_terr: 0.5,
        business_terr: 0.1,
        recreation_terr: 0.1,
        transport_terr: 0.1,
        agriculture_terr: 0.05,
        special_terr: 0.05,
    },
    "residential territory",
)

industrial_func_zone = FuncZone(
    {
        industrial_terr: 0.5,
        business_terr: 0.1,
        recreation_terr: 0.05,
        transport_terr: 0.1,
        agriculture_terr: 0.05,
        special_terr: 0.05,
    },
    "industrial territory",
)
business_func_zone = FuncZone(
    {
        residential_terr: 0.1,
        business_terr: 0.5,
        recreation_terr: 0.1,
        transport_terr: 0.1,
        agriculture_terr: 0.05,
        special_terr: 0.05,
    },
    "business territory",
)
recreation_func_zone = FuncZone(
    {
        residential_terr: 0.2,
        business_terr: 0.1,
        recreation_terr: 0.5,
        transport_terr: 0.05,
        agriculture_terr: 0.1,
    },
    "recreation territory",
)
transport_func_zone = FuncZone(
    {
        industrial_terr: 0.1,
        business_terr: 0.05,
        recreation_terr: 0.05,
        transport_terr: 0.5,
        agriculture_terr: 0.05,
        special_terr: 0.05,
    },
    "transport territory",
)
agricalture_func_zone = FuncZone(
    {
        residential_terr: 0.1,
        industrial_terr: 0.1,
        business_terr: 0.05,
        recreation_terr: 0.1,
        transport_terr: 0.05,
        agriculture_terr: 0.5,
        special_terr: 0.05,
    },
    "agriculture territory",
)
special_func_zone = FuncZone(
    {
        residential_terr: 0.01,
        industrial_terr: 0.1,
        business_terr: 0.05,
        recreation_terr: 0.05,
        transport_terr: 0.05,
        agriculture_terr: 0.05,
        special_terr: 0.5,
    },
    "special territory",
)
