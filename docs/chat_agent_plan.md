# Чат-интеграция для GenPlanner: агентная логика + MCP + история чата

> Статус: Фаза 0, Фаза 1, Фаза 2 — сделаны и запушены в `feat/agents_feature`
> (коммиты `5ff0bb0`, `be5ea8c`, `564ccff`, `c581bca`). Дальше — Фаза 3 (MCP-сервер)
> и Фаза 4 (docker-compose).

## Контекст

GenPlanner API сейчас работает только как classic REST: клиент сам собирает `GenPlannerFuncZonesDTO`
(территориальный баланс, соседство зон и т.д.) и шлёт его на `POST /genplanner/run_func_generation`.
Цель — дать пользователю задавать эти параметры диалогом на естественном языке, а также открыть
GenPlanner для внешних AI-агентов через MCP. Это делается по образцу уже работающего в экосистеме
IDU сервиса **PzzCompareAPI** (github.com/IDUclub/PzzCompareAPI), который уже имеет:
history чата во внешнем **ChatStorage** (Keycloak service-token), стриминг ответов LLM через **Ollama**,
и отдельный **MCP-сервер** для агентов.

Какие именно параметры чат вообще может задавать — уже зафиксировано в отдельном артефакте
(diagram, опубликован ранее в переписке) по трём уровням:
- **напрямую**: `territory_balance`, `neighbour_pairs`, `forbidden_pairs`
- **чат + уточнение**: `min_block_area`, `elevation_angle`, `roads_extend_distance`
- **не в MVP**: `fix_zones`, `functional_zones.*` (нужна карта / генерация всегда «с нуля»)
- **контекст сессии, не из чата**: `project_id`, `scenario_id` (выбраны на фронте), `test`

Решения по инфраструктуре (согласованы с пользователем):
- генерация остаётся **синхронной** (`asyncio.to_thread` внутри хода агента) — Celery/Redis/task-очередь
  из PzzCompareAPI **не переносим**, это оверинжиниринг для быстрого Rust-ядра;
- история чата хранится в **общем ChatStorage** платформы (тот же сервис, что у PzzCompareAPI) через
  Keycloak service-token — не поднимаем свою БД;
- LLM — **Ollama** (внешний сервис уже поднят), тот же паттерн, что в PzzCompareAPI.

## Архитектура (компоненты)

```
                    ┌─ POST /genplanner/scenarios/{id}/chat/stream (SSE, Bearer) ─┐
                    │        app/chat/chat_controller.py                          │
                    ▼                                                             │
            app/chat/chat_service.py  ── агентный цикл (см. ниже) ────────────────┘
                    │                                    │
     OllamaChatClient.complete_json           GenPlannerService.run_func_generation
     (структурированное решение хода)          (тот же вызов, что и обычный REST)
                    │
          ChatStorageClient (история + draft в metadata сообщений)
                    │
          Keycloak service-token (idu-service-auth, client_credentials)

Отдельный процесс:
  app/mcp_server/  (FastMCP, свой порт) ── тонкий HTTP-клиент к самому GenPlanner API ──▶ те же REST-эндпоинты
  (нужен для ВНЕШНИХ агентов — не для нашего бота, который зовёт GenPlannerService напрямую in-process)
```

## Agentic-цикл одного хода чата

На каждый `user_query` в рамках `chat_id`:

1. Подтянуть историю + последний сохранённый `draft` (JSON: `territory_balance`, `neighbour_pairs`,
   `forbidden_pairs`, `min_block_area`, `elevation_angle`, `roads_extend_distance`) из ChatStorage —
   он лежит в `metadata` последнего ассистентского сообщения (своя БД не нужна).
2. Один вызов `OllamaChatClient.complete_json(...)` со схемой:
   ```json
   {"action": "update_draft | ask_clarifying_question | run_generation | list_zones | chat",
    "patch": {...частичные поля DTO...}, "reply": "текст пользователю"}
   ```
   Системный промпт описывает DTO-поля, актуальные id зон (`scenario_func_zones_map`/`default_terr_zones_map`)
   и текущий `draft`. Это ЕДИНСТВЕННЫЙ вызов LLM за ход (дешевле, чем decision+reply как в PzzCompareAPI) —
   `reply` уже готовый текст, стримится пользователю нарезкой на чанки (без второго обращения к модели).
