"""Orchestrator brief unpack: expand vague tasks into a buildable product brief.

Does NOT block for user answers — ships assumptions + clarifying questions so
workers get a concrete brief and the UI can show what was assumed.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app import upstream
from app.config import get_settings

settings = get_settings()

_EXPAND_SYSTEM = """Ты оркестратор ZeusCode Studio. Распаковываешь короткое ТЗ в рабочий бриф продукта.

Правила:
1. НЕ задавай вопросы пользователю в ожидании ответа — СРАЗУ строй бриф с явными допущениями.
2. Вопросы клади в questions[] — это follow-up после сдачи, не блокер.
3. Пиши конкретику: бренд, город/район (если не дан — выдумай реалистичный РФ), услуги, цены в ₽, часы, телефон, CTA, секции страницы, API если нужен.
4. Anti-AI: запрети indigo/purple/Inter; палитра под отрасль (для автосервиса — масло/металл/асфальт/янтарь, не SaaS).
5. Ответ СТРОГО JSON без markdown fence:
{
  "title": "краткое имя продукта",
  "summary": "1-2 предложения что строим",
  "assumptions": ["..."],
  "questions": ["до 4 уточнений на потом"],
  "brand": {"name": "...", "tone": "...", "city": "..."},
  "sections": ["Hero", "..."],
  "services": [{"name":"...","price_from_rub":0,"note":"..."}],
  "cta": {"primary":"...","secondary":"..."},
  "contacts": {"phone":"...","address":"...","hours":"..."},
  "api": [{"method":"POST","path":"/api/...","fields":["name","phone"]}],
  "must_haves": ["..."],
  "visual": "1 абзац: палитра, фото-якорь, атмосфера",
  "brief_md": "полный markdown-бриф для агентов (секции, копирайт-якоря, запреты)"
}
6. brief_md — главный артефакт для воркеров: полный, на русском, без воды.
7. Если задача уже очень детальная — всё равно нормализуй в эту схему, не раздувай.
"""


def needs_expand(user_text: str, brief: str | None = None) -> bool:
    """Heuristic: short / vague build tasks benefit from expansion."""
    text = (user_text or "").strip()
    if not text:
        return False
    if brief and len(brief.strip()) > 400:
        return False
    # Already looks like a packed brief
    if re.search(r"(?i)must[- ]?have|##\s*бриф|sections?:|услуги:|прайс", text):
        if len(text) > 600:
            return False
    # Short product asks
    if len(text) < 280:
        return True
    if re.search(
        r"(?i)сделай|собери|лендинг|сайт|страниц|landing|для\s+\w+",
        text,
    ) and len(text) < 800:
        return True
    return False


def format_expanded_brief(data: dict[str, Any]) -> str:
    """Render structured expand result into worker-facing markdown."""
    if data.get("brief_md"):
        md = str(data["brief_md"]).strip()
    else:
        md = str(data.get("summary") or "").strip()
    bits: list[str] = [md]
    assumptions = data.get("assumptions") or []
    if assumptions:
        bits.append("\n## Допущения оркестратора")
        bits.extend(f"- {a}" for a in assumptions[:8])
    questions = data.get("questions") or []
    if questions:
        bits.append("\n## Уточнения (не блокируют сборку — можно ответить позже)")
        bits.extend(f"- {q}" for q in questions[:6])
    must = data.get("must_haves") or []
    if must:
        bits.append("\n## Must-have")
        bits.extend(f"- {m}" for m in must[:10])
    return "\n".join(bits).strip()


def _fallback_autoservice(user_text: str) -> dict[str, Any]:
    """Deterministic rich brief when LLM fails — used for autoservice-like tasks."""
    is_auto = bool(
        re.search(
            r"(?i)автосервис|сто\b|шиномонтаж|ремонт\s+авто|автомастер",
            user_text or "",
        )
    )
    if not is_auto:
        return {
            "title": "Сайт по запросу",
            "summary": user_text.strip()[:200],
            "assumptions": [
                "Один лендинг + форма заявки",
                "Реалистичные контакты и цены в ₽",
                "Фото/атмосфера в hero, не пустой градиент",
            ],
            "questions": [
                "Как называется бренд и город?",
                "Какой главный CTA: звонок, заявка, запись?",
                "Нужен ли прайс с цифрами или только услуги?",
            ],
            "brand": {"name": "Studio", "tone": "деловой", "city": "Москва"},
            "sections": ["Hero", "Услуги", "Как работаем", "Отзывы", "Заявка", "Контакты"],
            "services": [],
            "cta": {"primary": "Оставить заявку", "secondary": "Позвонить"},
            "contacts": {
                "phone": "+7 (495) 000-00-00",
                "address": "Москва",
                "hours": "Пн–Сб 09:00–20:00",
            },
            "api": [
                {
                    "method": "POST",
                    "path": "/api/lead",
                    "fields": ["name", "phone", "message"],
                }
            ],
            "must_haves": [
                "Рабочая форма заявки",
                "Реальные секции и цены если уместно",
                "Адаптив + a11y focus",
            ],
            "visual": "Отраслевая палитра, full-bleed hero с фото, без indigo/Inter.",
            "brief_md": (
                f"# Бриф\n\nЗадача: {user_text.strip()}\n\n"
                "Собери лендинг с hero, услугами, формой заявки POST /api/lead "
                "(name, phone, message), контактами. Цены в ₽. Без AI-look."
            ),
        }

    return {
        "title": "Автосервис полного цикла",
        "summary": "Лендинг СТО: все виды работ, прайс, запись на ремонт, контакты.",
        "assumptions": [
            "Бренд: «МоторХаус» · Москва, ЮАО, Каширское ш.",
            "Полный цикл: ТО, диагностика, ходовая, масло, шиномонтаж, кузов/полировка, электрика",
            "Запись онлайн + звонок; ответ мастера за 15 минут в рабочее время",
            "Цены «от» в ₽, без скрытых доплат в копирайте",
        ],
        "questions": [
            "Фиксируем бренд «МоторХаус» или своё имя?",
            "Нужен ли личный кабинет / история заказов или только заявка?",
            "Есть ли свои фото боксов/мастеров для hero?",
            "Работаете с юрлицами (счёт) — показывать блок B2B?",
        ],
        "brand": {
            "name": "МоторХаус",
            "tone": "уверенный, мастерской, без «премиум-воды»",
            "city": "Москва",
        },
        "sections": [
            "Hero",
            "Все виды работ",
            "Прайс от",
            "Как записаться",
            "Гарантия / почему мы",
            "Отзывы",
            "Форма записи",
            "Контакты / карта-заглушка",
        ],
        "services": [
            {"name": "Диагностика", "price_from_rub": 1500, "note": "компьютер + осмотр"},
            {"name": "ТО по регламенту", "price_from_rub": 4500, "note": "масло + фильтры"},
            {"name": "Ходовая / тормоза", "price_from_rub": 2500, "note": "запчасти отдельно"},
            {"name": "Шиномонтаж", "price_from_rub": 1800, "note": "R15–R21"},
            {"name": "Электрика", "price_from_rub": 2000, "note": "стартер, генератор, проводка"},
            {"name": "Кузов / полировка", "price_from_rub": 5000, "note": "оценка после осмотра"},
        ],
        "cta": {"primary": "Записаться на ремонт", "secondary": "Позвонить мастеру"},
        "contacts": {
            "phone": "+7 (495) 120-45-67",
            "address": "Москва, Каширское ш., 31с1",
            "hours": "Пн–Сб 09:00–21:00, Вс 10:00–18:00",
        },
        "api": [
            {
                "method": "POST",
                "path": "/api/booking",
                "fields": ["name", "phone", "car", "service", "slot"],
            }
        ],
        "must_haves": [
            "Hero с атмосферой бокса/авто, не пустой градиент",
            "Сетка услуг со всеми видами работ + цены от",
            "Форма записи → POST /api/booking",
            "Телефон кликабельный tel:",
            "Блок гарантии / этапов работы",
            "Адаптив mobile-first",
        ],
        "visual": (
            "Палитра: асфальт #1a1c1e, металл #c5c9ce, янтарь-масло #c47a2c, "
            "светлый цех #f3f1ec. Display: плотный гротеск/Georgia для заголовков, "
            "system-ui для текста. Hero — full-bleed фото бокса или авто в работе."
        ),
        "brief_md": """# Бриф: автосервис «МоторХаус»

