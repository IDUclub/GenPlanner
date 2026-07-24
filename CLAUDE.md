# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

GenPlanner API — a FastAPI REST service that wraps the `genplanner` library (a Rust-backed Python package for generating
territorial/functional zones and road networks from urban geometry). The service fetches project/scenario geometry from
external "Urban API" and "Ecodonut API" instances, feeds it into `genplanner`, and returns generated functional zones and
roads as GeoJSON. It integrates with the "Prostor" platform.

## Commands

Dependency management is via Poetry (`pyproject.toml`), Python `>=3.11,<3.13`.

```bash
poetry install --with dev        # install all deps including dev tools (equivalent to `make install-dev`)
make format                       # isort + black on app/
make lint                         # pylint on app/
```

There is no test suite in this repository (no `tests/` directory, no pytest config). Do not invent test commands.

Running the app locally:

```bash
uvicorn app.main:app --reload --port 80
```

Docker (production entrypoint uses gunicorn + uvicorn workers, see `Dockerfile` CMD):

```bash
docker compose up            # docker-compose.yml — local build
```

The `docker-compose.actions.yml` file is only used by the CI/CD deploy workflow (`.github/workflows/build_and_deploy.yml`),
not for local development.

### Configuration

Config is loaded via `iduconfig.Config()` (reads `.env.development` / environment) and stashed on `app.state.config` at
startup (`app/init_dependencies.py`). Key vars (see `.env.development`): `URBAN_API`, `TEST_URBAN_API`, `ECODONUT_API`,
`MAX_API_ASYNC_EXTRACTIONS`, `LOG_LEVEL`, `LOG_FILE`, `APP_ENV`. `APP_ENV=development` disables `parallel` mode in
`GenPlanner` construction (see `gen_planner_service.form_genplanner`).

Chat-feature vars are all optional — leaving any of them empty disables that piece rather than crashing at startup
(see `app/common/config_utils.get_optional_config`, used instead of `Config.get()` which raises on a missing key):
`OLLAMA_BASE_URL`, `GENERATE_MODEL`/`CHAT_MODEL`, `CHAT_TEMPERATURE`, `CHAT_REQUEST_TIMEOUT_SECONDS` (Ollama);
`CHAT_STORAGE_BASE_URL`, `CHAT_STORAGE_TIMEOUT_SECONDS` (ChatStorage history); `KEYCLOAK_URL`, `KEYCLOAK_REALM`,
`KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_SCOPE` (service-to-service token for ChatStorage).

## Architecture

Layered structure under `app/`, two feature modules (`gen_planner`, `chat`) plus shared infrastructure:

- **`app/main.py`** — FastAPI app factory, CORS, router registration, lifespan hook that calls `init_dependencies`.
- **`app/init_dependencies.py`** — builds all singletons once at startup and attaches them to `app.state`
  (`config`, `log_path`, `genplanner_service`, `test_genplanner_service`). Two `GenPlannerService` instances exist —
  one wired to `URBAN_API`, one to `TEST_URBAN_API` — selected per-request via the DTO's `test: bool` field.
- **`app/dependencies.py`** — FastAPI `Depends` accessors that read back off `request.app.state`.
- **`app/gen_planner/`** — the only feature module:
  - `gen_planner_controller.py` — routes (`/genplanner/...`), thin: parses DTOs, delegates to `GenPlannerService`.
  - `gen_planner_service.py` — all business logic. Orchestrates external API calls, builds a `genplanner.GenPlanner`
    instance, runs generation (in a thread via `asyncio.to_thread` since the Rust core is sync/CPU-bound), and shapes
    the response.
  - `dto/` — pydantic request DTOs. Each DTO does its own validation/transformation in `@model_validator(mode="after")`
    hooks and stashes derived, non-serialized state in private (`_`-prefixed) attributes — e.g.
    `GenPlannerFuncZonesDTO._territory_gdf`, `._fix_zones_gdf`, `._custom_func_zone`. Controllers and the service read
    these private attrs directly; this is the primary way data flows from "raw request" to "ready-to-use GeoDataFrame /
    genplanner object" without a separate mapper layer.
  - `schema/` — response schema (`GenPlannerResultSchema`).
- **`app/clients/`** — outbound HTTP clients, all built on `app/common/api_handlers/json_api_handler.py`
  (`AsyncJsonApiHandler`, a thin aiohttp GET wrapper that converts non-2xx responses into `http_exception`).
  - `UrbanApiClient` — territory/project/scenario/physical-objects/functional-zones lookups; also batches parallel
    requests via `extract_several_requests` (chunked by `MAX_API_ASYNC_EXTRACTIONS`) and can convert
    FeatureCollection responses straight to GeoDataFrames.
  - `EcodonutApiClient` — slope polygon lookups (used to exclude steep terrain from generation).
