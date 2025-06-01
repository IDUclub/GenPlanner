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


minimum_block_area = 80000

residential_terr = TerritoryZone(
    "residential",
    minimum_block_area,
)
industrial_terr = TerritoryZone(
    "industrial",
    minimum_block_area * 4,
)
business_terr = TerritoryZone(
    "business",
    minimum_block_area,
)
recreation_terr = TerritoryZone(
    "recreation",
    minimum_block_area * 2,
)
transport_terr = TerritoryZone(
    "transport",
    minimum_block_area,
)
agriculture_terr = TerritoryZone(
    "agriculture",
    minimum_block_area * 4,
)
special_terr = TerritoryZone(
    "special",
    minimum_block_area,
)
