"""ZeusCode Telegram bot — welcome + Mini App + optional chat."""

from __future__ import annotations

import asyncio
import json
import logging
import sys

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.fusion import (
    DEFAULT_PRODUCT_MODE,
    normalize_product_mode,
    parse_fusion_models_json,
)
from app.telegram_accounts import (
    active_key_prefix,
    ensure_telegram_user,
    format_creds,
    rotate_telegram_key,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("zeuscode.bot")
settings = get_settings()


async def _log_action(
    user,
    event: str,
    *,
    prompt_preview: str = "",
    meta: dict | None = None,
    db=None,
    latency_ms: int = 0,
    error: str = "",
    status_code: int = 200,
) -> None:
    """Best-effort product analytics for bot actions."""
    try:
        from app.usage_analytics import log_user_action

        kwargs = dict(
            event=event,
            user=user,
            source="tg_bot",
            prompt_preview=prompt_preview,
            latency_ms=latency_ms,
            error=error,
            status_code=status_code,
            meta=meta,
        )
        if db is not None:
            await log_user_action(db, **kwargs)
            return
        async with SessionLocal() as session:
            await log_user_action(session, **kwargs)
    except Exception:  # noqa: BLE001
        log.debug("bot analytics failed", exc_info=True)


def normalize_effort(raw: str | None) -> str:
    try:
        from app.fusion.metrics import normalize_effort as _ne

        return _ne(raw)
    except Exception:  # noqa: BLE001
        v = (raw or "normal").strip().lower()
        return v if v in ("low", "normal", "high", "max") else "normal"


MODE_LABELS = {
    "standard": "ZeusCode",
    "manual": "Ручной",
    "combo2": "Ручной",  # legacy → manual; Combo-2 removed
    "combo3": "ZeusCode",
    "simple": "Ручной",
    "power": "ZeusCode",
    "custom": "Ручной",
}

_PAGE_SIZE = 8
_BASE = settings.APP_PUBLIC_URL.rstrip("/") + "/v1"


def miniapp_url(view: str = "") -> str:
    """Mini App URL. Use ?view= — Telegram often strips #hash from WebAppInfo."""
    base = settings.APP_PUBLIC_URL.rstrip("/") + "/tg"
    v = (view or "").strip().lstrip("#").lstrip("/").lower()
    if v in ("learn", "onboarding"):
        return f"{base}?view=learn"
    if v in ("fusion", "models", "mode"):
        return f"{base}?view=fusion"
    if v in ("subscription", "sub", "plan", "limits", "usage"):
        return f"{base}?view=subscription"
    return base


def _webapp_info(view: str = "") -> WebAppInfo:
    return WebAppInfo(url=miniapp_url(view))


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Начать обучение",
                    web_app=_webapp_info("learn"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Открыть модели",
                    web_app=_webapp_info("fusion"),
                )
            ],
        ]
    )


def _hello_name(message: Message) -> str:
    """Короткое имя для обращения — без хвостов вроде «| ИИ-агенты»."""
    u = message.from_user
    if not u:
        return ""
    name = (u.first_name or "").strip()
    if "|" in name:
        name = name.split("|", 1)[0].strip()
    if "—" in name:
        name = name.split("—", 1)[0].strip()
    if name and len(name) <= 40:
        return name
    if u.username:
        return u.username
    return ""


# Telegram hard limit 4096; keep margin for entities / UTF-16 quirks.
_TG_MSG_LIMIT = 3800


def _split_tg_text(text: str, limit: int = _TG_MSG_LIMIT) -> list[str]:
    """Split long answers on paragraph / line boundaries."""
    s = (text or "").strip() or "…"
    if len(s) <= limit:
        return [s]
    parts: list[str] = []
    rest = s
    while rest:
        if len(rest) <= limit:
            parts.append(rest)
            break
        cut = rest.rfind("\n\n", 0, limit)
        if cut < limit // 3:
            cut = rest.rfind("\n", 0, limit)
        if cut < limit // 3:
            cut = limit
        chunk = rest[:cut].rstrip()
        parts.append(chunk or rest[:limit])
        rest = rest[cut:].lstrip()
    return parts or ["…"]