- **`app/common/`** — cross-cutting:
  - `geometries_dto/geometries.py` — GeoJSON pydantic models (`Feature`, `FeatureCollection`, and typed variants like
    `PolygonalFeatureCollection`, `FixZoneFeatureCollection`) with `.as_gdf()` to convert to GeoPandas. This is the
    shared geometry validation layer used by request DTOs.
  - `constants/api_constants.py` — maps between the API's integer functional/territorial zone IDs and `genplanner`'s
    `TerritoryZone`/`FunctionalZone`/`TerritoryZoneKind` objects (`scenario_func_zones_map`, `default_terr_zones_map`,
    `custom_ter_zones_map_by_name`). This mapping is the bridge between "IDs the outside world sends" and "objects
    genplanner understands" — most zone-related bugs trace back to a mismatch here.
  - `auth/bearer.py` — `verify_bearer_token`: passes through a bearer token from the request (does not itself validate
    it — the downstream Urban/Ecodonut APIs do) for use as the auth token forwarded to external APIs.
  - `exceptions/http_exception.py` — `http_exception(status_code, msg, _input, _detail)` factory used everywhere
    instead of raising `HTTPException` directly, to keep error payload shape consistent (`{msg, input, detail}`).
  - `exceptions/exception_handler.py` — `ExceptionHandlerMiddleware`, currently commented out in `main.py`.
  - `logging/init_logger.py` — loguru setup, writes to `app.state.log_path`, exposed for download via
    `app/system/logs_router.py` (`GET /genplanner/logs/log_file`).
  - `llm/ollama_chat_client.py` — `OllamaChatClient`, aiohttp wrapper around Ollama's `/api/chat`:
    `.stream_chat()` for token streaming, `.complete_json()` for schema-constrained structured output
    (used once per chat turn instead of hand-rolled tool-calling).
  - `chat_storage/chat_storage_client.py` — `ChatStorageClient`, persists chat history to the IDUclub
    ChatStorage service. Authenticated with OUR service token (not the user's, which can expire mid-chat),
    end user identified via `X-User-Id`.
  - `auth/service_token.py` — Keycloak `client_credentials` token client (`idu_service_auth`, a git
    dependency — not on the private PyPI mirror) for the ChatStorage calls above.
  - `auth/user_identity.py` — extracts the `sub` claim from the user's bearer token (unverified, same
    trust model as `bearer.py`) to attribute chat history to the right user.
  - `config_utils.get_optional_config` — `Config.get()` that returns `None` instead of raising, for the
    chat feature's optional integrations.
- **`app/chat/`** — the chat feature module, `POST /genplanner/scenarios/{scenario_id}/chat/stream` (SSE):
  - `chat_service.stream_chat_turn` — one call to `OllamaChatClient.complete_json` per turn decides an
    `action` (`update_draft` / `ask_clarifying_question` / `run_generation` / `list_zones` / `chat`) and
    produces the reply text in the same call; the reply is then chunked and replayed as `token` events
    rather than issuing a second LLM call just for streaming. `run_generation` builds a
    `GenPlannerFuncZonesDTO` directly as a Python object (not through FastAPI) and calls
    `GenPlannerService.run_func_generation` in-process — no separate task queue.
  - `agent/draft.py` — `GenerationDraft`, the in-progress DTO fields the chat can actually set
    (`territory_balance`/`neighbour_pairs`/`forbidden_pairs` directly, `min_block_area`/`elevation_angle`/
    `roads_extend_distance` via clarifying questions). Deliberately excludes `fix_zones`/`functional_zones`
    (would need a map / imply reusing existing zones) and `project_id`/`scenario_id`/`test` (session
    context, never chat text). Persisted as JSON in the latest assistant message's ChatStorage `metadata`
    — no separate database for chat state.
  - `agent/schema.py` / `agent/prompts.py` — the JSON Schema passed as Ollama's `format`, and the system
    prompt (data/chat_system_prompt.txt) rendered with a live zone-id reference table and the current draft.
  - Note: `project_id` is a *required* field on `GenPlannerFuncZonesDTO` (pydantic-enforced) — constructing
    it directly (as the chat service does) always needs a real value, so `chat_service._resolve_project_id`
    looks it up from `scenario_id` before building the DTO, rather than relying on
    `GenPlannerService.restore_params`'s "resolve if missing" branch (which is unreachable via the plain
    REST endpoint too: FastAPI's own query-param validation already 422s on a missing `project_id` before
    `restore_params` ever runs).

### Request flow (typical: `POST /genplanner/run_func_generation`)

1. Controller builds `GenPlannerFuncZonesDTO` from query/body; its validators pre-compute
   `_custom_id_ter_zone_map` / `_custom_func_zone` (territory-balance IDs → `genplanner` zone objects) and
   `_fix_zones_gdf` (fixed-zone GeoJSON → GeoDataFrame).
2. `GenPlannerService.run_func_generation` → `form_genplanner`: resolves `project_id` from scenario if missing
   (`restore_params`), fetches territory geometry, physical objects (roads, water, slope-exclusion) concurrently via
   `asyncio.gather`, optionally fetches and splits existing functional zones into "fixed" vs "remaining" subsets, then
   constructs a `genplanner.GenPlanner` instance.
3. Generation itself (`genplanner.features2terr_zones2blocks`) runs off the event loop via `asyncio.to_thread`, wrapped
   in `_run_features_generation_with_retries` (3 attempts, since the Rust core occasionally fails intermittently).
4. Result zones/roads GeoDataFrames are reconciled with any "fixed" zones and serialized to GeoJSON
   (`form_genplanner_response`).

There is also a "custom" path (`/custom/run_func_generation`, `GenPlannerCustomDTO`) that skips the Urban API entirely
and generates zones directly on a user-supplied polygon + `profile_id` — useful for zone-ratio experiments without a
real project/scenario.

### Working with zone IDs

Functional zone "profile" IDs (`scenario_func_zones_map`) and territorial zone IDs (`default_terr_zones_map`) are
separate ID spaces defined in `app/common/constants/api_constants.py` — don't conflate a `functional_zone_type_id`
from Urban API with a `profile_id` used by `/custom/run_func_generation`. `GET /genplanner/zones_list` and
`GET /genplanner/default/func_ratio` exist specifically to introspect these mappings at runtime.

## Notes

- Loose `.geojson` files and `genplanner.log` at the repo root are runtime/debug artifacts (not fixtures checked in on
  purpose) — don't treat them as canonical sample data without checking with the user first.
- `app/version.py` (`__version__`) and `pyproject.toml`'s `version` should be bumped together on release.
