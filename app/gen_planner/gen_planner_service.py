# import datetime
# import hashlib
# import json
#
# import geopandas as gpd
# from loguru import logger
# from shapely.geometry import shape
#
# from app.common.exceptions.http_exception import http_exception
#
# from .gen_planner_dto import GenPlannerDTO
# from .python.src.genplanner import GenPlanner
# from .task_service import Task, task_map, task_queue
#
#
# class GenPlannerService:
#
#     @staticmethod
#     async def p_hash(polygon: gpd.GeoDataFrame) -> str:
#         """Hash creation function"""
#
#         json_str = str(json.loads(polygon.to_json()))
#         request_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S%M")
#         readable_hash = hashlib.sha256(json_str.encode()).hexdigest() + request_time
#         return readable_hash
#
#     @staticmethod
#     async def get_task_status(task_id: str) -> dict:
#         """
#
#         :param task_id: str, task_id to check
#         :return: dict, info with check results
#         """
#
#         if task_to_check := task_map.get(task_id):
#             result = await task_to_check.get_result()
#             if result["status"] in ("done", "failed"):
#                 result = result.copy()
#                 del task_to_check
#
#             return result
#
#         raise http_exception(404, msg="Task not found", _input=task_id, _detail=None)
#
#     async def add_task_to_queue(self, planner_params: GenPlannerDTO) -> dict:
#
#         territory_gdf = gpd.GeoDataFrame(geometry=[shape(planner_params.territory.__dict__)], crs=4326)
#         task_id = await self.p_hash(territory_gdf)
#         gen_planer = GenPlanner(territory_gdf)
#         task_to_register = Task(task_id=task_id, processor=gen_planer)
#         task_map[task_id] = task_to_register
#         await task_queue.put(task_to_register)
#         logger.info(f"Task {task_id} added to queue")
#         return {"task_id": task_id}
#
#
# gen_planner_service = GenPlannerService()
