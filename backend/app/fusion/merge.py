"""File-aware merge (Epic 4 / AD-26 / FR-18.6).

Assembly by Brief ``files_hint`` / ``// file:`` markers.
No conflict → no extra top-level LLM call.
Conflict / broken API seam → one strong (≥950) else curator call.
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from .model_power import TEST_AUTHOR_MIN, power_score
from .types import BranchUsage

UpstreamCall = Callable[..., Awaitable[dict[str, Any]]]

_FILE_RE = re.compile(
    r"(?m)^(?://|#|--)\s*file:\s*([^\s]+)\s*$",
)


def extract_file_sections(text: str) -> dict[str, str]:
    """Split artifact text into path → body using ``// file:`` / ``# file:`` markers."""
    raw = text or ""
    matches = list(_FILE_RE.finditer(raw))
    if not matches:
        return {}
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        path = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = raw[start:end].strip()
        if path:
            out[path] = body
    return out


def detect_file_conflicts(chunks: list[dict[str, Any]]) -> list[str]:
    """Paths claimed by more than one component with different non-empty bodies."""
    owners: dict[str, list[tuple[str, str]]] = {}
    for ch in chunks or []:
        cid = str(ch.get("component_id") or ch.get("id") or "?")
        text = str(ch.get("answer") or ch.get("text") or "")
        sections = extract_file_sections(text)
        hints = ch.get("files_hint") or []
        if not sections and hints:
            # Whole answer attributed to first hint
            path = str(hints[0]).strip()
            if path and text.strip():
                sections = {path: text.strip()}
        for path, body in sections.items():
            owners.setdefault(path, []).append((cid, body))

    conflicts: list[str] = []
    for path, rows in owners.items():
        if len(rows) < 2:
            continue
        bodies = {b for _, b in rows if (b or "").strip()}
        if len(bodies) > 1:
            conflicts.append(path)
    return conflicts


def _assemble_by_path(
    chunks: list[dict[str, Any]],
    *,
    brief: dict[str, Any] | None,
) -> tuple[str, dict[str, str], str]:
    """Return (answer, files_map, strategy)."""
    files: dict[str, str] = {}
    order: list[str] = []
    # Prefer Brief files_hint order
    if isinstance(brief, dict):
        for c in brief.get("components") or []:
            if not isinstance(c, dict):
                continue
            for h in c.get("files_hint") or []:
                p = str(h).strip()
                if p and p not in order:
                    order.append(p)

    for ch in chunks or []:
        text = str(ch.get("answer") or ch.get("text") or "")
        sections = extract_file_sections(text)
        hints = [str(h).strip() for h in (ch.get("files_hint") or []) if str(h).strip()]
        if not sections:
            if hints and text.strip():
                sections = {hints[0]: text.strip()}
            elif text.strip():
                cid = str(ch.get("component_id") or "chunk")
                sections = {f"{cid}.txt": text.strip()}
        for path, body in sections.items():
            if path not in order:
                order.append(path)
            # First writer wins unless conflict handler overwrites
            if path not in files or not files[path].strip():
                files[path] = body

    parts = [f"// file: {p}\n{files[p]}" for p in order if p in files and files[p].strip()]
    if not parts:
        # Fallback concat
        blob = "\n\n".join(
            str(c.get("answer") or c.get("text") or "")
            for c in (chunks or [])
            if str(c.get("answer") or c.get("text") or "").strip()
        )
        return blob, files, "concat_fallback"
    return "\n\n".join(parts), files, "file_aware"


