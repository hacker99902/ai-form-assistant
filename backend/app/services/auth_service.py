
import logging

from app.core.database import get_db_pool

logger = logging.getLogger(__name__)


def get_or_create_google_user(user_info: dict) -> dict:
    """
    Find an existing user by Google's stable subject ID,
    or create a new user in Neon PostgreSQL.
    """

    google_id = user_info.get("sub")
    email = user_info.get("email")
    full_name = user_info.get("name")
    picture_url = user_info.get("picture")

    if not google_id or not email:
        raise ValueError("Google user ID or email is missing")

    if user_info.get("email_verified") is not True:
        raise ValueError("Google email is not verified")

    pool = get_db_pool()

    with pool.connection() as conn:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO users (
                    google_id,
                    email,
                    full_name,
                    picture_url
                )
                VALUES (%s, %s, %s, %s)

                ON CONFLICT (google_id)
                DO UPDATE SET
                    email = EXCLUDED.email,
                    full_name = EXCLUDED.full_name,
                    picture_url = EXCLUDED.picture_url,
                    updated_at = NOW()

                RETURNING
                    id,
                    google_id,
                    email,
                    full_name,
                    picture_url,
                    created_at
                """,
                (
                    google_id,
                    email,
                    full_name,
                    picture_url
                )
            )

            user = cursor.fetchone()

    if not user:
        raise RuntimeError("Could not create or retrieve Google user")

    return {
        "id": str(user[0]),
        "google_id": user[1],
        "email": user[2],
        "full_name": user[3],
        "picture_url": user[4],
        "created_at": user[5].isoformat()
    }
