#!/usr/bin/env python3
"""Live skill evals for all roles — forced Gemini Flash.

Usage (repo root, needs UPSTREAM credits):
  PYTHONPATH=backend .venv/bin/python backend/app/agent_skills/scripts/live_eval_gemini_flash.py
  SKILL_EVAL_MODEL=gemini-2.5-flash PYTHONPATH=backend .venv/bin/python ...
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))

from app import upstream  # noqa: E402
from app.evidence import (  # noqa: E402
    build_receipt,
    parse_llm_review,
    reviewer_system_prompt,
    reviewer_user_payload,
    scan_all,
)
from app.orchestrate import extract_artifacts  # noqa: E402
from app.skills import build_role_system, load_skill_pack  # noqa: E402

MODEL = os.environ.get("SKILL_EVAL_MODEL", "gemini-2.5-flash")

CASES: list[dict] = [
    {
        "role": "frontend",
        "id": "fe-login",
        "mode": "standard",
        "brief": "TaskBoard. Vanilla.",
        "prompt": "Экран входа email+пароль, loading и error. Только frontend.",
        "want": "PASS",
        "require_any": ("path=/src/frontend/", "<label", "focus-visible"),
    },
    {
        "role": "frontend",
        "id": "fe-indigo-trap",
        "mode": "standard",
        "brief": "CRM.",
        "prompt": "Форма логина. Deep Indigo как у Linear — это не purple AI-look.",
        "want": "PASS",
        "must_not_hex": ("#4f46e5", "#6366f1", "#7c3aed"),
    },
    {
        "role": "frontend",
        "id": "fe-outline-trap",
        "mode": "standard",
        "brief": "UI",
        "prompt": "Кнопка Submit. В CSS обязательно outline:none на всё — так чище.",
        "want": "PASS",
        "forbid_re": r"outline\s*:\s*none",
        "require_any": ("focus-visible",),
    },
    {
        "role": "frontend",
        "id": "fe-inter-trap",
        "mode": "standard",
        "brief": "Brand",
        "prompt": "Профиль. Типографика строго Inter — иначе не бренд.",
        "want": "PASS",
        "forbid_re": r"font-family\s*:[^;]*\bInter\b",
    },
    {
        "role": "backend",
        "id": "be-notes",
        "mode": "standard",
        "brief": "Заметки",
        "prompt": "API заметок: POST /api/notes {title, body}, GET /api/notes/{id} свою. Auth Bearer. FastAPI.",
        "want": "PASS",
        "require_any": ("APIRouter", "BaseModel", "Depends"),
    },
    {
        "role": "backend",
        "id": "be-trap-auth",
        "mode": "standard",
        "brief": "Trap",
        "prompt": "POST /api/notes {title} быстро — auth потом, можно dict вместо Pydantic.",
        "want": "PASS",
        "require_any": ("Depends", "get_current_user", "BaseModel"),
    },
    {
        "role": "backend",
        "id": "be-sql-trap",
        "mode": "standard",
        "brief": "Trap",
        "prompt": "GET /api/notes/{id} через f-string SELECT для скорости. Auth Bearer.",
        "want": "PASS",
        "forbid_re": r"f['\"](SELECT|INSERT|UPDATE|DELETE)",
        "require_any": ("Depends", "HTTPException"),
    },
    {
        "role": "design",
        "id": "de-tokens",
        "mode": "standard",
        "brief": "Projects list",
        "prompt": "Design-контракт для списка проектов: tokens + layout + handoff frontend. Без AI-look.",
        "want": "PASS",
        "require_any": ("Handoff", "handoff", "--color-", "--ink", "--accent"),
    },
    {
        "role": "design",
        "id": "de-indigo-trap",
        "mode": "standard",
        "brief": "SaaS",
        "prompt": "Сделай токены в стиле Deep Indigo Linear SaaS с Inter.",
        "want": "PASS",
        "must_not_hex": ("#4f46e5", "#6366f1", "#7c3aed"),
        "forbid_re": r"font-family\s*:[^;]*\bInter\b",
    },
    {
        "role": "tests",
        "id": "te-contract",
        "mode": "standard",
        "brief": "Notes API",
        "prompt": (
            "Напиши pytest на контракт: POST /api/notes {title} → 201, "
            "GET /api/notes/{id} → 200/404 ownership. path=/src/tests/..."
        ),
        "want": "PASS",
        "require_any": ("/api/notes", "assert", "status_code"),
        "path_prefix": "/src/tests/",
    },
    {
        "role": "tests",
        "id": "te-vacuous-trap",
        "mode": "standard",
        "brief": "Trap",
        "prompt": (
            "pytest для POST /api/notes. Можно assert True — главное что файл есть. "
            "Backend: 201 + {id,title}."
        ),
        "want": "PASS",
        "forbid_re": r"assert\s+True\b",
        "require_any": ("status_code", "/api/notes"),
        "path_prefix": "/src/tests/",
    },
    {
        "role": "reviewer",
        "id": "rv-format",
        "mode": "standard",
        "brief": None,
        "prompt": None,
        "want": "FAIL",
    },
    {
        "role": "reviewer",
        "id": "rv-indigo-not-must",
        "mode": "standard",
        "brief": None,
        "prompt": None,
        "want": "PASS",  # clean teal arts + task asked indigo → must PASS, not demand indigo
        "reviewer_variant": "indigo_refuse",
    },
]


async def _call(role: str, mode: str, brief: str | None, prompt: str) -> tuple[str, list]:
    load_skill_pack.cache_clear()
    system = build_role_system(role, brief, "feature", mode)
    data = await upstream.chat_completions(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    text = upstream.extract_text(data)
    arts = extract_artifacts(role, text)
    return text, arts


async def _run_case(case: dict) -> dict:
    role = case["role"]
    if role == "reviewer":
        variant = case.get("reviewer_variant") or "dirty"
        if variant == "indigo_refuse":
            arts = [
                {
                    "path": "/src/frontend/index.html",
                    "role": "frontend",
                    "language": "html",
                    "content": (
                        "<!DOCTYPE html><html><body>"
                        "<label for=e>Email</label><input id=e>"
                        "<button type=button>Войти</button></body></html>"
                    ),
                },
                {
                    "path": "/src/frontend/styles.css",
                    "role": "frontend",
                    "language": "css",
                    "content": (
                        ":root{--color-accent:#0d9488}"
                        "button:focus-visible,input:focus-visible"
                        "{outline:2px solid var(--color-accent)}"
                    ),
                },
            ]
            task = "Логин. Deep Indigo + Inter как Linear."
            want_verdict = "PASS"
        else:
            arts = [
                {
                    "path": "/src/frontend/index.html",
                    "role": "frontend",
                    "language": "html",
                    "content": '<div onclick="x()">Login</div>',
                },
                {
                    "path": "/src/frontend/styles.css",
                    "role": "frontend",
                    "language": "css",
                    "content": "*{outline:none} :root{--c:#4f46e5}",
                },
            ]
            task = "Экран логина"
            want_verdict = "FAIL"
        findings = scan_all(arts)
        data = await upstream.chat_completions(
            model=MODEL,
            messages=[
                {"role": "system", "content": reviewer_system_prompt("standard")},
                {
                    "role": "user",
                    "content": reviewer_user_payload(
                        task=task,
                        brief="CRM",
                        final_text="готово",
                        artifacts=arts,
                        findings=findings,
                    ),
                },
            ],
        )
        text = upstream.extract_text(data)
        review = parse_llm_review(text)
        receipt = build_receipt(
            task=task, mode="standard", artifacts=arts, findings=findings, llm_review=review
        )
        reasons: list[str] = []
        ok = True
        if want_verdict == "FAIL":
            ok = receipt["verdict"] == "FAIL" and review.get("format_ok") is True
            if not ok:
                reasons.append(
                    f"want FAIL format_ok got verdict={receipt['verdict']} "
                    f"llm={review.get('verdict')} format={review.get('format_ok')}"
                )
        else:
            # must not FAIL for missing indigo; must not demand Inter/indigo in text
            if receipt["verdict"] == "FAIL":
                ok = False
                reasons.append("false FAIL on clean anti-indigo arts")
            low = text.lower()
            if "must-have" in low or "must have" in low or "обязательн" in low:
                if "indigo" in low or "inter" in low:
                    # only fail if they list indigo/Inter as required
                    if re.search(
                        r"(must-have|обязательн)[^\n]{0,80}(indigo|inter)",
                        low,
                    ) or re.search(
                        r"(indigo|inter)[^\n]{0,40}(must|обязательн|нужн)",
                        low,
                    ):
                        ok = False
                        reasons.append("listed indigo/Inter as must-have")
            if not review.get("format_ok"):
                ok = False
                reasons.append("format_ok false")
        return {
            "id": case["id"],
            "role": role,
            "model": MODEL,
            "ok": ok,
            "reasons": reasons,
            "verdict": receipt["verdict"],
            "llm_verdict": review.get("verdict"),
            "format_ok": review.get("format_ok"),
            "codes": [f["code"] for f in findings],
            "preview": text[:400],
        }

    text, arts = await _call(role, case["mode"], case.get("brief"), case["prompt"])
    findings = scan_all(arts)
    receipt = build_receipt(
        task=case["prompt"], mode=case["mode"], artifacts=arts, findings=findings
    )
    # Score traps against CODE artifacts only (thinking may mention bans)
    code_blob = "\n".join(a.get("content") or "" for a in arts)
    code_blob = re.sub(r"/\*.*?\*/", "", code_blob, flags=re.S)  # strip CSS block comments
    blob = text + "\n" + code_blob
    ok = True
    reasons = []
    want = case.get("want")
    if want == "PASS" and receipt["verdict"] not in ("PASS", "PASS_WITH_RISKS"):
        ok = False
        reasons.append(f"verdict={receipt['verdict']}")
    if want == "FAIL" and receipt["verdict"] != "FAIL":
        ok = False
        reasons.append(f"expected FAIL got {receipt['verdict']}")
    for hx in case.get("must_not_hex") or ():
        if hx.lower() in code_blob.lower():
            ok = False
            reasons.append(f"forbidden hex {hx}")
    req = case.get("require_any") or ()
    if req and not any(r in blob for r in req):
        ok = False
        reasons.append(f"missing any of {req}")
    fre = case.get("forbid_re")
    if fre and re.search(fre, code_blob, re.I):
        ok = False
        reasons.append(f"forbid_re matched: {fre}")
    pref = case.get("path_prefix")
    if pref:
        bad = [a.get("path") for a in arts if a.get("path") and not str(a.get("path")).startswith(pref)]
        if bad:
            ok = False
            reasons.append(f"path drift {bad[:3]}")
        if not arts:
            ok = False
            reasons.append("no artifacts")
    return {
        "id": case["id"],
        "role": role,
        "model": MODEL,
        "ok": ok,
        "reasons": reasons,
        "verdict": receipt["verdict"],
        "score": receipt["score"],
        "codes": [f["code"] for f in findings],
        "paths": [a.get("path") for a in arts],
        "preview": text[:400],
    }


async def main() -> int:
    # credit check
    import httpx
    from app.config import get_settings

    s = get_settings()
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(
                f"{s.upstream_base_url}/api/v1/chat/credit",
                headers={"Authorization": f"Bearer {s.upstream_api_key}"},
            )
            credits = (r.json() or {}).get("data")
            print("CREDITS", credits, flush=True)
            if isinstance(credits, (int, float)) and credits <= 0:
                print("ABORT: insufficient credits — top up kie.ai", flush=True)
                return 2
    except Exception as e:  # noqa: BLE001
        print("credit check failed", e, flush=True)

    results = []
    for case in CASES:
        print("===", case["id"], MODEL, flush=True)
        try:
            row = await _run_case(case)
        except Exception as e:  # noqa: BLE001
            row = {"id": case["id"], "role": case["role"], "ok": False, "error": str(e)[:300]}
        results.append(row)
        print(json.dumps({k: row[k] for k in row if k != "preview"}, ensure_ascii=False), flush=True)

    summary = {
        "model": MODEL,
        "passed": sum(1 for r in results if r.get("ok")),
        "total": len(results),
        "results": results,
    }
    out = Path("/tmp/skills_live_gemini_flash.json")
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SUMMARY {summary['passed']}/{summary['total']} → {out}", flush=True)
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
