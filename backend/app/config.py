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
    DEFAULT_MODEL: str = "zeuscode"
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
    TELEGRAM_BOT_TOKEN: str = ""
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # --- Fusion Epic 4: flags (AD-9) + runtime budgets (AD-12 / FR29) ---
    # Shadow: log candidate Path vs baseline_id; serve baseline decision.
    FUSION_SHADOW_MODE: bool = False
    # Canary cohort percent 0..100 (stable hash of user_id).
    FUSION_CANARY_PCT: float = 0.0
    # Global Kill-Switch → clamp serving Path to FAST.
    FUSION_KILL_SWITCH: bool = False
    # Empty → derived from policy+lexicon_v1+panel (see fusion.metrics.compute_baseline_id).
    FUSION_BASELINE_ID: str = ""
    # Sticky session TTL
    FUSION_STICKY_TTL_HOURS: float = 24.0
    # Runtime budgets — presence required for Path ship (numeric freeze before canary 100%).
    # Wall-clock budget for a Fusion request (long HTML/sites need headroom).
    FUSION_GLOBAL_TIMEOUT_S: float = 600.0
    FUSION_PANEL_CONCURRENCY: int = 3
    FUSION_RACE_CONCURRENCY: int = 3
    FUSION_RETRY_MAX: int = 2
    FUSION_RETRY_BACKOFF_S: float = 0.4
    FUSION_THINKING_KEEPALIVE_S: float = 8.0
    FUSION_RATE_LIMIT_RPM: int = 60
    FUSION_OVERFLOW_CONTEXT_CHARS: int = 120_000
    FUSION_DISASTER_ERROR_CODE: str = "fusion_disaster"
    # Publish regression gate (FR26): when true, publish path runs badge/HTML check.
    FUSION_PUBLISH_REGRESSION_GATE: bool = True
    # Output ceiling for chat/agents. Claude API requires max_tokens — we set the
    # highest practical ceiling so tasks are not cut mid-page. 0 = omit when optional.
    UPSTREAM_MAX_OUTPUT_TOKENS: int = 65536
    # Kie Claude gateway: Internal error on max_tokens >= 8192 for long HTML (live
    # probe 2026-07-24: 7680 OK, 8192 FAIL; support Motohaus used 4096 + thinkingFlag).
    UPSTREAM_CLAUDE_MAX_TOKENS: int = 7680
    # Kie Claude Messages hybrid: required for Fable/Opus stability (support 2026-07).
    UPSTREAM_CLAUDE_THINKING_FLAG: bool = True
    # Fusion panel agent answers (FULL/RACE/CASCADE) use this, not tiny 4k/8k caps.
    FUSION_AGENT_MAX_TOKENS: int = 65536
    # UI Crew: Author(max power) → Critics(+web) → Author revise (not 3-way HTML mash).
    FUSION_UI_CREW_ENABLED: bool = True
    # Retries for the strongest author before failover to weaker panel models.
    FUSION_UI_AUTHOR_RETRIES: int = 2
    # Optional Tavily for critic web search (empty → DuckDuckGo HTML fallback).
    TAVILY_API_KEY: str = ""
    WEB_RESEARCH_ENABLED: bool = True
    # Standard pack: 3 reference sites for critics (still compressed for tokens).
    WEB_RESEARCH_MAX_RESULTS: int = 3
    WEB_RESEARCH_MAX_FETCH: int = 3
    WEB_REFS_CHAR_BUDGET: int = 4200
    WEB_REF_EXTRACT_CHARS: int = 850
    # DJARVIS browser-daemon (optional). Socket preferred; CLI fallback if socket down.
    WEB_BROWSER_ENABLED: bool = True
    WEB_BROWSER_SOCK: str = "/run/browser-daemon/daemon.sock"
    JARVIS_BROWSER_CLI: str = "/usr/local/bin/browser-cli.py"
    # Thin-fetch escalate + forced live-competitor peeks.
    WEB_BROWSER_MAX_PAGES: int = 2
    WEB_BROWSER_LIVE_COMPETITORS: int = 2
    WEB_BROWSER_TIMEOUT_S: float = 18.0
    WEB_BROWSER_FETCH_CHARS: int = 2200
    # Product usage analytics (Cursor/API events → DB + data/usage/*.jsonl)
    USAGE_ANALYTICS_ENABLED: bool = True
    USAGE_LOG_DIR: str = ""  # empty → <repo>/data/usage
    # Optional bearer for GET /admin/usage/* (if empty, endpoint disabled)
    USAGE_ADMIN_TOKEN: str = ""
    # Studio/agent skill packs (agent_skills/* + media packs + golden etalon).
    # False = agents get short role prompt only, no disk skill dump.
    AGENT_SKILLS_ENABLED: bool = False

    @property
    def upstream_api_key(self) -> str:
        return self.UPSTREAM_API_KEY.strip()

    @property
    def upstream_base_url(self) -> str:
        return self.UPSTREAM_BASE_URL.strip().rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
