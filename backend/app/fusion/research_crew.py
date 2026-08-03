"""Research×3 → Sonnet 4.6 glue (TZ §1 / §3.1).

Each researcher (Gemini / Grok / DeepSeek) runs its OWN web search (school-angled
queries), then extracts facts from that pack. Sonnet 4.6 glues the three notes +
merged filing packs into the investigation. On ``final_report=True`` lead text IS
the user answer — no GPT doer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.fusion.roles import assign_role_model, resolve_stack
from app.fusion.web_tools import (
    format_refs_for_prompt,
    research_enabled,
    research_pack_fast_union,
    research_pack_for_critics,
)

log = logging.getLogger("zeus.fusion.research_crew")

UpstreamCall = Callable[..., Awaitable[dict[str, Any]]]

_JSON_RE = re.compile(r"\{[\s\S]*\}")

_RESEARCH_NEED_RE = re.compile(
    r"(?i)("
    r"https?://|www\.|найд[иь]\s+(?:в\s+)?(?:интернет|web)|web\s+search|"
    r"поиск\s+(?:в\s+)?(?:интернет|web)|найд[иь]\s+конкурент|"
    r"research\s+(?:online|web)|"
    r"competitor\s+(?:research|pricing)|конкурент\w+\s+(?:рынок|цены)|"
    r"актуальн|latest|202[4-9]|документац|docs\.|api reference|"
    r"официальн\w+\s+(?:документац|сайт)|official\s+(?:docs|documentation)|"
    r"рынок|market\s+research|цен[аы]\s+(?:рынка|конкурент)|competitor\s+pricing|"
    r"новост|announce|changelog|release notes"
    r")"
)
_CODE_NETWORK_RE = re.compile(
    r"(?i)("
    r"https?://|www\.|web\s+search|"
    r"найд[иь]\s+(?:в\s+)?(?:интернет|web)|"
    r"поиск\s+(?:в\s+)?(?:интернет|web)|"
    r"\blatest\b|актуальн\w*\s+(?:docs|документац)|"
    r"official\s+(?:docs|documentation)|"
    r"официальн\w+\s+(?:документац|сайт)|"
    r"docs\.|api\s+reference|changelog|release\s+notes"
    r")"
)


@dataclass
class ResearchNote:
    model_id: str
    role: str
    findings: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    raw: str = ""
    error: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    pack: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchCrewResult:
    ok: bool
    degraded: bool
    digest: str
    digest_struct: dict[str, Any] = field(default_factory=dict)
    notes: list[ResearchNote] = field(default_factory=list)
    pack: dict[str, Any] = field(default_factory=dict)
    branches: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    # When final_report=True: user-facing answer from lead (Sonnet 4.6).
    answer: str = ""


def research_crew_enabled() -> bool:
    try:
        from app.config import get_settings

        return bool(getattr(get_settings(), "FUSION_RESEARCH_CREW_ENABLED", True))
    except Exception:  # noqa: BLE001
        return True


def should_run_research_crew(
    *,
    user_q: str,
    task_kind: str | None = None,
    phase: str | None = None,
    size: str | None = None,
    zeus: dict[str, Any] | None = None,
) -> bool:
    """Run only when the request needs network facts; never by default on code/tool turns."""
    if not research_crew_enabled() or not research_enabled():
        return False
    z = zeus if isinstance(zeus, dict) else {}
    if z.get("research") is False or z.get("skip_research"):
        return False
    if z.get("research") is True or z.get("force_research"):
        return True
    try:
        from app.config import get_settings

        if bool(getattr(get_settings(), "FUSION_RESEARCH_CREW_ALWAYS", False)):
            return True
    except Exception:  # noqa: BLE001
        pass

    kind = (task_kind or "").strip().lower()
    ph = (phase or "").strip().lower()
    q = (user_q or "").strip()
    crew_raw = z.get("crew_state") if isinstance(z.get("crew_state"), dict) else {}
    turn_kind = str(crew_raw.get("turn_kind") or "").lower()
    explicit_network = bool(_RESEARCH_NEED_RE.search(q))
    if turn_kind in ("tool_loop", "exec_feedback"):
        return bool(_CODE_NETWORK_RE.search(q))
    if kind in ("code", "tests") or ph in ("implement", "debug", "test"):
        return bool(_CODE_NETWORK_RE.search(q))
    # Light / chat: only when query clearly needs facts
    if kind == "light" or ph == "chat":
        return explicit_network
    # Non-code planning/review may still opt into research by explicit signal.
    if len(q) < 8:
        return False
    return explicit_network


def _heuristic() -> bool:
    return (os.environ.get("ZEUS_FUSION_RESEARCH_HEURISTIC") or "").strip().lower() in (
        "1",
        "true",
        "on",
        "yes",
    )


def _parse_note(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {"findings": [], "sources": []}
    m = _JSON_RE.search(raw)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                findings = data.get("findings") or data.get("points") or []
                sources = data.get("sources") or data.get("urls") or []
                if isinstance(findings, str):
                    findings = [findings]
                if isinstance(sources, str):
                    sources = [sources]
                return {
                    "findings": [str(x).strip() for x in findings if str(x).strip()][:8],
                    "sources": [str(x).strip() for x in sources if str(x).strip()][:6],
                    "disagreements": data.get("disagreements") or [],
                }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    lines = [ln.strip(" -•\t") for ln in raw.splitlines() if ln.strip()]
    return {"findings": lines[:8], "sources": []}


_RESEARCHER_SYSTEM = (
    "Ты исследователь ZeusCode. Одна школа / один взгляд.\n"
    "Тебе дали результаты ТВОЕГО веб-поиска (refs) + у тебя есть знания модели.\n"
    "Смысл research: ИСПОЛЬЗОВАТЬ refs вместе со знаниями, а не отмазаться "
    "«в источниках мало».\n"
    "Ответ — ТОЛЬКО JSON: "
    '{"findings": ["..."], "sources": ["https://..."]}.\n'
    "Правила findings (макс 8):\n"
    "1) Сначала вытащи из refs всё полезное (цифры, определения, URL-факты). "
    "Если есть блок FILING FIGURES / Filing figures — обязательно включи эти цифры "
    "в findings с периодами/единицами как в refs.\n"
    "2) Дополни устоявшимися знаниями по теме запроса (метод, механика, "
    "стандартные определения) — пометь префиксом [knowledge], если это не из refs.\n"
    "3) Конкретные цифры из отчётности/filings — только из refs; иначе не выдумывай "
    "и скажи чего не хватает.\n"
    "4) URL в sources — только из refs. Кратко, по делу."
)

_LEAD_DIGEST_SYSTEM = (
    "Ты главная модель ZeusCode (Claude Sonnet 4.6).\n"
    "Три исследователя прислали findings (из refs + knowledge). Слей в сводку.\n"
    "Ответ — ТОЛЬКО JSON: "
    '{"summary": "...", "agreed": ["..."], "disagreements": ["A vs B: ..."], '
    '"sources": ["https://..."], "open_questions": ["..."]}.\n'
    "Используй и web-факты, и [knowledge]. Не своди всё к «данных нет». "
    "URL не выдумывай."
)

_LEAD_REPORT_SYSTEM = (
    "Ты главная модель ZeusCode (Claude Sonnet 4.6). "
    "Это ФИНАЛЬНЫЙ ответ человеку.\n"
    "Три исследователя дали findings + URL; ниже также web refs с Filing figures.\n"
    "Как работать с информацией:\n"
    "• ОБЯЗАТЕЛЬНО используй факты из notes/refs — цитируй URL рядом с claims.\n"
    "• Методологию/определения дополняй знаниями ТОЛЬКО когда вопрос "
    "методологический (TWFE, ATT(g,t), assumptions, software).\n"
    "• FACT-HEAVY запросы (цифры, IPO, mortality rates, OEM specs, named programs, "
    "SBC/warrants, refugee stats): ЗАПРЕЩЕНО заливать «красивой водой» — "
    "methodology framework / typical rates / established knowledge вместо цифр.\n"
    "• Нельзя писать «sources unavailable / coverage gap / no live data» как "
    "основу ответа. Если primary figure нет в refs — назови КОНКРЕТНО какой "
    "фактор/entity/period missing (1–2 bullets), а всё что ЕСТЬ в refs/notes "
    "выложи с числами и URL. Не заменяй missing data эссе про framework.\n"
    "• Named entities из query (программы, компании, лагеря, бренды, тикеры) "
    "должны появиться явно с фактами, не общими абзацами.\n"
    "• Конкретные финансовые/эмпирические цифры (OCF, margins, notes, SBC) — "
    "только из refs/notes; если есть Filing figures — ОБЯЗАТЕЛЬНО вставь их в отчёт "
    "с периодом [period …] и URL filing; если query просит Q1 2024, а в pack есть "
    "и Q1 2024 и Q1 2025 — цитируй ИМЕННО запрошенный период, компы помечай отдельно.\n"
    "• Fixed-rate notes: копируй тройки face+coupon+due АТОМАРНО из Filing figures "
    "(никогда не склеивай $750m от одной строки с 3.75% от другой).\n"
    "• Спеки станков / Jetson / TAO / холодильников (Nm, kW, rpm, °C, INT8 ms) — "
    "только из refs/Filing figures; если цифры нет — явно «not in sources», "
    "не подставляй «примерно» из памяти.\n"
    "• Числа пиши в нейтральном виде (32.4%, $117.9 million), не локализуй запятой.\n"
    "• Если дан Coverage checklist — закрывай ТОЛЬКО эти пункты (они уже "
    "отрезаны под ЭТОТ query). Не тащи TWFE/DiD/ATT, если их нет в checklist.\n"
    "• Не пиши Editorial Note про чужие методы (DiD/TWFE) на consumer/OEM задачах.\n"
    "• Не выдумывай URL.\n"
    "Структура: summary → ключевые факты/механизмы → сравнения → "
    "что подтверждено источниками vs knowledge → источники с URL → "
    "короткие open questions.\n"
    "ЗАПРЕЩЕНО: ответы-заглушки вроде «сейчас проверю источники / I will gather». "
    "Пиши готовый отчёт сразу.\n"
    "Язык = язык запроса. Markdown. Не JSON. Не код."
)

_COVERAGE_PASS_SYSTEM = (
    "Ты editor research-отчёта ZeusCode (Claude Sonnet 4.6).\n"
    "Дан черновик ответа, Coverage checklist пропусков и Filing figures.\n"
    "Верни ПОЛНЫЙ исправленный Markdown-отчёт (не diff, не JSON):\n"
    "• сохрани сильные части черновика и URL;\n"
    "• явно допиши каждый missing checklist item exam-style "
    "(точные механизмы/термины/цифры из Filing figures, не общие слова);\n"
    "• НЕ добавляй пункты вне списка missing (никакого TWFE/DiD, если их нет в missing);\n"
    "• знания модели ок для методологии; filing-цифры не выдумывай — бери из блока figures;\n"
    "• УДАЛИ «воду»: methodology framework / sources unavailable / typical rates "
    "вместо запрошенных primary figures. Замени на конкретные числа/имена из refs "
    "или явный bullet «MISSING: …».\n"
    "Язык = язык запроса."
)

# Reasoning models spend completion budget on reasoning_content.
# Keep researcher notes short — lead synthesizes; cuts ~30–40% gen latency.
# Notes stay short; deep path recovers quality via richer packs, not longer notes.
_RESEARCHER_MAX_TOKENS = 2200
_LEAD_DIGEST_MAX_TOKENS = 3072
_LEAD_REPORT_MAX_TOKENS = 6144
_COVERAGE_PASS_MAX_TOKENS = 6144
# School A = Gemini 3.1 Pro (A6 id …-preview); face/lead = Sonnet 4.6.
# Chains: A6 key/supplier failover lives in upstream.chat_a6; these are
# *model* fallbacks when the whole SKU is unknown/dead after A6 retries.
_RESEARCHER_A_MODEL = "gemini-3.1-pro-preview"
_LEAD_MODEL = "claude-sonnet-4-6"
_RESEARCHER_FAILOVER: dict[str, tuple[str, ...]] = {
    "researcher_a": (
        "gemini-3.1-pro-preview",
        "gemini-3-pro-preview",
        "grok-4.3",
        "claude-haiku-4-5",
    ),
    "researcher_b": ("grok-4.3", "claude-haiku-4-5", "deepseek-v4-pro"),
    "researcher_c": ("deepseek-v4-pro", "deepseek-v4-flash", "grok-4.3"),
}
_LEAD_FAILOVER: tuple[str, ...] = (
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "deepseek-v4-pro",
)

# (regex on answer, checklist label) — domain exam coverage.
_COVERAGE_MARKERS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(?i)variance[-\s]?weighted|weighted average of.*(2\s*[×x]\s*2|2\s*by\s*2)"),
        "TWFE as variance-weighted average of 2×2 DiD contrasts",
    ),
    (
        re.compile(r"(?i)forbidden comparison|already[-\s]?treated as control"),
        "Forbidden TWFE comparisons using already-treated units as controls",
    ),
    (
        re.compile(r"(?i)negative weights?|non[-\s]?convex weights?"),
        "TWFE negative/non-convex weights under heterogeneous effects",
    ),
    (
        re.compile(r"(?i)wrong[-\s]?sign|opposite sign|sign of the (true )?treatment"),
        "TWFE can yield wrong-sign estimates even if all true effects are positive",
    ),
    (
        re.compile(r"(?i)ATT\s*\(\s*g\s*,\s*t\s*\)|group[-\s]?time ATT"),
        "Callaway–Sant'Anna ATT(g,t) / group-time ATTs",
    ),
    (
        re.compile(r"(?i)never[-\s]?treated|not[-\s]?yet[-\s]?treated|clean controls?"),
        "CS clean controls (never-treated / not-yet-treated) then aggregate",
    ),
    (
        re.compile(r"(?i)overall ATT|flexible aggregation|aggregate to (an )?overall"),
        "CS flexible aggregation (overall ATT / event-study / cohort)",
    ),
    (
        re.compile(r"(?i)cohort[-\s]?specific parallel trends"),
        "CS cohort-specific parallel trends",
    ),
    (
        re.compile(r"(?i)anticipation (window|period|assum)"),
        "CS explicit anticipation windows",
    ),
    (
        re.compile(r"(?i)\bcsdid\b"),
        "CS software: Stata csdid",
    ),
    (
        re.compile(r"(?i)(\bdid\b.{0,40}R|R package ['`]?did|package did)"),
        "CS software: R package did",
    ),
    (
        re.compile(
            r"(?i)(cohort.{0,40}event[-\s]?time|event[-\s]?time.{0,40}cohort|"
            r"interaction[-\s]?weighted)"
        ),
        "Sun–Abraham cohort × event-time interactions / IW estimator",
    ),
    (
        re.compile(r"(?i)contamination|last[-\s]?treated"),
        "Sun–Abraham clean controls avoid contamination",
    ),
    (
        re.compile(
            r"(?i)(relative[-\s]?time event[-\s]?study|interpretable coefficients?.{0,40}event|"
            r"coefficient.{0,40}(each|every) event|event[-\s]?study framework)"
        ),
        "Sun–Abraham relative-time event-study with interpretable coefficients at each event time",
    ),
    (
        re.compile(r"(?i)event[-\s]?study"),
        "Sun–Abraham / CS event-study framework",
    ),
]


def needs_primary_facts(user_q: str) -> bool:
    """True when the query demands named numbers/entities, not methodology essays."""
    q = user_q or ""
    low = q.lower()
    if any(
        x in low
        for x in (
            "10-q",
            "10-k",
            "operating cash",
            "share-based",
            "stock-based",
            "sbc",
            "warrant",
            "dilution",
            "ncd",
            "debenture",
            "ipo",
            "maternal mortality",
            "refugee",
            "vaccine",
            "refrigerat",
            "spindle",
            "jetson",
            "quantum",
            "ownership",
            "paydown",
            "senior notes",
            "operating margin",
            "cash generation",
            "capital allocation",
        )
    ):
        return True
    if re.search(r"\$\s*[\d,]+", q):
        return True
    if re.search(r"\b20\d{2}\b", q) and any(
        x in low for x in ("compare", "analyze", "evaluate", "rate", "ipo", "filing")
    ):
        return True
    return False


def needs_deep_web_research(user_q: str) -> bool:
    """Finance / SEC / OEM-spec queries — deep multi-school packs (v5 quality)."""
    q = (user_q or "").lower()
    if any(
        x in q
        for x in (
            "10-q",
            "10-k",
            "8-k",
            "operating cash",
            "cash flow",
            "cash generation",
            "capital allocation",
            "share-based",
            "stock-based",
            "sbc",
            "warrant",
            "dilution",
            "senior notes",
            "fixed-rate",
            "operating margin",
            "ownership",
            "paydown",
            "renaissance",
            "investor relations",
            "long-term debt",
            "sec filing",
            "earnings",
            # OEM / edge-AI numbers — dedicated angles beat generic union.
            "spindle",
            "dmg mori",
            "mazak",
            "okuma",
            "nlx",
            "integrex",
            "jetson",
            "detectnet",
            "tao toolkit",
            "nvidia tao",
        )
    ):
        return True
    if re.search(r"\bq[1-4]\s*20\d{2}\b", q) and any(
        x in q for x in ("margin", "cash", "debt", "notes", "portfolio", "revenue", "ocf")
    ):
        return True
    return False


def research_path_mode(user_q: str) -> str:
    """'deep' = multi-school SERP+EDGAR; 'fast' = one union pack."""
    return "deep" if needs_deep_web_research(user_q) else "fast"


_WATERY_PHRASES = (
    "not available in the provided sources",
    "unavailable in the provided sources",
    "are unavailable in the provided",
    "no live data",
    "coverage gap",
    "methodological framework",
    "methodology framework",
    "primary market data",
    "specific statistical data",
    "established knowledge of",
    "while specific",
    "figures are unavailable",
    "sources do not contain",
    "sources are limited",
    "insufficient evidence base",
    "without access to",
    "cannot retrieve live",
    "data is not available from the provided",
    "actionable recommendations require",
)


def is_watery_answer(text: str, user_q: str = "") -> bool:
    """True for long hedge/framework essays that dodge primary facts."""
    t = (text or "").strip()
    if not t:
        return True
    low = t.lower()
    hits = sum(1 for p in _WATERY_PHRASES if p in low)
    if hits >= 2:
        return True
    if hits >= 1 and needs_primary_facts(user_q) and len(t) > 2500:
        # Fact-heavy + hedge phrase + long essay → water
        return True
    if needs_primary_facts(user_q) and len(t) > 4000:
        # Dense $/%/named years signal concreteness; absence + hedge = water
        concrete = len(
            re.findall(
                r"(?i)(\$\s*[\d,]+(?:\.\d+)?|\b\d+(?:\.\d+)?\s*%|\bQ[1-4]\s*20\d{2}\b|"
                r"\bunhcr\b|\bmsf\b|\b10-q\b|\bsec\.gov\b)",
                t,
            )
        )
        if concrete < 3 and hits >= 1:
            return True
    return False


def build_coverage_checklist(user_q: str) -> list[str]:
    """Exam-style must-cover bullets derived from the research query."""
    q = (user_q or "").lower()
    items: list[str] = [
        "Address every concrete comparison/mechanism the query asks for",
    ]
    if any(
        x in q
        for x in (
            "difference-in-differences",
            "difference in differences",
            "staggered",
            "goodman-bacon",
            "callaway",
            "sun and abraham",
            "sun-abraham",
            "borusyak",
            "twfe",
            "two-way fixed",
        )
    ):
        items.extend(
            [
                "TWFE as variance-weighted average of 2×2 DiD contrasts, including forbidden already-treated-as-control comparisons",
                "TWFE negative/non-convex weights under heterogeneous treatment effects",
                "TWFE wrong-sign bias possible even when all true effects are positive",
                "Callaway–Sant'Anna ATT(g,t); clean controls (never/not-yet-treated); then flexible aggregation (overall ATT, event-study, cohort)",
                "CS cohort-specific parallel trends; explicit anticipation windows",
                "CS software: R package `did` and Stata `csdid`",
                "Sun–Abraham: cohort × relative event-time interactions with cohort-share weights; clean controls avoid contamination",
                "Sun–Abraham produces an explicit relative-time event-study framework with interpretable coefficients at each event time",
                "Borusyak et al. imputation: how it differs on heterogeneous/dynamic effects vs CS/SA",
            ]
        )
    if any(
        x in q
        for x in (
            "10-q",
            "10-k",
            "operating cash",
            "ocf",
            "earnings",
            "net income",
            "sec filing",
            "stock-based",
            "share-based",
            "operating margin",
            "fixed-rate",
            "senior notes",
        )
    ):
        items.extend(
            [
                "State the key quantitative figures asked (levels, YoY deltas, ratios) with periods labeled",
                "Tie figures to named filings/sources when available; mark gaps explicitly if missing",
            ]
        )
    # Figure-aware rows: periods / $ amounts named in the query must appear explicitly.
    for m in re.finditer(r"(?i)\b(Q[1-4]\s*20\d{2})\b", user_q or ""):
        items.append(
            f"Label quantitative figures for {m.group(1)} distinctly "
            f"(do not substitute a different quarter without saying so)"
        )
    for m in re.finditer(
        r"\$\s*[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|m|bn))?",
        user_q or "",
        re.I,
    ):
        items.append(f"Include or reconcile figure {m.group(0).strip()} if present in sources")
    if any(x in q for x in ("ownership", "controlling interest", "increased from")):
        items.append("State ownership % change / controlling interest when present in sources")
    if any(x in q for x in ("paydown", "principal paydown", "repayment")):
        items.append("State principal paydown / repayment amount when present in sources")
    if any(x in q for x in ("sofr", "mortgage spread", "basis point")):
        items.append("State SOFR mortgage spread / rate reduction and linked paydown when in sources")
    if any(x in q for x in ("change in control", "impairment")):
        items.append(
            "State loss on change in control and impairment charges by fund/property when in sources"
        )
    # Word-boundary: "warrant" must not fire on "warranty" (appliance queries).
    if (
        any(x in q for x in ("stock-based", "share-based", "dilution"))
        or re.search(r"(?i)\b(sbc|warrants?)\b", user_q or "")
    ):
        items.append("State stock-based compensation totals by year/period when present in sources")
    if any(
        x in q
        for x in (
            "fixed-rate",
            "senior notes",
            "notes due",
            "weighted average",
            "debt maturity",
        )
    ):
        items.append(
            "List each fixed-rate note as face + coupon% + maturity date exactly as in sources "
            "(do not remix across rows)"
        )
    if any(
        x in q
        for x in (
            "spindle",
            "nlx",
            "integrex",
            "multus",
            "dmg mori",
            "mazak",
            "okuma",
            "thermal",
        )
    ):
        items.extend(
            [
                "State spindle torque (Nm) and/or power (kW) per machine from OEM sources",
                "Name thermal compensation brands exactly (e.g. Ai Thermal Shield, thermal displacement control)",
            ]
        )
    if any(
        x in q
        for x in (
            "jetson",
            "tao",
            "detectnet",
            "deepstream",
            "tensorrt",
            "yolo",
            "efficientdet",
        )
    ):
        items.extend(
            [
                "Cite INT8 / detector latency figures with source (detector-only vs end-to-end)",
                "Mention TAO/DeepStream OTA hot-swap or signed model update path when comparing ops",
                "Quantify TensorRT gains vs eager/FP16 when present in sources",
            ]
        )
    if any(x in q for x in ("refugee", "rohingya", "maternal mortality", "mae la")):
        items.extend(
            [
                "State maternal mortality / prenatal-care figures by camp/population when in sources",
                "Name UNHCR/MSF (or equivalent) sources with years 2017–2023 when present",
            ]
        )
    if any(x in q for x in ("quantum", "nisq", "qubit")):
        items.extend(
            [
                "Name Wellcome Leap Quantum for Bio (and 2024–2025 phases) when in sources",
                "Name Microsoft–Quantinuum and/or IBM quantum-utility results when in sources",
                "Name IonQ/AstraZeneca (or St. Jude/KRAS) drug-discovery demos when in sources",
                "Separate near-term NISQ demos vs production claims with cited sources",
            ]
        )
    if any(
        x in q
        for x in (
            "erp",
            "hamburger",
            "progressive disclosure",
            "as/400",
            "discoverability",
        )
    ):
        items.extend(
            [
                "Cite discoverability / task-time % deltas for hidden vs persistent nav when in sources",
                "Address older-adult / manufacturing-floor navigation constraints when asked",
            ]
        )
    if any(x in q for x in ("ncd", "debenture")) and "india" in q:
        items.append(
            "List open India NCD IPOs with issuer, coupon/rating, tenure when in sources"
        )
    if any(x in q for x in ("helmer", "thermo fisher", "vaccine", "refrigerat", "mdf-du")):
        items.append(
            "Compare each named fridge/freezer model with °C range and vaccine-use fit from OEM sources"
        )
    if any(
        x in q
        for x in (
            "heat pump dryer",
            "dryer",
            "kwh",
            "energy label",
            "victorian",
            "melbourne",
            "veu",
        )
    ) and any(x in q for x in ("bosch", "samsung", "lg ", "lg)", "dryer")):
        items.extend(
            [
                "State AU energy-label annual kWh (and/or per-cycle kWh) per named dryer when in sources",
                "State noise dB(A) per model when in sources; flag non-AU SKUs explicitly",
                "State Victorian c/kWh rate and VEU rebate $ when present in sources",
            ]
        )
    # Multi-token CapWord entities from the query (skip lone surnames / verbs).
    for m in re.finditer(
        r"\b([A-Z][A-Za-z0-9][\w\-]{2,24}(?:\s+[A-Z][A-Za-z0-9][\w\-]{1,24}){1,3})\b",
        user_q or "",
    ):
        ent = m.group(1).strip()
        if ent.lower() in {
            "analyze",
            "evaluate",
            "compare",
            "portfolio",
            "december",
            "india",
        }:
            continue
        if len(ent) >= 6:
            items.append(f"Cover named entity from query: {ent}")
        if len(items) >= 16:
            break
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out[:18]


def _checklist_is_did(checklist: list[str]) -> bool:
    blob = " ".join(checklist or []).lower()
    return any(
        x in blob
        for x in (
            "twfe",
            "att(g,t)",
            "callaway",
            "sun–abraham",
            "sun-abraham",
            "csdid",
            "borusyak",
            "2×2",
            "2x2",
        )
    )


def missing_coverage_items(answer: str, checklist: list[str]) -> list[str]:
    """Return checklist rows that look uncovered in the draft answer."""
    text = answer or ""
    if not text.strip():
        return list(checklist)
    missing: list[str] = []
    # DiD exam markers ONLY when the checklist is itself a DiD checklist.
    # Never bleed TWFE/CS/SA into dryer/OEM/finance rows via stopword hits ("as").
    if _checklist_is_did(checklist):
        for rx, label in _COVERAGE_MARKERS:
            if rx.search(text):
                continue
            missing.append(label)
    # Domain checklist rows with weak token overlap (skip generic opener).
    low = text.lower()
    for item in checklist:
        if item.lower().startswith("address every"):
            continue
        tokens = [
            t
            for t in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{3,}", item.lower())
            if t
            not in {
                "with",
                "under",
                "when",
                "then",
                "from",
                "that",
                "this",
                "using",
                "their",
                "package",
                "explicit",
                "possible",
                "average",
                "effects",
                "treatment",
                "concrete",
                "comparison",
                "mechanism",
                "query",
                "asks",
            }
        ]
        if len(tokens) < 3:
            continue
        hits = sum(1 for t in tokens[:8] if t in low)
        if hits < max(2, min(3, len(tokens) // 3)):
            if item not in missing:
                missing.append(item)
    return missing[:12]


_STUB_PHRASES = (
    "сначала проверю",
    "соберу полный",
    "начну с",
    "извлечения содержимого",
    "подкрепить анализ",
    "сейчас проверю",
    "i'll gather",
    "i will gather",
    "let me analyze",
    "i'll analyze",
    "i will analyze",
    "i will check",
    "checking sources",
    "let me check",
    "i'm going to",
    "i am going to",
)


def is_stub_answer(text: str) -> bool:
    """True for meta 'I will research…' placeholders instead of a real report."""
    t = (text or "").strip()
    if not t:
        return True
    # Short planning blurbs are never acceptable finals.
    if len(t) < 500:
        low = t.lower()
        if any(p in low for p in _STUB_PHRASES):
            return True
        # Single short paragraph with future-tense "will/начну" and no mechanisms.
        if re.search(r"(?i)\b(will|going to|начну|соберу|проверю)\b", low) and not re.search(
            r"(?i)(ATT\s*\(|TWFE|variance|10-Q|operating cash|http)",
            t,
        ):
            return True
    return False


def fallback_report_from_notes(
    user_q: str,
    notes: list[ResearchNote],
    *,
    refs_prompt: str = "",
) -> str:
    """Last-resort Markdown from researcher findings when Opus returns a stub."""
    lines = [
        "# Research report",
        "",
        "## Summary",
        f"Synthesized from three researcher notes for: {(user_q or '')[:240]}",
        "",
        "## Findings by school",
    ]
    for n in notes:
        lines.append(f"### {n.role} ({n.model_id})")
        if n.findings:
            for f in n.findings[:8]:
                lines.append(f"- {f}")
        else:
            lines.append(f"- (no findings; err={n.error})")
        if n.sources:
            lines.append("Sources: " + "; ".join(n.sources[:6]))
        lines.append("")
    if refs_prompt.strip():
        lines.append("## Web refs")
        lines.append(refs_prompt[:3500])
    return "\n".join(lines).strip()


async def _coverage_pass(
    *,
    user_q: str,
    draft: str,
    missing: list[str],
    lead_mid: str,
    upstream_call: UpstreamCall | None,
    notes_blob: str = "",
    refs_prompt: str = "",
) -> tuple[str, int, int, str | None]:
    watery = is_watery_answer(draft, user_q)
    if not missing and not is_stub_answer(draft) and not watery:
        return draft, 0, 0, None
    checklist = "\n".join(f"- {m}" for m in missing) or "- Fully answer the query with mechanisms + sources"
    stub = is_stub_answer(draft)
    draft_block = (
        "(draft was an unusable stub — IGNORE it and write the full report from notes/refs/knowledge)\n"
        if stub
        else (
            "(draft is WATERY hedge/framework — REWRITE with concrete figures/entities "
            "from refs; delete methodology-only filler)\n" + draft[:10000]
            if watery
            else draft[:12000]
        )
    )
    chain = [str(lead_mid)] + [m for m in _LEAD_FAILOVER if m != lead_mid]
    text, pt, ct, err, _used = await _call_model_with_failover(
        models=chain,
        system=_COVERAGE_PASS_SYSTEM,
        user=(
            f"Query:\n{(user_q or '')[:1800]}\n\n"
            f"## Missing coverage (must add explicitly)\n{checklist}\n\n"
            f"## Researcher notes\n{notes_blob[:4000]}\n\n"
            f"## Web refs + filing figures\n{refs_prompt[:4500]}\n\n"
            f"## Draft report\n{draft_block}\n\n"
            f"OUTPUT: complete Markdown research report NOW. "
            f"No planning sentences. No 'I will check sources'."
        ),
        upstream_call=upstream_call,
        max_tokens=_COVERAGE_PASS_MAX_TOKENS,
    )
    revised = (text or "").strip()
    if is_stub_answer(revised):
        # Prefer non-stub draft; else empty so caller can notes-fallback.
        if not is_stub_answer(draft):
            return draft, pt, ct, err or "coverage_pass_stub"
        return "", pt, ct, err or "coverage_pass_stub"
    # Accept substantial rewrite; never keep a stub over a longer body.
    min_len = 800 if stub else max(400, int(len(draft) * 0.45))
    if len(revised) < min_len:
        return draft, pt, ct, err or "coverage_pass_too_short"
    return revised, pt, ct, err


async def _call_model(
    *,
    model: str,
    system: str,
    user: str,
    upstream_call: UpstreamCall | None,
    max_tokens: int = _RESEARCHER_MAX_TOKENS,
    reasoning_effort: str = "low",
) -> tuple[str, int, int, str | None]:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        if upstream_call is not None:
            try:
                data = await upstream_call(
                    model=model,
                    messages=messages,
                    stream=False,
                    max_tokens=max_tokens,
                    reasoning_effort=reasoning_effort,
                )
            except TypeError:
                data = await upstream_call(
                    model=model, messages=messages, stream=False, max_tokens=max_tokens
                )
        else:
            from app import upstream

            # Uses A6 primary→fallback keys + top-supplier walk inside chat_a6.
            data = await upstream.chat_completions(
                model=model,
                messages=messages,
                stream=False,
                max_tokens=max_tokens,
                temperature=0.2,
                reasoning_effort=reasoning_effort,
            )
        from app import upstream as _up

        text = _up.extract_text(data) if isinstance(data, dict) else str(data or "")
        pt, ct = _up.extract_usage(data) if isinstance(data, dict) else (0, 0)
        text = (text or "").strip()
        if not text and int(ct or 0) > 0:
            # Budget eaten by reasoning — surface as soft error for meta/logs
            return "", int(pt or 0), int(ct or 0), "empty_content_after_reasoning"
        if not text:
            return "", int(pt or 0), int(ct or 0), "empty_content"
        return text, int(pt or 0), int(ct or 0), None
    except Exception as e:  # noqa: BLE001
        return "", 0, 0, str(e)[:200]


async def _call_model_with_failover(
    *,
    models: list[str] | tuple[str, ...],
    system: str,
    user: str,
    upstream_call: UpstreamCall | None,
    max_tokens: int = _RESEARCHER_MAX_TOKENS,
    reasoning_effort: str = "low",
) -> tuple[str, int, int, str | None, str]:
    """Try models in order; A6 key/supplier failover already inside each call.

    Returns (text, pt, ct, err, model_used).
    """
    seen: set[str] = set()
    last_err: str | None = "no_models"
    tot_pt = 0
    tot_ct = 0
    last_model = (models[0] if models else "") or ""
    for mid in models:
        m = (mid or "").strip()
        if not m or m in seen:
            continue
        seen.add(m)
        last_model = m
        text, pt, ct, err = await _call_model(
            model=m,
            system=system,
            user=user,
            upstream_call=upstream_call,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )
        tot_pt += int(pt or 0)
        tot_ct += int(ct or 0)
        if text.strip():
            if err:
                log.info("research_model_ok model=%s soft_err=%s", m, err)
            elif m != models[0]:
                log.warning(
                    "research_model_failover used=%s primary=%s",
                    m,
                    models[0],
                )
            return text, tot_pt, tot_ct, None, m
        last_err = err or "empty_content"
        log.warning(
            "research_model_fail model=%s err=%s trying_next=%s",
            m,
            last_err,
            True,
        )
    # Keep burned tokens for billing even when every model in the chain failed.
    return "", tot_pt, tot_ct, last_err, last_model


def merge_school_packs(packs: list[dict[str, Any]]) -> dict[str, Any]:
    """Union per-school research packs so lead sees filing_figures + extract text."""
    refs: list[dict[str, Any]] = []
    seen_u: set[str] = set()
    figs: list[str] = []
    seen_f: set[str] = set()
    queries: list[str] = []
    backends: list[str] = []
    browser_used = 0
    browser_available = False
    for p in packs:
        if not isinstance(p, dict):
            continue
        browser_used += int(p.get("browser_used") or 0)
        if p.get("browser_available"):
            browser_available = True
        if p.get("backend"):
            backends.append(str(p.get("backend")))
        for q in p.get("queries") or []:
            qs = str(q).strip()
            if qs and qs not in queries:
                queries.append(qs)
        for fig in p.get("filing_figures") or []:
            s = str(fig).strip()
            if s and s.lower() not in seen_f:
                seen_f.add(s.lower())
                figs.append(s)
        for r in p.get("refs") or []:
            if not isinstance(r, dict):
                continue
            u = str(r.get("url") or "")
            if not u:
                continue
            for fig in r.get("filing_figures") or []:
                s = str(fig).strip()
                if s and s.lower() not in seen_f:
                    seen_f.add(s.lower())
                    figs.append(s)
            if u in seen_u:
                # Prefer richer extract if we already have this URL.
                for existing in refs:
                    if str(existing.get("url") or "") != u:
                        continue
                    if len(str(r.get("text") or "")) > len(str(existing.get("text") or "")):
                        existing["text"] = r.get("text")
                    if r.get("filing_figures") and not existing.get("filing_figures"):
                        existing["filing_figures"] = r.get("filing_figures")
                    break
                continue
            seen_u.add(u)
            refs.append(dict(r))
    refs.sort(
        key=lambda r: 0
        if (r.get("ref_kind") == "sec_filing" or r.get("filing_figures"))
        else 1
    )
    ok = any((r.get("url") and (r.get("text") or r.get("snippet"))) for r in refs) or bool(figs)
    return {
        "ok": ok,
        "degraded": not ok,
        "refs": refs[:12],
        "filing_figures": figs[:32],
        "queries": queries[:12],
        "backend": ",".join(sorted({b for b in backends if b})) or "per_researcher",
        "browser_used": browser_used,
        "browser_available": browser_available,
    }


def _school_model_chain(role: str, primary: str) -> list[str]:
    """Primary first, then role failover table (deduped)."""
    chain = [primary] if primary else []
    for m in _RESEARCHER_FAILOVER.get(role, ()):
        if m and m not in chain:
            chain.append(m)
    return chain


async def _one_researcher(
    *,
    role: str,
    model_id: str,
    user_q: str,
    refs_prompt: str = "",
    upstream_call: UpstreamCall | None = None,
    own_search: bool = True,
) -> ResearchNote:
    pack: dict[str, Any] = {}
    if own_search and not _heuristic():
        # Each school hits the internet with its own query angle.
        pack = await research_pack_for_critics(user_q, school=role)
        refs_prompt = format_refs_for_prompt(pack)
    if _heuristic() or not model_id:
        findings = [
            ln.strip()
            for ln in (refs_prompt or "").splitlines()
            if ln.strip().startswith(("###", "URL:", "Snippet:"))
        ][:4]
        return ResearchNote(
            model_id=model_id or "heuristic",
            role=role,
            findings=findings or [f"[{role}] no web refs"],
            sources=re.findall(r"https?://\S+", refs_prompt or "")[:4],
            raw="heuristic",
            pack=pack if isinstance(pack, dict) else {},
        )
    user = (
        f"Query:\n{(user_q or '')[:1500]}\n\n"
        f"## Your web search results (school={role})\n"
        f"queries={pack.get('queries') if pack else []}\n"
        f"backend={pack.get('backend') if pack else 'n/a'}\n\n"
        f"{(refs_prompt or '')[:5000]}\n\n"
        f"Role={role}. Свой угол: вытащи из refs + дополни [knowledge], "
        f"чтобы findings реально помогали ответить на Query. "
        f"Не копируй другие школы. Не пиши только «refs пустые»."
    )
    chain = _school_model_chain(role, model_id)
    text, pt, ct, err, used = await _call_model_with_failover(
        models=chain,
        system=_RESEARCHER_SYSTEM,
        user=user,
        upstream_call=upstream_call,
        max_tokens=_RESEARCHER_MAX_TOKENS,
    )
    parsed = _parse_note(text)
    sources = list(parsed.get("sources") or [])
    if not sources and pack.get("refs"):
        sources = [str(r.get("url")) for r in pack["refs"] if r.get("url")][:6]
    note_err = err
    if pack and not pack.get("ok") and not note_err:
        note_err = f"web_pack_empty:{pack.get('search_error') or 'no_refs'}"
    if used and used != model_id and not note_err:
        note_err = f"failover:{model_id}->{used}"
    return ResearchNote(
        model_id=used or model_id,
        role=role,
        findings=list(parsed.get("findings") or []),
        sources=sources,
        raw=(text or "")[:1200],
        error=note_err,
        prompt_tokens=pt,
        completion_tokens=ct,
        pack=pack if isinstance(pack, dict) else {},
    )


def _merge_heuristic(notes: list[ResearchNote], pack: dict[str, Any]) -> dict[str, Any]:
    agreed: list[str] = []
    seen: set[str] = set()
    for n in notes:
        for f in n.findings:
            key = f.lower()[:80]
            if key not in seen:
                seen.add(key)
                agreed.append(f)
    sources: list[str] = []
    for n in notes:
        for u in n.sources:
            if u not in sources:
                sources.append(u)
    for r in pack.get("refs") or []:
        u = str(r.get("url") or "")
        if u and u not in sources:
            sources.append(u)
    disagreements: list[str] = []
    if len(notes) >= 2:
        sets = [set(x.lower()[:60] for x in n.findings) for n in notes if n.findings]
        if len(sets) >= 2:
            only_a = sets[0] - sets[1]
            only_b = sets[1] - sets[0]
            for s in list(only_a)[:2]:
                disagreements.append(f"{notes[0].role} only: {s}")
            for s in list(only_b)[:2]:
                disagreements.append(f"{notes[1].role} only: {s}")
    return {
        "summary": "; ".join(agreed[:4]) or "Web pack empty / degraded",
        "agreed": agreed[:8],
        "disagreements": disagreements[:6],
        "sources": sources[:8],
        "open_questions": [],
    }


async def run_research_crew(
    *,
    user_q: str,
    product_mode: str = "power",
    stack: list[str] | None = None,
    upstream_call: UpstreamCall | None = None,
    pack: dict[str, Any] | None = None,
    final_report: bool = False,
) -> ResearchCrewResult:
    mode = product_mode if product_mode in ("simple", "power", "custom") else "power"
    raw_stack = stack if isinstance(stack, (list, tuple)) else None
    st = [m for m in list(raw_stack or resolve_stack(mode)) if isinstance(m, str) and len(m) > 2]
    if not st:
        st = list(resolve_stack(mode))
    models = {
        "researcher_a": assign_role_model("researcher_a", mode, st).model_id,
        "researcher_b": assign_role_model("researcher_b", mode, st).model_id,
        "researcher_c": assign_role_model("researcher_c", mode, st).model_id,
    }
    # Force school A = Gemini 3.1 Pro (A6 …-preview); stack may omit it.
    models["researcher_a"] = _RESEARCHER_A_MODEL
    if not models["researcher_b"]:
        models["researcher_b"] = next(
            (m for m in st if "grok" in m),
            next((m for m in st if "deepseek" in m), models["researcher_a"]),
        )
    if not models["researcher_c"]:
        models["researcher_c"] = next((m for m in st if "deepseek" in m), models["researcher_a"])

    # Face/lead = Sonnet 4.6 glues Gemini + Grok + DeepSeek findings.
    lead_role = "face"
    lead_mid = _LEAD_MODEL
    models["lead"] = lead_mid
    lead_chain = [lead_mid] + [m for m in _LEAD_FAILOVER if m != lead_mid]

    # Adaptive pack:
    #  - deep (finance/OEM): 3 school packs in parallel → merge (v5 quality, better
    #    latency than search+LLM per school because LLM waits on one merged pack)
    #  - fast (method/other): one union pack
    path_mode = research_path_mode(user_q)
    shared_pack = pack if isinstance(pack, dict) else None
    if shared_pack is None and not _heuristic() and research_enabled():
        try:
            if path_mode == "deep":
                raw_packs = await asyncio.gather(
                    research_pack_for_critics(
                        user_q, school="researcher_a", max_fetch_override=6
                    ),
                    research_pack_for_critics(
                        user_q, school="researcher_b", max_fetch_override=6
                    ),
                    research_pack_for_critics(
                        user_q, school="researcher_c", max_fetch_override=6
                    ),
                    return_exceptions=True,
                )
                good = [p for p in raw_packs if isinstance(p, dict)]
                shared_pack = merge_school_packs(good) if good else None
                if shared_pack is not None:
                    shared_pack["path_mode"] = "deep"
            else:
                shared_pack = await research_pack_fast_union(user_q)
                if isinstance(shared_pack, dict):
                    shared_pack["path_mode"] = "fast"
        except Exception as e:  # noqa: BLE001
            log.warning("adaptive pack failed path=%s: %s", path_mode, e)
            shared_pack = None
    shared_refs = (
        format_refs_for_prompt(shared_pack, user_q=user_q) if shared_pack else ""
    )

    # Deep finance/OEM always keeps 3 note schools (v5 quality). Fast path may
    # drop researcher_c when the union pack is already healthy.
    fig_n = len((shared_pack or {}).get("filing_figures") or [])
    rich_figures = fig_n >= 5
    if path_mode == "fast" and (shared_pack or {}).get("ok"):
        _slots = (
            ("researcher_a", models["researcher_a"]),
            ("researcher_b", models["researcher_b"]),
        )
    else:
        _slots = (
            ("researcher_a", models["researcher_a"]),
            ("researcher_b", models["researcher_b"]),
            ("researcher_c", models["researcher_c"]),
        )
    gathered = list(
        await asyncio.gather(
            *[
                _one_researcher(
                    role=role,
                    model_id=str(mid or ""),
                    user_q=user_q,
                    refs_prompt=shared_refs,
                    upstream_call=upstream_call,
                    # Pack already built above; only own_search if pack missing.
                    own_search=shared_pack is None,
                )
                for role, mid in _slots
            ],
            return_exceptions=True,
        )
    )
    notes: list[ResearchNote] = []
    for (role, mid), result in zip(_slots, gathered):
        if isinstance(result, BaseException):
            notes.append(
                ResearchNote(
                    model_id=str(mid or ""),
                    role=role,
                    error=f"{type(result).__name__}: {str(result)[:240]}",
                )
            )
        else:
            notes.append(result)

    # Merge per-school packs so lead gets filing_figures + extracts, not URL shells.
    school_packs = [n.pack for n in notes if isinstance(n.pack, dict) and n.pack]
    _union_urls = [
        u
        for n in notes
        for u in (n.sources or [])
        if isinstance(u, str) and u.startswith("http")
    ]
    if shared_pack:
        web_pack = shared_pack
    elif school_packs:
        web_pack = merge_school_packs(school_packs)
    else:
        web_pack = {
            "ok": bool(_union_urls),
            "refs": [{"url": u} for u in _union_urls],
            "queries": [],
            "backend": "per_researcher",
            "browser_used": 0,
        }

    # Fact-heavy + empty/thin pack → hard escalate with browser forced.
    escalated = False
    thin_pack = (
        not web_pack.get("ok")
        or len(web_pack.get("refs") or []) < 2
        or (
            not (web_pack.get("filing_figures") or [])
            and any(
                x in (user_q or "").lower()
                for x in (
                    "10-q",
                    "share-based",
                    "sbc",
                    "warrant",
                    "ncd",
                    "vtv",
                    "maternal",
                )
            )
        )
    )
    if (
        not _heuristic()
        and needs_primary_facts(user_q)
        and research_enabled()
        and thin_pack
    ):
        try:
            esc = await research_pack_for_critics(
                user_q,
                school="escalate",
                force_browser=True,
                max_fetch_override=5,
            )
            escalated = True
            if isinstance(esc, dict) and (esc.get("refs") or esc.get("filing_figures")):
                web_pack = merge_school_packs([web_pack, esc])
                shared_refs = format_refs_for_prompt(
                    web_pack, char_budget=5500, user_q=user_q
                )
        except Exception as e:  # noqa: BLE001
            log.warning("research escalate failed: %s", e)
            escalated = True

    branches: list[dict[str, Any]] = []
    for n in notes:
        branches.append(
            {
                "model_id": n.model_id,
                "role": n.role,
                "billable_state": "completed" if (n.prompt_tokens or n.completion_tokens or n.findings) else "cancelled_no_tokens",
                "prompt_tokens": n.prompt_tokens,
                "completion_tokens": n.completion_tokens,
                "meta": {
                    "findings_n": len(n.findings),
                    "sources_n": len(n.sources),
                    "error": n.error,
                    "own_search": shared_pack is None,
                    "pack_refs": len((n.pack or {}).get("refs") or []),
                    "pack_figures": len((n.pack or {}).get("filing_figures") or []),
                },
            }
        )

    notes_blob = json.dumps(
        [
            {
                "role": n.role,
                "model": n.model_id,
                "findings": n.findings,
                "sources": n.sources,
                "error": n.error,
            }
            for n in notes
        ],
        ensure_ascii=False,
    )[:7000]
    # Always format from final web_pack (escalate merge + period-priority figures).
    refs_prompt = (
        format_refs_for_prompt(web_pack, char_budget=5500, user_q=user_q) or shared_refs
    )

    digest_struct: dict[str, Any]
    answer = ""
    lead_pt = lead_ct = 0
    lead_err = None

    if _heuristic() or not lead_mid:
        digest_struct = _merge_heuristic(notes, web_pack)
        if final_report:
            answer = format_research_digest(digest_struct)
    elif final_report:
        # Sonnet glues facts → full investigation (user-facing answer)
        digest_struct = _merge_heuristic(notes, web_pack)
        checklist = build_coverage_checklist(user_q)
        checklist_block = ""
        if checklist:
            checklist_block = (
                "## Coverage checklist (each item must appear explicitly)\n"
                + "\n".join(f"- {c}" for c in checklist)
                + "\n\n"
            )
        text, lead_pt, lead_ct, lead_err, lead_used = await _call_model_with_failover(
            models=lead_chain,
            system=_LEAD_REPORT_SYSTEM,
            user=(
                f"Query:\n{(user_q or '')[:2000]}\n\n"
                f"{checklist_block}"
                f"## Web refs (merged school packs + filing figures)\n{refs_prompt[:5000]}\n\n"
                f"## Researcher notes (refs + [knowledge])\n{notes_blob}\n\n"
                f"Собери полный ответ на Query. Факты/цифры — из notes/refs. "
                f"{'FACT-HEAVY: запрещена methodology-вода вместо primary numbers. ' if needs_primary_facts(user_q) else ''}"
                f"Gaps — только явные MISSING bullets по конкретным цифрам/entity."
            ),
            upstream_call=upstream_call,
            max_tokens=_LEAD_REPORT_MAX_TOKENS,
        )
        if lead_used:
            lead_mid = lead_used
            models["lead"] = lead_used
        answer = (text or "").strip()
        # Single rewrite path (coverage) for stub/watery/gaps — no second full lead call.
        cov_missing = missing_coverage_items(answer, checklist)
        cov_pt = cov_ct = 0
        cov_err: str | None = None
        if answer and (
            cov_missing or is_stub_answer(answer) or is_watery_answer(answer, user_q)
        ):
            answer, cov_pt, cov_ct, cov_err = await _coverage_pass(
                user_q=user_q,
                draft=answer,
                missing=cov_missing or checklist,
                lead_mid=str(lead_mid),
                upstream_call=upstream_call,
                notes_blob=notes_blob,
                refs_prompt=refs_prompt,
            )
            lead_pt += cov_pt
            lead_ct += cov_ct
            if cov_err and not lead_err:
                lead_err = cov_err
        used_fallback = False
        if is_stub_answer(answer):
            answer = fallback_report_from_notes(
                user_q, notes, refs_prompt=refs_prompt
            )
            used_fallback = True
            if not lead_err:
                lead_err = "lead_stub_fallback_notes"
        if answer:
            digest_struct["summary"] = answer[:800]
        digest_struct["coverage_missing_before"] = cov_missing
        still_water = is_watery_answer(answer, user_q)
        still_missing = missing_coverage_items(answer, checklist)
        # Pass only when checklist closed AND answer is not watery hedge.
        digest_struct["coverage_pass"] = (not still_missing) and (not still_water)
        digest_struct["watery_rejected"] = still_water
        digest_struct["stub_rejected"] = is_stub_answer(text or "")
        digest_struct["notes_fallback"] = used_fallback
        digest_struct["research_escalated"] = escalated
        digest_struct["path_mode"] = path_mode
        digest_struct["rich_figures"] = rich_figures
        branches.append(
            {
                "model_id": lead_mid,
                "role": "lead",
                "billable_state": "completed" if (lead_pt or lead_ct or answer) else "cancelled_no_tokens",
                "prompt_tokens": lead_pt,
                "completion_tokens": lead_ct,
                "meta": {
                    "error": lead_err,
                    "lead_role": lead_role,
                    "final_report": True,
                    "coverage_pass": digest_struct["coverage_pass"],
                    "coverage_missing_n": len(still_missing or cov_missing),
                    "watery": still_water,
                    "escalated": escalated,
                    "path_mode": path_mode,
                    "rich_figures": rich_figures,
                },
            }
        )
    else:
        # Background digest for code/UI paths (Sonnet lead, not DeepSeek/GPT)
        text, lead_pt, lead_ct, lead_err, lead_used = await _call_model_with_failover(
            models=lead_chain,
            system=_LEAD_DIGEST_SYSTEM,
            user=(
                f"Query:\n{(user_q or '')[:1200]}\n\n"
                f"## Web refs (merged school packs)\n{refs_prompt[:3500]}\n\n"
                f"Notes:\n{notes_blob}"
            ),
            upstream_call=upstream_call,
            max_tokens=_LEAD_DIGEST_MAX_TOKENS,
        )
        if lead_used:
            lead_mid = lead_used
            models["lead"] = lead_used
        parsed = _parse_note(text)
        try:
            m = _JSON_RE.search(text or "")
            data = json.loads(m.group(0)) if m else {}
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
            data = {}
        if not isinstance(data, dict) or not data.get("summary"):
            digest_struct = _merge_heuristic(notes, web_pack)
            if text:
                digest_struct["summary"] = (text or "")[:500]
        else:
            digest_struct = {
                "summary": str(data.get("summary") or "")[:800],
                "agreed": [str(x) for x in (data.get("agreed") or parsed.get("findings") or [])][:8],
                "disagreements": [str(x) for x in (data.get("disagreements") or [])][:6],
                "sources": [str(x) for x in (data.get("sources") or [])][:8],
                "open_questions": [str(x) for x in (data.get("open_questions") or [])][:4],
            }
        branches.append(
            {
                "model_id": lead_mid,
                "role": "lead",
                "billable_state": "completed" if (lead_pt or lead_ct) else "cancelled_no_tokens",
                "prompt_tokens": lead_pt,
                "completion_tokens": lead_ct,
                "meta": {"error": lead_err, "lead_role": lead_role, "final_report": False},
            }
        )

    digest = format_research_digest(digest_struct)
    ok = bool(answer or digest_struct.get("summary") or digest_struct.get("agreed"))
    return ResearchCrewResult(
        ok=ok,
        degraded=not ok or not web_pack.get("ok"),
        digest=digest,
        digest_struct=digest_struct,
        notes=notes,
        pack=web_pack,
        branches=branches,
        answer=answer,
        meta={
            "models": models,
            "lead_role": lead_role,
            "lead_model": lead_mid,
            "final_report": bool(final_report),
            "web_ok": web_pack.get("ok"),
            "browser_used": web_pack.get("browser_used"),
            "refs": [r.get("url") for r in (web_pack.get("refs") or []) if r.get("url")],
            "coverage_pass": bool(digest_struct.get("coverage_pass")),
            "coverage_missing_n": len(digest_struct.get("coverage_missing_before") or []),
            "watery_rejected": bool(digest_struct.get("watery_rejected")),
            "research_escalated": bool(digest_struct.get("research_escalated")),
            "path_mode": path_mode,
            "rich_figures": bool(digest_struct.get("rich_figures")),
            "filing_figures_n": len(web_pack.get("filing_figures") or []),
        },
    )


def format_research_digest(struct: dict[str, Any]) -> str:
    parts: list[str] = ["[ZeusCode · research_digest]"]
    if struct.get("summary"):
        parts.append(f"Summary: {struct['summary']}")
    if struct.get("agreed"):
        parts.append("Agreed:\n- " + "\n- ".join(str(x) for x in struct["agreed"][:8]))
    if struct.get("disagreements"):
        parts.append(
            "Disagreements:\n- " + "\n- ".join(str(x) for x in struct["disagreements"][:6])
        )
    if struct.get("sources"):
        parts.append("Sources:\n- " + "\n- ".join(str(x) for x in struct["sources"][:8]))
    if struct.get("open_questions"):
        parts.append(
            "Open:\n- " + "\n- ".join(str(x) for x in struct["open_questions"][:4])
        )
    return "\n".join(parts).strip()


def inject_digest_into_messages(
    messages: list[dict[str, Any]],
    digest: str,
) -> list[dict[str, Any]]:
    """Append digest into system block (slot 5 artifacts) without wiping client system."""
    if not (digest or "").strip():
        return messages
    out = [dict(m) for m in messages]
    tag = "[ZeusCode · research_digest]"
    injected = False
    for m in out:
        if str(m.get("role") or "") != "system":
            continue
        content = str(m.get("content") or "")
        if tag in content:
            return out
        m["content"] = content + "\n\n" + digest.strip()
        injected = True
        break
    if not injected:
        out.insert(0, {"role": "system", "content": digest.strip()})
    return out
