"""Zeus Fusion — fixed 3-model panel + judge.

Product modes (``zeus.mode`` / user.fusion_pref):
  • simple — дешёвый стек: deepseek-v4-flash + gemini-3-pro + claude-haiku-4-5
             умный роутинг 1↔3 внутри стека
  • power  — сильный стек: claude-opus-4-8 + deepseek-v4-pro + gemini-3.1-pro
             умный роутинг 1↔3 внутри стека
  • custom — свои models[]; умный роутинг 1↔3

Auto stack/task: flash micro-classifier (JSON) → regex fallback if
confidence < 0.6 / timeout / parse error. Pure chitchat skips LLM.

Stack size never lands on 2 for auto routes: only 1 or 3.

Legacy aliases:
  • zeus/fusion-fast | zeus.mode=fast — force 1 (first of simple stack)
  • zeus/fusion-full | zeus.mode=full — force 3 (power stack)
  • zeus/fusion | zeus.mode=auto|power — power auto-route

Optional body:
  models: [...]
  zeus: {"mode": "simple"|"power"|"custom"|"fast"|"full"|"auto",
         "judge": "...", "thinking": bool}
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Any

from fastapi import HTTPException

from app import upstream
from app.catalog import get_model, public_catalog
from app.model_policy import model_allowed_for_user

from .brief import build_satellite_brief, satellite_messages_from_brief
from .types import BranchUsage, FusionResult

# Path enum (AD-15). Brownfield stack size stays fast|full internally.
_STACK_TO_PATH = {"fast": "FAST", "full": "FULL"}

# Closed routed_by values used by brownfield today (FR-28 / FR-37). Epic 2 adds policy_*.
_ROUTED_BY_CLOSED = frozenset(
    {
        "legacy_fast_alias",
        "legacy_full_alias",
        "forced_fast",
        "forced_full",
        "compat_1to3_auto",
        "compat_1to3_classify",
        "mode_ignored",
        # Keep accepting legacy bridge labels during migration
        "auto",
        "forced",
    }
)

_SCRUB_PLACEHOLDER = "[REDACTED]"
# Idempotent: placeholders and already-masked spans must not rematch.
_API_KEY_RE = re.compile(
    r"(?i)\b("
    r"sk-[A-Za-z0-9_-]{20,}|"
    r"AIza[0-9A-Za-z_-]{20,}|"
    r"ghp_[A-Za-z0-9]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"api[_-]?key[=:\s]+[A-Za-z0-9._\-]{16,}"
    r")\b"
)
_BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)([A-Za-z0-9._\-+/=]{16,})")
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN[^-]*PRIVATE KEY-----[\s\S]*?-----END[^-]*PRIVATE KEY-----",
    re.IGNORECASE,
)
_EMAIL_SECRET_RE = re.compile(r"(?i)\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Public id for clients: ``zeuscode``. Legacy ``zeus/fusion*`` kept as aliases.
PUBLIC_FUSION_MODEL_ID = "zeuscode"

FUSION_IDS = frozenset(
    {
        "zeuscode",
        "zeuscode-simple",
        "zeuscode-power",
        "zeuscode-custom",
        "zeus/fusion",
        "zeus-fusion",
        "fusion",
        "zeus/fusion-fast",
        "zeus/fusion-full",
        "zeus/fusion-simple",
        "zeus/fusion-power",
        "zeus/fusion-custom",
        "fusion-fast",
        "fusion-full",
        "fusion-simple",
        "fusion-power",
        "fusion-custom",
    }
)

# User-facing product modes (TG / cabinet / zeus.mode)
PRODUCT_MODES = frozenset({"simple", "power", "custom"})
DEFAULT_PRODUCT_MODE = "power"

# Простой — дешёвые модели
_SIMPLE_PANEL = (
    "deepseek-v4-flash",
    "gemini-3-pro",
    "claude-haiku-4-5",
)
_SIMPLE_JUDGE = "gemini-3-pro"

# Мощный — сильный стек
_POWER_PANEL = (
    "claude-opus-4-8",
    "deepseek-v4-pro",
    "gemini-3.1-pro",
)
_POWER_JUDGE = "gemini-3.1-pro"

# Legacy names used by resolve_panel fallbacks / force aliases
_FULL_PANEL = _POWER_PANEL
_FULL_JUDGE = _POWER_JUDGE
_FAST_PANEL = (_SIMPLE_PANEL[0],)

_MAX_PANEL = 3

# Serious intent → full power
_SERIOUS_RE = re.compile(
    r"(?i)"
    r"("
    r"напиш|сделай|реализ|почин|исправ|рефактор|debug|баг|ошибк|"
    r"код|функц|класс|api|endpoint|sql|миграц|тест|архитект|"
    r"сравн|проанализир|разбер|объясни подробно|план|дизайн|"
    r"landing|лендинг|сайт|компонент|css|html|react|python|"
    r"implement|fix|build|refactor|architecture|write code|"
    r"create|design|analyze|compare|review"
    r")"
)

# Small UI tweaks → stay on fast even if "сделай/поменяй" matched serious-ish
_TRIVIAL_RE = re.compile(
    r"(?i)"
    r"("
    r"поменяй\s+(цвет|размер|шрифт|отступ|padding|margin|border|background)|"
    r"сдвинь|переименуй|перекрась|"
    r"(сделай|поставь|покрась|измени)\s+.{0,48}"
    r"(красн|син|зелен|жёлт|желт|бел|чёрн|черн|оранж|серы|grey|gray|red|blue|green)|"
    r"change\s+(the\s+)?(color|size|font|padding|margin)|"
    r"rename\s+|make\s+it\s+(red|blue|green|bigger|smaller)"
    r")"
)

# Blocks trivial shortcut when the ask is really heavy
_HEAVY_RE = re.compile(
    r"(?i)"
    r"("
    r"рефактор|архитект|миграц|endpoint|sql|landing|лендинг|сайт|"
    r"refactor|architecture|implement|"
    r"напиш\w*\s+.{0,20}(код|функц|класс|api|сайт|лендинг)|"
    r"сделай\s+(сайт|лендинг|api|компонент|приложение|сервис)"
    r")"
)

_CHITCHAT_RE = re.compile(
    r"(?i)^\s*("
    r"привет|прив|салам|салам алейкум|ассалам|хай|хелло|hello|hi|yo|"
    r"здаров[аоуы]?|здоров[аоуы]?|добрый\s+(день|вечер|утро)|"
    r"как дела|что умеешь|кто ты|"
    r"спасибо|спс|ок|ага|лан|ку|йо|hey|thanks|thx|норм|нормально|пока|бай"
    r")[\s!.?]*$"
)


def is_fusion_model(model_id: str | None) -> bool:
    mid = (model_id or "").strip().lower()
    return mid in FUSION_IDS


def normalize_product_mode(raw: str | None) -> str | None:
    """Map aliases → simple|power|custom, or None if not a product mode."""
    m = (raw or "").strip().lower()
    if m in PRODUCT_MODES:
        return m
    if m in ("lite", "easy", "cheap"):
        return "simple"
    if m in ("auto", "smart", "мощный", "powerful"):
        return "power"
    if m in ("pick", "manual", "свой"):
        return "custom"
    return None


def product_mode_from_model_id(model_id: str | None) -> str | None:
    mid = (model_id or "").strip().lower()
    if mid in ("zeuscode-simple", "zeus/fusion-simple", "fusion-simple"):
        return "simple"
    if mid in ("zeuscode-power", "zeus/fusion-power", "fusion-power"):
        return "power"
    if mid in ("zeuscode-custom", "zeus/fusion-custom", "fusion-custom"):
        return "custom"
    if mid in ("zeuscode", "zeus/fusion", "fusion", "zeus-fusion"):
        return None  # defer to zeus.mode / user pref
    return None


def stack_to_path(stack: str | None) -> str:
    """Map brownfield stack size → Path enum (AD-15). Unknown → CASCADE-safe FULL? → FAST."""
    s = (stack or "").strip().lower()
    if s.startswith("fast"):
        return "FAST"
    if s.startswith("full"):
        return "FULL"
    if s in ("cascade", "race"):
        return s.upper()
    return _STACK_TO_PATH.get(s, "FAST")


def resolve_routing(
    model_id: str | None, zeus: dict[str, Any] | None, user_q: str
) -> tuple[str, str]:
    """Return (stack, routed_by) where stack is fast|full.

    ``routed_by`` uses FR-37 codes: ``legacy_*`` ≠ ``forced_*``; auto → ``compat_1to3_*``.
    """
    stack, routed_by, _prod = resolve_routing_ex(model_id, zeus, user_q)
    return stack, routed_by


def resolve_routing_ex(
    model_id: str | None, zeus: dict[str, Any] | None, user_q: str
) -> tuple[str, str, str]:
    """Return (stack fast|full, routed_by, product_mode simple|power|custom).

    Legacy model-id aliases never share codes with ``zeus.mode`` force (FR-37 / AD-15).
    """
    mid = (model_id or "").strip().lower()
    raw = ""
    if isinstance(zeus, dict):
        raw = str(zeus.get("mode") or "").strip().lower()

    # Legacy aliases (model id) — FR-37
    if mid in ("zeus/fusion-fast", "fusion-fast"):
        return "fast", "legacy_fast_alias", "simple"
    if mid in ("zeus/fusion-full", "fusion-full"):
        return "full", "legacy_full_alias", "power"

    # Explicit zeus.mode force — never conflated with legacy_*
    if raw == "fast":
        return "fast", "forced_fast", "simple"
    if raw == "full":
        return "full", "forced_full", "power"

    product = product_mode_from_model_id(mid) or normalize_product_mode(raw)
    if product is None:
        product = DEFAULT_PRODUCT_MODE

    # Historic brownfield auto 1↔3 (Epic 2 will replace with policy_*)
    if product == "custom":
        return classify_query(user_q), "compat_1to3_auto", "custom"
    if product == "simple":
        return classify_query(user_q), "compat_1to3_auto", "simple"
    return classify_query(user_q), "compat_1to3_auto", "power"


def resolve_mode(model_id: str | None, zeus: dict[str, Any] | None, user_q: str) -> str:
    """Return fast | full stack size."""
    stack, _, _ = resolve_routing_ex(model_id, zeus, user_q)
    return stack


def parse_fusion_models_json(raw: str | None) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text) if text.startswith("[") else [x.strip() for x in text.split(",")]
    except json.JSONDecodeError:
        data = [x.strip() for x in text.split(",") if x.strip()]
    out: list[str] = []
    for mid in data:
        mid = str(mid).strip()
        if mid and mid not in out and not is_fusion_model(mid):
            out.append(mid)
        if len(out) >= _MAX_PANEL:
            break
    return out


def apply_user_fusion_pref(
    user: Any | None,
    *,
    zeus: dict[str, Any] | None,
    models: list[str] | None,
) -> tuple[dict[str, Any], list[str] | None]:
    """Fill zeus.mode / models from user.fusion_pref when client omitted them."""
    zeus_out: dict[str, Any] = dict(zeus) if isinstance(zeus, dict) else {}
    panel = list(models) if models else None
    if panel is None and isinstance(zeus_out.get("models"), list):
        panel = [str(x) for x in zeus_out["models"] if str(x).strip()]

    has_mode = bool(str(zeus_out.get("mode") or "").strip())
    if not has_mode and user is not None:
        pref = normalize_product_mode(getattr(user, "fusion_pref", None)) or DEFAULT_PRODUCT_MODE
        zeus_out["mode"] = pref

    product = normalize_product_mode(str(zeus_out.get("mode") or "")) or DEFAULT_PRODUCT_MODE
    if product == "custom" and not panel and user is not None:
        panel = parse_fusion_models_json(getattr(user, "fusion_models", None))
        if panel:
            zeus_out["models"] = panel

    # EPIC4-HOOK: Effort + Kill-Switch prefs (zeus.* > prefs > default). Product modes untouched.
    from app.fusion.metrics import apply_effort_kill_prefs, kill_switch_active

    zeus_out = apply_effort_kill_prefs(user, zeus_out)
    # Kill-Switch clamps Path to FAST (AD-9); does not rewrite stored product pref.
    # Global + account kill both surface as zeus.kill_switch so policy routed_by=kill_switch.
    if kill_switch_active(zeus_out):
        zeus_out["kill_switch"] = True
        zeus_out["mode"] = "fast"
        zeus_out["kill_forced"] = True
    return zeus_out, panel


def classify_query(user_q: str) -> str:
    """Heuristic: chitchat/short/trivial UI → fast; serious/long → full."""
    q = (user_q or "").strip()
    if not q:
        return "fast"
    if _CHITCHAT_RE.match(q):
        return "fast"
    # Trivial UI tweak wins over broad "сделай/поменяй" unless ask is heavy
    if _TRIVIAL_RE.search(q) and not _HEAVY_RE.search(q) and len(q) < 160:
        return "fast"
    if len(q) >= 180 or _SERIOUS_RE.search(q):
        return "full"
    if len(q) <= 60:
        return "fast"
    return "fast"  # bias to speed; user can force full


# Task kinds → who should be "голова" (leader) inside a panel
_TASK_ARCH_RE = re.compile(
    r"(?i)(архитект|рефактор|миграц|спроектир|design system|ddd|микросервис|"
    r"architecture|refactor|migrate|redesign)"
)
_TASK_UI_RE = re.compile(
    r"(?i)(css|html|ui|ux|кнопк|цвет|стиль|вёрстк|верстк|layout|tailwind|"
    r"компонент|анимац|pixel|figma|лендинг|landing|hero)"
)
_TASK_REVIEW_RE = re.compile(
    r"(?i)(ревью|review|проверь код|найди баг|audit|security|уязвим)"
)
_TASK_TEST_RE = re.compile(
    r"(?i)(тест|pytest|unit test|e2e|покрой тест|coverage)"
)
_TASK_CODE_RE = re.compile(
    r"(?i)(код|функц|класс|api|endpoint|sql|python|react|typescript|баг|ошибк|"
    r"implement|fix|debug|напиш)"
)

# Base strength (higher = stronger generalist). Used when picking голова.
_MODEL_STRENGTH: dict[str, int] = {
    "claude-opus-4-8": 100,
    "claude-opus-4-7": 98,
    "claude-opus-4-6": 96,
    "claude-opus-4-5": 94,
    "gemini-3.1-pro": 93,
    "gemini-3-pro": 88,
    "claude-sonnet-5": 87,
    "claude-sonnet-4-6": 86,
    "claude-sonnet-4-5": 85,
    "deepseek-v4-pro": 84,
    "gpt-5.5": 83,
    "gpt-5.4": 82,
    "gemini-3.5-flash": 78,
    "gemini-2.5-pro": 77,
    "claude-haiku-4-5": 72,
    "deepseek-v4-flash": 70,
    "deepseek-chat": 68,
    "gemini-2.5-flash": 66,
    "gemini-3-flash": 65,
}

# Extra score by task affinity (added to strength when model is in panel)
_TASK_BONUS: dict[str, dict[str, int]] = {
    "architecture": {
        "claude-opus-4-8": 25,
        "claude-opus-4-7": 22,
        "gemini-3.1-pro": 18,
        "gemini-3-pro": 12,
        "deepseek-v4-pro": 8,
    },
    "code": {
        "claude-opus-4-8": 20,
        "gemini-3.1-pro": 16,
        "gemini-3-pro": 14,
        "deepseek-v4-pro": 12,
        "claude-haiku-4-5": 6,
        "deepseek-v4-flash": 4,
    },
    "ui": {
        "claude-haiku-4-5": 18,
        "gemini-3-pro": 14,
        "gemini-3.1-pro": 12,
        "deepseek-v4-flash": 10,
        "claude-opus-4-8": 6,
    },
    "review": {
        "gemini-3.1-pro": 20,
        "claude-opus-4-8": 18,
        "gemini-3-pro": 14,
        "deepseek-v4-pro": 8,
    },
    "tests": {
        "deepseek-v4-pro": 16,
        "gemini-3.1-pro": 14,
        "claude-opus-4-8": 12,
        "gemini-3-pro": 10,
        "deepseek-v4-flash": 8,
    },
    "light": {
        "deepseek-v4-flash": 30,
        "deepseek-chat": 22,
        "deepseek-v4-pro": 18,
        "claude-haiku-4-5": 16,
        "gemini-3-flash": 14,
        "gemini-2.5-flash": 12,
    },
}


def classify_task(user_q: str) -> str:
    """Return task kind: light | ui | tests | review | architecture | code | general."""
    q = (user_q or "").strip()
    if not q or _CHITCHAT_RE.match(q):
        return "light"
    if _TRIVIAL_RE.search(q) and not _HEAVY_RE.search(q) and len(q) < 160:
        return "light"
    if _TASK_ARCH_RE.search(q):
        return "architecture"
    if _TASK_REVIEW_RE.search(q):
        return "review"
    if _TASK_TEST_RE.search(q):
        return "tests"
    if _TASK_UI_RE.search(q) and not _TASK_ARCH_RE.search(q):
        return "ui"
    if _TASK_CODE_RE.search(q) or len(q) >= 120:
        return "code"
    if classify_query(q) == "fast":
        return "light"
    return "general"


# ——— Flash micro-classifier (LLM) + regex fallback ———
_TASK_KINDS = frozenset(
    {"light", "ui", "tests", "review", "architecture", "code", "general"}
)
_CLASSIFIER_MODELS = ("deepseek-v4-flash", "gemini-2.5-flash")
_CLASSIFIER_MODEL = _CLASSIFIER_MODELS[0]
_CLASSIFIER_TIMEOUT_S = 2.4
_CLASSIFIER_MIN_CONF = 0.6
_CODE_BLOCK_RE = re.compile(r"```|^\s{4}\S", re.MULTILINE)
_ERROR_TRACE_RE = re.compile(
    r"(?i)(traceback|exception|error:|typeerror|referenceerror|syntaxerror|"
    r"failed|ENOENT|undefined is not|cannot find module|ModuleNotFoundError)"
)
_FOLLOWUP_RE = re.compile(
    r"(?i)^\s*("
    r"поправь|исправь|переделай|доделай|продолжи|ещё|еще|теперь|"
    r"то же|тоже|и для|а теперь|сделай так|fix this|fix it|"
    r"same for|now do|update it|retry|again"
    r").{0,120}$"
)

_CLASSIFIER_SYSTEM = """Ты роутер Zeus Fusion. Ответ — ТОЛЬКО один JSON-объект, без markdown и текста вокруг.
Схема: {"stack":"fast"|"full","task":"light"|"ui"|"tests"|"review"|"architecture"|"code"|"general","confidence":0.0-1.0}