async def _deliver_answer(
    message: Message,
    text: str,
    *,
    status_msg: Message | None = None,
    reply_markup=None,
    parse_mode: str = "HTML",
) -> None:
    """
    Надёжная доставка ответа (без «стрима» через edit).
    Старый typewriter ронял HTML mid-edit / flood — ответ «ложился».
    """
    parts = _split_tg_text(text)
    first = parts[0]
    rest = parts[1:]

    async def _edit(msg: Message, body: str, *, markup=None) -> bool:
        try:
            await msg.edit_text(body, parse_mode=parse_mode, reply_markup=markup)
            return True
        except Exception:  # noqa: BLE001
            try:
                await msg.edit_text(body, reply_markup=markup)
                return True
            except Exception:  # noqa: BLE001
                return False

    async def _send(body: str, *, markup=None) -> None:
        try:
            await message.answer(body, parse_mode=parse_mode, reply_markup=markup)
        except Exception:  # noqa: BLE001
            await message.answer(body, reply_markup=markup)

    if status_msg is not None:
        ok = await _edit(status_msg, first, markup=reply_markup if not rest else None)
        if not ok:
            try:
                await status_msg.delete()
            except Exception:  # noqa: BLE001
                pass
            await _send(first, markup=reply_markup if not rest else None)
    else:
        await _send(first, markup=reply_markup if not rest else None)

    for i, part in enumerate(rest):
        last = i == len(rest) - 1
        await _send(part, markup=reply_markup if last else None)


HELP = (
    "<b>ZeusCode</b> — кодинг в связке топовых нейросетей.\n\n"
    "Обучение, ключ и модели — в приложении.\n"
    "В чат напиши вопрос — советник подскажет режим и нейронки.\n\n"
    "/start — приветствие\n"
    "/learn — обучение\n"
    "/mode — модели\n"
    "/balance — баланс\n"
    "/help — справка"
)


