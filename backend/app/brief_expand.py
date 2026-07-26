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
from app.media_packs import (
    detect_media_niche,
    media_brief_block,
    pick_media_pair,
)
from app.uniqueness import (
    build_sto_identity,
    css_skeleton_from_identity,
    uniqueness_brief_block,
)

settings = get_settings()

_EXPAND_SYSTEM = """Ты оркестратор ZeusCode Studio. Распаковываешь короткое ТЗ в рабочий бриф продукта.

Правила:
1. НЕ задавай вопросы пользователю в ожидании ответа — СРАЗУ строй бриф с явными допущениями.
2. Вопросы клади в questions[] — это follow-up после сдачи, не блокер.
3. Пиши конкретику: бренд УНИКАЛЬНЫЙ для этого ТЗ (не штампуй «МоторХаус» всем), город/район, услуги, цены в ₽, часы, телефон, CTA, секции, API.
4. Anti-AI: запрети indigo/purple/Inter; палитра под отрасль (для автосервиса — масло/металл/асфальт/янтарь, не SaaS). Уникальность: другой бренд/адрес/H1/порядок секций чем у чужого клиента.
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
        r"(?i)сделай|собери|лендинг|сайт|страниц|landing|презентац|pitch|deck|слайд|"
        r"приложен|web\s*app|для\s+\w+|to-?do|задач|кабинет|crm",
        text,
    ) and len(text) < 800:
        return True
    return False


def _looks_like_app(user_text: str) -> bool:
    t = user_text or ""
    if re.search(r"(?i)лендинг|landing|визитк|автосервис|\bсто\b|кофейн", t):
        return False
    return bool(
        re.search(
            r"(?i)приложен|web\s*app|\bapps?\b|to-?do|задач|кабинет|crm|"
            r"инструмент|сервис\s+для|список.+созда",
            t,
        )
    )


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


def _fallback_app(user_text: str) -> dict[str, Any]:
    """Deterministic app brief when LLM fails or niche skip."""
    t = user_text or ""
    shop = bool(
        re.search(
            r"(?i)букет|цвет|каталог|магазин|заказ|доставк|salon|shop",
            t,
        )
    )
    if shop:
        return {
            "title": "Каталог + заказ",
            "summary": (t.strip()[:220] or "Мини-приложение: каталог и заказ"),
            "product_id": "app",
            "assumptions": [
                "App-shell: catalog / order / orders",
                "≥4 позиции с image+price+composition",
                "Форма: name, phone, bouquet_id, date, address",
                "Только HTML+CSS+JS",
            ],
            "questions": [],
            "brand": {"name": "Букет Лайн", "tone": "тёплый продуктовый", "city": "Москва"},
            "sections": ["catalog", "order", "orders"],
            "screens_or_sections": ["catalog", "order", "orders"],
            "services": [],
            "cta": {"primary": "Оформить заказ", "secondary": "К каталогу"},
            "contacts": {"phone": "+7 (495) 123-45-67", "address": "Москва"},
            "api": [
                {"method": "GET", "path": "/api/bouquets", "fields": ["id", "name", "price", "image", "composition"]},
                {"method": "GET", "path": "/api/orders", "fields": []},
                {
                    "method": "POST",
                    "path": "/api/orders",
                    "fields": ["name", "phone", "bouquet_id", "delivery_date", "address"],
                },
            ],
            "must_haves": [
                "3 экрана: catalog, order, orders",
                "Карточки: img + price + meta + «В заказ»",
                "select наполняется из GET /api/bouquets",
                "POST json + address + res.ok",
                "styles.css ≥2.5KB, не скелет",
                "Backend seed ≥4 с unsplash image",
            ],
            "visual": "Плотный app UI: tokens, шрифты, grid карточек с фото. Не лендинг. Не React.",
            "brief_md": """# Бриф: каталог + заказ (product_id=app)

## Продукт
Не лендинг. App-shell: Каталог / Новый заказ / Мои заказы.

## Стек
HTML + CSS + JS. Запрет: React, Vue, JSX, alert(), onclick=.

## Экраны
1. catalog — карточки img+price+composition+кнопка «В заказ»; states loading/empty/error
2. order — name, phone, bouquet_id (select из API), address, delivery_date; POST json
3. orders — список GET /api/orders

## API
- GET /api/bouquets → ≥4 {id,name,price,image,composition}
- GET /api/orders
- POST /api/orders {name,phone,bouquet_id,delivery_date,address}

