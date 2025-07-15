from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.common.exceptions.http_exception import http_exception
from app.dependencies import config

logs_router = APIRouter(prefix="/logs", tags=["logs"])


@logs_router.get("/logs")
async def get_logs():
    """
    Get logs file from app
    """

    try:
        return FileResponse(
            f"{config.get('LOG_FILE')}.log",
            media_type="application/octet-stream",
            filename=f"{config.get('LOG_FILE')}.log",
        )
    except FileNotFoundError as e:
        raise http_exception(
            status_code=404,
            msg="Log file not found",
            _input={"lof_file_name": f"{config.get('LOG_FILE')}.log"},
            _detail={"error": e.__str__()},
        )
    except Exception as e:
        raise http_exception(
            status_code=500,
            msg="Internal server error during reading logs",
            _input={"lof_file_name": f"{config.get('LOG_FILE')}.log"},
            _detail={"error": e.__str__()},
        )
