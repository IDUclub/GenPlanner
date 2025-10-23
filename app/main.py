from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.common.exceptions.exception_handler import ExceptionHandlerMiddleware
from app.gen_planner.gen_planner_controller import gen_planner_router
from app.init_dependencies import init_dependencies
from app.system.logs_router import logs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_dependencies(app)
    yield


app = FastAPI(lifespan=lifespan, title="GenPlanner", description="GenPlanner by DDonnyy api service", version="0.1.0")

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ExceptionHandlerMiddleware)


@app.get("/", response_model=dict[str, str])
def read_root():
    return RedirectResponse(url="/docs")


app.include_router(logs_router, prefix="/genplanner")
app.include_router(gen_planner_router, prefix="/genplanner")
