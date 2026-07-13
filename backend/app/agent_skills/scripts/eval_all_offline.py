#!/usr/bin/env python3
"""Offline workability battery for all Studio skill packs (no upstream credits).

Usage (repo root):
  PYTHONPATH=backend .venv/bin/python backend/app/agent_skills/scripts/eval_all_offline.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))

from app.evidence import (  # noqa: E402
    build_receipt,
    reviewer_system_prompt,
    reviewer_user_payload,
    scan_all,
)
from app.orchestrate import extract_artifacts  # noqa: E402
from app.skills import build_role_system, load_skill_pack  # noqa: E402

SKILLS = ROOT / "backend" / "app" / "agent_skills"


def _verify_templates() -> dict:
    out = {}
    for role in ("frontend", "backend", "design", "tests"):
        sh = SKILLS / role / "scripts" / "verify.sh"
        tmpl = SKILLS / role / "assets" / "templates"
        if not sh.is_file() or not tmpl.is_dir():
            out[role] = {"ok": False, "err": "missing"}
            continue
        proc = subprocess.run(
            ["bash", str(sh), str(tmpl)], capture_output=True, text=True, timeout=30
        )
        out[role] = {"ok": proc.returncode == 0}
    return out


def _score(role: str, text: str) -> dict:
    arts = extract_artifacts(role, text)
    findings = scan_all(arts) if arts else []
    receipt = (
        build_receipt(task=role, mode="standard", artifacts=arts, findings=findings)
        if arts
        else None
    )
    blob = text.lower()
    structure = (
        ("## мышление" in blob and "## результат" in blob and f"path=/src/{role}/" in text)
        if role != "reviewer"
        else ("## вердикт" in blob or "pass" in blob)
    )
    return {
        "arts": len(arts),
        "structure_ok": structure,
        "verdict": (receipt or {}).get("verdict"),
        "score": (receipt or {}).get("score"),
        "codes": [f["code"] for f in findings],
    }


TRAPS = [
    (
        "frontend",
        "bad",
        """## Мышление\nx\n## Результат\n```html path=/src/frontend/index.html\n<div onclick=x()>x</div>\n```\n```css path=/src/frontend/s.css\n*{outline:none}:root{--c:#4f46e5}\n```\n""",
        "FAIL",
    ),
    (
        "frontend",
        "good",
        """## Мышление\nx\n## Результат\n```html path=/src/frontend/index.html\n<!DOCTYPE html><html><body><label for=e>Email</label><input id=e><button type=button id=go>Go</button></body></html>\n```\n```css path=/src/frontend/s.css\n:root{--color-accent:#0d9488}button:focus-visible,input:focus-visible{outline:2px solid #0d9488}\n```\n```js path=/src/frontend/app.js\ndocument.getElementById('go').onclick=()=>{}\n```\n""",
        "PASS",
    ),
    (
        "backend",
        "bad",
        """## Мышление\nx\n## Результат\n```python path=/src/backend/r.py\nSECRET='sk-abcdefghijklmnopqrstuvwxyz012345'\ndef g(i):\n  return f'SELECT {i}'\n```\n""",
        "FAIL",
    ),
    (
        "backend",
        "good",
        """## Мышление\nx\n## Результат\n```python path=/src/backend/schemas/n.py\nfrom pydantic import BaseModel, Field\nclass In(BaseModel):\n  title: str = Field(min_length=1)\n```\n```python path=/src/backend/routers/n.py\nfrom fastapi import APIRouter, Depends, HTTPException\nfrom schemas.n import In\nrouter=APIRouter()\nclass U: id=1\ndef get_current_user(): return U()\n@router.post('/api/notes')\nasync def c(b: In, u=Depends(get_current_user)):\n  return {'id':1,'title':b.title,'user_id':u.id}\n@router.get('/api/notes/{id}')\nasync def g(id:int, u=Depends(get_current_user)):\n  if id!=1: raise HTTPException(404,'Not found')\n  return {'id':id,'title':'t','user_id':u.id}\n```\n""",
        "PASS",
    ),
    (
        "design",
        "bad",
        """## Мышление\nx\n## Результат\n```css path=/src/design/tokens.css\n:root{--color-accent:#6366f1;--font:Inter}\n```\n""",
        "FAIL",
    ),
    (
        "design",
        "good",
        """## Мышление\nx\n## Результат\n```css path=/src/design/tokens.css\n:root{--color-accent:#8aa624;--space-2:8px;--radius-sm:8px;--focus-ring:2px solid #8aa624}\n```\n### Handoff frontend\n- states ready\n""",
        "PASS",
    ),
    (
        "tests",
        "bad",
        """## Мышление\nx\n## Результат\n```python path=/src/tests/t.py\nimport pytest\n@pytest.mark.skip\ndef test_x():\n  q=f'SELECT {1}'\n```\n""",
        "FAIL",
    ),
    (
        "tests",
        "good",
        """## Мышление\nx\n## Результат\n```python path=/src/tests/test_n.py\ndef test_ok():\n  assert 201==201\n  assert {'title':'a'}['title']=='a'\n```\n""",
        "PASS",
    ),
]


