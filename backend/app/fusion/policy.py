"""Path policy: classify, Effort, Path table, MoR tip, clamps (Epic 2 / FR-28).

Order (AD-3): classify → Effort=+1 → first-match table → MoR tip 0|1 → mode clamp.
``fusion/*`` must not import ``routers.*``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from .types import ComplexityBand, PathName

EffortLevel = Literal["low", "med", "high"]
ProductMode = Literal["simple", "power", "custom"]
ClassifyPhase = Literal[
    "chat", "ui", "docs", "test", "implement", "debug", "plan", "review"
]

LEXICON_ID = "lexicon_v1"
DESIGN_LEXICON_RE = re.compile(
    r"(?i)("
    r"спроектируй|спроектировать|architecture|design the system|"
    r"ревью\s*PR|code review|спроектируй модуль"
    r")"
)

_TRACEBACK_RE = re.compile(
    r"(?i)(traceback|exception|error:|typeerror|referenceerror|syntaxerror|"
    r"ModuleNotFoundError|ENOENT|undefined is not|cannot find module)"
)
_CODE_FENCE_RE = re.compile(r"```|^\s{4}\S", re.MULTILINE)
_CHITCHAT_RE = re.compile(
    r"(?i)^\s*("
    r"привет|прив|салам|хай|хелло|hello|hi|yo|"
    r"здаров[аоуы]?|здоров[аоуы]?|добрый\s+(день|вечер|утро)|"
    r"как дела|что умеешь|кто ты|"
    r"спасибо|спс|ок|ага|лан|ку|йо|hey|thanks|thx|норм|нормально|пока|бай"
    r")[\s!.?]*$"
)
_UI_RE = re.compile(
    r"(?i)(css|html|ui|ux|кнопк|цвет|стиль|вёрстк|верстк|layout|tailwind|"
    r"компонент|анимац|pixel|figma|лендинг|landing|hero|"
    r"поменяй\s+(цвет|размер|шрифт|отступ)|change\s+(the\s+)?(color|size|font))"
)
_PLAN_RE = re.compile(
    r"(?i)(архитект|спроектир|design system|ddd|микросервис|"
    r"architecture|migrate|redesign|план\s+модул)"
)
_REVIEW_RE = re.compile(
    r"(?i)(ревью|review|проверь код|найди баг|audit|security|уязвим|code review)"
)
_DEBUG_RE = re.compile(
    r"(?i)(debug|traceback|stacktrace|почему падает|fix this bug|исправь ошибк)"
)
_TEST_RE = re.compile(r"(?i)(тест|pytest|unit test|e2e|покрой тест|coverage)")
_DOCS_RE = re.compile(r"(?i)(документац|readme|docstring|напиши docs|api docs)")
_IMPLEMENT_RE = re.compile(
    r"(?i)(напиш|сделай|реализ|почин|исправ|рефактор|код|функц|класс|api|"
    r"implement|fix|build|refactor|write code|добавь|кнопк)"
)
# Role Routing second_signal closed set (AD-22) — any one
_SECOND_ARCH_MIGRATE_RE = re.compile(
    r"(?i)(архитект|спроектир|architecture|migrate|миграц|redesign|"
    r"design\s+the\s+system|микросервис)"
)
_SECOND_LANDING_RE = re.compile(
    r"(?i)(лендинг|landing\s+(page|site)|сайт\s+с\s+нуля|с\s+нуля\s+(сайт|лендинг)|"
    r"landing-from-scratch|make\s+a\s+landing)"
)
_SECOND_MULTIFILE_RE = re.compile(
    r"(?i)(нескольк\w*\s+файл|multi[- ]?file|across\s+files|"
    r"в\s+разных\s+файл|пакет\s+файл|\.tsx?.+\.tsx?)"
)
_SECOND_EXPLICIT_HEAVY_RE = re.compile(
    r"(?i)(полная\s+фича|large\s+feature|heavy\s+task|сложн\w+\s+фич|"
    r"end[- ]to[- ]end\s+feature|весь\s+модуль)"
)
_PHASE_TO_TASK_KIND: dict[str, str] = {
    "chat": "light",
    "ui": "ui",
    "docs": "light",
    "test": "tests",
    "implement": "code",
    "debug": "code",
    "plan": "architecture",
    "review": "review",
}

PATH_ORDER: tuple[PathName, ...] = ("FAST", "CASCADE", "RACE", "FULL")
COMPLEXITY_ORDER: tuple[ComplexityBand, ...] = ("light", "med", "heavy")
MOR_B: dict[ComplexityBand, float] = {"light": 0.35, "med": 0.55, "heavy": 0.80}

# Ops-ordered Leader failover lists (FR-15). Empty → disaster.
LEADER_FAILOVER: dict[ProductMode, tuple[str, ...]] = {
    "simple": ("deepseek-v4-flash", "gemini-3-pro", "claude-haiku-4-5"),
    "power": ("claude-opus-4-8", "deepseek-v4-pro", "gemini-3.1-pro"),
    "custom": (),  # filled from selected ready models at resolve time
}

CLOSED_ROUTED_BY = frozenset(
    {
        "kill_switch",
        "forced_fast",
        "forced_full",
        "legacy_fast_alias",
        "legacy_full_alias",
        "mode_ignored",
        "mode_simple_clamp",
        "classify_fallback_cascade",
        "policy_heavy_full",
        "policy_chat_light",
        "policy_light_cascade",
        "policy_race_borderline",
        "policy_default_cascade",
        "policy_design_lexicon_full",
        "cascade_escalate_stronger",
        "cascade_escalate_full",
        "policy_cascade_mini_pass",
        "cascade_disaster",
        "race_escalate_full",
        "race_soft_stop",
        "race_disaster",
        # MoR tip codes (generated as mor_escalate_<from>_to_<to>)
        "mor_escalate_fast_to_cascade",
        "mor_escalate_cascade_to_race",
        "mor_escalate_race_to_full",
    }
)

_FORCED_PATH_MODES = frozenset({"fast", "full"})
_PRODUCT_MODES = frozenset({"simple", "power", "custom"})
_PRODUCT_ALIASES = {
    "lite": "simple",
    "easy": "simple",
    "cheap": "simple",
    "auto": "power",
    "smart": "power",
    "мощный": "power",
    "powerful": "power",
    "pick": "custom",
    "manual": "custom",
    "свой": "custom",
}
_LEGACY_FAST_IDS = frozenset({"zeus/fusion-fast", "fusion-fast"})
_LEGACY_FULL_IDS = frozenset({"zeus/fusion-full", "fusion-full"})
_TASK_TO_PHASE: dict[str, ClassifyPhase] = {
    "light": "chat",
    "ui": "ui",
    "tests": "test",
    "test": "test",
    "review": "review",
    "architecture": "plan",
    "code": "implement",
    "general": "implement",
    "chat": "chat",
    "docs": "docs",
    "debug": "debug",
    "plan": "plan",
    "implement": "implement",
}


@dataclass
class ClassifyResult:
    classify_phase: ClassifyPhase
    complexity_band: ComplexityBand
    confidence: float
    design_lexicon: bool = False
    failed: bool = False
    source: str = "regex"
    meta: dict[str, Any] = field(default_factory=dict)
    # Role Routing (Epic 1 / FR-1)
    size: Literal["small", "large"] = "small"
    second_signal: bool = False
    task_kind: str = "general"


def detect_second_signal(user_q: str, *, messages: list[dict[str, Any]] | None = None) -> bool:
    """Closed set (AD-22): architecture/migrate · multi-file · landing · explicit heavy."""
    q = user_q or ""
    if _SECOND_ARCH_MIGRATE_RE.search(q) or DESIGN_LEXICON_RE.search(q):
        return True
    if _SECOND_LANDING_RE.search(q):
        return True
    if _SECOND_MULTIFILE_RE.search(q):
        return True
    if _SECOND_EXPLICIT_HEAVY_RE.search(q):
        return True
    # Multi-file hint from message attachments / many path-like tokens
    if messages:
        joined = " ".join(str(m.get("content") or "") for m in messages[-6:])
        paths = re.findall(r"[\w./-]+\.(?:py|ts|tsx|js|jsx|go|rs|java)\b", joined)
        if len(set(paths)) >= 3:
            return True
    return False


def derive_size_and_task(
    *,
    phase: ClassifyPhase,
    band: ComplexityBand,
    confidence: float,
    user_q: str,
    second_signal: bool,
    context_chars: int = 0,
) -> tuple[Literal["small", "large"], str]:
    """size + task_kind. confidence<0.6 may label large but is NOT second_signal."""
    task_kind = _PHASE_TO_TASK_KIND.get(phase, "general")
    large = False
    if second_signal:
        large = True
    if band == "heavy":
        large = True
    if confidence < 0.6:
        large = True  # risk label only
    if context_chars > 4000 and phase not in ("chat",):
        large = True
    q = (user_q or "").strip()
    if phase == "chat" and (not q or _CHITCHAT_RE.match(q)):
        large = False
    if phase == "ui" and len(q) < 160 and not second_signal and confidence >= 0.6:
        large = False
    size: Literal["small", "large"] = "large" if large else "small"
    return size, task_kind


@dataclass
class PolicyDecision:
    path: PathName
    policy_path: PathName
    routed_by: str
    phase: ClassifyPhase  # classify_phase (sticky never feeds this)
    policy_phase: ClassifyPhase  # may be plan override for lexicon
    complexity: ComplexityBand  # post-Effort
    confidence: float
    product_mode: ProductMode
    effort: EffortLevel
    design_lexicon: bool = False
    interactive: bool = False
    tip_escalate: int = 0
    mor_scores: dict[str, float] = field(default_factory=dict)
    mode_ignored: bool = False
    thinking_passthrough: Any | None = None
    classify_failed: bool = False
    reason: str = ""


@dataclass
class CascadeEscalateDecision:
    """FR-8 escalate map after Mini-Verifier fail."""

    action: Literal["stronger_leader", "full", "stop_disaster"]
    routed_by: str
    allow_full: bool


@dataclass
class CustomPanelPlan:
    """FR-34 custom panel shape."""

    path_hint: PathName  # FAST-equivalent for 1 model
    models: list[str]  # ready models only, ≤3
    roles: list[str]  # A / A,B / A,B,C


def epic2_policy_enabled() -> bool:
    """Epic2 Path policy serving flag.

    Default **on** (AC Done). Opt out: ``ZEUS_FUSION_EPIC2_POLICY=0|false|off``.
    """
    raw = (os.environ.get("ZEUS_FUSION_EPIC2_POLICY") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def bump_complexity(band: ComplexityBand, effort: EffortLevel) -> ComplexityBand:
    """Effort=high → +1 band (cap heavy). low|med → as-is (FR-5)."""
    if effort != "high":
        return band
    idx = COMPLEXITY_ORDER.index(band)
    return COMPLEXITY_ORDER[min(idx + 1, len(COMPLEXITY_ORDER) - 1)]


def escalate_one(path: PathName) -> PathName:
    idx = PATH_ORDER.index(path)
    return PATH_ORDER[min(idx + 1, len(PATH_ORDER) - 1)]


def path_to_legacy_stack(path: PathName | str) -> str:
    """Map Path → brownfield fast|full until Epic 3 executors own Paths."""
    p = str(path).upper()
    if p in ("FAST", "CASCADE"):
        return "fast"
    return "full"


def detect_design_lexicon(text: str) -> bool:
    return bool(DESIGN_LEXICON_RE.search(text or ""))


def normalize_effort(raw: Any) -> EffortLevel:
    m = str(raw or "med").strip().lower()
    if m in ("low", "med", "high"):
        return m  # type: ignore[return-value]
    if m in ("l", "0", "min"):
        return "low"
    if m in ("h", "2", "max"):
        return "high"
    return "med"


def normalize_product_mode_policy(raw: Any) -> ProductMode | None:
    m = str(raw or "").strip().lower()
    if m in _PRODUCT_MODES:
        return m  # type: ignore[return-value]
    return _PRODUCT_ALIASES.get(m)  # type: ignore[return-value]


def resolve_zeus_mode_fields(
    *,
    model_id: str | None,
    zeus: dict[str, Any] | None,
    prefs_product_mode: ProductMode | None = None,
) -> tuple[ProductMode, str | None, str | None, bool]:
    """Return (product_mode, forced_path_code|None, legacy_code|None, mode_ignored).

    Forced Path codes: forced_fast / forced_full.
    Legacy codes: legacy_fast_alias / legacy_full_alias.
    Unknown zeus.mode → mode_ignored (FR-37); product mode falls back to prefs/default.
    """
    mid = (model_id or "").strip().lower()
    z = zeus if isinstance(zeus, dict) else {}
    raw_mode = str(z.get("mode") or "").strip().lower()
    mode_ignored = False

    if mid in _LEGACY_FAST_IDS:
        return "simple", None, "legacy_fast_alias", False
    if mid in _LEGACY_FULL_IDS:
        return "power", None, "legacy_full_alias", False

    if raw_mode in _FORCED_PATH_MODES:
        prod = prefs_product_mode or ("simple" if raw_mode == "fast" else "power")
        code = "forced_fast" if raw_mode == "fast" else "forced_full"
        return prod, code, None, False

    prod = normalize_product_mode_policy(raw_mode)
    if raw_mode and prod is None and raw_mode not in _FORCED_PATH_MODES:
        # unknown token — ignore for Path; keep prefs
        mode_ignored = True
        prod = None

    if prod is None:
        prod = prefs_product_mode or "power"
    return prod, None, None, mode_ignored


def thinking_passthrough(zeus: dict[str, Any] | None) -> Any | None:
    """FR-37: zeus.thinking passthrough hint or ignore (no Path effect)."""
    if not isinstance(zeus, dict) or "thinking" not in zeus:
        return None
    return zeus.get("thinking")


def classify_local(
    user_q: str,
    *,
    messages: list[dict[str, Any]] | None = None,
    force_fail: bool = False,
) -> ClassifyResult:
    """Regex/heuristic classify → phase + complexity_band + confidence (FR-4)."""
    if force_fail:
        return ClassifyResult(
            classify_phase="implement",
            complexity_band="med",
            confidence=0.0,
            failed=True,
            source="fail",
            size="small",
            second_signal=False,
            task_kind="general",
        )

    q = (user_q or "").strip()
    has_trace = bool(_TRACEBACK_RE.search(q))
    has_code = bool(_CODE_FENCE_RE.search(q))
    design = detect_design_lexicon(q)
    last_assistant = ""
    if messages:
        for m in messages:
            if m.get("role") == "assistant":
                last_assistant = str(m.get("content") or "")

    # Phase
    phase: ClassifyPhase = "implement"
    if not q or _CHITCHAT_RE.match(q):
        phase = "chat"
    elif has_trace or _DEBUG_RE.search(q):
        phase = "debug"
    elif design or _PLAN_RE.search(q):
        phase = "plan"
    elif _REVIEW_RE.search(q):
        phase = "review"
    elif _TEST_RE.search(q):
        phase = "test"
    elif _DOCS_RE.search(q):
        phase = "docs"
    elif _UI_RE.search(q) and not _PLAN_RE.search(q):
        phase = "ui"
    elif _IMPLEMENT_RE.search(q) or has_code:
        phase = "implement"
    elif len(q) <= 80:
        phase = "chat"

    # Complexity
    band: ComplexityBand = "med"
    conf = 0.7
    if phase == "chat" and (not q or _CHITCHAT_RE.match(q)):
        band, conf = "light", 0.95
    elif phase == "ui" and len(q) < 160 and not has_trace:
        band, conf = "light", 0.85
    elif phase in ("plan", "review") or design:
        band, conf = "heavy", 0.85
    elif phase == "debug" or has_trace:
        band, conf = "med", 0.8
        if has_trace and len(q) > 400:
            band = "heavy"
    elif phase == "implement" and len(q) < 120 and not has_code:
        band, conf = "light", 0.75
    elif len(q) >= 900 or (has_code and len(q) > 600):
        band, conf = "heavy", 0.7
    else:
        band, conf = "med", 0.65

    if last_assistant and len(q) < 280 and phase == "implement":
        conf = min(conf, 0.65)

    ctx_chars = len(q)
    if messages:
        ctx_chars = sum(len(str(m.get("content") or "")) for m in messages)
    second = detect_second_signal(q, messages=messages)
    size, task_kind = derive_size_and_task(
        phase=phase,
        band=band,
        confidence=clamp01(conf),
        user_q=q,
        second_signal=second,
        context_chars=ctx_chars,
    )

    return ClassifyResult(
        classify_phase=phase,
        complexity_band=band,
        confidence=clamp01(conf),
        design_lexicon=design,
        failed=False,
        source="regex",
        meta={
            "user_chars": len(q),
            "has_traceback": has_trace,
            "has_code": has_code,
            "context_chars": ctx_chars,
        },
        size=size,
        second_signal=second,
        task_kind=task_kind,
    )


def classify_from_legacy(
    clf_meta: dict[str, Any] | None,
    user_q: str,
    *,
    messages: list[dict[str, Any]] | None = None,
) -> ClassifyResult:
    """Bridge brownfield classify_smart {stack,task,confidence} → FR-4 fields."""
    if clf_meta is None:
        return classify_local(user_q, messages=messages)

    # Explicit fail marker from callers / timeouts
    if clf_meta.get("failed") or clf_meta.get("classify_failed"):
        out = classify_local(user_q, messages=messages, force_fail=True)
        out.meta["legacy"] = clf_meta
        return out

    task = str(clf_meta.get("task") or "general").strip().lower()
    phase = _TASK_TO_PHASE.get(task, "implement")
    conf = clamp01(float(clf_meta.get("confidence") or 0.5))
    design = detect_design_lexicon(user_q)
    if design and phase not in ("plan", "review"):
        # lexicon may keep classify phase; Path overrides separately
        pass

    stack = str(clf_meta.get("stack") or "").lower()
    q = (user_q or "").strip()
    if phase == "chat" or task == "light":
        band: ComplexityBand = "light"
    elif task == "ui" and len(q) < 160:
        band = "light"
    elif task in ("architecture", "review") or design:
        band = "heavy"
    elif stack == "full" and len(q) >= 400:
        band = "heavy" if task in ("architecture", "review") else "med"
    elif stack == "fast":
        band = "light"
    else:
        band = "med"

    if _TRACEBACK_RE.search(q):
        phase = "debug"
        band = "med" if band == "light" else band

    ctx_chars = len(q)
    if messages:
        ctx_chars = sum(len(str(m.get("content") or "")) for m in messages)
    second = detect_second_signal(q, messages=messages) or design
    size, task_kind = derive_size_and_task(
        phase=phase,  # type: ignore[arg-type]
        band=band,
        confidence=conf,
        user_q=q,
        second_signal=second,
        context_chars=ctx_chars,
    )
    # Prefer legacy task label when it maps cleanly
    if task in ("light", "ui", "tests", "review", "architecture", "code", "general"):
        task_kind = task

    return ClassifyResult(
        classify_phase=phase,  # type: ignore[arg-type]
        complexity_band=band,
        confidence=conf,
        design_lexicon=design,
        failed=False,
        source=str(clf_meta.get("source") or "legacy"),
        meta={"legacy_task": task, "legacy_stack": stack, "context_chars": ctx_chars},
        size=size,
        second_signal=second,
        task_kind=task_kind,
    )


def is_follow_up_short(
    *,
    user_q: str,
    has_last_assistant: bool,
    has_new_traceback: bool,
) -> bool:
    return bool(
        has_last_assistant
        and len((user_q or "").strip()) < 280
        and not has_new_traceback
    )


def compute_interactive(
    *,
    policy_phase: ClassifyPhase,
    complexity: ComplexityBand,
    design_lexicon: bool,
    kill_switch: bool,
    user_q: str,
    has_last_assistant: bool,
    has_new_traceback: bool,
    stream: bool,
) -> bool:
    """Interactive hint (FR-28). All gates must hold."""
    if kill_switch or design_lexicon:
        return False
    if policy_phase in ("plan", "review", "debug") or complexity == "heavy":
        return False
    if policy_phase not in ("chat", "ui", "implement", "test"):
        return False
    if complexity not in ("light", "med"):
        return False
    follow = is_follow_up_short(
        user_q=user_q,
        has_last_assistant=has_last_assistant,
        has_new_traceback=has_new_traceback,
    )
    stream_short = bool(stream and len((user_q or "").strip()) < 400)
    return follow or stream_short


def mor_scores(
    *,
    complexity: ComplexityBand,
    effort: EffortLevel,
    confidence: float,
    interactive: bool,
) -> dict[str, float]:
    s_quality = clamp01(
        MOR_B[complexity]
        + (0.15 if effort == "high" else 0.0)
        + 0.20 * (1.0 - clamp01(confidence))
    )
    s_cost = clamp01(1.0 - s_quality)
    s_latency = 0.70 if interactive else 0.40
    return {
        "s_quality": s_quality,
        "s_cost": s_cost,
        "s_latency": s_latency,
    }


def mor_tip_escalate(
    scores: dict[str, float],
    *,
    policy_path: PathName,
    kill_switch: bool,
    forced_or_legacy: bool,
) -> int:
    """Return 0|1. Tip never demotes.

    MVP freeze (Eval F14): tip only FAST→CASCADE. Full PRD ladder tip
    (CASCADE→RACE…) deferred — RACE stays table row / Epic3 ownership.
    Env ``ZEUS_FUSION_MOR_FULL_LADDER=1`` enables tip for any path≠FULL.
    """
    if kill_switch or forced_or_legacy or policy_path == "FULL":
        return 0
    full_ladder = (os.environ.get("ZEUS_FUSION_MOR_FULL_LADDER") or "").strip().lower() in (
        "1",
        "true",
        "on",
        "yes",
    )
    if not full_ladder and policy_path != "FAST":
        return 0
    sq = float(scores.get("s_quality") or 0.0)
    sc = float(scores.get("s_cost") or 0.0)
    sl = float(scores.get("s_latency") or 0.0)
    # ties → quality > latency > cost
    dominant = "quality"
    best = sq
    if sl > best:
        dominant, best = "latency", sl
    if sc > best:
        dominant, best = "cost", sc
    if dominant == "quality" and sq >= 0.60:
        return 1
    return 0


def first_match_policy(
    *,
    kill_switch: bool,
    forced_code: str | None,
    legacy_code: str | None,
    design_lexicon: bool,
    policy_phase: ClassifyPhase,
    complexity: ComplexityBand,
    confidence: float,
    interactive: bool,
) -> tuple[PathName, str]:
    """FR-28 first-match table (MoR not inside)."""
    if kill_switch:
        return "FAST", "kill_switch"
    if forced_code == "forced_fast":
        return "FAST", "forced_fast"
    if forced_code == "forced_full":
        return "FULL", "forced_full"
    if legacy_code == "legacy_fast_alias":
        return "FAST", "legacy_fast_alias"
    if legacy_code == "legacy_full_alias":
        return "FULL", "legacy_full_alias"

    heavy_row = (
        design_lexicon
        or policy_phase in ("plan", "review")
        or complexity == "heavy"
        or (policy_phase == "debug" and complexity in ("med", "heavy"))
    )
    if heavy_row:
        code = "policy_design_lexicon_full" if design_lexicon else "policy_heavy_full"
        return "FULL", code

    if policy_phase == "chat" and complexity == "light" and confidence >= 0.70:
        return "FAST", "policy_chat_light"

    if (
        complexity == "light"
        and policy_phase in ("ui", "docs", "test", "implement")
        and confidence >= 0.60
    ):
        return "CASCADE", "policy_light_cascade"

    if (
        interactive
        and complexity in ("light", "med")
        and policy_phase in ("chat", "ui", "implement", "test")
        and confidence < 0.70
    ):
        return "RACE", "policy_race_borderline"

    return "CASCADE", "policy_default_cascade"


def apply_mode_clamp(
    path: PathName,
    *,
    product_mode: ProductMode,
    forced_or_legacy_full: bool,
    routed_by: str,
) -> tuple[PathName, str]:
    """simple: RACE/FULL → CASCADE unless forced/legacy full (FR-3)."""
    if product_mode != "simple":
        return path, routed_by
    if path in ("RACE", "FULL") and not forced_or_legacy_full:
        return "CASCADE", "mode_simple_clamp"
    return path, routed_by


def select_path_policy(
    *,
    classify: ClassifyResult,
    effort: EffortLevel = "med",
    product_mode: ProductMode = "power",
    kill_switch: bool = False,
    forced_code: str | None = None,
    legacy_code: str | None = None,
    mode_ignored: bool = False,
    user_q: str = "",
    has_last_assistant: bool = False,
    has_new_traceback: bool = False,
    stream: bool = False,
    thinking: Any | None = None,
) -> PolicyDecision:
    """Full AD-3 / FR-28 control flow → serving Path + closed routed_by."""
    if classify.failed:
        # FR-4/17: classify fail → CASCADE (Kill-Switch still wins)
        if kill_switch:
            return PolicyDecision(
                path="FAST",
                policy_path="FAST",
                routed_by="kill_switch",
                phase=classify.classify_phase,
                policy_phase=classify.classify_phase,
                complexity=bump_complexity(classify.complexity_band, effort),
                confidence=classify.confidence,
                product_mode=product_mode,
                effort=effort,
                design_lexicon=classify.design_lexicon,
                classify_failed=True,
                thinking_passthrough=thinking,
                mode_ignored=mode_ignored,
                reason="classify_failed+kill_switch",
            )
        return PolicyDecision(
            path="CASCADE",
            policy_path="CASCADE",
            routed_by="classify_fallback_cascade",
            phase=classify.classify_phase,
            policy_phase=classify.classify_phase,
            complexity=bump_complexity(classify.complexity_band, effort),
            confidence=classify.confidence,
            product_mode=product_mode,
            effort=effort,
            design_lexicon=classify.design_lexicon,
            classify_failed=True,
            thinking_passthrough=thinking,
            mode_ignored=mode_ignored,
            reason="classify_failed",
        )

    complexity = bump_complexity(classify.complexity_band, effort)
    classify_phase = classify.classify_phase
    design = classify.design_lexicon or detect_design_lexicon(user_q)

    # Path-only override: design_lexicon → policy_phase := plan
    policy_phase: ClassifyPhase = "plan" if design else classify_phase

    interactive = compute_interactive(
        policy_phase=policy_phase,
        complexity=complexity,
        design_lexicon=design,
        kill_switch=kill_switch,
        user_q=user_q,
        has_last_assistant=has_last_assistant,
        has_new_traceback=has_new_traceback,
        stream=stream,
    )

    policy_path, routed_by = first_match_policy(
        kill_switch=kill_switch,
        forced_code=forced_code,
        legacy_code=legacy_code,
        design_lexicon=design,
        policy_phase=policy_phase,
        complexity=complexity,
        confidence=classify.confidence,
        interactive=interactive,
    )

    forced_or_legacy = bool(forced_code or legacy_code)
    scores = mor_scores(
        complexity=complexity,
        effort=effort,
        confidence=classify.confidence,
        interactive=interactive,
    )
    tip = mor_tip_escalate(
        scores,
        policy_path=policy_path,
        kill_switch=kill_switch,
        forced_or_legacy=forced_or_legacy,
    )
    mor_path = escalate_one(policy_path) if tip else policy_path
    if tip and mor_path != policy_path:
        routed_by = f"mor_escalate_{policy_path.lower()}_to_{mor_path.lower()}"

    forced_or_legacy_full = (
        forced_code == "forced_full" or legacy_code == "legacy_full_alias"
    )
    serving, routed_by = apply_mode_clamp(
        mor_path,
        product_mode=product_mode,
        forced_or_legacy_full=forced_or_legacy_full,
        routed_by=routed_by,
    )

    # FR-37: unknown zeus.mode → mode_ignored as routed_by (Path still from table).
    if (
        mode_ignored
        and not kill_switch
        and not forced_or_legacy
        and str(routed_by).startswith("policy_")
    ):
        routed_by = "mode_ignored"

    return PolicyDecision(
        path=serving,
        policy_path=policy_path,
        routed_by=routed_by,
        phase=classify_phase,
        policy_phase=policy_phase,
        complexity=complexity,
        confidence=classify.confidence,
        product_mode=product_mode,
        effort=effort,
        design_lexicon=design,
        interactive=interactive,
        tip_escalate=tip,
        mor_scores=scores,
        mode_ignored=mode_ignored,
        thinking_passthrough=thinking,
        classify_failed=False,
        reason=f"lexicon={LEXICON_ID}",
    )


def resolve_request_policy(
    *,
    user_q: str,
    model_id: str | None = None,
    zeus: dict[str, Any] | None = None,
    messages: list[dict[str, Any]] | None = None,
    clf_meta: dict[str, Any] | None = None,
    classify_failed: bool = False,
    stream: bool = False,
    prefs_product_mode: ProductMode | None = None,
    prefs_effort: EffortLevel | None = None,
    prefs_kill_switch: bool | None = None,
) -> PolicyDecision:
    """High-level entry: prefs + zeus.* → PolicyDecision."""
    z = zeus if isinstance(zeus, dict) else {}
    prod, forced, legacy, ignored = resolve_zeus_mode_fields(
        model_id=model_id,
        zeus=z,
        prefs_product_mode=prefs_product_mode,
    )
    effort = normalize_effort(z.get("effort") if "effort" in z else prefs_effort)
    kill = bool(z.get("kill_switch") if "kill_switch" in z else (prefs_kill_switch or False))

    if classify_failed:
        classify = classify_local(user_q, messages=messages, force_fail=True)
    elif clf_meta is not None:
        classify = classify_from_legacy(clf_meta, user_q, messages=messages)
    else:
        classify = classify_local(user_q, messages=messages)

    has_assistant = False
    has_trace = bool(_TRACEBACK_RE.search(user_q or ""))
    if messages:
        for m in messages:
            if m.get("role") == "assistant" and str(m.get("content") or "").strip():
                has_assistant = True

    return select_path_policy(
        classify=classify,
        effort=effort,
        product_mode=prod,
        kill_switch=kill,
        forced_code=forced,
        legacy_code=legacy,
        mode_ignored=ignored,
        user_q=user_q,
        has_last_assistant=has_assistant,
        has_new_traceback=has_trace,
        stream=stream,
        thinking=thinking_passthrough(z),
    )


# —— CASCADE escalate + Leader failover (Story 2.3) ——


def cascade_escalate_action(
    *,
    kill_switch: bool,
    product_mode: ProductMode,
    complexity: ComplexityBand,
    phase: ClassifyPhase,
    stronger_already_tried: bool = False,
) -> CascadeEscalateDecision:
    """Deterministic FR-8 map after Mini-Verifier fail."""
    if kill_switch:
        return CascadeEscalateDecision(
            action="stronger_leader",
            routed_by="cascade_escalate_stronger",
            allow_full=False,
        )
    if product_mode == "simple":
        return CascadeEscalateDecision(
            action="stronger_leader",
            routed_by="cascade_escalate_stronger",
            allow_full=False,
        )
    if complexity == "heavy" or phase in ("plan", "review", "debug"):
        if product_mode in ("power", "custom"):
            return CascadeEscalateDecision(
                action="full",
                routed_by="cascade_escalate_full",
                allow_full=True,
            )
        return CascadeEscalateDecision(
            action="stronger_leader",
            routed_by="cascade_escalate_stronger",
            allow_full=False,
        )
    if complexity == "med" and product_mode in ("power", "custom"):
        if stronger_already_tried:
            return CascadeEscalateDecision(
                action="full",
                routed_by="cascade_escalate_full",
                allow_full=True,
            )
        return CascadeEscalateDecision(
            action="stronger_leader",
            routed_by="cascade_escalate_stronger",
            allow_full=True,
        )
    # light → stronger once → stop
    return CascadeEscalateDecision(
        action="stronger_leader",
        routed_by="cascade_escalate_stronger",
        allow_full=False,
    )


def next_leader_failover(
    current: str | None,
    *,
    product_mode: ProductMode,
    ready: list[str] | None = None,
    custom_order: list[str] | None = None,
) -> str | None:
    """Next ready model in ops-ordered failover list (FR-15). None → disaster."""
    if product_mode == "custom":
        order = list(custom_order or ready or [])
    else:
        order = list(LEADER_FAILOVER.get(product_mode) or ())
    if ready is not None:
        ready_set = {str(x) for x in ready}
        order = [m for m in order if m in ready_set]
    if not order:
        return None
    if not current:
        return order[0]
    try:
        idx = order.index(current)
    except ValueError:
        return order[0]
    if idx + 1 >= len(order):
        return None
    return order[idx + 1]


def leader_failover_chain(
    *,
    product_mode: ProductMode,
    ready: list[str] | None = None,
    custom_order: list[str] | None = None,
    start: str | None = None,
) -> list[str]:
    """Ordered ready Leaders from start (inclusive if ready)."""
    chain: list[str] = []
    cur = start
    if cur is None:
        cur = next_leader_failover(
            None,
            product_mode=product_mode,
            ready=ready,
            custom_order=custom_order,
        )
        if cur:
            chain.append(cur)
    else:
        # include start if ready
        if ready is None or cur in ready:
            chain.append(cur)
    seen = set(chain)
    while True:
        nxt = next_leader_failover(
            chain[-1] if chain else None,
            product_mode=product_mode,
            ready=ready,
            custom_order=custom_order,
        )
        if not nxt or nxt in seen:
            break
        chain.append(nxt)
        seen.add(nxt)
    return chain


# —— Custom panel rules (Story 2.4 / FR-34) ——


def resolve_custom_panel(
    selected: list[str] | None,
    *,
    ready: list[str] | None = None,
) -> CustomPanelPlan:
    """1→FAST-eq; 2→A+B; 3→A/B/C; dead models excluded."""
    ready_set = set(ready) if ready is not None else None
    models: list[str] = []
    for mid in selected or []:
        m = str(mid).strip()
        if not m:
            continue
        if ready_set is not None and m not in ready_set:
            continue
        if m not in models:
            models.append(m)
        if len(models) >= 3:
            break

    n = len(models)
    if n <= 1:
        return CustomPanelPlan(
            path_hint="FAST",
            models=models,
            roles=["A"] if models else [],
        )
    if n == 2:
        return CustomPanelPlan(path_hint="CASCADE", models=models, roles=["A", "B"])
    return CustomPanelPlan(path_hint="FULL", models=models[:3], roles=["A", "B", "C"])


def soft_resolve_for_monolith(
    *,
    user_q: str,
    model_id: str | None,
    zeus: dict[str, Any] | None,
    messages: list[dict[str, Any]],
    clf_meta: dict[str, Any] | None,
    classify_failed: bool = False,
    stream: bool = True,
) -> PolicyDecision | None:
    """Thin hook helper. Returns None when flag off or decision incomplete.

    AD-9: after policy computes ``candidate_path``, Shadow serves baseline while
    logging the candidate; canary cohort may take the candidate.
    """
    if not epic2_policy_enabled():
        return None
    try:
        decision = resolve_request_policy(
            user_q=user_q,
            model_id=model_id,
            zeus=zeus,
            messages=messages,
            clf_meta=clf_meta,
            classify_failed=classify_failed,
            stream=stream,
        )
    except Exception:  # noqa: BLE001 — soft fallback to brownfield
        return None
    if not decision.path or not decision.routed_by:
        return None

    # AD-9 shadow / canary / kill serving clamp (never invent a new policy row)
    try:
        from app.fusion.metrics import apply_serving_flags, legacy_baseline_path

        stack_hint = (
            str(clf_meta.get("stack"))
            if isinstance(clf_meta, dict) and clf_meta.get("stack")
            else path_to_legacy_stack(decision.path)
        )
        baseline = legacy_baseline_path(stack_hint)
        serving, policy_path, rb = apply_serving_flags(
            candidate_path=str(decision.path),
            baseline_path=baseline,
            zeus=zeus if isinstance(zeus, dict) else None,
            routed_by=decision.routed_by,
            phase=str(decision.phase),
        )
        if serving != str(decision.path).upper() or rb != decision.routed_by:
            decision = PolicyDecision(
                path=serving,  # type: ignore[arg-type]
                policy_path=policy_path,  # type: ignore[arg-type]
                routed_by=rb,
                phase=decision.phase,
                policy_phase=decision.policy_phase,
                complexity=decision.complexity,
                confidence=decision.confidence,
                product_mode=decision.product_mode,
                effort=decision.effort,
                design_lexicon=decision.design_lexicon,
                interactive=decision.interactive,
                tip_escalate=decision.tip_escalate,
                mor_scores=dict(decision.mor_scores),
                mode_ignored=decision.mode_ignored,
                thinking_passthrough=decision.thinking_passthrough,
                classify_failed=decision.classify_failed,
                reason=(decision.reason or "") + f"|serve:{rb}",
            )
    except Exception:  # noqa: BLE001 — never break policy soft hook
        pass
    return decision
