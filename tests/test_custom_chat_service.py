from typing import Any

import pytest
from fastapi import HTTPException

from app.chat.custom_chat_service import (
    _extract_territory_from_history,
    _territory_to_geojson_dict,
    stream_custom_chat_turn,
)
from app.chat.dto.chat_custom_dto import ChatCustomTurnDTO
from app.common.geometries_dto.geometries import PolygonalFeatureCollection


def _territory(lon: float, lat: float) -> PolygonalFeatureCollection:
    return PolygonalFeatureCollection.model_validate(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [lon, lat],
                                [lon + 0.1, lat],
                                [lon + 0.1, lat + 0.1],
                                [lon, lat + 0.1],
                                [lon, lat],
                            ]
                        ],
                    },
                    "properties": {},
                }
            ],
        }
    )


_TERRITORY_A = _territory(30.0, 59.0)
_TERRITORY_B = _territory(40.0, 69.0)


class FakeChatStorageClient:
    """In-memory stand-in for ChatStorageClient, mirroring its create_chat/get_chat/add_message contract."""

    def __init__(self):
        self._chats: dict[str, dict[str, Any]] = {}
        self._next_id = 1

    async def create_chat(self, user_id, *, title=None, scenario_id=None, project_id=None, metadata=None):
        chat_id = f"chat-{self._next_id}"
        self._next_id += 1
        self._chats[chat_id] = {"chat_id": chat_id, "messages": []}
        return {"chat_id": chat_id, "title": title}

    async def get_chat(self, user_id, chat_id):
        return self._chats[chat_id]

    async def add_message(self, user_id, chat_id, *, role, content=None, parts=None, metadata=None):
        message = {"role": role, "content": content, "metadata": metadata or {}}
        self._chats[chat_id]["messages"].append(message)
        return {"message_id": f"msg-{len(self._chats[chat_id]['messages'])}"}


class FakeChatClient:
    def __init__(self, decisions: list[dict[str, Any]]):
        self._decisions = list(decisions)

    async def complete_json(self, messages, schema):
        return self._decisions.pop(0)


class FakeGenPlannerResult:
    def model_dump(self):
        empty_collection = {"type": "FeatureCollection", "features": []}
        return {"zones": empty_collection, "roads": empty_collection}


class FakeGenPlannerService:
    def __init__(self):
        self.calls: list[Any] = []

    async def run_custom_func_generation(self, params):
        self.calls.append(params)
        return FakeGenPlannerResult()


async def _collect(agen):
    return [item async for item in agen]


def test_extract_territory_from_history_prefers_the_most_recent_upload():
    messages = [
        {"role": "user", "metadata": {"territory": _territory_to_geojson_dict(_TERRITORY_A)}},
        {"role": "assistant", "metadata": {}},
        {"role": "user", "metadata": {"territory": _territory_to_geojson_dict(_TERRITORY_B)}},
    ]

    extracted = _extract_territory_from_history(messages)

    assert extracted is not None
    assert _territory_to_geojson_dict(extracted) == _territory_to_geojson_dict(_TERRITORY_B)


@pytest.mark.asyncio
async def test_reuploaded_territory_replaces_the_original_for_later_turns():
    storage = FakeChatStorageClient()
    genplanner_service = FakeGenPlannerService()
    llm = FakeChatClient(
        [
            {"action": "chat", "reply": "первая территория принята"},
            {"action": "chat", "reply": "новая территория принята"},
            {"action": "run_generation", "patch": {"profile_id": 1}, "reply": "запускаю"},
        ]
    )

    turn_1 = await _collect(
        stream_custom_chat_turn(
            llm_client=llm,
            chat_storage_client=storage,
            genplanner_service=genplanner_service,
            user_id="00000000-0000-0000-0000-000000000001",
            territory=_TERRITORY_A,
            params=ChatCustomTurnDTO(user_query="вот граница", chat_id=None),
        )
    )
    chat_id = next(e["chat_id"] for e in turn_1 if e["type"] == "chat_created")

    await _collect(
        stream_custom_chat_turn(
            llm_client=llm,
            chat_storage_client=storage,
            genplanner_service=genplanner_service,
            user_id="00000000-0000-0000-0000-000000000001",
            territory=_TERRITORY_B,
            params=ChatCustomTurnDTO(user_query="вот другая граница", chat_id=chat_id),
        )
    )

    await _collect(
        stream_custom_chat_turn(
            llm_client=llm,
            chat_storage_client=storage,
            genplanner_service=genplanner_service,
            user_id="00000000-0000-0000-0000-000000000001",
            territory=None,
            params=ChatCustomTurnDTO(user_query="жилую застройку, запускай", chat_id=chat_id),
        )
    )

    assert len(genplanner_service.calls) == 1
    used_territory = genplanner_service.calls[0].territory
    assert _territory_to_geojson_dict(used_territory) == _territory_to_geojson_dict(_TERRITORY_B)


