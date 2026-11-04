from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    DATABASE_URL: str

    OPENROUTER_API_KEY: str
    OPENROUTER_MODEL: str = "openrouter/free"

    GROQ_API_KEY: str
    GROQ_MODEL: str = "openai/gpt-oss-20b"

    FIELD_ENCRYPTION_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()