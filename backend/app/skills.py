"""Role skills × depth — packs on disk + depth overlay by mode."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(__file__).resolve().parent / "agent_skills"

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
        ],
        "artifact_kinds": ["code", "checklist"],
        "pack": "frontend",
        "refs_by_mode": {
            "standard": ("anti-patterns.md", "checklist.md"),
            "ultra": ("anti-patterns.md", "checklist.md", "a11y.md"),
            "premium": ("anti-patterns.md", "checklist.md", "a11y.md", "stack.md"),
        },
        "overlay_by_mode": {
            "light": (
                "Лайт: 1–2 файла, happy path, label+focus-visible. Без AI-look."
            ),
            "standard": (
                "Стандарт: empty/error, styles.css, system-ui. "
                "Бан indigo/Inter/outline:none/div-onclick. Design tokens = SSoT если есть."
            ),
            "ultra": (
                "Ultra: команда. Handoff path/поля для tests. Полный DoD + a11y. "
                "Не пиши /src/frontend/tokens.css — только styles.css (+ @import design)."
            ),
            "premium": (
                "Premium: эталон. Сверь anti-patterns. Ноль AI-look."
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
        ],
        "artifact_kinds": ["code", "checklist"],
        "pack": "backend",
        # Role-specific refs (frontend uses a11y; backend uses security)
        "refs_by_mode": {
            "standard": ("checklist.md", "anti-patterns.md"),
            "ultra": ("checklist.md", "anti-patterns.md", "security.md"),
            "premium": (
                "checklist.md",
                "anti-patterns.md",
                "security.md",
                "stack.md",
            ),
        },
        "overlay_by_mode": {
            "light": (
                "Режим Лайт: очень кратко. Мышление — 2 предложения (method/path). "
                "Результат — минимум кода, happy path + базовая валидация."
            ),
            "standard": (
                "Режим Стандарт: нормальная глубина. "
                "Мышление: контракт + коды ошибок. "
                "Обязательно Pydantic In/Out и хотя бы один осмысленный 4xx; ownership если ресурс юзера."
            ),
            "ultra": (
                "Режим Ultra: ты часть команды. "
                "Мышление покажи явно (контракт для frontend/tests). "
                "Результат полный, готовый к склейке. "
                "Жёстко: anti-patterns + security. Без «auth потом»."
            ),
            "premium": (
                "Режим Premium: максимальное качество API. "
                "Мышление: контракт + риски + handoff. Результат эталонный. "
                "Сверься с good_output; не повторяй bad_output. "
                "Ноль security-дыр."
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
            "Только path=/src/design/...",
        ],
        "artifact_kinds": ["plan", "code", "checklist"],
        "pack": "design",
        "refs_by_mode": {
            "standard": ("anti-patterns.md", "checklist.md", "media.md"),
            "ultra": ("anti-patterns.md", "checklist.md", "media.md"),
            "premium": ("anti-patterns.md", "checklist.md", "media.md", "stack.md"),
        },
        "overlay_by_mode": {
            "light": (
                "Лайт: tokens.css + 3 буллета handoff. Без HTML/API."
            ),
            "standard": (
                "Стандарт: plan→tokens→### Handoff frontend (states/labels/Media). "
                "Бан indigo/Inter/outline:none/empty hero. Media=фото сюжета (media.md). "
                "Только /src/design/."
            ),
            "ultra": (
                "Ultra: команда. Токены SSoT для frontend. "
                "Обязательны loading/empty/error + Media-строка в handoff. Без полного UI."
            ),
            "premium": (
                "Premium: эталонный контракт. Сверь anti-patterns. Ноль AI-look."
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
            "light": "Кратко: вердикт + 1–3 findings в scope задачи.",
            "standard": (
                "Рубрика + scope. Не FAIL за PATCH если не просили. "
                "Critical только с path и фактом."
            ),
            "ultra": (
                "Жёстко anti-false-fail. "
                "Различай вину tests vs backend. Чистый gate ≠ повод выдумывать critical."
            ),
            "premium": (
                "Эталонный judge. Сверься с good_output reviewer. Ноль scope creep."
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
            "Режим Лайт: очень кратко. Мышление — 2 предложения. "
            "Результат — минимум кода, только суть. "
            "States можно кратко описать, не раздувай."
        ),
        "refs": (),
        "templates": False,
        "include_examples": False,
        "example_mode": None,
    },
    "standard": {
        "label": "стандарт",
        "think": True,
        "overlay": (
            "Режим Стандарт: нормальная глубина. "
            "Мышление короткое, результат рабочий и чистый. "
            "Обязательно empty/error если async/список; токены CSS. "
            "ЗАПРЕТ: outline:none; indigo/purple/Inter (даже «как бренд»); div onclick. "
            "Обязателен :focus-visible на интерактив. "
            "font-family без Inter/Roboto — только system-ui / ui-sans-serif / бриф-шрифт ≠ Inter."
        ),
        "refs": ("checklist.md", "anti-patterns.md"),
        "ref_limits": {"checklist.md": 1800, "anti-patterns.md": 2200, "stack.md": 1600},
        "templates": True,
        "template_chars": 500,
        "template_max_files": 2,
        "include_examples": True,
        "example_mode": "micro",  # bad only, tiny
    },
    "ultra": {
        "label": "ultra",
        "think": True,
        "overlay": (
            "Режим Ultra: ты часть команды из 4 агентов. "
            "Мышление покажи явно (что делаешь для кооператива). "
            "Результат полный, готовый к склейке. "
            "Жёстко: anti-patterns + a11y. Не AI-look. "
            "ЗАПРЕТ outline:none / indigo / Inter (нет исключений ради бренда). "
            "Только :focus-visible + system-ui."
        ),
        "refs": ("checklist.md", "anti-patterns.md", "a11y.md"),
        "ref_limits": {
            "checklist.md": 2000,
            "anti-patterns.md": 2400,
            "a11y.md": 1800,
            "security.md": 1800,
            "stack.md": 1600,
        },
        "templates": True,
        "template_chars": 600,
        "template_max_files": 2,
        "include_examples": True,
        "example_mode": "micro",
    },
    "premium": {
        "label": "premium",
        "think": True,
        "overlay": (
            "Режим Premium: максимальное качество. "
            "Мышление: план + риски + handoff. Результат эталонный. "
            "Сверься с good_output; не повторяй bad_output. "
            "Ноль AI-aesthetic."
        ),
        "refs": ("checklist.md", "anti-patterns.md", "a11y.md", "stack.md"),
        "ref_limits": {
            "checklist.md": 2800,
            "anti-patterns.md": 3000,
            "a11y.md": 2200,
            "stack.md": 2000,
            "security.md": 2200,
        },
        "templates": True,
        "template_chars": 800,
        "template_max_files": 3,
        "include_examples": True,
        "example_mode": "full",
    },
}

INTENT_TEAMS: dict[str, list[str]] = {
    "feature": ["design", "frontend", "backend", "tests"],
    "bug": ["backend", "frontend", "tests", "design"],
    "ui": ["frontend", "design", "backend", "tests"],
    "api": ["backend", "tests", "frontend", "design"],
    "tests": ["tests", "backend", "frontend", "design"],
    "refactor": ["backend", "frontend", "tests", "design"],
    "ask": ["general"],
}

INTENT_META: dict[str, dict[str, str]] = {
    "feature": {"title": "Фича", "hint": "собрать кусок продукта"},
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
    """Examples: micro = bad-only tiny (cheap); full = good+bad for premium."""
    ex_dir: Path = pack["examples_dir"]
    if mode == "micro":
        bad = _read_text(ex_dir / "bad_output.md", limit=900)
        if not bad:
            return ""
        return (
            "### Anti-example (не так — 900 символов)\n\n"
            + bad
            + "\n\nПравило: если похоже на anti-example — перепиши до сдачи."
        )
    blocks: list[str] = []
    for name in ("good_output.md", "good_auth.md"):
        text = _read_text(ex_dir / name, limit=2800 if name == "good_output.md" else 2000)
        if text:
            blocks.append(f"### examples/{name} (планка)\n\n" + text)
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
        r"\b(html|css|js|react|лендинг|экран|кнопк|форм[аыу]|ui|интерфейс|страниц)\b",
        r"\b(frontend|фронт)\b",
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
    scores = {k: 0 for k in ("api", "ui", "tests", "bug", "refactor", "ask")}
    if re.search(r"/api/|\bfastapi\b|\bendpoint\b|\bbearer\b|\bauth\b", low):
        scores["api"] += 3
    if re.search(r"\b(post|get|put|patch|delete)\s+/api/", low):
        scores["api"] += 2
    if re.search(r"\b(лендинг|экран|кнопк|html|css|ui|форм[аыу]|страниц)\b", low):
        scores["ui"] += 3
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
    depth = get_depth(mode)
    overlay = (skill.get("overlay_by_mode") or {}).get(mode) or depth["overlay"]
    parts = [
        skill["system"],
        "",
        f"Глубина скилла ({depth['label']}):",
        overlay,
    ]

    pack_name = skill.get("pack_name") or skill.get("pack")
    pack = load_skill_pack(pack_name) if pack_name else None
    if pack:
        ref_names = (skill.get("refs_by_mode") or {}).get(mode) or depth.get("refs") or ()
        limits = depth.get("ref_limits") or {}
        if "security.md" in ref_names and "security.md" not in limits:
            limits = {**limits, "security.md": 1800}
        ref_blocks = [
            _pack_ref(pack, n, limit=int(limits.get(n, 2000))) for n in ref_names
        ]
        ref_blocks = [b for b in ref_blocks if b]
        if ref_blocks:
            parts.append("\n## Reference pack (учти, ужато)\n")
            parts.extend(ref_blocks)

        if depth.get("include_examples"):
            ex_mode = depth.get("example_mode") or ("full" if mode == "premium" else "micro")
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
        parts.append(f"\nБриф проекта:\n{brief.strip()[:1500]}")
    intent_title = INTENT_META.get(intent, {}).get("title", intent)
    parts.append(f"\nИнтент: {intent_title}.")

    checklist = skill.get("checklist") or []
    if checklist and mode in ("ultra", "premium", "standard"):
        parts.append("\nЧеклист роли:\n- " + "\n- ".join(checklist[:6]))
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
