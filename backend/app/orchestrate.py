"""Studio orchestration: role skills × mode depth + live cooperative stream."""

from __future__ import annotations

import asyncio
import contextvars
import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
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
from app.media_packs import (
    allowlisted_image_ids,
    catalog_image_urls,
    detect_media_niche,
)
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


def _task_needs_api_backend(user_text: str | None) -> bool:
    """Brief/task mentions API or lead form that must hit a real backend route."""
    if not (user_text or "").strip():
        return False
    return bool(
        re.search(
            r"(?i)/api/[a-zA-Z0-9_/\-]+|POST\s+/api/|\bbooking\b|"
            r"форма\s+запис|оставить\s+заявк|api/lead|api/booking",
            user_text or "",
        )
    )


def _ensure_api_backend(team: list[str], user_text: str | None) -> list[str]:
    """If task needs API and team has ≥2 slots, backend must be present.

    Never drop frontend from a UI/landing team — swap tests/design only.
    """
    if not _task_needs_api_backend(user_text) or len(team) < 2:
        return team
    if "backend" in team:
        # Ensure frontend stays if this looks like a landing/site
        text = user_text or ""
        if re.search(r"(?i)лендинг|сайт|landing|автосервис|сто\b|кофейн", text):
            if "frontend" not in team:
                out = list(team)
                for cand in ("tests", "design"):
                    if cand in out:
                        out[out.index(cand)] = "frontend"
                        return out
        return team
    out = list(team)
    for cand in ("tests", "design"):
        if cand in out:
            out[out.index(cand)] = "backend"
            # keep frontend if present
            return out
    # last resort: replace non-frontend
    for i in range(len(out) - 1, -1, -1):
        if out[i] != "frontend":
            out[i] = "backend"
            return out
    return out


def _ensure_app_team(team: list[str], n: int, user_text: str | None) -> list[str]:
    """App intent: keep FE+BE+tests when N≥3 (Flash often skips tests otherwise)."""
    n = max(1, min(4, int(n)))
    if n == 1:
        return ["frontend"]
    if n == 2:
        return _ensure_api_backend(["frontend", "backend"], user_text)
    # N=3: drop design before tests — contracts matter more for apps
    core = ["frontend", "backend", "tests"]
    if n >= 4:
        core = ["design", "frontend", "backend", "tests"]
    # preserve any extra ranking hint from incoming team order for ties
    ordered: list[str] = []
    for r in team:
        if r in core and r not in ordered:
            ordered.append(r)
    for r in core:
        if r not in ordered:
            ordered.append(r)
    return _ensure_api_backend(ordered[:n], user_text)


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

    Landing tasks with /api/booking (etc.) force backend into the team when N≥2.
    App intent keeps tests in the team when N≥3.
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
        if effective == "app":
            return _ensure_app_team(team, n, user_text)
        if n >= 3 and len(team) < n:
            team = list(team_for_intent("feature"))
        if user_text and n < len(team):
            team = rank_roles_for_task(user_text, team)
        cut = team[:n]
        # Single-agent landing/site must be frontend (not API-only backend)
        if n == 1 and user_text and re.search(
            r"(?i)лендинг|сайт|landing|автосервис|сто\b|кофейн|магазин|клиник|салон",
            user_text,
        ):
            return ["frontend"]
        if n == 1 and user_text and re.search(
            r"(?i)приложен|web\s*app|\bapp\b|to-?do|задач",
            user_text,
        ):
            return ["frontend"]
        return _ensure_api_backend(cut, user_text)
    meta = MODE_META[mode]
    if mode in ("ultra", "premium"):
        if effective == "app":
            return _ensure_app_team(team, 4, user_text)
        base = team_for_intent("feature") if len(team) < 4 else team
        if user_text:
            base = rank_roles_for_task(user_text, list(base))
            # keep full 4 but preferred order for waves still via _phased_team
        return _ensure_api_backend(base[:4], user_text)
    cut = team[: int(meta["max_agents"])]
    if effective == "app":
        return _ensure_app_team(team, len(cut) or int(meta["max_agents"]), user_text)
    if user_text and len(team) > len(cut):
        cut = rank_roles_for_task(user_text, team)[: int(meta["max_agents"])]
    # mode=light max_agents=1 → same landing rule
    if len(cut) == 1 and user_text and re.search(
        r"(?i)лендинг|сайт|landing|автосервис|сто\b|кофейн|магазин|клиник|салон",
        user_text,
    ):
        return ["frontend"]
    return _ensure_api_backend(cut, user_text)


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
    # Workers: cheapest first so bulk code roles (design/FE early waves)
    # burn less $ and fragile providers (e.g. grok) don't block wave 1.
    rest = ranked[1:] or [judge]
    workers = sorted(rest, key=_model_strength)
    return {"judge": judge, "workers": workers, "all": clean}


