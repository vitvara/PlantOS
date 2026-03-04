from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Plant Ingestion Service"
    debug: bool = False

    # Database
    database_url: str = "sqlite:///./plant.db"

    # Security
    iot_api_key: str = "supersecretkey"

    # Media
    MEDIA_ROOT: str = "media"

    # OpenAI
    OPENAI_API_KEY: str = ""

    # Ingestion tuning
    max_payload_size: int = 1024  # bytes (for future use)

    # Sensor health check — seconds without data before marking sensor as failed
    sensor_timeout_seconds: int = 660

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Module-level singleton — `from app.core.config import settings` works everywhere.
settings: Settings = get_settings()
