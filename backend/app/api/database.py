import logging
from app.core.database import get_db_pool
from fastapi import APIRouter, HTTPException, Request
router = APIRouter()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@router.get("/test")
def test_database(request: Request):
    # Require an authenticated user.
    user_id = request.session.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Please log in first."
        )

    try:
        pool = get_db_pool()

        with pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                result = cursor.fetchone()

        return {
            "status": "connected",
            "database": result[0],
            "message": "Neon PostgreSQL connection successful"
        }

    except Exception:
        logger.exception("Neon database connection failed")

        raise HTTPException(
            status_code=500,
            detail="Neon database connection failed"
        )