stack=fast → одна быстрая модель (привет, мелкая правка UI/текста без кода, короткое уточнение без работы).
stack=full → панель из 3 моделей (написать/починить код, архитектура, лендинг, ревью, тесты, серьёзная правка, follow-up «поправь это» после кода/ошибки).

Правила:
1) Смотри сигналы: has_code_blocks, has_error_trace, short_followup, last_assistant, context_chars.
2) short_followup=true + (код или ошибка в контексте) → почти всегда full + task=code (или review если про баг/security).
3) «поменяй цвет кнопки» без кода/ошибки → fast + ui/light.
4) Длинный контекст (>4000 chars) и рабочий запрос → full, не fast.
5) confidence: 0.9+ если очевидно; 0.5–0.7 если двусмысленно; не завышай.

Примеры:
{"stack":"fast","task":"light","confidence":0.95}  ← привет
{"stack":"fast","task":"ui","confidence":0.85}     ← поменяй цвет кнопки
{"stack":"full","task":"code","confidence":0.9}    ← поправь это (после кода)
{"stack":"full","task":"architecture","confidence":0.92} ← отрефакторь API
{"stack":"full","task":"ui","confidence":0.88}     ← сделай лендинг для сто
"""


def classifier_features(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Compact signals for the micro-classifier (no full Cursor dump)."""
    user_texts: list[str] = []
    last_assistant = ""
    total_chars = 0
    has_code = False
    has_error = False
    for m in messages:
        text = _plain_text_local(m.get("content")).strip()
        total_chars += len(text)
        if text and _CODE_BLOCK_RE.search(text):
            has_code = True
        if text and _ERROR_TRACE_RE.search(text):
            has_error = True
        role = m.get("role")
        if role == "user" and text:
            user_texts.append(text)
        elif role == "assistant" and text:
            last_assistant = text
    last_users = user_texts[-2:] if user_texts else [""]
    last_user = last_users[-1] if last_users else ""
    short_followup = bool(
        last_user
        and len(last_user) <= 160
        and (_FOLLOWUP_RE.match(last_user) or len(last_user.split()) <= 6)
        and (has_code or has_error or len(last_assistant) > 80)
    )
    return {
        "n_messages": len(messages),
        "n_user": len(user_texts),
        "context_chars": total_chars,
        "has_code_blocks": has_code,
        "has_error_trace": has_error,
        "short_followup": short_followup,
        "last_user": last_user,
        "prev_user": last_users[-2] if len(last_users) > 1 else "",
        "last_assistant": last_assistant,
    }


def apply_classifier_guardrails(
    decision: dict[str, Any], feat: dict[str, Any]
) -> dict[str, Any]:
    """Hard overrides when signals are clearer than the model/regex."""
    out = dict(decision)
    stack = str(out.get("stack") or "fast")
    task = str(out.get("task") or "general")
    reasons: list[str] = list(out.get("guardrails") or [])

    short_fu = bool(feat.get("short_followup"))
    has_code = bool(feat.get("has_code_blocks"))
    has_err = bool(feat.get("has_error_trace"))
    ctx = int(feat.get("context_chars") or 0)
    last = (feat.get("last_user") or "").strip()

    # Follow-up after code/error must not stay on fast single model
    if short_fu and (has_code or has_err) and stack == "fast":
        stack = "full"
        if task in ("light", "general", "ui"):
            task = "review" if has_err else "code"
        reasons.append("followup+context→full")

    # Large working context + non-chitchat → full
    if (
        ctx >= 4000
        and stack == "fast"
        and last
        and not _CHITCHAT_RE.match(last)
        and not (_TRIVIAL_RE.search(last) and not _HEAVY_RE.search(last))
    ):
        stack = "full"
        if task == "light":
            task = "code" if has_code else "general"
        reasons.append("large-context→full")

    # Trivial UI without code/error stays fast
    if (
        last
        and _TRIVIAL_RE.search(last)
        and not _HEAVY_RE.search(last)
        and not has_code
        and not has_err
        and len(last) < 160
    ):
        stack = "fast"
        if task not in ("light", "ui"):
            task = "ui"
        reasons.append("trivial-ui→fast")

    out["stack"] = stack
    out["task"] = task
    if reasons:
        out["guardrails"] = reasons
    return out


def _parse_classifier_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    # Strip ```json fences if model ignored instructions
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    stack = str(data.get("stack") or "").strip().lower()
    if stack not in ("fast", "full"):
        return None
    task = str(data.get("task") or "").strip().lower()
    if task not in _TASK_KINDS:
        # soft map common aliases
        aliases = {
            "chitchat": "light",
            "chat": "light",
            "frontend": "ui",
            "css": "ui",
            "refactor": "architecture",
            "arch": "architecture",
            "bug": "code",
            "coding": "code",
            "test": "tests",
            "security": "review",
        }
        task = aliases.get(task, "")
        if task not in _TASK_KINDS:
            return None
    try:
        conf = float(data.get("confidence"))
    except (TypeError, ValueError):
        return None
    conf = max(0.0, min(1.0, conf))
    return {"stack": stack, "task": task, "confidence": conf}


def regex_classify(user_q: str) -> dict[str, Any]:
    """Deterministic fallback: stack + task + confidence=1.0 source=regex."""
    stack = classify_query(user_q)
    task = classify_task(user_q)
    if stack == "fast" and task not in ("light", "ui"):
        task = "light"
    return {
        "stack": stack,
        "task": task,
        "confidence": 1.0,
        "source": "regex",
        "model": None,
        "latency_s": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }


def _classifier_user_prompt(feat: dict[str, Any]) -> str:
    prev = (feat.get("prev_user") or "")[:400]
    last = (feat.get("last_user") or "")[:700]
    asst = (feat.get("last_assistant") or "")[:700]
    if len(feat.get("last_assistant") or "") > 700:
        # Keep head+tail of assistant — errors often at the end
        raw_a = feat["last_assistant"]
        asst = raw_a[:400] + "\n…\n" + raw_a[-280:]
    lines = [
        (
            f"n_messages={feat.get('n_messages')} context_chars={feat.get('context_chars')} "
            f"has_code_blocks={bool(feat.get('has_code_blocks'))} "
            f"has_error_trace={bool(feat.get('has_error_trace'))} "
            f"short_followup={bool(feat.get('short_followup'))}"
        ),
    ]
    if prev:
        lines.append(f"prev_user:\n{prev}")
    if asst:
        lines.append(f"last_assistant:\n{asst}")
    lines.append(f"last_user:\n{last}")
    return "\n\n".join(lines)


def _merge_lowconf(
    fallback: dict[str, Any], parsed: dict[str, Any], feat: dict[str, Any]
) -> dict[str, Any]:
    """When LLM confidence is low: keep regex stack unless signals push full."""
    out = dict(fallback)
    # Prefer LLM task label if it looks specific
    llm_task = parsed.get("task")
    if llm_task in _TASK_KINDS and llm_task not in ("light", "general"):
        out["task"] = llm_task
    if parsed.get("stack") == "full" and (
        feat.get("has_code_blocks")
        or feat.get("has_error_trace")
        or feat.get("short_followup")
        or int(feat.get("context_chars") or 0) >= 2500
    ):
        out["stack"] = "full"
    out["llm_stack"] = parsed.get("stack")
    out["llm_task"] = parsed.get("task")
    out["llm_confidence"] = parsed.get("confidence")
    return out


async def _classifier_llm_call(
    clf_messages: list[dict[str, Any]], *, timeout_s: float
) -> tuple[dict[str, Any] | None, str, int, int, str]:
    """Try primary then fallback model. Returns (parsed|None, model, pt, ct, raw_err)."""
    last_err = ""
    for mid in _CLASSIFIER_MODELS:
        try:
            data = await asyncio.wait_for(
                upstream.chat_completions(
                    model=mid,
                    messages=clf_messages,
                    stream=False,
                    max_tokens=80,
                    temperature=0.0,
                ),
                timeout=timeout_s,
            )
            raw = upstream.extract_text(data)
            pt, ct = upstream.extract_usage(data)
            parsed = _parse_classifier_json(raw)
            if parsed:
                return parsed, mid, pt, ct, ""
            last_err = "parse"
            # parse fail → try next model
        except asyncio.TimeoutError:
            last_err = "timeout"
            continue
        except Exception as e:  # noqa: BLE001
            last_err = str(e)[:120]
            continue
    return None, _CLASSIFIER_MODELS[0], 0, 0, last_err


