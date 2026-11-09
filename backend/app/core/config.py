from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    DATABASE_URL: str

    OPENROUTER_API_KEY: str
    OPENROUTER_MODEL: str = "openrouter/free"
    ENABLE_LOCAL_AADHAAR_FILL: bool = False
    GROQ_API_KEY: str
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    FIELD_ENCRYPTION_KEY: str
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    SESSION_SECRET: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()