## Запреты
thin_catalog, thin_styles, dead_select, missing_json_headers, hero-лендинг, React.
""",
            "source": "fallback_app_shop",
        }
    return {
        "title": "Веб-приложение",
        "summary": t.strip()[:200] or "Простое веб-приложение со списком и действием",
        "product_id": "app",
        "assumptions": [
            "App-shell: nav + ≥2 экрана (список / создание)",
            "Ключевое действие сохраняет данные через API",
            "States: loading / empty / error / ready",
            "Не маркетинговый лендинг",
            "Плотный UI: styles.css ≥2.5KB",
        ],
        "questions": [
            "Как назвать приложение?",
            "Какая главная сущность (задачи, записи, клиенты)?",
            "Нужен ли вход (auth) в этом MVP?",
        ],
        "brand": {"name": "App", "tone": "спокойный", "city": ""},
        "sections": ["list", "create"],
        "screens_or_sections": ["list", "create"],
        "services": [],
        "cta": {"primary": "Создать", "secondary": "К списку"},
        "contacts": {},
        "api": [
            {"method": "GET", "path": "/api/items", "fields": []},
            {"method": "POST", "path": "/api/items", "fields": ["title"]},
        ],
        "must_haves": [
            "Nav между списком и формой создания",
            "POST /api/items + показ в списке",
            "Empty и error состояния",
            "Только HTML+CSS+JS — без React/Vue",
            "styles.css плотный, не 14 строк",
            "Mobile-first, без AI-aesthetic",
        ],
        "visual": "Продуктовый UI: tokens, один accent. Не hero-лендинг. Не React.",
        "brief_md": """# Бриф: веб-приложение (product_id=app)

## Продукт
Не лендинг. App-shell: шапка + nav, экраны list/create, данные через API.

## Стек (жёстко)
HTML + CSS + JS. **Запрет:** React, Vue, npm-бандлы, JSX.

## Экраны
1. Список — loading / empty / error / ready
2. Создание — поле title + submit; ошибка через role=alert

## API
- GET /api/items → {items:[{id,title}]}
- POST /api/items {title} → 201 {id,title}

