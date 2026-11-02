
from fastapi import APIRouter, HTTPException
from app.core.supabase import get_supabase

router = APIRouter()


@router.get("/test")
async def test_database():
    try:
        db = get_supabase()

        response = (
            db.table("processing_sessions")
            .select("id")
            .limit(1)
            .execute()
        )

        return {
            "status": "connected",
            "database": "Supabase PostgreSQL",
            "message": "Database connection successful"
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Supabase database connection failed"
        )
