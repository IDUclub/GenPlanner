import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from loguru import logger

from app.common.config.config import config
# from app.gen_planner.task_service import task_queue
from app.gen_planner.gen_planner_controller import gen_planner_router
from app.common.exceptions.http_exception import http_exception


logger.remove()
log_level = "DEBUG"
log_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <yellow>Line {line: >4} ({file}):</yellow> <b>{message}</b>"
logger.add(sys.stderr, level=log_level, format=log_format, colorize=True, backtrace=True, diagnose=True)
logger.add(
    f'{config.get("LOGS_FILE")}.log',
    level=log_level,
    format=log_format,
    colorize=False,
    backtrace=True,
    diagnose=True
)


# async def process_tasks() -> None:
#     """Function for processing task from async queue"""
#
#     while True:
#         task = await task_queue.get()
#         await asyncio.to_thread(task.run_generations)
#         task_queue.task_done()
#         await asyncio.sleep(1)
#
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     """
#     Lifespan function for task creation and processing
#     """
#
#     asyncio.create_task(process_tasks(), name="plan_generation")
#     yield

app = FastAPI()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_model=dict[str, str])
def read_root():
    return RedirectResponse(url='/docs')

@app.get("/logs")
async def get_logs():
    """
    Get logs file from app
    """

    try:
        return FileResponse(
            f"{config.get('LOG_FILE')}.log",
            media_type='application/octet-stream',
            filename=f"{config.get('LOG_FILE')}.log",
        )
    except FileNotFoundError as e:
        raise http_exception(
            status_code=404,
            msg="Log file not found",
            _input={"lof_file_name": f"{config.get('LOG_FILE')}.log"},
            _detail={"error": e.__str__()}
        )
    except Exception as e:
        raise http_exception(
            status_code=500,
            msg="Internal server error during reading logs",
            _input={"lof_file_name": f"{config.get('LOG_FILE')}.log"},
            _detail={"error": e.__str__()}
        )


app.include_router(gen_planner_router, prefix=config.get("APP_PREFIX"))
