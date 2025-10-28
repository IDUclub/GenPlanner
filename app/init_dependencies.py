from pathlib import Path

from fastapi import FastAPI
from iduconfig import Config
from loguru import logger

from app.clients.ecodonat_api_client import EcodonutApiClient
from app.clients.urban_api_client import UrbanApiClient
from app.common.api_handlers.json_api_handler import AsyncJsonApiHandler
from app.common.logging.init_logger import init_logger
from app.gen_planner.gen_planner_service import GenPlannerService


async def init_dependencies(app: FastAPI):
    """
    Function to initialize dependencies in app state
    Args:
        app (FastAPI): FastAPI app instance
    """

    # app config initialization
    app.state.config = Config()

    # logger initialization
    app.state.log_path = Path().resolve().absolute() / app.state.config.get("LOG_FILE")
    init_logger(app.state.log_path, app.state.config.get("LOG_LEVEL"))

    # gen_planner_service initialisation
    urban_api_handler = AsyncJsonApiHandler(app.state.config.get("URBAN_API"))
    urban_api_client = UrbanApiClient(urban_api_handler, int(app.state.config.get("MAX_API_ASYNC_EXTRACTIONS")))
    ecodonut_api_handler = AsyncJsonApiHandler(app.state.config.get("ECODONUT_API"))
    ecodonut_api_client = EcodonutApiClient(
        ecodonut_api_handler, int(app.state.config.get("MAX_API_ASYNC_EXTRACTIONS"))
    )
    app.state.genplanner_service = GenPlannerService(urban_api_client, ecodonut_api_client)
    logger.info("Initialized app dependencies")
