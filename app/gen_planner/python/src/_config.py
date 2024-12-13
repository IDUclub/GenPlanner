import sys
from typing import Literal
import os
from loguru import logger


class Config:
    poisson_n_radius = {
        2: 0.25,
        3: 0.23,
        4: 0.22,
        5: 0.2,
        6: 0.17,
        7: 0.15,
        8: 0.1,
    }

    roads_width_def = {"high speed highway": 60, "regulated highway": 30, "local road": 10}

    def __init__(
            self,
    ):
        self.logger = logger
        print(f'Available workers count {os.cpu_count()}')

    def change_logger_lvl(self, lvl: Literal["TRACE", "DEBUG", "INFO", "WARN", "ERROR"]):
        self.logger.remove()
        self.logger.add(sys.stderr, level=lvl)


config = Config()
config.change_logger_lvl("INFO")
