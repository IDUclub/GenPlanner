from .models import TerritoryZone, FuncZone, GenPlan

minimum_block_area = 170000

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
    }
)