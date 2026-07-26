#!/usr/bin/env python3
"""Two different user briefs → two unique STO landings (gemini-3-flash ultra)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

BASE = "https://zeuscode.ru"
EMAIL = "gemini-only@onestack.dev"
PASS = "GeminiOnly2026!"
OUT = Path("/tmp/sto-uniq-bake")
MODEL = "gemini-3-flash"

CASES = [
    {
        "label": "sever",
        "prompt": (
            "Сделай вкусный лендинг автосервиса «СеверМотор» на Ленинградке: "
            "витрина 3×img≥280px, 6 услуг абзац+ul+цена, hero full-bleed, "
            "why+img+.btn, POST /api/booking, отзывы+FAQ, footer tel:, "
            "data-uniq из брифа, асфальт/янтарь. Не МоторХаус."
        ),
    },
    {
        "label": "box7",
        "prompt": (
            "Сделай вкусный лендинг автосервиса «Бокс№7» в Химках: "
            "витрина 3×img≥280px, 6 услуг абзац+ul+цена, hero full-bleed, "
            "why+img+.btn, POST /api/booking, отзывы+FAQ, footer tel:, "
            "data-uniq из брифа, асфальт/янтарь. Не МоторХаус."
        ),
    },
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


def _brand_of(html: str) -> str:
    m = re.search(
        r"""class=["'][^"']*\bbrand\b[^"']*["'][^>]*>\s*([^<]{2,40})\s*<""",
        html,
        re.I,
    )
    return m.group(1).strip() if m else ""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summary = []
    with httpx.Client(base_url=BASE, timeout=30.0, verify=False) as c:
        r = c.post("/auth/login", json={"email": EMAIL, "password": PASS})
        r.raise_for_status()
        tok = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}"}
        bal0 = c.get("/auth/me", headers=headers).json().get("balance_rub")
        print("LOGIN", bal0, flush=True)
        proj = c.post(
            "/projects",
            headers=headers,
            json={"title": f"STO uniq {int(time.time())}"},
        )
        proj.raise_for_status()
        pid = proj.json()["id"]

        for case in CASES:
            label = case["label"]
            print(f"\n===== {label} =====", flush=True)
            chat = c.post(
                f"/projects/{pid}/chats",
                headers=headers,
                json={"title": f"uniq-{label}"},
            )
            chat.raise_for_status()
            cid = chat.json()["id"]
            t0 = time.time()
            with c.stream(
                "POST",
                f"/projects/{pid}/chats/{cid}/complete/stream",
                headers=headers,
                json={
                    "content": case["prompt"],
                    "intent": "feature",
                    "mode": "ultra",
                    "agents": 4,
                    "team_models": [MODEL, MODEL, MODEL, MODEL],
                    "run_kind": "team",
                },
                timeout=900.0,
            ) as resp:
                raw = ""
                if resp.status_code >= 400:
                    print("FAIL", resp.status_code, resp.read().decode()[:400])
                    continue
                for chunk in resp.iter_text():
                    raw += chunk
            wall = round(time.time() - t0, 1)
            events = _parse_sse(raw)
            done = next((e for e in events if e.get("type") in ("done", "final")), {})
            arts = []
            for e in events:
                if e.get("type") in ("agent_done", "done", "final"):
                    arts.extend(e.get("artifacts") or [])
            if done.get("artifacts"):
                arts = list(done["artifacts"]) + arts
            by = {}
            for a in arts:
                p = (a.get("path") or "").strip()
                if p:
                    by[p] = a
            dest = OUT / label
            dest.mkdir(parents=True, exist_ok=True)
            html = ""
            for p, a in by.items():
                fp = dest / p.lstrip("/")
                fp.parent.mkdir(parents=True, exist_ok=True)
                content = a.get("content") or ""
                fp.write_text(content, encoding="utf-8")
                if p.endswith("index.html"):
                    html = content
            brand = _brand_of(html)
            uniq = ""
            m = re.search(r'data-uniq=["\']([a-f0-9]+)', html, re.I)
            if m:
                uniq = m.group(1)
            has_mh = "МоторХаус" in html
            row = {
                "label": label,
                "wall_s": wall,
                "brand": brand,
                "data_uniq": uniq,
                "has_motorhaus": has_mh,
                "gate": done.get("gate"),
                "score": done.get("score"),
                "html_bytes": len(html),
            }
            summary.append(row)
            print(row, flush=True)

        bal1 = c.get("/auth/me", headers=headers).json().get("balance_rub")
        report = {
            "balance_start": bal0,
            "balance_end": bal1,
            "charged": round(float(bal0 or 0) - float(bal1 or 0), 4),
            "runs": summary,
        }
        (OUT / "REPORT.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("\nREPORT", json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        brands = {r["brand"] for r in summary}
        assert len(brands) >= 2, f"brands not unique: {brands}"
        assert not any(r["has_motorhaus"] for r in summary), "MotоrХаус leaked"
        print("UNIQUENESS PASS", flush=True)


if __name__ == "__main__":
    main()
