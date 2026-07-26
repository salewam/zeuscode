"""ZeusCode friendly advisor — DeepSeek + база знаний + веб-исследование."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger("zeus.advisor")

_ROOT = Path(__file__).resolve().parents[2]
_VIRTUES = _ROOT / "docs" / "ZEUSCODE_DOSTOINSTVA.md"

_RESEARCH_MARK = "NEED_RESEARCH:"

_STYLE = """
## Как писать (обязательно)
Пиши по-человечески. Как умный собеседник в переписке — спокойно, ясно, с уважением.

Правила:
- Короткие абзацы. Одна мысль — один кусок.
- Обращение на «ты». Без крика и без канцелярита.
- Не начинай с приветствий и не с «Ок» / «Конечно!» / «Отличный вопрос!».
- Без жаргона: не пиши Fusion, Kie, OpenAI Compatible, если можно проще.
- Ключ в чат не выкладывай. Скажи: открой приложение → Модели или Старт.
- Ответ 3–8 коротких абзацев или аккуратный список. Не простыня.
- В конце — один следующий шаг.

## Оформление (строго)
- НЕ пиши HTML-теги: никаких <b> </b> <i> <code>.
- Важное выделяй двойными звёздочками: **Набор**, **Старт**.
- Списки: строки вида «1. …», «2. …» или «• …».
- Заголовки плана пиши просто строкой, без #.
- Абзацы разделяй пустой строкой.
"""

_FALLBACK_VIRTUES = """
ZeusCode — платформа для кодинга в связке топовых нейросетей.
Один ключ. Несколько сильных моделей. Режимы: пользовательский, продвинутый, набор.
Обучение и ключ — в Mini App. Советник отвечает в чате.
"""


def _load_virtues() -> str:
    try:
        if _VIRTUES.exists():
            return _VIRTUES.read_text(encoding="utf-8")[:12000]
    except Exception as e:  # noqa: BLE001
        log.warning("virtues load failed: %s", e)
    return _FALLBACK_VIRTUES


def build_system_prompt() -> str:
    virtues = _load_virtues()
    return f"""Ты — советник ZeusCode. Помогаешь выбрать режим, нейронки и куда вставить ключ.

{_STYLE}

## База знаний (достоинства и продукт)
{virtues}

## Режимы (в приложении → Модели)
• **Пользовательский** — лёгкие задачи, лендинги, мелкие правки.
• **Продвинутый** — серьёзный код, архитектура, рабочие проекты.
• **Набор** — до 3 топовых нейронок вручную, когда нужен максимум без ошибок.

## Окна
Continue / Cline / Roo в VS Code. Cursor отдельно. Aider — терминал.
Не знает куда — веди в Continue через обучение в приложении.

## Когда хватает базы
Если вопрос про ZeusCode (режимы, ключ, обучение, куда вставить, баланс в ₽) — отвечай из базы.

## Когда нужно исследование
Если вопрос вне базы (как настроить сторонний инструмент, свежие сравнения моделей,
внешние инструкции, то, чего нет выше) — НЕ выдумывай.
Ответь ОДНОЙ строкой строго в формате:
{_RESEARCH_MARK} <короткий поисковый запрос на русском или английском>

Не пиши ничего кроме этой строки, если нужен поиск.

Не выдумывай долларовые цены. Баланс в ₽.
Отвечай по-русски.
"""


def build_research_prompt() -> str:
    return f"""Ты — советник ZeusCode. Тебе дали результаты исследования из интернета.

{_STYLE}

Задача:
1) Кратко скажи, что понял из запроса (1 предложение).
2) Выдай **пошаговый план** — 4–7 шагов, каждый с новой строки: «1. …».
3) В каждом шаге — конкретное действие, без воды.
4) Если данные из сети слабые — честно скажи, что удалось найти, и всё равно дай разумный план.
5) В конце — один следующий шаг для пользователя в ZeusCode (приложение → Старт / Модели), если уместно.

