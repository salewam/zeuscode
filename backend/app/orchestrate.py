"""Studio orchestration: role skills × mode depth + live cooperative stream."""

from __future__ import annotations

import asyncio
import contextvars
import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app import upstream
from app.brief_expand import (
    expand_task_brief,
    format_expanded_brief,
    inject_api_prelock,
    needs_expand,
)
from app.catalog import get_model
from app.config import get_settings
from app import evidence as evidence_mod
from app.skills import (
    INTENT_META,
    THINK_PROMPT,
    build_role_system,
    get_depth,
    get_skill,
    infer_intent_from_task,
    rank_roles_for_task,
    split_thinking_result,
    team_for_intent,
)

settings = get_settings()

MODES = ("light", "standard", "ultra", "premium")

# Code agents = cheap Flash; synth+reviewer = stronger judge
CHEAP_MODEL = "gemini-2.5-flash"
JUDGE_ROLES = frozenset({"synth", "reviewer"})
_ROLES = (
    "frontend",
    "backend",
    "design",
    "tests",
    "docs",
    "general",
    "synth",
    "think",
    "reviewer",
)
ROLE_MODELS: dict[str, dict[str, str]] = {
    mode: {role: CHEAP_MODEL for role in _ROLES} for mode in MODES
}

# Per-run overrides from cabinet pack: judge + workers
_TEAM_MODEL_MAP: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "studio_team_model_map", default=None
)
_MODEL_FAMILY: contextvars.ContextVar[str] = contextvars.ContextVar(
    "studio_model_family", default=""
)

MODE_META: dict[str, dict[str, Any]] = {
    "light": {
        "title": "Лайт",
        "hint": "1 агент",
        "parallel": False,
        "max_agents": 1,
        "history_limit": 8,
    },
    "standard": {
        "title": "Стандарт",
        "hint": "2 агента",
        "parallel": True,
        "max_agents": 2,
        "history_limit": 16,
    },
    "ultra": {
        "title": "Ultra",
        "hint": "4 агента + сборка",
        "parallel": True,
        "max_agents": 4,
        "history_limit": 20,
    },
    "premium": {
        "title": "Premium",
        "hint": "4 топ + сборка",
        "parallel": True,
        "max_agents": 4,
        "history_limit": 28,
    },
}

