from pathlib import Path

from fastapi import FastAPI
from iduconfig import Config
from loguru import logger

from app.clients.ecodonat_api_client import EcodonutApiClient
from app.clients.urban_api_client import UrbanApiClient
from app.common.api_handlers.json_api_handler import AsyncJsonApiHandler
from app.common.auth.service_token import build_keycloak_token_client
from app.common.chat_storage.chat_storage_client import build_chat_storage_client
from app.common.llm.factory import build_chat_client
from app.common.logging.init_logger import init_logger
from app.gen_planner.gen_planner_service import GenPlannerService
from app.version import __version__ as version


async def init_dependencies(app: FastAPI):
    """
    Function to initialize dependencies in app state
    Args:
        app (FastAPI): FastAPI app instance
    """

    app.state.version = version

    # app config initialization
    app.state.config = Config()

    # logger initialization
    app.state.log_path = Path().resolve().absolute() / app.state.config.get("LOG_FILE")
    init_logger(app.state.log_path, app.state.config.get("LOG_LEVEL"))

    # gen_planner_service initialisation
    urban_api_handler = AsyncJsonApiHandler(app.state.config.get("URBAN_API"))
    test_urban_api_handler = AsyncJsonApiHandler(app.state.config.get("TEST_URBAN_API"))
    urban_api_client = UrbanApiClient(urban_api_handler, int(app.state.config.get("MAX_API_ASYNC_EXTRACTIONS")))
    test_urban_api_client = UrbanApiClient(
        test_urban_api_handler, int(app.state.config.get("MAX_API_ASYNC_EXTRACTIONS"))
    )
    ecodonut_api_handler = AsyncJsonApiHandler(app.state.config.get("ECODONUT_API"))
    ecodonut_api_client = EcodonutApiClient(
        ecodonut_api_handler, int(app.state.config.get("MAX_API_ASYNC_EXTRACTIONS"))
    )
    app.state.genplanner_service = GenPlannerService(urban_api_client, ecodonut_api_client)
    app.state.test_genplanner_service = GenPlannerService(test_urban_api_client, ecodonut_api_client)

    # chat feature dependencies -- all optional, left None (feature disabled) until
    # VLLM_BASE_URL / CHAT_STORAGE_BASE_URL / KEYCLOAK_* are actually configured
    app.state.llm_chat_client = build_chat_client(app.state.config)
    app.state.keycloak_token_client = build_keycloak_token_client(app.state.config)
    app.state.chat_storage_client = build_chat_storage_client(app.state.config, app.state.keycloak_token_client)

    if app.state.llm_chat_client is None:
        logger.warning("LLM base url/CHAT_MODEL not configured -- chat feature disabled")
    if app.state.chat_storage_client is None:
        logger.warning("ChatStorage/Keycloak not configured -- chat history persistence disabled")

    logger.info("Initialized app dependencies")
