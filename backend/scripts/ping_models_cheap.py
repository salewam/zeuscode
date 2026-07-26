#!/usr/bin/env python3
"""Minimal per-model health ping via Zeus /v1/chat/completions.

One tiny prompt + max_tokens=8 per model. Prints OK/FAIL + rub delta.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

BASE = "https://zeuscode.ru"
EMAIL = "gemini-only@onestack.dev"
PASS = "GeminiOnly2026!"
OUT = Path("/tmp/model-ping")

# Mixed-bake set + any extra cheap workers we care about
MODELS = [
    "gemini-2.5-flash",
    "gemini-3-flash",
    "claude-haiku-4-5",
    "grok-4-3",
    "gpt-5-2",
]

PROMPT = "Reply with exactly: OK"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    with httpx.Client(base_url=BASE, timeout=90.0, verify=False) as c:
        r = c.post("/auth/login", json={"email": EMAIL, "password": PASS})
        r.raise_for_status()
        tok = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}"}

        # fresh API key for /v1/chat/completions
        key_r = c.post("/keys", headers=headers, json={"name": f"ping-{int(time.time())}"})
        key_r.raise_for_status()
        api_key = key_r.json().get("raw_key") or key_r.json().get("api_key")
        if not api_key:
            raise SystemExit(f"no api key in response: {key_r.text[:300]}")

        me0 = c.get("/auth/me", headers=headers).json()
        bal0 = float(me0.get("balance_rub") or me0.get("kie_credits") or 0)
        print(f"LOGIN balance={bal0} models={len(MODELS)}", flush=True)

        api_h = {"Authorization": f"Bearer {api_key}"}

        for mid in MODELS:
            t0 = time.time()
            status = "FAIL"
            err = ""
            preview = ""
            usage = {}
            charged = None
            try:
                resp = c.post(
                    "/v1/chat/completions",
                    headers=api_h,
                    json={
                        "model": mid,
                        "messages": [{"role": "user", "content": PROMPT}],
                        "max_tokens": 8,
                        "stream": False,
                    },
                )
                latency = round(time.time() - t0, 2)
                body = resp.json() if resp.content else {}
                if resp.status_code >= 400:
                    err = (
                        body.get("detail")
                        or body.get("message")
                        or body.get("msg")
                        or resp.text[:240]
                    )
                    if isinstance(err, list):
                        err = json.dumps(err, ensure_ascii=False)[:240]
                else:
                    choice = (body.get("choices") or [{}])[0]
                    msg = (choice.get("message") or {}).get("content") or ""
                    preview = str(msg).replace("\n", " ")[:80]
                    usage = body.get("usage") or {}
                    charged = body.get("charged_rub") or body.get("cost_rub")
                    status = "OK" if preview.strip() else "EMPTY"
            except Exception as e:
                latency = round(time.time() - t0, 2)
                err = str(e)[:240]

            row = {
                "model": mid,
                "status": status,
                "latency_s": latency,
                "preview": preview,
                "error": str(err)[:300],
                "prompt_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
                "completion_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
                "charged_rub": charged,
            }
            rows.append(row)
            flag = "✓" if status == "OK" else "✗"
            print(
                f"{flag} {mid:22} {status:5} {latency:6.2f}s  "
                f"tok={row['prompt_tokens']}/{row['completion_tokens']}  "
                f"{preview or err}",
                flush=True,
            )

        me1 = c.get("/auth/me", headers=headers).json()
        bal1 = float(me1.get("balance_rub") or me1.get("kie_credits") or 0)
        spent = round(bal0 - bal1, 4)
        report = {
            "balance_start": bal0,
            "balance_end": bal1,
            "spent_rub": spent,
            "rows": rows,
        }
        (OUT / "REPORT.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nSPENT ≈ {spent} ₽  ({bal0} → {bal1})", flush=True)
        ok = sum(1 for r in rows if r["status"] == "OK")
        print(f"OK {ok}/{len(rows)}  → {OUT / 'REPORT.json'}", flush=True)


if __name__ == "__main__":
    main()
