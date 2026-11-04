from psycopg_pool import ConnectionPool
from app.core.config import settings

pool = ConnectionPool(
    conninfo=settings.DATABASE_URL,

    min_size=1,
    max_size=5,

    # Check pooled connections before reusing them.
    check=ConnectionPool.check_connection,

    # PostgreSQL connection settings.
    kwargs={
        "connect_timeout": 15,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    },

    # Pool management.
    timeout=30,
    reconnect_timeout=300,
    max_lifetime=1800,
    max_idle=300,

    open=False,
)


def get_db_pool():
    return pool
