"""Durable text reports shared in shape by independently deployed services."""

import asyncio
import json
import re
from uuid import uuid4

from fastapi import HTTPException
from fastapi.responses import Response

LABELS = {
    "buildings": "Количество зданий",
    "living_area_total": "Жилая площадь, м²",
    "residents_total": "Количество жителей",
    "buildings_by_zone": "Здания по зонам",
    "target_residents": "Целевое количество жителей",
    "achieved_residents": "Размещено жителей",
    "residents_deficit": "Дефицит размещения жителей",
    "target_functional_area": "Целевая функциональная площадь, м²",
    "achieved_functional_area": "Полученная функциональная площадь, м²",
    "functional_area_deficit": "Дефицит функциональной площади, м²",
    "territory_balance": "Баланс зон",
    "neighbour_pairs": "Соседство зон",
    "forbidden_pairs": "Запрещённое соседство",
    "min_block_area": "Минимальные площади кварталов",
    "targets_source": "Источник целевых показателей",
    "existing_buildings_preserved": "Существующая застройка сохранена",
    "service_normatives_loaded": "Нормативы обеспеченности загружены",
    "summary": "Сводка",
    "objects": "Объекты",
    "zones": "Зоны",
    "total": "Всего",
    "correct": "Соответствуют ПЗЗ",
    "wrong": "Не соответствуют ПЗЗ",
    "unclear": "Требуют ручной проверки",
    "fit": "Результат проверки",
    "feature_index": "Индекс объекта",
    "reason": "Основание",
    "name": "Название",
    "norms": "Нормативные ограничения",
    "requirement": "Требование",
    "document": "Документ",
    "clause": "Пункт",
    "status": "Статус",
    "note": "Примечание",
    "strictness": "Строгость",
    "ha": "Площадь, га",
    "generated_buildings": "Сгенерировано зданий",
    "buildings_count": "Количество зданий",
    "total_living_area": "Жилая площадь, м²",
    "total_residents": "Количество жителей",
    "residents_number": "Количество жителей",
    "living_area": "Жилая площадь, м²",
    "excluded_buildings": "Сохранено существующих объектов",
    "existing_living_area": "Существующая жилая площадь, м²",
    "existing_residents": "Жителей в существующей застройке",
    "residents_by_zone": "Расселение по зонам",
    "targets": "Целевые показатели и достижение",
    "target": "Цель",
    "actual": "Получено",
    "deficit": "Дефицит",
    "parameters": "Параметры",
    "scenario_id": "Сценарий",
    "project_id": "Проект",
    "warnings": "Предупреждения",
    "events": "Результаты этапов",
    "zone_code": "Код зоны",
    "zone_name": "Название зоны",
    "vri": "ВРИ",
    "regulations": "Источник регламентов",
    "source": "Источник",
}
VALUES = {
    "correct": "соответствует",
    "wrong": "не соответствует",
    "unclear": "ручная проверка",
    "applied": "применена",
    "not_applied": "не применена",
    "listed": "перечислена",
    "strict": "строгая",
    "soft": "нестрогая",
    "unchecked": "не проверена автоматически",
}


def render_details(value, depth=0):
    """Keep all report rows and requirements; never dump map geometry."""
    indent = "  " * depth
    lines = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"geometry", "coordinates", "features", "chat_message"}:
                continue
            label = LABELS.get(key, key)
            if isinstance(item, (dict, list)):
                lines.append(f"{indent}{label}:")
                lines.extend(render_details(item, depth + 1))
            else:
                lines.append(f"{indent}{label}: {display(item)}")
    elif isinstance(value, list):
        for index, item in enumerate(value, 1):
            lines.append(f"{indent}{index}.")
            lines.extend(render_details(item, depth + 1))
    else:
        lines.append(f"{indent}{display(value)}")
    return lines


def display(value):
    if value is None:
        return "нет данных"
    if isinstance(value, bool):
        return "да" if value else "нет"
    return VALUES.get(str(value), str(value))


def report_text(title, answer, details=None):
    sections = [title, "", answer.strip()]
    if details:
        sections.extend(["", "Подробные результаты", "", *render_details(details)])
    return "\n".join(sections).rstrip() + "\n"


def descriptor(service, base_path, result_id, title):
    url = f"{base_path}/reports/{result_id}"
    return {
        "name": "report",
        "title": title,
        "role": "report",
        "url": url,
        "download_url": f"{url}?download=true",
        "filename": "report.txt",
        "mime_type": "text/plain",
        "source_service": service,
    }


def file_part(report):
    return {key: value for key, value in report.items() if key != "type"}


def report_key(result_id):
    if re.fullmatch(r"[0-9a-f]{32}", result_id) is None:
        raise HTTPException(404, "Report not found")
    return f"reports/{result_id}.json"


async def store_report(storage, service, base_path, title, answer, details=None):
    """Emit a file only after storage succeeds, independently of chat persistence."""
    if storage is None:
        yield {"type": "warning", "stage": "store_report", "message": "Отчёт не сохранён: хранилище недоступно."}
        return
    result_id = uuid4().hex
    try:
        await asyncio.to_thread(storage.put_json, {"text": report_text(title, answer, details)}, report_key(result_id))
    except Exception:  # pylint: disable=broad-exception-caught
        yield {"type": "warning", "stage": "store_report", "message": "Не удалось сохранить файл отчёта."}
        return
    yield {"type": "file", **descriptor(service, base_path, result_id, title)}


def text_response(text, download=False):
    disposition = "attachment" if download else "inline"
    return Response(
        text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'{disposition}; filename="report.txt"', "X-Content-Type-Options": "nosniff"},
    )


def stored_report_response(storage, result_id, download=False):
    key = report_key(result_id)
    if storage is None:
        raise HTTPException(503, "Report storage unavailable")
    try:
        if not storage.exists(key):
            raise HTTPException(404, "Report not found")
        payload = json.loads(b"".join(storage.open_stream(key)))
        return text_response(payload["text"], download)
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise HTTPException(502, "Report storage unavailable") from exc
