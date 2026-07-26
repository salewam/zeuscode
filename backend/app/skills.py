"""Role skills × depth — packs on disk + depth overlay by mode."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(__file__).resolve().parent / "agent_skills"


def skills_enabled() -> bool:
    """Kill-switch: when False, disk packs/refs never reach agent prompts."""
    try:
        from app.config import get_settings

        return bool(get_settings().AGENT_SKILLS_ENABLED)
    except Exception:  # noqa: BLE001
        return False

# Metadata + fallback system when pack folder missing
SKILLS: dict[str, dict[str, Any]] = {
    "frontend": {
        "title": "Фронтенд",
        "label": "фронт",
        "path_prefix": "/src/frontend",
        "system": (
            "Ты Frontend-агент ZeusCode Studio.\n"
            "Стек: HTML/CSS/JS; React — только если просят.\n"
            "Отвечай структурно:\n"
            "1) ## Мышление — короткий ход мысли (что строишь и почему)\n"
            "2) ## Результат — рабочий код в блоках ```lang path=...\n"
            "Без воды. Учитывай бриф проекта."
        ),
        "checklist": [
            "UI закрывает задачу",
            "Пусто / ошибка / загрузка учтены",
            "Мобилка не разваливается",
            "Semantic HTML + focus-visible",
            "Не AI-aesthetic (см. anti-patterns)",
            "Landing: нет 000-телефона / битых assets / вранья в catch",
        ],
        "artifact_kinds": ["code", "checklist"],
        "pack": "frontend",
        "refs_by_mode": {
            "light": ("landing-ship.md", "publish.md", "anti-patterns.md"),
            "standard": ("landing-ship.md", "publish.md", "anti-patterns.md", "checklist.md"),
            "ultra": (
                "landing-ship.md",
                "publish.md",
                "uniqueness.md",
                "content-fill.md",
                "visual-polish.md",
                "taste.md",
                "anti-patterns.md",
                "checklist.md",
                "a11y.md",
            ),
            "premium": (
                "landing-ship.md",
                "publish.md",
                "uniqueness.md",
                "content-fill.md",
                "visual-polish.md",
                "taste.md",
                "anti-patterns.md",
                "checklist.md",
                "a11y.md",
                "stack.md",
            ),
        },
        "overlay_by_mode": {
            "light": (
                "Лайт: index.html+styles.css+app.js. Label+focus-visible. Без AI-look. "
                "Лендинг: landing-ship.md — не 000-телефон, не url(assets) без файла, "
                "форма либо fetch+error либо честный offline (не success в catch). "
                "ОБЯЗАТЕЛЬНО: zeus-badge «Сделано на ZeusCode» + publish.md (живая /go/ ссылка). "
                "UNIQUE под бриф — не клон эталона."
            ),
            "standard": (
                "Стандарт: empty/error, styles.css самодостаточный (:root). "
                "Бан indigo/Inter/outline:none/div-onclick. "
                "Качество: landing-ship + publish + content-fill + visual-polish. "
                "Каркас/палитра/копирайт — из брифа (uniqueness.md), не штамп. "
                "Design tokens = свой :root, не голый @import. "
                "Бейдж ZeusCode + публичный /go/ линк обязательны."
            ),
            "ultra": (
                "Ultra: вкус + архитектура под бриф (uniqueness.md + taste.md). "
                "good_* / templates = планка качества, НЕ бренд и НЕ обязательный layout. "
                "В Мышлении: UNIQUE (бренд, ниша, signature, палитра, 3 отличия от шаблона). "
                "Must ship: живой media-якорь, честные контакты, форма без лжи, "
                "достаточная плотность контента, zeus-badge + /go/. "
                "Бан: AI-purple, egg-copy, clone эталона, browser-blue chrome."
            ),
            "premium": (
                "Premium: максимальный вкус и UNIQUE юзера (не штамп). "
                "Эталон качества = taste + uniqueness. "
                "Ноль thin_* / clone_* / missing_uniq / egg_* / missing_zeus_badge."
            ),
        },
    },
    "backend": {
        "title": "Бэкенд",
        "label": "бэк",
        "path_prefix": "/src/backend",
        "system": (
            "Ты Backend-агент ZeusCode Studio.\n"
            "Стек: FastAPI / простой HTTP API.\n"
            "Отвечай структурно:\n"
            "1) ## Мышление — контракт, риски, данные\n"
            "2) ## Результат — код API в блоках ```lang path=...\n"
            "Валидация, ошибки, без секретов. Учитывай бриф."
        ),
        "checklist": [
            "Контракт method/path/auth/codes ясен",
            "Pydantic In/Out + осмысленные 4xx",
            "Ownership / auth на данных юзера",
            "Нет секретов и SQL f-string",
            "path=/src/backend/...",
            "Если brief POST /api/booking|lead — route сдан (анти api_orphan)",
        ],
        "artifact_kinds": ["code", "checklist"],
        "pack": "backend",
        # Role-specific refs (frontend uses a11y; backend uses security)
        "refs_by_mode": {
            "light": ("landing-api.md", "checklist.md"),
            "standard": ("landing-api.md", "checklist.md", "anti-patterns.md"),
            "ultra": ("landing-api.md", "checklist.md", "anti-patterns.md", "security.md"),
            "premium": (
                "landing-api.md",
                "checklist.md",
                "anti-patterns.md",
                "security.md",
                "stack.md",
            ),
        },
        "overlay_by_mode": {
            "light": (
                "Лайт: method/path в Мышлении. Happy path + 422. "
                "Если в задаче /api/booking|lead — сдай router (landing-api.md)."
            ),
            "standard": (
                "Стандарт: контракт + коды ошибок. Pydantic In/Out + ≥1 4xx. "
                "Лендинг-brief с API → обязательный route (иначе FE api_orphan)."
            ),
            "ultra": (
                "Ultra: команда. Мышление = контракт для frontend/tests. "
                "Жёстко: anti-patterns + security. Booking/lead из brief — не пропускай."
            ),
            "premium": (
                "Premium: эталонный API. Handoff + ноль security-дыр. "
                "Locked contract = закон для FE/tests."
            ),
        },
    },
    "design": {
        "title": "Дизайн",
        "label": "дизайн",
        "path_prefix": "/src/design",
        "system": (
            "Ты Design-агент ZeusCode Studio.\n"
            "Отвечай структурно:\n"
            "1) ## Мышление — иерархия, якорь, состояния\n"
            "2) ## Результат — layout + CSS-токены / ключевые стили\n"
            "Без generic AI-look (фиолет, Inter, карточки везде)."
        ),
        "checklist": [
            "Один визуальный якорь",
            "Иерархия текста ясная",
            "Состояния UI описаны",
            "### Handoff frontend обязателен",
            "Media-строка без битых assets / без 000-телефона",
            "Только path=/src/design/...",
        ],
        "artifact_kinds": ["plan", "code", "checklist"],
        "pack": "design",
        "refs_by_mode": {
            "light": ("landing-ship.md", "anti-patterns.md"),
            "standard": ("landing-ship.md", "anti-patterns.md", "checklist.md", "media.md"),
            "ultra": ("landing-ship.md", "anti-patterns.md", "checklist.md", "media.md"),
            "premium": (
                "landing-ship.md",
                "anti-patterns.md",
                "checklist.md",
                "media.md",
                "stack.md",
            ),
        },
        "overlay_by_mode": {
            "light": (
                "Лайт: tokens.css + Handoff с Media-строкой (landing-ship). Без HTML/API."
            ),
            "standard": (
                "Стандарт: plan→tokens→### Handoff frontend (states/labels/Media). "
                "Бан indigo/Inter/outline:none/empty hero. "
                "Media: local path только если FE сдаст файл, иначе https remote OK. "
                "Только /src/design/."
            ),
            "ultra": (
                "Ultra: токены SSoT под отрасль из брифа (свой :root). "
                "Не штампуй asphalt/amber всем — только если ниша авто. "
                "Handoff: remote URL из media pack ниши. "
                "Media + veil. Контакты из брифа. Без полного UI."
            ),
            "premium": (
                "Premium: контракт под бриф. anti-patterns + landing-ship + media.md. "
                "Палитра отрасли UNIQUE, ноль AI-look / empty_hero."
            ),
        },
    },
    "tests": {
        "title": "Тесты",
        "label": "тесты",
        "path_prefix": "/src/tests",
        "system": (
            "Ты QA-агент ZeusCode Studio.\n"
            "Стек: pytest / assert.\n"
            "1) ## Мышление — кейсы по контракту\n"
            "2) ## Результат — тесты path=/src/tests/...\n"
            "Happy + негативы. Не пиши SQL f-string сервер."
        ),
        "checklist": [
            "Контракт задачи/backend",
            "Happy + ≥1 негатив",
            "Нет SQL f-string / skip",
            "path=/src/tests/...",
        ],
        "artifact_kinds": ["code", "checklist"],
        "pack": "tests",
        "refs_by_mode": {
            "standard": ("checklist.md", "anti-patterns.md"),
            "ultra": ("checklist.md", "anti-patterns.md"),
            "premium": ("checklist.md", "anti-patterns.md", "stack.md"),
        },
        "overlay_by_mode": {
            "light": (
                "Режим Лайт: 1 файл тестов, happy + 1 негатив. "
                "Контракт из задачи/backend. Без SQL f-string."
            ),
            "standard": (
                "Режим Стандарт: contract-first. "
                "Те же path/поля что у backend. Happy + 2 негатива. "
                "Запрет skip, SQL f-string, assert True / assert 1."
            ),
            "ultra": (
                "Режим Ultra: жёстко anti-patterns. "
                "Выровняй статусы 401/404 с backend. Готовность к склейке."
            ),
            "premium": (
                "Режим Premium: эталонные тесты. Сверься с good_output. Ноль drift контракта."
            ),
        },
    },
    "docs": {
        "title": "Доки",
        "label": "доки",
        "path_prefix": "/docs",
        "system": (
            "Ты Docs-агент ZeusCode Studio.\n"
            "1) ## Мышление — что важно пользователю\n"
            "2) ## Результат — короткий README / next steps"
        ),
        "checklist": ["Есть запуск", "Есть next steps"],
        "artifact_kinds": ["plan", "checklist"],
    },
    "general": {
        "title": "Ассистент",
        "label": "ассистент",
        "path_prefix": "/notes",
        "system": (
            "Ты ассистент ZeusCode Studio.\n"
            "1) ## Мышление\n2) ## Результат\n"
            "Точно по задаче. Учитывай бриф.\n"
            "Если это приветствие / «как дела» / светский вопрос — ответь "
            "коротко и по-человечески. Не пиши код, не создавай файлы, "
            "не говори что «не удалось ничего создать»."
        ),
        "checklist": [],
        "artifact_kinds": ["plan"],
    },
    "reviewer": {
        "title": "Ревьюер",
        "label": "ревью",
        "path_prefix": "/evidence",
        "system": (
            "Ты Reviewer / Evidence-агент ZeusCode Studio.\n"
            "Не пиши фичи. Scope = задача. Self-report ≠ доказательство.\n"
            "## Вердикт → PASS|FAIL|PASS_WITH_RISKS\n"
            "Не FAIL за непрошенный CRUD."
        ),
        "checklist": [
            "Вердикт в ## Вердикт",
            "Scope = задача",
            "Critical → FAIL только в scope",
            "Честно: что не доказано",
        ],
        "artifact_kinds": ["checklist", "plan"],
        "pack": "reviewer",
        "refs_by_mode": {
            "standard": ("checklist.md", "rubric.md", "anti-false-fail.md"),
            "ultra": ("checklist.md", "rubric.md", "anti-false-fail.md"),
            "premium": ("checklist.md", "rubric.md", "anti-false-fail.md"),
        },
        "overlay_by_mode": {
            "light": (
                "Кратко: вердикт + findings в scope. "
                "Лендинг: отдельно media/телефон/форма (landing-ship gates)."
            ),
            "standard": (
                "Рубрика + scope. Не FAIL за PATCH если не просили. "
                "Critical только с path и фактом. "
                "Major: api_orphan / fake_form_success / missing_asset / placeholder_contact."
            ),
            "ultra": (
                "Жёстко anti-false-fail + landing-ship. "
                "Различай вину tests vs backend. Чистый старый regex ≠ повод игнорить ship gates."
            ),
            "premium": (
                "Эталонный judge. good_output reviewer. "
                "Ноль scope creep; ноль пропуска вранья формы на лендинге."
            ),
        },
    },
}

# Progressive disclosure: SKILL.md always; refs/examples/templates capped hard.
# Token budget: prefer short anti-examples + 1–2 skeleton snippets over dumping packs.
DEPTH: dict[str, dict[str, Any]] = {
    "light": {
        "label": "лайт",
        "think": False,
        "overlay": (
            "Режим Лайт: кратко, но shippable. Мышление — 2–4 предложения. "
            "Результат — рабочие файлы, не набросок. "
            "Лендинг: landing-ship (контакты/media/форма). "
            "Не url(assets) без файла; не success в catch; не 000-телефон."
        ),
        "refs": ("landing-ship.md", "anti-patterns.md"),
        "ref_limits": {
            "landing-ship.md": 1800,
            "anti-patterns.md": 1800,
            "landing-api.md": 1400,
            "checklist.md": 1200,
        },
        "templates": True,
        "template_chars": 400,
        "template_max_files": 1,
        "include_examples": True,
        "example_mode": "micro",
    },
    "standard": {
        "label": "стандарт",
        # Think phase = лишний LLM-раунд: мышление уже в ## Мышление основного ответа
        "think": False,
        "overlay": (
            "Режим Стандарт: нормальная глубина. "
            "Мышление в ## Мышление — максимум 6–8 строк, без воды. "
            "Результат рабочий и чистый. "
            "Обязательно empty/error если async/список; токены CSS. "
            "ЗАПРЕТ: outline:none; indigo/purple/Inter (даже «как бренд»); div onclick. "
            "Обязателен :focus-visible на интерактив. "
            "font-family без Inter/Roboto — только system-ui / ui-sans-serif / бриф-шрифт ≠ Inter. "
            "Лендинг: landing-ship.md обязателен (media/API/контакты)."
        ),
        "refs": ("landing-ship.md", "checklist.md", "anti-patterns.md"),
        "ref_limits": {
            "landing-ship.md": 1800,
            "checklist.md": 2000,
            "anti-patterns.md": 2400,
            "landing-api.md": 1600,
            "media.md": 1400,
            "stack.md": 1600,
        },
        "templates": True,
        "template_chars": 500,
        "template_max_files": 2,
        "include_examples": True,
        "example_mode": "micro",  # bad only, tiny
    },
    "ultra": {
        "label": "ultra",
        "think": False,
        "overlay": (
            "Режим Ultra: команда из 4. Мышление 6–8 строк. "
            "Frontend: uniqueness.md + taste — UNIQUE под бриф "
            "(бренд/IA/палитра/копирайт свои). "
            "Эталоны good_* = планка качества, НЕ layout и НЕ классы. "
            "Must: media-якорь, честные контакты, форма без лжи, плотность, "
            "zeus-badge + /go/. Бан: AI-purple, egg-copy, clone чужого бренда."
        ),
        "refs": (
            "landing-ship.md",
            "publish.md",
            "uniqueness.md",
            "content-fill.md",
            "visual-polish.md",
            "taste.md",
            "checklist.md",
            "anti-patterns.md",
            "a11y.md",
            "media.md",
        ),
        "ref_limits": {
            "landing-ship.md": 2800,
            "publish.md": 1600,
            "uniqueness.md": 2200,
            "content-fill.md": 3200,
            "visual-polish.md": 2800,
            "taste.md": 3200,
            "checklist.md": 2200,
            "anti-patterns.md": 2600,
            "a11y.md": 1800,
            "security.md": 1800,
            "landing-api.md": 1800,
            "media.md": 2800,
            "stack.md": 1600,
        },
        "templates": True,
        "template_chars": 1000,
        "template_max_files": 3,
        "include_examples": True,
        "example_mode": "landing",
    },
    "premium": {
        "label": "premium",
        # Отдельный think оставляем только в premium — эталонный план
        "think": True,
        "overlay": (
            "Режим Premium: максимальное качество. "
            "Мышление: план + риски + handoff (компактно). Результат эталонный. "
            "Сверься с good_* как с планкой качества (не клонируй бренд/layout); не повторяй bad_output. "
            "Ноль AI-aesthetic. Ноль api_orphan / fake_form_success / missing_asset / "
            "thin_landing / no_hero_media."
        ),
        "refs": (
            "landing-ship.md",
            "checklist.md",
            "anti-patterns.md",
            "a11y.md",
            "stack.md",
            "media.md",
        ),
        "ref_limits": {
            "landing-ship.md": 2800,
            "checklist.md": 2800,
            "anti-patterns.md": 3000,
            "a11y.md": 2200,
            "stack.md": 2000,
            "security.md": 2200,
            "landing-api.md": 1800,
            "media.md": 2200,
        },
        "templates": True,
        "template_chars": 900,
        "template_max_files": 3,
        "include_examples": True,
        "example_mode": "full",
    },
}

INTENT_TEAMS: dict[str, list[str]] = {
    "feature": ["design", "frontend", "backend", "tests"],
    "app": ["design", "frontend", "backend", "tests"],
    "bug": ["backend", "frontend", "tests", "design"],
    "ui": ["frontend", "design", "backend", "tests"],
    "api": ["backend", "tests", "frontend", "design"],
    "tests": ["tests", "backend", "frontend", "design"],
    "refactor": ["backend", "frontend", "tests", "design"],
    "ask": ["general"],
}

INTENT_META: dict[str, dict[str, str]] = {
    "feature": {"title": "Фича", "hint": "собрать кусок продукта"},
    "app": {"title": "Приложение", "hint": "экраны + действие + данные"},
    "bug": {"title": "Баг", "hint": "найти и починить"},
    "ui": {"title": "UI", "hint": "экран и визуал"},
    "api": {"title": "API", "hint": "эндпоинты и контракт"},
    "tests": {"title": "Тесты", "hint": "покрытие и регрессия"},
    "refactor": {"title": "Рефактор", "hint": "упростить без поломок"},
    "ask": {"title": "Спросить", "hint": "быстрый ответ"},
}

THINK_PROMPT = (
    "Только фаза мышления. Не пиши финальный код.\n"
    "За 4–8 предложений: что ты (роль) сделаешь по задаче, "
    "какие риски, что отдашь команде. Коротко и по делу."
)

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def _strip_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text, count=1).strip()


def _read_text(path: Path, limit: int | None = None) -> str:
    if not path.is_file():
        return ""
    raw = path.read_text(encoding="utf-8")
    if limit is not None and len(raw) > limit:
        return raw[:limit].rstrip() + "\n\n…[truncated]"
    return raw


@lru_cache(maxsize=16)
def load_skill_pack(pack_name: str) -> dict[str, Any] | None:
    """Load agent_skills/<pack>/SKILL.md + reference index. Cached."""
    if not skills_enabled():
        return None
    root = SKILLS_ROOT / pack_name
    skill_md = root / "SKILL.md"
    if not skill_md.is_file():
        return None
    body = _strip_frontmatter(_read_text(skill_md))
    refs_dir = root / "references"
    examples_dir = root / "examples"
    templates_dir = root / "assets" / "templates"
    return {
        "name": pack_name,
        "root": root,
        "system": body,
        "refs_dir": refs_dir,
        "examples_dir": examples_dir,
        "templates_dir": templates_dir,
        "has_verify": (root / "scripts" / "verify.sh").is_file(),
    }


def _pack_ref(pack: dict[str, Any], name: str, limit: int = 6000) -> str:
    path = pack["refs_dir"] / name
    text = _read_text(path, limit=limit)
    if not text:
        return ""
    return f"### references/{name}\n\n{text}"


def _pack_examples(pack: dict[str, Any], *, mode: str = "full") -> str:
    """Examples: micro=bad-only; landing=STO good+bad; full=good+auth+bad."""
    ex_dir: Path = pack["examples_dir"]
    if mode == "micro":
        bad = _read_text(ex_dir / "bad_output.md", limit=1400)
        if not bad:
            return ""
        return (
            "### Anti-example (не так — ужато)\n\n"
            + bad
            + "\n\nПравило: если похоже на anti-example — перепиши до сдачи."
        )
    blocks: list[str] = []
    if mode == "app":
        good = _read_text(ex_dir / "good_app.md", limit=4200)
        if good:
            blocks.append("### examples/good_app.md (планка app)\n\n" + good)
        blocks.append(
            "### APP CONTRACT (не клон шаблона)\n\n"
            "Сдай **уникальное** приложение под бриф юзера: свой бренд, ниша, "
            "копирайт, визуал, поля карточек. "
            "Шаблоны `app-shop*` — пример рабочих потоков, **не** обязательный UI.\n\n"
            "DoD: shell+nav ≥2 экрана; каталог из API с фото+CTA; "
            "заказ или корзина с fetch+res.ok; история заказов; "
            "filters ↔ seed; логика только в app.js; API=\".\"; "
            "не 2KB-скелет (HTML≥3KB, CSS≥4KB, JS≥3.5KB).\n\n"
            "ЗАПРЕТ: сдать «Букет Лайн/Свежая Полка» byte-for-byte; "
            "лендинг; inline `<script>`; React без просьбы; мёртвые CTA."
        )
        # No HTML dump from app-shop — even truncated markup biases clones
        blocks.append(
            "### Density hint (без HTML-эталона)\n\n"
            "Экраны: header+nav → каталог → заказ/корзина → история. "
            "Разметку, CSS и копирайт изобрети под **этот** бриф."
        )
        bad = _read_text(ex_dir / "bad_app_as_landing.md", limit=1400)
        if bad:
            blocks.append("### examples/bad_app_as_landing.md\n\n" + bad)
        return "\n\n".join(blocks) if blocks else ""
    if mode == "landing":
        # Never inject MotorHaus HTML — stamps every landing into one layout.
        blocks.append(
            "### Планка лендинга (без эталонного HTML)\n\n"
            "Каждый бриф = свой бренд, IA, палитра, копирайт (`uniqueness.md`).\n"
            "Must: media-якорь, честные контакты, форма без лжи, достаточная плотность, "
            "zeus-badge + /go/.\n"
            "Бан: AI-purple/Inter, egg-copy, клон чужого бренда, пустой hero.\n"
            "Файл `good_landing_sto.md` на диске — пример **только** для авто-ниши; "
            "в промпт полный HTML **не** кладём.\n"
        )
        bad = _read_text(ex_dir / "bad_output.md", limit=1600)
        if bad:
            blocks.append("### examples/bad_output.md (не так)\n\n" + bad)
        return "\n\n".join(blocks)
    # default/full: prefer small goods, never dump entire STO landing HTML
    for name in ("good_output.md", "good_deck.md", "good_auth.md"):
        lim = 2800 if name != "good_auth.md" else 2000
        text = _read_text(ex_dir / name, limit=lim)
        if text:
            blocks.append(f"### examples/{name} (планка)\n\n" + text)
    if ex_dir.joinpath("good_landing_sto.md").is_file():
        blocks.append(
            "### good_landing_sto — напоминание\n\n"
            "Эталон СТО = планка плотности для авто-ниши. "
            "Другая ниша → свой layout/палитра. Не клонируй МоторХаус.\n"
        )
    bad = _read_text(ex_dir / "bad_output.md", limit=1600)
    if bad:
        blocks.append("### examples/bad_output.md (не так)\n\n" + bad)
    return "\n\n".join(blocks)


_TEMPLATE_PRIORITY: dict[str, tuple[str, ...]] = {
    "frontend": ("styles.css", "form.html", "app.js"),
    "backend": ("schemas.py", "router.py", "deps_auth.py"),
    "design": ("tokens.css",),
    "tests": ("test_resource.py",),  # not test_sample (inline FastAPI trap)
}


def _template_snippets(
    pack: dict[str, Any],
    *,
    max_files: int = 2,
    chars: int = 500,
) -> str:
    """Cheap skeletons: 1–2 files truncated — not full dumps."""
    td: Path = pack["templates_dir"]
    if not td.is_dir():
        return ""
    pack_name = pack.get("name") or "frontend"
    preferred = list(_TEMPLATE_PRIORITY.get(pack_name) or ())
    available = {p.name: p for p in td.iterdir() if p.is_file()}
    chosen: list[Path] = []
    for name in preferred:
        if name in available:
            chosen.append(available[name])
        if len(chosen) >= max_files:
            break
    if not chosen:
        chosen = sorted(available.values(), key=lambda p: p.name)[:max_files]
    if not chosen:
        return ""
    prefix = f"/src/{pack_name}/"
    lines = [
        f"Скелеты (адаптируй под задачу, path={prefix}…; не копируй слепо):",
    ]
    for p in chosen:
        body = _read_text(p, limit=chars)
        lines.append(f"\n#### assets/templates/{p.name}\n```\n{body}\n```")
    return "\n".join(lines)


def _template_index(pack: dict[str, Any]) -> str:
    """Fallback name-only index if snippets empty."""
    td: Path = pack["templates_dir"]
    if not td.is_dir():
        return ""
    names = sorted(p.name for p in td.iterdir() if p.is_file())
    if not names:
        return ""
    pack_name = pack.get("name") or "frontend"
    return (
        f"Скелеты в assets/templates/: {', '.join(names)}. "
        f"Клади код в /src/{pack_name}/..."
    )


def get_skill(role: str) -> dict[str, Any]:
    base = dict(SKILLS.get(role) or SKILLS["general"])
    pack_name = base.get("pack") or (role if role in SKILLS else None)
    if pack_name:
        pack = load_skill_pack(pack_name)
        if pack and pack.get("system"):
            base["system"] = pack["system"]
            base["pack_loaded"] = True
            base["pack_name"] = pack_name
    return base


def get_depth(mode: str) -> dict[str, Any]:
    return DEPTH.get(mode) or DEPTH["standard"]


def team_for_intent(intent: str) -> list[str]:
    return list(INTENT_TEAMS.get(intent) or INTENT_TEAMS["feature"])


_ROLE_TASK_SIGNALS: dict[str, tuple[str, ...]] = {
    "backend": (
        r"/api/",
        r"\b(fastapi|endpoint|router|pydantic|Bearer|auth|JWT|Depends)\b",
        r"\b(POST|GET|PUT|PATCH|DELETE)\s+/",
        r"\b(бэкенд|backend|сервер|эндпоинт)\b",
    ),
    "frontend": (
        r"\b(html|css|js|react|лендинг|ленд|landing|сайт|экран|кнопк|форм[аыу]|ui|интерфейс|страниц)\b",
        r"\b(frontend|фронт)\b",
        r"\b(автосервис|сто\b|кофейн|магазин|клиник|салон)\b",
    ),
    "design": (
        r"\b(дизайн|design|токен|палитр|типограф|layout|handoff|tokens\.css)\b",
    ),
    "tests": (
        r"\b(pytest|тест|tests?|assert|покрыт)\b",
    ),
}


def infer_intent_from_task(task: str | None, fallback: str = "feature") -> str:
    """Guess Studio intent from free-text when UI left default 'feature'."""
    t = (task or "").strip()
    if not t:
        return fallback
    low = t.lower()
    # Web app / tool product (before generic landing "сайт")
    app_hit = bool(
        re.search(
            r"(?i)(приложени[еяю]|web[-\s]?apps?|\bapps?\b|сервис\b|инструмент|"
            r"кабинет|dashboard|to-?do|задач[аи]|"
            r"список\s+\w+|созда(ть|вай).{0,40}(задач|запис|элемент)|"
            r"\bcrm\b|учёт\b)",
            low,
        )
    )
    landing_hit = bool(
        re.search(
            r"(?i)(лендинг|ленд\b|landing|визитк|одностраничн|"
            r"автосервис|\bсто\b|кофейн|салон\s+красот)",
            low,
        )
    )
    if app_hit and not landing_hit:
        return "app"
    if app_hit and re.search(r"\b(экран|навигац|список|создать|кабинет)\b", low):
        return "app"

    scores = {k: 0 for k in ("api", "ui", "tests", "bug", "refactor", "ask")}
    if re.search(r"/api/|\bfastapi\b|\bendpoint\b|\bbearer\b|\bauth\b", low):
        scores["api"] += 3
    if re.search(r"\b(post|get|put|patch|delete)\s+/api/", low):
        scores["api"] += 2
    if re.search(r"\b(лендинг|ленд|landing|сайт|экран|кнопк|html|css|ui|форм[аыу]|страниц)\b", low):
        scores["ui"] += 3
    if re.search(r"\b(автосервис|сто\b|кофейн|магазин|клиник|салон)\b", low):
        scores["ui"] += 2
    if re.search(r"\b(pytest|тест|assert|покрыт)\b", low):
        scores["tests"] += 2
    if re.search(r"\b(баг|bug|почин|сломал|fix)\b", low):
        scores["bug"] += 2
    if re.search(r"\b(рефактор|refactor|упрост)\b", low):
        scores["refactor"] += 2
    # Chitchat / Q&A — never route to design team
    if len(t) < 120 and re.search(
        r"^(привет|здравствуй|здарова|добр(ый|ое|ого)|hello|hi|hey|yo)\b",
        low,
    ):
        scores["ask"] += 4
    if len(t) < 80 and re.fullmatch(
        r"(как дела|как жизнь|что нового|how are you|what'?s up)"
        r"[\s\?!\.]*",
        low,
    ):
        scores["ask"] += 4
    if len(t) < 40 and re.fullmatch(
        r"(спасибо|thanks|thank you|ок|окей|ладно|понял|понятно)[\s\!\.]*",
        low,
    ):
        scores["ask"] += 4
    if re.search(r"^(что|как|зачем|почему)\b|\?$", low) and len(t) < 120:
        scores["ask"] += 2
    best = max(scores, key=lambda k: scores[k])
    if scores[best] <= 0:
        return fallback
    # Landing + API together → full feature team (FE+BE), never API-only
    if scores["ui"] >= 3 and scores["api"] >= 3:
        return "feature"
    # API+tests phrasing → api (backend first) unless UI dominates
    if scores["api"] >= 3 and scores["ui"] < 3:
        return "api"
    if scores["ui"] >= 3 and scores["api"] < 3:
        return "ui"
    if best == "tests" and scores["api"] >= 2:
        return "api"
    return best


def rank_roles_for_task(task: str | None, team: list[str]) -> list[str]:
    """Reorder team so the most relevant roles come first when cutting to N agents."""
    if not team:
        return team
    text = task or ""
    scores: dict[str, int] = {}
    for i, role in enumerate(team):
        score = 0
        for pat in _ROLE_TASK_SIGNALS.get(role) or ():
            if re.search(pat, text, re.I):
                score += 2
        # slight preference to original intent order as tie-breaker (lower i = better)
        scores[role] = score * 100 - i
    return sorted(team, key=lambda r: scores.get(r, 0), reverse=True)


def build_role_system(role: str, brief: str | None, intent: str, mode: str) -> str:
    skill = get_skill(role)
    if not skills_enabled():
        # Minimal role prompt — no pack SKILL.md / refs / examples / templates.
        parts = [
            skill.get("system") or f"Ты {skill.get('title') or role}-агент ZeusCode.",
            "Скилл-паки отключены (AGENT_SKILLS_ENABLED=false). Работай по брифу и ТЗ пользователя.",
        ]
        if brief and brief.strip():
            parts.append(f"\nБриф проекта:\n{brief.strip()[:3500]}")
        intent_title = INTENT_META.get(intent, {}).get("title", intent)
        parts.append(f"\nИнтент: {intent_title}.")
        return "\n".join(parts)

    depth = get_depth(mode)
    overlay = (skill.get("overlay_by_mode") or {}).get(mode) or depth["overlay"]
    if intent == "app" and role in ("frontend", "design"):
        overlay = (
            "Интент APP: изобрети мини-приложение **под бриф** (бренд, ниша, визуал, копирайт). "
            "Не клонируй один шаблон всем юзерам. DoD = рабочие потоки, не имена CSS-классов. "
            "Обязательно: nav≥2 экрана; каталог из API (фото+цена+CTA); "
            "заказ или корзина с fetch+res.ok; экран истории; filters↔seed; "
            "index.html+styles.css+app.js; логика только в app.js; API=\".\". "
            "Плотность: не 2KB-скелет (HTML≥3KB CSS≥4KB JS≥3.5KB). "
            "Шаблоны app-shop* — справка по плотности, не pixel-clone. "
            "ЗАПРЕТ: React без просьбы, alert-success, onclick, inline script, "
            "лендинг вместо shell, мёртвые картинки, grocery без корзины."
        )
    if intent == "app" and role == "backend":
        overlay = (
            "Интент APP: /api из brief. Seed ≥4 с image=unsplash, поле **name** (не title), "
            "desc|description|composition, tag|category. "
            "category/tag значения = ТОЧНО data-filter на FE (не хит при Овощи). "
            "POST orders → *_name из item['name']. APIRouter(prefix=\"/api\") + include_router. "
            "См. app-api.md."
        )
    parts = [
        skill["system"],
        "",
        f"Глубина скилла ({depth['label']}):",
        overlay,
    ]

    pack_name = skill.get("pack_name") or skill.get("pack")
    pack = load_skill_pack(pack_name) if pack_name else None
    if pack:
        ref_names = list(
            (skill.get("refs_by_mode") or {}).get(mode) or depth.get("refs") or ()
        )
        if intent == "app" and role == "frontend":
            # Prefer app-shell over landing-ship for apps
            ref_names = [
                "app-shell.md" if n == "landing-ship.md" else n for n in ref_names
            ]
            if "app-shell.md" not in ref_names:
                ref_names = ["app-shell.md", *ref_names]
        if intent == "app" and role == "design":
            ref_names = [
                "app-shell.md" if n == "landing-ship.md" else n for n in ref_names
            ]
            if "app-shell.md" not in ref_names and (pack["refs_dir"] / "app-shell.md").is_file():
                ref_names = ["app-shell.md", *ref_names]
            # design pack may not have app-shell — frontend does; skip missing
        if intent == "app" and role == "backend":
            ref_names = [
                "app-api.md" if n == "landing-api.md" else n for n in ref_names
            ]
            if "app-api.md" not in ref_names:
                ref_names = ["app-api.md", *ref_names]
        limits = dict(depth.get("ref_limits") or {})
        limits.setdefault("app-shell.md", 3200)
        limits.setdefault("app-api.md", 2200)
        if "security.md" in ref_names and "security.md" not in limits:
            limits = {**limits, "security.md": 1800}
        ref_blocks = []
        for n in ref_names:
            # design: load app-shell from frontend pack if missing locally
            block = _pack_ref(pack, n, limit=int(limits.get(n, 2000)))
            if not block and n == "app-shell.md" and role == "design":
                fe = load_skill_pack("frontend")
                if fe:
                    block = _pack_ref(fe, n, limit=int(limits.get(n, 2000)))
            if block:
                ref_blocks.append(block)
        if ref_blocks:
            parts.append("\n## Reference pack (учти, ужато)\n")
            parts.extend(ref_blocks)

        if depth.get("include_examples"):
            ex_mode = depth.get("example_mode") or ("full" if mode == "premium" else "micro")
            if intent == "app" and role == "frontend":
                ex_mode = "app"
            ex = _pack_examples(pack, mode=ex_mode)
            if ex:
                parts.append("\n## Examples\n" + ex)

        if depth.get("templates"):
            tmpl = _template_snippets(
                pack,
                max_files=int(depth.get("template_max_files") or 2),
                chars=int(depth.get("template_chars") or 500),
            ) or _template_index(pack)
            if tmpl:
                parts.append("\n## Templates\n" + tmpl)

    if brief and brief.strip():
        # Landing briefs carry Unsplash URLs + service packs — don't truncate to death
        brief_lim = 6000 if mode in ("ultra", "premium") else 3500
        parts.append(f"\nБриф проекта:\n{brief.strip()[:brief_lim]}")
    intent_title = INTENT_META.get(intent, {}).get("title", intent)
    parts.append(f"\nИнтент: {intent_title}.")

    checklist = skill.get("checklist") or []
    if intent == "app" and role == "frontend":
        checklist = [
            "Уникальный UI под бриф (не клон эталона)",
            "Shell: бренд + nav ≥2 экрана + status/toast",
            "Каталог: API + img + CTA; filters ↔ seed",
            "Заказ/корзина + история с fetch и res.ok",
            "Логика только в app.js; API=\".\"",
            "Без React/alert/onclick/лендинга",
        ]
    if checklist and mode in ("ultra", "premium", "standard", "light"):
        n = 4 if mode == "light" else 6
        parts.append("\nЧеклист роли:\n- " + "\n- ".join(checklist[:n]))
    return "\n".join(parts)


def split_thinking_result(text: str) -> tuple[str, str]:
    """Split ## Мышление / ## Результат if present."""
    raw = text or ""
    lower = raw.lower()
    markers = [
        ("## мышление", "## результат"),
        ("## thinking", "## result"),
        ("### мышление", "### результат"),
    ]
    for think_m, result_m in markers:
        ti = lower.find(think_m)
        ri = lower.find(result_m)
        if ti >= 0 and ri > ti:
            thinking = raw[ti:ri].split("\n", 1)[-1].strip()
            result = raw[ri:].split("\n", 1)[-1].strip()
            return thinking, result
    parts = raw.strip().split("\n\n", 1)
    if len(parts) == 2 and len(parts[0]) < 600:
        return parts[0].strip(), parts[1].strip()
    return "", raw