Не выдумывай факты, которых нет в материалах.
Не используй HTML-теги.
"""


def normalize_advisor_text(text: str) -> str:
    """Clean model output for elegant display (no raw HTML tags)."""
    s = (text or "").strip()
    if not s:
        return s
    # convert accidental HTML emphasis → markdown bold/italic first
    s = re.sub(r"<(?:b|strong)>(.*?)</(?:b|strong)>", r"**\1**", s, flags=re.I | re.S)
    s = re.sub(r"<(?:i|em)>(.*?)</(?:i|em)>", r"**\1**", s, flags=re.I | re.S)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    # strip remaining accidental HTML tags
    s = re.sub(r"</?(?:b|i|em|strong|code|pre|u|br|p|div|span)(?:\s[^>]*)?>", "", s, flags=re.I)
    s = s.replace("&lt;b&gt;", "").replace("&lt;/b&gt;", "")
    s = s.replace("&lt;i&gt;", "").replace("&lt;/i&gt;", "")
    # markdown bold leftovers of empty ** **
    s = re.sub(r"\*\*\s*\*\*", "", s)
    # collapse noisy blank lines
    s = re.sub(r"\n{3,}", "\n\n", s)
    if len(s) > 3800:
        s = s[:3790].rstrip() + "…"
    return s.strip()


def to_telegram_html(text: str) -> str:
    """Escape + convert **bold** for Telegram HTML parse_mode."""
    s = normalize_advisor_text(text)
    s = (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.S)
    return s


async def _deepseek_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.5,
    max_tokens: int = 900,
) -> str | None:
    settings = get_settings()
    key = (settings.DEEPSEEK_API_KEY or "").strip()
    base = (settings.DEEPSEEK_BASE_URL or "https://api.deepseek.com").rstrip("/")
    if not key:
        return None
    url = f"{base}/chat/completions"
    payload: dict[str, Any] = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        async with httpx.AsyncClient(timeout=55.0) as client:
            r = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if r.status_code >= 400:
                log.warning("advisor HTTP %s: %s", r.status_code, r.text[:300])
                return None
            data = r.json()
            return (
                ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
                or ""
            ).strip() or None
    except Exception as e:  # noqa: BLE001
        log.warning("advisor deepseek failed: %s", e)
        return None


def _parse_research_mark(text: str) -> str | None:
    s = (text or "").strip()
    if not s:
        return None
    # allow mark on first line even if model adds fluff
    for line in s.splitlines():
        line = line.strip()
        if line.upper().startswith(_RESEARCH_MARK):
            q = line.split(":", 1)[-1].strip()
            return q or None
    if s.upper().startswith("NEED_RESEARCH"):
        q = s.split(":", 1)[-1].strip()
        return q or None
    return None


def _pack_research(results: list[dict[str, Any]], fetches: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for i, item in enumerate(results[:5], 1):
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        snip = (item.get("snippet") or "").strip()
        parts.append(f"{i}. {title}\n   {url}\n   {snip}")
    for i, item in enumerate(fetches[:3], 1):
        if not item.get("ok"):
            continue
        url = (item.get("url") or "").strip()
        text = (item.get("text") or "").strip()[:1200]
        if text:
            parts.append(f"Источник {i} ({url}):\n{text}")
    return "\n\n".join(parts).strip() or "Поиск почти ничего не дал."


async def _run_web_research(query: str) -> str:
    """Search + light fetch; return packed notes for the synthesizer."""
    try:
        from app.fusion.web_tools import web_fetch, web_search
    except Exception as e:  # noqa: BLE001
        log.warning("web_tools import failed: %s", e)
        return f"Поиск недоступен ({e}). Ответь по общим знаниям осторожно."

    search = await web_search(query, max_results=4)
    results = list(search.get("results") or [])
    fetches: list[dict[str, Any]] = []
    for item in results[:2]:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        try:
            fetches.append(await web_fetch(url, limit=1600))
        except Exception as e:  # noqa: BLE001
            log.warning("advisor fetch failed: %s", e)
    return _pack_research(results, fetches)


async def ask_advisor(
    user_text: str,
    *,
    name: str | None = None,
    mode: str | None = None,
    balance_rub: float | None = None,
    history: list[dict[str, str]] | None = None,
    on_status: Any | None = None,
) -> dict[str, Any]:
    """
    Call DeepSeek; optionally research the web.

    Returns {answer, researched, research_query}.
    `answer` is plain elegant text with **bold** (no HTML tags).
    `on_status` — optional async callable(str) for live UX ("делаю исследование").
    """
    offline = {
        "answer": (
            "Советник пока отдыхает.\n\n"
            "Открой вкладку **Модели** или **Старт** в приложении — там всё под рукой."
        ),
        "researched": False,
        "research_query": None,
    }
    settings = get_settings()
    if not (settings.DEEPSEEK_API_KEY or "").strip():
        return offline

    async def _status(msg: str) -> None:
        if on_status is None:
            return
        try:
            await on_status(msg)
        except Exception:  # noqa: BLE001
            pass

    context = []
    if name:
        context.append(f"Имя: {name}")
    if mode:
        labels = {
            "simple": "Пользовательский",
            "power": "Продвинутый",
            "custom": "Набор",
        }
        context.append(f"Сейчас выбран режим: {labels.get(mode, mode)}")
    if balance_rub is not None:
        context.append(f"Баланс: {balance_rub} ₽")

    sys = build_system_prompt()
    if context:
        sys += "\n\n## Контекст\n" + "\n".join(context)

    messages: list[dict[str, str]] = [{"role": "system", "content": sys}]
    if history:
        for h in history[-8:]:
            role = h.get("role") or "user"
            content = (h.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content[:2000]})
    messages.append({"role": "user", "content": (user_text or "").strip()[:4000]})

    first = await _deepseek_chat(messages, temperature=0.45, max_tokens=700)
    if not first:
        return {
            "answer": (
                "Не дотянулся до ответа.\n\n"
                "Попробуй ещё раз — или открой **Старт** / **Модели** в приложении."
            ),
            "researched": False,
            "research_query": None,
        }

    query = _parse_research_mark(first)
    if not query:
        return {
            "answer": normalize_advisor_text(first),
            "researched": False,
            "research_query": None,
        }

    await _status("Подождите, делаю исследование…")

    pack = await _run_web_research(query)
    research_messages = [
        {"role": "system", "content": build_research_prompt()},
        {
            "role": "user",
            "content": (
                f"Вопрос пользователя:\n{(user_text or '').strip()[:2000]}\n\n"
                f"Поисковый запрос:\n{query}\n\n"
                f"Материалы исследования:\n{pack[:7000]}"
            ),
        },
    ]
    second = await _deepseek_chat(research_messages, temperature=0.4, max_tokens=1100)
    if not second:
        return {
            "answer": (
                "Сделал исследование, но ответ не собрался.\n\n"
                "Напиши вопрос чуть проще — или открой **Старт** в приложении."
            ),
            "researched": True,
            "research_query": query,
        }
    answer = normalize_advisor_text(second)
    if "1." not in answer and "1)" not in answer:
        answer = "Краткий план по тому, что удалось найти:\n\n" + answer
    return {
        "answer": answer,
        "researched": True,
        "research_query": query,
    }


# Back-compat for callers that expect a string
async def ask_advisor_text(*args: Any, **kwargs: Any) -> str:
    data = await ask_advisor(*args, **kwargs)
    return str(data.get("answer") or "")
