from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from app.common.exceptions.exception_handler import ExceptionHandlerMiddleware
from app.dependencies import config
from app.gen_planner.gen_planner_controller import gen_planner_router
from app.system.logs_router import logs_router

app = FastAPI(
    title="GenPlanner",
    description="GenPlanner by DDonnyy api service",
)

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


app.include_router(logs_router, prefix=config.get("APP_PREFIX"))
app.include_router(gen_planner_router, prefix=config.get("APP_PREFIX"))
