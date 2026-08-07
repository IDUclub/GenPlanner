# GenPlanner MCP — гайд для внешних агентов

Это описание отдельного MCP-сервера (`app/mcp_server`), который отдаёт функциональность
GenPlanner сторонним LLM-агентам (Claude Desktop, другие MCP-клиенты вне этого продукта).
**Не для фронтенда и не для чат-виджета этого продукта** — тот ходит в `GenPlannerService`
напрямую, в обход MCP; см. `docs/frontend_integration_guide.md`, если нужен REST/SSE.

## Подключение

- Транспорт: `streamable-http` (`fastmcp`/`mcp` Python SDK, либо любой MCP-клиент с
  поддержкой HTTP-транспорта).
- Endpoint: `<base_url>/mcp`.
- Прод: `http://10.32.1.102:8766/mcp`.
- Локально (`docker compose up` из этого репо, сервис `mcp`): `http://localhost:8766/mcp`.
- `GET <base_url>/health` → `{"status": "ok"}` — без авторизации, годится для liveness-проверки
  до подключения по MCP-протоколу.

Пример подключения (`fastmcp` Python-клиент):

```python
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://10.32.1.102:8766/mcp", auth="<bearer-token>") as client:
        tools = await client.list_tools()
        result = await client.call_tool("list_zone_types", {})
        print(result.data)

asyncio.run(main())
```

## Авторизация

MCP-сессия (`app/mcp_server/auth.py`, `AnyTokenVerifier`) требует **непустой**
`Authorization: Bearer <token>` для **любого** вызова тула — но сам MCP-сервер его не
валидирует (не проверяет подпись/срок действия/scope), только факт, что он не пустой.
Реальная проверка токена происходит ниже по цепочке, в Urban API, и только для тех тулов,
которые реально его туда пробрасывают.

Из пяти тулов реальный Keycloak-токен нужен только для `run_func_generation` — он
пробрасывает `Authorization` в `POST /genplanner/run_func_generation`, который сам GenPlanner
API защищает через `verify_bearer_token`. Остальные четыре тула (`list_available_zones`,
`list_zone_types`, `get_func_zone_ratio`, `get_default_forbidden_matrix`) ходят в REST-ручки,
которые вообще не требуют авторизации на стороне GenPlanner API (`zones_list`,
`zones_reference`, `default/func_ratio`, `default_matrix`) — для них MCP-сессии достаточно
любой непустой строки в `auth` (токен не обязан быть настоящим, валидным или даже похожим на
JWT). Проверено вживую на проде: `auth="dummy-smoke-test-token"` — все четыре тула отработали
и вернули настоящие данные, пятый (`run_func_generation`) с таким токеном упадёт на стороне
Urban API.

## Тулы

### `list_available_zones() -> list[int]`
Голые id доступных территориальных зон, без расшифровки. Пример ответа:
`[8, 1, 4, 7, 2, 6, 5, 3, 10, 11, 12, 13]`.

### `list_zone_types() -> list[{id, kind, name, profile}]`
То же самое, но с расшифровкой — используйте, если нужно смаппить человеческое слово
("жильё") на id. Пример элемента:
```json
{"id": 1, "kind": "residential", "name": "жилая", "profile": "residential territory"}
```
id 10–13 — подпрофили жилой (`kind` тот же, `id` разные). Никогда не изобретайте id
самостоятельно — только из этого списка.

### `get_func_zone_ratio(zone_id: int) -> dict[str, float]`
Дефолтное распределение функциональных зон для одного из "профилей" из
`list_available_zones`. Пример: `get_func_zone_ratio(1)` →
`{"1": 0.56, "7": 0.11, "2": 0.11, "6": 0.11, "5": 0.06, "3": 0.06}`.

### `get_default_forbidden_matrix() -> {"forbidden_pairs": [[int, int], ...]}`
Дефолтные запрещённые пары соседства (используются, если `run_func_generation` вызван без
`neighbour_pairs`/`forbidden_pairs`/`ignore_default_relations`). Это **мягкое** ограничение
внутри генератора, не жёсткий запрет — см. пояснение в `docs/frontend_integration_guide.md`
(раздел про `neighbour_pairs`/`forbidden_pairs`), та же семантика действует и через MCP.

### `run_func_generation(...) -> {"zones": FeatureCollection, "roads": FeatureCollection}`
Запускает генерацию и возвращает тот же формат, что и `POST /genplanner/run_func_generation`
в REST (см. `GenPlannerResultSchema` в основном гайде).

Параметры:

| параметр | тип | обязательный | описание |
|---|---|---|---|
| `project_id` | int | да | |
| `scenario_id` | int | да | |
| `territory_balance` | `dict[int, float]` | да | id зоны → доля площади, id только из `list_available_zones`/`list_zone_types` |
| `neighbour_pairs` | `list[[int, int]]` | нет | пары id, поощряемые к соседству |
| `forbidden_pairs` | `list[[int, int]]` | нет | пары id, отговариваемые от соседства (мягко) |
| `min_block_area` | `dict[int, float]` | нет | переопределение мин. площади квартала по зоне |
| `elevation_angle` | int (0–90) | нет | обрезка по уклону рельефа |
| `roads_extend_distance` | float | нет | |
| `functional_zones` | объект | нет | режим доработки существующих зон, см. ниже |
| `ignore_default_relations` | bool | нет, default `false` | `true` — не применять дефолтную матрицу запретов |
| `test` | bool | нет, default `false` | тестовая БД вместо боевой |

`functional_zones` (опционально, режим доработки вместо генерации с нуля):
```json
{"year": 2025, "source": "User", "fixed_functional_zones_ids": [1619712]}
```
- `source`: `"PZZ" | "OSM" | "User"`.
- `year`/`source` обязаны приходить из реального контекста вызывающего (сессии/проекта),
  никогда не угадывайте — неверная пара молча сгенерирует поверх другого слоя зонирования.
- `fixed_functional_zones_ids` — опционально, какие существующие зоны оставить как есть.

Требует настоящий валидный Keycloak Bearer (см. "Авторизация" выше) — иначе упадёт на
`verify_bearer_token` в самом GenPlanner API, а не в MCP-слое.

## Ошибки

Если нижестоящий GenPlanner API вернул не-2xx, MCP-тул кидает `ToolError` с телом ответа
REST-эндпоинта как текстом (тот же `{msg, input, detail}`, что и в `422` у REST —
см. `app/mcp_server/tools/genplanner_tools.py:_call` / `app/mcp_server/api_client.py`).
Отдельного структурированного формата ошибки на уровне MCP нет — весь объект приходит как
строка внутри `ToolError`.

## Таймауты

Внутренний HTTP-клиент MCP→GenPlanner API (`GenPlannerApiClient`) использует
`MCP_UPSTREAM_TIMEOUT_SECONDS` (env, default 300s). `run_func_generation` — не sub-second
операция (см. "Тайминги" в `docs/frontend_integration_guide.md`), закладывайте это же время
ожидания в MCP-клиенте.
