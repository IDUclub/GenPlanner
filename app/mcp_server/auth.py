from fastmcp.exceptions import AuthorizationError
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_http_headers


class AnyTokenVerifier(TokenVerifier):
    """
    Requires a non-empty Bearer token at the MCP transport level for every tool call,
    without validating it -- signature/scope validation happens downstream in Urban API,
    same as the rest of this app (see app/common/auth/bearer.py). Matches the pattern
    used by gMART's idu_mcp (github.com/IDUclub/gMART).
    """

    async def verify_token(self, token: str) -> AccessToken:
        if not token:
            raise AuthorizationError("Bearer token is required")

        return AccessToken(token=token, client_id="unknown", scopes=[])


def extract_token() -> str:
    """
    FastMCP dependency (usable via `Depends(extract_token)`) returning the caller's
    raw Bearer token, to forward to GenPlanner API downstream. AnyTokenVerifier already
    guarantees the header is present by the time a tool runs; this stays defensive to
    match gMART's idu_mcp convention.
    """

    headers = get_http_headers(include={"authorization"})
    auth_header = headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise ValueError("Unauthorized: Bearer token is missing")
    return auth_header.removeprefix("Bearer ").strip()
