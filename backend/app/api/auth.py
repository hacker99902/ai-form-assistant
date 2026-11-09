
import logging
import secrets
import hashlib

from uuid import UUID

from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core.oauth import oauth
from app.core.database import get_db_pool
from app.core.security import (
    create_extension_token,
    verify_extension_token,
)
from app.services.auth_service import get_or_create_google_user


logger = logging.getLogger(__name__)

router = APIRouter()

EXTENSION_REDIRECT_URI = (
    "https://fmlhmanmpdailmkppahfjafndjgebhjg.chromiumapp.org/"
)


class ExtensionCodeRequest(BaseModel):
    code: str


# --------------------------------------------------
# GOOGLE LOGIN - WEB APPLICATION
# --------------------------------------------------

@router.get("/google/login")
async def google_login(request: Request):

    redirect_uri = request.url_for("google_callback")

    return await oauth.google.authorize_redirect(
        request,
        redirect_uri
    )


# --------------------------------------------------
# GOOGLE LOGIN - CHROME EXTENSION
# --------------------------------------------------

@router.get("/extension/login")
async def extension_login(request: Request):

    request.session["extension_login"] = True

    redirect_uri = request.url_for("google_callback")

    return await oauth.google.authorize_redirect(
        request,
        redirect_uri
    )


# --------------------------------------------------
# GOOGLE OAUTH CALLBACK
# --------------------------------------------------

@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request):

    try:

        token = await oauth.google.authorize_access_token(request)

        user_info = token.get("userinfo")

        if not user_info:
            user_info = await oauth.google.userinfo(token=token)

        user = get_or_create_google_user(dict(user_info))

        request.session["user_id"] = str(user["id"])

        # Chrome extension authentication
        if request.session.pop("extension_login", False):

            auth_code = secrets.token_urlsafe(32)

            code_hash = hashlib.sha256(
                auth_code.encode("utf-8")
            ).hexdigest()

            pool = get_db_pool()

            with pool.connection() as conn:
                with conn.cursor() as cursor:

                    cursor.execute(
                        """
                        INSERT INTO extension_auth_codes (
                            code_hash,
                            user_id,
                            expires_at
                        )
                        VALUES (
                            %s,
                            %s,
                            NOW() + INTERVAL '2 minutes'
                        )
                        """,
                        (code_hash, user["id"])
                    )

            return RedirectResponse(
                url=f"{EXTENSION_REDIRECT_URI}?code={auth_code}",
                status_code=303
            )

        # Existing frontend login remains unchanged
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


# --------------------------------------------------
# EXCHANGE ONE-TIME CODE FOR EXTENSION JWT
# --------------------------------------------------

@router.post("/extension/exchange")
async def exchange_extension_code(
    request: ExtensionCodeRequest
):

    if not request.code or len(request.code) > 256:
        raise HTTPException(
            status_code=400,
            detail="Invalid authorization code"
        )

    code_hash = hashlib.sha256(
        request.code.encode("utf-8")
    ).hexdigest()

    pool = get_db_pool()

    try:

        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cursor:

                    cursor.execute(
                        """
                        UPDATE extension_auth_codes
                        SET consumed_at = NOW()
                        WHERE code_hash = %s
                          AND consumed_at IS NULL
                          AND expires_at > NOW()
                        RETURNING user_id
                        """,
                        (code_hash,)
                    )

                    result = cursor.fetchone()

        if not result:
            raise HTTPException(
                status_code=401,
                detail=(
                    "Authorization code is invalid, "
                    "expired, or already used"
                )
            )

        user_id = str(result[0])

        access_token = create_extension_token(user_id)

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 1800
        }

    except HTTPException:
        raise

    except Exception:

        logger.exception(
            "Extension authorization code exchange failed"
        )

        raise HTTPException(
            status_code=500,
            detail="Could not authenticate Chrome extension"
        )


# --------------------------------------------------
# EXTENSION PROFILE RETRIEVAL
# --------------------------------------------------

@router.get("/extension/profile")
async def get_extension_profile(
    authorization: str = Header(None)
):

    # Validate Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing authentication token"
        )

    token = authorization.split(" ", 1)[1].strip()

    try:

        user_id = verify_extension_token(token)
        user_uuid = UUID(user_id)

    except (ValueError, TypeError):

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token"
        )

    pool = get_db_pool()

    try:

        with pool.connection() as conn:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                        SELECT
                            id,
                            session_id,
                            profile_data,
                            status,
                            approved_at,
                            created_at
                        FROM verified_profiles
                        WHERE user_id = %s
                        AND status = 'approved'
                        ORDER BY approved_at DESC NULLS LAST, created_at DESC
                        LIMIT 1
                    """,
                    (user_uuid,)
                )

                profile = cursor.fetchone()

        if not profile:
            raise HTTPException(
                status_code=404,
                detail="No student profile found"
            )

        (
            profile_id,
            session_id,
            profile_data,
            status,
            approved_at,
            created_at
        ) = profile

        profile_data = dict(profile_data or {})

        # Never expose full Aadhaar to the extension
        if profile_data.get("aadhaar_number"):
            profile_data["aadhaar_number"] = "XXXX XXXX XXXX"

        return {
            "message": "Student profile retrieved successfully",
            "profile_id": str(profile_id),
            "session_id": str(session_id),
            "status": status,
            "approved_at": (
                approved_at.isoformat()
                if approved_at else None
            ),
            "created_at": created_at.isoformat(),
            "profile_data": profile_data
        }

    except HTTPException:
        raise

    except Exception:

        logger.exception(
            "Extension profile retrieval failed"
        )

        raise HTTPException(
            status_code=500,
            detail="Could not retrieve student profile"
        )


# --------------------------------------------------
# CURRENT WEB USER
# --------------------------------------------------

@router.get("/me")
async def get_current_user(request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated"
        )

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


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@router.post("/logout")
async def logout(request: Request):

    request.session.clear()

    return {
        "message": "Logged out successfully"
    }
