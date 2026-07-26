import secrets
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    telegram_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True, nullable=True)
    telegram_username: Mapped[str] = mapped_column(String(120), default="", index=True)
    telegram_first_name: Mapped[str] = mapped_column(String(120), default="")
    telegram_last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    balance_usd: Mapped[float] = mapped_column(Float, default=0.0)  # stores RUB
    low_balance_alert: Mapped[int] = mapped_column(Integer, default=1)
    low_balance_threshold_rub: Mapped[float] = mapped_column(Float, default=50.0)
    monthly_budget_rub: Mapped[float] = mapped_column(Float, default=0.0)  # 0 = off
    # "" = all models; "gemini" = Gemini family only (catalog + API + Studio)
    model_family: Mapped[str] = mapped_column(String(40), default="")
    # Fusion product mode: simple | power | custom (TG / cabinet / Cursor pref)
    fusion_pref: Mapped[str] = mapped_column(String(20), default="power")
    # JSON list of model ids when fusion_pref=custom, e.g. ["deepseek-chat","gemini-3.1-pro",…]
    fusion_models: Mapped[str] = mapped_column(Text, default="")
    # Effort level: low | normal | high | max (FR5 / FR23); zeus.effort overrides
    fusion_effort: Mapped[str] = mapped_column(String(20), default="normal")
    # Kill-Switch: 1 → force FAST Path (AD-9); zeus.kill_switch may also set per-request
    fusion_kill_switch: Mapped[int] = mapped_column(Integer, default=0)
    # TG Mini App onboarding «Первый результат» completed
    onboarding_done: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user")
    usage_logs: Mapped[list["UsageLog"]] = relationship(back_populates="user")
    projects: Mapped[list["Project"]] = relationship(back_populates="user")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="default")
    key_prefix: Mapped[str] = mapped_column(String(16), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    budget_rub: Mapped[float] = mapped_column(Float, default=0.0)  # 0 = без лимита
    spent_rub: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship(back_populates="api_keys")

    @staticmethod
    def generate_raw() -> str:
        return "zeus_" + secrets.token_urlsafe(32)


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True)
    model: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(40), default="solo")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_upstream_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cost_user_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    meta: Mapped[str] = mapped_column(Text, default="")

    user: Mapped[User] = relationship(back_populates="usage_logs")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="Новый проект")
    brief: Mapped[str] = mapped_column(Text, default="")
    workspace_path: Mapped[str] = mapped_column(String(500), default="")
    github_repo: Mapped[str] = mapped_column(String(200), default="")  # owner/name
    github_default_branch: Mapped[str] = mapped_column(String(120), default="main")
    github_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="projects")
    chats: Mapped[list["Chat"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class GitHubAccount(Base):
    __tablename__ = "github_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    login: Mapped[str] = mapped_column(String(120), default="")
    access_token_enc: Mapped[str] = mapped_column(Text, default="")
    scopes: Mapped[str] = mapped_column(String(255), default="")
    avatar_url: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="Чат")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="chats")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    mode: Mapped[str] = mapped_column(String(40), default="solo")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_user_usd: Mapped[float] = mapped_column(Float, default=0.0)
    meta: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    chat: Mapped[Chat] = relationship(back_populates="messages")


class Artifact(Base):
    """Typed project artifacts — bridge to future workspace file tree."""

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("chats.id"), nullable=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), default="code")  # plan|code|checklist|diff-candidate
    role: Mapped[str] = mapped_column(String(40), default="")
    path: Mapped[str] = mapped_column(String(400), default="/")
    title: Mapped[str] = mapped_column(String(200), default="")
    language: Mapped[str] = mapped_column(String(40), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="artifacts")


class FusionStickySession(Base):
    """Sticky Leader/stack only (AD-7). Path is never authoritative here."""

    __tablename__ = "fusion_sticky_sessions"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    leader: Mapped[str] = mapped_column(String(120), default="")
    stack_json: Mapped[str] = mapped_column(Text, default="[]")
    phase_meta_json: Mapped[str] = mapped_column(Text, default="{}")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FusionFeedbackEvent(Base):
    """👍/👎/regen ingest with routing context — no Elo writeback (FR24)."""

    __tablename__ = "fusion_feedback_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    event: Mapped[str] = mapped_column(String(20), default="")  # up | down | regen
    path: Mapped[str] = mapped_column(String(20), default="")
    phase: Mapped[str] = mapped_column(String(40), default="")
    leader: Mapped[str] = mapped_column(String(120), default="")
    routed_by: Mapped[str] = mapped_column(String(80), default="")
    model_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProductUsageEvent(Base):
    """Product analytics: every API/chat request people make (for owner insights)."""

    __tablename__ = "product_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(24), default="")
    event: Mapped[str] = mapped_column(String(40), default="chat_request", index=True)
    source: Mapped[str] = mapped_column(String(40), default="api")  # api|tg|cabinet
    model: Mapped[str] = mapped_column(String(120), default="")
    stream: Mapped[int] = mapped_column(Integer, default=0)
    session_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    prompt_preview: Mapped[str] = mapped_column(Text, default="")
    path: Mapped[str] = mapped_column(String(20), default="")
    policy_path: Mapped[str] = mapped_column(String(20), default="")
    leader: Mapped[str] = mapped_column(String(120), default="")
    routed_by: Mapped[str] = mapped_column(String(80), default="")
    trace_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_rub: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str] = mapped_column(Text, default="")
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
