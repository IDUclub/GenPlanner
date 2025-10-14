from functools import total_ordering


@total_ordering
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

    def __hash__(self):
        return hash((self.name, self.min_block_area))

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__hash__() == other.__hash__()
        else:
            return NotImplemented

    def __lt__(self, other):
        if not isinstance(other, TerritoryZone):
            return NotImplemented
        return (self.name, self.min_block_area) < (other.name, other.min_block_area)


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
