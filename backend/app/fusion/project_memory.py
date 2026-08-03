"""Server-side project memory (TZ §5.5 / H5).

Stores decisions, file map, session conclusions keyed by project_id / session.
In-process + optional JSON file under data/ — no routers import.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("zeus.fusion.project_memory")

_LOCK = threading.RLock()
_MEM: dict[str, dict[str, Any]] = {}
_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "project_memory"


def _path(key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)[:120]
    return _DATA_DIR / f"{safe}.json"


def memory_key(*, project_id: str | None = None, session_id: str | None = None) -> str | None:
    pid = (project_id or "").strip()
    sid = (session_id or "").strip()
    if pid:
        return f"proj:{pid[:96]}"
    if sid:
        return f"sess:{sid[:96]}"
    return None


def load_memory(key: str | None) -> dict[str, Any]:
    if not key:
        return {}
    with _LOCK:
        if key in _MEM:
            return dict(_MEM[key])
    path = _path(key)
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                with _LOCK:
                    _MEM[key] = raw
                return dict(raw)
        except (OSError, json.JSONDecodeError) as e:
            log.warning("project_memory load fail key=%s err=%s", key, e)
    return {}


def save_memory(key: str | None, data: dict[str, Any]) -> None:
    if not key or not isinstance(data, dict):
        return
    payload = dict(data)
    payload["updated_at"] = time.time()
    with _LOCK:
        _MEM[key] = payload
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            target = _path(key)
            tmp = target.with_suffix(f".{threading.get_ident()}.tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(target)
        except OSError as e:
            log.warning("project_memory save fail key=%s err=%s", key, e)


def _mutate_memory(
    key: str | None, mutation: Callable[[dict[str, Any]], Any]
) -> Any:
    """Atomically mutate one in-process record under the existing RLock.

    This prevents lost updates between threads in this process only. It does
    not claim distributed or NFS locking semantics.
    """
    if not key:
        return None
    with _LOCK:
        memory = load_memory(key)
        result = mutation(memory)
        save_memory(key, memory)
        return result


def remember_decision(key: str | None, decision: str) -> None:
    if not key or not (decision or "").strip():
        return
    text = decision.strip()[:500]

    def mutate(mem: dict[str, Any]) -> None:
        decisions = list(mem.get("decisions") or [])
        if text not in decisions:
            decisions.append(text)
        mem["decisions"] = decisions[-40:]

    _mutate_memory(key, mutate)


def remember_files(key: str | None, paths: list[str]) -> None:
    if not key or not paths:
        return
    def mutate(mem: dict[str, Any]) -> None:
        files = list(mem.get("files") or [])
        for raw in paths:
            path = str(raw).strip()
            if path and path not in files:
                files.append(path)
        mem["files"] = files[-200:]

    _mutate_memory(key, mutate)


def remember_conclusion(key: str | None, conclusion: str) -> None:
    if not key or not (conclusion or "").strip():
        return
    text = conclusion.strip()[:800]

    def mutate(mem: dict[str, Any]) -> None:
        notes = list(mem.get("conclusions") or [])
        notes.append(text)
        mem["conclusions"] = notes[-20:]

    _mutate_memory(key, mutate)


def _safe_path(path: str) -> str:
    """Reject traversal/absolute/oversized paths before they reach a command."""
    text = str(path or "").strip()
    if (
        not text
        or len(text) > 200
        or text.startswith(("/", "~", "-"))
        or ".." in text
        or "\\" in text
    ):
        return ""
    return text


def remember_test_command(key: str | None, paths: list[str] | None, command: str) -> None:
    """Bind source files to a test command that was actually observed green."""
    from app.fusion.verify import validate_test_command

    # Stored commands are replayed into a prompt and a gate ask, so only a
    # single runnable command may enter the map — never a shell program.
    text = validate_test_command(command)[:300]
    if not key or not text or not paths:
        return
    def mutate(mem: dict[str, Any]) -> None:
        table = dict(mem.get("test_map") or {})
        for raw in paths:
            path = _safe_path(raw)
            if path:
                table[path] = text
        if table:
            # Bounded: newest bindings win when the map overflows.
            mem["test_map"] = dict(list(table.items())[-120:])

    _mutate_memory(key, mutate)


def known_test_commands(key: str | None, paths: list[str] | None) -> list[str]:
    """Green test commands previously recorded for these files, newest first."""
    if not key or not paths:
        return []
    table = load_memory(key).get("test_map")
    if not isinstance(table, dict):
        return []
    out: list[str] = []
    for raw in paths:
        command = table.get(_safe_path(raw))
        if isinstance(command, str) and command and command not in out:
            out.append(command)
    return out


def remember_failed_command(key: str | None, command: str, reason: str = "") -> None:
    """Bank commands the environment rejected so the crew stops retrying them."""
    from app.fusion.verify import sanitize_evidence_text

    # The bank is rendered into a system block, so strip escapes and secrets.
    text = " ".join(sanitize_evidence_text(command, max_chars=200).split())[:200]
    if not key or not text:
        return
    def mutate(mem: dict[str, Any]) -> None:
        bank = [
            row for row in (mem.get("failed_commands") or []) if isinstance(row, dict)
        ]
        for row in bank:
            if row.get("command") == text:
                row["count"] = int(row.get("count") or 1) + 1
                row["reason"] = str(reason or row.get("reason") or "")[:160]
                break
        else:
            bank.append(
                {"command": text, "reason": str(reason or "")[:160], "count": 1}
            )
        mem["failed_commands"] = bank[-40:]

    _mutate_memory(key, mutate)


def failed_commands(key: str | None) -> list[str]:
    if not key:
        return []
    bank = load_memory(key).get("failed_commands")
    if not isinstance(bank, list):
        return []
    return [
        str(row.get("command"))
        for row in bank
        if isinstance(row, dict) and row.get("command")
    ]


def remember_task_card(key: str | None, card: Any) -> None:
    """Persist one validated Task Card in the tenant-scoped memory record."""
    if not key:
        return
    from app.fusion.task_card import TaskCard, parse_task_card

    if isinstance(card, TaskCard):
        validated = card
    elif isinstance(card, dict):
        validated = parse_task_card(
            card,
            user_q=str(card.get("goal") or ""),
            tier="serious" if card.get("tier") == "serious" else "compact",
            degraded=bool(card.get("degraded")),
            critique_applied=bool(card.get("critique_applied")),
        )
    else:
        return

    def mutate(mem: dict[str, Any]) -> None:
        cards = [row for row in (mem.get("task_cards") or []) if isinstance(row, dict)]
        payload = validated.to_dict()
        cards = [row for row in cards if row.get("card_id") != payload["card_id"]]
        cards.append(payload)
        mem["task_cards"] = cards[-20:]
        mem["active_task_card_id"] = payload["card_id"]

    _mutate_memory(key, mutate)


def load_task_card(key: str | None, card_id: str | None = None) -> dict[str, Any] | None:
    if not key:
        return None
    mem = load_memory(key)
    wanted = str(card_id or mem.get("active_task_card_id") or "")
    cards = [row for row in (mem.get("task_cards") or []) if isinstance(row, dict)]
    for row in reversed(cards):
        if not wanted or str(row.get("card_id") or "") == wanted:
            return dict(row)
    return None


def remember_analyst_report(
    key: str | None,
    *,
    card_id: str,
    evidence_hash: str,
    report: dict[str, Any],
) -> None:
    if not key or not card_id or not evidence_hash or not isinstance(report, dict):
        return

    def mutate(mem: dict[str, Any]) -> None:
        reports = [row for row in (mem.get("analyst_reports") or []) if isinstance(row, dict)]
        reports = [
            row
            for row in reports
            if not (
                row.get("card_id") == card_id
                and row.get("evidence_hash") == evidence_hash
            )
        ]
        reports.append(
            {
                "card_id": card_id,
                "evidence_hash": evidence_hash,
                "report": dict(report),
            }
        )
        mem["analyst_reports"] = reports[-40:]

    _mutate_memory(key, mutate)


def load_analyst_report(
    key: str | None, *, card_id: str, evidence_hash: str
) -> dict[str, Any] | None:
    if not key or not card_id or not evidence_hash:
        return None
    rows = load_memory(key).get("analyst_reports")
    if not isinstance(rows, list):
        return None
    for row in reversed(rows):
        if (
            isinstance(row, dict)
            and row.get("card_id") == card_id
            and row.get("evidence_hash") == evidence_hash
            and isinstance(row.get("report"), dict)
        ):
            return dict(row["report"])
    return None


def record_finding(
    key: str | None,
    *,
    card_id: str,
    evidence_hash: str,
    report: dict[str, Any],
) -> None:
    """Create one open DeepSeek finding for one fresh evidence hash."""
    if not key or not card_id or not evidence_hash or not isinstance(report, dict):
        return

    def mutate(mem: dict[str, Any]) -> None:
        findings = [row for row in (mem.get("findings") or []) if isinstance(row, dict)]
        if any(
            row.get("card_id") == card_id
            and row.get("evidence_hash") == evidence_hash
            for row in findings
        ):
            return
        findings.append(
            {
                "card_id": card_id,
                "evidence_hash": evidence_hash,
                "report": dict(report),
                "outcome": "open",
                "created_at": time.time(),
            }
        )
        mem["findings"] = findings[-80:]

    _mutate_memory(key, mutate)


def close_open_findings(
    key: str | None,
    *,
    card_id: str,
    outcome: str = "resolved",
) -> int:
    """Close findings after the next successful machine event."""
    if not key or not card_id or outcome not in {"accepted", "resolved", "irrelevant"}:
        return 0

    def mutate(mem: dict[str, Any]) -> int:
        findings = [row for row in (mem.get("findings") or []) if isinstance(row, dict)]
        closed = 0
        for row in findings:
            if row.get("card_id") == card_id and row.get("outcome") == "open":
                row["outcome"] = outcome
                row["closed_at"] = time.time()
                closed += 1
        if closed:
            mem["findings"] = findings[-80:]
        return closed

    return int(_mutate_memory(key, mutate) or 0)


def finding_outcomes(key: str | None, *, card_id: str | None = None) -> dict[str, int]:
    counts = {"open": 0, "accepted": 0, "resolved": 0, "irrelevant": 0}
    if not key:
        return counts
    rows = load_memory(key).get("findings")
    if not isinstance(rows, list):
        return counts
    for row in rows:
        if not isinstance(row, dict):
            continue
        if card_id and row.get("card_id") != card_id:
            continue
        outcome = str(row.get("outcome") or "open")
        if outcome in counts:
            counts[outcome] += 1
    return counts


def sync_from_evidence(key: str | None, evidence: dict[str, Any] | None) -> None:
    """Persist what the tool loop just proved, so the next task starts informed."""
    if not key or not isinstance(evidence, dict):
        return
    paths = [
        path
        for path in (evidence.get("changed_paths") or [])
        if isinstance(path, str) and _safe_path(path)
    ]
    if paths:
        remember_files(key, paths)
        if evidence.get("fresh_green_test") is True:
            remember_test_command(key, paths, str(evidence.get("test_command") or ""))
    event = evidence.get("last_tool_event")
    if not isinstance(event, dict) or evidence.get("last_event_failed") is not True:
        return
    # A red test is a finding about the code, not about the command; only
    # commands the environment itself rejected belong in the bank.
    if event.get("is_test") or event.get("is_build"):
        return
    code = event.get("return_code")
    if code in (None, 0):
        return
    command = str(event.get("command") or "")
    # 126/127 mean the tool itself is missing or not executable — worth banking
    # even for a reader like `rg`. Any other nonzero exit from a read-only
    # command is usually just a missing file, which says nothing about the tool.
    if code not in (126, 127):
        from app.fusion.verify import _command_is_clearly_read_only

        if _command_is_clearly_read_only(command):
            return
    remember_failed_command(key, command, reason=f"exit {code}")


def format_memory_block(key: str | None, *, max_chars: int = 2400) -> str:
    """Compact block for prompt slot 3 (stable-ish across turns)."""
    mem = load_memory(key)
    if not mem:
        return ""
    parts: list[str] = []
    decisions = mem.get("decisions") or []
    if decisions:
        parts.append("Decisions:\n- " + "\n- ".join(str(d) for d in decisions[-8:]))
    files = mem.get("files") or []
    if files:
        parts.append("Files:\n- " + "\n- ".join(str(f) for f in files[-24:]))
    conclusions = mem.get("conclusions") or []
    if conclusions:
        parts.append("Last conclusions:\n- " + "\n- ".join(str(c) for c in conclusions[-4:]))
    table = mem.get("test_map")
    if isinstance(table, dict) and table:
        parts.append(
            "Known green tests:\n- "
            + "\n- ".join(
                f"{path} → {command}" for path, command in list(table.items())[-8:]
            )
        )
    bank = [row for row in (mem.get("failed_commands") or []) if isinstance(row, dict)]
    if bank:
        parts.append(
            "Commands that failed here (do not retry as-is):\n- "
            + "\n- ".join(
                f"{row.get('command')}" + (f" — {row['reason']}" if row.get("reason") else "")
                for row in bank[-6:]
            )
        )
    taste = mem.get("taste_urls") or []
    if taste:
        parts.append("User taste refs:\n- " + "\n- ".join(str(u) for u in taste[-6:]))
    blob = "\n\n".join(parts).strip()
    return blob[:max_chars]


def remember_taste_urls(key: str | None, urls: list[str]) -> None:
    if not key or not urls:
        return

    def mutate(mem: dict[str, Any]) -> None:
        cur = list(mem.get("taste_urls") or [])
        for raw in urls:
            url = str(raw).strip()
            if url.startswith("http") and url not in cur:
                cur.append(url)
        mem["taste_urls"] = cur[-30:]

    _mutate_memory(key, mutate)


def reset_memory_for_tests() -> None:
    with _LOCK:
        _MEM.clear()
