from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

http_bearer = HTTPBearer()


async def verify_bearer_token(credentials: HTTPAuthorizationCredentials = Depends(http_bearer)) -> str:
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing",
        )

    token = credentials.credentials

    if not token:
        raise HTTPException(status_code=400, detail="Token is missing in the authorization header")

    return token
