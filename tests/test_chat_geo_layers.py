from typing import Any

import geopandas as gpd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import box

from app.chat.chat_service import stream_chat_turn
from app.chat.custom_chat_service import stream_custom_chat_turn
from app.chat.dto.chat_custom_dto import ChatCustomTurnDTO
from app.chat.dto.chat_dto import ChatTurnDTO
from app.chat.files_controller import files_router
from app.chat.geo_layers import (
    FILE_SLOTS,
    assistant_message_parts,
    build_stored_layer,
    new_result_id,
    object_key,
    store_result_layers,
)
from app.common.geometries_dto.geometries import PolygonalFeatureCollection
from app.common.object_storage.object_storage import (
    LocalStorage,
    MinioStorage,
    ObjectStorage,
    ObjectStorageError,
    build_object_storage,
)

_USER_ID = "00000000-0000-0000-0000-000000000001"
_COLLECTION = {"type": "FeatureCollection", "features": []}
_RESULT_PAYLOAD = {"zones": _COLLECTION, "roads": _COLLECTION, "territory": _COLLECTION}


async def _collect(agen):
    return [item async for item in agen]


class FakeConfig:
    def __init__(self, values: dict[str, str]):
        self._values = values

    def get(self, key):
        if key not in self._values:
            raise ValueError(key)
        return self._values[key]


class FailingStorage(ObjectStorage):
    def put_json(self, payload, object_key):  # pylint: disable=redefined-outer-name
        raise ObjectStorageError("minio is down")

    def exists(self, object_key):  # pylint: disable=redefined-outer-name
        raise ObjectStorageError("minio is down")

    def open_stream(self, object_key):  # pylint: disable=redefined-outer-name
        raise ObjectStorageError("minio is down")


class RecordingChatStorageClient:
    """Keeps add_message calls as sent, parts included, to check what history will hold."""

    def __init__(self):
        self.messages: list[dict[str, Any]] = []

    async def create_chat(self, user_id, *, title=None, scenario_id=None, project_id=None, metadata=None):
        return {"chat_id": "chat-1", "title": title}

    async def get_chat(self, user_id, chat_id):
        return {"chat_id": chat_id, "messages": list(self.messages)}

    async def add_message(self, user_id, chat_id, *, role, content=None, parts=None, metadata=None):
        self.messages.append({"role": role, "content": content, "parts": parts, "metadata": metadata or {}})
        return {"message_id": f"msg-{len(self.messages)}"}


class FakeChatClient:
    def __init__(self, decisions: list[dict[str, Any]]):
        self._decisions = list(decisions)

    async def complete_json(self, messages, schema, temperature=None):
        return self._decisions.pop(0)


class FakeGenPlannerResult:
    def model_dump(self):
        return {"zones": _COLLECTION, "roads": _COLLECTION}


class FakeUrbanApiClient:
    async def get_scenario_info(self, scenario_id, token):
        return {"project": {"project_id": 7}}


class FakeGenPlannerService:
    def __init__(self):
        self.urban_api_client = FakeUrbanApiClient()

    async def run_func_generation(self, params, token, config):
        params._territory_gdf = gpd.GeoDataFrame(  # pylint: disable=protected-access
            geometry=[box(30.0, 59.0, 30.1, 59.1)], crs=4326
        )
        return FakeGenPlannerResult()

    async def run_custom_func_generation(self, params):
        return FakeGenPlannerResult()


_TERRITORY = PolygonalFeatureCollection.model_validate(
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[30.0, 59.0], [30.1, 59.0], [30.1, 59.1], [30.0, 59.1], [30.0, 59.0]]],
                },
                "properties": {},
            }
        ],
    }
)


def test_stored_layer_url_is_relative_to_the_service():
    """The frontend prepends its own address for `source_service`; no host goes into history."""

    result_id = new_result_id()

    layer = build_stored_layer(slot="zones", result_id=result_id)

    assert layer["url"] == f"/genplanner/files/zones/{result_id}"
    assert layer["download_url"] is None
    assert layer["source_service"] == "genplanner"
    assert layer["mime_type"] == "application/geo+json"


@pytest.mark.parametrize("result_id", ["../etc", "A" * 32, "0" * 31, "g" * 32])
def test_object_key_refuses_anything_but_a_result_id(result_id):
    with pytest.raises(ValueError):
        object_key(result_id, "zones")


def test_message_parts_keep_the_reply_as_a_text_part():
    """ChatStorage takes content or parts, never both -- the text would be lost otherwise."""

    layer = build_stored_layer(slot="roads", result_id=new_result_id())

    parts = assistant_message_parts("готово", [layer])

    assert parts[0] == {"kind": "text", "payload": {"text": "готово"}}
    assert parts[1]["kind"] == "file"
    assert parts[1]["payload"]["url"] == layer["url"]
    assert "download_url" not in parts[1]["payload"]


async def test_store_result_layers_writes_every_slot(tmp_path):
    storage = LocalStorage(tmp_path)
    file_layers: list[dict[str, Any]] = []

    events = await _collect(store_result_layers(storage, _RESULT_PAYLOAD, file_layers))

    assert [event["name"] for event in events] == list(FILE_SLOTS)
    assert all(event["type"] == "file" for event in events)
    result_id = events[0]["url"].rsplit("/", 1)[1]
    for slot in FILE_SLOTS:
        assert storage.exists(object_key(result_id, slot))
    assert file_layers == [{k: v for k, v in event.items() if k != "type"} for event in events]


async def test_store_result_layers_turns_a_storage_failure_into_warnings():
    file_layers: list[dict[str, Any]] = []

    events = await _collect(store_result_layers(FailingStorage(), _RESULT_PAYLOAD, file_layers))

    assert {event["type"] for event in events} == {"warning"}
    assert {event["stage"] for event in events} == {"store_layer"}
    assert not file_layers


