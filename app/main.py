from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.chat.chat_controller import chat_router
from app.chat.custom_chat_controller import custom_chat_router
from app.chat.files_controller import files_router
from app.common.auth.bearer import http_bearer, verify_bearer_token
from app.common.config_utils import get_optional_config
from app.common.exceptions.exception_handler import ExceptionHandlerMiddleware
from app.dependencies import get_config
from app.gen_planner.gen_planner_controller import gen_planner_router
from app.init_dependencies import init_dependencies
from app.resumable_streams import install_resumable_streams, keycloak_owner
from app.system.admin_config_router import router as admin_config_router
from app.system.logs_router import logs_router
from app.version import __version__ as version


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_dependencies(app)
    yield
    if app.state.keycloak_token_client is not None:
        await app.state.keycloak_token_client.aclose()


app = FastAPI(lifespan=lifespan, title="GenPlanner", description="GenPlanner by DDonnyy api service", version=version)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
# app.add_middleware(ExceptionHandlerMiddleware)


@app.get("/", response_model=dict[str, str])
def read_root():
    return RedirectResponse(url="/docs")


app.include_router(logs_router, prefix="/genplanner")
app.include_router(gen_planner_router, prefix="/genplanner")
app.include_router(chat_router, prefix="/genplanner")
app.include_router(custom_chat_router, prefix="/genplanner")
app.include_router(files_router, prefix="/genplanner")
app.include_router(admin_config_router)


async def _stream_owner(request):
    token = await verify_bearer_token(await http_bearer(request))
    config = get_config(request)
    return await keycloak_owner(
        token, get_optional_config(config, "KEYCLOAK_URL"), get_optional_config(config, "KEYCLOAK_REALM")
    )


install_resumable_streams(app, service="genplanner", prefix="/genplanner", authenticate=_stream_owner)
