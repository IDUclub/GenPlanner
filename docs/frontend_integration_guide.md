# GenPlanner — гайд для фронтенда

Все эндпоинты живут под префиксом `/genplanner` (см. `app/main.py`). Ниже — только
`gen_planner`-роутер (`app/gen_planner/gen_planner_controller.py`).

## Аутентификация

`run_func_generation`, `run_func_generation/only_zones` и `cut_polygons` требуют
`Authorization: Bearer <keycloak access token>` (обычный пользовательский токен, тот же,
что и для Urban API). Без него — `401`.

`zones_list`, `zones_reference`, `default/func_ratio`, `default_matrix` — без авторизации,
их можно дергать сразу при загрузке формы для справочников.

## 1. Справочники — дёргать до формы генерации

### `GET /genplanner/gen_planner/zones_list` → `list[int]`
Список id функциональных зон-профилей (используются в `default/func_ratio`, не в
`territory_balance` напрямую).

### `GET /genplanner/gen_planner/zones_reference` → `list[AvailableZoneSchema]`
Главный справочник для UI: какие id зон вообще можно использовать в `territory_balance` /
`neighbour_pairs` / `forbidden_pairs`.

```json
[
  {"id": 1, "kind": "residential", "name": "жилая", "profile": null},
  {"id": 2, "kind": "recreation", "name": "рекреационная", "profile": null},
  {"id": 3, "kind": "special", "name": "специального назначения", "profile": null},
  {"id": 4, "kind": "industrial", "name": "промышленная", "profile": null},
  {"id": 5, "kind": "agriculture", "name": "сельскохозяйственная", "profile": null},
  {"id": 6, "kind": "transport", "name": "транспортная", "profile": null},
  {"id": 7, "kind": "business", "name": "деловая", "profile": null},
  {"id": 10, "kind": "residential", "name": "...", "profile": "..."}
]
```
id 10–13 — это подпрофили жилой (`kind: residential`), у них у всех одинаковый `kind`, но
разные `id` — если в UI нужно единое "жильё", группируйте по `kind`, а не по `name`.

**Важно:** бэкенд не валидирует id зон в `territory_balance` / `neighbour_pairs` /
`forbidden_pairs` явной 422-ошибкой — неизвестный id молча выбрасывается из расчёта
(в худшем случае — с непонятной ошибкой из недр генератора, если выброшены все id).
Присылайте только id из этого справочника.

### `GET /genplanner/default_matrix` → `{"forbidden_pairs": [[int, int], ...]}`
Дефолтные запрещённые пары **по умолчанию** (используются, если не передавать
`neighbour_pairs`/`forbidden_pairs`/`ignore_default_relations` вовсе). Полезно показать в UI
как preset ("стандартные ограничения соседства"), который пользователь может донастроить.

### `GET /genplanner/default/func_ratio?zone=<id>` → `dict[str, float]`
Дефолтное распределение зон для одного из "профилей" из `zones_list` (id из `zones_list`,
не из `zones_reference`) — годится как стартовое значение слайдеров `territory_balance`,
если пользователь выбрал готовый профиль, а не настраивает баланс вручную.

## 2. Генерация: `POST /genplanner/run_func_generation`

Тело запроса — `GenPlannerFuncZonesDTO` (`app/gen_planner/dto/gen_planner_func_dto.py`):

| поле | тип | обязательное | описание |
|---|---|---|---|
| `project_id` | int | да | |
| `scenario_id` | int | да | |
| `territory_balance` | `dict[int, float]` | да, ≥1 запись | id зоны → доля площади. Id только из `zones_reference` |
| `neighbour_pairs` | `list[[int, int]]` \| null | нет | пары id, которые нужно **поощрять** к соседству |
| `forbidden_pairs` | `list[[int, int]]` \| null | нет | пары id, которые нужно **отговаривать** от соседства |
| `ignore_default_relations` | bool | нет, default `false` | `true` — не применять дефолтные запреты (`default_matrix`), стартовать с чистой матрицы |
| `functional_zones` | объект \| null | нет | режим доработки (amendment) существующих зон, см. ниже |
| `fix_zones` | GeoJSON FeatureCollection \| null | нет | точки/геометрии с явно закреплённым типом зоны |
| `min_block_area` | `dict[int, float]` | нет | переопределение минимальной площади квартала по зоне |
| `elevation_angle` | int (0–90) \| null | нет | обрезка по уклону рельефа |
| `roads_extend_distance` | float \| null | нет, default `5` | |
| `test` | bool | нет, default `false` | тестовая БД вместо боевой |

### Про `neighbour_pairs` / `forbidden_pairs` — как это реально работает

