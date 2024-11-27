class FuncZone:
    min_block_area: float  # m^2
    name: str

    def __init__(self, min_block_area: float = 160000, name="test"):
        self.min_block_area = min_block_area
        self.name = name


class Scenario:
    zones_ratio: dict[FuncZone, float]
    name: str

    def __init__(self, zones_ratio, name):
        self.zones_ratio = zones_ratio
        self.name = name


class GenPlan:
    scenarios_ratio: dict[Scenario, float]

    def __init__(self, scenarios_ratio: dict[Scenario, float]):
        self.scenarios_ratio = scenarios_ratio
