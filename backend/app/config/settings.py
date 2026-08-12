from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the project root .env regardless of the current working directory
# the app is launched from (e.g. `cd backend && uvicorn app.main:app`).
# settings.py -> config -> app -> backend -> <project root>
BASE_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    gemini_api_key: str
    database_url: str
    cors_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

settings = Settings()