3. Python-код (не LLM) исполняет действие:
   - `update_draft` — мёржит `patch` в draft;
   - `list_zones` — подтягивает `scenario_func_zones_map`/`default_terr_zones_map` в контекст (in-process,
     без HTTP);
   - `run_generation` — собирает `GenPlannerFuncZonesDTO(scenario_id=.., territory_balance=.., ...)`
     **напрямую как pydantic-объект** (валидаторы `assign_custom_ter_zone_name`/`validate_fixed_zones`
     отрабатывают как обычно) и зовёт `genplanner_service.run_func_generation(dto, token, config)` —
     тот же код, что и REST-эндпоинт, без похода через MCP.
4. Ошибки валидации (422 от `http_exception`, например неизвестный zone id) не роняют стрим — уходят как
   `warning`/`error` gMART-событие, чтобы модель на следующем ходу могла попросить пользователя уточнить.
5. Результат генерации (zones/roads GeoJSON) отдаётся отдельным событием `{"type": "result", ...}` **инлайн**
   в SSE-поток — в отличие от PzzCompareAPI, durable-ссылки через MinIO не делаем (нет очереди — незачем).
6. User-реплика и финальный ответ ассистента (+ `draft`, `action` в `metadata`) сохраняются в ChatStorage.

## Фаза 0 — блокирующий баг [СДЕЛАНО, коммит `be5ea8c`]

`gen_planner_service.py` (`_build_relation_matrix_arg`) читал `params.ignore_default_relations`,
которого не было в `GenPlannerFuncZonesDTO`. Это **не отложенный edge-case**:
`bool(None or None or params.ignore_default_relations)` кидал `AttributeError` для ЛЮБОГО запроса,
где не заданы ни `neighbour_pairs`, ни `forbidden_pairs` — а это самый частый чат-сценарий
(«хочу просто 50/30/20»). Добавлено поле в DTO; заодно поправлена сама логика
`_build_relation_matrix_arg` — раньше `ignore_default_relations=True` при наличии зон всё равно
засеивал матрицу дефолтными запрещёнными соседствами (`FORBIDDEN_NEIGHBORHOOD`), теряя смысл флага;
теперь при этом флаге матрица стартует пустой (`ZoneRelationMatrix.empty(zones)`), а явные
`neighbour_pairs`/`forbidden_pairs` по-прежнему накладываются поверх.

## Фаза 1 — общая инфраструктура [СДЕЛАНО, коммит `564ccff`]

Реализовано и проверено end-to-end (`init_dependencies` собирает всё, при пустом конфиге всё честно
`None` + warning в лог, при заполненном — реальные инстансы клиентов, `pylint` на новых файлах 10/10).

- **`app/common/llm/ollama_chat_client.py`** — `OllamaChatClient` (`stream_chat` + `complete_json` с
  JSON-схемой), на **aiohttp**, а не httpx — в этом репо уже есть `AsyncJsonApiHandler` на aiohttp
  (`app/common/api_handlers/json_api_handler.py`), вторую HTTP-библиотеку не добавляем.
- **`app/common/chat_storage/chat_storage_client.py`** — `ChatStorageClient` (create_chat/add_message/
  get_chat), тоже на aiohttp, заголовок `X-User-Id`.
- **`app/common/auth/service_token.py`** — Keycloak client_credentials токен для похода в ChatStorage,
  через пакет `idu-service-auth` (git-зависимость на github.com/IDUclub/idu-service-auth — не публиковался
  на приватный PyPI-мираж). API: `KeycloakTokenConfig(auth_server_url, realm, client_id, client_secret,
  scope=None, ...)` + `KeycloakTokenClient(config)` как async context manager, методы
  `get_access_token()` / `get_authorization_headers()`.
- **`app/common/auth/user_identity.py`** — извлечение `sub` (user_id) из пользовательского Bearer-токена
  без проверки подписи (как и `bearer.py` — он тоже ничего не валидирует, downstream это делает Urban
  API), через `python-jose`.
- **Конфиг** (`.env.development` + `iduconfig`): `OLLAMA_BASE_URL`, `GENERATE_MODEL`, `CHAT_MODEL`,
  `CHAT_TEMPERATURE`, `CHAT_REQUEST_TIMEOUT_SECONDS`, `CHAT_STORAGE_BASE_URL`, `CHAT_STORAGE_TIMEOUT_SECONDS`,
  `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_SCOPE`.
  Все опциональны — см. `app/common/config_utils.get_optional_config`.
