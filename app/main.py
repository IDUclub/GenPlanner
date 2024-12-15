import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.common.config.config import config
from app.gen_planner.gen_planner_controller import gen_planner_router
from app.gen_planner.task_service import task_queue

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:MM-DD HH:mm}</green> | <level>{level:<8}</level> | <cyan>{message}</cyan>",
    level="INFO",
    colorize=True,
)


async def process_tasks() -> None:
    """Function for processing task from async queue"""

    while True:
        task = await task_queue.get()
        await asyncio.to_thread(task.run_generations)
        task_queue.task_done()
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan function for task creation and processing
    """

    asyncio.create_task(process_tasks(), name="plan_generation")
    yield


app = FastAPI(lifespan=lifespan)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(gen_planner_router, prefix=config.get("APP_PREFIX"))
