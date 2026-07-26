"""Create / rotate ZeusCode accounts bound to a Telegram user id."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_api_key, hash_password
from app.config import get_settings
from app.models import ApiKey, User
from app.routers.keys import public_v1_base_url

settings = get_settings()


def _tg_email(telegram_id: int) -> str:
    return f"tg{telegram_id}@users.zeuscode.ru"


def _tg_password() -> str:
    return secrets.token_urlsafe(24)


def _clean_username(username: str | None) -> str:
    return (username or "").strip().lstrip("@")[:120]


def _clean_name(name: str | None) -> str:
    return (name or "").strip()[:120]


async def _create_key(db: AsyncSession, user: User, name: str = "telegram") -> tuple[ApiKey, str]:
    raw = ApiKey.generate_raw()
    key = ApiKey(
        user_id=user.id,
        name=name[:120],
        key_prefix=raw[:12],
        key_hash=hash_api_key(raw),
        budget_rub=0.0,
        spent_rub=0.0,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return key, raw


_LAST_SEEN_MIN_SECONDS = 300  # don't rewrite last_seen on every UI ping


def _touch_profile(
    user: User,
    *,
    username: str | None = None,
    first_name: str | None = None,
) -> bool:
    """Update stored TG profile fields. Returns True if something changed."""
    changed = False
    uname = _clean_username(username)
    fname = _clean_name(first_name)
    if uname and getattr(user, "telegram_username", "") != uname:
        user.telegram_username = uname
        changed = True
    if fname and getattr(user, "telegram_first_name", "") != fname:
        user.telegram_first_name = fname
        changed = True
    now = datetime.now(timezone.utc)
    last = getattr(user, "telegram_last_seen_at", None)
    if last is None:
        user.telegram_last_seen_at = now
        changed = True
    else:
        try:
            # DB may return naive UTC
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if (now - last).total_seconds() >= _LAST_SEEN_MIN_SECONDS:
                user.telegram_last_seen_at = now
                changed = True
        except Exception:  # noqa: BLE001
            user.telegram_last_seen_at = now
            changed = True
    return changed


async def ensure_telegram_user(
    db: AsyncSession,
    telegram_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
) -> tuple[User, str | None, bool]:
    """
    Find or create user by telegram_id. Refreshes username / first_name;
    last_seen throttled (avoids commit storm from Mini App /tg/events).

    Returns (user, raw_key_or_none, is_new_user).
    Raw key is only returned when a brand-new account (+ first key) is created.
    """
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        if _touch_profile(user, username=username, first_name=first_name):
            await db.commit()
            await db.refresh(user)
        return user, None, False

    email = _tg_email(telegram_id)
    conflict = await db.execute(select(User).where(User.email == email))
    existing = conflict.scalar_one_or_none()
    if existing:
        existing.telegram_id = telegram_id
        _touch_profile(existing, username=username, first_name=first_name)
        await db.commit()
        await db.refresh(existing)
        return existing, None, False

    label = _clean_username(username) or str(telegram_id)
    user = User(
        email=email,
        password_hash=hash_password(_tg_password()),
        telegram_id=telegram_id,
        telegram_username=_clean_username(username),
        telegram_first_name=_clean_name(first_name),
        telegram_last_seen_at=datetime.now(timezone.utc),
        # Telegram: без пробного баланса — старт с нуля
        balance_usd=0.0,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    _, raw = await _create_key(db, user, name=f"tg:{label}"[:120])
    try:
        from app.usage_analytics import log_user_action

        await log_user_action(
            db,
            event="user_created",
            user=user,
            source="tg",
            meta={"via": "telegram", "key_name": f"tg:{label}"[:120]},
        )
    except Exception:  # noqa: BLE001
        pass
    return user, raw, True


async def active_key_prefix(db: AsyncSession, user: User) -> str | None:
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == user.id, ApiKey.revoked == 0)
        .order_by(ApiKey.id.desc())
    )
    key = result.scalars().first()
    return key.key_prefix if key else None


async def rotate_telegram_key(db: AsyncSession, user: User) -> tuple[str, str]:
    """Revoke previous telegram keys and create a fresh one. Returns (raw, prefix)."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked == 0)
    )
    for key in result.scalars().all():
        key.revoked = 1
    await db.commit()
    label = (getattr(user, "telegram_username", None) or "").strip() or str(
        getattr(user, "telegram_id", "") or "telegram"
    )
    key, raw = await _create_key(db, user, name=f"tg:{label}"[:120])
    return raw, key.key_prefix


def format_creds(raw_key: str) -> str:
    base = public_v1_base_url()
    return (
        f"<b>Ключ</b> (скопируй сейчас):\n"
        f"<code>{raw_key}</code>\n\n"
        f"<b>Адрес</b>:\n<code>{base}</code>\n\n"
        f"Вставь в своё окно. Модель в настройках: <code>zeuscode</code> "
        f"(в чате это ZeusCode).\n"
        f"Обучение и модели — в приложении бота."
    )
