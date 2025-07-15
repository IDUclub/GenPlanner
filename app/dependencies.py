import sys

from iduconfig import Config
from loguru import logger

from app.gateways.urban_api_gateway import UrbanApiGateway

config = Config()

logger.remove()
log_level = "DEBUG"
log_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <yellow>Line {line: >4} ({file}):</yellow> <b>{message}</b>"
logger.add(sys.stderr, level=log_level, format=log_format, colorize=True, backtrace=True, diagnose=True)
logger.add(f".log", level=log_level, format=log_format, colorize=False, backtrace=True, diagnose=True)

urban_api_gateway = UrbanApiGateway(config.get("URBAN_API_URL"), int(config.get("MAX_API_ASYNC_EXTRACTIONS")))
