import sys
from pathlib import Path

from iduconfig import Config
from loguru import logger


def init_logger(log_path: Path):
    """
    Function initializes app logger
    Args:
        log_path (Path): Path to the log file
    """

    logger.remove()
    log_level = "DEBUG"
    log_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <yellow>Line {line: >4} ({file}):</yellow> <b>{message}</b>"
    logger.add(sys.stderr, level=log_level, format=log_format, colorize=True, backtrace=True, diagnose=True)
    logger.add(log_path, level=log_level, format=log_format, colorize=False, backtrace=True, diagnose=True)