_CODE_FENCE = re.compile(
    r"```(?P<lang>[\w.+-]*)?(?:[^\n]*?(?:path|file)=(?P<path>[^\s\n]+))?[^\n]*\n(?P<body>.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def normalize_mode(mode: str | None) -> str:
    m = (mode or "ultra").strip().lower()
    if m in ("studio-light", "lite"):
        return "light"
    if m in ("studio-standard", "solo", "normal"):
        return "standard"
    if m in ("studio-ultra", "ultra-mode", "ultra", "onestack-ultra"):
        return "ultra"
    if m in ("studio-premium", "premium"):
        return "premium"
    return m if m in MODES else "ultra"


def normalize_intent(intent: str | None) -> str:
    i = (intent or "feature").strip().lower()
    return i if i in INTENT_META else "feature"


def resolve_team(
    intent: str,
    mode: str,
    agents_n: int | None = None,
    user_text: str | None = None,
) -> list[str]:
    """Pick roles. agents_n wins over mode max_agents.

    When UI sends default intent=feature but the task is clearly API/UI/…,
    infer intent from text. When cutting to N<4, rank roles by task relevance
    so API tasks don't get design+frontend.

    Ask / chitchat always stays a single general reply — never inflate to
    design+frontend just because the UI requested N>1 agents.
    """
    effective = intent
    if user_text and intent in ("feature", "ask"):
        guessed = infer_intent_from_task(user_text, fallback=intent)
        if intent == "feature" and guessed != "feature":
            effective = guessed
        elif intent == "ask" and guessed not in ("ask", "feature"):
            # Explicit ask chip + a real build task → follow the task signal
            effective = guessed

    if effective == "ask":
        return ["general"]

    team = list(team_for_intent(effective))
    if agents_n is not None:
        n = max(1, min(4, int(agents_n)))
        if n >= 3 and len(team) < n:
            team = list(team_for_intent("feature"))
        if user_text and n < len(team):
            team = rank_roles_for_task(user_text, team)
        return team[:n]
    meta = MODE_META[mode]
    if mode in ("ultra", "premium"):
        base = team_for_intent("feature") if len(team) < 4 else team
        if user_text:
            base = rank_roles_for_task(user_text, list(base))
            # keep full 4 but preferred order for waves still via _phased_team
        return base[:4]
    cut = team[: int(meta["max_agents"])]
    if user_text and len(team) > len(cut):
        cut = rank_roles_for_task(user_text, team)[: int(meta["max_agents"])]
    return cut


def _model_strength(model_id: str) -> float:
    meta = get_model(model_id) or {}
    if meta.get("input_rub") is not None or meta.get("output_rub") is not None:
        return float(meta.get("input_rub") or 0) + float(meta.get("output_rub") or 0)
    pricing = meta.get("pricing") or {}
    if pricing.get("input_per_1m") is not None:
        return float(pricing.get("input_per_1m") or 0) + float(pricing.get("output_per_1m") or 0)
    # USD fallback (relative ranking still works)
    return float(meta.get("input_usd") or 0) + float(meta.get("output_usd") or 0)


def resolve_pack_models(team_models: list[str] | None) -> dict[str, Any] | None:
    """Strongest model = orchestrator/judge; rest = workers (cycled by role)."""
    ids = [str(x).strip() for x in (team_models or []) if str(x).strip()]
    # de-dupe keep order
    seen: set[str] = set()
    clean: list[str] = []
    for mid in ids:
        if mid in seen:
            continue
        if mid.startswith("studio-") or mid in ("ultra-mode", "ultra", "onestack-ultra"):
            continue
        meta = get_model(mid)
        if meta and meta.get("ready") is False:
            continue
        seen.add(mid)
        clean.append(mid)
    if not clean:
        return None
    ranked = sorted(clean, key=_model_strength, reverse=True)
    judge = ranked[0]
    workers = ranked[1:] or [judge]
    return {"judge": judge, "workers": workers, "all": clean}


def bind_team_models(team_models: list[str] | None, team: list[str]) -> dict[str, Any] | None:
    pack = resolve_pack_models(team_models)
    if not pack:
        _TEAM_MODEL_MAP.set(None)
        return None
    workers: list[str] = pack["workers"]
    role_map: dict[str, str] = {}
    wi = 0
    for role in team:
        if role in JUDGE_ROLES:
            continue
        role_map[role] = workers[wi % len(workers)]
        wi += 1
    payload = {
        "judge": pack["judge"],
        "workers": workers,
        "role_map": role_map,
        "all": pack["all"],
    }
    _TEAM_MODEL_MAP.set(payload)
    return payload


def model_for_role(mode: str, role: str) -> str:
    """Workers from cabinet pack; synth+reviewer = strongest orchestrator. Default Flash/Pro."""
    from app.model_policy import gemini_fallback_for_role, is_gemini_model

    pack = _TEAM_MODEL_MAP.get()
    mid = ""
    if pack:
        if role in JUDGE_ROLES:
            mid = pack["judge"]
        else:
            mapped = (pack.get("role_map") or {}).get(role)
            if mapped:
                mid = mapped
            else:
                workers = pack.get("workers") or []
                if workers:
                    mid = workers[0]
    if not mid:
        if role in JUDGE_ROLES:
            if mode == "premium":
                mid = (
                    (settings.STUDIO_PREMIUM_JUDGE_MODEL or "").strip()
                    or (settings.STUDIO_JUDGE_MODEL or "").strip()
                    or "gemini-2.5-pro"
                )
            else:
                mid = (settings.STUDIO_JUDGE_MODEL or "").strip() or "gemini-2.5-pro"
        else:
            mid = CHEAP_MODEL or settings.DEFAULT_MODEL
    if _MODEL_FAMILY.get() == "gemini" and not is_gemini_model(mid):
        return gemini_fallback_for_role(role)
    return mid


def set_model_family(family: str | None) -> None:
    _MODEL_FAMILY.set((family or "").strip().lower())


def build_system(role: str, brief: str | None, intent: str, mode: str = "ultra") -> str:
    return build_role_system(role, brief, intent, mode)


def extract_artifacts(role: str, text: str) -> list[dict[str, Any]]:
    skill = get_skill(role)
    prefix = skill.get("path_prefix") or f"/src/{role}"
    arts: list[dict[str, Any]] = []
    idx = 0
    for m in _CODE_FENCE.finditer(text or ""):
        idx += 1
        lang = (m.group("lang") or "").strip() or "text"
        path = (m.group("path") or "").strip()
        body = (m.group("body") or "").rstrip()
        if not body:
            continue
        if not path:
            # Agents sometimes put path in first-line comment: # path=/src/...
            m_c = re.search(
                r"(?m)^\s*(?:#|//)\s*path\s*=\s*(/src/[^\s]+)",
                body,
            )
            if m_c:
                path = m_c.group(1).strip()
                body = re.sub(
                    r"(?m)^\s*(?:#|//)\s*path\s*=\s*/src/[^\s]+\s*\n?",
                    "",
                    body,
                    count=1,
                ).rstrip()
        if not path:
            ext = {
                "python": "py",
                "py": "py",
                "javascript": "js",
                "js": "js",
                "typescript": "ts",
                "html": "html",
                "css": "css",
                "markdown": "md",
                "md": "md",
            }.get(lang.lower(), "txt")
            path = f"{prefix}/{role}_{idx}.{ext}"
        if not path.startswith("/"):
            path = f"{prefix}/{path.lstrip('./')}"
        kind = "plan" if lang.lower() in ("markdown", "md") else "code"
        arts.append(
            {
                "kind": kind,
                "role": role,
                "path": path,
                "language": lang,
                "content": body,
                "title": path.rsplit("/", 1)[-1],
            }
        )
    return arts


ROLE_SRC_PREFIX = {
    "frontend": "/src/frontend/",
    "backend": "/src/backend/",
    "design": "/src/design/",
    "tests": "/src/tests/",
}
ALLOWED_SRC_ROOTS = tuple(ROLE_SRC_PREFIX.values())

_OUTLINE_KILL = re.compile(r"outline\s*:\s*(?:none|0)\s*;?", re.I)
_INTER_FONT = re.compile(
    r"(?<![-\w])font-family\s*:\s*[^;{}]*\bInter\b[^;{}]*;?",
    re.I,
)
_INTER_IMPORT = re.compile(
    r"@import\s+[^;]*fonts\.googleapis[^;]*Inter[^;]*;",
    re.I,
)
_INTER_LINK = re.compile(
    r"<link[^>]*fonts\.googleapis[^>]*Inter[^>]*/?>",
    re.I,
)
_INTER_IN_FAMILY = re.compile(r"(['\"]?)Inter\1\s*,\s*", re.I)
_INTER_VAR_FONT = re.compile(
    r"(--(?:[a-z0-9-]*font[a-z0-9-]*)\s*:\s*)(?:['\"]?)Inter(?:['\"]?)(\s*,)?",
    re.I,
)


def harden_artifact_content(path: str, content: str) -> str:
    """Deterministic anti-trap fixes — no LLM, no credits."""
    if not content:
        return content
    pl = (path or "").lower()
    out = content
    if pl.endswith((".css",)) or "<style" in out.lower():
        out = _OUTLINE_KILL.sub("", out)
        out = _INTER_IMPORT.sub("", out)
        out = _INTER_FONT.sub(
            "font-family: system-ui, ui-sans-serif, sans-serif;",
            out,
        )
        out = _INTER_VAR_FONT.sub(r"\1system-ui, ui-sans-serif\2", out)
        out = _INTER_IN_FAMILY.sub("", out)
        # leftover bare Inter font token
        out = re.sub(r"(?i)(?<=:|,)\s*['\"]?Inter['\"]?\s*(?=,|;|})", "", out)
    if pl.endswith((".html", ".htm", ".js", ".jsx", ".tsx")):
        out = _INTER_LINK.sub("", out)
        out = _INTER_FONT.sub(
            "font-family: system-ui, ui-sans-serif, sans-serif;",
            out,
        )
        out = _INTER_IN_FAMILY.sub("", out)
    if pl.endswith(".py") and "/tests/" in pl.replace("\\", "/"):
        out = re.sub(
            r"(?m)^(\s*)assert\s+True\b.*$",
            r"\1pass  # hardened: dropped assert True",
            out,
        )
        out = re.sub(
            r"(?m)^(\s*)assert\s+1\b.*$",
            r"\1pass  # hardened: dropped assert 1",
            out,
        )
    return out


def harden_artifacts(arts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for a in arts or []:
        item = dict(a)
        path = item.get("path") or ""
        body = item.get("content") or ""
        fixed = harden_artifact_content(path, body)
        if fixed != body:
            item["content"] = fixed
            item["hardened"] = True
        out.append(item)
    return out


def sanitize_role_artifacts(role: str, arts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only /src/<role>/...; remap obvious mistakes; drop foreign dumps."""
    prefix = ROLE_SRC_PREFIX.get(role)
    if not prefix:
        return list(arts or [])
    out: list[dict[str, Any]] = []
    for a in arts or []:
        path = (a.get("path") or "").strip()
        if not path:
            continue
        if not path.startswith("/"):
            path = prefix + path.lstrip("./")
        if path.startswith("/src/") and not path.startswith(prefix):
            name = path.rsplit("/", 1)[-1]
            if role == "tests" and (name.startswith("test_") or "test" in name.lower()):
                path = f"{prefix}{name}"
            elif role == "frontend" and name.endswith((".html", ".css", ".js")):
                path = f"{prefix}{name}"
            elif role == "backend" and name.endswith(".py") and "/tests/" not in path:
                if "schema" in name.lower():
                    path = f"{prefix}schemas/{name}"
                elif "router" in name.lower():
                    path = f"{prefix}routers/{name}"
                else:
                    path = f"{prefix}{name}"
            elif role == "design" and name.endswith((".css", ".md")):
                path = f"{prefix}{name}"
            else:
                continue
        if not path.startswith(prefix):
            continue
        if path == "/src/frontend/style.css":
            path = "/src/frontend/styles.css"
        # FE must not own tokens.css — force into styles.css name if solo dump
        if role == "frontend" and path.endswith("/tokens.css"):
            path = "/src/frontend/styles.css"
        item = dict(a)
        item["path"] = path
        item["role"] = role
        item["title"] = path.rsplit("/", 1)[-1]
        item["content"] = harden_artifact_content(path, item.get("content") or "")
        out.append(item)
    return out


def filter_studio_artifacts(arts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop paths outside Studio zones; prefer longer content per path; SSoT harden."""
    by_path: dict[str, dict[str, Any]] = {}
    for a in arts or []:
        path = (a.get("path") or "").strip()
        if path == "/src/frontend/style.css":
            path = "/src/frontend/styles.css"
            a = {**a, "path": path, "title": "styles.css"}
        if path == "/src/frontend/tokens.css":
            # Prefer merging into styles later; drop if design tokens exist
            path = "/src/frontend/tokens.css"
        if not path.startswith(ALLOWED_SRC_ROOTS):
            continue
        item = dict(a)
        item["path"] = path
        item["content"] = harden_artifact_content(path, item.get("content") or "")
        prev = by_path.get(path)
        if not prev or len(item.get("content") or "") >= len(prev.get("content") or ""):
            by_path[path] = item
    # SSoT: design tokens win — drop FE tokens.css; inject @import into styles.css
    if "/src/design/tokens.css" in by_path:
        fe_tok = by_path.pop("/src/frontend/tokens.css", None)
        styles = by_path.get("/src/frontend/styles.css")
        if styles:
            body = styles.get("content") or ""
            if "@import" not in body or "tokens.css" not in body:
                styles["content"] = (
                    "@import url('../design/tokens.css');\n" + body.lstrip()
                )
                styles["hardened"] = True
                by_path["/src/frontend/styles.css"] = styles
        elif fe_tok:
            # no styles yet — keep design only; discard FE tokens duplicate
            pass
    elif "/src/frontend/tokens.css" in by_path:
        # No design pack — fold FE tokens into styles.css
        tok = by_path.pop("/src/frontend/tokens.css")
        styles = by_path.get("/src/frontend/styles.css")
        if styles:
            styles["content"] = (tok.get("content") or "") + "\n" + (styles.get("content") or "")
            styles["hardened"] = True
            by_path["/src/frontend/styles.css"] = styles
        else:
            by_path["/src/frontend/styles.css"] = {
                **tok,
                "path": "/src/frontend/styles.css",
                "title": "styles.css",
            }
    return list(by_path.values())


def _artifacts_handoff_blob(parts: list[dict[str, Any]], *, limit: int = 5500) -> str:
    """Prioritize design tokens + contracts so next wave consumes SSoT."""
    items: list[tuple[int, str, str, str]] = []
    for p in parts:
        role = p.get("role")
        if role in ("synth", "reviewer"):
            continue
        for a in p.get("artifacts") or []:
            path = (a.get("path") or "").strip()
            body = a.get("content") or ""
            if not path or not body:
                continue
            # Priority: tokens first, then contracts, then UI/API, docs last
            pri = 50
            pl = path.lower()
            if pl.endswith("tokens.css") or "/design/tokens" in pl:
                pri = 0
            elif role == "design":
                pri = 10
            elif role == "backend" and (
                "schema" in pl or "router" in pl or pl.endswith(".py")
            ):
                pri = 20
            elif role == "frontend":
                pri = 30
            elif role == "tests":
                pri = 40
            elif pl.endswith(".md"):
                pri = 80
            cap = 1600 if pri == 0 else 900
            items.append((pri, role or "", path, body[:cap]))
    items.sort(key=lambda x: (x[0], x[1], x[2]))
    lines: list[str] = []
    seen_roles: set[str] = set()
    for pri, role, path, body in items[:14]:
        if role not in seen_roles:
            lines.append(f"### Handoff от {role}")
            seen_roles.add(role)
        lines.append(f"- `{path}`\n```\n{body}\n```")
    # Оркестратор/воркеры видят только финальные файлы, не «мышление» процесса
    return "\n".join(lines)[:limit]


def _phased_team(team: list[str]) -> list[list[str]]:
    """design → (frontend∥backend) → tests."""
    waves: list[list[str]] = []
    rest = list(team)
    if "design" in rest:
        waves.append(["design"])
        rest.remove("design")
    mid = [r for r in ("frontend", "backend") if r in rest]
    for r in mid:
        rest.remove(r)
    if mid:
        waves.append(mid)
    if "tests" in rest:
        waves.append(["tests"])
        rest.remove("tests")
    if rest:
        waves.append(rest)
    return waves or [team]


def _role_call_user_text(
    role: str,
    user_text: str,
    prior_parts: list[dict[str, Any]],
    locked_contract: dict[str, Any] | None = None,
    product_brief: str | None = None,
) -> str:
    handoff = _artifacts_handoff_blob(prior_parts)
    rules = (
        f"\n\n## Studio path rules\n"
        f"- Пиши ТОЛЬКО `path=/src/{role}/...` в заголовке fence\n"
        f"- Не клади тесты/API/CSS в чужие зоны\n"
        f"- Anti-AI: indigo/purple/Inter/#4f46e5/#6366f1/#7c3aed запрещены "
        f"**даже если задача просит** — замени (navy/teal/amber + system-ui) и объясни в Мышлении\n"
        f"- outline:none / outline:0 запрещены — только :focus-visible усиление\n"
        f"- Соблюдай ## Product brief / must-have оркестратора — это SSoT по секциям и API\n"
    )
    if role == "frontend":
        rules += (
            "- Если в handoff есть `/src/design/tokens.css` — **SSoT**:\n"
            "  1) в `styles.css` первой строкой "
            "`@import url('../design/tokens.css');` "
            "ИЛИ скопируй весь `:root { ... }` из tokens без новых indigo/Inter;\n"
            "  2) цвета только через `var(--…)`;\n"
            "  3) не заводи параллельную `:root` палитру\n"
            "- Файл стилей: `styles.css` (не style.css)\n"
            "- Интерактив = button/a, не div onclick\n"
            "- fetch/API: только path из Locked contract (если есть)\n"
            "- **Визуальная планка (лендинг/кафе/СТО/страница):** НЕ текст на белом.\n"
            "  Нужны: атмосфера (фон/градиент/фото-плоскость), сильный hero, ритм отступов,\n"
            "  услуги/меню или 3+ карточки с ценами, социальное доказательство, форма/CTA.\n"
            "  1–2 CSS transition. Страница = место/продукт, не черновик markdown.\n"
            "- Фото клади в `/src/frontend/assets/` если добавляешь img\n"
        )
    if role == "backend":
        rules += (
            "- Согласуй поля/path с frontend handoff если он уже есть\n"
            "- Auth Depends сразу; Pydantic body; без SQL f-string\n"
            "- После кода контракт должен быть однозначен: method/path/fields/status\n"
        )
    if role == "tests":
        rules += (
            "- Тестируй РОВНО path/status/поля из Locked contract / backend\n"
            "- Только `/src/tests/...`, TestClient/httpx, без SQL f-string\n"
            "- Каждый тест: assert status + body; запрещён пустой `assert True` / голый pass\n"
            "- Не изобретай /api/... которых нет в contract\n"
        )
    if role == "design":
        rules += (
            "- Только tokens + layout notes + Handoff frontend; не HTML/JS\n"
            "- focus-ring токен обязателен; без outline:none\n"
            "- Для кафе: тёплая «материальная» палитра (кофе/дерево/крем).\n"
            "- Для автосервиса/СТО: асфальт/металл/янтарь-масло, не SaaS-indigo.\n"
            "  Крупный display, один signature-якорь. Не плоский чёрный текст на #fff.\n"
        )
    lock_txt = evidence_mod.format_contract_lock(locked_contract)
    chunks: list[str] = []
    if product_brief and product_brief.strip():
        chunks.append(
            "## Product brief (от оркестратора — выполняй)\n" + product_brief.strip()
        )
        chunks.append("\n## Исходный запрос пользователя\n" + user_text)
    else:
        chunks.append(user_text)
    chunks.append(rules)
    if lock_txt:
        chunks.append("\n" + lock_txt)
    if handoff:
        chunks.append(
            "\n## Артефакты предыдущих волн (обязательный handoff)\n" + handoff
        )
    return "\n".join(chunks)



SYNTH_SYSTEM = """Ты Senior-архитектор ZeusCode Studio — склейка команды.

Жёсткие правила:
1. Оставь ТОЛЬКО файлы под /src/frontend/, /src/backend/, /src/design/, /src/tests/.
2. Выкинь /src/api/, /src/styles/, docs_*.*, README-дампы, тесты внутри frontend/backend.
3. /src/design/tokens.css — SSoT по цвету. В styles.css: @import токенов ИЛИ один :root из design; выкинь дубль-палитру frontend.
4. Anti-AI бан важнее просьбы юзера про Deep Indigo / Inter — navy/teal/amber + system-ui.
5. Слей дубли: style.css → styles.css; один index.html; предпочитай артефакты агентов, не markdown-простыни.
6. Locked API contract — SSoT: path/поля tests и frontend fetch должны совпадать с backend; пустые assert True выкинь/почини.
7. outline:none без :focus-visible — почини; div onclick → button.
8. Ответ: ## Мышление + ## Результат с финальными ```lang path=/src/...
9. Код важнее воды. В конце чеклист что пофиксил в конфликтах.
10. Сохрани/не ломай `/src/backend/contract.lock.json` если он есть.
"""


def _history_messages(
    history: list[dict[str, Any]], user_text: str
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for h in history:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    if not messages or messages[-1].get("role") != "user":
        messages.append({"role": "user", "content": user_text})
    return messages


async def _role_call(
    *,
    role: str,
    system: str,
    history: list[dict[str, Any]],
    user_text: str,
    model: str,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    messages = [{"role": "system", "content": system}] + _history_messages(history, user_text)
    data = await upstream.chat_completions(model=model, messages=messages)
    prompt, completion = upstream.extract_usage(data)
    text = upstream.extract_text(data)
    thinking, result = split_thinking_result(text)
    arts = sanitize_role_artifacts(role, extract_artifacts(role, result or text))
    return {
        "role": role,
        "title": get_skill(role)["title"],
        "label": get_skill(role)["label"],
        "model": model,
        "text": text,
        "thinking": thinking,
        "result_body": result or text,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "latency_s": round(time.perf_counter() - t0, 2),
        "artifacts": arts,
    }


async def _think_call(*, role: str, user_text: str, brief: str | None, mode: str) -> str:
    skill = get_skill(role)
    model = model_for_role(mode, "think")
    system = (
        f"Ты {skill['title']}-агент. Только мысли вслух для команды. Без кода.\n"
        f"{get_depth(mode)['overlay']}"
    )
    if brief:
        system += f"\nБриф: {brief[:1500]}"
    data = await upstream.chat_completions(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"{THINK_PROMPT}\n\nЗадача:\n{user_text}"},
        ],
    )
    return upstream.extract_text(data).strip()


def _sse_artifacts(arts: list[dict[str, Any]], *, limit: int = 12000) -> list[dict[str, Any]]:
    """Compact artifacts for live playground SSE (path + content)."""
    out: list[dict[str, Any]] = []
    for a in arts or []:
        body = a.get("content") or ""
        if len(body) > limit:
            body = body[:limit] + "\n/* …truncated for live stream… */"
        out.append(
            {
                "path": a.get("path"),
                "title": a.get("title"),
                "role": a.get("role"),
                "language": a.get("language"),
                "kind": a.get("kind") or "code",
                "content": body,
                "bytes": len(a.get("content") or ""),
            }
        )
    return out


def _agent_done_event(part: dict[str, Any], *, preview_len: int = 500) -> dict[str, Any]:
    body = part.get("result_body") or part.get("text") or ""
    arts = part.get("artifacts") or []
    files = []
    for a in arts[:12]:
        path = a.get("path") or a.get("title") or ""
        if path:
            files.append(
                {
                    "path": path,
                    "bytes": len(a.get("content") or ""),
                    "language": a.get("language") or "",
                }
            )
    think = (part.get("thinking") or "").strip()
    think_one = " ".join(think.split())[:160] if think else ""
    role = part.get("role") or ""
    if files:
        names = ", ".join((f["path"].rsplit("/", 1)[-1] for f in files[:4]))
        summary = f"написал {len(files)} файл(ов): {names}"
    elif think_one:
        summary = think_one
    else:
        summary = "ответ без файлов"
    return {
        "type": "agent_done",
        "role": part["role"],
        "title": part.get("title"),
        "label": part.get("label"),
        "model": part.get("model"),
        "thinking": part.get("thinking") or "",
        "thinking_short": think_one,
        "summary": summary,
        "preview": body[:preview_len],
        "text": part.get("text") or "",
        "latency_s": part.get("latency_s"),
        "prompt_tokens": part.get("prompt_tokens"),
        "completion_tokens": part.get("completion_tokens"),
        "artifacts": _sse_artifacts(arts),
        "files": files,
    }


def _status(text: str, **extra: Any) -> dict[str, Any]:
    return {"type": "status", "text": text, **extra}


async def _run_evidence_gate(
    *,
    user_text: str,
    brief: str | None,
    mode: str,
    final_text: str,
    parts: list[dict[str, Any]],
    use_llm: bool,
    pre_artifacts: list[dict[str, Any]] | None = None,
    pre_findings: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    """Deterministic gates + optional LLM reviewer. Returns (final_text, receipt, reviewer_part)."""
    if pre_artifacts is not None:
        artifacts = list(pre_artifacts)
    else:
        artifacts = []
        for p in parts:
            if p.get("role") in ("synth", "reviewer"):
                continue
            artifacts.extend(p.get("artifacts") or [])
        artifacts.extend(
            filter_studio_artifacts(extract_artifacts("docs", final_text))
        )
        artifacts = filter_studio_artifacts(artifacts)
        by_path: dict[str, dict[str, Any]] = {}
        for a in artifacts:
            path = a.get("path") or ""
            prev = by_path.get(path)
            if not prev or len(a.get("content") or "") >= len(prev.get("content") or ""):
                by_path[path] = a
        artifacts = list(by_path.values())

    findings = list(pre_findings) if pre_findings is not None else evidence_mod.scan_all(artifacts)
    llm_review = None
    reviewer_part: dict[str, Any] | None = None

    if use_llm:
        model = model_for_role(mode if mode != "solo" else "standard", "reviewer")
        t0 = time.perf_counter()
        try:
            data = await upstream.chat_completions(
                model=model,
                messages=[
                    {"role": "system", "content": evidence_mod.reviewer_system_prompt(mode if mode != "solo" else "standard")},
                    {
                        "role": "user",
                        "content": evidence_mod.reviewer_user_payload(
                            task=user_text,
                            brief=brief,
                            final_text=final_text,
                            artifacts=artifacts,
                            findings=findings,
                        ),
                    },
                ],
            )
            text = upstream.extract_text(data)
            sp, sc = upstream.extract_usage(data)
            llm_review = evidence_mod.parse_llm_review(text)
            findings.extend(evidence_mod.reviewer_format_findings(llm_review))
            reviewer_part = {
                "role": "reviewer",
                "title": get_skill("reviewer")["title"],
                "label": get_skill("reviewer")["label"],
                "model": model,
                "text": text,
                "thinking": "",
                "result_body": text,
                "prompt_tokens": sp,
                "completion_tokens": sc,
                "latency_s": round(time.perf_counter() - t0, 2),
                "artifacts": [],
            }
        except Exception as e:  # noqa: BLE001
            llm_review = {
                "verdict": "PASS_WITH_RISKS",
                "text": f"(reviewer LLM недоступен: {e})",
                "source": "llm_reviewer_error",
            }

    receipt = evidence_mod.build_receipt(
        task=user_text,
        mode=mode,
        artifacts=artifacts,
        findings=findings,
        llm_review=llm_review,
    )
    stamped = final_text.rstrip() + evidence_mod.format_evidence_markdown(receipt)
    return stamped, receipt, reviewer_part


async def iter_studio_events(
    *,
    user_text: str,
    intent: str = "feature",
    mode: str = "ultra",
    history: list[dict[str, Any]] | None = None,
    brief: str | None = None,
    model_override: str | None = None,
    agents_n: int | None = None,
    team_models: list[str] | None = None,
    model_family: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield live cooperative events, then a final packed result."""
    set_model_family(model_family)
    intent = normalize_intent(intent)
    mode = normalize_mode(mode)
    mode_meta = MODE_META[mode]
    depth = get_depth(mode)
    hist = list(history or [])[-(mode_meta["history_limit"]) :]
    t_wall = time.perf_counter()
    agents_n = max(1, min(4, int(agents_n))) if agents_n is not None else None

    if model_override and model_override not in (
        "ultra-mode",
        "ultra",
        "onestack-ultra",
        "studio-light",
        "studio-standard",
        "studio-ultra",
        "studio-premium",
    ):
        # Studio: even solo override runs on cheapest Flash
        model_override = CHEAP_MODEL
        role = resolve_team(intent, "standard", user_text=user_text)[0]
        yield {
            "type": "meta",
            "intent": intent,
            "mode": "solo",
            "team": [role],
            "depth": depth["label"],
            "model": model_override,
        }
        yield {
            "type": "agent_start",
            "role": role,
            "title": get_skill(role)["title"],
            "model": model_override,
            "skill": get_skill(role)["label"],
        }
        part = await _role_call(
            role=role,
            system=build_system(role, brief, intent, mode),
            history=hist,
            user_text=user_text,
            model=model_override,
        )
        if part.get("thinking"):
            yield {"type": "agent_think", "role": role, "thinking": part["thinking"]}
        yield _agent_done_event(part, preview_len=400)
        # Evidence gate (deterministic always; LLM if power is not light)
        power = normalize_mode(mode)
        use_llm = power in ("standard", "ultra", "premium")
        yield {
            "type": "review_start",
            "model": model_for_role(power, "reviewer") if use_llm else "gate-only",
            "llm": use_llm,
        }
        stamped, receipt, rev = await _run_evidence_gate(
            user_text=user_text,
            brief=brief,
            mode="solo",
            final_text=part["text"],
            parts=[part],
            use_llm=use_llm,
        )
        parts_out = [part]
        if rev:
            parts_out.append(rev)
        yield {
            "type": "review_done",
            "verdict": receipt.get("verdict"),
            "gate": receipt.get("gate"),
            "score": receipt.get("score"),
            "grade": receipt.get("grade"),
            "findings_n": len(receipt.get("gate_findings") or []),
            "preview": (rev or {}).get("text", "")[:400]
            if rev
            else f"gate={receipt.get('gate')} score={receipt.get('score')}",
            "evidence": {
                "verdict": receipt.get("verdict"),
                "gate": receipt.get("gate"),
                "score": receipt.get("score"),
                "grade": receipt.get("grade"),
                "findings": receipt.get("gate_findings"),
                "artifact_paths": receipt.get("artifact_paths"),
                "proved": receipt.get("proved"),
                "not_proved": receipt.get("not_proved"),
            },
            "artifacts": _sse_artifacts(
                [
                    a
                    for p in parts_out
                    if p.get("role") not in ("synth", "reviewer")
                    for a in (p.get("artifacts") or [])
                ]
            ),
        }
        packed = _pack_result(
            mode="solo",
            intent=intent,
            power=power,
            parts=parts_out,
            final_text=stamped,
            synth_model=model_override,
            wall=part["latency_s"],
            team=[role],
            evidence=receipt,
        )
        yield {"type": "done", "result": packed}
        return

    team = resolve_team(intent, mode, agents_n=agents_n, user_text=user_text)
    pack = bind_team_models(team_models, team)
    waves = _phased_team(team)
    effective_intent = intent
    if user_text and intent == "feature":
        guessed = infer_intent_from_task(user_text, fallback=intent)
        if guessed != intent:
            effective_intent = guessed
    if team == ["general"]:
        effective_intent = "ask"

    # Q&A / chitchat: one assistant reply — no design team, no gate theatre
    if effective_intent == "ask" or team == ["general"]:
        role = "general"
        ask_model = CHEAP_MODEL
        yield {
            "type": "meta",
            "intent": intent,
            "intent_effective": "ask",
            "mode": "solo",
            "team": [role],
            "waves": [[role]],
            "depth": depth["label"],
            "agents_n": 1,
            "pipeline": "ask",
            "step": "reply",
            "plan": ["1) ответ"],
            "models": {"code": ask_model, "judge": ask_model, "role_map": {role: ask_model}, "pack": [ask_model]},
        }
        if intent != "ask":
            yield _status("Это вопрос — отвечаю без команды дизайна", phase="plan")
        yield {
            "type": "agent_start",
            "role": role,
            "title": get_skill(role)["title"],
            "model": ask_model,
            "skill": get_skill(role)["label"],
        }
        part = await _role_call(
            role=role,
            system=build_system(role, brief, "ask", mode),
            history=hist,
            user_text=user_text,
            model=ask_model,
        )
        if part.get("thinking"):
            yield {"type": "agent_think", "role": role, "thinking": part["thinking"]}
        yield _agent_done_event(part, preview_len=400)
        packed = _pack_result(
            mode="solo",
            intent="ask",
            power=normalize_mode(mode),
            parts=[part],
            final_text=part["text"],
            synth_model=ask_model,
            wall=part["latency_s"],
            team=[role],
            evidence=None,
        )
        yield {"type": "done", "result": packed}
        return

    wave_labels = {
        "design": "дизайн: токены и атмосфера",
        "frontend": "фронт: вёрстка и UI",
        "backend": "бэк: API и контракт",
        "tests": "тесты: проверки",
        "general": "ответ",
    }
    plan_bits = []
    for wi, w in enumerate(waves):
        labs = " + ".join(wave_labels.get(r, r) for r in w)
        plan_bits.append(f"{wi + 1}) {labs}")
    yield {
        "type": "meta",
        "intent": intent,
        "intent_effective": effective_intent,
        "mode": mode,
        "team": team,
        "waves": waves,
        "depth": depth["label"],
        "agents_n": len(team),
        "pipeline": "prelock→design→(frontend∥backend)→tests→synth→harden→gate→review",
        "step": "build",
        "plan": plan_bits,
        "models": {
            "code": (pack or {}).get("workers", [CHEAP_MODEL])[0] if pack else CHEAP_MODEL,
            "judge": (pack or {}).get("judge") or model_for_role(mode, "synth"),
            "role_map": (pack or {}).get("role_map") or {},
            "pack": (pack or {}).get("all") or [],
        },
    }
    if pack:
        worker_s = ", ".join((pack.get("role_map") or {}).values()) or ", ".join(pack.get("workers") or [])
        yield _status(
            f"Оркестратор {pack['judge']} делит задачи и проверяет только финал · "
            f"воркеры: {worker_s}",
            phase="plan",
        )
    if effective_intent != intent:
        yield _status(
            f"Интент уточнён по задаче: {intent} → {effective_intent}",
            phase="plan",
        )
    yield _status(
        f"Оркестратор разбил задачу на {len(waves)} волн · {len(team)} нейросети "
        f"({', '.join(team)})",
        phase="plan",
    )
    for i, bit in enumerate(plan_bits):
        yield _status(f"План: {bit}", phase="plan", wave=i)

    # --- Orchestrator unpack: expand vague task into product brief ---
    product_brief = (brief or "").strip() or None
    expand_meta: dict[str, Any] | None = None
    if needs_expand(user_text, brief):
        yield _status("Оркестратор распаковывает задачу в бриф…", phase="plan")
        expand_meta = await expand_task_brief(
            user_text=user_text,
            brief=brief,
            mode=mode,
            model=model_for_role(mode, "synth"),
        )
        product_brief = format_expanded_brief(expand_meta)
        # Prefer expanded brief as project brief for workers/synth/reviewer
        if product_brief:
            brief = product_brief
        yield {
            "type": "brief_expand",
            "title": expand_meta.get("title"),
            "summary": expand_meta.get("summary"),
            "assumptions": expand_meta.get("assumptions") or [],
            "questions": expand_meta.get("questions") or [],
            "must_haves": expand_meta.get("must_haves") or [],
            "source": expand_meta.get("source"),
            "model": expand_meta.get("model"),
            "brief_preview": (product_brief or "")[:900],
        }
        qn = len(expand_meta.get("questions") or [])
        an = len(expand_meta.get("assumptions") or [])
        yield _status(
            f"Бриф готов · допущений {an} · уточнений на потом {qn}"
            + (f" · {(expand_meta.get('title') or '')}" if expand_meta.get("title") else ""),
            phase="plan",
        )
        for q in (expand_meta.get("questions") or [])[:4]:
            yield _status(f"Уточнение: {q}", phase="plan")

    for role in team:
        yield {
            "type": "agent_start",
            "role": role,
            "title": get_skill(role)["title"],
            "model": model_for_role(mode, role),
            "skill": get_skill(role)["label"],
        }

    parts: list[dict[str, Any]] = []
    think_map: dict[str, str] = {}
    # P0: task pre-lock so FE∥BE share the same draft contract
    task_prelock: dict[str, Any] | None = evidence_mod.extract_prelock_from_task(
        user_text
    )
    expand_prelock = inject_api_prelock(expand_meta) if expand_meta else None
    if expand_prelock and task_prelock:
        task_prelock = evidence_mod.merge_contracts(expand_prelock, task_prelock)
    elif expand_prelock and not task_prelock:
        task_prelock = expand_prelock
    locked_contract: dict[str, Any] | None = task_prelock
    if locked_contract:
        yield {
            "type": "contract_lock",
            "wave": -1,
            "source": locked_contract.get("source") or "task_prelock",
            "contract": locked_contract,
        }
        yield _status(
            "Pre-lock из задачи: "
            + ", ".join((locked_contract.get("paths") or [])[:4] or ["fields only"]),
            phase="plan",
        )

    for wave_i, wave in enumerate(waves):
        labs = ", ".join(get_skill(r)["label"] for r in wave)
        yield {"type": "wave_start", "wave": wave_i, "roles": wave}
        yield _status(
            f"Волна {wave_i + 1}/{len(waves)}: запускаю {labs}",
            phase="build",
            wave=wave_i,
        )

        if depth.get("think"):

            async def _th(role: str) -> tuple[str, str]:
                try:
                    return role, await _think_call(
                        role=role, user_text=user_text, brief=brief, mode=mode
                    )
                except Exception as e:  # noqa: BLE001
                    return role, f"(мышление недоступно: {e})"

            yield _status(
                f"Волна {wave_i + 1}: думают {labs}…",
                phase="think",
                wave=wave_i,
            )
            for coro in asyncio.as_completed([_th(r) for r in wave]):
                role, thinking = await coro
                think_map[role] = thinking
                short = " ".join((thinking or "").split())[:140]
                yield {"type": "agent_think", "role": role, "thinking": thinking}
                yield _status(
                    f"{get_skill(role)['label']}: {short or 'думает…'}",
                    phase="think",
                    role=role,
                )

        prior = list(parts)
        lock_snap = locked_contract

        async def _build(role: str) -> dict[str, Any]:
            part = await _role_call(
                role=role,
                system=build_system(role, brief, intent, mode),
                history=hist,
                user_text=_role_call_user_text(
                    role,
                    user_text,
                    prior,
                    locked_contract=lock_snap,
                    product_brief=product_brief,
                ),
                model=model_for_role(mode, role),
            )
            if not part.get("thinking") and think_map.get(role):
                part["thinking"] = think_map[role]
            return part

        yield _status(
            f"Волна {wave_i + 1}: пишут код {labs}…",
            phase="build",
            wave=wave_i,
        )
        wave_parts: list[dict[str, Any]] = []
        for coro in asyncio.as_completed([_build(r) for r in wave]):
            part = await coro
            wave_parts.append(part)
            parts.append(part)
            ev = _agent_done_event(part)
            yield ev
            yield _status(
                f"{get_skill(part['role'])['label']}: {ev.get('summary')}",
                phase="build",
                role=part["role"],
            )

        # Refresh contract lock after any backend wave (merge with task prelock)
        be_arts = [
            a
            for p in parts
            if p.get("role") == "backend"
            for a in (p.get("artifacts") or [])
        ]
        if be_arts:
            new_lock = evidence_mod.extract_locked_contract(be_arts)
            if new_lock:
                locked_contract = evidence_mod.merge_contracts(task_prelock, new_lock)
                yield {
                    "type": "contract_lock",
                    "wave": wave_i,
                    "source": (locked_contract or {}).get("source") or "backend",
                    "contract": locked_contract,
                }
                yield _status(
                    "Зафиксировал API-контракт для тестов и фронта",
                    phase="build",
                )

        yield {
            "type": "wave_done",
            "wave": wave_i,
            "roles": [p["role"] for p in wave_parts],
            "artifacts_n": sum(len(p.get("artifacts") or []) for p in wave_parts),
        }
        yield _status(
            f"Волна {wave_i + 1} готова · файлов: "
            f"{sum(len(p.get('artifacts') or []) for p in wave_parts)}",
            phase="build",
            wave=wave_i,
        )

    # Keep team order for synth
    order = {r: i for i, r in enumerate(team)}
    parts.sort(key=lambda p: order.get(p["role"], 99))

    # Attach locked contract as studio artifact for evidence / UI
    if locked_contract:
        lock_art = {
            "path": "/src/backend/contract.lock.json",
            "title": "contract.lock.json",
            "language": "json",
            "role": "backend",
            "content": json.dumps(locked_contract, ensure_ascii=False, indent=2),
        }
        for p in parts:
            if p.get("role") == "backend":
                arts = list(p.get("artifacts") or [])
                arts = [a for a in arts if a.get("path") != lock_art["path"]]
                arts.append(lock_art)
                p["artifacts"] = arts
                break

    if len(parts) == 1:
        final_text = parts[0]["text"]
        synth_model = parts[0]["model"]
    else:
        synth_model = model_for_role(mode, "synth")
        yield {"type": "synth_start", "model": synth_model}
        yield _status("Склеиваю ответы команды в один результат…", phase="synth")
        blob = []
        for p in parts:
            paths = ", ".join(
                (a.get("path") or "?") for a in (p.get("artifacts") or [])[:12]
            )
            blob.append(
                f"\n===== {p['title'].upper()} ({p['model']}) paths: {paths} =====\n"
                f"Мышление:\n{p.get('thinking') or '—'}\n\n"
                f"Результат:\n{(p.get('result_body') or p['text'])[:5000]}\n"
            )
        lock_block = evidence_mod.format_contract_lock(locked_contract)
        synth = await upstream.chat_completions(
            model=synth_model,
            messages=[
                {"role": "system", "content": SYNTH_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Задача:\n{user_text}\n\n"
                        f"Бриф:\n{(brief or '—')[:1500]}\n\n"
                        f"{lock_block}\n\n"
                        f"Куски агентов (уже path-sanitized по ролям):\n{''.join(blob)}"
                    ),
                },
            ],
        )
        final_text = upstream.extract_text(synth)
        sp, sc = upstream.extract_usage(synth)
        synth_arts = filter_studio_artifacts(extract_artifacts("docs", final_text))
        # Prefer agent artifacts; synth may add merged files under allowed roots
        parts.append(
            {
                "role": "synth",
                "title": "Сборка",
                "label": "сборка",
                "model": synth_model,
                "text": final_text,
                "thinking": "",
                "result_body": final_text,
                "prompt_tokens": sp,
                "completion_tokens": sc,
                "latency_s": 0,
                "artifacts": synth_arts,
            }
        )
        yield {
            "type": "synth_done",
            "text": final_text,
            "preview": final_text[:500],
            "artifacts": _sse_artifacts(synth_arts),
        }
        yield _status("Сборка готова — гоню проверки качества", phase="check")

    # Deterministic gate BEFORE LLM reviewer (visible in stream)
    pre_arts: list[dict[str, Any]] = []
    for p in parts:
        if p.get("role") in ("synth", "reviewer"):
            continue
        pre_arts.extend(p.get("artifacts") or [])
    pre_arts.extend(filter_studio_artifacts(extract_artifacts("docs", final_text)))
    pre_arts = filter_studio_artifacts(pre_arts)
    gate_findings = evidence_mod.scan_all(pre_arts)
    g_score, g_grade, g_gate = evidence_mod.score_from_findings(gate_findings)
    yield _status(
        f"Автопроверка: {g_gate} · оценка {g_score} · находок {len(gate_findings)}",
        phase="check",
    )
    yield {
        "type": "gate_done",
        "score": g_score,
        "grade": g_grade,
        "gate": g_gate,
        "findings_n": len(gate_findings),
        "findings": gate_findings[:24],
        "contract": locked_contract,
    }

    # Evidence gate: reuse scan (no second Playwright); LLM reviewer for standard+
    use_llm = mode in ("standard", "ultra", "premium")
    yield {
        "type": "review_start",
        "model": model_for_role(mode, "reviewer") if use_llm else "gate-only",
        "llm": use_llm,
    }
    yield _status(
        "Ревьюер ищет баги и AI-look…" if use_llm else "Только автогейт (без LLM-ревью)",
        phase="check",
    )
    stamped, receipt, rev = await _run_evidence_gate(
        user_text=user_text,
        brief=brief,
        mode=mode,
        final_text=final_text,
        parts=parts,
        use_llm=use_llm,
        pre_artifacts=pre_arts,
        pre_findings=gate_findings,
    )
    if rev:
        parts.append(rev)
    if expand_meta and isinstance(receipt, dict):
        receipt = dict(receipt)
        receipt["brief_expand"] = {
            "title": expand_meta.get("title"),
            "summary": expand_meta.get("summary"),
            "assumptions": expand_meta.get("assumptions") or [],
            "questions": expand_meta.get("questions") or [],
            "must_haves": expand_meta.get("must_haves") or [],
            "source": expand_meta.get("source"),
            "model": expand_meta.get("model"),
        }
    if expand_meta and (expand_meta.get("questions") or expand_meta.get("assumptions")):
        head = ["\n\n## Распаковка оркестратора"]
        if expand_meta.get("title"):
            head.append(f"**{expand_meta['title']}** — {expand_meta.get('summary') or ''}")
        if expand_meta.get("assumptions"):
            head.append("### Допущения")
            head.extend(f"- {a}" for a in expand_meta["assumptions"][:8])
        if expand_meta.get("questions"):
            head.append("### Вопросы на потом (сборка уже сделана)")
            head.extend(f"- {q}" for q in expand_meta["questions"][:6])
        stamped = "\n".join(head) + "\n\n" + stamped
    yield {
        "type": "review_done",
        "verdict": receipt.get("verdict"),
        "gate": receipt.get("gate"),
        "score": receipt.get("score"),
        "grade": receipt.get("grade"),
        "findings_n": len(receipt.get("gate_findings") or []),
        "preview": (rev or {}).get("text", "")[:500]
        if rev
        else f"gate={receipt.get('gate')} score={receipt.get('score')}",
        "evidence": {
            "verdict": receipt.get("verdict"),
            "gate": receipt.get("gate"),
            "score": receipt.get("score"),
            "grade": receipt.get("grade"),
            "findings": receipt.get("gate_findings"),
            "artifact_paths": receipt.get("artifact_paths"),
            "proved": receipt.get("proved"),
            "not_proved": receipt.get("not_proved"),
        },
        "artifacts": _sse_artifacts(
            [
                a
                for p in parts
                if p.get("role") not in ("synth", "reviewer")
                for a in (p.get("artifacts") or [])
            ]
        ),
    }

    wall = time.perf_counter() - t_wall
    packed = _pack_result(
        mode=mode,
        intent=intent,
        power=mode,
        parts=parts,
        final_text=stamped,
        synth_model=synth_model,
        wall=wall,
        team=team,
        evidence=receipt,
    )
    yield {"type": "done", "result": packed}


async def run_studio(
    *,
    user_text: str,
    intent: str = "feature",
    mode: str = "ultra",
    history: list[dict[str, Any]] | None = None,
    brief: str | None = None,
    model_override: str | None = None,
    agents_n: int | None = None,
    team_models: list[str] | None = None,
    model_family: str | None = None,
) -> dict[str, Any]:
    result = None
    async for ev in iter_studio_events(
        user_text=user_text,
        intent=intent,
        mode=mode,
        history=history,
        brief=brief,
        model_override=model_override,
        agents_n=agents_n,
        team_models=team_models,
        model_family=model_family,
    ):
        if ev.get("type") == "done":
            result = ev["result"]
    if not result:
        raise RuntimeError("Studio run produced no result")
    return result


def _pack_result(
    *,
    mode: str,
    intent: str,
    power: str,
    parts: list[dict[str, Any]],
    final_text: str,
    synth_model: str,
    wall: float,
    team: list[str],
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    total_prompt = sum(int(p.get("prompt_tokens") or 0) for p in parts)
    total_completion = sum(int(p.get("completion_tokens") or 0) for p in parts)
    artifacts: list[dict[str, Any]] = []
    for p in parts:
        if p.get("role") in ("synth", "reviewer"):
            continue
        artifacts.extend(p.get("artifacts") or [])
    if mode in ("ultra", "premium", "standard", "solo"):
        artifacts.extend(filter_studio_artifacts(extract_artifacts("docs", final_text)))

    artifacts = filter_studio_artifacts(artifacts)
    by_path: dict[str, dict[str, Any]] = {}
    for a in artifacts:
        prev = by_path.get(a["path"])
        if not prev or len(a.get("content") or "") >= len(prev.get("content") or ""):
            by_path[a["path"]] = a
    artifacts = list(by_path.values())

    bill_model = synth_model or settings.DEFAULT_MODEL
    display_model = {
        "light": "studio-light",
        "standard": "studio-standard",
        "ultra": "studio-ultra",
        "premium": "studio-premium",
        "solo": bill_model,
    }.get(mode, f"studio-{mode}")

    return {
        "id": f"chatcmpl-studio-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": display_model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": final_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
        },
        "onestack": {
            "mode": mode,
            "power": power,
            "intent": intent,
            "intent_title": INTENT_META.get(intent, {}).get("title", intent),
            "team": team,
            "wall_s": round(wall, 2),
            "bill_model": bill_model,
            "agents": [
                {
                    "role": p["role"],
                    "title": p.get("title"),
                    "label": p.get("label"),
                    "model": p.get("model"),
                    "latency_s": p.get("latency_s"),
                    "prompt_tokens": p.get("prompt_tokens"),
                    "completion_tokens": p.get("completion_tokens"),
                    "thinking": (p.get("thinking") or "")[:500],
                    "preview": (p.get("result_body") or p.get("text") or "")[:280],
                }
                for p in parts
                if p.get("role") != "synth"
            ],
            "artifacts": artifacts,
            "evidence": evidence,
        },
        "_bill_model": bill_model,
    }


def modes_public() -> list[dict[str, Any]]:
    return [
        {
            "id": mid,
            "title": MODE_META[mid]["title"],
            "hint": MODE_META[mid]["hint"],
            "parallel": MODE_META[mid]["parallel"],
            "agents": MODE_META[mid]["max_agents"],
        }
        for mid in MODES
    ]


def intents_public() -> list[dict[str, str]]:
    return [{"id": k, **v} for k, v in INTENT_META.items()]


async def iter_fork_events(
    *,
    user_text: str,
    intent: str = "feature",
    models: list[str],
    brief: str | None = None,
    workspace: Any = None,
) -> AsyncIterator[dict[str, Any]]:
    """Best-of-N: same prompt → N models in isolated git worktrees."""
    from pathlib import Path

    from app import git_ops
    from app import workspace as ws_mod

    intent = normalize_intent(intent)
    role = resolve_team(intent, "standard", user_text=user_text)[0]
    root = Path(workspace) if workspace else None
    if root is None:
        raise RuntimeError("workspace required for fork")

    models = [CHEAP_MODEL, CHEAP_MODEL, CHEAP_MODEL]
    yield {"type": "meta", "mode": "fork", "models": models, "team": [role]}

    async def _one(idx: int, model: str) -> dict[str, Any]:
        fork_id = f"m{idx}"
        fork_path = git_ops.create_worktree(root, fork_id)
        part = await _role_call(
            role=role,
            system=build_system(role, brief, intent, "standard"),
            history=[],
            user_text=user_text,
            model=model,
        )
        arts = part.get("artifacts") or []
        written = ws_mod.apply_artifacts(fork_path, arts)
        diff = git_ops.diff(fork_path)
        return {
            "fork_id": fork_id,
            "model": model,
            "index": idx,
            "text": part.get("text") or "",
            "preview": (part.get("result_body") or part.get("text") or "")[:800],
            "thinking": (part.get("thinking") or "")[:400],
            "artifacts": _sse_artifacts(arts),
            "files": written,
            "diff": (diff or "")[:12000],
            "prompt_tokens": part.get("prompt_tokens"),
            "completion_tokens": part.get("completion_tokens"),
            "latency_s": part.get("latency_s"),
        }

    # announce starts
    for i, m in enumerate(models):
        yield {"type": "fork_start", "fork_id": f"m{i}", "model": m, "index": i}

    results: list[dict[str, Any]] = []
    for coro in asyncio.as_completed([_one(i, m) for i, m in enumerate(models)]):
        try:
            r = await coro
            results.append(r)
            yield {
                "type": "fork_done",
                "fork_id": r["fork_id"],
                "model": r["model"],
                "index": r["index"],
                "preview": r["preview"],
                "thinking": r["thinking"],
                "artifacts": r["artifacts"],
                "files": r["files"],
                "diff": r["diff"][:4000],
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "latency_s": r["latency_s"],
            }
        except Exception as e:  # noqa: BLE001
            yield {"type": "fork_error", "message": str(e)}

    results.sort(key=lambda x: x.get("index", 0))
    yield {
        "type": "fork_final",
        "forks": [
            {
                "fork_id": r["fork_id"],
                "model": r["model"],
                "preview": r["preview"],
                "diff": r["diff"][:6000],
                "files": r["files"],
                "text": r["text"][:4000],
            }
            for r in results
        ],
    }
