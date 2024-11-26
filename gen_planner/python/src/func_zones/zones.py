class FuncZone:
    min_block_area: float  # m^2
    name: str

    def __init__(self, min_block_area: float = 160000, name="test"):
        self.min_block_area = min_block_area
        self.name = name


residential = FuncZone(0.1, "residential")
industrial = FuncZone(0.1, "industrial")
business = FuncZone(0.1, "business")
recreation = FuncZone(0.1, "recreation")
transport = FuncZone(0.1, "transport")
agricalture = FuncZone(0.1, "agriculture")
special = FuncZone(0.1, "special")


class Scenario:
    zones_ratio = dict[FuncZone, float]

    def __init__(self, zones_ratio):
        self.zones_ratio = zones_ratio


basic_gen_plan = Scenario(
    {
        residential: 0.25,
        industrial: 0.12,
        business: 0.08,
        recreation: 0.3,
        transport: 0.1,
        agricalture: 0.03,
        special: 0.02,
    }
)

residential_territory = Scenario(
    {
        residential: 0.5,
        business: 0.1,
        recreation: 0.1,
        transport: 0.1,
        agricalture: 0.05,
        special: 0.05,
    }
)

industrial_territory = Scenario(
    {
        industrial: 0.5,
        business: 0.1,
        recreation: 0.05,
        transport: 0.1,
        agricalture: 0.05,
        special: 0.05,
    }
)
business_territory = Scenario(
    {
        residential: 0.1,
        business: 0.5,
        recreation: 0.1,
        transport: 0.1,
        agricalture: 0.05,
        special: 0.05,
    }
)
recreation_territory = Scenario(
    {
        residential: 0.2,
        business: 0.1,
        recreation: 0.5,
        transport: 0.05,
        agricalture: 0.1,
    }
)
transport_territory = Scenario(
    {
        industrial: 0.1,
        business: 0.05,
        recreation: 0.05,
        transport: 0.5,
        agricalture: 0.05,
        special: 0.05,
    }
)
agricalture_territory = Scenario(
    {
        residential: 0.1,
        industrial: 0.1,
        business: 0.05,
        recreation: 0.1,
        transport: 0.05,
        agricalture: 0.5,
        special: 0.05,
    }
)
special_territory = Scenario(
    {
        residential: 0.01,
        industrial: 0.1,
        business: 0.05,
        recreation: 0.05,
        transport: 0.05,
        agricalture: 0.03,
        special: 0.02,
    }
)
