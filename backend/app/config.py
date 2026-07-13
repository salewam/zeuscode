from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[2]
_ENV = _ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV) if _ENV.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "ZeusCode"
    UPSTREAM_API_KEY: str = ""
    UPSTREAM_BASE_URL: str = ""
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 72
    MARKUP: float = 1.5
    # 1.5 × 92.016 ≈ 138.024 — same pass-through as Polza Gemini Flash
    USD_RUB: float = 92.016
    TRIAL_RUB: float = 90.0
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/onestack.db"
    HOST: str = "127.0.0.1"
    PORT: int = 8080
    DEFAULT_MODEL: str = "gemini-2.5-flash"
    ULTRA_MODEL: str = "gemini-2.5-flash"
    # Code agents = Flash; synth+reviewer = judge (stronger, fewer calls)
    STUDIO_JUDGE_MODEL: str = "gemini-2.5-pro"
    STUDIO_PREMIUM_JUDGE_MODEL: str = "claude-sonnet-4-5"
    # GitHub OAuth (Studio)
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = "http://127.0.0.1:8080/github/callback"
    APP_PUBLIC_URL: str = "http://127.0.0.1:8080"
    TOKEN_ENCRYPT_KEY: str = ""
    FORK_MODELS: str = "gemini-2.5-flash,gemini-2.5-flash,gemini-2.5-flash"

    @property
    def upstream_api_key(self) -> str:
        return self.UPSTREAM_API_KEY.strip()

    @property
    def upstream_base_url(self) -> str:
        return self.UPSTREAM_BASE_URL.strip().rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