- **Зависимости** (`pyproject.toml`): `fastmcp` (^3.3, потянул bump `uvicorn` 0.32→0.35), `sse-starlette`
  (^2.3), `python-jose[cryptography]`, `idu-service-auth` (git-зависимость). БЕЗ celery/redis/sqlalchemy/
  psycopg/minio/alembic — они в референсе нужны только для очереди задач и файлового стораджа, которые
  мы осознанно не переносим.

**Единственное реально неизвестное:** точные пути/формат тела запросов ChatStorage
(`create_chat`/`add_message`/`get_chat` в `chat_storage_client.py`) — реализовано по описанному
интерфейсу (`user_id`+`chat_id`, `X-User-Id` заголовок), но НЕ сверено с реальным OpenAPI самого
ChatStorage (нет его спеки/URL) — сверить и поправить пути при первом реальном подключении.

## Фаза 2 — чат-модуль (`app/chat/`) [СДЕЛАНО, коммит `c581bca`]

Новый feature-модуль, по структуре как `app/gen_planner/`:
- `chat_controller.py` — `POST /genplanner/scenarios/{scenario_id}/chat/stream`, Bearer обязателен
  (`verify_bearer_token`), `EventSourceResponse` из `sse_starlette`. Тело: `{"user_query": str,
  "chat_id": str | None, "test": bool = False}`.
- `dto/chat_dto.py` — DTO этого запроса.
- `chat_service.py` — оркестрация хода (шаги 1–6 выше).
- `agent/draft.py` — `GenerationDraft` (pydantic), merge-логика патчей.
- `agent/schema.py` — JSON-схема для `complete_json`.
- `agent/prompts.py` + `agent/data/chat_system_prompt.txt` — системный промпт (описание DTO-полей,
  тон ответов на русском, что нельзя спрашивать — `project_id`/`scenario_id`/`fix_zones`/`functional_zones`).

`project_id` резолвится через `_resolve_project_id()` (тот же lookup через `get_scenario_info`, что
и `restore_params`) перед конструированием DTO — не через `restore_params`, потому что `project_id`
обязательное pydantic-поле на `GenPlannerFuncZonesDTO`, и конструктор упадёт без него ещё до вызова
`restore_params`.

Прогнано end-to-end на фейках (Ollama/ChatStorage/GenPlannerService замоканы, без реальной сети) — все
три ветки агентного цикла отработали: `update_draft` + стриминг ответа кусками; `run_generation` с
пустым draft вежливо отказывается, не роняя стрим; `run_generation` с draft, подгруженным из истории
ChatStorage, реально резолвит `project_id`, строит `GenPlannerFuncZonesDTO` и вызывает
`run_func_generation`, отдаёт `result`-событие с zones/roads. `pylint` 10/10 на всём новом коде.

**Побочная находка** (не баг, задокументирована в CLAUDE.md): `restore_params`'s ветка "resolve
project_id if missing" на практике недостижима даже через обычный REST — FastAPI сам возвращает 422 на
отсутствующий `project_id` в query, раньше, чем код до `restore_params` доходит.

## Фаза 3 — MCP-сервер (`app/mcp_server/`) [НЕ СДЕЛАНО]

Отдельный процесс (свой порт, например 8766), по структуре как `service/mcp_server/` в PzzCompareAPI:
- `main.py` — `FastMCP("GenPlanner MCP")`, `/health`, `/` → `/mcp`.
- `api_client.py` — тонкий aiohttp-клиент к самому GenPlanner API (не к genplanner-сервису напрямую —
  через HTTP, как в референсе), с Bearer forwarding.
- `tools/genplanner_tools.py`:
  - `list_available_zones()` → `GET /genplanner/gen_planner/zones_list`
  - `get_func_zone_ratio(zone_id)` → `GET /genplanner/default/func_ratio`
  - `get_default_forbidden_matrix()` → `GET /genplanner/default_matrix`
  - `run_func_generation(scenario_id, territory_balance, neighbour_pairs?, forbidden_pairs?,
    min_block_area?, elevation_angle?, roads_extend_distance?)` → `POST /genplanner/run_func_generation`
  - Сознательно НЕ включаем `fix_zones`/`functional_zones`/`only_zones`-режим в тулы — они вне MVP
    по уже принятому решению.
- Ошибки — тот же payload, что уже возвращает `http_exception` (`{msg, input, detail}`), просто
  прокинутый как ошибка MCP-тула.

## Фаза 4 — деплой [НЕ СДЕЛАНО]

