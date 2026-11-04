
from uuid import UUID

from psycopg.types.json import Jsonb

from app.core.database import get_db_pool
from app.core.encryption import encrypt_value


PROFILE_ID = UUID("3260eb5d-fe65-459d-81c7-cded23762ea4")


def migrate():

    pool = get_db_pool()

    try:
        # Open the connection pool because this script runs independently
        # of FastAPI's application lifespan.
        pool.open(wait=True)

        with pool.connection() as conn:
            with conn.cursor() as cursor:

                # 1. Retrieve the existing profile
                cursor.execute(
                    """
                    SELECT profile_data
                    FROM verified_profiles
                    WHERE id = %s
                    FOR UPDATE
                    """,
                    (PROFILE_ID,)
                )

                row = cursor.fetchone()

                if not row:
                    raise ValueError("Profile not found")

                profile_data = dict(row[0])

                # 2. Get Aadhaar value
                aadhaar = profile_data.get("aadhaar_number")

                if not aadhaar:
                    raise ValueError("Aadhaar field not found")

                # 3. Avoid encrypting an already encrypted value
                if aadhaar.startswith("fernet:v1:"):
                    print("Aadhaar is already encrypted.")
                    return

                # 4. Encrypt existing Aadhaar
                encrypted = encrypt_value(aadhaar)

                profile_data["aadhaar_number"] = (
                    "fernet:v1:" + encrypted
                )

                # 5. Update profile JSONB
                cursor.execute(
                    """
                    UPDATE verified_profiles
                    SET profile_data = %s
                    WHERE id = %s
                    """,
                    (Jsonb(profile_data), PROFILE_ID)
                )

        print("Profile Aadhaar encryption migration successful.")

    finally:
        # Close the standalone connection pool
        pool.close()


if __name__ == "__main__":
    migrate()
