import sys
from pathlib import Path

from loguru import logger


def init_logger(log_path: Path, log_level: str):
    """
    Function initializes app logger
    Args:
        log_path (Path): Path to the log file
        log_level (str): Logging level for loguru logger
    """

    logger.remove()
    log_level = log_level.upper()
    log_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <yellow>Line {line: >4} ({file}):</yellow> <b>{message}</b>"
    logger.add(sys.stderr, level=log_level, format=log_format, colorize=True, backtrace=True, diagnose=True)
    logger.add(log_path, level=log_level, format=log_format, colorize=False, backtrace=True, diagnose=True)
