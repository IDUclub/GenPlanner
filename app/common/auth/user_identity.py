from jose.exceptions import JWTError
from jose.jwt import get_unverified_claims


def extract_user_id(token: str) -> str | None:
    """
    Extract the end-user id (the `sub` claim) from a bearer JWT without verifying its
    signature -- mirrors bearer.verify_bearer_token, which already trusts the token
    as-is and lets the downstream Urban API do the actual validation. Used to attribute
    chat history to the right user in ChatStorage, which is reached with our own
    service token rather than the user's.
    """

    try:
        claims = get_unverified_claims(token)
    except JWTError:
        return None

    sub = claims.get("sub")
    return str(sub) if sub else None
