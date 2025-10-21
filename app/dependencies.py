import sys

from iduconfig import Config
from loguru import logger

from app.clients.ecodonat_api_client import EcodonutApiClient
from app.clients.urban_api_client import UrbanApiClient
from app.common.api_handlers.json_api_handler import AsyncJsonApiHandler

config = Config()

logger.remove()
log_level = "DEBUG"
log_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <yellow>Line {line: >4} ({file}):</yellow> <b>{message}</b>"
logger.add(sys.stderr, level=log_level, format=log_format, colorize=True, backtrace=True, diagnose=True)
logger.add(f".log", level=log_level, format=log_format, colorize=False, backtrace=True, diagnose=True)

urban_api_handler = AsyncJsonApiHandler(config.get("URBAN_API"))
urban_api_client = UrbanApiClient(urban_api_handler, int(config.get("MAX_API_ASYNC_EXTRACTIONS")))

ecodonut_api_handler = AsyncJsonApiHandler(config.get("ECODONUT_API"))
ecodonut_api_client = EcodonutApiClient(ecodonut_api_handler, int(config.get("MAX_API_ASYNC_EXTRACTIONS")))
