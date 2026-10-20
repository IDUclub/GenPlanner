"""Russian report presentation; stored schemas and API descriptors stay unchanged."""

import asyncio
import json
import logging
import re
from decimal import Decimal
from urllib.parse import quote
from uuid import uuid4

from fastapi import HTTPException
from fastapi.responses import Response

LOGGER = logging.getLogger(__name__)

LABELS = {
    "summary": "Сводка",
    "objects": "Объекты",
    "zones": "Зоны",
    "total": "Всего",
    "in_correct_zone": "Соответствуют ПЗЗ",
    "in_wrong_zone": "Не соответствуют ПЗЗ",
    "correct": "Соответствуют ПЗЗ",
    "wrong": "Не соответствуют ПЗЗ",
    "unclear": "Требуют ручной проверки",
    "fit": "Результат проверки",
    "verdict": "Статус",
    "reason": "Основание",
    "feature_index": "Индекс объекта в исходных данных",
    "vri_text": "Исходный вид использования",
    "zone_type_id": "Код зоны",
    "zone_code": "Код зоны",
    "zone_name": "Название зоны",
    "matched_vri_name": "Подобранный вид использования",
    "matched_vri_code": "Код подобранного ВРИ",
    "matched_vri": "Подобранный вид использования",
    "candidates": "Возможные виды использования",
    "resolution_basis": "Основание подбора вида использования",
    "category": "Категория объекта",
    "zones_count": "Количество типов территориальных зон",
    "zone_polygons_count": "Количество контуров зон",
    "not_in_zone": "Не пересекаются с зонами ПЗЗ",
    "by_verdict": "Распределение по статусам",
    "by_category": "Распределение по категориям",
    "with_candidate": "Вид использования подобран",
    "without_candidate": "Вид использования не подобран",
    "overlaps": "Наложения исходных слоёв",
    "parcel_overlaps": "Пересечения земельных участков",
    "parcels_with_overlaps": "Участки с наложениями",
    "parcels_in_multiple_zones": "Участки в нескольких зонах",
    "zone_overlaps": "Пересечения зон",
    "mo_overlaps": "Пересечения муниципальных образований",
    "parcels_in_multiple_mo": "Участки в нескольких муниципальных образованиях",
    "parcels_outside_mo": "Участки вне муниципальных образований",
    "zones_in_multiple_mo": "Зоны в нескольких муниципальных образованиях",
    "zones_outside_mo": "Зоны вне муниципальных образований",
    "pzz_summary": "Описание регламента зоны",
    "vri": "Вид разрешённого использования",
    "vri_code": "Код ВРИ",
    "vri_name": "Название ВРИ",
    "service_name": "Тип размещаемого объекта",
    "classes": "Пригодность территории",
    "zones_total": "Количество зон",
    "best_zones": "Наиболее подходящие зоны",
    "regulations": "Источник регламентов",
    "source": "Источник",
    "document": "Документ",
    "version": "Редакция",
    "code": "Код",
    "name": "Название",
    "limits": "Ограничения зоны",
    "szz_applied": "Санитарно-защитные зоны учтены",
    "szz_ha": "Площадь санитарно-защитных зон, га",
    "szz_by_class": "Санитарно-защитные зоны по классам опасности",
    "szz_default_class_parcels": "Участки с классом опасности по умолчанию",
    "hazard_class": "Класс опасности",
    "width_m": "Ширина санитарно-защитной зоны, м",
    "norms": "Нормативные ограничения",
    "requirement": "Требование",
    "clause": "Пункт",
    "reviewed": "Проверено экспертом",
    "status": "Статус",
    "note": "Примечание",
    "strictness": "Строгость требования",
    "ha": "Площадь, га",
    "notes": "Примечания",
    "reach_m": "Радиус доступности жилья, м",
    "reach_ha": "Площадь зоны доступности жилья, га",
    "reach_zones": "Зоны в пределах доступности жилья",
    "parcels": "Земельные участки",
    "cadastre_used": "Кадастровые данные использованы",
    "scenario_objects_used": "Объекты сценария использованы",
    "existing_objects_used": "Существующие объекты использованы",
    "existing_objects_count": "Количество существующих объектов",
    "existing_objects_source": "Источник существующих объектов",
    "used_default_mapping": "Использован типовой справочник ВРИ",
    "uncovered_zones": "Зоны без описания регламентов",
    "target": "Объекты выбранного типа",
    "production": "Производственные и складские объекты",
    "housing": "Жилые объекты",
    "other": "Прочие объекты",
    "buildings": "Количество зданий",
    "generated_buildings": "Сгенерировано зданий",
    "buildings_count": "Количество зданий",
    "living_area_total": "Жилая площадь, м²",
    "total_living_area": "Общая жилая площадь, м²",
    "residents_total": "Количество жителей",
    "total_residents": "Общее количество жителей",
    "residents": "Количество жителей",
    "residents_number": "Количество жителей",
    "living_area": "Жилая площадь, м²",
    "living_area_m2": "Жилая площадь, м²",
    "building_area_m2": "Площадь застройки, м²",
    "buildings_by_zone": "Здания по зонам",
    "residents_by_zone": "Расселение по зонам",
    "excluded_buildings": "Сохранено существующих объектов",
    "existing_living_area": "Существующая жилая площадь, м²",
    "existing_residents": "Жителей в существующей застройке",
    "existing_buildings_preserved": "Существующая застройка сохранена",
    "targets": "Целевые показатели и достижение",
    "target_residents": "Целевое количество жителей",
    "achieved_residents": "Размещено жителей",
    "residents_deficit": "Дефицит размещения жителей",
    "target_functional_area": "Целевая функциональная площадь, м²",
    "achieved_functional_area": "Полученная функциональная площадь, м²",
    "functional_area_deficit": "Дефицит функциональной площади, м²",
    "targets_source": "Источник целевых показателей",
    "actual": "Получено",
    "deficit": "Дефицит",
    "coverage_area": "Функциональная площадь, м²",
    "functional_area": "Функциональная площадь, м²",
    "floors_avg": "Средняя этажность",
    "floors": "Этажность",
    "density_scenario": "Плотность застройки",
    "default_floor_group": "Группа этажности по умолчанию",
    "la_per_person": "Жилая площадь на человека, м²",
    "service_normatives_loaded": "Нормативы обеспеченности загружены",
    "parameters": "Параметры",
    "scenario_id": "Номер сценария",
    "project_id": "Номер проекта",
    "profile_id": "Номер профиля",
    "profile": "Профиль зонирования",
    "profile_name": "Профиль зонирования",
    "territory_balance": "Баланс территориальных зон",
    "neighbour_pairs": "Соседствующие зоны",
    "forbidden_pairs": "Запрещённое соседство зон",
    "min_block_area": "Минимальные площади кварталов, м²",
    "elevation_angle": "Угол возвышения, градусы",
    "roads_extend_distance": "Расстояние продления дорог, м",
    "targets_overrides": "Переопределённые целевые показатели",
    "skip_generation": "Генерация зданий пропущена",
    "publish": "Сохранение результата в сценарий",
    "sirtep_periods": "Количество периодов строительства",
    "sirtep_max_area_per_period": "Максимальная площадь за период, м²",
    "sirtep_wait_provision": "Ожидание расчёта обеспеченности",
    "test": "Тестовый контур",
    "warnings": "Предупреждения",
    "events": "Результаты этапов",
    "published": "Публикация результата",
    "notified": "Расчёт оценок запущен",
    "notified_events": "Запущенные расчёты",
    "buildable": "Профиль допускает застройку",
    "indicator_id": "Номер показателя",
    "missing_indicator_ids": "Показатели без данных",
    "scoreboard": "Сравнение профилей",
    "raw": "Исходное значение",
    "normalized": "Нормированное значение",
    "schedule": "Очерёдность строительства",
    "provision": "Обеспеченность сервисами",
    "scores": "Оценки результата",
    "branch": "Способ расчёта",
    "period": "Период",
    "periods": "Периоды",
    "periods_planned": "Запланировано периодов",
    "periods_used": "Использовано периодов",
    "houses": "Жилые дома",
    "services": "Сервисы",
    "houses_total": "Построено жилых домов",
    "services_total": "Построено сервисов",
    "houses_area_m2": "Площадь жилых домов, м²",
    "services_area_m2": "Площадь сервисов, м²",
    "provided": "Обеспечено жителей",
    "provided_final": "Обеспечено жителей к концу строительства",
    "by_period": "Результаты по периодам",
    "comments": "Комментарии",
    "final_by_service": "Итоговые показатели обеспеченности",
    "unbuilt_services": "Сервисы с нулевой обеспеченностью",
    "arrived": "Получено оценок",
    "missing_ids": "Отсутствующие оценки",
    "items": "Показатели",
    "value": "Значение",
    "unit": "Единица измерения",
    "label": "Обозначение",
    "updated_at": "Дата обновления",
    "highlights": "Основные показатели",
    "sections": "Разделы показателей",
    "rows": "Показатели раздела",
    "title": "Название раздела",
    "max_floors": "Максимальная этажность",
    "min_floors": "Минимальная этажность",
    "max_height": "Максимальная высота, м",
    "min_area": "Минимальная площадь, м²",
    "max_area": "Максимальная площадь, м²",
    "max_density": "Максимальная плотность застройки",
    "max_building_percent": "Максимальный процент застройки",
}
VALUES = {
    "residential": "Жилая зона",
    "business": "Общественно-деловая зона",
    "industrial": "Промышленная зона",
    "transport": "Транспортная зона",
    "special": "Зона специального назначения",
    "recreation": "Рекреационная зона",
    "agriculture": "Сельскохозяйственная зона",
    "unknown": "Зона не определена",
    "correct": "соответствует ПЗЗ",
    "wrong": "не соответствует ПЗЗ",
    "unclear": "требует ручной проверки",
    "matched": "вид использования подобран",
    "applied": "применена",
    "not_applied": "не применена",
    "listed": "перечислена для ручной проверки",
    "strict": "строгое",
    "soft": "нестрогое",
    "unchecked": "автоматическая проверка не выполнена",
    "request": "запрос пользователя",
    "service_defaults": "настройки сервиса",
    "user": "данные пользователя",
    "default": "типовой справочник",
    "normgraph": "граф нормативных ограничений",
    "upload": "загруженный файл",
    "scenario": "сценарий",
    "cadastre": "кадастровые данные",
    "none": "отсутствует",
    "min": "минимальная",
    "mean": "средняя",
    "max": "максимальная",
    "private": "индивидуальная жилая застройка",
    "low": "малоэтажная застройка",
    "medium": "среднеэтажная застройка",
    "high": "многоэтажная застройка",
    "priority": "по приоритету",
    "simple": "упрощённый",
    "provision": "с учётом обеспеченности",
    "warning": "предупреждение",
    "error": "ошибка",
    "finished": "завершено",
    "failed": "завершено с ошибкой",
    "ready": "готово",
    "queued": "в очереди",
    "running": "выполняется",
    "allowed_main": "основной вид использования разрешён",
    "allowed_conditional": "вид использования условно разрешён",
    "allowed_auxiliary": "вспомогательный вид использования разрешён",
    "not_allowed": "вид использования не разрешён",
    "scenario_zones_updated": "расчёт по обновлённым зонам сценария",
    "scenario_objects_updated": "расчёт по обновлённым объектам сценария",
    "territory_indicators": "показатели территории",
    "profile_selected": "выбор профиля",
    "master_plan_summary": "итог комплексной планировки",
    "scenario_published": "сохранение сценария",
    "sirtep_schedule": "очерёдность строительства",
    "sirtep_provision": "обеспеченность сервисами",
    "result": "генерация застройки",
    "scores": "оценки результата",
    "buildplanner": "комплексная планировка",
    "genplanner": "генерация планировки",
    "genbuilder": "генерация застройки",
    "A": "Подходит: основной вид использования",
    "A*": "Подходит: объект этого типа уже есть",
    "B": "Подходит с ограничениями",
    "B*": "Подходит с ограничениями: объект этого типа уже есть",
    "C": "Не подходит",
    "D": "Описание зоны отсутствует",
}
# System identifiers are already retained by the task API / attachment metadata.
HIDDEN_FIELDS = {
    "geometry",
    "coordinates",
    "features",
    "chat_message",
    "task_external_id",
    "external_id",
    "mode",
    "subject",
    "group_by",
    "type",
    "stage",
    "group",
    "source_service",
    "url",
    "download_url",
    "is_in_correct_zone",
}
TEXT_WORDS = {key: value for key, value in VALUES.items() if len(key) > 2}
TEXT_WORDS.update({"normgraph": "граф нормативных ограничений", "buildplanner": "сервис комплексной планировки"})
WORD_PATTERN = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(key) for key in sorted(TEXT_WORDS, key=len, reverse=True)) + r")(?![\w-])",
    re.IGNORECASE,
)


