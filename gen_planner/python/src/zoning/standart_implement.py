from .models import TerritoryZone, FuncZone, GenPlan

minimum_block_area = 160000

residential = TerritoryZone(
    "residential",
    minimum_block_area,
)
industrial = TerritoryZone(
    "industrial",
    minimum_block_area * 4,
)
business = TerritoryZone(
    "business",
    minimum_block_area,
)
recreation = TerritoryZone(
    "recreation",
    minimum_block_area * 2,
)
transport = TerritoryZone(
    "transport",
    minimum_block_area,
)
agriculture = TerritoryZone(
    "agriculture",
    minimum_block_area * 4,
)
special = TerritoryZone(
    "special",
    minimum_block_area,
)

basic_scenario = FuncZone(
    {
        residential: 0.25,
        industrial: 0.12,
        business: 0.08,
        recreation: 0.3,
        transport: 0.1,
        agriculture: 0.03,
        special: 0.02,
    },
    "basic",
)

residential_territory = FuncZone(
    {
        residential: 0.5,
        business: 0.1,
        recreation: 0.1,
        transport: 0.1,
        agriculture: 0.05,
        special: 0.05,
    },
    "residential territory",
)

industrial_territory = FuncZone(
    {
        industrial: 0.5,
        business: 0.1,
        recreation: 0.05,
        transport: 0.1,
        agriculture: 0.05,
        special: 0.05,
    },
    "industrial territory",
)
business_territory = FuncZone(
    {
        residential: 0.1,
        business: 0.5,
        recreation: 0.1,
        transport: 0.1,
        agriculture: 0.05,
        special: 0.05,
    },
    "business territory",
)
recreation_territory = FuncZone(
    {
        residential: 0.2,
        business: 0.1,
        recreation: 0.5,
        transport: 0.05,
        agriculture: 0.1,
    },
    "recreation territory",
)
transport_territory = FuncZone(
    {
        industrial: 0.1,
        business: 0.05,
        recreation: 0.05,
        transport: 0.5,
        agriculture: 0.05,
        special: 0.05,
    },
    "transport territory",
)
agricalture_territory = FuncZone(
    {
        residential: 0.1,
        industrial: 0.1,
        business: 0.05,
        recreation: 0.1,
        transport: 0.05,
        agriculture: 0.5,
        special: 0.05,
    },
    "agriculture territory",
)
special_territory = FuncZone(
    {
        residential: 0.01,
        industrial: 0.1,
        business: 0.05,
        recreation: 0.05,
        transport: 0.05,
        agriculture: 0.05,
        special: 0.5,
    },
    "special territory",
)

gen_plan = GenPlan(
    name="General Plan",
    func_zone_ratio={
        recreation_territory: 0.333,
        residential_territory: 0.277,
        industrial_territory: 0.133,
        transport_territory: 0.111,
        business_territory: 0.088,
        agricalture_territory: 0.033,
        special_territory: 0.022,
    }
)