Это **не жёсткое ограничение**, а штраф внутри оптимизатора генератора (подтверждено и
исходниками Rust-ядра, и живыми прогонами: 4 повтора baseline против 4 с
`forbidden_pairs=[[1,2]]` дали границу зон 23–192 м vs 0–2 м — эффект чёткий, но не
гарантированный ноль). Формулировки в UI должны быть аккуратными:

- Хорошо: "снизить вероятность соседства", "постараться развести зоны"
- Плохо: "гарантированно запретить соседство", "зоны никогда не будут рядом"

Обе зоны в паре обязаны присутствовать в `territory_balance` — иначе пара молча
игнорируется на бэкенде (см. предупреждение выше).

### Режим доработки существующих зон — `functional_zones`

```json
{
  "functional_zones": {
    "year": 2025,
    "source": "User",
    "fixed_functional_zones_ids": [1619712]
  }
}
```
- `source`: `"PZZ" | "OSM" | "User"` — откуда брать текущие функциональные зоны сценария.
- `year`: год снепшота.
- `fixed_functional_zones_ids`: опционально — конкретные существующие зоны, которые нужно
  оставить как есть (закрепить), а генератор доразмечает только оставшуюся территорию.
  Если не передавать — используется просто как контекст/база для доработки, без жёсткой
  фиксации конкретных зон.

Если `functional_zones` не передан — генерация "с нуля" по всей территории проекта/сценария.

### Ответ — `GenPlannerResultSchema`

```json
{
  "zones": { "type": "FeatureCollection", "features": [
    {"type": "Feature", "geometry": {...}, "properties": {
      "territory_zone": 1,
      "territory_zone_name": "residential",
      "functional_zone_id": null,
      "is_generated": true
    }}
  ]},
  "roads": { "type": "FeatureCollection", "features": [...] }
}
```
`is_generated: false` — это зона, пришедшая из `fix_zones`/`functional_zones` как есть, без
пересчёта геометрии; `functional_zone_id` заполнен только для таких "перенесённых" зон.

### `POST /genplanner/run_func_generation/only_zones`

Тот же DTO, но результат содержит только `functional_zone_id`/`is_generated` (без
`territory_zone_name`) — используйте, если UI не нужны подробности, только сами полигоны +
id. Более компактный ответ, тот же движок.

## 3. Тайминги, ретраи, недетерминизм — критично для UX

- **Не sub-second эндпоинт.** Реальная генерация — от ~60 секунд до нескольких минут
  (особенно если несколько генераций идут параллельно и делят CPU — на бэкенде это
  синхронный CPU-bound расчёт в потоке, не async I/O). UI обязан показывать
  progress/spinner с реалистичным ожиданием, не таймаутить запрос раньше 3-5 минут.
- **Бэкенд сам ретраит** до 3 раз при внутренних сбоях генератора (известны редкие
  паники в Rust-ядре на некоторых геометриях) — если после 3 попыток не получилось,
  клиенту прилетит ошибка; это стоит показывать как "не получилось сгенерировать,
  попробуйте ещё раз", а не как баг конкретно этого запроса.
- **Результат недетерминирован.** Один и тот же запрос с одинаковыми параметрами может
  дать разную планировку при каждом вызове (внутри генератора нет пробрасываемого seed —
  каждый вызов использует случайную инициализацию). Если в UI есть кнопка "перегенерировать"
  с теми же параметрами — это ожидаемо и полезно, а не признак бага.

## 4. Ошибки

Явно провалидированные случаи возвращают `422` с телом вида:
```json
{"msg": "...", "input": {...}, "detail": {...}}
```
Примеры: несуществующие `fixed_functional_zones_ids`, зафиксированные зоны не того типа,
fix-точки вне территории. Показывайте `msg`/`detail` пользователю как есть — там нет
внутренних деталей инфраструктуры.

Неожиданные внутренние ошибки сейчас возвращаются как обычный `500` без подробностей
(глобальный exception-handler в проекте временно отключён) — на такой случай в UI нужен
универсальный fallback "что-то пошло не так", без попытки распарсить `detail`.

## 5. MCP-сервер (для агентских/чат-сценариев, не для обычного UI)

Если фронтенд/продукт использует чат-агента или внешнего LLM-клиента (не прямой REST из
формы), тот же функционал доступен через MCP-сервер (`app/mcp_server`, порт `8766` по
умолчанию): `list_available_zones`, `list_zone_types`, `get_func_zone_ratio`,
`get_default_forbidden_matrix`, `run_func_generation`. Для обычного UI-фронтенда это не
нужно — используйте REST-эндпоинты выше напрямую.