async def classify_smart(
    messages: list[dict[str, Any]],
    *,
    user_q: str | None = None,
    force_regex: bool = False,
) -> dict[str, Any]:
    """LLM micro-router + guardrails; regex fallback on fail/low-conf.

    Obvious chitchat skips the LLM (instant, free).
    """
    q = (user_q if user_q is not None else _text_of(messages)).strip()
    feat = classifier_features(messages)
    fallback = apply_classifier_guardrails(regex_classify(q), feat)

    if force_regex:
        out = dict(fallback)
        out["source"] = "regex"
        return out

    # Instant path — no latency tax on greetings (no code/error context)
    if (not q or _CHITCHAT_RE.match(q)) and not feat.get("has_code_blocks"):
        out = dict(fallback)
        out["source"] = "regex-chitchat"
        return out

    prompt = _classifier_user_prompt(feat)
    clf_messages = [
        {"role": "system", "content": _CLASSIFIER_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    t0 = time.perf_counter()
    # Split budget across up to 2 models
    per_model_timeout = _CLASSIFIER_TIMEOUT_S / max(1, len(_CLASSIFIER_MODELS))
    parsed, used_model, pt, ct, err = await _classifier_llm_call(
        clf_messages, timeout_s=per_model_timeout
    )
    lat = round(time.perf_counter() - t0, 3)

    if not parsed:
        out = dict(fallback)
        out.update(
            {
                "source": f"regex-{err or 'error'}",
                "model": used_model,
                "latency_s": lat,
                "prompt_tokens": pt,
                "completion_tokens": ct,
                # FR-17 / Story 2.1: LLM classify fail → policy CASCADE fallback
                "classify_failed": True,
                "failed": True,
            }
        )
        return apply_classifier_guardrails(out, feat)

    if float(parsed["confidence"]) < _CLASSIFIER_MIN_CONF:
        out = _merge_lowconf(fallback, parsed, feat)
        out.update(
            {
                "source": "hybrid-lowconf",
                "model": used_model,
                "latency_s": lat,
                "prompt_tokens": pt,
                "completion_tokens": ct,
            }
        )
        return apply_classifier_guardrails(out, feat)

    out = {
        "stack": parsed["stack"],
        "task": parsed["task"],
        "confidence": parsed["confidence"],
        "source": "llm",
        "model": used_model,
        "latency_s": lat,
        "prompt_tokens": pt,
        "completion_tokens": ct,
    }
    return apply_classifier_guardrails(out, feat)


# Long-context affinity when prompt exceeds overflow budget (AD-16).
_OVERFLOW_BONUS: dict[str, int] = {
    "gemini-3.1-pro": 40,
    "gemini-3-pro": 35,
    "gemini-2.5-pro": 30,
    "gemini-2.5-flash": 18,
    "claude-opus-4-8": 22,
    "claude-opus-4-7": 20,
    "claude-sonnet-5": 12,
    "deepseek-v4-pro": 10,
    "gpt-5.5": 10,
}


def pick_leader(
    panel: list[str],
    task_kind: str,
    *,
    sticky_leader: str | None = None,
    unhealthy: set[str] | frozenset[str] | None = None,
    context_chars: int | None = None,
    overflow_chars: int | None = None,
) -> str:
    """AD-16: sticky hint → health filter → overflow/long-context → strength."""
    if not panel:
        raise HTTPException(400, "ZeusCode: пустая панель")
    if len(panel) == 1:
        return panel[0]

    dead = set(unhealthy or ())
    ready = [m for m in panel if m not in dead] or list(panel)

    if overflow_chars is None:
        try:
            from app.fusion.metrics import runtime_budgets_from_settings

            overflow_chars = runtime_budgets_from_settings().overflow_context_chars
        except Exception:  # noqa: BLE001
            overflow_chars = 120_000
    overflow = int(context_chars or 0) >= int(overflow_chars or 120_000)

    sticky = (sticky_leader or "").strip()
    # Sticky wins when healthy and context is within budget (Path never sticky).
    if sticky and sticky in ready and not overflow:
        return sticky

    kind = task_kind if task_kind in _TASK_BONUS else "general"
    bonus_map = _TASK_BONUS.get(kind) or {}
    best = ready[0]
    best_score = -10**9
    for mid in ready:
        score = float(int(_MODEL_STRENGTH.get(mid, 50)))
        score += int(bonus_map.get(mid, 0))
        if overflow:
            score += int(_OVERFLOW_BONUS.get(mid, 0))
        # slight preference for earlier exclusive order as tie-break
        try:
            score -= panel.index(mid) * 0.01
        except ValueError:
            pass
        if score > best_score:
            best_score = score
            best = mid
    return best


def order_panel_leader_first(panel: list[str], leader: str) -> list[str]:
    if leader not in panel:
        return list(panel)
    rest = [m for m in panel if m != leader]
    return [leader, *rest]


def _satellite_messages(
    messages: list[dict[str, Any]], user_q: str
) -> list[dict[str, Any]]:
    """Compressed Brief for satellites — last_assistant + errors + goal only (FR-22)."""
    brief = build_satellite_brief(messages, user_q=user_q)
    return satellite_messages_from_brief(brief)


def _judge_user_brief(user_q: str, max_len: int = 4000) -> str:
    q = (user_q or "").strip()
    if len(q) <= max_len:
        return q
    return q[: max_len - 40] + "\n…[обрезано для синтеза]…"


def _text_of(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user" and m.get("content") is not None:
            return _plain_text_local(m.get("content")).strip()
    return ""


def _plain_text_local(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                parts.append(str(p.get("text") or p.get("content") or ""))
        return "\n".join(x for x in parts if x)
    if content is None:
        return ""
    return str(content)


def scrub_secrets(text: str) -> str:
    """Mask MVP secret patterns (FR-21). Idempotent w.r.t. ``[REDACTED]``."""
    if not text:
        return text
    out = _PRIVATE_KEY_RE.sub(_SCRUB_PLACEHOLDER, text)
    out = _BEARER_RE.sub(rf"\1{_SCRUB_PLACEHOLDER}", out)
    out = _API_KEY_RE.sub(_SCRUB_PLACEHOLDER, out)
    out = _EMAIL_SECRET_RE.sub(_SCRUB_PLACEHOLDER, out)
    return out


def scrub_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Scrub string contents. Safe to call only at Edge→Policy (AD-17)."""
    out: list[dict[str, Any]] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = m.get("role") or "user"
        content = m.get("content")
        if isinstance(content, str):
            new_c: Any = scrub_secrets(content)
        elif isinstance(content, list):
            parts: list[Any] = []
            for p in content:
                if isinstance(p, str):
                    parts.append(scrub_secrets(p))
                elif isinstance(p, dict):
                    q = dict(p)
                    for k in ("text", "content"):
                        if isinstance(q.get(k), str):
                            q[k] = scrub_secrets(q[k])
                    parts.append(q)
                else:
                    parts.append(p)
            new_c = parts
        else:
            new_c = content
        out.append({"role": role, "content": new_c})
    return out


def sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten multimodal parts and strip Cursor Agent tool protocol.

    Cursor Agent sends role=tool / tool_calls. DeepSeek and many Kie paths
    reject tool turns (missing tool_call_id after a naive flatten) and the
    stream ends as an SSE error that Cursor shows as a blank reply.
    Convert the transcript to plain system/user/assistant text.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        role = (m.get("role") or "user").strip().lower()
        text = _plain_text_local(m.get("content")).strip()

        if role == "tool":
            if text:
                out.append({"role": "user", "content": f"[результат инструмента]\n{text[:4000]}"})
            continue

        if role not in ("system", "user", "assistant"):
            continue

        if role == "assistant" and not text:
            tcs = m.get("tool_calls") or []
            names: list[str] = []
            for tc in tcs:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                name = (fn or {}).get("name") or tc.get("name")
                if name:
                    names.append(str(name))
            if names:
                text = f"[вызов: {', '.join(names[:8])}]"
            else:
                continue

        if not text and role != "user":
            continue
        out.append({"role": role, "content": text or ""})

    # Drop leading empties; keep last ~30 turns so Agent history stays cheap
    out = [m for m in out if m.get("content") or m.get("role") == "user"]
    if len(out) > 30:
        # Always keep a leading system message if present
        if out[0].get("role") == "system":
            out = [out[0], *out[-29:]]
        else:
            out = out[-30:]
    return out or [{"role": "user", "content": "Привет"}]


def prepare_messages_for_policy(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Edge→Policy boundary: sanitize then scrub **once** (AD-17).

    Execute / Brief must use this output and must not re-scrub inconsistently.
    """
    return scrub_messages(sanitize_messages(messages))


def _ready_chat_ids(user: Any | None) -> list[str]:
    rows = public_catalog()
    out: list[str] = []
    for r in rows:
        mid = r.get("id") or ""
        if not r.get("ready"):
            continue
        if (r.get("modality") or "chat") != "chat":
            continue
        if is_fusion_model(mid) or str(mid).startswith("studio-") or mid in (
            "ultra-mode",
            "ultra",
            "onestack-ultra",
        ):
            continue
        meta = get_model(mid) or {}
        if meta.get("adapter") in (None, "pending", "ultra", "fusion"):
            continue
        if user is not None and not model_allowed_for_user(user, mid):
            continue
        out.append(mid)
    return out


def _exclusive_for_product(product_mode: str) -> tuple[list[str], str]:
    """Return (panel, default_judge) for simple/power stacks."""
    if product_mode == "simple":
        return list(_SIMPLE_PANEL), _SIMPLE_JUDGE
    return list(_POWER_PANEL), _POWER_JUDGE


def resolve_panel(
    *,
    user: Any | None,
    models: list[str] | None,
    judge: str | None = None,
    mode: str = "full",
    product_mode: str = "power",
) -> tuple[list[str], str | None]:
    """Return (panel_models, judge_or_None). Judge None = race/fast path."""
    ready = _ready_chat_ids(user)
    ready_set = set(ready)

    prod = product_mode if product_mode in PRODUCT_MODES else DEFAULT_PRODUCT_MODE
    exclusive, default_judge = _exclusive_for_product(prod)
    # Legacy force-fast without product context → first of simple stack
    if mode == "fast" and prod == "power" and not models:
        # When caller only asked fast stack size on power/default, still use
        # product exclusive (first model) — product_mode should already be set.
        pass

    panel: list[str] = []
    # Custom models only if caller explicitly passed them — still capped to 3.
    for mid in models or []:
        mid = str(mid).strip()
        if not mid or is_fusion_model(mid):
            continue
        if mid not in ready_set:
            raise HTTPException(400, f"ZeusCode: модель «{mid}» недоступна или не подключена")
        if user is not None and not model_allowed_for_user(user, mid):
            raise HTTPException(403, f"ZeusCode: на аккаунте нет доступа к «{mid}»")
        if mid not in panel:
            panel.append(mid)
        if len(panel) >= _MAX_PANEL:
            break

    if not panel:
        # AD-21 / FR2: custom never invents out-of-stack models (no silent power fill).
        if prod == "custom":
            raise HTTPException(
                400,
                "ZeusCode: custom mode requires models[] (1–3) from your stack",
            )
        missing = [m for m in exclusive if m not in ready_set]
        if missing:
            raise HTTPException(
                400,
                f"Fusion: эксклюзивный стек недоступен, нет: {', '.join(missing)}",
            )
        for mid in exclusive:
            if user is not None and not model_allowed_for_user(user, mid):
                raise HTTPException(403, f"Fusion: нет доступа к «{mid}»")
            panel.append(mid)

    if not panel:
        raise HTTPException(400, "Fusion: нет доступных моделей для панели")

    panel = panel[:_MAX_PANEL]

    # Fast: return full panel so caller can pick_leader; judge stays None.
    if mode == "fast":
        return panel, None

    j = (judge or "").strip() or default_judge
    if j not in ready_set:
        # fallback: first panel model as judge if default missing
        if default_judge in panel:
            j = default_judge
        elif panel:
            j = panel[0]
        else:
            raise HTTPException(400, f"Fusion: judge «{j}» недоступен")
    if j not in ready_set:
        raise HTTPException(400, f"Fusion: judge «{j}» недоступен")
    if user is not None and not model_allowed_for_user(user, j):
        raise HTTPException(403, f"Fusion: нет доступа к judge «{j}»")

    return panel, j


_JUDGE_SYSTEM = """Ты judge в Zeus Fusion.
Тебе дали ответы панели моделей на один запрос.

Сделай сильный финальный ответ пользователю (на русском, если вопрос на русском).
Не устраивай длинный мета-разбор — сразу полезный ответ.
Если все ответы слабые — собери лучшее из них.
Формат: только финальный ответ пользователю, без заголовка «Анализ».

Если сдаёшь HTML сайт/лендинг/приложение:
1) Вставь перед </body> еле прозрачный бейдж:
<a class="zeus-badge" href="https://zeuscode.ru" target="_blank" rel="noopener">Сделано на ZeusCode</a>
(+ CSS position:fixed; right/bottom; color:rgba(120,120,120,.42)).
2) Полный документ в блоке ```html — шлюз сам опубликует на https://zeuscode.ru/go/…
"""


async def _panel_one(
    model: str,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        data = await upstream.chat_completions(model=model, messages=messages, stream=False)
        text = upstream.extract_text(data)
        pt, ct = upstream.extract_usage(data)
        return {
            "model": model,
            "ok": True,
            "text": text,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "latency_s": round(time.perf_counter() - t0, 3),
            "error": None,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "model": model,
            "ok": False,
            "text": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_s": round(time.perf_counter() - t0, 3),
            "error": str(e)[:400],
        }


async def _race_first(
    panel: list[str],
    messages: list[dict[str, Any]],
    *,
    timeout_s: float | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Start panel in parallel; return first OK non-empty answer. Cancel the rest.

    FAST/kill path: longer timeout + sequential failover so a single flaky
    cheap model does not hard-fail the request (502).
    """
    try:
        from app.fusion.metrics import runtime_budgets_from_settings

        budgets = runtime_budgets_from_settings()
        default_timeout = min(90.0, max(45.0, float(budgets.global_timeout_s)))
    except Exception:  # noqa: BLE001
        default_timeout = 60.0
    timeout_s = float(timeout_s) if timeout_s is not None else default_timeout

    # Prefer sequential for 1-model FAST (clear errors); parallel only for 2+.
    ordered = [m for m in panel if str(m).strip()]
    if not ordered:
        raise HTTPException(400, "Fusion fast: пустая панель")

    results: list[dict[str, Any]] = []
    winner: dict[str, Any] | None = None

    if len(ordered) == 1:
        mid = ordered[0]
        # One shot + one retry on transient upstream errors
        for attempt in range(2):
            try:
                r = await asyncio.wait_for(_panel_one(mid, messages), timeout=timeout_s)
            except asyncio.TimeoutError:
                r = {
                    "model": mid,
                    "ok": False,
                    "text": "",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "latency_s": timeout_s,
                    "error": f"timeout>{timeout_s:.0f}s",
                }
            results.append(r)
            if r.get("ok") and (r.get("text") or "").strip():
                winner = r
                break
            err = str(r.get("error") or "").lower()
            transient = any(
                x in err for x in ("rate limit", "429", "timeout", "cancelled", "503", "502")
            )
            if not transient:
                break
            await asyncio.sleep(0.35 * (attempt + 1))
        # Failover across simple stack if primary still dead
        if winner is None:
            for alt in _SIMPLE_PANEL:
                if alt == mid:
                    continue
                try:
                    r = await asyncio.wait_for(_panel_one(alt, messages), timeout=timeout_s)
                except asyncio.TimeoutError:
                    r = {
                        "model": alt,
                        "ok": False,
                        "text": "",
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "latency_s": timeout_s,
                        "error": f"timeout>{timeout_s:.0f}s",
                    }
                results.append(r)
                if r.get("ok") and (r.get("text") or "").strip():
                    winner = r
                    break
    else:
        tasks = {asyncio.create_task(_panel_one(m, messages), name=m): m for m in ordered}
        deadline = time.perf_counter() + timeout_s
        try:
            while tasks and winner is None:
                left = max(0.05, deadline - time.perf_counter())
                done, _pending = await asyncio.wait(
                    tasks.keys(),
                    timeout=left,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    break
                for t in done:
                    mid = tasks.pop(t)
                    try:
                        r = t.result()
                    except Exception as e:  # noqa: BLE001
                        r = {
                            "model": mid,
                            "ok": False,
                            "text": "",
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "latency_s": 0,
                            "error": str(e)[:400],
                        }
                    results.append(r)
                    if r.get("ok") and (r.get("text") or "").strip():
                        winner = r
                        break
        finally:
            for t in list(tasks):
                t.cancel()
            if tasks:
                await asyncio.gather(*tasks.keys(), return_exceptions=True)

        # Cancelled-before-tokens branches (FR-19)
        seen = {r.get("model") for r in results}
        for mid in ordered:
            if mid not in seen:
                results.append(
                    {
                        "model": mid,
                        "ok": False,
                        "text": "",
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "latency_s": 0,
                        "error": "cancelled",
                        "billable_state": "cancelled_no_tokens",
                    }
                )

    if winner is None:
        ok = [r for r in results if r.get("ok") and (r.get("text") or "").strip()]
        if ok:
            winner = ok[0]
        else:
            errors = (
                "; ".join(f"{r['model']}: {r.get('error') or 'empty'}" for r in results)
                or "timeout"
            )
            raise HTTPException(502, f"Fusion fast: нет ответа ({errors})")

    return winner, results


def infer_billable_state(agent: dict[str, Any]) -> str:
    """Map agent/branch row → FR-19 billable state."""
    explicit = agent.get("billable_state")
    if explicit in (
        "completed",
        "partial_stream",
        "cancelled_no_tokens",
        "cancelled_with_usage",
    ):
        return str(explicit)
    pt = int(agent.get("prompt_tokens") or 0)
    ct = int(agent.get("completion_tokens") or 0)
    ok = bool(agent.get("ok"))
    if agent.get("partial_stream") or agent.get("partial"):
        return "partial_stream"
    if not ok and pt == 0 and ct == 0:
        return "cancelled_no_tokens"
    if not ok and (pt > 0 or ct > 0):
        return "cancelled_with_usage"
    return "completed"


def _complexity_for_stack(stack: str, task_kind: str | None) -> str:
    if str(stack).startswith("fast"):
        return "light"
    if task_kind in ("architecture", "review"):
        return "heavy"
    return "med"


def _phase_for_task(task_kind: str | None, classifier: dict[str, Any] | None) -> str:
    if isinstance(classifier, dict):
        for key in ("classify_phase", "phase"):
            val = classifier.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip().lower()
    tk = (task_kind or "general").lower()
    if tk in ("light", "ui"):
        return "chat"
    if tk in ("architecture", "review"):
        return "debug" if tk == "review" else "plan"
    return "implement"


def agents_to_branches(
    agents: list[dict[str, Any]],
    *,
    classifier: dict[str, Any] | None = None,
) -> list[BranchUsage]:
    """Build FusionResult.branches from onestack agents (+ optional classifier call)."""
    branches: list[BranchUsage] = []
    if isinstance(classifier, dict):
        cpt = int(classifier.get("prompt_tokens") or 0)
        cct = int(classifier.get("completion_tokens") or 0)
        if cpt or cct or classifier.get("source") == "llm":
            branches.append(
                BranchUsage(
                    model_id=str(classifier.get("model") or "classifier"),
                    billable_state="completed" if (cpt or cct) else "cancelled_no_tokens",
                    prompt_tokens=cpt,
                    completion_tokens=cct,
                    role="classifier",
                    meta={"source": classifier.get("source")},
                )
            )
    for a in agents:
        role = str(a.get("role") or "agent")
        if role == "panel":
            role = "agent"
        branches.append(
            BranchUsage(
                model_id=str(a.get("model") or ""),
                billable_state=infer_billable_state(a),  # type: ignore[arg-type]
                prompt_tokens=int(a.get("prompt_tokens") or 0),
                completion_tokens=int(a.get("completion_tokens") or 0),
                role=role,
                meta={
                    k: a.get(k)
                    for k in ("label", "title", "ok", "winner", "leader", "error", "latency_s")
                    if k in a
                },
            )
        )
    return branches


def build_fusion_result(
    *,
    answer: str,
    stack_mode: str,
    routed_by: str,
    leader: str | None,
    agents: list[dict[str, Any]],
    task_kind: str | None = None,
    classifier: dict[str, Any] | None = None,
    escalate_from: str | None = None,
    policy_path: str | None = None,
    serving_path: str | None = None,
    trace_id: str | None = None,
    completion: dict[str, Any] | None = None,
    onestack: dict[str, Any] | None = None,
) -> FusionResult:
    """Execute→Bill handoff (AD-14).

    ``serving_path`` is the AD-15 Path enum. ``stack_mode`` is Edge stack size only
    (fast|full) used for complexity heuristics when Path is FAST/FULL-mapped.
    """
    path = (serving_path or "").strip().upper() or stack_to_path(stack_mode)
    if path not in ("FAST", "CASCADE", "RACE", "FULL"):
        path = stack_to_path(stack_mode)
    pol = (policy_path or path).strip().upper() if policy_path else path
    if pol not in ("FAST", "CASCADE", "RACE", "FULL"):
        pol = path
    tid = trace_id or f"fus-{uuid.uuid4().hex[:16]}"
    rb = routed_by if routed_by in _ROUTED_BY_CLOSED or routed_by.startswith(
        ("policy_", "mor_", "cascade_", "race_", "compat_1to3_")
    ) else "compat_1to3_auto"
    # Normalize legacy bridge labels
    if rb == "auto":
        rb = "compat_1to3_auto"
    if rb == "forced":
        rb = "forced_fast" if path == "FAST" else "forced_full"
    return FusionResult(
        path=path,
        policy_path=pol,
        routed_by=rb,
        phase=_phase_for_task(task_kind, classifier),
        complexity=_complexity_for_stack(stack_mode, task_kind),
        leader=leader,
        branches=agents_to_branches(agents, classifier=classifier),
        answer=answer,
        trace_id=tid,
        escalate_from=escalate_from,
        completion=completion,
        onestack=onestack or {},
    )


def fusion_result_to_dict(fr: FusionResult) -> dict[str, Any]:
    """JSON-friendly FusionResult for Onestack / meta (AD-14 shape)."""
    return {
        "path": fr.path,
        "policy_path": fr.policy_path,
        "escalate_from": fr.escalate_from,
        "routed_by": fr.routed_by,
        "phase": fr.phase,
        "complexity": fr.complexity,
        "leader": fr.leader,
        "answer": fr.answer,
        "trace_id": fr.trace_id,
        "branches": [
            {
                "model": b.model_id,
                "model_id": b.model_id,
                "role": b.role,
                "billable_state": b.billable_state,
                "usage": b.usage,
                "prompt_tokens": b.prompt_tokens,
                "completion_tokens": b.completion_tokens,
                "meta": b.meta,
            }
            for b in fr.branches
        ],
    }


def _pack_completion(
    *,
    answer: str,
    panel: list[str],
    judge_model: str | None,
    agents: list[dict[str, Any]],
    mode: str,
    total_pt: int,
    total_ct: int,
    visible: str | None = None,
    routed_by: str = "compat_1to3_auto",
    product_mode: str = DEFAULT_PRODUCT_MODE,
    leader: str | None = None,
    task_kind: str | None = None,
    classifier: dict[str, Any] | None = None,
    escalate_from: str | None = None,
    policy_path: str | None = None,
    serving_path: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    # `visible` = thinking + answer for the client; `answer` kept clean in onestack
    body = visible if visible is not None else answer
    # AD-15: serving Path enum is authoritative; mode/fast|full is Edge stack size only.
    stack_size = "fast" if str(mode).startswith("fast") else "full"
    path = (serving_path or "").strip().upper() or stack_to_path(mode)
    if path not in ("FAST", "CASCADE", "RACE", "FULL"):
        path = stack_to_path(mode)
    pol_path = (policy_path or path).strip().upper() if policy_path else path
    if pol_path not in ("FAST", "CASCADE", "RACE", "FULL"):
        pol_path = path
    prod = product_mode if product_mode in PRODUCT_MODES else DEFAULT_PRODUCT_MODE
    head = leader or (panel[0] if panel else None)
    tid = trace_id or f"fus-{uuid.uuid4().hex[:16]}"

    # Stamp billable_state onto agent rows for Onestack transparency
    stamped_agents: list[dict[str, Any]] = []
    for a in agents:
        row = dict(a)
        row["billable_state"] = infer_billable_state(row)
        stamped_agents.append(row)

    fr = build_fusion_result(
        answer=answer,
        stack_mode=stack_size,
        routed_by=routed_by,
        leader=head,
        agents=stamped_agents,
        task_kind=task_kind,
        classifier=classifier,
        escalate_from=escalate_from,
        policy_path=pol_path,
        serving_path=path,
        trace_id=tid,
    )
    fr_dict = fusion_result_to_dict(fr)

    clf = classifier if isinstance(classifier, dict) else {}
    onestack = {
        "mode": f"fusion-{stack_size}",
        # legacy bridge — NOT serving mode (AD-15). Prefer path / stack_size.
        "fusion_mode": stack_size,
        "stack_size": stack_size,
        "path": fr.path,
        "policy_path": fr.policy_path,
        "escalate_from": fr.escalate_from,
        "product_mode": prod,
        "routed_by": fr.routed_by,
        "phase": fr.phase,
        "complexity": fr.complexity,
        "task_kind": task_kind or clf.get("task_kind") or "general",
        "leader": head,
        "panel": panel,
        "judge": judge_model,
        "classifier": classifier,
        "panel_ok": [a["model"] for a in stamped_agents if a.get("role") == "panel" and a.get("ok")],
        "agents": stamped_agents,
        "branches": fr_dict["branches"],
        "trace_id": fr.trace_id,
        "answer_only": answer,
        "thinking_visible": True,
        # Role Routing FR-14 / AD-28
        "pipeline": clf.get("pipeline") or "small",
        "size": clf.get("size") or "small",
        "second_signal": bool(clf.get("second_signal")),
        "curator_model": clf.get("curator_model") or head,
        "role_table": clf.get("role_table") or "v1",
        "roles": list(clf.get("roles") or []),
        "models_by_role": dict(clf.get("models_by_role") or {}),
        "gate": clf.get("gate"),
        "gate_reasons": list(clf.get("gate_reasons") or []),
        "escalate_count": int(clf.get("escalate_count") or 0),
        "soft_stop": bool(clf.get("soft_stop")),
    }
    fr.pipeline = onestack["pipeline"]
    fr.curator_model = onestack["curator_model"]
    fr.role_table = onestack["role_table"]
    fr.roles = list(onestack["roles"])
    fr.models_by_role = dict(onestack["models_by_role"])
    fr.task_kind = onestack["task_kind"]
    fr.size = onestack["size"]
    fr.gate = onestack.get("gate")
    fr.gate_reasons = list(onestack.get("gate_reasons") or [])
    fr.escalate_count = int(onestack.get("escalate_count") or 0)
    fr.soft_stop = bool(onestack.get("soft_stop"))
    fr.onestack = onestack
    data = {
        "id": f"chatcmpl-fusion-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": PUBLIC_FUSION_MODEL_ID,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": body},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": total_pt,
            "completion_tokens": total_ct,
            "total_tokens": total_pt + total_ct,
        },
        "onestack": onestack,
        "_bill_model": judge_model or head or "deepseek-chat",
        "_fusion_result": fr,
        "fusion_result": fr_dict,
    }
    fr.completion = {k: v for k, v in data.items() if k != "_fusion_result"}
    return data


def _clip(text: str, n: int = 160) -> str:
    t = " ".join((text or "").split())
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


_LATIN_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _variant_label(i: int) -> str:
    if 0 <= i < len(_LATIN_LABELS):
        return f"вариант {_LATIN_LABELS[i]}"
    return f"вариант {i + 1}"


def _short_label(i: int) -> str:
    if 0 <= i < len(_LATIN_LABELS):
        return _LATIN_LABELS[i]
    return str(i + 1)


def _progress_bar(ready: int, total: int) -> str:
    total = max(total, 1)
    ready = max(0, min(int(ready), total))
    return "▓" * ready + "░" * (total - ready)


def _think_frame_open(n: int) -> str:
    return f"╭ мышление · {_progress_bar(0, n)} · {n} ветки"


def _think_branch(ready: int, total: int, done_labels: list[str], lat: float | None = None) -> str:
    bar = _progress_bar(ready, total)
    tags = " · ".join(done_labels) if done_labels else "—"
    extra = f" · {lat:.1f}с" if lat is not None else ""
    return f"│ {bar}  {tags}{extra}"


def _think_synth() -> str:
    return "│ ◆ синтез"


def _think_frame_close() -> str:
    return "╰"


async def iter_fusion(
    *,
    messages: list[dict[str, Any]],
    user: Any | None = None,
    models: list[str] | None = None,
    judge: str | None = None,
    mode: str | None = None,
    model_id: str | None = None,
    zeus: dict[str, Any] | None = None,
    show_thinking: bool | None = None,
    cancel_event: Any | None = None,
):
    """Yield events: {kind: think|answer|done, text?, data?} — no model names in text.

    Scrub once at Edge→Policy (AD-17). Done payload carries FusionResult (AD-14).
    ``cancel_event`` (asyncio.Event) signals client disconnect / Soft-Stop mid-flight.
    """
    messages = prepare_messages_for_policy(messages)
    user_q = _text_of(messages) or "Ответь на запрос."
    product_mode = DEFAULT_PRODUCT_MODE
    routed_by = "forced_full"
    resolved = (mode or "").strip().lower()
    # AD-15: Path enum is the serving decision; fast|full is Edge stack size only.
    serving_path = "FULL"
    policy_path_serving: str | None = None
    clf_meta: dict[str, Any] | None = None
    trace_id = f"fus-{uuid.uuid4().hex[:16]}"
    if resolved not in ("fast", "full"):
        # Regex/product + legacy/forced aliases; stack may be overridden by LLM
        resolved, routed_by, product_mode = resolve_routing_ex(model_id, zeus, user_q)
        if routed_by in ("compat_1to3_auto", "auto"):
            clf_meta = await classify_smart(messages, user_q=user_q)
            resolved = str(clf_meta.get("stack") or resolved)
            if resolved not in ("fast", "full"):
                resolved = "fast"
            routed_by = "compat_1to3_classify"
        serving_path = stack_to_path(resolved)
        policy_path_serving = serving_path
        # EPIC2-HOOK — soft Path policy; flag off / incomplete → brownfield above
        try:
            from app.fusion.policy import (  # noqa: WPS433
                path_to_legacy_stack,
                soft_resolve_for_monolith,
            )

            _src = str((clf_meta or {}).get("source") or "")
            _clf_failed = bool(
                (clf_meta or {}).get("classify_failed")
                or (clf_meta or {}).get("failed")
                or (
                    _src.startswith("regex-")
                    and _src not in ("regex-chitchat",)
                )
            )
            _epic2 = soft_resolve_for_monolith(
                user_q=user_q,
                model_id=model_id,
                zeus=zeus,
                messages=messages,
                clf_meta=clf_meta,
                classify_failed=_clf_failed,
                stream=True,
            )
            if _epic2 is not None:
                serving_path = str(_epic2.path).upper()
                policy_path_serving = str(_epic2.policy_path or serving_path).upper()
                # Edge adapter: Path → panel stack size (not serving mode)
                # CASCADE keeps distinct serving_path; stack size still fast for panel pick.
                resolved = path_to_legacy_stack(serving_path)
                routed_by = str(_epic2.routed_by)
                product_mode = str(_epic2.product_mode)
                if clf_meta is None:
                    clf_meta = {}
                clf_meta = dict(clf_meta)
                clf_meta.update(
                    {
                        "classify_phase": _epic2.phase,
                        "complexity_band": _epic2.complexity,
                        "confidence": _epic2.confidence,
                        "policy_path": policy_path_serving,
                        "path": serving_path,
                        "epic2_routed_by": _epic2.routed_by,
                        "mode_ignored": _epic2.mode_ignored,
                        "classify_failed": _epic2.classify_failed,
                    }
                )
        except Exception:  # noqa: BLE001 — never break brownfield
            pass
    else:
        # Explicit stack override via mode= arg → forced_* (not legacy_*)
        routed_by = "forced_fast" if resolved == "fast" else "forced_full"
        product_mode = "simple" if resolved == "fast" else "power"
        serving_path = stack_to_path(resolved)
        policy_path_serving = serving_path
        if isinstance(zeus, dict):
            pm = normalize_product_mode(str(zeus.get("mode") or ""))
            if pm:
                product_mode = pm

    # EPIC4-HOOK AD-9: shadow/canary/kill when soft_resolve did not already clamp
    _rb_l = (routed_by or "").lower()
    _flags_already = any(
        tok in _rb_l
        for tok in (
            "shadow_baseline",
            "+shadow",
            "canary_holdout",
            "+canary",
            "kill_switch",
        )
    )
    if not _flags_already:
        try:
            from app.fusion.metrics import (
                apply_serving_flags,
                legacy_baseline_path,
                load_fusion_flags,
            )

            _flags = load_fusion_flags()
            if _flags.shadow or _flags.canary_pct > 0 or _flags.kill or (
                isinstance(zeus, dict) and zeus.get("kill_switch")
            ):
                _base = legacy_baseline_path(resolved)
                _cand = str(policy_path_serving or serving_path)
                serving_path, policy_path_serving, routed_by = apply_serving_flags(
                    candidate_path=_cand,
                    baseline_path=_base,
                    zeus=zeus if isinstance(zeus, dict) else None,
                    routed_by=routed_by,
                    phase=str((clf_meta or {}).get("classify_phase") or ""),
                    trace_id=trace_id,
                )
                resolved = "fast" if serving_path in ("FAST", "CASCADE") else "full"
        except Exception:  # noqa: BLE001
            pass

    if show_thinking is None:
        if isinstance(zeus, dict) and "thinking" in zeus:
            show_thinking = bool(zeus.get("thinking"))
        else:
            # Brief status on both paths so Cursor never stares at a blank pane
            show_thinking = True

    # simple/power → exclusive Zeus stack; custom → caller's models[] (1↔3 auto)
    panel_models = models if product_mode == "custom" else None

    panel, judge_model = resolve_panel(
        user=user,
        models=panel_models,
        judge=judge,
        mode=resolved,
        product_mode=product_mode,
    )

    # FR-34 custom panel rules (1→FAST / 2→A+B / 3→A/B/C)
    if product_mode == "custom" and panel:
        try:
            from app.fusion.policy import resolve_custom_panel

            _cplan = resolve_custom_panel(panel, ready=panel)
            if _cplan.models:
                panel = list(_cplan.models)
            if _cplan.path_hint == "FAST":
                serving_path = "FAST"
                resolved = "fast"
                judge_model = None
            elif _cplan.path_hint == "CASCADE" and serving_path not in (
                "RACE",
                "FULL",
            ):
                serving_path = "CASCADE"
                resolved = "fast"
                judge_model = None
            elif _cplan.path_hint == "FULL":
                serving_path = "FULL"
                resolved = "full"
        except Exception:  # noqa: BLE001
            pass

    if clf_meta and clf_meta.get("source") == "llm":
        task_kind = str(clf_meta.get("task") or "general")
        if task_kind not in _TASK_KINDS:
            task_kind = classify_task(user_q)
    else:
        task_kind = (
            str(clf_meta.get("task"))
            if clf_meta and clf_meta.get("task") in _TASK_KINDS
            else classify_task(user_q)
        )
    # Light asks force light affinity even if regex said "code" from a short "напиши"
    if resolved == "fast" and task_kind not in ("light", "ui"):
        task_kind = "light"
    _sticky = None
    _unhealthy: set[str] = set()
    if isinstance(zeus, dict):
        _sticky = str(zeus.get("sticky_leader") or "").strip() or None
        raw_un = zeus.get("unhealthy_models") or zeus.get("dead_models") or []
        if isinstance(raw_un, (list, tuple, set)):
            _unhealthy = {str(x).strip() for x in raw_un if str(x).strip()}
    _ctx_chars = sum(len(str(m.get("content") or "")) for m in messages)
    leader = pick_leader(
        panel,
        task_kind,
        sticky_leader=_sticky,
        unhealthy=_unhealthy or None,
        context_chars=_ctx_chars,
    )
    panel = order_panel_leader_first(panel, leader)

    # --- Role Routing Epic 1: classify size/2nd → roles → pipeline=small clamps ---
    _rr_decision = None
    _rr_roles = None
    try:
        from app.fusion.pipeline import (
            apply_small_path_clamps,
            pick_pipeline,
        )
        from app.fusion.policy import classify_local as _rr_classify_local
        from app.fusion.roles import resolve_roles

        _rr_clf = _rr_classify_local(user_q, messages=messages)
        # AD-22: classify_local is authoritative for RR pipeline pick — do not let
        # stale brownfield clf_meta.size/second_signal suppress fallback_single/v1.
        _rr_size = str(getattr(_rr_clf, "size", None) or "small")
        _rr_second = bool(getattr(_rr_clf, "second_signal", False))
        if clf_meta is None:
            clf_meta = {}
        clf_meta = dict(clf_meta)
        clf_meta["size"] = _rr_size
        clf_meta["second_signal"] = _rr_second
        if getattr(_rr_clf, "task_kind", None):
            task_kind = str(_rr_clf.task_kind)
            clf_meta["task_kind"] = task_kind
        else:
            clf_meta.setdefault("task_kind", task_kind)
        _kill_rr = bool(
            (zeus or {}).get("kill_switch")
            if isinstance(zeus, dict)
            else False
        ) or ("kill_switch" in (routed_by or "").lower())
        # Custom must use caller models[] (AD-21) — never the exclusive fill from resolve_panel.
        _rr_custom = list(panel_models) if product_mode == "custom" else None
        _rr_roles = resolve_roles(
            product_mode=product_mode,
            task_kind=task_kind,
            panel=panel,
            custom_models=_rr_custom,
            unhealthy=_unhealthy or None,
        )
        _rr_decision = pick_pipeline(
            size=_rr_size,
            second_signal=_rr_second,
            product_mode=product_mode,
            kill_switch=_kill_rr,
            roles=_rr_roles,
            forced_path=routed_by
            in ("forced_fast", "forced_full", "legacy_fast_alias", "legacy_full_alias"),
        )
        # Apply clamps for small/fallback; v1 also demotes RACE (AD-20) via same helper
        serving_path, panel, leader = apply_small_path_clamps(
            serving_path=serving_path,
            panel=panel,
            leader=leader,
            decision=_rr_decision,
        )
        # Curator ≡ Leader (AD-32)
        if _rr_decision.curator_model:
            leader = _rr_decision.curator_model
        panel = order_panel_leader_first(panel, leader)
        resolved = "fast" if serving_path in ("FAST", "CASCADE") else "full"
        clf_meta["pipeline"] = _rr_decision.pipeline
        clf_meta["curator_model"] = leader
        clf_meta["role_table"] = _rr_roles.role_table
        clf_meta["roles"] = list(_rr_roles.roles)
        clf_meta["models_by_role"] = dict(_rr_roles.models_by_role)
        clf_meta["size"] = _rr_decision.size
        clf_meta["second_signal"] = bool(_rr_decision.second_signal)
        # Keep clf path in sync — later epic3 override reads clf_meta["path"]
        clf_meta["path"] = serving_path
        clf_meta["policy_path"] = serving_path
        # AD-9 / NFR-5 defense: kill never leaves pipeline=v1 intent
        if _kill_rr:
            clf_meta["pipeline"] = "small"
            clf_meta["second_signal"] = False
    except Exception:  # noqa: BLE001 — Role Routing must never break brownfield
        _rr_decision = None
        _rr_roles = None
        if not isinstance(clf_meta, dict):
            clf_meta = {}
        else:
            clf_meta = dict(clf_meta)
        # Best-effort salvage: still try to stamp fallback_single when eligible (AD-23)
        try:
            from app.fusion.pipeline import apply_small_path_clamps, pick_pipeline
            from app.fusion.policy import classify_local as _rr_classify_local2
            from app.fusion.roles import resolve_roles as _resolve_roles2

            _clf2 = _rr_classify_local2(user_q, messages=messages)
            _kill2 = bool(
                isinstance(zeus, dict) and zeus.get("kill_switch")
            ) or ("kill_switch" in (routed_by or "").lower())
            _roles2 = _resolve_roles2(
                product_mode=product_mode,
                task_kind=str(
                    getattr(_clf2, "task_kind", None) or task_kind or "general"
                ),
                panel=panel,
                custom_models=(
                    list(panel_models) if product_mode == "custom" else None
                ),
                unhealthy=_unhealthy or None,
            )
            _dec2 = pick_pipeline(
                size=str(getattr(_clf2, "size", None) or "small"),
                second_signal=bool(getattr(_clf2, "second_signal", False)),
                product_mode=product_mode,
                kill_switch=_kill2,
                roles=_roles2,
            )
            serving_path, panel, leader = apply_small_path_clamps(
                serving_path=serving_path,
                panel=panel,
                leader=leader,
                decision=_dec2,
            )
            if _dec2.curator_model:
                leader = _dec2.curator_model
            panel = order_panel_leader_first(panel, leader)
            resolved = "fast" if serving_path in ("FAST", "CASCADE") else "full"
            clf_meta["pipeline"] = _dec2.pipeline
            clf_meta["curator_model"] = leader
            clf_meta["role_table"] = _roles2.role_table
            clf_meta["roles"] = list(_roles2.roles)
            clf_meta["models_by_role"] = dict(_roles2.models_by_role)
            clf_meta["size"] = _dec2.size
            clf_meta["second_signal"] = bool(_dec2.second_signal)
            clf_meta["path"] = serving_path
            clf_meta["policy_path"] = serving_path
            _rr_decision = _dec2
            _rr_roles = _roles2
            if _kill2:
                clf_meta["pipeline"] = "small"
                clf_meta["second_signal"] = False
        except Exception:  # noqa: BLE001
            clf_meta.setdefault("pipeline", "small")
            if panel and len(panel) > 2:
                panel = list(panel)[:2]
                panel = order_panel_leader_first(panel, leader)

    clf_tokens_pt = int((clf_meta or {}).get("prompt_tokens") or 0)
    clf_tokens_ct = int((clf_meta or {}).get("completion_tokens") or 0)

    think_parts: list[str] = []

    def think(line: str) -> dict[str, Any]:
        think_parts.append(line)
        return {"kind": "think", "text": line + "\n"}

    # --- Clarifier (pre-dev interview) — before Path/pipeline execute ---
    try:
        from app.fusion.clarifier import (
            ClarifierState,
            apply_enriched_to_messages,
            run_clarifier_turn,
            should_run_clarifier,
        )
        from app.fusion.session import extract_session_id
        from app.fusion.types import BranchUsage

        _z_cl = zeus if isinstance(zeus, dict) else {}
        _sid = extract_session_id(zeus=_z_cl)
        _cl_state = ClarifierState.from_dict(
            _z_cl.get("clarify_state")
            if isinstance(_z_cl.get("clarify_state"), dict)
            else (clf_meta or {}).get("clarify_state")
        )
        _kill_cl = bool(_z_cl.get("kill_switch")) or "kill_switch" in (
            routed_by or ""
        ).lower()
        _size_cl = str((clf_meta or {}).get("size") or "small")
        _second_cl = bool((clf_meta or {}).get("second_signal"))
        if should_run_clarifier(
            product_mode=product_mode,
            size=_size_cl,
            second_signal=_second_cl,
            kill_switch=_kill_cl,
            zeus=_z_cl,
            user_q=user_q,
            state=_cl_state,
        ):
            _stack_cl = list(
                (_rr_roles.stack if _rr_roles else None)
                or panel
                or []
            )
            _cur_cl = (
                (_rr_roles.curator_model if _rr_roles else None)
                or leader
                or (_stack_cl[0] if _stack_cl else None)
            )
            if show_thinking:
                yield think("╭ clarifier · уточняю задачу…")
            _cl_turn = await run_clarifier_turn(
                user_q=user_q,
                messages=messages,
                state=_cl_state,
                stack=_stack_cl,
                curator=_cur_cl,
                unhealthy=_unhealthy or None,
                session_id=_sid,
            )
            _cl_state = _cl_turn.state
            if isinstance(clf_meta, dict):
                clf_meta["clarify_phase"] = _cl_turn.phase
                clf_meta["clarifier_model"] = _cl_turn.model_id
                clf_meta["clarify_state"] = _cl_state.to_dict()
                clf_meta["brief_approved"] = bool(
                    (_cl_turn.meta or {}).get("brief_approved")
                )
            if _cl_turn.halt:
                if show_thinking:
                    yield think(f"│ clarifier · phase={_cl_turn.phase}")
                    yield think(_think_frame_close())
                    yield think("")
                _cl_answer = (_cl_turn.user_text or "").strip()
                yield {"kind": "answer", "text": _cl_answer}
                _cl_agents: list[dict[str, Any]] = []
                if _cl_turn.model_id:
                    _cl_agents.append(
                        {
                            "model": _cl_turn.model_id,
                            "role": "clarifier",
                            "ok": True,
                            "prompt_tokens": int(_cl_turn.prompt_tokens or 0),
                            "completion_tokens": int(_cl_turn.completion_tokens or 0),
                            "preview": _cl_answer[:280],
                        }
                    )
                _cl_data = _pack_completion(
                    answer=_cl_answer,
                    panel=panel,
                    judge_model=None,
                    agents=_cl_agents,
                    mode="fast",
                    total_pt=int(_cl_turn.prompt_tokens or 0) + clf_tokens_pt,
                    total_ct=int(_cl_turn.completion_tokens or 0) + clf_tokens_ct,
                    routed_by="clarifier_" + str(_cl_turn.phase),
                    product_mode=product_mode,
                    leader=_cur_cl or leader,
                    task_kind=task_kind,
                    classifier=clf_meta,
                    policy_path="FAST",
                    serving_path="FAST",
                    trace_id=trace_id,
                )
                if isinstance(_cl_data.get("onestack"), dict):
                    _cl_data["onestack"]["clarify_phase"] = _cl_turn.phase
                    _cl_data["onestack"]["clarifier_model"] = _cl_turn.model_id
                    _cl_data["onestack"]["brief_approved"] = False
                    _cl_data["onestack"]["clarify_state"] = _cl_state.to_dict()
                    _cl_data["onestack"]["pipeline"] = (
                        (clf_meta or {}).get("pipeline") or "small"
                    )
                _cl_data["clarify_state"] = _cl_state.to_dict()
                # Attach billable clarifier branch on FusionResult when present
                try:
                    _fr = _cl_data.get("_fusion_result")
                    if _fr is not None and _cl_turn.model_id:
                        _fr.branches = list(getattr(_fr, "branches", None) or []) + [
                            BranchUsage(
                                model_id=_cl_turn.model_id,
                                billable_state="completed",
                                prompt_tokens=int(_cl_turn.prompt_tokens or 0),
                                completion_tokens=int(_cl_turn.completion_tokens or 0),
                                role="clarifier",
                                meta={"phase": _cl_turn.phase},
                            )
                        ]
                        _fr.routed_by = "clarifier_" + str(_cl_turn.phase)
                except Exception:  # noqa: BLE001
                    pass
                yield {"kind": "done", "data": _cl_data}
                return
            # Approved — continue into normal pipeline with enriched prompt
            if _cl_turn.phase == "done" and (_cl_turn.user_text or "").strip():
                user_q = _cl_turn.user_text.strip()
                messages = apply_enriched_to_messages(messages, user_q)
                if show_thinking:
                    yield think("│ clarifier · ТЗ утверждено → разработка")
    except Exception:  # noqa: BLE001 — clarifier must never break brownfield
        pass

    # EPIC2/3 Path executors — CASCADE/RACE/FULL. FAST stays brownfield below.
    from app.fusion.panel import (  # local import keeps facade load light
        PanelDiversityError as _PanelDiversityError,
        clamp_f13_never_race_on_heavy as _clamp_f13,
        execute_cascade as _epic2_execute_cascade,
        execute_full as _epic3_execute_full,
        execute_race as _epic3_execute_race,
        outcome_to_completion as _epic3_outcome_to_completion,
        resolve_path_override as _epic3_resolve_path_override,
        execute_fallback_single as _execute_fallback_single,
    )
    from app.fusion.pipeline import (  # AD-29: orchestration surface via pipeline.py
        execute_pipeline_v1 as _execute_pipeline_v1,
        write_pipeline as _write_pipeline,
    )
    from app.fusion.ui_crew import (
        execute_ui_crew as _execute_ui_crew,
        is_ui_crew_task as _is_ui_crew_task,
        ui_crew_enabled as _ui_crew_enabled,
    )

    _z = zeus if isinstance(zeus, dict) else {}
    _complexity = str(
        _z.get("complexity")
        or (clf_meta or {}).get("complexity_band")
        or "med"
    )
    _phase = str(
        (clf_meta or {}).get("classify_phase")
        or (clf_meta or {}).get("phase")
        or _z.get("phase")
        or "implement"
    )

    _use_ui_crew = _ui_crew_enabled() and _is_ui_crew_task(
        task_kind=task_kind, user_q=user_q, phase=_phase
    )

    async def _epic3_execute_full_or_crew(**kwargs):
        """FULL path: UI Crew for site/HTML tasks, classic 3-author judge otherwise."""
        if _use_ui_crew:
            return await _execute_ui_crew(
                panel=kwargs.get("panel") or panel,
                leader=kwargs.get("leader") or leader,
                messages=kwargs.get("messages") or messages,
                user_q=kwargs.get("user_q") or user_q,
                policy_path=kwargs.get("policy_path") or "FULL",
                cancel_event=kwargs.get("cancel_event"),
            )
        return await _epic3_execute_full(**kwargs)

    _epic3_path = _epic3_resolve_path_override(
        _z, complexity=_complexity, phase=_phase
    )
    # AD-9 / NFR-5: kill wins over zeus.path / clf path overrides
    if bool(_z.get("kill_switch")) or "kill_switch" in (routed_by or "").lower():
        _epic3_path = None
        serving_path = "FAST"
        if isinstance(clf_meta, dict):
            clf_meta["path"] = "FAST"
            clf_meta["policy_path"] = "FAST"
            clf_meta["pipeline"] = "small"
            clf_meta["second_signal"] = False
    if _epic3_path is None and isinstance(clf_meta, dict):
        _p = str(clf_meta.get("path") or "").strip().upper()
        if _p in ("RACE", "FULL", "CASCADE"):
            _epic3_path = _p  # type: ignore[assignment]
    # Serving Path is authoritative (no silent brownfield FULL fallthrough)
    if _epic3_path is None and serving_path in ("CASCADE", "RACE", "FULL"):
        _epic3_path = serving_path  # type: ignore[assignment]
    if _epic3_path is None and str(resolved).startswith("full"):
        _epic3_path = "FULL"  # type: ignore[assignment]
        serving_path = "FULL"

    if _epic3_path in ("CASCADE", "RACE", "FULL"):
        _epic3_path = _clamp_f13(
            _epic3_path, complexity=_complexity, phase=_phase
        )
        # AD-20: zeus.path / clf_meta can reintroduce RACE/FULL after RR clamps — demote again.
        # Keep forced/legacy FULL (ops/tests); still never allow RACE on RR small/fallback.
        _pipe = str((clf_meta or {}).get("pipeline") or "")
        _forced_full = (routed_by or "") in (
            "forced_full",
            "legacy_full_alias",
        )
        if _pipe == "v1" and _epic3_path == "RACE":
            _epic3_path = "FULL"  # type: ignore[assignment]
        elif _pipe in ("small", "fallback_single") and _epic3_path == "RACE":
            _epic3_path = "CASCADE"  # type: ignore[assignment]
        elif (
            _pipe in ("small", "fallback_single")
            and _epic3_path == "FULL"
            and not _forced_full
        ):
            _epic3_path = "CASCADE"  # type: ignore[assignment]
        serving_path = str(_epic3_path)
        policy_path_serving = policy_path_serving or serving_path
        _soft_stop = bool(_z.get("soft_stop"))
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            _soft_stop = True
        _ops_div = bool(_z.get("ops_diversity_exception"))
        _kill = bool(_z.get("kill_switch"))
        _pipe_exec = str((clf_meta or {}).get("pipeline") or "")
        if show_thinking:
            if _pipe_exec == "v1":
                yield think("╭ path FULL · pipeline v1 (Brief→tests→doers)…")
            elif _pipe_exec == "fallback_single":
                yield think("╭ path CASCADE · fallback_single curator…")
            else:
                _crew_tag = " · UI Crew" if _use_ui_crew and _epic3_path == "FULL" else ""
                yield think(f"╭ path {_epic3_path}{_crew_tag}…")
        try:
            # Epic 4 / AD-20..26: Pipeline v1 before brownfield FULL/CASCADE
            if _pipe_exec == "v1":
                _cur = leader or (panel[0] if panel else "")
                _outcome = await _execute_pipeline_v1(
                    stack=list(panel or []),
                    curator=_cur,
                    messages=messages,
                    user_q=user_q,
                    product_mode=product_mode,
                    complexity=_complexity,
                    phase=_phase,
                    cancel_event=cancel_event,
                    unhealthy=_unhealthy or None,
                )
                if (_outcome.meta or {}).get("degrade_to_fallback"):
                    # FR-12 / AD-23: invalid Brief → curator one-shot
                    _degrade_reason = str(
                        (_outcome.meta or {}).get("degrade_reason") or "invalid_brief"
                    )
                    clf_meta = _write_pipeline(
                        clf_meta if isinstance(clf_meta, dict) else {},
                        "fallback_single",
                        reason=f"degrade_from_v1:{_degrade_reason}",
                    )
                    # Keep classifier path honest with serving Path (AD-8 / composition E4→E3)
                    clf_meta["path"] = "CASCADE"
                    clf_meta["policy_path"] = "CASCADE"
                    _pipe_exec = "fallback_single"
                    if show_thinking:
                        yield think(
                            f"│ Brief invalid → degrade fallback_single ({_degrade_reason})"
                        )
                    _prior_branches = list(_outcome.branches or [])
                    _outcome = await _execute_fallback_single(
                        curator=_cur,
                        messages=messages,
                        user_q=user_q,
                        product_mode=product_mode,
                        complexity=_complexity,
                        phase=_phase,
                        cancel_event=cancel_event,
                        adapt_prompts=True,
                    )
                    # Keep Architect attempt billable (FR-15)
                    if _prior_branches:
                        _outcome.branches = list(_prior_branches) + list(
                            _outcome.branches or []
                        )
                    _outcome.meta = {
                        **(dict(_outcome.meta or {})),
                        "degraded_from": "v1",
                        "degrade_reason": _degrade_reason,
                        "pipeline": "fallback_single",
                    }
                    serving_path = "CASCADE"
                    policy_path_serving = "CASCADE"
                else:
                    serving_path = "FULL"
                    policy_path_serving = "FULL"
                    clf_meta = _write_pipeline(
                        clf_meta if isinstance(clf_meta, dict) else {},
                        "v1",
                        reason="pipeline_v1_ok",
                    )
                    clf_meta["path"] = "FULL"
                    clf_meta["policy_path"] = "FULL"
            # Epic 3 / AD-23: curator one-shot — never CASCADE multi-doer or FULL handoff
            elif _pipe_exec == "fallback_single":
                _cur = leader or (panel[0] if panel else "")
                # Enforce single-model panel (no mid-parallel)
                panel = [_cur] if _cur else []
                _outcome = await _execute_fallback_single(
                    curator=_cur,
                    messages=messages,
                    user_q=user_q,
                    product_mode=product_mode,
                    complexity=_complexity,
                    phase=_phase,
                    cancel_event=cancel_event,
                    adapt_prompts=True,
                )
                serving_path = "CASCADE"
                policy_path_serving = "CASCADE"
            elif _epic3_path == "CASCADE":
                _outcome = await _epic2_execute_cascade(
                    panel=panel,
                    leader=leader,
                    messages=messages,
                    user_q=user_q,
                    product_mode=product_mode,
                    complexity=_complexity,
                    phase=_phase,
                    kill_switch=_kill,
                    ready=panel,
                    cancel_event=cancel_event,
                    adapt_prompts=True,
                )
                if _outcome.meta.get("hand_off_full") or (
                    _outcome.path == "FULL"
                    and _outcome.routed_by == "cascade_escalate_full"
                ):
                    if show_thinking and _use_ui_crew:
                        yield think("│ UI Crew (Author→Critics→Revise)…")
                    _outcome = await _epic3_execute_full_or_crew(
                        panel=panel,
                        leader=leader,
                        messages=messages,
                        user_q=user_q,
                        judge_model=judge_model,
                        policy_path="CASCADE",
                        soft_stop=_soft_stop,
                        ops_diversity_exception=_ops_div,
                        cancel_event=cancel_event,
                    )
                    _outcome.escalate_from = "CASCADE"
                    if not str(_outcome.routed_by or "").startswith("ui_"):
                        _outcome.routed_by = "cascade_escalate_full"
                    serving_path = "FULL"
            elif _epic3_path == "RACE":
                _cheap = panel[-1] if len(panel) > 1 else panel[0]
                _strong = leader
                _outcome = await _epic3_execute_race(
                    cheap_model=_cheap,
                    strong_model=_strong,
                    messages=messages,
                    user_q=user_q,
                    product_mode=product_mode,
                    complexity=_complexity,
                    soft_stop=_soft_stop,
                    cancel_event=cancel_event,
                )
                if (
                    _outcome.routed_by == "race_escalate_full"
                    and product_mode in ("power", "custom")
                ):
                    if show_thinking and _use_ui_crew:
                        yield think("│ UI Crew (Author→Critics→Revise)…")
                    _outcome = await _epic3_execute_full_or_crew(
                        panel=panel,
                        leader=leader,
                        messages=messages,
                        user_q=user_q,
                        judge_model=judge_model,
                        policy_path="RACE",
                        ops_diversity_exception=_ops_div,
                        soft_stop=_soft_stop,
                        cancel_event=cancel_event,
                    )
                    _outcome.escalate_from = "RACE"
                    if not str(_outcome.routed_by or "").startswith("ui_"):
                        _outcome.routed_by = "race_escalate_full"
            else:
                if show_thinking and _use_ui_crew:
                    yield think("│ UI Crew (Author→Critics→Revise)…")
                _outcome = await _epic3_execute_full_or_crew(
                    panel=panel,
                    leader=leader,
                    messages=messages,
                    user_q=user_q,
                    judge_model=judge_model,
                    ops_diversity_exception=_ops_div,
                    soft_stop=_soft_stop,
                    cancel_event=cancel_event,
                )
        except _PanelDiversityError as e:
            raise HTTPException(
                502,
                f"ZeusCode: panel diversity ({e})",
            ) from e

        if _outcome.disaster and not (_outcome.answer or "").strip():
            # AD-23: empty fallback_single curator must still hit Soft-Stop via TV, not 502
            if _pipe_exec == "fallback_single" or (
                isinstance(getattr(_outcome, "meta", None), dict)
                and (_outcome.meta or {}).get("pipeline") == "fallback_single"
            ):
                _outcome.disaster = False
                _outcome.answer = ""
            else:
                raise HTTPException(
                    502,
                    f"ZeusCode: пустой ответ модели ({_outcome.disaster_code or _outcome.routed_by})",
                )
        # FR-37: force/legacy labels win — except UI Crew executor signals (ui_*)
        if routed_by.startswith(("forced_", "legacy_")):
            if str(_outcome.routed_by or "").startswith("ui_"):
                _outcome.meta = dict(_outcome.meta or {})
                _outcome.meta["policy_routed_by"] = routed_by
            else:
                _outcome.routed_by = routed_by
        _answer = (_outcome.answer or "").strip()
        if not _answer:
            if _pipe_exec == "fallback_single" or (
                isinstance(getattr(_outcome, "meta", None), dict)
                and (_outcome.meta or {}).get("pipeline") == "fallback_single"
            ):
                # Placeholder so TV Soft-Stop has a body to stamp RED line on
                _answer = "Ответ куратора недоступен."
            else:
                _answer = "Привет! На связи. Напиши задачу — отвечу."
        if show_thinking:
            yield think(f"│ ✓ {_outcome.routed_by}")
            yield think(_think_frame_close())
            yield think("")
        _rr_payload = {
            "pipeline": (clf_meta or {}).get("pipeline") or "small",
            "size": (clf_meta or {}).get("size") or "small",
            "second_signal": bool((clf_meta or {}).get("second_signal")),
            "curator_model": (clf_meta or {}).get("curator_model") or leader,
            "role_table": (clf_meta or {}).get("role_table") or "v1",
            "roles": list((clf_meta or {}).get("roles") or []),
            "models_by_role": dict((clf_meta or {}).get("models_by_role") or {}),
            "task_kind": task_kind,
            "gate": (clf_meta or {}).get("gate"),
            "gate_reasons": list((clf_meta or {}).get("gate_reasons") or []),
            "escalate_count": int((clf_meta or {}).get("escalate_count") or 0),
            "soft_stop": bool((clf_meta or {}).get("soft_stop")),
        }
        # Epic 5 Layer A (FR-9/10): Studio allowlist executor before Gate
        _tests_failed = None
        try:
            import asyncio as _aio_la

            from app.fusion.test_executor import (
                executor_signal_for_gate as _la_signal,
                run_layer_a_for_request,
            )

            # B1: never block the event loop on subprocess.run (≤120s)
            _ex = await _aio_la.to_thread(run_layer_a_for_request, _z)
            _tests_failed = _la_signal(_ex)
            if isinstance(clf_meta, dict):
                clf_meta["layer_a"] = {
                    "skipped": _ex.skipped,
                    "reason": _ex.reason,
                    "exit_code": _ex.exit_code,
                    "tests_failed": _ex.tests_failed,
                }
            _rr_payload["layer_a"] = {
                "skipped": _ex.skipped,
                "reason": _ex.reason,
                "tests_failed": _ex.tests_failed,
            }
            if show_thinking and (_tests_failed is not None or not _ex.skipped):
                yield think(
                    f"│ Layer A → {(_ex.reason or '?')}"
                    + (
                        f" · {'FAIL' if _ex.tests_failed else 'PASS'}"
                        if _ex.exit_code is not None
                        else ""
                    )
                )
        except Exception:  # noqa: BLE001 — executor must not break chat
            _tests_failed = None

        # Epic 2 Trusted Verify Loop (AD-25/27): Log → Gate → Escalate≤2 → Soft-Stop
        _tv = None
        try:
            from app.fusion.verify import run_trusted_verify_loop

            _kill_tv = bool(_z.get("kill_switch")) or "kill_switch" in (
                routed_by or ""
            ).lower()
            # AD-25: post-merge/outcome only — never raw live doer chunks when answer exists
            _cands: list[tuple[str, str]] = []
            if _answer:
                _cands.append((str(leader or "leader"), _answer))
            else:
                for _lb in getattr(_outcome, "live", None) or []:
                    _t = str(getattr(_lb, "text", "") or "").strip()
                    if _t:
                        _cands.append(
                            (str(getattr(_lb, "model_id", "") or leader), _t)
                        )
            _tv = await run_trusted_verify_loop(
                answer=_answer,
                user_q=user_q,
                messages=messages,
                panel=panel,
                models_by_role=_rr_payload.get("models_by_role") or {},
                curator_model=_rr_payload.get("curator_model") or leader,
                early_exit=_outcome.early_exit,
                routed_by=_outcome.routed_by,
                branches=list(_outcome.branches or []),
                disaster=bool(_outcome.disaster),
                soft_stop_already=bool(_soft_stop)
                or "soft_stop" in str(_outcome.early_exit or "").lower()
                or "soft_stop" in str(_outcome.routed_by or "").lower(),
                # FR-8: Mini skip only on kill/legacy FAST — not every FAST
                allow_green_without_mini=_kill_tv
                or (routed_by or "")
                in ("forced_fast", "legacy_fast_alias", "kill_switch"),
                max_escalate=0 if _kill_tv else 2,  # AD-9: kill stays cheap
                candidate_answers=_cands,
                tests_failed=_tests_failed,
            )
            _answer = _tv.answer
            _rr_payload["gate"] = _tv.gate
            _rr_payload["gate_reasons"] = list(_tv.gate_reasons)
            _rr_payload["escalate_count"] = int(_tv.escalate_count)
            _rr_payload["soft_stop"] = bool(_tv.soft_stop)
            _rr_payload["log_report"] = _tv.log_report
            _rr_payload["soft_stop_model"] = _tv.soft_stop_model
            if _tv.branches:
                _outcome.branches = list(_outcome.branches or []) + list(_tv.branches)
        except Exception:  # noqa: BLE001 — fail closed: RED Soft-Stop shell (FR-6)
            from app.fusion.verify import append_soft_stop_red_line

            _answer = append_soft_stop_red_line(_answer)
            _rr_payload["gate"] = "RED"
            _rr_payload["gate_reasons"] = ["verify_loop_failed"]
            _rr_payload["escalate_count"] = 0
            _rr_payload["soft_stop"] = True
            _rr_payload["log_report"] = "N/A"
            _rr_payload["soft_stop_model"] = leader
            _tv = type(
                "TV",
                (),
                {
                    "answer": _answer,
                    "gate": "RED",
                    "gate_reasons": ["verify_loop_failed"],
                    "escalate_count": 0,
                    "soft_stop": True,
                    "log_report": "N/A",
                    "soft_stop_model": leader,
                    "branches": [],
                },
            )()

        if show_thinking and _tv is not None:
            yield think(
                f"│ gate {_tv.gate}"
                + (f" · esc={_tv.escalate_count}" if _tv.escalate_count else "")
                + (" · soft-stop" if _tv.soft_stop else "")
            )
        yield {"kind": "answer", "text": _answer}
        _data = _epic3_outcome_to_completion(
            _outcome,
            panel=panel,
            product_mode=product_mode,
            task_kind=task_kind,
            role_routing=_rr_payload,
        )
        # Soft-Stop / escalate may rewrite answer after outcome_to_completion
        if _tv is not None:
            _data["choices"] = [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": _answer},
                    "finish_reason": "stop",
                }
            ]
            _data["onestack"]["gate"] = _tv.gate
            _data["onestack"]["gate_reasons"] = list(_tv.gate_reasons)
            _data["onestack"]["escalate_count"] = int(_tv.escalate_count)
            _data["onestack"]["soft_stop"] = bool(_tv.soft_stop)
            _data["onestack"]["log_report"] = _tv.log_report
            if _tv.soft_stop_model:
                _data["onestack"]["soft_stop_model"] = _tv.soft_stop_model
            _data["onestack"]["answer_only"] = _answer
            if _data.get("_fusion_result") is not None:
                try:
                    _fr = _data["_fusion_result"]
                    _fr.answer = _answer
                    _fr.gate = _tv.gate
                    _fr.gate_reasons = list(_tv.gate_reasons)
                    _fr.escalate_count = int(_tv.escalate_count)
                    _fr.soft_stop = bool(_tv.soft_stop)
                    # TV branches already merged into _outcome before outcome_to_completion
                    # (FR-15 / NFR-7) — do NOT append again (double-bill bug)
                except Exception:  # noqa: BLE001
                    pass
        _data["usage"]["prompt_tokens"] = int(_data["usage"]["prompt_tokens"]) + clf_tokens_pt
        _data["usage"]["completion_tokens"] = (
            int(_data["usage"]["completion_tokens"]) + clf_tokens_ct
        )
        # TV tokens already in outcome_to_completion totals via _outcome.branches merge
        _data["usage"]["total_tokens"] = (
            _data["usage"]["prompt_tokens"] + _data["usage"]["completion_tokens"]
        )
        if clf_meta:
            _data["onestack"]["classifier"] = clf_meta
            if isinstance(clf_meta.get("clarify_state"), dict):
                _data["onestack"]["clarify_state"] = clf_meta["clarify_state"]
                _data["onestack"]["clarify_phase"] = clf_meta.get("clarify_phase")
                _data["onestack"]["clarifier_model"] = clf_meta.get("clarifier_model")
                _data["onestack"]["brief_approved"] = bool(
                    clf_meta.get("brief_approved")
                )
        _data["onestack"]["trace_id"] = _data["onestack"].get("trace_id") or trace_id
        yield {"kind": "done", "data": _data}
        return

    # ——— FAST ———
    if resolved == "fast" or judge_model is None:
        panel = [leader]
        if show_thinking:
            yield think("╭ быстрый ответ…")
        # Budgets own timeout; old hard 10s caused kill/FAST 502 under slow upstream.
        winner, partial = await _race_first(panel, messages)
        agents: list[dict[str, Any]] = []
        for p in partial:
            is_win = p.get("model") == winner.get("model") and bool(p.get("ok"))
            row = {
                "role": "panel",
                "title": "panel",
                "label": "panel",
                "model": p["model"],
                "latency_s": p["latency_s"],
                "prompt_tokens": p["prompt_tokens"],
                "completion_tokens": p["completion_tokens"],
                "preview": (p.get("text") or p.get("error") or "")[:280],
                "ok": p["ok"],
                "winner": is_win,
                "leader": p.get("model") == leader,
            }
            if p.get("billable_state"):
                row["billable_state"] = p["billable_state"]
            agents.append(row)

        answer = (winner.get("text") or "").strip()
        if not answer:
            answer = "Привет! На связи. Напиши задачу — отвечу."
        if show_thinking:
            lat = winner.get("latency_s")
            try:
                lat_s = f"{float(lat):.1f}с" if lat is not None else ""
            except (TypeError, ValueError):
                lat_s = ""
            yield think(f"│ ✓ готово" + (f" · {lat_s}" if lat_s else ""))
            yield think(_think_frame_close())
            yield think("")
        _pol = policy_path_serving
        if isinstance(clf_meta, dict):
            _pol = clf_meta.get("policy_path") or clf_meta.get("path") or _pol
        # Epic 5 Layer A on FAST when Studio workspace+test requested
        _fast_tests_failed = None
        try:
            import asyncio as _aio_la_fast

            from app.fusion.test_executor import (
                executor_signal_for_gate as _la_signal_fast,
                run_layer_a_for_request,
            )

            _z_fast = zeus if isinstance(zeus, dict) else {}
            _ex_fast = await _aio_la_fast.to_thread(run_layer_a_for_request, _z_fast)
            _fast_tests_failed = _la_signal_fast(_ex_fast)
            if isinstance(clf_meta, dict):
                clf_meta["layer_a"] = {
                    "skipped": _ex_fast.skipped,
                    "reason": _ex_fast.reason,
                    "exit_code": _ex_fast.exit_code,
                    "tests_failed": _ex_fast.tests_failed,
                }
        except Exception:  # noqa: BLE001
            _fast_tests_failed = None

        # Epic 2 light verify on FAST (kill/legacy): Log+Gate; no Mini required
        _fast_tv = None
        try:
            from app.fusion.verify import run_trusted_verify_loop

            _kill_fast = bool(
                isinstance(zeus, dict) and zeus.get("kill_switch")
            ) or "kill_switch" in (routed_by or "").lower()
            _legacy_fast = (routed_by or "") in (
                "forced_fast",
                "legacy_fast_alias",
                "kill_switch",
            )
            _fast_tv = await run_trusted_verify_loop(
                answer=answer,
                user_q=user_q,
                messages=messages,
                panel=panel,
                models_by_role=dict((clf_meta or {}).get("models_by_role") or {}),
                curator_model=(clf_meta or {}).get("curator_model") or leader,
                early_exit=None,
                routed_by=routed_by,
                branches=[],
                disaster=False,
                soft_stop_already=False,
                allow_green_without_mini=_kill_fast or _legacy_fast,
                max_escalate=0 if _kill_fast else 2,
                candidate_answers=[(str(leader or "leader"), answer)],
                tests_failed=_fast_tests_failed,
            )
            answer = _fast_tv.answer
        except Exception:  # noqa: BLE001 — fail closed
            from app.fusion.verify import append_soft_stop_red_line

            answer = append_soft_stop_red_line(answer)
            _fast_tv = type(
                "TV",
                (),
                {
                    "answer": answer,
                    "gate": "RED",
                    "gate_reasons": ["verify_loop_failed"],
                    "escalate_count": 0,
                    "soft_stop": True,
                    "log_report": "N/A",
                    "soft_stop_model": leader,
                },
            )()
        yield {"kind": "answer", "text": answer}
        data = _pack_completion(
            answer=answer,
            panel=panel,
            judge_model=None,
            agents=agents,
            mode="fast",
            total_pt=int(winner.get("prompt_tokens") or 0) + clf_tokens_pt,
            total_ct=int(winner.get("completion_tokens") or 0) + clf_tokens_ct,
            visible=answer,
            routed_by=routed_by,
            product_mode=product_mode,
            leader=leader,
            task_kind=task_kind,
            classifier=clf_meta,
            policy_path=str(_pol) if _pol else None,
            serving_path=serving_path,
            trace_id=trace_id,
        )
        if _fast_tv is not None and isinstance(data.get("onestack"), dict):
            data["onestack"]["gate"] = _fast_tv.gate
            data["onestack"]["gate_reasons"] = list(_fast_tv.gate_reasons)
            data["onestack"]["escalate_count"] = int(_fast_tv.escalate_count)
            data["onestack"]["soft_stop"] = bool(_fast_tv.soft_stop)
            data["onestack"]["log_report"] = _fast_tv.log_report
            if _fast_tv.soft_stop_model:
                data["onestack"]["soft_stop_model"] = _fast_tv.soft_stop_model
            for k in (
                "pipeline",
                "curator_model",
                "role_table",
                "roles",
                "models_by_role",
                "size",
                "second_signal",
                "task_kind",
            ):
                if clf_meta and k in clf_meta and k not in data["onestack"]:
                    data["onestack"][k] = clf_meta[k]
            # FR-15 / NFR-7: bill TV (mini/log/judge_fix) on FAST path
            for _vb in getattr(_fast_tv, "branches", None) or []:
                data["usage"]["prompt_tokens"] = int(data["usage"]["prompt_tokens"]) + int(
                    getattr(_vb, "prompt_tokens", 0) or 0
                )
                data["usage"]["completion_tokens"] = int(
                    data["usage"]["completion_tokens"]
                ) + int(getattr(_vb, "completion_tokens", 0) or 0)
            data["usage"]["total_tokens"] = (
                int(data["usage"]["prompt_tokens"])
                + int(data["usage"]["completion_tokens"])
            )
            if data.get("_fusion_result") is not None:
                try:
                    _ffr = data["_fusion_result"]
                    _ffr.gate = _fast_tv.gate
                    _ffr.gate_reasons = list(_fast_tv.gate_reasons)
                    _ffr.escalate_count = int(_fast_tv.escalate_count)
                    _ffr.soft_stop = bool(_fast_tv.soft_stop)
                    _ffr.answer = answer
                    if _fast_tv.branches:
                        _ffr.branches = list(_ffr.branches or []) + list(
                            _fast_tv.branches
                        )
                except Exception:  # noqa: BLE001
                    pass
        yield {"kind": "done", "data": data}
        return

    # ——— FULL ———
    # Leader = full Cursor context; satellites = short brief (не ×3 токены)
    sat_messages = _satellite_messages(messages, user_q)
    n_panel = len(panel)
    if show_thinking:
        yield think(_think_frame_open(n_panel))

    tasks = [
        asyncio.create_task(
            _panel_one(m, messages if m == leader else sat_messages)
        )
        for m in panel
    ]
    panel_results: list[dict[str, Any]] = [None] * len(panel)  # type: ignore[list-item]
    ready_n = 0
    pending = {t: i for i, t in enumerate(tasks)}
    while pending:
        done, _ = await asyncio.wait(pending.keys(), return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            i = pending.pop(t)
            try:
                r = t.result()
            except Exception as e:  # noqa: BLE001
                r = {
                    "model": panel[i],
                    "ok": False,
                    "text": "",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "latency_s": 0,
                    "error": str(e)[:400],
                }
            panel_results[i] = r
            ready_n += 1
            if show_thinking:
                labels: list[str] = []
                last_lat: float | None = None
                for j, pr in enumerate(panel_results):
                    if pr is None:
                        continue
                    lab = _short_label(j)
                    ok_j = bool(pr.get("ok") and (pr.get("text") or "").strip())
                    labels.append(f"{lab}✓" if ok_j else f"{lab}✗")
                    if j == i:
                        try:
                            last_lat = float(pr.get("latency_s") or 0)
                        except (TypeError, ValueError):
                            last_lat = None
                yield think(_think_branch(ready_n, n_panel, labels, last_lat))

    ok_parts = [p for p in panel_results if p and p.get("ok") and (p.get("text") or "").strip()]
    if not ok_parts:
        errors = "; ".join(
            f"{_short_label(i)}: {(p or {}).get('error') or 'empty'}"
            for i, p in enumerate(panel_results)
        )
        raise HTTPException(502, f"Fusion: все ветки упали ({errors})")

    agents = []
    total_pt = 0
    total_ct = 0
    for i, p in enumerate(panel_results):
        if not p:
            continue
        agents.append(
            {
                "role": "panel",
                "title": _variant_label(i),
                "label": _short_label(i),
                "model": p["model"],
                "latency_s": p["latency_s"],
                "prompt_tokens": p["prompt_tokens"],
                "completion_tokens": p["completion_tokens"],
                "preview": (p.get("text") or p.get("error") or "")[:280],
                "ok": p["ok"],
                "leader": p.get("model") == leader,
            }
        )
        total_pt += int(p["prompt_tokens"] or 0)
        total_ct += int(p["completion_tokens"] or 0)

    if len(ok_parts) == 1:
        if show_thinking:
            yield think(_think_frame_close())
            yield think("")
        answer = (ok_parts[0].get("text") or "").strip()
        yield {"kind": "answer", "text": answer}
        _pol = policy_path_serving
        if isinstance(clf_meta, dict):
            _pol = clf_meta.get("policy_path") or clf_meta.get("path") or _pol
        yield {
            "kind": "done",
            "data": _pack_completion(
                answer=answer,
                panel=panel,
                judge_model=None,
                agents=agents,
                mode="full-skip-judge",
                total_pt=total_pt + clf_tokens_pt,
                total_ct=total_ct + clf_tokens_ct,
                visible=answer,
                routed_by=routed_by,
                product_mode=product_mode,
                leader=leader,
                task_kind=task_kind,
                classifier=clf_meta,
                policy_path=str(_pol) if _pol else None,
                serving_path=serving_path,
                trace_id=trace_id,
            ),
        }
        return

    if show_thinking:
        yield think(_think_synth())

    # Anonymize for judge; brief user_q (не весь Cursor history ×3)
    blocks = []
    for i, p in enumerate(panel_results):
        if not p or not p.get("ok") or not (p.get("text") or "").strip():
            continue
        # Leader answer gets more budget — it's the strongest signal
        budget = 10000 if p.get("model") == leader else 6000
        blocks.append(f"### {_variant_label(i)}\n{p['text'][:budget]}")
    judge_user = (
        f"Запрос пользователя:\n{_judge_user_brief(user_q)}\n\n"
        f"Независимые варианты ({len(ok_parts)}; A = голова панели):\n\n"
        + "\n\n".join(blocks)
    )
    judge_messages = [
        {"role": "system", "content": _JUDGE_SYSTEM},
        {"role": "user", "content": judge_user},
    ]

    t0 = time.perf_counter()
    assert judge_model is not None
    judge_data = await upstream.chat_completions(
        model=judge_model, messages=judge_messages, stream=False
    )
    final = upstream.extract_text(judge_data)
    j_pt, j_ct = upstream.extract_usage(judge_data)
    judge_lat = round(time.perf_counter() - t0, 3)

    answer = final.strip()
    for marker in ("## Ответ", "## Final", "## Финал"):
        if marker in final:
            answer = final.split(marker, 1)[1].strip() or final
            break

    agents.append(
        {
            "role": "judge",
            "title": "synth",
            "label": "synth",
            "model": judge_model,
            "latency_s": judge_lat,
            "prompt_tokens": j_pt,
            "completion_tokens": j_ct,
            "preview": (answer or "")[:280],
            "ok": True,
        }
    )
    total_pt += j_pt
    total_ct += j_ct

    if show_thinking:
        yield think(f"│ ✓ готово · {judge_lat:.1f}с")
        yield think(_think_frame_close())
        yield think("")

    yield {"kind": "answer", "text": answer}
    _pol = policy_path_serving
    if isinstance(clf_meta, dict):
        _pol = clf_meta.get("policy_path") or clf_meta.get("path") or _pol
    yield {
        "kind": "done",
        "data": _pack_completion(
            answer=answer,
            panel=panel,
            judge_model=judge_model,
            agents=agents,
            mode="full",
            total_pt=total_pt + clf_tokens_pt,
            total_ct=total_ct + clf_tokens_ct,
            visible=answer,
            routed_by=routed_by,
            product_mode=product_mode,
            leader=leader,
            task_kind=task_kind,
            classifier=clf_meta,
            policy_path=str(_pol) if _pol else None,
            serving_path=serving_path,
            trace_id=trace_id,
        ),
    }


async def run_fusion(
    *,
    messages: list[dict[str, Any]],
    user: Any | None = None,
    models: list[str] | None = None,
    judge: str | None = None,
    mode: str | None = None,
    model_id: str | None = None,
    zeus: dict[str, Any] | None = None,
    show_thinking: bool | None = None,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] | None = None
    async for ev in iter_fusion(
        messages=messages,
        user=user,
        models=models,
        judge=judge,
        mode=mode,
        model_id=model_id,
        zeus=zeus,
        cancel_event=cancel_event,
        show_thinking=show_thinking,
    ):
        if ev.get("kind") == "done":
            data = ev["data"]
    if not data:
        raise HTTPException(502, "Fusion: пустой результат")
    return data
