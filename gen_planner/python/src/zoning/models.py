class TerritoryZone:
    min_block_area: float  # m^2
    name: str

    def __init__(self, name, min_block_area: float = 160000):
        self.min_block_area = min_block_area
        self.name = name


class FuncZone:
    zones_ratio: dict[TerritoryZone, float]
    name: str

    def __init__(self, zones_ratio, name):
        self.zones_ratio = zones_ratio
        self.name = name

    def _calc_min_area(self):
        [(ratio*zone.min_block_area,ratio) for zone,ratio in self.zones_ratio.items()]


class GenPlan:
    func_zone_ratio: dict[FuncZone, float]
    name: str

    def __init__(self, name, scenarios_ratio: dict[FuncZone, float]):
        self.func_zone_ratio = scenarios_ratio
        self.name = name
