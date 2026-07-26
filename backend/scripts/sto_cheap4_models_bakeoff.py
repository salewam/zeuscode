#!/usr/bin/env python3
"""STO skill bake: ultra agents=4 × 4 cheapest worker models.

Compares how well the skill pack lifts each cheap model.
Output: /tmp/sto-cheap4-bake/
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
OUT = Path("/tmp/sto-cheap4-bake")

# 4 cheapest *usable* chat workers from live catalog (2026-07-14).
# Skipped claude-opus-4-7/4-8: catalog price looks broken (opus < haiku).
CHEAP4 = [
    "gemini-2.5-flash",   # ~116 ₽/1M sum — cheapest
    "claude-haiku-4-5",   # ~293
    "gemini-3-flash",     # ~357
    "grok-4-3",           # ~382
]

PROMPT = (
    "Сделай вкусный лендинг автосервиса МоторХаус (Каширское ш.): "
    "витрина из 3 реальных фото <img> height≥280px, 6 услуг с описанием и списком «включает», "
    "hero full-bleed с живым фото (не серый градиент), why с другим <img> + кнопка .btn, "
    "запись POST /api/booking (name, phone, car, service, slot), отзывы со стилем, FAQ, "
    "footer с tel:, шапка без синих ссылок (.top__nav a + .tel,.top__nav a.tel янтарь), "
    "H1 без «Профессиональный/Качественный», асфальт/янтарь, без indigo/Inter. "
    "CSS: sticky, Georgia, transition+:hover, @media 640, hero linear-gradient(90deg). "
    f"Вариант #{int(time.time()) % 97}."
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
    html = ""
    css = ""
    for p, a in by_path.items():
        if p.endswith(".html") and ("/frontend/" in p or "/deck/" in p):
            html += a.get("content") or ""
        if p.endswith(".css") and ("/frontend/" in p or "/deck/" in p):
            css += a.get("content") or ""
    photos = sorted(set(re.findall(r"photo-([0-9a-zA-Z_-]+)", html + css, re.I)))
    img_https = len(re.findall(r"""<img\b[^>]*\bsrc\s*=\s*['"]https?://""", html, re.I))
    vit_h = re.search(r"\.vitrine\s+img\s*\{[^}]*height\s*:\s*(\d+)px", css, re.I | re.S)
    return {
        "html_bytes": len(html),
        "css_bytes": len(css),
        "sections": len(re.findall(r"<section\b", html, re.I)),
        "articles": len(re.findall(r"<article\b", html, re.I)),
        "photo_n": len(photos),
        "photo_ids": photos,
        "img_https": img_https,
        "has_vitrine": bool(re.search(r"""id=["']vitrine["']""", html, re.I)),
        "vit_height": int(vit_h.group(1)) if vit_h else 0,
        "nav_color": bool(re.search(r"\.top__nav\s+a\s*\{[^}]*color\s*:", css, re.I | re.S)),
        "tel_spec": bool(re.search(r"\.top__nav\s+a\.tel|\.tel\s*,\s*\.top__nav", css, re.I)),
        "reviews_css": bool(re.search(r"\.reviews\s*\{", css, re.I)),
        "has_btn": bool(re.search(r"\bbtn\b", html + css, re.I)),
        "has_reviews": bool(re.search(r"<blockquote\b", html, re.I)),
        "has_faq": bool(re.search(r"<details\b", html, re.I)),
        "footer_tel": bool(re.search(r"<footer\b[\s\S]{0,1200}tel:", html, re.I)),
        "h1": (
            re.sub(
                r"<[^>]+>",
                " ",
                (re.search(r"<h1\b[^>]*>([\s\S]*?)</h1>", html, re.I) or [None, ""])[1],
            ).strip()[:80]
        ),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summary: list[dict] = []

    with httpx.Client(base_url=BASE, timeout=30.0, verify=False) as c:
        r = c.post("/auth/login", json={"email": EMAIL, "password": PASS})
        r.raise_for_status()
        tok = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}"}
        me = c.get("/auth/me", headers=headers).json()
        print("LOGIN ok balance", me.get("balance_rub"), flush=True)

        proj = c.post(
            "/projects",
            headers=headers,
            json={"title": f"STO cheap4 skill bake {int(time.time())}"},
        )
        proj.raise_for_status()
        project_id = proj.json()["id"]
        print("PROJECT", project_id, "models", CHEAP4, flush=True)

        for mid in CHEAP4:
            label = mid.replace("/", "-").replace(".", "-")
            # resume: skip if FE already baked
            if (OUT / label / "src" / "frontend" / "index.html").exists():
                print(f"\n===== SKIP {mid} (already have artifacts) =====", flush=True)
                continue
            print(f"\n===== {mid} mode=ultra agents=4 =====", flush=True)
            chat = c.post(
                f"/projects/{project_id}/chats",
                headers=headers,
                json={"title": f"sto-{label}"},
            )
            chat.raise_for_status()
            chat_id = chat.json()["id"]

            team = [mid, mid, mid, mid]
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
                    "team_models": team,
                    "run_kind": "team",
                },
                timeout=700.0,
            ) as resp:
                raw = ""
                if resp.status_code >= 400:
                    err = resp.read().decode()[:800]
                    print("FAIL HTTP", resp.status_code, err, flush=True)
                    summary.append(
                        {"label": label, "model": mid, "ok": False, "error": err}
                    )
                    continue
                for chunk in resp.iter_text():
                    raw += chunk
            wall = round(time.time() - t0, 1)
            events = _parse_sse(raw)
            done = next(
                (e for e in events if e.get("type") in ("done", "final")), None
            ) or {}
            gate = next((e for e in events if e.get("type") == "gate_done"), None) or {}

            arts: list[dict] = []
            for e in events:
                if e.get("type") in ("agent_done", "review_done", "final", "done"):
                    arts.extend(e.get("artifacts") or [])
            if done.get("artifacts"):
                arts = list(done["artifacts"]) + arts

            dest = OUT / label
            dest.mkdir(parents=True, exist_ok=True)
            by_path: dict[str, dict] = {}
            for a in arts:
                p = (a.get("path") or "").strip()
                if not p:
                    continue
                prev = by_path.get(p)
                if not prev or len(a.get("content") or "") >= len(
                    prev.get("content") or ""
                ):
                    by_path[p] = a
            for p, a in by_path.items():
                fp = dest / p.lstrip("/")
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(a.get("content") or "", encoding="utf-8")

            (dest / "_events.json").write_text(
                json.dumps(events, ensure_ascii=False, indent=2)[:400_000],
                encoding="utf-8",
            )

            import sys

            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from app.evidence import scan_artifacts, score_from_findings

            findings = scan_artifacts(list(by_path.values()))
            score, grade, ggate = score_from_findings(findings)
            majors = sorted(
                {
                    f["code"]
                    for f in findings
                    if f.get("severity") == "major"
                }
            )
            fe = _fe_metrics(by_path)
            bal = None
            try:
                bal_r = c.get("/auth/me", headers=headers)
                if bal_r.status_code == 200:
                    bal = bal_r.json().get("balance_rub")
            except Exception:
                bal = None

            row = {
                "label": label,
                "model": mid,
                "ok": True,
                "wall_s": wall,
                "agents": 4,
                "mode": "ultra",
                "team_models": team,
                "paths": sorted(by_path.keys()),
                "stream_score": gate.get("score") or done.get("score"),
                "stream_gate": gate.get("gate") or done.get("gate"),
                "local_score": score,
                "local_grade": grade,
                "local_gate": ggate,
                "local_majors": majors,
                "fe": fe,
                "balance_after": bal,
            }
            summary.append(row)
            print(
                f"  wall={wall}s html={fe['html_bytes']}B img={fe['img_https']} "
                f"vit_h={fe['vit_height']} nav={fe['nav_color']} tel={fe['tel_spec']} "
                f"local={ggate}/{score} majors={majors} bal={bal}",
                flush=True,
            )
            print(f"  h1={fe['h1']!r}", flush=True)

        me2_bal = me.get("balance_rub")
        try:
            me2 = c.get("/auth/me", headers=headers)
            if me2.status_code == 200:
                me2_bal = me2.json().get("balance_rub")
        except Exception:
            pass
        report = {
            "prompt": PROMPT,
            "focus": "ultra_agents4_x_cheap4",
            "models": CHEAP4,
            "balance_start": me.get("balance_rub"),
            "balance_end": me2_bal,
            "project_id": project_id,
            "runs": summary,
        }
        (OUT / "REPORT.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("\n==== REPORT ====", flush=True)
        print(json.dumps(report, ensure_ascii=False, indent=2)[:8000], flush=True)


if __name__ == "__main__":
    main()
