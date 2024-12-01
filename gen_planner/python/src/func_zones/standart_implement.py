from .models import FuncZone, Scenario, GenPlan

minimum_block_area = 160000

residential = FuncZone(minimum_block_area, "residential")
industrial = FuncZone(minimum_block_area * 4, "industrial")
business = FuncZone(minimum_block_area, "business")
recreation = FuncZone(minimum_block_area * 2, "recreation")
transport = FuncZone(minimum_block_area, "transport")
agricalture = FuncZone(minimum_block_area * 4, "agriculture")
special = FuncZone(minimum_block_area, "special")

basic_scenario = Scenario(
    {
        residential: 0.25,
        industrial: 0.12,
        business: 0.08,
        recreation: 0.3,
        transport: 0.1,
        agricalture: 0.03,
        special: 0.02,
    },
    'basic'
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
    ,
    'residential territory'
)

industrial_territory = Scenario(
    {
        industrial: 0.5,
        business: 0.1,
        recreation: 0.05,
        transport: 0.1,
        agricalture: 0.05,
        special: 0.05,
    },
    'industrial territory'
)
business_territory = Scenario(
    {
        residential: 0.1,
        business: 0.5,
        recreation: 0.1,
        transport: 0.1,
        agricalture: 0.05,
        special: 0.05,
    },
    'business territory'
)
recreation_territory = Scenario(
    {
        residential: 0.2,
        business: 0.1,
        recreation: 0.5,
        transport: 0.05,
        agricalture: 0.1,
    },
    'recreation territory'
)
transport_territory = Scenario(
    {
        industrial: 0.1,
        business: 0.05,
        recreation: 0.05,
        transport: 0.5,
        agricalture: 0.05,
        special: 0.05,
    },
    'transport territory'
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
    },
    'agriculture territory'
)
special_territory = Scenario(
    {
        residential: 0.01,
        industrial: 0.1,
        business: 0.05,
        recreation: 0.05,
        transport: 0.05,
        agricalture: 0.05,
        special: 0.5,
    },
    'special territory'
)

gen_plan = GenPlan({residential_territory: 0.196,
                    industrial_territory: 0.08,
                    business_territory: 0.1195,
                    recreation_territory: 0.203,
                    transport_territory: 0.1225,
                    agricalture_territory: 0.081,
                    special_territory: 0.049,
                    })
