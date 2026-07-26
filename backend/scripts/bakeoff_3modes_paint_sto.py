#!/usr/bin/env python3
"""3 Fusion modes × same paint-shop STO prompt (FULL / UI Crew when applicable).

Modes match TG Mini App labels:
  1) simple  = Пользовательский
  2) power   = Продвинутый
  3) custom  = Набор из самых сильных (Fable / GPT-5.6 Sol / Opus)
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

BASE = "https://zeuscode.ru"
OUT = Path(
    "/Users/money/Desktop/Projects/ultra-mode-mvp/"
    "_bmad-output/implementation-artifacts/bakeoff-paint-3modes-"
    f"{time.strftime('%Y%m%d-%H%M%S')}"
)
API_KEY_FILE = Path(
    "/Users/money/Desktop/Projects/ultra-mode-mvp/"
    "_bmad-output/implementation-artifacts/bakeoff-sto-2026-07-23/.api_key"
)

# Strong prompt: autoservice + paint/body shop
PROMPT = """Сделай продающий одностраничный сайт автосервиса «МоторХаус» на Каширском шоссе.

Специализация: полный сервис + малярный цех (покраска, локальный ремонт, полировка, антикор).

Верни ТОЛЬКО один готовый HTML-файл (HTML+CSS+JS внутри), без markdown и пояснений.

Обязательно:
1) Бренд «МоторХаус» — главный герой первого экрана, не мелкая подпись.
2) Hero full-bleed: атмосфера живого бокса/малярки (не плоский серый градиент, не «AI-purple»).
3) Палитра: асфальт + янтарь/охра. Без Inter/Roboto/Arial, без indigo.
4) Услуги (минимум 6 карточек с нормальным текстом, не одно слово):
   - Слесарные работы / ТО
   - Диагностика
   - Малярные работы и покраска
   - Локальный кузовной ремонт
   - Полировка и детейлинг
   - Шиномонтаж
5) Отдельный блок «Малярный цех»: камера, материалы, сроки, гарантия на ЛКП, до/после (можно стилизованные фото-плейсхолдеры https).
6) Почему мы: честная смета, гарантия, зона ожидания.
7) Отзывы (3) + FAQ (аккордеон кликабельный).
8) Форма записи: имя, телефон, авто, услуга (select с маляркой), дата/время; не один alert — inline success.
9) Контакты: Каширское шоссе, телефон, часы 9:00–21:00.
10) Мобилка обязательна: viewport, @media ≤768 и ≤480, сетки в 1 колонку, hamburger-nav, inputs ≥16px, без горизонтального скролла.
11) 2–3 осознанных motion (не бесконечный пульс CTA).
12) Sticky CTA «Записаться» на мобилке не перекрывает форму.