def _mode_keyboard(current: str) -> InlineKeyboardMarkup:
    """Legacy inline (старые сообщения). Новый вход — только Mini App."""
    rows = [
        [
            InlineKeyboardButton(
                text="Открыть модели",
                web_app=_webapp_info("fusion"),
            )
        ],
        [
            InlineKeyboardButton(
                text="Начать обучение",
                web_app=_webapp_info("learn"),
            )
        ],
    ]
    for mid, title in (
        ("standard", "ZeusCode"),
        ("manual", "Ручной"),
    ):
        mark = " ✓" if mid == current else ""
        rows.append(
            [InlineKeyboardButton(text=f"{title}{mark}", callback_data=f"fm:{mid}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _coding_chat_models(user=None) -> list[tuple[str, str]]:
    from app.catalog import public_catalog
    from app.fusion import is_fusion_model
    from app.model_policy import filter_catalog_for_user

    rows = filter_catalog_for_user(user, public_catalog())
    out: list[tuple[str, str]] = []
    for m in rows:
        mid = str(m.get("id") or "")
        if not m.get("ready"):
            continue
        if (m.get("modality") or "chat") != "chat":
            continue
        if m.get("family") in ("studio", "ultra", "fusion"):
            continue
        if mid.startswith("studio-") or mid == "ultra-mode" or is_fusion_model(mid):
            continue
        title = (m.get("title") or mid).strip()
        if len(title) > 36:
            title = title[:34] + "…"
        out.append((mid, title))
    return out


def _custom_models_keyboard(
    selected: list[str], *, page: int = 0, user=None
) -> InlineKeyboardMarkup:
    picks = _coding_chat_models(user)
    if not picks:
        picks = [("deepseek-chat", "DeepSeek Chat")]
    pages = max(1, (len(picks) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(int(page), pages - 1))
    chunk = picks[page * _PAGE_SIZE : (page + 1) * _PAGE_SIZE]

    rows: list[list[InlineKeyboardButton]] = []
    for mid, title in chunk:
        mark = "✓ " if mid in selected else ""
        rows.append(
            [InlineKeyboardButton(text=f"{mark}{title}", callback_data=f"fc:t:{mid}")]
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="« Назад", callback_data=f"fc:page:{page - 1}")
        )
    nav.append(
        InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data=f"fc:page:{page}")
    )
    if page < pages - 1:
        nav.append(
            InlineKeyboardButton(text="Ещё »", callback_data=f"fc:page:{page + 1}")
        )
    rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(
                text=f"✅ Готово ({len(selected)}/3)", callback_data="fc:done"
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="← Назад", callback_data="fm:back")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _sync_balance(user) -> tuple[float, bool]:
    """Только локальный баланс пользователя. Без подтягивания общего upstream."""
    return round(float(user.balance_usd or 0), 2), False


def _pref_summary(user) -> str:
    mode = normalize_product_mode(getattr(user, "fusion_pref", None)) or DEFAULT_PRODUCT_MODE
    label = MODE_LABELS.get(mode, mode)
    models = parse_fusion_models_json(getattr(user, "fusion_models", None))
    if models:
        return f"Режим: <b>{label}</b> · {len(models)} модели · {' + '.join(models[:3])}"
    return f"Режим: <b>{label}</b> · выбери модели в приложении"


def _welcome_text(*, name: str, balance: float, is_new: bool) -> str:
    """Элегантное приветствие из файла достоинств. Ключ — только в приложении."""
    bal = f"{balance:g}" if balance == int(balance) else f"{balance:.1f}"
    who = f"<b>{name}</b>" if name else "дорогой пользователь"
    tail_new = (
        "Нажми <b>Начать обучение</b> — покажем, куда вставить ключ.\n"
        "Или <b>Открыть модели</b> — выбрать силу нейронок."
        if is_new
        else (
            "Ниже — обучение и модели.\n"
            "Или просто напиши сюда вопрос. Подскажу, что взять."
        )
    )
    return (
        f"Приветствую тебя, {who}.\n\n"
        f"<b>ZeusCode</b> — платформа для кодинга в связке топовых нейросетей.\n"
        f"Один ключ. Несколько сильных моделей. Ты ставишь задачу — они делают работу.\n\n"
        f"<b>Зачем это тебе</b>\n"
        f"• быстрее собирать продукт — без прыжков между сервисами\n"
        f"• под задачу: лёгкий режим или максимальный стек\n"
        f"• обучение, ключ и модели — в одном приложении\n"
        f"• в чате рядом советник: что взять и куда вставить\n\n"
        f"Твой баланс: <b>{bal} ₽</b>\n\n"
        f"{tail_new}"
    )


async def cmd_start(message: Message) -> None:
    if not message.from_user:
        return
    name = _hello_name(message)
    tg_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    async with SessionLocal() as db:
        user, raw, is_new = await ensure_telegram_user(
            db, tg_id, username=username, first_name=first_name
        )
        balance, _synced = await _sync_balance(user)
        await db.commit()
        await _log_action(
            user,
            "bot_start",
            db=db,
            meta={"is_new": bool(is_new or raw), "balance_rub": balance},
        )
        text = _welcome_text(
            name=name,
            balance=balance,
            is_new=bool(is_new or raw),
        )
    await _deliver_answer(message, text, reply_markup=_main_keyboard())


async def cmd_learn(message: Message) -> None:
    if not message.from_user:
        return
    name = _hello_name(message)
    who = name or "дорогой пользователь"
    async with SessionLocal() as db:
        user, _, _ = await ensure_telegram_user(
            db,
            message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        await db.commit()
        await _log_action(user, "bot_command", db=db, meta={"command": "/learn"})
    text = (
        f"Приветствую тебя, <b>{who}</b>.\n\n"
        "Обучение — в приложении: куда вставить ключ, какое окно выбрать, первая задача.\n"
        "Коротко. По шагам. Без лишней теории."
    )
    await _deliver_answer(message, text)


async def cmd_mode(message: Message) -> None:
    if not message.from_user:
        return
    name = _hello_name(message)
    async with SessionLocal() as db:
        user, _, _ = await ensure_telegram_user(
            db,
            message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        await db.commit()
        await _log_action(user, "bot_command", db=db, meta={"command": "/mode"})
        pref = _pref_summary(user)
    who = name or "дорогой пользователь"
    text = (
        f"<b>{who}</b>, модели и режимы — в приложении (кнопка «Модели» внизу).\n\n"
        f"{pref}\n\n"
        "Там же можно собрать свой набор нейронок."
    )
    await message.answer(text, parse_mode="HTML")


async def on_mode_callback(query: CallbackQuery) -> None:
    if not query.from_user or not query.data:
        return
    data = query.data
    if data == "fm:menu":
        await query.answer()
        if query.message:
            await query.message.answer(
                "Модели удобнее в приложении — кнопка «Модели» внизу экрана."
            )
        return
    if data == "fm:back":
        await query.answer()
        async with SessionLocal() as db:
            user, _, _ = await ensure_telegram_user(
                db,
                query.from_user.id,
                username=query.from_user.username,
                first_name=query.from_user.first_name,
            )
            await db.commit()
            mode = (
                normalize_product_mode(getattr(user, "fusion_pref", None))
                or DEFAULT_PRODUCT_MODE
            )
        if query.message:
            await query.message.edit_text(
                "Режим:\n" + _pref_summary(user),
                parse_mode="HTML",
                reply_markup=_mode_keyboard(mode),
            )
        return
    if data.startswith("fm:") and data[3:] in (
        "standard",
        "manual",
        "combo2",
        "combo3",
        "simple",
        "power",
        "custom",
    ):
        mode = data[3:]
        async with SessionLocal() as db:
            user, _, _ = await ensure_telegram_user(
                db,
                query.from_user.id,
                username=query.from_user.username,
                first_name=query.from_user.first_name,
            )
            from app.fusion.combo import resolve_stack_definition, ComboConfigError

            models = parse_fusion_models_json(getattr(user, "fusion_models", None))
            try:
                definition = resolve_stack_definition(
                    mode, models, allow_standard_fill=True
                )
                user.fusion_pref = definition.product_mode
                user.fusion_models = json.dumps(list(definition.models), ensure_ascii=False)
                mode = definition.product_mode
            except ComboConfigError:
                user.fusion_pref = mode
            await db.commit()
            await db.refresh(user)
            await _log_action(
                user, "pref_change", db=db, meta={"mode": mode, "via": "bot_callback"}
            )
        await query.answer(f"Режим: {MODE_LABELS.get(mode, mode)}")
        models = parse_fusion_models_json(getattr(user, "fusion_models", None))
        if mode == "manual":
            n = len(_coding_chat_models(user))
            if query.message:
                await query.message.edit_text(
                    f"<b>Ручной</b> — отметь 1 или 3 модели ({n} в списке).\n"
                    "1 = соло, 3 = Combo-3. Две модели больше нельзя.\n"
                    "Или открой приложение — там удобнее.",
                    parse_mode="HTML",
                    reply_markup=_custom_models_keyboard(models, page=0, user=user),
                )
            return
        if query.message:
            await query.message.edit_text(
                "Сохранено.\n" + _pref_summary(user),
                parse_mode="HTML",
                reply_markup=_mode_keyboard(mode),
            )
        return
    await query.answer()


async def on_custom_callback(query: CallbackQuery) -> None:
    if not query.from_user or not query.data:
        return
    data = query.data
    async with SessionLocal() as db:
        user, _, _ = await ensure_telegram_user(
            db,
            query.from_user.id,
            username=query.from_user.username,
            first_name=query.from_user.first_name,
        )
        selected = parse_fusion_models_json(getattr(user, "fusion_models", None))

        if data.startswith("fc:page:"):
            try:
                page = int(data.split(":")[-1])
            except ValueError:
                page = 0
            await db.commit()
            await query.answer()
            if query.message:
                await query.message.edit_reply_markup(
                    reply_markup=_custom_models_keyboard(selected, page=page, user=user)
                )
            return

        if data.startswith("fc:t:"):
            mid = data[5:]
            if mid in selected:
                selected = [m for m in selected if m != mid]
            elif len(selected) >= 3:
                await query.answer("Максимум 3", show_alert=True)
                await db.commit()
                return
            else:
                selected = selected + [mid]
            user.fusion_pref = "manual"
            user.fusion_models = json.dumps(selected, ensure_ascii=False)
            await db.commit()
            page = 0
            await query.answer(f"{len(selected)}/3")
            if query.message:
                await query.message.edit_reply_markup(
                    reply_markup=_custom_models_keyboard(selected, page=page, user=user)
                )
            return

        if data == "fc:done":
            from app.fusion.combo import resolve_stack_definition, ComboConfigError

            try:
                definition = resolve_stack_definition(
                    "manual", selected, allow_standard_fill=False
                )
            except ComboConfigError as exc:
                await query.answer(str(exc), show_alert=True)
                await db.commit()
                return
            user.fusion_pref = definition.product_mode
            user.fusion_models = json.dumps(list(definition.models), ensure_ascii=False)
            await db.commit()
            await _log_action(
                user,
                "pref_change",
                db=db,
                meta={
                    "mode": definition.product_mode,
                    "models": list(definition.models),
                    "architecture": definition.architecture,
                    "via": "bot_custom",
                },
            )
            await query.answer("Готово")
            if query.message:
                await query.message.edit_text(
                    "Сохранено.\n" + _pref_summary(user),
                    parse_mode="HTML",
                    reply_markup=_mode_keyboard(definition.product_mode),
                )
            return
    await query.answer()


async def cmd_key(message: Message) -> None:
    if not message.from_user:
        return
    async with SessionLocal() as db:
        user, raw, _ = await ensure_telegram_user(
            db,
            message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        await db.commit()
        await _log_action(user, "bot_key_show", db=db, meta={"issued_new": bool(raw)})
        if raw:
            await message.answer(
                format_creds(raw)
                + "\n\nДальше удобнее в приложении — обучение и модели.",
                parse_mode="HTML",
            )
            return
        prefix = await active_key_prefix(db, user)
    if not prefix:
        await message.answer("Ключа ещё нет. Открой приложение — ключ появится сам.")
        return
    await message.answer(
        f"Ключ: <code>{prefix}…</code>\n\n"
        "Полный ключ в чат повторно не отдаём.\n"
        "Перевыпустить — в приложении (Модели) или /newkey.",
        parse_mode="HTML",
    )


async def cmd_newkey(message: Message) -> None:
    if not message.from_user:
        return
    async with SessionLocal() as db:
        user, _, _ = await ensure_telegram_user(
            db,
            message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        raw, prefix = await rotate_telegram_key(db, user)
        await db.commit()
        await _log_action(
            user, "bot_key_rotate", db=db, meta={"key_prefix": prefix}
        )
    await message.answer(
        "Старый ключ отозван. Новый:\n\n"
        + format_creds(raw)
        + "\n\nСохрани его. Потом — в приложении.",
        parse_mode="HTML",
    )


async def cmd_balance(message: Message) -> None:
    if not message.from_user:
        return
    name = _hello_name(message)
    async with SessionLocal() as db:
        user, _, _ = await ensure_telegram_user(
            db,
            message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        bal, _synced = await _sync_balance(user)
        await db.commit()
        await _log_action(
            user, "bot_balance", db=db, meta={"balance_rub": bal}
        )
    bal_s = f"{bal:g}" if bal == int(bal) else f"{bal:.1f}"
    await message.answer(
        f"<b>{name}</b>, баланс: <b>{bal_s} ₽</b>\n"
        "Пополнить можно в кабинете на сайте.",
        parse_mode="HTML",
    )


async def cmd_help(message: Message) -> None:
    if message.from_user:
        async with SessionLocal() as db:
            user, _, _ = await ensure_telegram_user(
                db,
                message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
            )
            await db.commit()
            await _log_action(user, "bot_command", db=db, meta={"command": "/help"})
    await message.answer(HELP, parse_mode="HTML")


async def cmd_effort(message: Message) -> None:
    if not message.from_user:
        return
    parts = (message.text or "").split(maxsplit=1)
    level = (parts[1] if len(parts) > 1 else "").strip().lower()
    if level not in ("low", "normal", "high", "max"):
        async with SessionLocal() as db:
            user, _, _ = await ensure_telegram_user(
                db,
                message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
            )
            await db.commit()
            cur = normalize_effort(getattr(user, "fusion_effort", None))
        await message.answer(
            f"Effort сейчас: <b>{cur}</b>\n"
            "Или открой модели в приложении.\n"
            "/effort low|normal|high|max",
            parse_mode="HTML",
        )
        return
    async with SessionLocal() as db:
        user, _, _ = await ensure_telegram_user(
            db,
            message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        user.fusion_effort = normalize_effort(level)
        await db.commit()
        await db.refresh(user)
        await _log_action(
            user, "pref_change", db=db, meta={"effort": level, "via": "bot_effort"}
        )
    await message.answer(f"Сохранено.\n{_pref_summary(user)}", parse_mode="HTML")


async def cmd_kill(message: Message) -> None:
    if not message.from_user:
        return
    parts = (message.text or "").split(maxsplit=1)
    arg = (parts[1] if len(parts) > 1 else "").strip().lower()
    if arg not in ("on", "off", "1", "0", "true", "false"):
        async with SessionLocal() as db:
            user, _, _ = await ensure_telegram_user(
                db,
                message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
            )
            await db.commit()
            on = bool(getattr(user, "fusion_kill_switch", 0))
        await message.answer(
            f"Kill-Switch: <b>{'ON' if on else 'OFF'}</b>\n/kill on|off",
            parse_mode="HTML",
        )
        return
    enabled = arg in ("on", "1", "true")
    async with SessionLocal() as db:
        user, _, _ = await ensure_telegram_user(
            db,
            message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        user.fusion_kill_switch = 1 if enabled else 0
        await db.commit()
        await db.refresh(user)
        await _log_action(
            user,
            "pref_change",
            db=db,
            meta={"kill_switch": enabled, "via": "bot_kill"},
        )
    await message.answer(f"Сохранено.\n{_pref_summary(user)}", parse_mode="HTML")


async def on_text(message: Message) -> None:
    """Plain text → дружелюбный советник (DeepSeek + база + веб-исследование)."""
    if not message.from_user or not (message.text or "").strip():
        return
    text = (message.text or "").strip()
    if text.startswith("/"):
        return

    # ПРИОРИТЕТ 1: Запрос о подключении окна разработки
    from app.window_setup import detect_window_request, generate_window_config, format_setup_message

    window_id = detect_window_request(text)
    if window_id:
        try:
            async with SessionLocal() as db:
                user, _, _ = await ensure_telegram_user(
                    db,
                    message.from_user.id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                )
                await db.commit()

                # Получаем ключ пользователя
                prefix = active_key_prefix(user)
                api_key = prefix if prefix else "zeus_ВАШ_КЛЮЧ"

                # Генерируем конфиг
                window_config = generate_window_config(window_id, api_key)
                response = format_setup_message(window_config)

                await message.answer(response, parse_mode="HTML")

                await _log_action(
                    user,
                    "bot_window_setup",
                    prompt_preview=text[:500],
                    meta={"window_id": window_id},
                )
                return
        except Exception:  # noqa: BLE001
            log.exception("window setup failed")
            # Продолжаем к обычному advisor

    try:
        await message.bot.send_chat_action(message.chat.id, action="typing")
    except Exception:  # noqa: BLE001
        pass

    status_msg = None
    user = None
    t0 = asyncio.get_event_loop().time()
    try:
        from app.advisor import ask_advisor, to_telegram_html
        from app.fusion import DEFAULT_PRODUCT_MODE, normalize_product_mode

        name = _hello_name(message)
        async with SessionLocal() as db:
            user, _, _ = await ensure_telegram_user(
                db,
                message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
            )
            balance, _ = await _sync_balance(user)
            await db.commit()
            mode = (
                normalize_product_mode(getattr(user, "fusion_pref", None))
                or DEFAULT_PRODUCT_MODE
            )

        try:
            status_msg = await message.answer("Секунду, думаю…")
        except Exception:  # noqa: BLE001
            status_msg = None

        async def _status(msg: str) -> None:
            if status_msg is None:
                return
            try:
                await status_msg.edit_text(msg)
            except Exception:  # noqa: BLE001
                pass

        result = await ask_advisor(
            text,
            name=name,
            mode=mode,
            balance_rub=balance,
            on_status=_status,
        )
        latency_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
        await _log_action(
            user,
            "bot_advisor",
            prompt_preview=text[:500],
            latency_ms=latency_ms,
            meta={
                "researched": bool(result.get("researched")),
                "research_query": result.get("research_query"),
                "answer_preview": str(result.get("answer") or "")[:280],
            },
        )
        answer_html = to_telegram_html(str(result.get("answer") or ""))
        await _deliver_answer(message, answer_html, status_msg=status_msg)
    except Exception:  # noqa: BLE001
        log.exception("advisor chat failed")
        if user is not None:
            await _log_action(
                user,
                "bot_advisor",
                prompt_preview=text[:500],
                error="advisor_failed",
                status_code=500,
            )
        if status_msg is not None:
            try:
                await status_msg.edit_text(
                    "Не получилось ответить.\nОткрой приложение — обучение и модели."
                )
                return
            except Exception:  # noqa: BLE001
                pass
        await message.answer(
            "Не получилось ответить.\n"
            "Открой приложение — обучение и модели."
        )


async def main() -> None:
    token = settings.TELEGRAM_BOT_TOKEN.strip()
    if not token:
        log.error("TELEGRAM_BOT_TOKEN is empty")
        sys.exit(1)

    await init_db()
    bot = Bot(token=token)
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Модели", web_app=_webapp_info("fusion")
            )
        )
        log.info("Mini App menu button → %s", miniapp_url("fusion"))
    except Exception as e:  # noqa: BLE001
        log.warning("set_chat_menu_button failed: %s", e)

    dp = Dispatcher()
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_learn, Command("learn"))
    dp.message.register(cmd_mode, Command("mode"))
    dp.message.register(cmd_effort, Command("effort"))
    dp.message.register(cmd_kill, Command("kill"))
    dp.message.register(cmd_key, Command("key"))
    dp.message.register(cmd_newkey, Command("newkey"))
    dp.message.register(cmd_balance, Command("balance"))
    dp.callback_query.register(on_mode_callback, F.data.startswith("fm:"))
    dp.callback_query.register(on_custom_callback, F.data.startswith("fc:"))
    dp.message.register(on_text)

    me = await bot.get_me()
    log.info(
        "ZeusCode bot @%s starting miniapp=%s",
        me.username,
        miniapp_url(),
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