## Продукт
Одностраничный сайт СТО полного цикла: запись на ремонт, прайс «от», все виды работ, контакты.

## Бренд
- Имя: МоторХаус
- Город: Москва, Каширское ш., 31с1
- Тон: мастерской, цифры и факты, без «премиум-яйцевого» копирайта

## Секции (обязательно)
1. Hero — название, 1 оффер («Все виды работ · запись сегодня»), CTA запись + tel
2. Все виды работ — карточки/список: диагностика, ТО, ходовая, шиномонтаж, электрика, кузов
3. Прайс «от» в ₽ (таблица или сетка)
4. Как записаться — 3 шага
5. Гарантия / почему мы — 3 факта (не вода)
6. Отзывы — 2–3 коротких с именем и авто
7. Форма записи: имя, телефон, марка/модель, услуга, удобный слот
8. Контакты + часы

## API
POST /api/booking JSON: name, phone, car, service, slot → 200 {ok:true}

## Визуал
Асфальт/металл/янтарь, full-bleed hero с фото, без indigo/Inter/purple. 1–2 CSS transition.

## Запреты
Пустой hero-void, egg-copy («три сильные вещи»), outline:none без :focus-visible.
""",
    }


def _parse_json_loose(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def inject_api_prelock(data: dict[str, Any]) -> dict[str, Any] | None:
    """Turn expand.api into evidence-style prelock contract."""
    apis = data.get("api") or []
    if not apis:
        return None
    endpoints: list[dict[str, Any]] = []
    paths: list[str] = []
    fields: list[str] = []
    for item in apis:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        method = str(item.get("method") or "POST").upper()
        if not path.startswith("/"):
            continue
        fl = [str(x) for x in (item.get("fields") or []) if str(x).strip()]
        endpoints.append({"method": method, "path": path, "fields": fl})
        paths.append(path)
        fields.extend(fl)
    if not endpoints:
        return None
    # unique fields preserve order
    seen: set[str] = set()
    uniq_fields: list[str] = []
    for f in fields:
        if f not in seen:
            seen.add(f)
            uniq_fields.append(f)
    return {
        "source": "brief_expand",
        "endpoints": endpoints,
        "paths": paths,
        "fields": uniq_fields,
        "auth_required": False,
    }


async def expand_task_brief(
    *,
    user_text: str,
    brief: str | None = None,
    mode: str = "ultra",
    model: str | None = None,
) -> dict[str, Any]:
    """LLM (or fallback) expansion. Always returns a dict with brief_md + questions."""
    if not needs_expand(user_text, brief):
        return {
            "title": "Как в задаче",
            "summary": (user_text or "")[:240],
            "assumptions": [],
            "questions": [],
            "skipped": True,
            "brief_md": (brief or user_text or "").strip(),
            "source": "passthrough",
        }

    mid = (model or "").strip() or (settings.STUDIO_JUDGE_MODEL or "gemini-2.5-pro")
    # light: skip LLM cost — use deterministic fallback for known niches / generic
    if mode == "light":
        data = _fallback_autoservice(user_text)
        data["source"] = "fallback_light"
        data["model"] = "deterministic"
        return data

    user_payload = (
        f"Режим Studio: {mode}\n"
        f"Существующий бриф проекта: {(brief or '—')[:1200]}\n\n"
        f"Задача пользователя:\n{user_text.strip()}"
    )
    try:
        resp = await upstream.chat_completions(
            model=mid,
            messages=[
                {"role": "system", "content": _EXPAND_SYSTEM},
                {"role": "user", "content": user_payload},
            ],
        )
        text = upstream.extract_text(resp)
        data = _parse_json_loose(text)
        if not data or not (data.get("brief_md") or data.get("summary")):
            raise ValueError("empty expand json")
        pt, ct = upstream.extract_usage(resp)
        data["source"] = "llm"
        data["model"] = mid
        data["prompt_tokens"] = pt
        data["completion_tokens"] = ct
        return data
    except Exception as e:
        data = _fallback_autoservice(user_text)
        data["source"] = "fallback_error"
        data["error"] = str(e)[:200]
        data["model"] = mid
        return data
