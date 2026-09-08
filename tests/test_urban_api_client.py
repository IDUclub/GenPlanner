from unittest.mock import AsyncMock

from app.clients.urban_api_client import UrbanApiClient


def _physical_objects_collection(*, nested_type_id: int, flat_type_id: int | None = None) -> dict:
    properties = {
        "physical_object_id": 1898125,
        "physical_object_type": {
            "physical_object_type_id": nested_type_id,
            "name": "Местная дорога",
        },
    }
    if flat_type_id is not None:
        properties["physical_object_type_id"] = flat_type_id

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[30.0, 60.0], [30.1, 60.1]]},
                "properties": properties,
            }
        ],
    }


async def test_physical_object_type_id_is_flattened_from_urban_api_response():
    handler = AsyncMock()
    handler.get.return_value = _physical_objects_collection(nested_type_id=52)
    client = UrbanApiClient(handler)

    objects = await client.get_physical_objects("/physical_objects", [52], token="token")

    assert objects.iloc[0]["physical_object_type_id"] == 52
    assert objects.iloc[0]["physical_object_type"]["physical_object_type_id"] == 52


async def test_existing_flat_physical_object_type_id_takes_precedence():
    handler = AsyncMock()
    handler.get.return_value = _physical_objects_collection(nested_type_id=52, flat_type_id=51)
    client = UrbanApiClient(handler)

    objects = await client.get_physical_objects("/physical_objects", [51], token="token")

    assert objects.iloc[0]["physical_object_type_id"] == 51