def merge_artifacts(
    chunks: list[dict[str, Any]],
    *,
    brief: dict[str, Any] | None = None,
    strong_model: str | None = None,
    curator_model: str | None = None,
    upstream_call: UpstreamCall | None = None,
    cancel_event: Any = None,
) -> dict[str, Any]:
    """Sync entry: file-aware assemble; flag conflict for optional async resolve."""
    answer, files, strategy = _assemble_by_path(chunks, brief=brief)
    conflicts = detect_file_conflicts(chunks)
    api_broken = False
    if isinstance(brief, dict):
        api = str(brief.get("api_contract") or "").strip()
        if api and answer and api.split()[0:1]:
            # Soft seam check: first token of api_contract should appear if short identifier
            token = api.split()[0].strip("`'\"")
            if len(token) >= 3 and token.isidentifier() and token not in answer:
                api_broken = True

    need_strong = bool(conflicts) or api_broken
    result: dict[str, Any] = {
        "answer": answer,
        "merged": True,
        "strategy": strategy,
        "conflict": need_strong,
        "conflict_paths": conflicts,
        "api_seam_broken": api_broken,
        "files": files,
        "brief": brief,
        "conflict_call": False,
        "conflict_branch": None,
    }
    if not need_strong:
        return result

    # Sync path cannot await — mark for caller; if no upstream, keep file_aware + note
    resolver = strong_model or curator_model
    if resolver and power_score(resolver) < TEST_AUTHOR_MIN and strong_model:
        resolver = strong_model
    if not resolver:
        result["strategy"] = "file_aware_conflict_unresolved"
        return result

    # If upstream provided, caller should use merge_artifacts_async; keep sync safe
    if upstream_call is None:
        result["strategy"] = "file_aware_needs_conflict_resolve"
        result["conflict_model"] = resolver
        return result

    # Sync callers accidentally passing upstream — leave unresolved (async preferred)
    result["conflict_model"] = resolver
    result["strategy"] = "file_aware_needs_conflict_resolve"
    return result


async def merge_artifacts_async(
    chunks: list[dict[str, Any]],
    *,
    brief: dict[str, Any] | None = None,
    strong_model: str | None = None,
    curator_model: str | None = None,
    upstream_call: UpstreamCall | None = None,
    cancel_event: Any = None,
) -> dict[str, Any]:
    """File-aware merge with optional one strong conflict call."""
    base = merge_artifacts(
        chunks,
        brief=brief,
        strong_model=strong_model,
        curator_model=curator_model,
        upstream_call=None,
        cancel_event=cancel_event,
    )
    if not base.get("conflict"):
        return base

    resolver = (
        strong_model
        if strong_model and power_score(strong_model) >= TEST_AUTHOR_MIN
        else None
    ) or curator_model or strong_model
    if not resolver or upstream_call is None:
        base["strategy"] = "file_aware_conflict_unresolved"
        return base

    if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
        base["strategy"] = "file_aware_conflict_cancelled"
        return base

    prompt = (
        "Merge conflicting file sections into one coherent multi-file answer. "
        "Use `// file: path` markers. Prefer Brief API/files contract.\n\n"
        f"Brief: {brief}\n\n"
        f"Conflict paths: {base.get('conflict_paths')}\n"
        f"API seam broken: {base.get('api_seam_broken')}\n\n"
        "Artifacts:\n"
        + "\n---\n".join(
            f"[{c.get('component_id')}]\n{c.get('answer') or ''}" for c in (chunks or [])
        )[:12000]
    )
    try:
        data = await upstream_call(
            resolver,
            [
                {
                    "role": "system",
                    "content": "You are Zeus conflict merger. One merged answer only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=8192,
        )
        text = str((data or {}).get("text") or "").strip()
        pt = int((data or {}).get("prompt_tokens") or 0)
        ct = int((data or {}).get("completion_tokens") or 0)
        ok = bool((data or {}).get("ok", True)) and bool(text)
        base["conflict_call"] = True
        base["conflict_branch"] = BranchUsage(
            model_id=resolver,
            billable_state="completed" if ok else "cancelled_no_tokens",
            prompt_tokens=pt,
            completion_tokens=ct,
            # AD-26: conflict call is strong/Architect-class, not escalate judge_fix
            role="architect",
            meta={"conflict_merge": True, "paths": base.get("conflict_paths")},
        )
        if text:
            base["answer"] = text
            base["strategy"] = "file_aware_conflict_strong"
            base["files"] = extract_file_sections(text) or base.get("files") or {}
        else:
            base["strategy"] = "file_aware_conflict_failed"
    except Exception as e:  # noqa: BLE001
        base["strategy"] = "file_aware_conflict_error"
        base["error"] = str(e)[:200]
        base["conflict_call"] = False
    return base