- `docker-compose.yml` — новый сервис `mcp` (тот же образ, другой `CMD`/`command`, порт 8766).
- `Dockerfile` — без изменений в сборке, только новая точка входа для MCP-процесса.
- `docker-compose.actions.yml` — по аналогии с `api`, если CI должен поднимать MCP отдельно.

## Верификация

- Ручной прогон разговора: «хочу 50% жильё, 30% бизнес, 20% рекреация» → `update_draft` → confirm →
  `run_generation` → событие `result` с zones/roads.
- Уточняющий вопрос: «не строй на крутых склонах» → ожидаем `ask_clarifying_question` про угол в градусах.
- Неизвестное название зоны → ответ должен явно сказать, что зона не распознана (не молча дропнуть,
  как сейчас происходит в `assign_custom_ter_zone_name`).
- Новая Postman-коллекция `postman/collections/GenPlanner Chat — SSE Stream/`, по образцу уже лежащей
  в репо `PzzCompareAPI — SSE Stream` (`.request.yaml` с `Accept: text/event-stream`).
- MCP — вызов `run_func_generation`-тула через MCP-инспектор или Claude Desktop с реальным Bearer-токеном.

## Открытые риски

- Точный пакет/интерфейс `idu-service-auth` — **уточнено**: github.com/IDUclub/idu-service-auth,
  пакет `idu_service_auth` (PEP 621, `name = "idu-service-auth"`, version 0.1.0, не публиковался на
  приватный PyPI-зеркало — ставить как git-зависимость: `idu-service-auth = {git =
  "https://github.com/IDUclub/idu-service-auth.git"}`). См. Фазу 1 — уже сделано и работает.
- Надёжность `complete_json` на конкретной Ollama-модели для строгого JSON — если модель мелкая,
  может потребоваться fallback на retry с более жёстким prompt или переход на decision+reply в два вызова
  (как в PzzCompareAPI), а не один.
- Большие территории → большой inline GeoJSON в SSE-событии `result`; если станет проблемой на практике —
  тогда и добавлять durable-ссылки (MinIO), не раньше.
- ChatStorage endpoint-paths (`chat_storage_client.py`) не сверены с реальным OpenAPI сервиса — см.
  Фазу 1.

## Найденный по ходу баг №2 (сверка с genplanner-lib 1.0.3) [ИСПРАВЛЕНО, коммит `5ff0bb0`]

Проверил реальные сигнатуры `GenPlanner.__init__`/`features2terr_zones2blocks`/`ZoneRelationMatrix` в
установленном пакете (`.venv/Lib/site-packages/genplanner`) — использование библиотеки в целом корректно
(конструктор, `relation_matrix`, `existing_terr_zones`+`territory_zone`-колонка, `FORBIDDEN_NEIGHBORHOOD`
как `set` — всё совпадает).

Но нашёлся реальный баг в `form_genplanner_response`, напрямую касающийся `min_block_area` — параметра,
который чат должен уметь задавать (тир «чат + уточнение»):

`TerritoryZone` — Rust-класс с value-based `__eq__`/`__hash__` **по всем полям, включая `min_block_area`**
(проверено эмпирически на установленном пакете). `reverse_default_zone_map` в `form_genplanner_response`
строился из `default_terr_zones_map` (объекты с *дефолтным* `min_block_area`), а зоны, которые реально
возвращает генерация, несут объекты из `_custom_func_zone.zones_ratio` (построены в
`assign_custom_ter_zone_name` с `min_block_area`, который мог быть переопределён через `min_block_area`
в запросе). Как только `min_block_area` переопределён для зоны — `reverse_default_zone_map.get(territory_zone)`
промахивался (другой hash), и код молча падал на фолбэк `kind_to_default_id.get(kind)` — первый
дефолтный id для этого kind, а не реальный id из запроса.

На практике это не ломало уникальные-по-kind зоны (RECREATION/TRANSPORT/AGRICULTURE/SPECIAL/INDUSTRIAL/
BUSINESS — у каждого один id), но **RESIDENTIAL** имеет 5 id (1,10,11,12,13). Значит: если в
`territory_balance` указан id **10/11/12/13** И для него передан кастомный `min_block_area` — в ответе
`territory_zone` у сгенерированных зон этого профиля был бы ошибочно **"1"** вместо реального id.

Исправлено: `_resolve_territory_zone_id` теперь берёт id напрямую из `territory_zone.name` (всегда
равно строковому id зоны по построению), без value-equality lookup.
