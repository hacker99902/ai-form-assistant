import logging

from fastapi import APIRouter, HTTPException
from app.core.database import get_db_pool

router = APIRouter()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@router.get("/test")
def test_database():
    try:
        pool = get_db_pool()

        with pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT current_database(), version()
                """)

                result = cursor.fetchone()

        return {
            "status": "connected",
            "database": result[0],
            "message": "Neon PostgreSQL connection successful"
        }

    except Exception as exc:
        logger.exception("Neon database connection failed")

        raise HTTPException(
            status_code=500,
            detail=f"Neon connection failed: {type(exc).__name__}"
        ) from exc