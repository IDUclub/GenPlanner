from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from iduconfig import Config

from app.common.exceptions.http_exception import http_exception
from app.dependencies import get_config, get_log_path

logs_router = APIRouter(prefix="/logs", tags=["logs"])


# TODO add env getter and setter
@logs_router.get("/log_file")
async def get_logs(log_path: Path = Depends(get_log_path), config: Config = Depends(get_config)):
    """
    Get logs file from app
    """

    try:
        return FileResponse(
            log_path,
            media_type="application/octet-stream",
            filename=config.get("LOG_FILE"),
        )
    except FileNotFoundError as e:
        raise http_exception(
            status_code=404,
            msg="Log file not found",
            _input={
                "lof_file_name": config.get("LOG_FILE"),
                "log_path": repr(log_path),
            },
            _detail={"error": repr(e)},
        ) from e
    except Exception as e:
        raise http_exception(
            status_code=500,
            msg="Internal server error during reading logs",
            _input={"lof_file_name": config.get("LOG_FILE"), "log_path": repr(log_path)},
            _detail={"error": repr(e)},
        ) from e
