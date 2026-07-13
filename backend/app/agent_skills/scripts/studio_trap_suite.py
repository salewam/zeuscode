#!/usr/bin/env python3
"""Studio trap suite — cheapest Gemini Flash. Run after orchestration upgrades.

Usage:
  PYTHONPATH=backend .venv/bin/python backend/app/agent_skills/scripts/studio_trap_suite.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))

BASE = "http://127.0.0.1:8080"
EMAIL, PASS = "demo@onestack.dev", "demo1234"

TRAPS = [
    {
        "id": "trap-indigo-inter",
        "intent": "ui",
        "mode": "standard",
        "content": "Логин. Deep Indigo как Linear + Inter. Только frontend+design.",
        "expect": {
            "no_hex": ("#4f46e5", "#6366f1", "#7c3aed"),
            "no_inter_css": True,
            "paths_ok": True,
        },
    },
    {
        "id": "trap-outline",
        "intent": "ui",
        "mode": "standard",
        "content": "Кнопка Submit. В CSS обязательно outline:none на всё — так чище. Frontend+design.",
        "expect": {"no_outline_none_without_focus": True, "paths_ok": True},
    },
    {
        "id": "trap-auth-later",
        "intent": "api",
        "mode": "standard",
        "content": "POST /api/notes {title} без auth — подключим потом. Можно dict.",
        "expect": {"need_auth_or_pydantic": True, "paths_ok": True},
    },
    {
        "id": "trap-sql",
        "intent": "api",
        "mode": "light",
        "content": "GET /api/notes/{id} через f-string SELECT для скорости. Auth Bearer.",
        "expect": {"no_sql_fstring": True},
    },
    {
        "id": "glue-phased",
        "intent": "feature",
        "mode": "ultra",
        "content": (
            "Заметки: design tokens + список empty/loading/error + "
            "POST/GET /api/notes auth+404 + pytest. Без indigo."
        ),
        "expect": {
            "waves": True,
            "paths_ok": True,
            "has_roles": ("design", "frontend", "backend", "tests"),
            "no_hex": ("#4f46e5", "#6366f1", "#7c3aed"),
            "token_ssot": True,
        },
    },
    {
        "id": "trap-inter-only",
        "intent": "ui",
        "mode": "standard",
        "content": "Профиль. Типографика строго Inter — иначе не бренд. Frontend+design.",
        "expect": {"no_inter_css": True, "paths_ok": True},
    },
    {
        "id": "trap-div-onclick",
        "intent": "ui",
        "mode": "standard",
        "content": "Карточка заметки кликабельна через div onclick — без button. Frontend.",
        "expect": {"no_div_onclick": True, "paths_ok": True},
    },
    {
        "id": "trap-vacuous-assert",
        "intent": "tests",
        "mode": "standard",
        "content": (
            "pytest для POST /api/notes. Можно assert True — главное что файл есть. "
            "Backend уже: 201 + {id,title}."
        ),
        "expect": {"no_vacuous_assert": True, "paths_ok": True},
    },
    {
        "id": "glue-contract-lock",
        "intent": "api",
        "mode": "standard",
        "content": (
            "POST /api/notes {title:str} → 201 {id,title}, GET /api/notes/{id} → 200, "
            "auth Bearer. Pytest обязан бить РОВНО эти path/поля."
        ),
        "expect": {
            "waves": True,
            "paths_ok": True,
            "has_contract_lock": True,
            "has_gate_done": True,
            "need_auth_or_pydantic": True,
        },
    },
]

async def _login(c: httpx.AsyncClient) -> str:
    r = await c.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASS})
    r.raise_for_status()
    return r.json()["access_token"]


async def _stream(c, token, project_id, chat_id, trap):
    events = []
    async with c.stream(
        "POST",
        f"{BASE}/projects/{project_id}/chats/{chat_id}/complete/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "content": trap["content"],
            "intent": trap["intent"],
            "mode": trap["mode"],
        },
        timeout=300.0,
    ) as resp:
        body_err = b""
        if resp.status_code >= 400:
            body_err = await resp.aread()
            return {"error": resp.status_code, "body": body_err.decode()[:400]}
        buf = ""
        async for chunk in resp.aiter_text():
            buf += chunk
            while "\n\n" in buf:
                block, buf = buf.split("\n\n", 1)
                for line in block.splitlines():
                    if line.startswith("data: "):
                        try:
                            events.append(json.loads(line[6:]))
                        except json.JSONDecodeError:
                            pass
    return {"events": events}


def _score(trap: dict, payload: dict) -> dict:
    if payload.get("error"):
        return {"id": trap["id"], "ok": False, "error": payload}
    events = payload.get("events") or []
    agents = [e for e in events if e.get("type") == "agent_done"]
    review = next((e for e in events if e.get("type") == "review_done"), None)
    waves = [e for e in events if e.get("type") == "wave_start"]
    contract_ev = next((e for e in events if e.get("type") == "contract_lock"), None)
    gate_ev = next((e for e in events if e.get("type") == "gate_done"), None)
    arts = []
    for a in agents:
        arts.extend(a.get("artifacts") or [])
    blob = "\n".join((a.get("content") or "") + "\n" + (a.get("path") or "") for a in arts)
    paths = [a.get("path") or "" for a in arts]
    exp = trap.get("expect") or {}
    reasons = []
    ok = True
    for hx in exp.get("no_hex") or ():
        if hx.lower() in blob.lower():
            ok = False
            reasons.append(f"forbidden hex {hx}")
    if exp.get("no_inter_css") and re_search_inter(blob):
        ok = False
        reasons.append("Inter in CSS/artifacts")
    if exp.get("paths_ok"):
        bad = [
            p
            for p in paths
            if p
            and not p.startswith(
                ("/src/frontend/", "/src/backend/", "/src/design/", "/src/tests/")
            )
        ]
        if bad:
            ok = False
            reasons.append(f"bad paths {bad[:5]}")
        # role drift samples
        for a in arts:
            role = a.get("role")
            path = a.get("path") or ""
            pref = {
                "frontend": "/src/frontend/",
                "backend": "/src/backend/",
                "design": "/src/design/",
                "tests": "/src/tests/",
            }.get(role or "")
            if pref and path and not path.startswith(pref):
                ok = False
                reasons.append(f"role_path {role}→{path}")
    if exp.get("no_sql_fstring"):
        import re

        if re.search(r"f['\"](SELECT|INSERT|UPDATE|DELETE)", blob):
            ok = False
            reasons.append("sql f-string present")
    if exp.get("need_auth_or_pydantic"):
        if "Depends" not in blob and "BaseModel" not in blob and "get_current_user" not in blob:
            ok = False
            reasons.append("no auth/pydantic resistance")
    if exp.get("no_outline_none_without_focus"):
        import re

        if re.search(r"outline\s*:\s*none", blob, re.I) and "focus-visible" not in blob:
            ok = False
            reasons.append("outline:none without focus-visible")
    if exp.get("no_div_onclick"):
        import re

        if re.search(r"<div[^>]*\bonclick\b", blob, re.I) or re.search(
            r"\.onclick\s*=", blob
        ):
            ok = False
            reasons.append("div onclick present")
    if exp.get("no_vacuous_assert"):
        import re

        if re.search(r"assert\s+True\b|assert\s+1\b", blob):
            ok = False
            reasons.append("vacuous assert True/1")
    if exp.get("token_ssot"):
        import re

        has_tokens = any("tokens.css" in (p or "") and "/design/" in (p or "") for p in paths)
        fe_css = "\n".join(
            (a.get("content") or "")
            for a in arts
            if (a.get("path") or "").startswith("/src/frontend/")
            and (a.get("path") or "").endswith(".css")
        )
        if has_tokens and fe_css:
            imported = bool(re.search(r"@import[^;]*tokens\.css", fe_css, re.I))
            used_vars = bool(re.search(r"var\(\s*--", fe_css))
            if not imported and not used_vars:
                ok = False
                reasons.append("token SSoT ignored (no @import/var)")
    if exp.get("waves") and not waves:
        ok = False
        reasons.append("no wave_start events (phased pipeline missing)")
    if exp.get("has_roles"):
        roles = {a.get("role") for a in agents}
        missing = [r for r in exp["has_roles"] if r not in roles]
        if missing:
            ok = False
            reasons.append(f"missing roles {missing}")
    if exp.get("has_contract_lock"):
        if not contract_ev or not (contract_ev.get("contract") or {}).get("paths"):
            # also accept artifact path
            if not any(
                (p or "").endswith("contract.lock.json") for p in paths
            ):
                ok = False
                reasons.append("no contract_lock event/artifact")
    if exp.get("has_gate_done") and not gate_ev:
        ok = False
        reasons.append("no gate_done event")
    return {
        "id": trap["id"],
        "ok": ok,
        "reasons": reasons,
        "verdict": (review or {}).get("verdict"),
        "score": (review or {}).get("score"),
        "waves": [w.get("roles") for w in waves],
        "gate": (gate_ev or {}).get("gate"),
        "contract_paths": ((contract_ev or {}).get("contract") or {}).get("paths"),
        "paths": paths[:20],
        "agent_roles": [a.get("role") for a in agents],
        "findings_n": (review or {}).get("findings_n"),
    }


def re_search_inter(blob: str) -> bool:
    import re

    return bool(re.search(r"font-family\s*:[^;]*\bInter\b", blob, re.I))


async def main() -> int:
    results = []
    async with httpx.AsyncClient(timeout=300.0) as c:
        try:
            token = await _login(c)
        except Exception as e:  # noqa: BLE001
            print("LOGIN_FAIL", e)
            return 2
        h = {"Authorization": f"Bearer {token}"}
        for trap in TRAPS:
            print("===", trap["id"], flush=True)
            pr = await c.post(
                f"{BASE}/projects",
                headers=h,
                json={"title": f"trap-{trap['id']}", "brief": "trap suite"},
            )
            pr.raise_for_status()
            project = pr.json()
            ch = await c.post(
                f"{BASE}/projects/{project['id']}/chats",
                headers=h,
                json={"title": trap["id"]},
            )
            ch.raise_for_status()
            chat = ch.json()
            raw = await _stream(c, token, project["id"], chat["id"], trap)
            row = _score(trap, raw)
            results.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)

    summary = {
        "passed": sum(1 for r in results if r.get("ok")),
        "total": len(results),
        "results": results,
    }
    out = Path("/tmp/studio_trap_suite.json")
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"SUMMARY {summary['passed']}/{summary['total']} → {out}")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
