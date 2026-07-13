#!/usr/bin/env python3
"""Frontend skill eval — same gates as Studio Evidence (playground contract).

Usage (from repo root):
  PYTHONPATH=backend .venv/bin/python backend/app/agent_skills/frontend/scripts/eval_run.py

This is the offline twin of the live playground gate. Browser preview in UI
is separate (iframe srcdoc); Webwright-level proof comes later.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# repo root: .../ultra-mode-mvp
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "backend"))

from app import upstream  # noqa: E402
from app.evidence import build_receipt, scan_all  # noqa: E402
from app.orchestrate import extract_artifacts, model_for_role  # noqa: E402
from app.skills import build_role_system, load_skill_pack  # noqa: E402

TASKS = [
    {
        "id": "login",
        "mode": "standard",
        "brief": "TaskBoard. Vanilla.",
        "prompt": "Экран входа email+пароль, loading и error. Только frontend.",
    },
    {
        "id": "ai_trap",
        "mode": "standard",
        "brief": "InvoiceApp.",
        "prompt": "Красивый wow SaaS hero+login как у AI-стартапов.",
    },
    {
        "id": "indigo_trap",
        "mode": "standard",
        "brief": "CRM.",
        "prompt": "Форма логина. Deep Indigo как у Linear — это не purple AI-look.",
    },
]


async def run_one(t: dict) -> dict:
    load_skill_pack.cache_clear()
    system = build_role_system("frontend", t["brief"], "ui", t["mode"])
    model = model_for_role(t["mode"], "frontend")
    # Prefer cheap Flash for skill evals when set
    import os

    model = os.environ.get("SKILL_EVAL_MODEL", model)
    data = await upstream.chat_completions(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": t["prompt"]},
        ],
    )
    text = upstream.extract_text(data)
    arts = extract_artifacts("frontend", text)
    findings = scan_all(arts)
    receipt = build_receipt(
        task=t["prompt"], mode=t["mode"], artifacts=arts, findings=findings
    )
    return {
        "id": t["id"],
        "verdict": receipt["verdict"],
        "score": receipt["score"],
        "findings": [f["code"] for f in findings],
        "paths": [a.get("path") for a in arts],
    }


async def main() -> None:
    rows = []
    for t in TASKS:
        print("===", t["id"], flush=True)
        row = await run_one(t)
        rows.append(row)
        print(row, flush=True)
    out = Path("/tmp/frontend_skill_eval_latest.json")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        k: sum(1 for r in rows if r["verdict"] == k)
        for k in ("PASS", "PASS_WITH_RISKS", "FAIL")
    }
    print("SUMMARY", summary, "→", out)


if __name__ == "__main__":
    asyncio.run(main())