async def test_store_result_layers_is_a_no_op_without_storage():
    file_layers: list[dict[str, Any]] = []

    assert await _collect(store_result_layers(None, _RESULT_PAYLOAD, file_layers)) == []


async def test_scenario_chat_persists_layers_as_file_parts(tmp_path):
    storage = RecordingChatStorageClient()
    llm = FakeChatClient([{"action": "run_generation", "patch": {"territory_balance": {"жилая": 1.0}}, "reply": "ok"}])

    events = await _collect(
        stream_chat_turn(
            llm_client=llm,
            chat_storage_client=storage,
            genplanner_service=FakeGenPlannerService(),
            config=None,
            token="token",
            user_id=_USER_ID,
            scenario_id=1,
            params=ChatTurnDTO(user_query="запускай"),
            object_storage=LocalStorage(tmp_path),
        )
    )

    assert [event["name"] for event in events if event["type"] == "file"] == list(FILE_SLOTS)
    assistant = storage.messages[-1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] is None
    assert [part["kind"] for part in assistant["parts"]] == ["text", "file", "file", "file"]
    assert [part["payload"]["name"] for part in assistant["parts"][1:]] == list(FILE_SLOTS)


async def test_custom_chat_persists_layers_as_file_parts(tmp_path):
    storage = RecordingChatStorageClient()
    llm = FakeChatClient([{"action": "run_generation", "patch": {"profile_id": 1}, "reply": "запускаю"}])

    events = await _collect(
        stream_custom_chat_turn(
            llm_client=llm,
            chat_storage_client=storage,
            genplanner_service=FakeGenPlannerService(),
            user_id=_USER_ID,
            territory=_TERRITORY,
            params=ChatCustomTurnDTO(user_query="жилую застройку, запускай", chat_id=None),
            object_storage=LocalStorage(tmp_path),
        )
    )

    file_events = [event for event in events if event["type"] == "file"]
    assert [event["name"] for event in file_events] == list(FILE_SLOTS)
    result_index = next(i for i, event in enumerate(events) if event["type"] == "result")
    assert events.index(file_events[0]) > result_index
    assistant = storage.messages[-1]
    assert assistant["parts"][0] == {"kind": "text", "payload": {"text": "запускаю"}}
    assert [part["payload"]["url"] for part in assistant["parts"][1:]] == [event["url"] for event in file_events]


async def test_chat_without_generation_keeps_plain_content(tmp_path):
    storage = RecordingChatStorageClient()
    llm = FakeChatClient([{"action": "chat", "reply": "привет"}])

    await _collect(
        stream_custom_chat_turn(
            llm_client=llm,
            chat_storage_client=storage,
            genplanner_service=FakeGenPlannerService(),
            user_id=_USER_ID,
            territory=_TERRITORY,
            params=ChatCustomTurnDTO(user_query="привет", chat_id=None),
            object_storage=LocalStorage(tmp_path),
        )
    )

    assistant = storage.messages[-1]
    assert assistant["content"] == "привет"
    assert assistant["parts"] is None


def _files_client(storage: ObjectStorage | None) -> TestClient:
    app = FastAPI()
    app.state.object_storage = storage
    app.include_router(files_router, prefix="/genplanner")
    return TestClient(app)


def test_files_route_streams_the_stored_layer(tmp_path):
    storage = LocalStorage(tmp_path)
    result_id = new_result_id()
    payload = {"type": "FeatureCollection", "features": [], "name": "зоны"}
    storage.put_json(payload, object_key(result_id, "zones"))

    response = _files_client(storage).get(f"/genplanner/files/zones/{result_id}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/geo+json"
    assert response.json() == payload


@pytest.mark.parametrize(
    "path",
    ["/genplanner/files/buildings/{id}", "/genplanner/files/zones/not-a-result-id", "/genplanner/files/roads/{id}"],
)
def test_files_route_returns_404_for_unknown_layers(tmp_path, path):
    storage = LocalStorage(tmp_path)
    result_id = new_result_id()
    storage.put_json(_COLLECTION, object_key(result_id, "zones"))

    response = _files_client(storage).get(path.format(id=result_id))

    assert response.status_code == 404


def test_files_route_reports_unavailable_storage():
    response = _files_client(FailingStorage()).get(f"/genplanner/files/zones/{new_result_id()}")

    assert response.status_code == 502


def test_files_route_without_storage_is_503():
    response = _files_client(None).get(f"/genplanner/files/zones/{new_result_id()}")

    assert response.status_code == 503


def test_build_object_storage_falls_back_to_local_disk(tmp_path):
    storage = build_object_storage(FakeConfig({"LAYERS_STORAGE_DIR": str(tmp_path)}))

    assert isinstance(storage, LocalStorage)


def test_build_object_storage_refuses_a_partial_minio_config():
    """Silently falling back would give history links that die at the next restart."""

    with pytest.raises(ObjectStorageError, match="FILESERVER_SECRET_KEY"):
        build_object_storage(
            FakeConfig(
                {
                    "FILESERVER_ENDPOINT": "minio:9000",
                    "FILESERVER_ACCESS_KEY": "key",
                    "FILESERVER_BUCKET_NAME": "genplanner",
                }
            )
        )


def test_build_object_storage_uses_minio_when_fully_configured():
    storage = build_object_storage(
        FakeConfig(
            {
                "FILESERVER_ENDPOINT": "minio:9000",
                "FILESERVER_ACCESS_KEY": "key",
                "FILESERVER_SECRET_KEY": "secret",
                "FILESERVER_BUCKET_NAME": "genplanner",
            }
        )
    )

    assert isinstance(storage, MinioStorage)
