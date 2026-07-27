from pathlib import Path

from fastmcp import FastMCP
from iduconfig import Config
from loguru import logger
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.common.config_utils import get_optional_config
from app.common.logging.init_logger import init_logger
from app.mcp_server.api_client import GenPlannerApiClient
from app.mcp_server.auth import AnyTokenVerifier
from app.mcp_server.tools.genplanner_tools import register_tools
from app.version import __version__ as version

DEFAULT_PORT = 8766
DEFAULT_UPSTREAM_TIMEOUT_SECONDS = 300.0


def build_mcp(config: Config) -> FastMCP:
    base_url = config.get("GENPLANNER_API_BASE_URL")
    timeout_raw = get_optional_config(config, "MCP_UPSTREAM_TIMEOUT_SECONDS")
    timeout_seconds = float(timeout_raw) if timeout_raw else DEFAULT_UPSTREAM_TIMEOUT_SECONDS
    client = GenPlannerApiClient(base_url, timeout_seconds=timeout_seconds)

    mcp = FastMCP("GenPlanner MCP", version=version, auth=AnyTokenVerifier())
    register_tools(mcp, client)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> Response:
        return JSONResponse({"status": "ok"})

    @mcp.custom_route("/", methods=["GET"])
    async def root(_request: Request) -> Response:
        return RedirectResponse(url="/mcp")

    return mcp


def main() -> None:
    config = Config()

    log_path = Path().resolve().absolute() / config.get("LOG_FILE")
    init_logger(log_path, config.get("LOG_LEVEL"))

    port = int(get_optional_config(config, "MCP_SERVER_PORT") or DEFAULT_PORT)

    mcp = build_mcp(config)
    logger.info(f"Starting GenPlanner MCP server on port {port}")
    mcp.run(transport="http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
