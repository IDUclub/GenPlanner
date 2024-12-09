import json
from typing import Literal
from asyncio.queues import Queue
from loguru import logger

from app.common.config.config import config
from app.common.exceptions.http_exception import http_exception
from .python.src.genplanner import GenPlanner
from .python.src.zoning.standart_implement import FuncZone, basic_scenario


task_queue = Queue()
task_map = {}

class Task:
    """This class describes task object parametres for queue"""

    def __init__(
            self,
            task_id: str,
            processor: GenPlanner,
            scenario: FuncZone = basic_scenario,
            total_generations: int = 5,
    ) -> None:
        """Task class initialisation function"""

        self.task_id: str = task_id
        self.task_results: list[dict] = []
        self.processor: GenPlanner = processor
        self.total_generations: int = total_generations
        self.scenario: FuncZone = scenario
        self.current_generation: int = 0
        self.status: Literal[
            "pending",
            "running",
            "done",
            "failed",
        ] = "pending"
        self.max_generations_retries: int = config.get_default("MAX_GENERATIONS_RETRIES", 10)
        self.errors: list = []
        self.task_queue: list = task_queue

    async def add_task_id_to_task_map(self):
        task_map[self.task_id] = self

    async def set_status(self, status: str) -> None:
        self.status = status

    def add_result(self, result: dict) -> None:
        self.task_results.append(result)

    async def get_result(
            self
    ) -> dict[str, list[dict] | float | str] | dict[str, str | float]:
        """
        Get available task results from task service queue

        Returns:
            dict[str, list[dict] | float | str] | dict[str, str | float | str]: dict info to sent to user
        """

        progress = self.current_generation / self.total_generations * 100

        match self.status:
            case "pending":
                return {
                    "status": self.status,
                    "progress": progress,
                }
            case "running":
                if self.task_results:
                    results = self.task_results.copy()
                    self.task_results = []
                    return {
                        "status": self.status,
                        "progress": progress,
                        "geojson": results,
                    }
                return {
                    "status": self.status,
                    "progress": progress,
                }
            case "done":
                results = self.task_results.copy()
                return {
                    "status": self.status,
                    "progress": progress,
                    "geojson": results,
                }
            case "failed":
                return {
                    "status": self.status,
                    "progress": progress,
                    "errors": self.errors,
                }

    def run_generations(
            self
    ) -> None:

        logger.info(f"Starting generation {self.current_generation}")
        self.status = "running"
        generation_retries = 0
        while self.current_generation < self.total_generations:
            if generation_retries >= self.max_generations_retries:
                self.status = "failed"
                error_info = http_exception(
                    500,
                    msg="Maximum number of retries reached",
                    _input=self.task_id,
                    _detail=f"broken on generation {self.current_generation}",
                )
                self.errors.append(error_info)
                break
            try:
                current_generation_result, roads = self.processor.district2zone2block(self.scenario)
                json_zones_result = json.loads(current_generation_result.to_json())
                json_roads_result = json.loads(roads.to_json())
                current_result = {
                    "zones": json_zones_result,
                    "roads": json_roads_result,
                }
                self.task_results.append(current_result)
                self.current_generation += 1
                generation_retries = 0
            except Exception as e:
                logger.warning(e)
                generation_retries += 1
                continue