def localize_text(value):
    """Translate system vocabulary while preserving source names, codes and requirements."""
    return WORD_PATTERN.sub(lambda match: TEXT_WORDS[match.group().lower()], str(value))


def field_label(key):
    text = str(key)
    if text in LABELS:
        return LABELS[text]
    if text in VALUES:
        return VALUES[text]
    if re.search(r"[А-Яа-яЁё]", text) or text.isdigit():
        return text.replace("_", " ")
    LOGGER.warning("Unlabelled report field: %s", text)
    return "Дополнительный показатель"


def number_text(value):
    decimal = Decimal(str(value))
    if not decimal.is_finite():
        return "нет данных"
    number = format(decimal, "f")
    return (number.rstrip("0").rstrip(".") if "." in number else number).replace(".", ",")


def display(value, key=None):
    if value is None or value == "":
        return "нет данных"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, float):
        return number_text(value)
    if key in {"code", "zone_type_id", "zone_code", "vri_code", "matched_vri_code", "document", "clause"}:
        return str(value)
    if str(value) in VALUES and str(value) not in {"A", "A*", "B", "B*", "C", "D"}:
        return VALUES[str(value)]
    return localize_text(value)


def table_cell(value):
    return str(value).replace("|", r"\|").replace("\n", "; ")


def heading(title, depth):
    return "#" * min(depth + 3, 6) + " " + title


