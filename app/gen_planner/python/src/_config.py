import os
import sys
from typing import Literal

from loguru import logger


class Config:
    poisson_n_radius = {
        2: 0.25,
        3: 0.23,
        4: 0.21,
        5: 0.18,
        6: 0.16,
        7: 0.14,
        8: 0.12,
    }

    roads_width_def = {"high speed highway": 30, "regulated highway": 20, "local road": 5}

    def __init__(
        self,
    ):
        self.logger = logger
        print(f"Available workers count {os.cpu_count()}")

    def change_logger_lvl(self, lvl: Literal["TRACE", "DEBUG", "INFO", "WARN", "ERROR"]):
        self.logger.remove()
        self.logger.add(sys.stderr, level=lvl)


config = Config()
config.change_logger_lvl("INFO")
