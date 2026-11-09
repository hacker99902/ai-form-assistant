
from datetime import datetime, timedelta, timezone
import jwt

from app.core.config import settings


def create_extension_token(user_id: str) -> str:
    """
    Create a short-lived JWT for Chrome Extension authentication.
    """

    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=30),
        "type": "extension_access"
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM
    )

    return token


def verify_extension_token(token: str) -> str:
    """
    Verify an extension JWT and return its user ID.
    """

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )

        if payload.get("type") != "extension_access":
            raise ValueError("Invalid token type")

        user_id = payload.get("sub")

        if not user_id:
            raise ValueError("User ID missing from token")

        return user_id

    except jwt.InvalidTokenError as exc:
        raise ValueError("Invalid or expired extension token") from exc


from fastapi import Request, HTTPException

def get_authenticated_user_id(request: Request) -> str:
    """
    Authenticate using the existing web session or
    the Chrome extension's Bearer JWT.
    """

    # First support normal web-app authentication.
    user_id = request.session.get("user_id")

    if user_id:
        return str(user_id)

    # Then support Chrome extension authentication.
    authorization = request.headers.get("Authorization", "")

    if authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()

        try:
            return verify_extension_token(token)
        except ValueError:
            pass

    raise HTTPException(
        status_code=401,
        detail="Authentication required. Please sign in."
    )
