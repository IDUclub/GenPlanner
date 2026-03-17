from pathlib import Path

from fastapi import Request
from iduconfig import Config

from app.gen_planner.gen_planner_service import GenPlannerService


def get_config(request: Request) -> Config:

    return request.app.state.config


def get_genplanner_service(request: Request) -> GenPlannerService:

    return request.app.state.genplanner_service


def get_log_path(request: Request) -> Path:
    return request.app.state.log_path
