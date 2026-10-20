import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.service_reports import file_part, report_text, store_report, stored_report_response


class MemoryStorage:
    def __init__(self):
        self.objects = {}

    def put_json(self, payload, key):
        self.objects[key] = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def exists(self, key):
        return key in self.objects

    def open_stream(self, key):
        yield self.objects[key]


def test_report_can_be_opened_and_downloaded_after_chat_ends():
    storage = MemoryStorage()

    async def collect():
        return [
            event
            async for event in store_report(
                storage,
                "test",
                "",
                "Отчёт",
                "Полный ответ ассистента.",
                {"summary": {"buildings": 7}, "norms": [{"requirement": "Полный текст нормы " * 100}]},
            )
        ]

    events = asyncio.run(collect())
    report = events[0]
    saved = file_part(report)
    assert saved["role"] == "report"
    assert saved["mime_type"] == "text/plain"
    assert saved["download_url"] == saved["url"] + "?download=true"
    assert "type" not in saved
    app = FastAPI()

    @app.get("/reports/{result_id}")
    def report_endpoint(result_id: str, download: bool = False):
        return stored_report_response(storage, result_id, download)

    client = TestClient(app)
    opened = client.get(saved["url"])
    downloaded = client.get(saved["download_url"])
    assert opened.status_code == downloaded.status_code == 200
    assert opened.content == downloaded.content
    assert "Полный ответ ассистента." in opened.text
    assert "Количество зданий: 7" in opened.text
    assert ("Полный текст нормы " * 100).rstrip() in opened.text
    assert opened.headers["content-type"] == "text/plain; charset=utf-8"
    assert opened.headers["content-disposition"].startswith("inline;")
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert client.get("/reports/" + "a" * 32).status_code == 404
    assert client.get("/reports/invalid").status_code == 404


def test_report_falls_back_to_the_entire_answer():
    answer = "Весь ответ.\nВторая строка."
    assert report_text("Отчёт", answer) == "Отчёт\n\n" + answer + "\n"


@pytest.mark.parametrize("storage", [None, "broken"])
def test_storage_failure_emits_warning_without_a_broken_file_link(storage):
    class BrokenStorage:
        def put_json(self, *_args):
            raise OSError("internal-storage-secret")

    async def collect():
        return [
            event async for event in store_report(BrokenStorage() if storage else None, "test", "", "Отчёт", "Ответ")
        ]

    events = asyncio.run(collect())
    assert [event["type"] for event in events] == ["warning"]
    assert events[0]["stage"] == "store_report"
    assert "internal-storage-secret" not in str(events)
