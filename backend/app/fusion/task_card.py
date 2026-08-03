"""Typed, cache-stable Task Card contract for the ZeusCode coding crew."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

TaskCardTier = Literal["compact", "serious"]

CARD_VERSION = 1
_MAX_GOAL = 1600
_MAX_MOTIVATION = 1200
_MAX_SCOPE_ITEM = 300
_MAX_CRITERION = 400
_MAX_ASSIGNMENT = 800


def _sanitize_card_text(value: Any) -> str:
    """Redact credentials/control sequences while preserving task meaning."""
    text = str(value or "").replace("\x00", "")
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = "".join(
        ch for ch in text if ch in "\n\t" or ord(ch) >= 32 and ord(ch) != 127
    )
    text = re.sub(
        r"(?i)\b(Authorization\s*:\s*(?:Bearer|Basic)\s+)\S+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password|passwd)\s*([=:]\s*)\S+",
        r"\1\2[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)\b(?:zeus_|sk-|ghp_|github_pat_)[A-Za-z0-9._-]{12,}",
        "[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)\b(https?://)([^/@\s:]+):([^/@\s]+)@",
        r"\1[REDACTED]@",
        text,
    )
    return text


def _text(value: Any, limit: int) -> str:
    return " ".join(_sanitize_card_text(value).split())[:limit]


def _strings(value: Any, *, limit: int, count: int) -> list[str]:
    source = value if isinstance(value, (list, tuple)) else [value]
    out: list[str] = []
    for item in source:
        text = _text(item, limit)
        if text and text not in out:
            out.append(text)
        if len(out) >= count:
            break
    return out


def _json_object(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    text = str(raw or "").strip()
    if not text:
        return {}
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        value = json.loads(text[start : end + 1])
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def task_card_tier(
    *,
    user_q: str,
    zeus: dict[str, Any] | None = None,
) -> TaskCardTier:
    """Use explicit/structural signals only; never a task-label regex or score."""
    data = zeus if isinstance(zeus, dict) else {}
    explicit = str(data.get("task_card_tier") or "").strip().lower()
    if explicit in ("compact", "serious"):
        return explicit  # type: ignore[return-value]
    if (
        data.get("serious") is True
        or data.get("high_risk") is True
        or data.get("multi_system") is True
        or bool(data.get("risk_profile"))
        or str(data.get("effort") or "").strip().lower() in ("high", "max")
        or len(user_q or "") >= 5000
    ):
        return "serious"
    return "compact"


@dataclass(frozen=True)
class TaskCard:
    goal: str
    motivation: str
    scope: list[str]
    test_command: str
    done_criteria: list[str]
    assignments: dict[str, str]
    tier: TaskCardTier = "compact"
    version: int = CARD_VERSION
    degraded: bool = False
    critique_applied: bool = False
    card_id: str = ""
    critique_summary: str = ""

    def __post_init__(self) -> None:
        canonical = self.canonical_dict(include_id=False)
        digest = hashlib.sha256(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:20]
        object.__setattr__(self, "card_id", self.card_id or f"tc_{digest}")

    def canonical_dict(self, *, include_id: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "version": CARD_VERSION,
            "tier": self.tier,
            "goal": _text(self.goal, _MAX_GOAL),
            "motivation": _text(self.motivation, _MAX_MOTIVATION),
            "scope": _strings(self.scope, limit=_MAX_SCOPE_ITEM, count=20),
            "test_command": _text(self.test_command, 500),
            "done_criteria": _strings(
                self.done_criteria, limit=_MAX_CRITERION, count=16
            ),
            "assignments": {
                role: _text(self.assignments.get(role), _MAX_ASSIGNMENT)
                for role in ("leader", "doer", "analyst", "verifier")
                if _text(self.assignments.get(role), _MAX_ASSIGNMENT)
            },
            "degraded": bool(self.degraded),
            "critique_applied": bool(self.critique_applied),
            "critique_summary": _text(self.critique_summary, 1000),
        }
        if include_id:
            payload["card_id"] = self.card_id
        return payload

    def to_dict(self) -> dict[str, Any]:
        return self.canonical_dict()

    def stable_prefix(self) -> str:
        """Byte-stable, bounded execution contract used as the cache prefix."""
        payload = {
            "version": CARD_VERSION,
            "tier": self.tier,
            "card_id": self.card_id,
            "goal": _text(self.goal, 800),
            "motivation": _text(self.motivation, 300),
            "scope": _strings(self.scope, limit=120, count=8),
            "test_command": _text(self.test_command, 250),
            "done_criteria": _strings(
                self.done_criteria, limit=180, count=6
            ),
            "assignments": {
                role: _text(self.assignments.get(role), 280)
                for role in ("leader", "doer", "analyst", "verifier")
                if _text(self.assignments.get(role), 280)
            },
            "degraded": bool(self.degraded),
            "critique_applied": bool(self.critique_applied),
        }
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )


def fallback_task_card(
    user_q: str,
    *,
    tier: TaskCardTier = "compact",
    degraded: bool = True,
) -> TaskCard:
    goal = _text(user_q, _MAX_GOAL) or "Complete the requested coding task safely."
    return TaskCard(
        tier=tier,
        goal=goal,
        motivation="Deliver the requested behavior without unrelated changes.",
        scope=["Inspect only relevant files", "Make the smallest safe implementation"],
        test_command="",
        done_criteria=[
            "Requested behavior is implemented",
            "Relevant deterministic tests or compile checks are green",
            "No unrelated working-tree changes are reverted",
        ],
        assignments={
            "leader": "Own and revise this Task Card.",
            "doer": "Inspect, implement, and use client tools.",
            "analyst": "Diagnose only a fresh failed tool event.",
            "verifier": "Select a test only when no deterministic command is known.",
        },
        degraded=degraded,
    )


def parse_task_card(
    raw: str | dict[str, Any] | None,
    *,
    user_q: str,
    tier: TaskCardTier,
    degraded: bool = False,
    critique_applied: bool = False,
) -> TaskCard:
    data = _json_object(raw)
    fallback = fallback_task_card(user_q, tier=tier, degraded=True)
    if (
        not isinstance(data.get("goal"), str)
        or not isinstance(data.get("done_criteria"), list)
        or not all(isinstance(item, str) for item in data["done_criteria"])
        or not isinstance(data.get("assignments"), dict)
        or not all(
            isinstance(role, str) and isinstance(instruction, str)
            for role, instruction in data["assignments"].items()
        )
        or ("scope" in data and not isinstance(data.get("scope"), list))
        or (
            isinstance(data.get("scope"), list)
            and not all(isinstance(item, str) for item in data["scope"])
        )
        or ("motivation" in data and not isinstance(data.get("motivation"), str))
        or ("test_command" in data and not isinstance(data.get("test_command"), str))
    ):
        return fallback
    goal = _text(data.get("goal"), _MAX_GOAL)
    criteria = _strings(data.get("done_criteria"), limit=_MAX_CRITERION, count=16)
    raw_assignments = data.get("assignments")
    assignments = (
        {
            str(role): _text(instruction, _MAX_ASSIGNMENT)
            for role, instruction in raw_assignments.items()
            if str(role) in {"leader", "doer", "analyst", "verifier"}
            and _text(instruction, _MAX_ASSIGNMENT)
        }
        if isinstance(raw_assignments, dict)
        else {}
    )
    valid = bool(goal and criteria and assignments.get("leader") and assignments.get("doer"))
    if not valid:
        return fallback
    return TaskCard(
        tier=tier,
        goal=goal,
        motivation=_text(data.get("motivation"), _MAX_MOTIVATION)
        or fallback.motivation,
        scope=_strings(data.get("scope"), limit=_MAX_SCOPE_ITEM, count=20)
        or fallback.scope,
        test_command=_text(data.get("test_command"), 500),
        done_criteria=criteria,
        assignments={**fallback.assignments, **assignments},
        degraded=bool(degraded),
        critique_applied=bool(critique_applied),
        critique_summary=_text(data.get("critique_summary"), 1000),
    )


def card_author_messages(user_q: str, *, tier: TaskCardTier) -> list[dict[str, str]]:
    detail = (
        "This is compact: keep each field short."
        if tier == "compact"
        else "This is serious: include risk boundaries, rollback/safety, and precise gates."
    )
    return [
        {
            "role": "system",
            "content": (
                "You are the ZeusCode Task Card owner. Return one JSON object only with "
                "goal, motivation, scope (array), test_command (possibly empty), "
                "done_criteria (array), and assignments (leader/doer/analyst/verifier). "
                "Keep goal under 800 chars, motivation under 300, at most 8 concise "
                "scope items, 6 done criteria, and each assignment under 280 chars. "
                "The client executes tools; you only define the durable contract. "
                + detail
            ),
        },
        {"role": "user", "content": _text(user_q, 7000)},
    ]


def card_critique_messages(card: TaskCard) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the GPT ZeusCode plan critic. Critique this serious Task Card "
                "once. Return JSON only with omissions, unsafe_assumptions, test_gaps, "
                "and assignment_gaps arrays. Do not write code."
            ),
        },
        {"role": "user", "content": card.stable_prefix()},
    ]


def card_revision_messages(
    user_q: str, draft: TaskCard, critique: str
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You own the final ZeusCode Task Card. Revise the draft using the GPT "
                "critique. Return the complete JSON card only, with the same required "
                "fields. Preserve intent; reject scope expansion."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Request:\n{_text(user_q, 5000)}\n\n"
                f"Draft:\n{draft.stable_prefix()}\n\nCritique:\n{_text(critique, 3500)}"
            ),
        },
    ]


def evidence_hash(evidence: dict[str, Any] | None) -> str:
    """Hash only bounded fresh evidence used by DeepSeek."""
    data = evidence if isinstance(evidence, dict) else {}
    event = data.get("last_tool_event")
    payload = {
        "event": event if isinstance(event, dict) else {},
        "tests_failed": data.get("tests_failed"),
        "build_failed": data.get("build_failed"),
        "compile_failed": data.get("compile_failed"),
        "command_exit_nonzero": data.get("command_exit_nonzero"),
        "ui_broken": data.get("ui_broken"),
    }
    def bounded(value: Any, depth: int = 0) -> Any:
        if depth >= 5:
            return _text(value, 600)
        if isinstance(value, dict):
            return {
                str(key)[:120]: bounded(item, depth + 1)
                for key, item in sorted(value.items(), key=lambda row: str(row[0]))[:80]
            }
        if isinstance(value, (list, tuple)):
            return [bounded(item, depth + 1) for item in value[:80]]
        if isinstance(value, str):
            return value[:4000]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return _text(value, 600)

    blob = json.dumps(
        bounded(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(blob.encode("utf-8", errors="ignore")).hexdigest()


def _valid_critique(raw: str | dict[str, Any] | None) -> bool:
    data = _json_object(raw)
    required = ("omissions", "unsafe_assumptions", "test_gaps", "assignment_gaps")
    return all(
        isinstance(data.get(key), list)
        and all(isinstance(item, str) for item in data[key])
        for key in required
    )


async def bootstrap_task_card(
    *,
    user_q: str,
    tier: TaskCardTier,
    leader_model: str,
    critic_model: str,
    upstream_call: Any,
    cancel_event: Any | None = None,
) -> tuple[TaskCard, list[dict[str, Any]]]:
    """Run compact authoring or exactly draft→critique→final for serious work."""
    phases: list[dict[str, Any]] = []

    async def call(model: str, phase: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        started = time.perf_counter()
        if cancel_event is not None and cancel_event.is_set():
            row = {
                "phase": phase,
                "model_id": model,
                "ok": False,
                "text": "",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
                "latency_s": 0.0,
                "error": "cancelled",
            }
            phases.append(row)
            return row
        try:
            data = await upstream_call(
                model,
                messages,
                temperature=0.1,
                max_tokens=1400 if phase != "critique" else 700,
            )
            row = {
                "phase": phase,
                "model_id": str(data.get("model_id") or model),
                "ok": bool(str(data.get("text") or "").strip()),
                "text": str(data.get("text") or ""),
                "prompt_tokens": int(data.get("prompt_tokens") or 0),
                "completion_tokens": int(data.get("completion_tokens") or 0),
                "cached_tokens": int(data.get("cached_tokens") or 0),
                "latency_s": round(time.perf_counter() - started, 4),
            }
        except Exception as exc:  # noqa: BLE001
            row = {
                "phase": phase,
                "model_id": model,
                "ok": False,
                "text": "",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
                "latency_s": round(time.perf_counter() - started, 4),
                "error": str(exc)[:240],
            }
        phases.append(row)
        return row

    draft_row = await call(
        leader_model, "draft" if tier == "serious" else "compact", card_author_messages(user_q, tier=tier)
    )
    draft = parse_task_card(
        draft_row.get("text"),
        user_q=user_q,
        tier=tier,
        degraded=not draft_row["ok"],
    )
    if tier != "serious":
        return draft, phases

    critique_row = await call(
        critic_model, "critique", card_critique_messages(draft)
    )
    critique_ok = bool(critique_row["ok"] and _valid_critique(critique_row.get("text")))
    critique_row["ok"] = critique_ok
    final_row = await call(
        leader_model,
        "final",
        card_revision_messages(user_q, draft, str(critique_row.get("text") or "")),
    )
    final = parse_task_card(
        final_row.get("text"),
        user_q=user_q,
        tier="serious",
        degraded=not (draft_row["ok"] and critique_ok and final_row["ok"]),
        critique_applied=bool(critique_ok and final_row["ok"]),
    )
    return final, phases
