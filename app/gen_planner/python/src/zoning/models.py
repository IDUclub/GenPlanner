class TerritoryZone:
    min_block_area: float  # m^2
    name: str

    def __init__(self, name, min_block_area: float = 160000):
        self.min_block_area = min_block_area
        self.name = name

    def __str__(self):
        return f'Territory zone "{self.name}"'

    def __repr__(self):
        return self.__str__()


class FuncZone:
    zones_ratio: dict[TerritoryZone, float]
    name: str
    min_zone_area: float

    def __init__(self, zones_ratio, name):
        self.zones_ratio = self._recalculate_ratio(zones_ratio)
        self.name = name
        self._calc_min_area()

    def __str__(self):
        return f'Functional zone "{self.name}"'

    def __repr__(self):
        return self.__str__()

    @staticmethod
    def _recalculate_ratio(zones_ratio):
        r_sum = sum(zones_ratio.values())
        return {zone: ratio / r_sum for zone, ratio in zones_ratio.items()}

    def _calc_min_area(self):
        self.min_zone_area = max([zone.min_block_area / ratio for zone, ratio in self.zones_ratio.items()])


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
