from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized application settings, loaded from environment variables / .env file.
    """

    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/itg_career"

    SECRET_KEY: str = "change-this-to-a-long-random-secret-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # AI resume analysis (see app/ai_service.py). Leave ANTHROPIC_API_KEY empty to
    # fall back to a deterministic skill-overlap heuristic instead of a real LLM call.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5-20250929"
    RESUME_TEXT_MAX_CHARS: int = 15000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