def render_details(value, depth=0):
    """Markdown in a UTF-8 TXT file, compatible with a plain or formatted viewer."""
    if isinstance(value, dict):
        return render_mapping(value, depth)
    if isinstance(value, (list, tuple)):
        return render_items(value, depth)
    return [display(value)]


def render_mapping(value, depth):
    visible = [(key, item) for key, item in value.items() if key not in HIDDEN_FIELDS]
    scalars = [(key, item) for key, item in visible if not isinstance(item, (dict, list, tuple))]
    lines = []
    if scalars:
        lines = ["| Показатель | Значение |", "| --- | --- |"]
        lines += [f"| {table_cell(field_label(key))} | {table_cell(display(item, key))} |" for key, item in scalars]
    for key, item in visible:
        if isinstance(item, (dict, list, tuple)):
            lines += ["", heading(field_label(key), depth), "", *render_details(item, depth + 1)]
    return lines or ["_Нет._"]


def render_items(value, depth):
    if not value:
        return ["_Нет._"]
    lines = []
    for index, item in enumerate(value, 1):
        if isinstance(item, dict):
            number = item.get("feature_index")
            title = f"Объект {number + 1}" if isinstance(number, int) else f"{index}."
            if item.get("document"):
                title = f"{index}. {item['document']}"
                if item.get("clause"):
                    title += f", п. {item['clause']}"
            lines += [heading(title, depth), "", *render_details(item, depth + 1), ""]
        elif isinstance(item, (list, tuple)):
            lines.append("- " + " — ".join(display(part) for part in item))
        else:
            lines.append("- " + display(item))
    return lines


