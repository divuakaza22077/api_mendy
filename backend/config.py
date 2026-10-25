from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    github_token: str | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    github_api_version: str = "2026-03-10"
    github_api_base: str = "https://api.github.com"
    api_key: str | None = Field(default=None, validation_alias="API_MEND_API_KEY")
    allowed_origins: str = "http://localhost:5173"
    demo_mode: bool = False
    allow_github_writes: bool = False
    allowed_repositories: str = ""
    max_scan_files: int = Field(default=500, ge=1, le=5000)
    max_scan_bytes: int = Field(default=5_000_000, ge=100_000, le=50_000_000)
    max_request_bytes: int = Field(default=1_000_000, ge=1_024, le=10_000_000)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10_000)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @field_validator("github_api_base")
    @classmethod
    def validate_github_api_base(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in {"api.github.com"}:
            raise ValueError("GITHUB_API_BASE must be https://api.github.com")
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError("GITHUB_API_BASE must not contain credentials, path, query, or fragment")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_write_configuration(self) -> "Settings":
        if self.allow_github_writes and not self.api_key:
            raise ValueError("API_MEND_API_KEY is required when ALLOW_GITHUB_WRITES=true")
        if self.allow_github_writes and not self.github_token:
            raise ValueError("GITHUB_TOKEN is required when ALLOW_GITHUB_WRITES=true")
        return self

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def repository_allowlist(self) -> set[str]:
        return {
            repository.strip().lower()
            for repository in self.allowed_repositories.split(",")
            if repository.strip()
        }

    def can_write_repository(self, owner: str, repo: str) -> bool:
        return self.allow_github_writes and f"{owner}/{repo}".lower() in self.repository_allowlist


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
