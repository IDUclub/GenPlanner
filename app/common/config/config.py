from pathlib import Path
from dotenv import load_dotenv
import os
from loguru import logger


class ApplicationConfig:
    def __init__(self):
        load_dotenv(Path().absolute() / f".env.{os.getenv('APP_ENV')}")
        logger.info("Env variables loaded")

    @staticmethod
    def get(key: str) -> str | int | None:
        res = os.getenv(key)
        if res.isnumeric():
            res = int(res)
        return res

    @staticmethod
    def get_default(key: str, default=None) -> str | int | None:
        res = os.getenv(key)
        if res:
            if res.isnumeric():
                res = int(res)
            return res
        return default


config = ApplicationConfig()