def object_sections(objects):
    known = {"wrong", "correct", "matched", "unclear"}
    groups = [
        ("wrong", "Не соответствуют ПЗЗ"),
        ("correct", "Соответствуют ПЗЗ"),
        ("matched", "Подобраны виды использования"),
        ("unclear", "Требуют ручной проверки"),
        (None, "Результаты по объектам"),
    ]
    lines = []
    for fit, title in groups:
        rows = [
            row
            for row in objects
            if isinstance(row, dict) and (row.get("fit") == fit if fit else row.get("fit") not in known)
        ]
        if rows:
            lines += ["", "## " + title, "", *render_items(rows, 0)]
    return lines or ["", "## Результаты по объектам", "", "_Нет._"]


def report_text(title, answer, details=None):
    lines = ["# " + localize_text(title), "", "## Результат работы", "", localize_text(answer).strip()]
    for key, value in (details or {}).items():
        if key in HIDDEN_FIELDS:
            continue
        if key == "objects" and isinstance(value, list):
            lines += object_sections(value)
        else:
            lines += ["", "## " + field_label(key), "", *render_details(value)]
    return "\n".join(lines).rstrip() + "\n"


def descriptor(service, base_path, result_id, title):
    url = f"{base_path}/reports/{result_id}"
    return {
        "name": "report",
        "title": title,
        "role": "report",
        "url": url,
        "download_url": f"{url}?download=true",
        "filename": "Отчёт.txt",
        "mime_type": "text/plain",
        "source_service": service,
    }


def file_part(report):
    return {key: value for key, value in report.items() if key != "type"}


def report_key(result_id):
    if re.fullmatch(r"[0-9a-f]{32}", result_id) is None:
        raise HTTPException(404, "Отчёт не найден")
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
        headers={
            "Content-Disposition": f'{disposition}; filename="report.txt"; filename*=UTF-8\'\'{quote("Отчёт.txt")}',
            "X-Content-Type-Options": "nosniff",
        },
    )


def stored_report_response(storage, result_id, download=False):
    key = report_key(result_id)
    if storage is None:
        raise HTTPException(503, "Хранилище отчётов недоступно")
    try:
        if not storage.exists(key):
            raise HTTPException(404, "Отчёт не найден")
        payload = json.loads(b"".join(storage.open_stream(key)))
        return text_response(payload["text"], download)
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise HTTPException(502, "Хранилище отчётов недоступно") from exc
