from psycopg_pool import ConnectionPool
from app.core.config import settings

pool = ConnectionPool(
    conninfo=settings.DATABASE_URL,
    min_size=1,
    max_size=5,
    open=False,
)


def get_db_pool():
    return pool