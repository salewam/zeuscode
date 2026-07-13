#!/usr/bin/env python3
"""Run backend skill evals (live upstream) + deterministic rubric.

Usage (from repo root):
  PYTHONPATH=backend .venv/bin/python backend/app/agent_skills/backend/evals/run_evals.py
  PYTHONPATH=backend .venv/bin/python ... --ids be-notes-crud
  PYTHONPATH=backend .venv/bin/python ... --dry-run   # only load cases / no API
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]  # ultra-mode-mvp/
CASES = Path(__file__).resolve().parent / "cases.json"
VERIFY = Path(__file__).resolve().parents[1] / "scripts" / "verify.sh"


def _write_arts(tmp: Path, arts: list[dict]) -> Path:
    base = tmp / "src" / "backend"
    for a in arts:
        path = (a.get("path") or "").strip()
        rel = path.replace("/src/backend/", "").lstrip("/")
        if not rel:
            continue
        out = base / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(a.get("content") or "", encoding="utf-8")
    return base


def _verify(arts: list[dict]) -> tuple[bool, str]:
    if not arts:
        return False, "no artifacts"
    with tempfile.TemporaryDirectory() as td:
        base = _write_arts(Path(td), arts)
        if not any(base.rglob("*.py")):
            return False, "no py written"
        proc = subprocess.run(
            ["bash", str(VERIFY), str(base)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, out.strip()


def _rubric(case: dict, text: str, arts: list[dict], verify_ok: bool) -> list[tuple[str, bool]]:
    blob = text + "\n" + "\n".join(a.get("content") or "" for a in arts)
    low = blob.lower()
    checks: list[tuple[str, bool]] = []
    for exp in case.get("expected_behavior") or []:
        e = exp.lower()
        ok = True
        if "мышление" in e and "результат" in e:
            ok = "## мышление" in low and "## результат" in low
        elif "path=/src/backend" in e:
            ok = any((a.get("path") or "").startswith("/src/backend/") for a in arts)
        elif "pydantic" in e or "basemodel" in e:
            ok = "basemodel" in low or "field(" in low
        elif "404" in e or "ownership" in e or "чужой" in e:
            ok = "404" in blob or "not found" in low or "user_id" in low
        elif "sql f-string" in e:
            ok = not re.search(r'f["\'](SELECT|INSERT|UPDATE|DELETE)', blob)
        elif "sk-" in e or "password в return" in e or "секретов" in e:
            ok = not re.search(r"sk-[a-zA-Z0-9]{20,}", blob) and not re.search(
                r'return\s*\{[^}]*["\']password["\']', blob, re.I
            )
        elif "verify.sh" in e:
            ok = verify_ok
        elif "401" in e or "единый" in e:
            ok = "401" in blob and (
                "invalid email or password" in low
                or "неверн" in low
                or "одинаков" in low
                or "единый" in low
                or "enumeration" in low
                or low.count("invalid") >= 1
            )
        elif "password в json" in e or "нет password" in e:
            # Explicit password field in *Out* / return dict — not password_hash
            outs = re.findall(
                r"class\s+\w*Out\w*\([\s\S]*?(?=\nclass|\Z)",
                blob,
            )
            leak_field = any(
                re.search(r"(?m)^\s*password\s*:", block) for block in outs
            )
            leak_return = bool(
                re.search(r'return\s*\{[^}]*["\']password["\']', blob, re.I)
            )
            ok = (not leak_field) and (not leak_return)
        elif "email" in e:
            ok = "emailstr" in low or "email" in low
        elif "limit" in e:
            ok = "limit" in low and (
                "le=100" in low or "le = 100" in low or "max" in low or "100" in blob
            )
        elif "user_id" in e or "фильтр" in e:
            ok = "user_id" in low
        elif "response_model не dict" in e or "не dict" in e or "response_model=dict" in e:
            ok = not re.search(r"response_model\s*=\s*dict\b", blob)
        elif "depends" in e or "get_current_user" in e or "auth на мутации" in e:
            ok = (
                "depends(" in low
                or "get_current_user" in low
                or "current_user" in low
                or "authorization" in low
            ) and ("auth потом" not in low or "depends" in low)
        else:
            ok = True  # unknown → don't fail hard
        checks.append((exp, ok))
    return checks


async def _run_case(case: dict) -> dict:
    from app.skills import build_role_system, load_skill_pack
    from app.orchestrate import model_for_role, _role_call, extract_artifacts

    load_skill_pack.cache_clear()
    mode = case.get("mode") or "standard"
    role = "backend"
    system = build_role_system(role, case.get("brief"), case.get("intent") or "api", mode)
    model = model_for_role(mode, role)
    import os

    model = os.environ.get("SKILL_EVAL_MODEL", model)
    out = await _role_call(
        role=role,
        system=system,
        history=[],
        user_text=case["query"],
        model=model,
    )
    text = out.get("text") or ""
    arts = out.get("artifacts") or extract_artifacts(role, out.get("result_body") or text)
    verify_ok, verify_out = _verify(arts)
    checks = _rubric(case, text, arts, verify_ok)
    passed = all(ok for _, ok in checks)
    return {
        "id": case["id"],
        "mode": mode,
        "model": model,
        "passed": passed,
        "latency_s": out.get("latency_s"),
        "artifacts_n": len(arts),
        "paths": [a.get("path") for a in arts],
        "checks": [{"expected": e, "ok": ok} for e, ok in checks],
        "verify_ok": verify_ok,
        "verify_tail": "\n".join(verify_out.splitlines()[-8:]),
        "text_preview": text[:600],
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", help="subset of case ids")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--out",
        default=str(ROOT / "data" / "backend_skill_evals.json"),
    )
    args = ap.parse_args()
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if args.ids:
        cases = [c for c in cases if c["id"] in set(args.ids)]
    if args.dry_run:
        print(json.dumps({"cases": [c["id"] for c in cases], "dry_run": True}, indent=2))
        return 0

    sys.path.insert(0, str(ROOT / "backend"))
    results = []
    for c in cases:
        print(f"=== RUN {c['id']} ({c.get('mode')}) ===", flush=True)
        try:
            r = await _run_case(c)
        except Exception as e:  # noqa: BLE001
            r = {"id": c["id"], "passed": False, "error": str(e)}
        results.append(r)
        print(json.dumps({k: r[k] for k in r if k != "text_preview"}, ensure_ascii=False, indent=2))
        print(flush=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "passed": sum(1 for r in results if r.get("passed")),
        "total": len(results),
        "results": results,
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SUMMARY {summary['passed']}/{summary['total']} → {out_path}")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