Сделай сайт максимально продуманным — как у сильного конкурента, не шаблонный AI-лендинг.
"""

RUNS = [
    {
        "label": "1_simple_polzovatelskiy",
        "title": "Пользовательский (simple)",
        "extra": {
            "zeus": {
                "mode": "simple",
                "path": "FULL",
                "product_mode": "simple",
            }
        },
    },
    {
        "label": "2_power_prodvinutyy",
        "title": "Продвинутый (power)",
        "extra": {
            "zeus": {
                "mode": "power",
                "path": "FULL",
                "product_mode": "power",
            }
        },
    },
    {
        "label": "3_custom_strongest",
        "title": "Набор из самых сильных",
        "extra": {
            "models": [
                "claude-fable-5",
                "gpt-5.6-sol",
                "claude-opus-4-8",
            ],
            "zeus": {
                "mode": "custom",
                "path": "FULL",
                "product_mode": "custom",
                "models": [
                    "claude-fable-5",
                    "gpt-5.6-sol",
                    "claude-opus-4-8",
                ],
                "leader": "claude-fable-5",
            },
        },
    },
]


def _load_key() -> str:
    k = API_KEY_FILE.read_text(encoding="utf-8").strip() if API_KEY_FILE.exists() else ""
    if not k:
        raise SystemExit(f"missing api key: {API_KEY_FILE}")
    return k


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
        "has_viewport": "viewport" in h.lower(),
        "has_form": "<form" in h.lower(),
        "has_nav": bool(re.search(r"<nav\b", h, re.I)),
        "has_paint": bool(re.search(r"маляр|покраск|лкп|paint|кузов", h, re.I)),
        "sections": len(re.findall(r"<section\b", h, re.I)),
        "live_link": (
            m.group(0)
            if (m := re.search(r"https://zeuscode\.ru/go/site-[a-z0-9]+/", h))
            else None
        ),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "PROMPT.txt").write_text(PROMPT, encoding="utf-8")
    key = _load_key()
    summary: list[dict] = []

    with httpx.Client(
        base_url=BASE,
        timeout=httpx.Timeout(1200.0, connect=30.0),
        headers={"Authorization": f"Bearer {key}"},
    ) as c:
        for cfg in RUNS:
            label = cfg["label"]
            print(f"\n===== {cfg['title']} ({label}) =====", flush=True)
            payload = {
                "model": "zeus/fusion",
                "stream": False,
                "max_tokens": 65536,
                "messages": [{"role": "user", "content": PROMPT}],
                **cfg["extra"],
            }
            t0 = time.perf_counter()
            data: dict = {}
            answer = ""
            status = 0
            err: str | None = None
            for attempt in range(1, 4):
                try:
                    r = c.post("/v1/chat/completions", json=payload)
                    status = r.status_code
                    try:
                        data = r.json()
                    except Exception:
                        data = {"raw": r.text[:2000]}
                    if isinstance(data, dict):
                        try:
                            answer = data["choices"][0]["message"]["content"] or ""
                        except Exception:
                            answer = ""
                    if status == 200 and answer.strip():
                        err = None
                        break
                    err = (r.text or "")[:600]
                except Exception as e:  # noqa: BLE001
                    err = str(e)[:600]
                    print(f"  retry {attempt}/3 after error: {err[:120]}", flush=True)
                    time.sleep(3 * attempt)
                    continue
                if attempt < 3:
                    print(f"  retry {attempt}/3 status={status}", flush=True)
                    time.sleep(3 * attempt)
            latency = round(time.perf_counter() - t0, 2)
            onestack = (data or {}).get("onestack") if isinstance(data, dict) else {}
            html = _extract_html(answer)
            (OUT / f"{label}.raw.txt").write_text(answer, encoding="utf-8")
            (OUT / f"{label}.html").write_text(html, encoding="utf-8")
            row = {
                "label": label,
                "title": cfg["title"],
                "ok": status == 200 and bool(html.strip()),
                "status": status,
                "latency_s": latency,
                "routed_by": (onestack or {}).get("routed_by"),
                "path": (onestack or {}).get("path"),
                "product_mode": (onestack or {}).get("product_mode"),
                "leader": (onestack or {}).get("leader"),
                "panel": (onestack or {}).get("panel"),
                "ui_crew": (onestack or {}).get("ui_crew"),
                "metrics": _metrics(html if html else answer),
                "error": err,
            }
            (OUT / f"{label}.json").write_text(
                json.dumps({**row, "onestack": onestack}, ensure_ascii=False, indent=2)[:400000],
                encoding="utf-8",
            )
            summary.append(row)
            print(
                json.dumps(
                    {
                        "ok": row["ok"],
                        "latency_s": row["latency_s"],
                        "routed_by": row["routed_by"],
                        "author": ((row.get("ui_crew") or {}) or {}).get("author"),
                        "panel": row["panel"],
                        "bytes": row["metrics"]["bytes"],
                        "paint": row["metrics"]["has_paint"],
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
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:5000])


if __name__ == "__main__":
    main()