def main() -> int:
    load_skill_pack.cache_clear()
    report: dict = {"packs": {}, "verify": _verify_templates(), "examples": {}, "traps": {}, "gaps": []}

    for role in ("frontend", "backend", "design", "tests", "reviewer"):
        p = load_skill_pack(role)
        sys = build_role_system(role, "brief", "feature", "standard")
        report["packs"][role] = {
            "loaded": bool(p),
            "system_len": len(p.get("system") or ""),
            "built_len": len(sys),
            "has_verify": bool(p.get("has_verify")),
        }
        if role in ("design", "tests", "reviewer") and not (
            (SKILLS / role / "evals").exists()
            or (SKILLS / role / "scripts" / "eval_run.py").exists()
        ):
            # covered by scripts/live_eval_gemini_flash.py
            if not (SKILLS / "scripts" / "live_eval_gemini_flash.py").exists():
                report["gaps"].append(f"{role}: no live eval runner")

    for role in ("frontend", "backend", "design", "tests", "reviewer"):
        report["examples"][role] = {}
        for f in sorted((SKILLS / role / "examples").glob("*.md")):
            report["examples"][role][f.name] = _score(role, f.read_text(encoding="utf-8"))

    for role, tid, text, expect in TRAPS:
        r = _score(role, text)
        if expect == "PASS":
            match = r["verdict"] == "PASS" and r["structure_ok"]
        elif expect == "FAIL":
            match = r["verdict"] == "FAIL"
        else:
            match = r["verdict"] in ("PASS_WITH_RISKS", "FAIL")
        report["traps"][f"{role}:{tid}"] = {**r, "expect": expect, "match": match}

    dirty = extract_artifacts("frontend", TRAPS[0][2])
    findings = scan_all(dirty)
    report["reviewer"] = {
        "system_len": len(reviewer_system_prompt("standard")),
        "gate_verdict": build_receipt(
            task="t", mode="standard", artifacts=dirty, findings=findings
        )["verdict"],
        "payload_has_must": "must-have"
        in reviewer_user_payload(
            task="login", brief="x", final_text="готово", artifacts=dirty, findings=findings
        ).lower(),
    }

    trap_ok = sum(1 for v in report["traps"].values() if v["match"])
    report["summary"] = {
        "traps": f"{trap_ok}/{len(report['traps'])}",
        "verify_ok": all(v.get("ok") for v in report["verify"].values()),
        "gaps": report["gaps"],
    }

    out = Path("/tmp/skills_eval_all_offline.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("→", out)

    # Fail CI if traps or verify break
    if trap_ok != len(report["traps"]) or not report["summary"]["verify_ok"]:
        return 1
    # good examples should not FAIL (except intentionally bad_*)
    for role, files in report["examples"].items():
        for name, row in files.items():
            if name.startswith("good") and row.get("verdict") == "FAIL":
                print("GOOD_EXAMPLE_FAIL", role, name, row.get("codes"))
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
