from fastapi import APIRouter

from .gen_planner_dto import GenPlannerDTO
from .gen_planner_service import gen_planner_service

gen_planner_router = APIRouter(tags=["gen_planner"])


@gen_planner_router.post("/run_generation")
async def run_generation(params: GenPlannerDTO):
    result = await gen_planner_service.add_task_to_queue(params)
    return result

@gen_planner_router.get("/check_generation")
async def check_generation(task_id: str):
    result = await gen_planner_service.get_task_status(task_id)
    return result
