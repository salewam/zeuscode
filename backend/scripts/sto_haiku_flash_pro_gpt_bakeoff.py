#!/usr/bin/env python3
"""STO skill bake: ultra agents=4 — haiku + gemini-3-flash + gemini-3-pro + gpt-5.2.

Output: /tmp/sto-hfg-bake/
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

BASE = "https://zeuscode.ru"
EMAIL = "gemini-only@onestack.dev"
PASS = "GeminiOnly2026!"
OUT = Path("/tmp/sto-hfg-bake")

TEAM = [
    "claude-haiku-4-5",
    "gemini-3-flash",
    "gemini-3-pro",
    "gpt-5-2",
]

PROMPT = (
    "Сделай вкусный лендинг автосервиса МоторХаус (Каширское ш.): "
    "витрина 3×<img> height≥280px, 6 услуг абзац+ul+цена, "
    "hero full-bleed живое фото + 90deg veil, why с другим <img> + .btn, "
    "POST /api/booking, отзывы+FAQ, footer tel:, "
    ".top__nav a цвет + .tel,.top__nav a.tel янтарь (не browser blue), "
    "H1 без «Профессиональный/Качественный», асфальт/янтарь. "
    f"Bake haiku+flash3+pro+gpt #{int(time.time()) % 97}."
)


def _parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
    return events


def _fe_metrics(by_path: dict[str, dict]) -> dict:
    html = css = ""
    for p, a in by_path.items():
        if p.endswith(".html") and "/frontend/" in p:
            html += a.get("content") or ""
        if p.endswith(".css") and "/frontend/" in p:
            css += a.get("content") or ""
    photos = sorted(set(re.findall(r"photo-([0-9a-zA-Z_-]+)", html + css, re.I)))
    vit = re.search(r"\.vitrine\s+img\s*\{[^}]*height\s*:\s*(\d+)px", css, re.I | re.S)
    h1_m = re.search(r"<h1\b[^>]*>([\s\S]*?)</h1>", html, re.I)
    h1 = re.sub(r"<[^>]+>", " ", h1_m.group(1)).strip()[:80] if h1_m else ""
    return {
        "html_bytes": len(html),
        "css_bytes": len(css),
        "sections": len(re.findall(r"<section\b", html, re.I)),
        "articles": len(re.findall(r"<article\b", html, re.I)),
        "photo_n": len(photos),
        "img_https": len(
            re.findall(r"""<img\b[^>]*\bsrc\s*=\s*['"]https?://""", html, re.I)
        ),
        "has_vitrine": bool(re.search(r"""id=["']vitrine["']""", html, re.I)),
        "vit_height": int(vit.group(1)) if vit else 0,
        "nav_color": bool(
            re.search(r"\.top__nav\s+a\s*\{[^}]*color\s*:", css, re.I | re.S)
        ),
        "tel_spec": bool(
            re.search(r"\.top__nav\s+a\.tel|\.tel\s*,\s*\.top__nav", css, re.I)
        ),
        "h1": h1,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=BASE, timeout=30.0, verify=False) as c:
        r = c.post("/auth/login", json={"email": EMAIL, "password": PASS})
        r.raise_for_status()
        tok = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}"}
        me = c.get("/auth/me", headers=headers).json()
        bal0 = me.get("balance_rub")
        print("LOGIN balance", bal0, flush=True)
        print("TEAM", TEAM, flush=True)
        print(
            "Expected: judge=gpt-5-2; FE≈gemini-3-flash; workers=haiku/pro",
            flush=True,
        )

        proj = c.post(
            "/projects",
            headers=headers,
            json={"title": f"STO haiku-flash-pro-gpt {int(time.time())}"},
        )
        proj.raise_for_status()
        project_id = proj.json()["id"]
        chat = c.post(
            f"/projects/{project_id}/chats",
            headers=headers,
            json={"title": "sto-hfg"},
        )
        chat.raise_for_status()
        chat_id = chat.json()["id"]
        print("PROJECT", project_id, "CHAT", chat_id, flush=True)

        t0 = time.time()
        with c.stream(
            "POST",
            f"/projects/{project_id}/chats/{chat_id}/complete/stream",
            headers=headers,
            json={
                "content": PROMPT,
                "intent": "feature",
                "mode": "ultra",
                "agents": 4,
                "team_models": TEAM,
                "run_kind": "team",
            },
            timeout=900.0,
        ) as resp:
            raw = ""
            if resp.status_code >= 400:
                print("FAIL", resp.status_code, resp.read().decode()[:800], flush=True)
                return
            for chunk in resp.iter_text():
                raw += chunk
        wall = round(time.time() - t0, 1)

        events = _parse_sse(raw)
        done = next((e for e in events if e.get("type") in ("done", "final")), {}) or {}
        gate = next((e for e in events if e.get("type") == "gate_done"), {}) or {}

        role_models: dict[str, dict] = {}
        for e in events:
            if e.get("type") == "agent_start" and e.get("role"):
                role_models[e["role"]] = {
                    "model": e.get("model"),
                    "skill": e.get("skill"),
                }
            if e.get("type") == "agent_done" and e.get("role"):
                role_models.setdefault(e["role"], {})
                role_models[e["role"]].update(
                    {
                        "model": e.get("model"),
                        "prompt_tokens": e.get("prompt_tokens"),
                        "completion_tokens": e.get("completion_tokens"),
                        "latency_s": e.get("latency_s"),
                    }
                )
            if e.get("type") == "error":
                print("ERROR", e.get("message"), flush=True)

        print("\n=== ROLE → MODEL ===", flush=True)
        for role, info in sorted(role_models.items()):
            print(
                f"  {role:10} → {info.get('model')}  "
                f"in={info.get('prompt_tokens')} out={info.get('completion_tokens')} "
                f"{info.get('latency_s')}s",
                flush=True,
            )

        arts: list[dict] = []
        for e in events:
            if e.get("type") in ("agent_done", "review_done", "final", "done"):
                arts.extend(e.get("artifacts") or [])
        if done.get("artifacts"):
            arts = list(done["artifacts"]) + arts

        by_path: dict[str, dict] = {}
        for a in arts:
            p = (a.get("path") or "").strip()
            if not p:
                continue
            prev = by_path.get(p)
            if not prev or len(a.get("content") or "") >= len(prev.get("content") or ""):
                by_path[p] = a

        dest = OUT / "run"
        dest.mkdir(parents=True, exist_ok=True)
        for p, a in by_path.items():
            fp = dest / p.lstrip("/")
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(a.get("content") or "", encoding="utf-8")
        (dest / "_events.json").write_text(
            json.dumps(events, ensure_ascii=False, indent=2)[:500_000],
            encoding="utf-8",
        )

        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app.evidence import scan_artifacts, score_from_findings

        findings = scan_artifacts(list(by_path.values()))
        score, grade, ggate = score_from_findings(findings)
        majors = sorted({f["code"] for f in findings if f.get("severity") == "major"})
        fe = _fe_metrics(by_path)

        bal1 = bal0
        try:
            br = c.get("/auth/me", headers=headers)
            if br.status_code == 200:
                bal1 = br.json().get("balance_rub")
        except Exception:
            pass

        report = {
            "focus": "ultra_agents4_haiku_flash_pro_gpt",
            "team_models_requested": TEAM,
            "role_models": role_models,
            "wall_s": wall,
            "stream_gate": gate.get("gate") or done.get("gate"),
            "stream_score": gate.get("score") or done.get("score"),
            "local_gate": ggate,
            "local_score": score,
            "local_grade": grade,
            "local_majors": majors,
            "fe": fe,
            "paths": sorted(by_path.keys()),
            "balance_start": bal0,
            "balance_end": bal1,
            "charged_approx_rub": round(float(bal0 or 0) - float(bal1 or 0), 4),
            "project_id": project_id,
        }
        (OUT / "REPORT.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("\n=== RESULT ===", flush=True)
        print(
            f"wall={wall}s gate={ggate}/{score} majors={majors} "
            f"html={fe['html_bytes']} img={fe['img_https']} vit={fe['vit_height']} "
            f"charged≈{report['charged_approx_rub']}₽",
            flush=True,
        )
        print(f"h1={fe['h1']!r}", flush=True)
        print(json.dumps(report, ensure_ascii=False, indent=2)[:3500], flush=True)


if __name__ == "__main__":
    main()