## Запреты
Hero-маркетинг, indigo/Inter/glow, fake success в catch, alert(), onclick=, React, thin_styles.
""",
        "source": "fallback_app",
    }


def _is_deck_task(user_text: str) -> bool:
    return bool(
        re.search(r"(?i)презентац|pitch|deck|слайд|питч|инвестор.?deck", user_text or "")
    )


def _fallback_deck(user_text: str) -> dict[str, Any]:
    """HTML deck brief — content-filled slides for cheap models."""
    pair = pick_media_pair(user_text, niche="deck")
    media_md = media_brief_block(pair)
    return {
        "title": "Презентация",
        "summary": "HTML-колода 8 слайдов с фактами, цифрами и разным media.",
        "product_kind": "deck",
        "product_id": "deck",
        "assumptions": [
            "Формат: HTML-deck /src/deck/ (или /src/frontend/)",
            "8 слайдов × 100vh, навигация точками/клавишами",
            "Бренд и цифры — реалистичные допущения РФ",
        ],
        "questions": [
            "Для кого колода: инвесторы, клиенты, партнёры?",
            "Есть ли обязательные цифры/логотип?",
        ],
        "brand": {"name": "Проект", "tone": "деловой, факты", "city": "Москва"},
        "sections": [
            "Title", "Problem", "Solution", "How", "Proof", "Offer", "Why", "CTA"
        ],
        "cta": {"primary": "Назначить созвон", "secondary": "Написать в Telegram"},
        "contacts": {
            "phone": "+7 (495) 211-34-56",
            "address": "Москва",
            "hours": "Ответ в будни до 18:00",
        },
        "api": [],
        "must_haves": [
            "≥8 слайдов с текстом",
            "3 разных remote фото на разных слайдах",
            "Цифры/факты, не egg-copy",
            "CTA с tel на последнем слайде",
        ],
        "hero_media": {
            "primary": pair["primary"]["url"],
            "secondary": pair["secondary"]["url"],
            "tertiary": pair["tertiary"]["url"],
            "rule": pair["rule"],
        },
        "visual": "Без indigo/Inter. Full-bleed фото на слайдах 1, 3, 5 — разные URL.",
        "brief_md": (
            f"# Бриф: презентация (HTML deck)\n\n## Задача\n{user_text.strip()}\n\n"
            "## Формат\n`/src/deck/index.html` + `styles.css`. "
            "Каждый слайд = section.slide на min-height:100vh.\n\n"
            f"{media_md}\n"
            "## Слайды (все 8)\n"
            "1 Title · 2 Problem (3 боли) · 3 Solution (+photo #2) · 4 How · "
            "5 Proof (+photo #3) · 6 Offer · 7 Why · 8 CTA tel:+74952113456\n\n"
            "## Запреты\nОдин URL на колоду; lorem; egg-copy; 3 пустых слайда. "
            "См. content-fill.md § Презентация.\n"
        ),
    }


def _fallback_autoservice(user_text: str) -> dict[str, Any]:
    """Deterministic rich brief — landings / STO / decks for cheap models."""
    if _is_deck_task(user_text) and not re.search(
        r"(?i)автосервис|сто\b|лендинг\s+сайт|сайт\s+авто",
        user_text or "",
    ):
        return _fallback_deck(user_text)

    is_auto = bool(
        re.search(
            r"(?i)автосервис|сто\b|шиномонтаж|ремонт\s+авто|автомастер",
            user_text or "",
        )
    )
    if not is_auto:
        pair = pick_media_pair(user_text)
        media_md = media_brief_block(pair)
        return {
            "title": "Сайт по запросу",
            "summary": user_text.strip()[:200],
            "product_kind": "landing",
            "assumptions": [
                "Один лендинг + форма заявки",
                "Реалистичные контакты и цены в ₽",
                "Разные remote-фото в hero и mid-page",
            ],
            "questions": [
                "Как называется бренд и город?",
                "Какой главный CTA: звонок, заявка, запись?",
                "Нужен ли прайс с цифрами или только услуги?",
            ],
            "brand": {"name": "Studio", "tone": "деловой", "city": "Москва"},
            "sections": [
                "Hero", "Услуги", "Как работаем", "Почему мы",
                "Отзывы", "FAQ", "Заявка", "Контакты",
            ],
            "services": [],
            "reviews": [
                {
                    "quote": "Сделали быстро, всё объяснили по делу, без навязывания.",
                    "name": "Анна",
                    "detail": "Москва",
                },
                {
                    "quote": "Удобная запись, перезвонили через десять минут.",
                    "name": "Сергей",
                    "detail": "Химки",
                },
            ],
            "faq": [
                {"q": "Сколько занимает ответ?", "a": "В рабочие часы — до 15 минут."},
                {"q": "Цена заранее?", "a": "Ориентир «от» на сайте, смета после уточнения."},
                {"q": "Гарантия?", "a": "На работы — по договору."},
            ],
            "cta": {"primary": "Оставить заявку", "secondary": "Позвонить"},
            "contacts": {
                "phone": "+7 (495) 211-34-56",
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
                "Hero + mid-page: два разных remote URL",
                "≥6 секций + форма + FAQ/отзывы с текстом",
                "Явный CTA (кнопка/ссылка — класс любой)",
                "Адаптив + a11y focus",
            ],
            "hero_media": {
                "primary": pair["primary"]["url"],
                "secondary": pair["secondary"]["url"],
                "tertiary": pair["tertiary"]["url"],
                "rule": pair["rule"],
            },
            "visual": "Отраслевая палитра, два remote фото, без indigo/Inter.",
            "brief_md": (
                f"# Бриф\n\nЗадача: {user_text.strip()}\n\n{media_md}\n"
                "Лендинг: hero + услуги + как работаем + отзывы + FAQ + "
                "форма POST /api/lead (name, phone, message). "
                "См. content-fill.md. Без одного фото на всё."
            ),
        }

    pair = pick_media_pair(user_text, niche="sto")
    media_md = media_brief_block(pair)
    ident = build_sto_identity(user_text)
    uniq_md = uniqueness_brief_block(ident)
    p_url = pair["primary"]["url"]
    s_url = pair["secondary"]["url"]
    t_url = pair["tertiary"]["url"]
    f_url = (pair.get("fourth") or pair["tertiary"])["url"]
    css_skel = css_skeleton_from_identity(ident, p_url)
    services_out = [
        {
            "name": name,
            "price_from_rub": price,
            "note": note,
            "includes": includes,
        }
        for name, price, note, includes in ident["services"]
    ]
    reviews_out = [
        {"quote": q, "name": n, "detail": d} for q, n, d in ident["reviews"]
    ]
    faq_out = [{"q": q, "a": a} for q, a in ident["faq"]]
    brand = ident["brand"]
    return {
        "title": f"Автосервис «{brand}»",
        "summary": f"Лендинг СТО {brand}: витрина, прайс, запись, FAQ. uniq={ident['uniq']}",
        "product_kind": "landing",
        "assumptions": [
            f"Бренд: «{brand}» · {ident['address']}",
            "Полный цикл работ, цены «от» в ₽",
            "Запись онлайн + звонок в рабочие часы",
            f"UNIQUE seed {ident['uniq']} — не клонировать чужой сайт",
        ],
        "questions": [
            f"Бренд «{brand}» ок или своё имя?",
            "Нужен ли кабинет или только заявка?",
        ],
        "brand": {
            "name": brand,
            "tone": ident["tone"],
            "city": ident["city"],
            "uniq": ident["uniq"],
        },
        "sections": [
            "Hero", "Витрина", "Услуги", "Как записаться", "Почему мы",
            "Отзывы", "FAQ", "Форма", "Контакты",
        ],
        "services": services_out,
        "reviews": reviews_out,
        "faq": faq_out,
        "cta": {
            "primary": ident["cta_primary"],
            "secondary": ident["cta_secondary"],
        },
        "contacts": {
            "phone": ident["phone"],
            "address": ident["address"],
            "hours": ident["hours"],
        },
        "api": [
            {
                "method": "POST",
                "path": "/api/booking",
                "fields": ["name", "phone", "car", "service", "slot"],
            }
        ],
        "must_haves": [
            f'html data-uniq="{ident["uniq"]}" + бренд «{brand}» в chrome/title',
            "Hero: живой remote photo (не серый void)",
            "Медиа-ряд: ≥2 разных <img src=https> (id/классы — свои, не обязан #vitrine)",
            "6 услуг: абзац + список + цена от (из UNIQUE блока)",
            "why: реальное <img> (не только div background)",
            "HTML ≥7500B, ≥7 section, ≥3 photo-ID",
            "Свой type + chrome + motion + @media; палитра из UNIQUE (токены — любые имена)",
            "НЕ копировать МоторХаус/Каширское и НЕ клонировать один каркас с заменой имени",
        ],
        "hero_media": {
            "primary": p_url,
            "secondary": s_url,
            "tertiary": t_url,
            "fourth": f_url,
            "scene": pair["primary"]["scene"],
            "rule": pair["rule"],
        },
        "uniqueness": ident,
        "visual": (
            f"Палитра UNIQUE accent={ident['palette']['amber']}. "
            "Hero=фото+читаемый overlay (направление градиента — любое). "
            "Медиа-ряд ≥2 фото. Не #f8fafc. Свой layout — не штамп эталона."
        ),
        "brief_md": (
            f"# Бриф: автосервис «{brand}»\n\n"
            f"## Продукт\nВкусный лендинг СТО **{brand}**: медиа, жирные услуги, запись, FAQ.\n\n"
            f"## Бренд\n{brand} · {ident['address']} · {ident['phone']} · {ident['hours']}\n\n"
            f"{uniq_md}\n"
            f"{media_md}\n"
            "## Контент-якоря (классы/id — invent)\n"
            "```html\n"
            f'<html lang="ru" data-uniq="{ident["uniq"]}">\n'
            f"<!-- brand chrome: {brand} -->\n"
            f"<h1>{ident['h1']}</h1>\n"
            f"<p>{ident['lead']}</p>\n"
            f"<!-- media gallery ≥2 imgs: {s_url[:60]}… -->\n"
            f"<!-- h2 hint: {ident['vitrine_title']} -->\n"
            "```\n\n"
            "## CSS tokens ONLY (полный layout — invent, не копируй эталон)\n"
            "```css\n"
            f"{css_skel}"
            "```\n\n"
            f"## Секции (порядок UNIQUE `{ident['layout']['id']}`)\n"
            f"{ident['layout']['order']}\n\n"
            "## API\nPOST /api/booking {{name,phone,car,service,slot}}\n\n"
            "## Запреты\n"
            "Клон чужого бренда; серый hero; browser-blue; пустой media; "
            "H1 «Профессиональный/Качественный»; один photo-ID; услуги без списка; "
            "why=hero фото; footer без tel:; #f8fafc; "
            "один каркас sticky+Georgia+#vitrine всем юзерам.\n"
            "Эталон КАЧЕСТВА (не бренда/не layout): taste.md + uniqueness.md + content-fill.md.\n"
        ),
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


def _niche_instant_expand(user_text: str) -> dict[str, Any] | None:
    """Rich deterministic briefs for known niches — same quality, 0 LLM latency."""
    if _is_deck_task(user_text or "") and not re.search(
        r"(?i)автосервис|\bсто\b",
        user_text or "",
    ):
        data = _fallback_deck(user_text)
        data["source"] = "niche_instant_deck"
        data["model"] = "deterministic"
        return data
    if re.search(
        r"(?i)автосервис|сто\b|шиномонтаж|ремонт\s+авто|автомастер",
        user_text or "",
    ):
        data = _fallback_autoservice(user_text)
        data["source"] = "niche_instant"
        data["model"] = "deterministic"
        return data
    if _looks_like_app(user_text or ""):
        data = _fallback_app(user_text)
        data["source"] = "niche_instant_app"
        data["model"] = "deterministic"
        return data
    return None


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

    # Niche packs are curated — better+faster than a slow judge rewrite
    niche = _niche_instant_expand(user_text)
    if niche:
        return niche

    mid = "gemini-2.5-flash"
    if mode == "premium" and (model or "").strip():
        mid = (model or "").strip()

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
            max_tokens=1800,
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
        data = (
            _fallback_app(user_text)
            if _looks_like_app(user_text)
            else _fallback_autoservice(user_text)
        )
        data["source"] = "fallback_error"
        data["error"] = str(e)[:200]
        data["model"] = mid
        return data