def bind_team_models(team_models: list[str] | None, team: list[str]) -> dict[str, Any] | None:
    pack = resolve_pack_models(team_models)
    if not pack:
        _TEAM_MODEL_MAP.set(None)
        return None
    workers: list[str] = list(pack["workers"])
    workers_asc = sorted(workers, key=_model_strength)  # cheap → expensive
    workers_desc = list(reversed(workers_asc))
    role_map: dict[str, str] = {}
    # Frontend carries the landing — prefer stable Gemini flash over flaky grok/haiku.
    if "frontend" in team:
        gemini_fe = [
            w
            for w in workers_desc
            if "gemini" in w.lower() and "flash" in w.lower()
        ]
        role_map["frontend"] = gemini_fe[0] if gemini_fe else workers_desc[0]
    wi = 0
    for role in team:
        if role in JUDGE_ROLES or role in role_map:
            continue
        mid = workers_asc[wi % len(workers_asc)]
        # Prefer variety vs frontend when possible
        if (
            len(workers_asc) > 1
            and mid == role_map.get("frontend")
            and role != "frontend"
        ):
            wi += 1
            mid = workers_asc[wi % len(workers_asc)]
        role_map[role] = mid
        wi += 1
    payload = {
        "judge": pack["judge"],
        "workers": workers_asc,
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
# /src/deck/ — HTML presentations (same frontend agent)
ALLOWED_SRC_ROOTS = tuple(ROLE_SRC_PREFIX.values()) + ("/src/deck/",)

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
# Flash app traps
_ALERT_SUCCESS = re.compile(
    r"""alert\s*\(\s*(['\"`])([^'\"`]*?(?:заказ|сохран|принят|успех|оформлен|отправлен|готово)[^'\"`]*)\1\s*\)""",
    re.I,
)
_INLINE_ONCLICK = re.compile(r"""\sonclick\s*=\s*(['\"])[\s\S]*?\1""", re.I)
_LOCAL_ASSET_URL = re.compile(
    r"""(['\"])(/assets/[a-zA-Z0-9_\-./]+\.(?:png|jpe?g|webp|gif|svg))\1""",
    re.I,
)
_REMOTE_FLOWER = (
    "https://images.unsplash.com/photo-1490750967868-88aa4486c946"
    "?auto=format&fit=crop&w=800&q=80"
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
        # Drop success alert(...) — forces honest status UI
        out = _ALERT_SUCCESS.sub(
            "/* hardened: removed success alert — use role=status/alert */ undefined",
            out,
        )
        # Strip inline onclick= (prefer addEventListener)
        out = _INLINE_ONCLICK.sub("", out)
    # App DoD: logic only in app.js — GPT/Haiku dump second loadOrders into index.html
    if pl.endswith((".html", ".htm")) and "/frontend/" in pl.replace("\\", "/"):
        # Keep external <script src="...">, drop inline <script>...</script>
        if re.search(r"<script\b(?![^>]*\bsrc=)[^>]*>", out, re.I):
            out2 = re.sub(
                r"<script\b(?![^>]*\bsrc=)[^>]*>[\s\S]*?</script\s*>",
                "<!-- hardened: removed inline script — use app.js -->",
                out,
                flags=re.I,
            )
            # Ensure app.js is linked
            if "app.js" in out2 and not re.search(
                r"""<script[^>]+src=["'][^"']*app\.js["']""", out2, re.I
            ):
                out2 = out2.replace(
                    "</body>",
                    '<script src="app.js"></script>\n</body>',
                    1,
                )
            elif "app.js" not in out2 and "</body>" in out2:
                out2 = out2.replace(
                    "</body>",
                    '<script src="app.js"></script>\n</body>',
                    1,
                )
            out = out2
    if pl.endswith(".js") and "/frontend/" in pl.replace("\\", "/"):
        # Subpath demos (/demo/…/) break on API="" → fetch("/api/…") hits site root 404
        out = re.sub(
            r"""(const|let|var)\s+API\s*=\s*["']/?["']\s*;""",
            r'const API = ".";',
            out,
        )
        out = re.sub(
            r"""(const|let|var)\s+API\s*=\s*["']["']\s*;""",
            r'const API = ".";',
            out,
        )
        # Absolute /api from pages under /demo/…/
        out = re.sub(r"""fetch\(\s*(['\"])/api/""", r"fetch(\1./api/", out)
        # Flash often renders data-id buttons without click wiring
        if re.search(r"data-id=", out) and not re.search(
            r"dataset\.id|getAttribute\(\s*['\"]data-id['\"]|\[data-id\]|data-pick",
            out,
        ):
            out += (
                "\n\n/* hardened: wire catalog CTA */\n"
                "document.addEventListener('click', (e) => {\n"
                "  const btn = e.target && e.target.closest && e.target.closest('[data-id]');\n"
                "  if (!btn) return;\n"
                "  const id = btn.getAttribute('data-id');\n"
                "  const sel = document.querySelector('#bouquet_id, #product_id, #item_id, select[name=\"bouquet_id\"], select[name=\"product_id\"]');\n"
                "  if (sel) sel.value = id;\n"
                "  const orderBtn = document.querySelector('[data-nav=\"order\"], [data-view=\"order\"]');\n"
                "  if (orderBtn) orderBtn.click();\n"
                "});\n"
            )
        # Field aliases: Flash invents .title while API has .name
        out = out.replace("${i.title}", "${i.name || i.title}")
        out = out.replace("${b.title}", "${b.name || b.title}")
        out = out.replace("${item.title}", "${item.name || item.title}")
        out = out.replace("i.title}", "i.name || i.title}")
        out = re.sub(
            r"\$\{(\w+)\.title\}",
            r"${\1.name || \1.title}",
            out,
        )
        out = re.sub(
            r"\b(state\.cart|cart|selected|b|i|item)\.title\b",
            r"(\1.name || \1.title)",
            out,
        )
        # image alias
        out = re.sub(
            r"\$\{(\w+)\.image\}",
            r"${\1.image || \1.image_url}",
            out,
        )
        if "image_url" in out and not re.search(r"\b\.image\b|b\.image|item\.image", out):
            out = out.replace("${b.image_url}", "${b.image || b.image_url}")
            out = out.replace("${item.image_url}", "${item.image || item.image_url}")
            out = out.replace("${i.image_url}", "${i.image || i.image_url}")
        # Prefer numeric data-pick=id over JSON blob in attribute
        out = re.sub(
            r"""data-pick=['\"]\$\{JSON\.stringify\((\w+)\)\}['\"]""",
            r'data-pick="${\1.id}"',
            out,
        )
    if pl.endswith(".py") and "/backend/" in pl.replace("\\", "/"):
        # Ghost local assets in mock DB → remote https
        out = _LOCAL_ASSET_URL.sub(lambda m: f"{m.group(1)}{_REMOTE_FLOWER}{m.group(1)}", out)
        # Public MVP must not require mystery auth headers
        out = re.sub(
            r"(\w+)\s*:\s*str\s*=\s*Header\(\s*\.\.\.\s*\)",
            r'\1: str = Header(default="demo")',
            out,
        )
        # Alias image_url field in seed dicts → also expose image
        if "image_url" in out and '"image"' not in out and "'image'" not in out:
            out = out.replace('"image_url":', '"image":')
        # title-only seeds → name (FE + orders product_name)
        if re.search(r"""['\"]title['\"]\s*:""", out) and not re.search(
            r"""['\"]name['\"]\s*:""", out
        ):
            out = re.sub(
                r"""(['\"])title\1\s*:\s*""",
                r'\1name\1: ',
                out,
            )
            out = out.replace('"title":', '"name":').replace("'title':", "'name':")
        # description → desc alias for etalon FE
        if re.search(r"""['\"]description['\"]\s*:""", out) and not re.search(
            r"""['\"]desc['\"]\s*:""", out
        ):
            out = out.replace('"description":', '"desc":').replace(
                "'description':", "'desc':"
            )
        # Replace seed images with verified media-pack URLs (Flash invents 404 IDs)
        niche = "grocery" if re.search(
            r"PRODUCTS\s*=|/api/products|category['\"]\s*:\s*['\"]Овощи", out
        ) else ("flowers" if re.search(r"BOUQUETS\s*=|/api/bouquets", out) else None)
        if niche:
            allowed = allowlisted_image_ids(niche)
            pack = catalog_image_urls(niche, n=12)
            idx = 0

            def _swap(m: re.Match[str]) -> str:
                nonlocal idx
                url = m.group(2)
                pid = re.search(r"photo-([0-9a-zA-Z_-]+)", url)
                if pid and pid.group(1) in allowed:
                    return m.group(0)
                repl = pack[idx % len(pack)]
                idx += 1
                return f"{m.group(1)}{repl}{m.group(3)}"

            out = re.sub(
                r"""(['\"]image(?:_url)?['\"]\s*:\s*['\"])(https?://[^'\"]+)(['\"])""",
                _swap,
                out,
            )
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


_APP_SHOP_DIR = (
    Path(__file__).resolve().parent
    / "agent_skills"
    / "frontend"
    / "templates"
    / "app-shop"
)
_APP_SHOP_PRODUCTS_DIR = (
    Path(__file__).resolve().parent
    / "agent_skills"
    / "frontend"
    / "templates"
    / "app-shop-products"
)
_APP_SHOP_CSS = _APP_SHOP_DIR / "styles.css"
_APP_SHOP_HTML = _APP_SHOP_DIR / "index.html"
_APP_SHOP_JS = _APP_SHOP_DIR / "app.js"
_APP_SHOP_PRODUCTS_HTML = _APP_SHOP_PRODUCTS_DIR / "index.html"
_APP_SHOP_PRODUCTS_JS = _APP_SHOP_PRODUCTS_DIR / "app.js"
_APP_DENSITY_CSS = (
    Path(__file__).resolve().parent
    / "agent_skills"
    / "frontend"
    / "templates"
    / "app-density.css"
)


def _catalogish_blob(blob: str) -> bool:
    return bool(
        re.search(
            r"bouquet|каталог|catalog|/api/bouquets|/api/products|order-form|"
            r"data-filter|букет|app-shop|продукт|товар|магазин|grocery",
            blob,
            re.I,
        )
    )


def _ensure_app_density(
    arts_by_path: dict[str, dict[str, Any]],
    *,
    allow_etalon_replace: bool = False,
) -> None:
    """Catalog/shop density.

    Gate/repair: do NOT replace HTML/JS (model invents under brief).
    Final ship only: if still behaviorally thin, inject adapted template as failsafe.
    """
    from app.skills import skills_enabled

    if not skills_enabled():
        # Skill packs / golden etalon off — never stamp templates onto agents' work.
        return

    styles = arts_by_path.get("/src/frontend/styles.css")
    html = arts_by_path.get("/src/frontend/index.html")
    js = arts_by_path.get("/src/frontend/app.js")
    blob = "\n".join((a.get("content") or "") for a in (html, styles, js) if a)
    if not _catalogish_blob(blob):
        # non-shop: do NOT append shop density CSS (Instrument Serif / panel stamps).
        # Thin CSS is a gate problem — uniqueness > forced chrome pack.
        return

    if not allow_etalon_replace:
        return

    html_body = (html or {}).get("content") or ""
    js_body = (js or {}).get("content") or ""
    css_body = (styles or {}).get("content") or ""

    # Behavioral thin — not “missing panel__head from one template”
    products = _is_products_domain(blob, None)
    thin_html = not _app_shop_file_ok("index.html", html_body, products=products)
    thin_js = not _app_shop_file_ok("app.js", js_body, products=products)
    thin_css = not _app_shop_file_ok("styles.css", css_body, products=products)
    et_html = _APP_SHOP_PRODUCTS_HTML if products and _APP_SHOP_PRODUCTS_HTML.is_file() else _APP_SHOP_HTML
    et_js = _APP_SHOP_PRODUCTS_JS if products and _APP_SHOP_PRODUCTS_JS.is_file() else _APP_SHOP_JS
    if products:
        if "cart-badge" not in html_body and "addToCart" not in js_body:
            thin_html = True
            thin_js = True

    # Preserve brand name from model if present
    brand = "Свежая Полка" if products else "Букет Лайн"
    m = re.search(
        r"""brand__name["'][^>]*>\s*([^<]+)\s*<|class=["'][^"']*brand__name[^"']*["'][^>]*>\s*([^<]+)"""
        r"""|<title>\s*([^<]{2,40})""",
        html_body,
        re.I,
    )
    if m:
        brand = (m.group(1) or m.group(2) or m.group(3) or brand).strip() or brand

    if thin_css and _APP_SHOP_CSS.is_file() and "hardened: golden app-shop" not in css_body:
        pack = _APP_SHOP_CSS.read_text(encoding="utf-8")
        arts_by_path["/src/frontend/styles.css"] = {
            **(styles or {"path": "/src/frontend/styles.css", "title": "styles.css"}),
            "path": "/src/frontend/styles.css",
            "title": "styles.css",
            "content": "/* hardened: golden app-shop styles (skill etalon) */\n" + pack,
            "hardened": True,
            "role": (styles or {}).get("role") or "frontend",
        }

    if thin_html and et_html.is_file() and "hardened: golden app-shop html" not in html_body:
        h = et_html.read_text(encoding="utf-8")
        if brand not in h:
            h = h.replace("Букет Лайн", brand).replace("Свежая Полка", brand)
        arts_by_path["/src/frontend/index.html"] = {
            **(html or {"path": "/src/frontend/index.html", "title": "index.html"}),
            "path": "/src/frontend/index.html",
            "title": "index.html",
            "content": "<!-- hardened: golden app-shop html (skill etalon) -->\n" + h,
            "hardened": True,
            "role": (html or {}).get("role") or "frontend",
        }

    if thin_js and et_js.is_file() and "hardened: golden app-shop js" not in js_body:
        j = et_js.read_text(encoding="utf-8")
        arts_by_path["/src/frontend/app.js"] = {
            **(js or {"path": "/src/frontend/app.js", "title": "app.js"}),
            "path": "/src/frontend/app.js",
            "title": "app.js",
            "content": "/* hardened: golden app-shop js (skill etalon) */\n" + j,
            "hardened": True,
            "role": (js or {}).get("role") or "frontend",
        }

    # Fonts if HTML somehow lacks them
    html2 = arts_by_path.get("/src/frontend/index.html")
    if html2 and "fonts.googleapis.com" not in (html2.get("content") or ""):
        h = html2.get("content") or ""
        link = (
            '<link rel="preconnect" href="https://fonts.googleapis.com" />\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />\n'
            '<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap" rel="stylesheet" />\n'
        )
        if "<head>" in h:
            html2["content"] = h.replace("<head>", "<head>\n" + link, 1)
            arts_by_path["/src/frontend/index.html"] = html2


def _app_shop_repair_bundle() -> str:
    """Repair hint: density reference — invent under brief, don't clone brand."""
    chunks: list[str] = [
        "Repair: приложение сломано/тонкое. Сдай плотный UI **под бриф юзера**. "
        "Ниже — справка по потокам (не копируй бренд/CSS эталона байт-в-байт). "
        "DoD: nav≥2 экрана, каталог+заказ/корзина+история, fetch+res.ok, app.js only."
    ]
    for fname, lang in (
        ("index.html", "html"),
        ("styles.css", "css"),
        ("app.js", "javascript"),
    ):
        path = {
            "index.html": _APP_SHOP_HTML,
            "styles.css": _APP_SHOP_CSS,
            "app.js": _APP_SHOP_JS,
        }[fname]
        if path.is_file():
            body = path.read_text(encoding="utf-8")
            hint = body[:1400] + ("\n/* … trim … */\n" if len(body) > 1400 else "")
            chunks.append(
                f"\n### path=/src/frontend/{fname} (паттерн)\n```{lang}\n"
                + hint
                + "\n```"
            )
    return "\n".join(chunks)


def _seed_facet_values(be_blob: str) -> list[str]:
    vals = [
        v.strip()
        for v in re.findall(
            r"""['\"](?:category|tag)['\"]\s*:\s*['\"]([^'\"]+)['\"]""",
            be_blob or "",
        )
        if v.strip()
    ]
    # unique preserve order
    out: list[str] = []
    for v in vals:
        if v not in out:
            out.append(v)
    return out


def _sync_catalog_filters(arts_by_path: dict[str, dict[str, Any]]) -> None:
    """Rewrite FE data-filter chips to match backend seed category/tag values."""
    html = arts_by_path.get("/src/frontend/index.html")
    js = arts_by_path.get("/src/frontend/app.js")
    be_blob = "\n".join(
        (a.get("content") or "")
        for p, a in arts_by_path.items()
        if p.startswith("/src/backend") and p.endswith(".py")
    )
    if not html or not be_blob:
        return
    facets = _seed_facet_values(be_blob)
    if len(facets) < 2:
        return
    html_body = html.get("content") or ""
    chips = {
        c
        for c in re.findall(r"""data-filter=["']([^"']+)["']""", html_body, re.I)
        if c.lower() not in ("all", "все", "*")
    }
    if chips and chips.issubset(set(facets)):
        return
    # Rebuild filters block
    chip_html = ['<button type="button" class="chip is-on" data-filter="all">Все</button>']
    for fac in facets[:6]:
        chip_html.append(
            f'<button type="button" class="chip" data-filter="{fac}">{fac}</button>'
        )
    new_filters = '<div class="filters" role="toolbar" aria-label="Фильтры">\n          ' + "\n          ".join(chip_html) + "\n        </div>"
    if re.search(r'<div class="filters"[^>]*>.*?</div>', html_body, re.S | re.I):
        html_body = re.sub(
            r'<div class="filters"[^>]*>.*?</div>',
            new_filters,
            html_body,
            count=1,
            flags=re.S | re.I,
        )
    else:
        # insert after panel__head / before catalog-list
        html_body = html_body.replace(
            'id="catalog-list"',
            new_filters + '\n        <div id="catalog-list"',
            1,
        )
    html["content"] = html_body
    html["hardened"] = True
    arts_by_path["/src/frontend/index.html"] = html

    if js:
        js_body = js.get("content") or ""
        # Prefer category then tag for filter match
        js_body = re.sub(
            r"""filter\s*===\s*["']all["']\s*\|\|\s*p\.(tag|category)\s*===\s*filter""",
            'filter === "all" || p.category === filter || p.tag === filter',
            js_body,
        )
        js_body = re.sub(
            r"""filter\s*===\s*["']all["']\s*\|\|\s*\w+\.(tag|category)\s*===\s*filter""",
            'filter === "all" || p.category === filter || p.tag === filter',
            js_body,
        )
        # Kill tiny inline preview hacks
        js_body = re.sub(
            r"""\s*style=["']max-width:\s*120px;?[^"']*["']""",
            "",
            js_body,
            flags=re.I,
        )
        js["content"] = js_body
        js["hardened"] = True
        arts_by_path["/src/frontend/app.js"] = js


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
    by_path = {(a.get("path") or ""): a for a in out if a.get("path")}
    _ensure_app_density(by_path, allow_etalon_replace=False)
    # rebuild list preserving order, with updated density
    return [by_path.get(a.get("path") or "", a) for a in out]


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


def filter_studio_artifacts(
    arts: list[dict[str, Any]],
    *,
    allow_etalon_replace: bool = False,
) -> list[dict[str, Any]]:
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
        # Drop junk dumps: backend_1.txt / design_2.css numbered scratch files
        base = path.rsplit("/", 1)[-1]
        if re.match(r"^(frontend|backend|design|tests)_\d+\.(txt|md)$", base, re.I):
            continue
        if not path.startswith(ALLOWED_SRC_ROOTS):
            continue
        item = dict(a)
        item["path"] = path
        item["content"] = harden_artifact_content(path, item.get("content") or "")
        prev = by_path.get(path)
        if not prev or len(item.get("content") or "") >= len(prev.get("content") or ""):
            by_path[path] = item
    # SSoT: design tokens win — drop FE tokens.css; INLINE tokens into styles.css
    # (preview/srcdoc/static demos cannot resolve @import ../design/tokens.css)
    if "/src/design/tokens.css" in by_path:
        by_path.pop("/src/frontend/tokens.css", None)
        styles = by_path.get("/src/frontend/styles.css")
        tokens_body = (by_path["/src/design/tokens.css"].get("content") or "").strip()
        if styles and tokens_body:
            body = styles.get("content") or ""
            body = re.sub(
                r"@import\s+url\([\"']?[^\"')]*tokens\.css[\"']?\)\s*;?\s*",
                "",
                body,
                flags=re.I,
            )
            if "/* inlined design tokens" not in body:
                styles["content"] = (
                    "/* inlined design tokens (SSoT) */\n"
                    + tokens_body
                    + "\n\n"
                    + body.lstrip()
                )
                styles["hardened"] = True
                by_path["/src/frontend/styles.css"] = styles
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
    _ensure_app_density(by_path, allow_etalon_replace=allow_etalon_replace)
    _sync_catalog_filters(by_path)
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
        f"- Темп: ## Мышление ≤8 строк, затем ## Результат с готовыми файлами (без воды)\n"
    )
    if role == "frontend":
        rules += (
            "- Токены design = SSoT: **свой `:root` в styles.css** "
            "(предпочтительно). Голый `@import '../design/tokens.css'` ломает static demo.\n"
            "- Файл стилей: `styles.css` (не style.css). Цвета через `var(--…)`.\n"
            "- Интерактив = button/a, не div onclick\n"
            "- fetch/API: только path из Locked contract (если есть)\n"
            "- **Лендинг/сайт DoD (принципы, НЕ один шаблон):**\n"
            "  UNIQUE из брифа (бренд, IA, палитра, копирайт) — см. uniqueness.md;\n"
            "  предметный media-якорь; честные контакты; форма без лжи в catch;\n"
            "  достаточная плотность секций/контента; motion+mobile; anti-AI look;\n"
            "  zeus-badge + публичный /go/. "
            "Эталоны good_* = планка качества, не обязательные классы/#vitrine/.top__nav.\n"
            "- Презентация: path=/src/deck/, достаточное число слайдов, разные фото, CTA\n"
            "- Remote https из Media pack brief; не assets/ без файла\n"
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


def _parts_have_path_conflicts(parts: list[dict[str, Any]]) -> bool:
    """True when two agents wrote different substantial bodies for the same path."""
    by_path: dict[str, str] = {}
    for p in parts:
        if p.get("role") in ("synth", "reviewer"):
            continue
        for a in p.get("artifacts") or []:
            path = (a.get("path") or "").strip()
            body = (a.get("content") or "").strip()
            if not path or len(body) < 40:
                continue
            prev = by_path.get(path)
            if prev is not None and prev != body:
                return True
            by_path[path] = body
    return False


def _assemble_fast_merge(
    parts: list[dict[str, Any]],
    *,
    user_text: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Deterministic merge — preserves agent code, skips slow/lossy LLM synth."""
    role_order = {"design": 0, "frontend": 1, "backend": 2, "tests": 3, "docs": 4, "general": 5}
    by_path: dict[str, dict[str, Any]] = {}
    for p in sorted(parts, key=lambda x: role_order.get(x.get("role") or "", 99)):
        if p.get("role") in ("synth", "reviewer"):
            continue
        for a in p.get("artifacts") or []:
            path = (a.get("path") or "").strip()
            if not path:
                continue
            prev = by_path.get(path)
            body = a.get("content") or ""
            if not prev or len(body) >= len(prev.get("content") or ""):
                by_path[path] = dict(a)
    arts = filter_studio_artifacts(list(by_path.values()))
    lines = [
        "## Мышление",
        "Склейка без повторной генерации: пути агентов не конфликтуют — "
        "сохраняю исходный код команд (качество выше, чем переписывать судьёй).",
        "",
        f"Задача: {user_text.strip()[:240]}",
        "",
        "## Результат",
    ]
    for a in arts:
        path = a.get("path") or "/src/frontend/out.txt"
        lang = a.get("language") or path.rsplit(".", 1)[-1]
        body = a.get("content") or ""
        lines.append(f"```{lang} path={path}\n{body}\n```")
        lines.append("")
    return "\n".join(lines).strip(), arts


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
    # App-shop etalon ~20KB FE — Flash must emit full HTML+CSS+JS without truncation
    try:
        from app.config import get_settings as _gs

        _ceil = int(getattr(_gs(), "UPSTREAM_MAX_OUTPUT_TOKENS", 65536) or 65536)
    except Exception:  # noqa: BLE001
        _ceil = 65536
    # No per-role artificial cutoffs — same high ceiling for every Studio agent.
    max_tok = max(1024, _ceil)
    data = await upstream.chat_completions(
        model=model, messages=messages, max_tokens=max_tok
    )
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


def _app_shop_file_ok(fname: str, body: str, *, products: bool = False) -> bool:
    """Behavioral density — not etalon class-name clone."""
    b = body or ""
    if fname == "index.html":
        multi = len(re.findall(r"data-screen\s*=", b, re.I)) >= 2 or bool(
            re.search(r"data-view\s*=", b, re.I)
        )
        has_list = bool(
            re.search(
                r"id=[\"'][^\"']*(catalog|list|grid|items|products|bouquets)",
                b,
                re.I,
            )
        )
        has_form = bool(re.search(r"<form\b", b, re.I)) or bool(
            re.search(r"cart-badge|id=[\"']cart", b, re.I)
        )
        no_inline_logic = not re.search(
            r"<script\b(?![^>]*\bsrc=)[^>]*>[\s\S]{40,}?</script>", b, re.I
        )
        return len(b) >= 2800 and multi and has_list and has_form and no_inline_logic
    if fname == "styles.css":
        layout = bool(re.search(r"display\s*:\s*(grid|flex)", b, re.I))
        return len(b) >= 3500 and layout and ("{" in b)
    if fname == "app.js":
        has_fetch = bool(re.search(r"\bfetch\s*\(", b))
        has_api = bool(re.search(r"""API\s*=\s*["']\.|["']/api/|`\$\{API\}|/api/""", b))
        has_orders = bool(re.search(r"loadOrders|/api/orders|orders-list", b, re.I))
        has_catalog = bool(
            re.search(r"renderCatalog|catalog-list|/api/(products|bouquets|items)", b, re.I)
        )
        has_cta = bool(re.search(r"addToCart|data-pick|dataset\.pick|В корзину|В заказ", b))
        has_ok = bool(re.search(r"\.ok\b|!res\.ok|!r\.ok", b))
        cart_ok = (not products) or bool(re.search(r"addToCart|cart-badge|В корзину", b))
        return (
            len(b) >= 3200
            and has_fetch
            and has_api
            and has_orders
            and has_catalog
            and has_cta
            and has_ok
            and cart_ok
        )
    return bool(b)


def _pick_brand_from_task(user_text: str) -> str | None:
    m = re.search(r"[«\"]([^»\"]{2,40})[»\"]", user_text or "")
    if m:
        return m.group(1).strip()
    return None


def _is_products_domain(user_text: str, brief: str | None = None) -> bool:
    """Grocery/products shop — bare «цвет» is CSS, not flowers."""
    blob = f"{user_text or ''}\n{brief or ''}"
    grocery = bool(
        re.search(
            r"/api/products|продукт|grocery|лавка|супермаркет|овощ|фрукт|молоч|"
            r"свежая\s+полка|в\s+корзину|cart-badge",
            blob,
            re.I,
        )
    )
    flowers = bool(
        re.search(
            r"/api/bouquets|букет|bouquet|flower|флорист|роза|тюльпан",
            blob,
            re.I,
        )
    )
    if grocery and not flowers:
        return True
    if grocery and flowers:
        return bool(
            re.search(r"/api/products|овощ|фрукт|молоч|в\s+корзину|grocery", blob, re.I)
        )
    return False


def _adapt_shop_domain(body: str, *, brand: str, products: bool) -> str:
    """Map flower etalon labels/API → product shop when task demands it."""
    out = body or ""
    if brand and brand != "Букет Лайн":
        out = out.replace("Букет Лайн", brand)
    if not products:
        return out
    reps = (
        ("/api/bouquets", "/api/products"),
        ("bouquets", "products"),
        ("bouquet_id", "product_id"),
        ("Bouquet", "Product"),
        ("bouquet", "product"),
        ("Букеты", "Товары"),
        ("букеты", "товары"),
        ("Букет", "Товар"),
        ("букет", "товар"),
        ("Каталог букетов", "Каталог товаров"),
        ("Выберите букет", "Выберите товар"),
        ('data-filter="хит"', 'data-filter="Овощи"'),
        ('data-filter="премиум"', 'data-filter="Фрукты"'),
        ('data-filter="новый"', 'data-filter="Молочка"'),
        (">хит<", ">Овощи<"),
        (">премиум<", ">Фрукты<"),
        (">новый<", ">Молочка<"),
    )
    for a, b in reps:
        out = out.replace(a, b)
    # JS filter by category for grocery
    out = re.sub(
        r"""filter\s*===\s*["']all["']\s*\|\|\s*\w+\.tag\s*===\s*filter""",
        'filter === "all" || p.category === filter || p.tag === filter',
        out,
    )
    return out


async def _role_call_app_frontend(
    *,
    brief: str | None,
    intent: str,
    mode: str,
    history: list[dict[str, Any]],
    user_text: str,
    model: str,
    prior_parts: list[dict[str, Any]] | None = None,
    locked_contract: dict[str, Any] | None = None,
    product_brief: str | None = None,
) -> dict[str, Any]:
    """Per-file FE for weak models: invent under brief; template only if DoD fails.

    DoD is behavioral (screens/fetch/cart/orders), not class-name clone of app-shop.
    """
    t0 = time.perf_counter()
    products = _is_products_domain(user_text, brief)
    brand = _pick_brand_from_task(user_text) or (
        "Свежая Полка" if products else "Букет Лайн"
    )
    html_src = _APP_SHOP_PRODUCTS_HTML if products and _APP_SHOP_PRODUCTS_HTML.is_file() else _APP_SHOP_HTML
    js_src = _APP_SHOP_PRODUCTS_JS if products and _APP_SHOP_PRODUCTS_JS.is_file() else _APP_SHOP_JS
    files = (
        ("index.html", "html", html_src),
        ("styles.css", "css", _APP_SHOP_CSS),
        ("app.js", "javascript", js_src),
    )
    arts: list[dict[str, Any]] = []
    texts: list[str] = []
    prompt_tokens = 0
    completion_tokens = 0
    sources: dict[str, str] = {}

    base_user = _role_call_user_text(
        "frontend",
        user_text,
        prior_parts or [],
        locked_contract=locked_contract,
        product_brief=product_brief,
    )
    domain_note = (
        "Домен: магазин продуктов. API /api/products + /api/orders. "
        "Нужна корзина (В корзину + badge) и экран покупок. "
        "Поля карточки под продукты — НЕ composition/size/stems.\n"
        if products
        else "Домен по brief (цветы/другое). API из задачи. "
        "Карточка и фильтры = сущность brief, не чужой ниши.\n"
    )

    for fname, lang, _path in files:
        # Principles only — never dump app-shop HTML/CSS into the prompt (stamps clones)
        density_hint = (
            "Плотность: chrome+nav, каталог с карточками (img+цена+CTA), "
            "корзина/заказ, история; empty/error/loading; "
            "фильтры меняют список; fetch с res.ok. "
            "Визуал и классы — под бриф, не «Букет Лайн»/«Свежая Полка»."
        )
        system = (
            f"Роль: frontend. Интент APP. Сейчас сдаёшь ТОЛЬКО один файл.\n"
            f"path=/src/frontend/{fname}\n"
            f"{domain_note}"
            f"Бренд из задачи: «{brand}». Изобрети UI под ЭТОТ бриф — "
            f"не клонируй один шаблон всем юзерам.\n"
            f"DoD: nav≥2 экрана; каталог+заказ/корзина+история; fetch+res.ok; "
            f"filters↔seed; логика только в app.js; API=\".\"; "
            f"файл плотный (не скелет). Имена CSS-классов — любые.\n"
            f"НЕ React. НЕ пиши другие файлы.\n"
            f"Формат: path=/src/frontend/{fname} затем ```{lang} … ```\n\n"
            f"{density_hint}\n"
            f"(Файл-эталон `{fname}` на диске — failsafe/справка, в промпт HTML не кладём.)"
        )
        if brief:
            system += f"\n\nБриф (источник правды):\n{(brief or '')[:2000]}"
        part = await _role_call(
            role="frontend",
            system=system,
            history=history,
            user_text=(
                base_user
                + f"\n\nСдай ТОЛЬКО /src/frontend/{fname} под задачу и бренд «{brand}». "
                f"Уникальный UI, рабочий DoD."
            ),
            model=model,
        )
        prompt_tokens += int(part.get("prompt_tokens") or 0)
        completion_tokens += int(part.get("completion_tokens") or 0)
        texts.append(part.get("text") or "")
        got = ""
        for a in part.get("artifacts") or []:
            if (a.get("path") or "").endswith(fname):
                got = a.get("content") or ""
                break
        if not got:
            for a in part.get("artifacts") or []:
                c = a.get("content") or ""
                if fname.endswith(".html") and "<html" in c.lower():
                    got = c
                elif fname.endswith(".css") and "{" in c and len(c) > len(got):
                    got = c
                elif fname.endswith(".js") and ("function" in c or "const " in c) and len(c) > len(got):
                    got = c
        got = _adapt_shop_domain(got, brand=brand, products=products)
        src = "model"
        if not got.strip():
            # Empty only — never stamp golden shop HTML onto every user
            got = (
                f"/* empty {fname}: model failed; do not ship clone */\n"
                if fname.endswith((".css", ".js"))
                else f"<!-- empty {fname}: model failed; do not ship clone -->\n"
            )
            src = "empty"
        elif not _app_shop_file_ok(fname, got, products=products):
            # Keep model output even if thin — gate will catch; uniqueness > template
            src = "model_thin"
        sources[fname] = src
        arts.append(
            {
                "path": f"/src/frontend/{fname}",
                "title": fname,
                "role": "frontend",
                "content": got,
                "hardened": False,
            }
        )

    note = (
        "## Результат\n"
        + "\n".join(f"- {k}: {v}" for k, v in sources.items())
        + "\n\n"
        + "\n\n".join(
            f"path=/src/frontend/{a['title']}\n```\n{(a.get('content') or '')[:200]}…\n```"
            for a in arts
        )
    )
    return {
        "role": "frontend",
        "title": get_skill("frontend")["title"],
        "label": get_skill("frontend")["label"],
        "model": model,
        "text": note,
        "thinking": "app: invent under brief (template fill only if DoD fails)",
        "result_body": note,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_s": round(time.perf_counter() - t0, 2),
        "artifacts": arts,
        "app_shop_sources": sources,
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
            if role == "frontend" and intent == "app" and _catalogish_blob(
                f"{user_text}\n{brief or ''}"
            ):
                part = await _role_call_app_frontend(
                    brief=brief,
                    intent=intent,
                    mode=mode,
                    history=hist,
                    user_text=user_text,
                    model=model_for_role(mode, role),
                    prior_parts=prior,
                    locked_contract=lock_snap,
                    product_brief=product_brief,
                )
            else:
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
        conflict = _parts_have_path_conflicts(parts)
        # Fast merge keeps agent code intact (often higher quality than LLM rewrite).
        # LLM synth only when two agents wrote different bodies for the same path.
        use_llm_synth = conflict

        if not use_llm_synth:
            yield {"type": "synth_start", "model": "fast-merge"}
            yield _status(
                "Склеиваю артефакты без переписывания (пути не конфликтуют)…",
                phase="synth",
            )
            final_text, synth_arts = _assemble_fast_merge(parts, user_text=user_text)
            parts.append(
                {
                    "role": "synth",
                    "title": "Сборка",
                    "label": "сборка",
                    "model": "fast-merge",
                    "text": final_text,
                    "thinking": "",
                    "result_body": final_text,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
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
        else:
            yield {"type": "synth_start", "model": synth_model}
            yield _status(
                "Конфликт путей — судья склеивает без потери контракта…",
                phase="synth",
            )
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
                max_tokens=8192,
            )
            final_text = upstream.extract_text(synth)
            sp, sc = upstream.extract_usage(synth)
            synth_arts = filter_studio_artifacts(extract_artifacts("docs", final_text))
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

    # One cheap repair pass for Flash traps on app/frontend
    _REPAIR_CODES = frozenset(
        {
            "react_without_ask",
            "fake_alert_success",
            "inline_onclick",
            "fake_form_success",
            "wrong_product_shape",
            "missing_state",
            "thin_catalog",
            "thin_styles",
            "dead_select",
            "missing_json_headers",
            "missing_address_field",
            "missing_orders_screen",
            "thin_app_chrome",
            "missing_filters",
            "missing_order_preview",
            "dead_pick_cta",
            "mystery_auth_header",
            "thin_catalog_seed",
            "thin_app_html",
            "thin_app_js",
            "filter_seed_mismatch",
            "seed_title_not_name",
            "thin_catalog_fields",
            "dead_catalog_images",
            "missing_cart",
            "inline_script_in_html",
        }
    )
    repair_hits = [f for f in gate_findings if f.get("code") in _REPAIR_CODES]
    # Backend seed repair first (contract + images)
    _BE_SEED_CODES = frozenset(
        {
            "thin_catalog_seed",
            "seed_title_not_name",
            "thin_catalog_fields",
            "filter_seed_mismatch",
            "dead_catalog_images",
        }
    )
    if any(f.get("code") in _BE_SEED_CODES for f in repair_hits) and any(
        p.get("role") == "backend" for p in parts
    ):
        be_codes = sorted(
            {f.get("code") for f in repair_hits if f.get("code") in _BE_SEED_CODES}
        )
        yield _status(
            f"Чиню backend seed (1× Flash): {', '.join(be_codes[:4])}",
            phase="build",
        )
        yield {
            "type": "repair_start",
            "role": "backend",
            "codes": be_codes,
            "model": model_for_role(mode, "backend"),
        }
        try:
            be_repair = await _role_call(
                role="backend",
                system=build_system("backend", brief, intent, mode),
                history=[],
                user_text=_role_call_user_text(
                    "backend",
                    user_text
                    + "\n\nREPAIR seed: ≥4 позиций, **name** (не title), image unsplash, "
                    "desc|composition, category|tag. "
                    "Значения category/tag = data-filter на FE (продукты: Овощи/Фрукты/Молочка; "
                    "цветы: хит/премиум/новый). "
                    "POST orders → product_name/bouquet_name = item['name']. "
                    "См. app-api.md.",
                    [p for p in parts if p.get("role") != "backend"],
                    locked_contract=locked_contract,
                    product_brief=product_brief,
                ),
                model=model_for_role(mode, "backend"),
            )
            be_repair["repaired"] = True
            parts = [p for p in parts if p.get("role") != "backend"]
            parts.append(be_repair)
            yield _agent_done_event(be_repair, preview_len=300)
            yield {
                "type": "repair_done",
                "role": "backend",
                "artifacts_n": len(be_repair.get("artifacts") or []),
            }
            pre_arts = []
            for p in parts:
                if p.get("role") in ("synth", "reviewer"):
                    continue
                pre_arts.extend(p.get("artifacts") or [])
            pre_arts = filter_studio_artifacts(pre_arts)
            gate_findings = evidence_mod.scan_all(pre_arts)
            repair_hits = [f for f in gate_findings if f.get("code") in _REPAIR_CODES]
        except Exception as e:  # noqa: BLE001
            yield _status(f"Ремонт backend не удался: {e}", phase="check")

    if repair_hits and any(p.get("role") == "frontend" for p in parts):
        _FE_CODES = _REPAIR_CODES - {
            "thin_catalog_seed",
            "seed_title_not_name",
            "thin_catalog_fields",
        }
        codes = sorted(
            {f.get("code") for f in repair_hits if f.get("code") in _FE_CODES}
        )
        if not codes:
            pass
        else:
            yield _status(
                f"Чиню фронт (1× Flash): {', '.join(codes[:5])}",
                phase="build",
            )
            yield {
                "type": "repair_start",
                "role": "frontend",
                "codes": codes,
                "model": model_for_role(mode, "frontend"),
            }
            fe_prev = []
            for p in parts:
                if p.get("role") == "frontend":
                    fe_prev.extend(p.get("artifacts") or [])
            repair_brief = (
                (brief or "")
                + "\n\n## REPAIR PASS (обязательно)\n"
                + "Предыдущая сдача провалила gate: "
                + ", ".join(codes)
                + ".\nПерепиши фронт под бриф: /src/frontend/index.html + styles.css + app.js.\n"
                "ЗАПРЕТ: React/Vue/JSX/createRoot/react-query/npm.\n"
                "ЗАПРЕТ: alert(), onclick=, inline <script> логика.\n"
                "DoD: nav≥2 экрана; каталог+заказ/корзина+история; fetch+res.ok; "
                "для продуктов — addToCart + cart-badge + «В корзину».\n"
                "Не клонируй чужой бренд; плотность не скелет.\n"
            )
            try:
                # Same per-file copy path as first pass — one-shot repair Flash only shrinks
                repair_part = await _role_call_app_frontend(
                    brief=repair_brief,
                    intent=intent,
                    mode=mode,
                    history=[],
                    user_text=user_text
                    + "\n\nREPAIR: почини gate (корзина/экраны/fetch) под этот бриф.",
                    model=model_for_role(mode, "frontend"),
                    prior_parts=[p for p in parts if p.get("role") != "frontend"],
                    locked_contract=locked_contract,
                    product_brief=product_brief,
                )
                repair_part["repaired"] = True
                parts = [p for p in parts if p.get("role") != "frontend"]
                parts.append(repair_part)
                yield _agent_done_event(repair_part, preview_len=300)
                yield {
                    "type": "repair_done",
                    "role": "frontend",
                    "artifacts_n": len(repair_part.get("artifacts") or []),
                    "app_shop_sources": repair_part.get("app_shop_sources"),
                }
                # re-scan after repair
                pre_arts = []
                for p in parts:
                    if p.get("role") in ("synth", "reviewer"):
                        continue
                    pre_arts.extend(p.get("artifacts") or [])
                pre_arts = filter_studio_artifacts(pre_arts)
                gate_findings = evidence_mod.scan_all(pre_arts)
                g_score, g_grade, g_gate = evidence_mod.score_from_findings(gate_findings)
                yield _status(
                    f"После ремонта: {g_gate} · {g_score} · находок {len(gate_findings)}",
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
                    "after_repair": True,
                }
            except Exception as e:  # noqa: BLE001
                yield _status(f"Ремонт фронта не удался: {e}", phase="check")

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

    # Final ship: density hints only — NEVER inject golden HTML/JS clone
    artifacts = filter_studio_artifacts(artifacts, allow_etalon_replace=False)
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
