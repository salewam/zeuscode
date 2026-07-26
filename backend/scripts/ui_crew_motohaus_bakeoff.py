#!/usr/bin/env python3
"""Bakeoff: Fusion UI Crew (power FULL) vs solo Opus — Motohaus landing."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

BASE = "https://zeuscode.ru"
OUT = Path(
    "/Users/money/Desktop/Projects/ultra-mode-mvp/"
    "_bmad-output/implementation-artifacts/bakeoff-sto-2026-07-23"
) / f"ui-crew-{time.strftime('%Y%m%d-%H%M%S')}"
API_KEY_FILE = Path(
    "/Users/money/Desktop/Projects/ultra-mode-mvp/"
    "_bmad-output/implementation-artifacts/bakeoff-sto-2026-07-23/.api_key"
)

PROMPT = (
    "Сделай вкусный одностраничный сайт автосервиса МоторХаус (Каширское шоссе): "
    "полный HTML+CSS+JS в одном файле. Hero full-bleed с атмосферой бокса (не плоский серый), "
    "бренд МоторХаус крупно, 6 услуг с нормальным описанием, отзывы, FAQ, форма записи, "
    "мобильный @media, 2-3 анимации, асфальт/янтарь, без indigo/Inter. "
    "Верни только готовый HTML документ."
)


def _load_key() -> str:
    if API_KEY_FILE.exists():
        k = API_KEY_FILE.read_text(encoding="utf-8").strip()
        if k:
            return k
    raise SystemExit(f"missing api key: {API_KEY_FILE}")


def _extract_html(text: str) -> str:
    t = text or ""
    m = re.search(r"(<!doctype html[\s\S]*?</html>)", t, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"(<html[\s\S]*?</html>)", t, re.I)
    if m:
        return m.group(1).strip()
    return t.strip()


def _metrics(html: str) -> dict:
    h = html or ""
    return {
        "bytes": len(h.encode("utf-8")),
        "has_html_close": "</html>" in h.lower(),
        "has_media": "@media" in h,
        "has_form": "<form" in h.lower(),
        "has_nav": bool(re.search(r"<nav\b", h, re.I)),
        "sections": len(re.findall(r"<section\b", h, re.I)),
        "live_link": (
            m.group(0)
            if (m := re.search(r"https://zeuscode\.ru/go/site-[a-z0-9]+/", h))
            else None
        ),
    }


def chat(client: httpx.Client, *, model: str, body_extra: dict | None = None) -> dict:
    payload = {
        "model": model,
        "stream": False,
        "max_tokens": 65536,
        "messages": [{"role": "user", "content": PROMPT}],
    }
    if body_extra:
        payload.update(body_extra)
    t0 = time.perf_counter()
    r = client.post("/v1/chat/completions", json=payload)
    latency = round(time.perf_counter() - t0, 2)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:2000]}
    answer = ""
    if isinstance(data, dict):
        try:
            answer = data["choices"][0]["message"]["content"] or ""
        except Exception:
            answer = ""
    onestack = (data or {}).get("onestack") if isinstance(data, dict) else None
    return {
        "ok": r.status_code == 200 and bool(answer.strip()),
        "status": r.status_code,
        "latency_s": latency,
        "answer": answer,
        "onestack": onestack,
        "error": None if r.status_code == 200 else (r.text[:800]),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    key = _load_key()
    summary: list[dict] = []

    runs = [
        {
            "label": "fusion_ui_crew",
            "model": "zeus/fusion",
            "extra": {
                "models": [
                    "claude-opus-4-8",
                    "gemini-3.1-pro",
                    "deepseek-v4-pro",
                ],
                "zeus": {
                    "path": "FULL",
                    "mode": "power",
                    "product_mode": "power",
                    "models": [
                        "claude-opus-4-8",
                        "gemini-3.1-pro",
                        "deepseek-v4-pro",
                    ],
                    "leader": "claude-opus-4-8",
                },
            },
        },
        {
            "label": "solo_opus",
            "model": "claude-opus-4-8",
            "extra": {},
        },
    ]

    with httpx.Client(
        base_url=BASE,
        timeout=httpx.Timeout(900.0, connect=30.0),
        headers={"Authorization": f"Bearer {key}"},
        verify=True,
    ) as c:
        for cfg in runs:
            label = cfg["label"]
            print(f"\n===== {label} =====", flush=True)
            out = chat(c, model=cfg["model"], body_extra=cfg.get("extra"))
            html = _extract_html(out.get("answer") or "")
            (OUT / f"{label}.raw.txt").write_text(out.get("answer") or "", encoding="utf-8")
            (OUT / f"{label}.html").write_text(html, encoding="utf-8")
            os_meta = out.get("onestack") or {}
            row = {
                "label": label,
                "ok": out["ok"],
                "status": out["status"],
                "latency_s": out["latency_s"],
                "routed_by": os_meta.get("routed_by"),
                "ui_crew": os_meta.get("ui_crew"),
                "leader": os_meta.get("leader"),
                "task_kind": os_meta.get("task_kind"),
                "path": os_meta.get("path"),
                "metrics": _metrics(html),
                "error": out.get("error"),
            }
            (OUT / f"{label}.json").write_text(
                json.dumps({**row, "onestack": os_meta}, ensure_ascii=False, indent=2)[:500000],
                encoding="utf-8",
            )
            summary.append(row)
            print(
                json.dumps(
                    {
                        "ok": row["ok"],
                        "latency_s": row["latency_s"],
                        "routed_by": row["routed_by"],
                        "ui_crew_author": (row.get("ui_crew") or {}).get("author")
                        if isinstance(row.get("ui_crew"), dict)
                        else None,
                        "bytes": row["metrics"]["bytes"],
                        "live": row["metrics"]["live_link"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    (OUT / "SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nOUT", OUT)
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    main()
