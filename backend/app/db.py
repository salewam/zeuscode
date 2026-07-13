from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()
_connect_args: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    # Avoid "database is locked" under concurrent Studio writes
    _connect_args = {"timeout": 30, "check_same_thread": False}
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=_connect_args,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_sqlite_columns(conn)


async def _ensure_sqlite_columns(conn) -> None:
    """Add new columns on existing SQLite DBs without wiping data."""

    async def cols(table: str) -> set[str]:
        rows = await conn.execute(text(f"PRAGMA table_info({table})"))
        return {r[1] for r in rows.fetchall()}

    user_cols = await cols("users")
    for name, ddl in [
        ("low_balance_alert", "ALTER TABLE users ADD COLUMN low_balance_alert INTEGER DEFAULT 1"),
        (
            "low_balance_threshold_rub",
            "ALTER TABLE users ADD COLUMN low_balance_threshold_rub FLOAT DEFAULT 50.0",
        ),
        ("monthly_budget_rub", "ALTER TABLE users ADD COLUMN monthly_budget_rub FLOAT DEFAULT 0.0"),
        ("model_family", "ALTER TABLE users ADD COLUMN model_family VARCHAR(40) DEFAULT ''"),
    ]:
        if name not in user_cols:
            await conn.execute(text(ddl))

    key_cols = await cols("api_keys")
    for name, ddl in [
        ("budget_rub", "ALTER TABLE api_keys ADD COLUMN budget_rub FLOAT DEFAULT 0.0"),
        ("spent_rub", "ALTER TABLE api_keys ADD COLUMN spent_rub FLOAT DEFAULT 0.0"),
    ]:
        if name not in key_cols:
            await conn.execute(text(ddl))

    proj_cols = await cols("projects")
    for name, ddl in [
        ("brief", "ALTER TABLE projects ADD COLUMN brief TEXT DEFAULT ''"),
        ("workspace_path", "ALTER TABLE projects ADD COLUMN workspace_path VARCHAR(500) DEFAULT ''"),
        ("github_repo", "ALTER TABLE projects ADD COLUMN github_repo VARCHAR(200) DEFAULT ''"),
        (
            "github_default_branch",
            "ALTER TABLE projects ADD COLUMN github_default_branch VARCHAR(120) DEFAULT 'main'",
        ),
        ("github_connected_at", "ALTER TABLE projects ADD COLUMN github_connected_at DATETIME"),
    ]:
        if name not in proj_cols:
            await conn.execute(text(ddl))
