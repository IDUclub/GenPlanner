# from typing import Optional
#
# from pydantic import BaseModel
# from geojson_pydantic import FeatureCollection
#
# class GenPlannerStartSchema(BaseModel):
#     task_id: str
#
# class GenPlannerResultSchema(BaseModel):
#     zones: FeatureCollection
#     roads: FeatureCollection
#
# class GenPlannerSchema(BaseModel):
#     status: str
#     progress: int
#     geojson: Optional[list[GenPlannerResultSchema]] = None
#     errors: Optional[dict] = None
