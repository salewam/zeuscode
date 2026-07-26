"""Pre-dev Clarifier — ask → confirm → enriched prompt → pipeline (Gemini-first).

Sits before small/v1/fallback. ``fusion/*`` must not import ``routers.*``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .model_power import power_score

ClarifyPhase = Literal["ask", "confirm", "done", "skip"]

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_SKIP_RE = re.compile(
    r"(?i)^\s*(без\s+уточнен|сразу\s+делай|skip\s*clarify|no\s*clarify|просто\s+сделай)",
)
_YES_RE = re.compile(
    r"(?i)^\s*(да|yes|ok|ок|утверждаю|утверждено|согласен|погнали|делай|go)\s*[.!]?\s*$",
)

_GEMINI_PREFS = (
    "gemini-3.1-pro",
    "gemini-3-pro",
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
)

MAX_CONFIRM_REVISIONS = 2

_ASK_SYSTEM = (
    "Ты Clarifier ZeusCode — продуктовый интервьюер перед разработкой. "
    "НЕ пиши код. Ответ — ТОЛЬКО JSON:\n"
    '{"phase":"ask","questions":["q1",...],"spec_summary":"","enriched_prompt":""}\n'
    "5–8 коротких конкретных вопросов (цели, аудитория, стек/платформа, "
    "ограничения, референсы, критерии готово). Без prose вне JSON."
)

_CONFIRM_SYSTEM = (
    "Ты Clarifier ZeusCode. По исходной задаче и ответам юзера собери краткое ТЗ. "
    "НЕ пиши код. Ответ — ТОЛЬКО JSON:\n"
    '{"phase":"confirm","questions":[],"spec_summary":"маркированный список ТЗ",'
    '"enriched_prompt":"полный промпт для разработчика со всеми деталями"}\n'
    "spec_summary — коротко для человека. enriched_prompt — полный бриф для пайплайна."
)

_REVISE_SYSTEM = (
    "Ты Clarifier ZeusCode. Юзер дал правки к ТЗ. Обнови ТЗ. НЕ пиши код. "
    "Ответ — ТОЛЬКО JSON с phase=confirm, spec_summary и enriched_prompt."
)


@dataclass
class ClarifierState:
    phase: ClarifyPhase = "ask"
    original_goal: str = ""
    questions: list[str] = field(default_factory=list)
    answers: str = ""
    spec_summary: str = ""
    enriched_prompt: str = ""
    clarifier_model: str | None = None
    revision_count: int = 0
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ClarifierState:
        if not isinstance(raw, dict):
            return ClarifierState()
        phase = str(raw.get("phase") or "ask")
        if phase not in ("ask", "confirm", "done", "skip"):
            phase = "ask"
        qs = raw.get("questions") or []
        if not isinstance(qs, list):
            qs = []
        return ClarifierState(
            phase=phase,  # type: ignore[arg-type]
            original_goal=str(raw.get("original_goal") or "")[:4000],
            questions=[str(q)[:400] for q in qs if str(q).strip()][:12],
            answers=str(raw.get("answers") or "")[:8000],
            spec_summary=str(raw.get("spec_summary") or "")[:4000],
            enriched_prompt=str(raw.get("enriched_prompt") or "")[:12000],
            clarifier_model=(str(raw.get("clarifier_model") or "").strip() or None),
            revision_count=max(0, int(raw.get("revision_count") or 0)),
            session_id=(str(raw.get("session_id") or "").strip() or None),
        )


@dataclass
class ClarifierTurnResult:
    """``halt=True`` → return questions/spec to user; do not start pipeline."""

    halt: bool
    phase: ClarifyPhase
    user_text: str
    state: ClarifierState
    model_id: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


def pick_clarifier_model(
    stack: list[str],
    *,
    unhealthy: set[str] | None = None,
    curator: str | None = None,
) -> str | None:
    """Prefer Gemini from user stack; else mid; else curator (AD-21: no invent)."""
    dead = set(unhealthy or ())
    ready = [m for m in stack if m and m not in dead] or [m for m in stack if m]
    if not ready:
        return (curator or "").strip() or None
    for pref in _GEMINI_PREFS:
        if pref in ready:
            return pref
    for m in ready:
        if "gemini" in m.lower():
            return m
    # mid-band prefer
    mid = [m for m in ready if 700 <= power_score(m) <= 940]
    if mid:
        return max(mid, key=power_score)
    if curator and curator in ready:
        return curator
    return ready[0]


def should_run_clarifier(
    *,
    product_mode: str,
    size: str,
    second_signal: bool,
    kill_switch: bool,
    zeus: dict[str, Any] | None,
    user_q: str,
    state: ClarifierState | None = None,
) -> bool:
    """When to engage clarifier (plan defaults)."""
    z = zeus if isinstance(zeus, dict) else {}
    if kill_switch:
        return False
    if (product_mode or "").lower() == "simple":
        return False
    if z.get("clarify") is False or str(z.get("clarify") or "").lower() in (
        "0",
        "false",
        "off",
        "no",
    ):
        return False
    if state and state.phase in ("done", "skip"):
        return False
    if _SKIP_RE.search(user_q or ""):
        return False
    # Already mid-flow
    if state and state.phase in ("ask", "confirm") and (state.questions or state.spec_summary):
        return True
    if z.get("clarify") is True or str(z.get("clarify") or "").lower() in (
        "1",
        "true",
        "on",
        "yes",
    ):
        return True
    if (size or "").lower() == "large":
        return True
    if second_signal:
        return True
    return False


def is_approval(text: str) -> bool:
    return bool(_YES_RE.match((text or "").strip()))


def user_wants_skip(text: str) -> bool:
    return bool(_SKIP_RE.search(text or ""))


def _extract_json(raw: str | dict[str, Any] | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    if text.startswith("```"):
        text = _JSON_FENCE_RE.sub("", text).strip()
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _heuristic() -> bool:
    return (os.environ.get("ZEUS_FUSION_CLARIFIER_HEURISTIC") or "").strip().lower() in (
        "1",
        "true",
        "on",
        "yes",
    )


def format_ask_message(questions: list[str], *, has_session: bool) -> str:
    lines = ["Перед разработкой уточню несколько вещей:\n"]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}) {q}")
    lines.append("\nОтветьте по пунктам одним сообщением.")
    if not has_session:
        lines.append(
            "\n_(Для продолжения в API передайте тот же `zeus.session_id` "
            "или заголовок `X-Zeus-Session-Id`.)_"
        )
    return "\n".join(lines)


def format_confirm_message(spec: str) -> str:
    body = (spec or "").strip() or "— (пустое ТЗ)"
    return (
        f"Собрал ТЗ:\n\n{body}\n\n"
        "Пиши **да**, чтобы начать разработку, или пришли правки."
    )


def build_enriched_fallback(
    *,
    goal: str,
    answers: str,
    spec: str,
) -> str:
    return (
        f"## Утверждённое ТЗ (Clarifier)\n{spec.strip()}\n\n"
        f"## Исходная задача\n{goal.strip()}\n\n"
        f"## Ответы на уточнения\n{answers.strip()}\n\n"
        "Реализуй по ТЗ полностью."
    )


async def _call_model(
    *,
    model_id: str,
    system: str,
    user: str,
    upstream_call: Any | None,
) -> tuple[str, int, int]:
    if _heuristic():
        return "", 0, 8
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if upstream_call is not None:
        data = await upstream_call(
            model_id, msgs, temperature=0.2, max_tokens=2048
        )
        text = str((data or {}).get("text") or "")
        pt = int((data or {}).get("prompt_tokens") or 0)
        ct = int((data or {}).get("completion_tokens") or 0)
        return text, pt, ct
    from app.fusion.panel import _default_upstream

    data = await _default_upstream(
        model_id, msgs, temperature=0.2, max_tokens=2048
    )
    return (
        str(data.get("text") or ""),
        int(data.get("prompt_tokens") or 0),
        int(data.get("completion_tokens") or 0),
    )


def _heuristic_ask(goal: str) -> dict[str, Any]:
    g = (goal or "задача")[:80]
    return {
        "phase": "ask",
        "questions": [
            f"Какая главная цель для «{g}»?",
            "Кто целевая аудитория?",
            "Какой стек/платформа (web/TG/API)?",
            "Есть ли обязательные страницы/экраны?",
            "Ограничения по стилю, сроку, бюджету моделей?",
            "Как поймём, что готово (критерий приёмки)?",
        ],
        "spec_summary": "",
        "enriched_prompt": "",
    }


def _heuristic_confirm(goal: str, answers: str) -> dict[str, Any]:
    spec = (
        f"— Цель: {goal[:200]}\n"
        f"— Уточнения: {(answers or 'не указаны')[:600]}\n"
        "— Сделать рабочий результат по пунктам выше"
    )
    enriched = build_enriched_fallback(goal=goal, answers=answers, spec=spec)
    return {
        "phase": "confirm",
        "questions": [],
        "spec_summary": spec,
        "enriched_prompt": enriched,
    }


async def run_clarifier_turn(
    *,
    user_q: str,
    messages: list[dict[str, Any]] | None = None,
    state: ClarifierState | None = None,
    stack: list[str],
    curator: str | None = None,
    unhealthy: set[str] | None = None,
    session_id: str | None = None,
    upstream_call: Any | None = None,
) -> ClarifierTurnResult:
    """One clarifier turn. ``halt=True`` until phase=done."""
    st = state or ClarifierState()
    st.session_id = session_id or st.session_id
    model = pick_clarifier_model(stack, unhealthy=unhealthy, curator=curator)
    st.clarifier_model = model

    text = (user_q or "").strip()
    if user_wants_skip(text) and st.phase in ("ask", "confirm") and not st.questions:
        st.phase = "skip"
        return ClarifierTurnResult(
            halt=False,
            phase="skip",
            user_text=text,
            state=st,
            model_id=model,
            meta={"skipped": True},
        )

    # --- Fresh start → ASK ---
    if st.phase in ("ask", "skip") and not st.questions and not st.spec_summary:
        st.original_goal = text
        st.phase = "ask"
        if _heuristic() or not model:
            data = _heuristic_ask(text)
            pt, ct = 0, 8
        else:
            raw, pt, ct = await _call_model(
                model_id=model,
                system=_ASK_SYSTEM,
                user=f"Задача пользователя:\n{text[:3000]}",
                upstream_call=upstream_call,
            )
            data = _extract_json(raw) or _heuristic_ask(text)
        qs = [str(q).strip() for q in (data.get("questions") or []) if str(q).strip()]
        if not qs:
            qs = _heuristic_ask(text)["questions"]
        st.questions = qs[:8]
        msg = format_ask_message(st.questions, has_session=bool(st.session_id))
        return ClarifierTurnResult(
            halt=True,
            phase="ask",
            user_text=msg,
            state=st,
            model_id=model,
            prompt_tokens=pt,
            completion_tokens=ct,
            meta={"questions_n": len(st.questions)},
        )

    # --- Waiting answers (phase ask with questions) → CONFIRM ---
    if st.phase == "ask" and st.questions:
        st.answers = text
        goal = st.original_goal or text
        if _heuristic() or not model:
            data = _heuristic_confirm(goal, text)
            pt, ct = 0, 10
        else:
            raw, pt, ct = await _call_model(
                model_id=model,
                system=_CONFIRM_SYSTEM,
                user=(
                    f"Исходная задача:\n{goal[:2500]}\n\n"
                    f"Вопросы:\n{json.dumps(st.questions, ensure_ascii=False)}\n\n"
                    f"Ответы пользователя:\n{text[:4000]}"
                ),
                upstream_call=upstream_call,
            )
            data = _extract_json(raw) or _heuristic_confirm(goal, text)
        st.spec_summary = str(data.get("spec_summary") or "").strip() or _heuristic_confirm(
            goal, text
        )["spec_summary"]
        st.enriched_prompt = str(data.get("enriched_prompt") or "").strip() or build_enriched_fallback(
            goal=goal, answers=text, spec=st.spec_summary
        )
        st.phase = "confirm"
        return ClarifierTurnResult(
            halt=True,
            phase="confirm",
            user_text=format_confirm_message(st.spec_summary),
            state=st,
            model_id=model,
            prompt_tokens=pt,
            completion_tokens=ct,
        )

    # --- CONFIRM: yes → done; else revise ---
    if st.phase == "confirm":
        if is_approval(text):
            st.phase = "done"
            if not st.enriched_prompt:
                st.enriched_prompt = build_enriched_fallback(
                    goal=st.original_goal,
                    answers=st.answers,
                    spec=st.spec_summary,
                )
            return ClarifierTurnResult(
                halt=False,
                phase="done",
                user_text=st.enriched_prompt,
                state=st,
                model_id=model,
                meta={"brief_approved": True},
            )

        # Revisions
        st.revision_count += 1
        if st.revision_count > MAX_CONFIRM_REVISIONS:
            # Force proceed with current spec
            st.phase = "done"
            st.enriched_prompt = build_enriched_fallback(
                goal=st.original_goal,
                answers=f"{st.answers}\n\nПравки (учтены частично):\n{text}",
                spec=st.spec_summary + f"\n— Правки: {text[:500]}",
            )
            return ClarifierTurnResult(
                halt=False,
                phase="done",
                user_text=st.enriched_prompt,
                state=st,
                model_id=model,
                meta={"brief_approved": True, "forced_after_revisions": True},
            )

        goal = st.original_goal
        if _heuristic() or not model:
            data = _heuristic_confirm(goal, f"{st.answers}\nПравки: {text}")
            pt, ct = 0, 10
        else:
            raw, pt, ct = await _call_model(
                model_id=model,
                system=_REVISE_SYSTEM,
                user=(
                    f"Исходная задача:\n{goal[:2000]}\n\n"
                    f"Текущее ТЗ:\n{st.spec_summary[:2000]}\n\n"
                    f"Правки пользователя:\n{text[:3000]}"
                ),
                upstream_call=upstream_call,
            )
            data = _extract_json(raw) or _heuristic_confirm(
                goal, f"{st.answers}\nПравки: {text}"
            )
        st.spec_summary = str(data.get("spec_summary") or st.spec_summary).strip()
        st.enriched_prompt = str(data.get("enriched_prompt") or st.enriched_prompt).strip()
        st.phase = "confirm"
        return ClarifierTurnResult(
            halt=True,
            phase="confirm",
            user_text=format_confirm_message(st.spec_summary),
            state=st,
            model_id=model,
            prompt_tokens=pt,
            completion_tokens=ct,
            meta={"revision": st.revision_count},
        )

    # done/skip passthrough
    return ClarifierTurnResult(
        halt=False,
        phase=st.phase,
        user_text=st.enriched_prompt or text,
        state=st,
        model_id=model,
    )


def apply_enriched_to_messages(
    messages: list[dict[str, Any]],
    enriched: str,
) -> list[dict[str, Any]]:
    """Replace last user message content with enriched prompt."""
    out = [dict(m) for m in (messages or [])]
    for i in range(len(out) - 1, -1, -1):
        if (out[i].get("role") or "").lower() == "user":
            out[i] = {**out[i], "content": enriched}
            return out
    out.append({"role": "user", "content": enriched})
    return out
