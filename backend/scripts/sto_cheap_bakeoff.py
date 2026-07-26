#!/usr/bin/env python3
"""Autoservice landing bake-off: agents=3 and agents=4 on cheapest flash.

Skill-loop focus — modes that nest the full team with gemini-2.5-flash workers.
Saves artifacts + gate summary under /tmp/sto-cheap-bake.
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
CHEAP = "gemini-2.5-flash"
OUT = Path("/tmp/sto-cheap-bake")
PROMPT = (
    "Сделай вкусный лендинг автосервиса МоторХаус (Каширское ш.): "
    "витрина из 3 реальных фото <img>, 6 услуг с нормальным описанием и списком «включает», "
    "hero full-bleed с живым фото бокса (не серый градиент), второе фото в «почему мы» как <img>, "
    "запись POST /api/booking (name, phone, car, service, slot), отзывы, FAQ, CTA class=btn, "
    "адаптив, асфальт/янтарь, без indigo/Inter. "
    "CSS: sticky, Georgia, .btn transition+:hover, @media 640, hero linear-gradient(90deg). "
    f"Вариант наполнения #{int(time.time()) % 97}."
)

# agents 3 → ultra team; agents 4 → ultra (or premium if mode=premium)
MODES = [
    {"label": "agents3", "mode": "ultra", "agents": 3, "intent": "feature"},
    {"label": "agents4", "mode": "ultra", "agents": 4, "intent": "feature"},
]


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
    sections = len(re.findall(r"<section\b", html, re.I))
    articles = len(re.findall(r"<article\b", html, re.I))
    photos = sorted(set(re.findall(r"photo-([0-9a-zA-Z_-]+)", html + css, re.I)))
    img_https = len(re.findall(r"""<img\b[^>]*\bsrc\s*=\s*['"]https?://""", html, re.I))
    has_http_hero = bool(
        re.search(r"url\s*\(\s*['\"]?https?://", html + css, re.I)
        or re.search(r"""src\s*=\s*['"]https?://""", html, re.I)
    )
    return {
        "html_bytes": len(html),
        "css_bytes": len(css),
        "sections": sections,
        "articles": articles,
        "photo_ids": photos,
        "photo_n": len(photos),
        "img_https": img_https,
        "has_btn": bool(re.search(r"\bbtn\b", html + css, re.I)),
        "has_reviews": bool(re.search(r"<blockquote\b", html, re.I)),
        "has_faq": bool(re.search(r"<details\b|id=[\"']faq", html, re.I)),
        "has_http_hero": has_http_hero,
        "has_vitrine": bool(re.search(r"""id=["']vitrine["']""", html, re.I)),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summary: list[dict] = []

    with httpx.Client(base_url=BASE, timeout=30.0, verify=False) as c:
        r = c.post("/auth/login", json={"email": EMAIL, "password": PASS})
        r.raise_for_status()
        tok = r.json()["access_token"]
        bal0 = r.json().get("balance_rub")
        headers = {"Authorization": f"Bearer {tok}"}
        me = c.get("/auth/me", headers=headers).json()
        print("LOGIN ok balance", me.get("balance_rub"), "kie", me.get("kie_credits"))

        proj = c.post(
            "/projects",
            headers=headers,
            json={"title": f"STO skill-loop agents3-4 {int(time.time())}"},
        )
        proj.raise_for_status()
        project_id = proj.json()["id"]
        print("PROJECT", project_id)

        for cfg in MODES:
            label = cfg["label"]
            mode = cfg["mode"]
            print(
                f"\n===== {label.upper()} mode={mode} agents={cfg['agents']} =====",
                flush=True,
            )
            chat = c.post(
                f"/projects/{project_id}/chats",
                headers=headers,
                json={"title": f"sto-{label}"},
            )
            chat.raise_for_status()
            chat_id = chat.json()["id"]

            team = [CHEAP, CHEAP, CHEAP, CHEAP]

            t0 = time.time()
            with c.stream(
                "POST",
                f"/projects/{project_id}/chats/{chat_id}/complete/stream",
                headers=headers,
                json={
                    "content": PROMPT,
                    "intent": cfg["intent"],
                    "mode": mode,
                    "agents": cfg["agents"],
                    "team_models": team,
                    # Do NOT set "model" — that forces solo single-agent path
                    "run_kind": "team",
                },
                timeout=600.0,
            ) as resp:
                raw = ""
                if resp.status_code >= 400:
                    err = resp.read().decode()[:500]
                    print("FAIL HTTP", resp.status_code, err)
                    summary.append(
                        {
                            "label": label,
                            "mode": mode,
                            "ok": False,
                            "http": resp.status_code,
                            "error": err,
                        }
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
            review = next((e for e in events if e.get("type") == "review_done"), None)
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
                rel = p.lstrip("/")
                fp = dest / rel
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
            majors = sorted(
                {
                    f["code"]
                    for f in findings
                    if f.get("severity") in ("major", "critical")
                }
            )
            metrics = _fe_metrics(by_path)

            me2 = c.get("/auth/me", headers=headers).json()
            row = {
                "label": label,
                "mode": mode,
                "ok": True,
                "wall_s": wall,
                "agents": cfg["agents"],
                "team_models": team,
                "paths": sorted(by_path.keys()),
                "stream_score": done.get("score") or gate.get("score"),
                "stream_gate": done.get("gate") or gate.get("gate"),
                "stream_verdict": done.get("verdict") or (review or {}).get("verdict"),
                "local_score": score,
                "local_gate": ggate,
                "local_majors": majors,
                "fe": metrics,
                "charged_hint": done.get("billing") or done.get("onestack_billing"),
                "balance_after": me2.get("balance_rub"),
                "kie_after": me2.get("kie_credits"),
            }
            (dest / "_summary.json").write_text(
                json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            summary.append(row)
            print(
                f"  wall={wall}s paths={len(by_path)} "
                f"html={metrics['html_bytes']}B sections={metrics['sections']} "
                f"photos={metrics.get('photo_n')} btn={metrics.get('has_btn')} "
                f"rev={metrics.get('has_reviews')} faq={metrics.get('has_faq')} "
                f"http_hero={metrics['has_http_hero']} "
                f"stream={row['stream_gate']}/{row['stream_score']} "
                f"local={ggate}/{score} majors={majors} "
                f"bal={me2.get('balance_rub')}",
                flush=True,
            )

        me_end = c.get("/auth/me", headers=headers).json()
        report = {
            "prompt": PROMPT,
            "cheap_model": CHEAP,
            "focus": "agents_3_and_4",
            "balance_start": bal0,
            "balance_end": me_end.get("balance_rub"),
            "kie_end": me_end.get("kie_credits"),
            "project_id": project_id,
            "runs": summary,
        }
        (OUT / "REPORT.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("\n==== REPORT ====")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
