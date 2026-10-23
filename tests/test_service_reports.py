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
    assert "| Количество зданий | 7 |" in opened.text
    assert ("Полный текст нормы " * 100).rstrip() in opened.text
    assert opened.headers["content-type"] == "text/plain; charset=utf-8"
    assert opened.headers["content-disposition"].startswith("inline;")
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert "filename*=UTF-8''%D0%9E" in downloaded.headers["content-disposition"]
    assert client.get("/reports/" + "a" * 32).status_code == 404
    assert client.get("/reports/invalid").status_code == 404


def test_report_falls_back_to_the_entire_answer():
    answer = "Весь ответ.\nВторая строка."
    assert report_text("Отчёт", answer) == "# Отчёт\n\n## Результат работы\n\n" + answer + "\n"


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


def test_report_has_russian_fields_zones_statuses_and_sections():
    import re

    details = {
        "task_external_id": "hidden-task-id",
        "mode": "pzz_check",
        "group_by": "object",
        "summary": {
            "in_correct_zone": 1,
            "in_wrong_zone": 1,
            "unclear": 1,
            "buildings_by_zone": {"residential": 2, "business": 1},
            "targets_source": "service_defaults",
            "regulations": {"source": "normgraph"},
            "classes": {"A*": {"zones": 1, "ha": 12.5}},
            "norms": [
                {
                    "document": "СП 1",
                    "clause": "2.1",
                    "strictness": "strict",
                    "status": "not_applied",
                    "requirement": "Проверить расстояние.",
                    "note": "Данные отсутствуют",
                }
            ],
        },
        "objects": [
            {"feature_index": 0, "fit": "correct", "vri_text": "Жилой дом"},
            {
                "feature_index": 1,
                "fit": "wrong",
                "matched_vri_name": "Производство",
                "reason": "Недопустимый вид использования",
            },
            {"feature_index": 2, "fit": "unclear", "verdict": "Нет описания зоны", "is_in_correct_zone": False},
        ],
        "parameters": {"density_scenario": "mean", "default_floor_group": "high"},
        "warnings": [],
    }
    text = report_text("Отчёт", "Проверка завершена.", details)
    assert text.startswith("# Отчёт\n")
    assert "## Сводка" in text
    assert "## Не соответствуют ПЗЗ" in text
    assert "## Соответствуют ПЗЗ" in text
    assert "## Требуют ручной проверки" in text
    assert "| Соответствуют ПЗЗ | 1 |" in text
    assert "Жилая зона" in text
    assert "Жилой дом" in text and "Производство" in text
    assert "Нет описания зоны" in text
    assert "не применена" in text and "Данные отсутствуют" in text
    assert "12,5" in text
    assert not re.search(r"[A-Za-z]", text)


def test_report_escapes_table_cells_and_keeps_unknown_values(caplog):
    text = report_text("Отчёт", "Ответ", {"summary": {"future_metric": 987, "name": "Зона | номер\nодин"}})
    assert "Дополнительный показатель" in text and "987" in text
    assert "future_metric" not in text
    assert "future_metric" in caplog.text
    assert r"Зона \| номер; один" in text


def test_classification_does_not_claim_pzz_compliance():
    text = report_text(
        "Отчёт",
        "Классификация завершена",
        {"objects": [{"feature_index": 0, "fit": "matched", "matched_vri": "Жилая застройка"}]},
    )
    assert "## Подобраны виды использования" in text
    assert "## Соответствуют ПЗЗ" not in text


def test_localization_preserves_numbers_and_source_codes():
    text = report_text(
        "Отчёт",
        "Ответ",
        {
            "summary": {
                "living_area_total": 1234567.89,
                "zone_type_id": "A",
                "vri_code": "6.0",
                "document": "ГОСТ A-1",
                "clause": "B",
                "feature_index": 2,
            }
        },
    )
    assert "1234567,89" in text
    assert "| Код зоны | A |" in text
    assert "| Код ВРИ | 6.0 |" in text
    assert "ГОСТ A-1" in text and "| Пункт | B |" in text
    assert "| Индекс объекта в исходных данных | 2 |" in text
