
import logging

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

from app.core.oauth import oauth
from app.services.auth_service import get_or_create_google_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/google/login")
async def google_login(request: Request):
    """
    Redirect the user to Google's login page.
    """

    redirect_uri = request.url_for("google_callback")

    return await oauth.google.authorize_redirect(
        request,
        redirect_uri
    )


@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request):
    """
    Handle Google's authentication response.
    """

    try:
        token = await oauth.google.authorize_access_token(request)

        user_info = token.get("userinfo")

        if not user_info:
            user_info = await oauth.google.userinfo(token=token)

        user = get_or_create_google_user(dict(user_info))

        # Store only the internal application user ID.
        request.session["user_id"] = user["id"]

        # Temporary redirect to the existing frontend.
        return RedirectResponse(
            url="http://127.0.0.1:5500/",
            status_code=303
        )

    except Exception:
        logger.exception("Google authentication failed")

        request.session.clear()

        raise HTTPException(
            status_code=401,
            detail="Google authentication failed"
        )


@router.get("/me")
async def get_current_user(request: Request):
    """
    Return the currently authenticated user.
    """

    user_id = request.session.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated"
        )

    from app.core.database import get_db_pool

    pool = get_db_pool()

    with pool.connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, full_name, picture_url
                FROM users
                WHERE id = %s
                """,
                (user_id,)
            )

            user = cursor.fetchone()

    if not user:
        request.session.clear()

        raise HTTPException(
            status_code=401,
            detail="User account not found"
        )

    return {
        "id": str(user[0]),
        "email": user[1],
        "full_name": user[2],
        "picture_url": user[3]
    }


@router.post("/logout")
async def logout(request: Request):
    """
    Clear the current application session.
    """

    request.session.clear()

    return {
        "message": "Logged out successfully"
    }
