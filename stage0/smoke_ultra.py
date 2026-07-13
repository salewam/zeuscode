#!/usr/bin/env python3
"""ZeusCode — Stage 0 smoke: ONLY cheapest upstream chat model (Gemini 2.5 Flash)."""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

UPSTREAM_BASE = os.getenv("UPSTREAM_BASE_URL", "").strip().rstrip("/")
API_KEY = os.getenv("UPSTREAM_API_KEY", "").strip()
OUT_DIR = Path(__file__).resolve().parent / "out"

# Cheapest chat model today: $0.09 / $0.90 per 1M (in/out)
CHEAP_PATH = "gemini-2.5-flash"
CHEAP_LABEL = "gemini-2.5-flash"
PRICE_IN = 0.09
PRICE_OUT = 0.75

USER_TASK = """Сделай минимальный TODO-сервис:
- frontend: одна HTML-страница со списком и формой добавления
- backend: простой FastAPI с in-memory списком
- tests: 2-3 pytest проверки
- docs: короткий README
Код должен быть коротким, без лишней воды."""


@dataclass
class AgentResult:
    role: str
    model: str
    ok: bool
    text: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    latency_s: float = 0.0
    error: str = ""


def require_key() -> str:
    if not API_KEY or not UPSTREAM_BASE:
        raise SystemExit("Нет UPSTREAM_API_KEY / UPSTREAM_BASE_URL в .env")
    return API_KEY


async def get_credits(client: httpx.AsyncClient) -> Any:
    r = await client.get(f"{UPSTREAM_BASE}/api/v1/chat/credit")
    r.raise_for_status()
    return r.json()


async def call_gemini(
    client: httpx.AsyncClient,
    *,
    system: str,
    user: str,
) -> tuple[str, dict[str, Any]]:
    url = f"{UPSTREAM_BASE}/{CHEAP_PATH}/v1/chat/completions"
    payload = {
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": system}]},
            {"role": "user", "content": [{"type": "text", "text": user}]},
        ],
        "stream": False,
        "include_thoughts": False,
        "reasoning_effort": "low",
    }
    r = await client.post(url, json=payload)
    data = r.json()
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {json.dumps(data, ensure_ascii=False)[:1200]}")
    if "choices" not in data:
        raise RuntimeError(f"Unexpected: {json.dumps(data, ensure_ascii=False)[:1200]}")
    msg = data["choices"][0].get("message") or {}
    text = msg.get("content") or ""
    if isinstance(text, list):
        text = "\n".join(p.get("text", "") for p in text if isinstance(p, dict))
    return str(text), data.get("usage") or {}


AGENTS = [
    (
        "frontend",
        "Ты Frontend-разработчик. Верни только HTML+минимальный JS для UI TODO. Без markdown-объяснений.",
    ),
    (
        "backend",
        "Ты Backend-разработчик. Верни только код FastAPI (in-memory TODO API). Без лишних пояснений.",
    ),
    (
        "tests",
        "Ты QA-инженер. Верни только pytest-тесты для TODO FastAPI сервиса. Коротко, 2-3 теста.",
    ),
    (
        "docs",
        "Ты technical writer. Верни только короткий README.md: запуск, эндпоинты, структура.",
    ),
]


async def run_agent(client: httpx.AsyncClient, role: str, system: str) -> AgentResult:
    t0 = time.perf_counter()
    try:
        text, usage = await call_gemini(client, system=system, user=USER_TASK)
        return AgentResult(
            role=role,
            model=CHEAP_LABEL,
            ok=True,
            text=text,
            usage=usage,
            latency_s=time.perf_counter() - t0,
        )
    except Exception as e:  # noqa: BLE001
        return AgentResult(
            role=role,
            model=CHEAP_LABEL,
            ok=False,
            latency_s=time.perf_counter() - t0,
            error=str(e),
        )


async def synthesize(client: httpx.AsyncClient, parts: list[AgentResult]) -> AgentResult:
    blob = []
    for p in parts:
        blob.append(f"\n===== {p.role.upper()} =====\n{p.text[:5000]}\n")
    user = (
        "Склей в один проект файлы: frontend.html, main.py, test_main.py, README.md. "
        "Исправь конфликты. Код важнее воды.\n" + "".join(blob)
    )
    t0 = time.perf_counter()
    try:
        text, usage = await call_gemini(
            client,
            system="Ты Senior-архитектор. Склеиваешь параллельные куски в рабочий MVP.",
            user=user,
        )
        return AgentResult(
            role="synthesis",
            model=CHEAP_LABEL,
            ok=True,
            text=text,
            usage=usage,
            latency_s=time.perf_counter() - t0,
        )
    except Exception as e:  # noqa: BLE001
        return AgentResult(
            role="synthesis",
            model=CHEAP_LABEL,
            ok=False,
            latency_s=time.perf_counter() - t0,
            error=str(e),
        )


def estimate_usd(usage: dict[str, Any]) -> float:
    inn = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    out = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    return (inn / 1_000_000) * PRICE_IN + (out / 1_000_000) * PRICE_OUT


async def main() -> None:
    require_key()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(headers=headers, timeout=180.0) as client:
        print("=== ZeusCode Stage 0 — CHEAP ONLY (gemini-2.5-flash) ===\n")
        before = await get_credits(client)
        print("Credits before:", json.dumps(before, ensure_ascii=False))

        print("\n→ 4 parallel agents...")
        t0 = time.perf_counter()
        results = await asyncio.gather(
            *[run_agent(client, role, system) for role, system in AGENTS]
        )
        parallel_s = time.perf_counter() - t0

        for r in results:
            flag = "OK" if r.ok else "FAIL"
            print(
                f"  [{flag}] {r.role:10} {r.latency_s:.1f}s "
                f"usage={r.usage or '-'} err={r.error[:160]}"
            )

        ok = [r for r in results if r.ok]
        if len(ok) < 2:
            raise SystemExit("Мало успешных агентов")

        print("\n→ Synthesis...")
        synth = await synthesize(client, ok)
        print(
            f"  [{'OK' if synth.ok else 'FAIL'}] synthesis {synth.latency_s:.1f}s "
            f"usage={synth.usage or '-'} err={synth.error[:160]}"
        )

        after = await get_credits(client)
        print("\nCredits after:", json.dumps(after, ensure_ascii=False))

        all_runs = list(results) + [synth]
        est = sum(estimate_usd(r.usage) for r in all_runs if r.ok)

        before_c = (before.get("data") if isinstance(before, dict) else None)
        after_c = (after.get("data") if isinstance(after, dict) else None)
        spent = None
        if isinstance(before_c, (int, float)) and isinstance(after_c, (int, float)):
            spent = before_c - after_c

        report = {
            "model": CHEAP_LABEL,
            "price_in_out_per_1m_usd": [PRICE_IN, PRICE_OUT],
            "parallel_wall_s": round(parallel_s, 2),
            "credits_before": before_c,
            "credits_after": after_c,
            "credits_spent": spent,
            "estimate_usd_from_tokens": round(est, 6),
            "agents": [
                {
                    "role": r.role,
                    "ok": r.ok,
                    "latency_s": round(r.latency_s, 2),
                    "usage": r.usage,
                    "chars": len(r.text),
                    "error": r.error,
                }
                for r in all_runs
            ],
        }
        (OUT_DIR / "smoke_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (OUT_DIR / "synthesis.txt").write_text(synth.text or synth.error, encoding="utf-8")
        for r in results:
            (OUT_DIR / f"{r.role}.txt").write_text(r.text or r.error, encoding="utf-8")

        print("\n=== SUMMARY ===")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\nSaved → {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
