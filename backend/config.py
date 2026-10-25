from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    github_token: str | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    github_api_version: str = "2026-03-10"
    github_api_base: str = "https://api.github.com"
    allowed_origins: str = "http://localhost:5173"
    demo_mode: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