@pytest.mark.asyncio
async def test_agent_picks_the_profile_by_name_and_generation_gets_its_id():
    """The agent answers in zone names now; the id only appears when the DTO is built."""

    storage = FakeChatStorageClient()
    genplanner_service = FakeGenPlannerService()
    llm = FakeChatClient([{"action": "run_generation", "patch": {"profile": "жилая"}, "reply": "запускаю"}])

    await _collect(
        stream_custom_chat_turn(
            llm_client=llm,
            chat_storage_client=storage,
            genplanner_service=genplanner_service,
            user_id="00000000-0000-0000-0000-000000000001",
            territory=_TERRITORY_A,
            params=ChatCustomTurnDTO(user_query="жилую застройку, запускай", chat_id=None),
        )
    )

    assert len(genplanner_service.calls) == 1
    assert genplanner_service.calls[0].profile_id == 1


@pytest.mark.asyncio
async def test_unresolvable_profile_does_not_leave_the_user_thinking_generation_started():
    """The model may claim it is running; if nothing ran, the user must be told so."""

    storage = FakeChatStorageClient()
    genplanner_service = FakeGenPlannerService()
    llm = FakeChatClient([{"action": "run_generation", "patch": {"profile": "зона мечты"}, "reply": "запускаю"}])

    events = await _collect(
        stream_custom_chat_turn(
            llm_client=llm,
            chat_storage_client=storage,
            genplanner_service=genplanner_service,
            user_id="00000000-0000-0000-0000-000000000001",
            territory=_TERRITORY_A,
            params=ChatCustomTurnDTO(user_query="__bogus__ запускай", chat_id=None),
        )
    )

    reply = "".join(e["content"] for e in events if e["type"] == "token")
    assert not genplanner_service.calls
    assert not any(e["type"] == "result" for e in events)
    assert "запускаю" not in reply
    assert "профиль" in reply


class FailingGenPlannerService:
    """GenPlannerService stand-in whose generation always fails the given way."""

    def __init__(self, error):
        self._error = error
        self.calls: list[Any] = []

    async def run_custom_func_generation(self, params):
        self.calls.append(params)
        raise self._error


@pytest.mark.parametrize(
    "error, expected_event",
    [
        (HTTPException(status_code=400, detail={"msg": "территория пустая"}), "warning"),
        (RuntimeError("core panicked"), "error"),
    ],
)
@pytest.mark.asyncio
async def test_failed_generation_replaces_the_models_success_text(error, expected_event):
    """A failure event plus the model's "запускаю" would read as success to the user."""

    genplanner_service = FailingGenPlannerService(error)
    llm = FakeChatClient([{"action": "run_generation", "patch": {"profile": "жилая"}, "reply": "Генерация запущена!"}])

    events = await _collect(
        stream_custom_chat_turn(
            llm_client=llm,
            chat_storage_client=FakeChatStorageClient(),
            genplanner_service=genplanner_service,
            user_id="00000000-0000-0000-0000-000000000001",
            territory=_TERRITORY_A,
            params=ChatCustomTurnDTO(user_query="жилая, запускай", chat_id=None),
        )
    )

    reply = "".join(e["content"] for e in events if e["type"] == "token")
    assert genplanner_service.calls, "generation should have been attempted"
    assert any(e["type"] == expected_event and e["stage"] == "run_generation" for e in events)
    assert not any(e["type"] == "result" for e in events)
    assert "Генерация запущена!" not in reply
    assert "ошибк" in reply.lower() or "не запустилась" in reply.lower()
