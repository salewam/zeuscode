"""Измерить реальную себестоимость моделей A6 по расходу баланса.

На каждую модель два вызова:
  A: много уникального входа, max_tokens=1  -> цена входа
  B: мало входа, длинный выход             -> цена выхода
Стоимость снимается как дельта /dashboard/billing/usage (USD) вокруг вызова.
Уникальный текст глушит prefix-кэш провайдера.

Результат: backend/scripts/a6_prices_measured.json
"""

from __future__ import annotations

import datetime
import json
import random
import string
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "a6_prices_measured.json"

IN_TOKENS_A = 8000
OUT_TOKENS_B = 1000
SETTLE_TRIES = 10
SETTLE_SLEEP = 2.0


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def unique_text(approx_tokens: int) -> str:
    # ~1 токен на слово из 6 латинских букв
    return " ".join(
        "".join(random.choices(string.ascii_lowercase, k=6)) for _ in range(approx_tokens)
    )


class Meter:
    def __init__(self, client: httpx.Client, base: str, headers: dict[str, str]) -> None:
        self.c = client
        self.headers = headers
        today = datetime.date.today()
        self.url = (
            f"{base}/dashboard/billing/usage"
            f"?start_date={today - datetime.timedelta(days=1)}"
            f"&end_date={today + datetime.timedelta(days=1)}"
        )

    def read(self) -> float:
        for _ in range(5):
            try:
                return float(self.c.get(self.url, headers=self.headers).json()["total_usage"])
            except Exception:
                time.sleep(2.0)
        raise RuntimeError("billing usage endpoint unreadable")

    def stable(self) -> float:
        """Дождаться, пока отложенные списания осядут: два одинаковых чтения подряд.

        Без этого списание предыдущей модели попадает в окно следующей и цена
        улетает в космос (наблюдалось на gemini-2.5-pro: $157/1M).
        """
        prev = self.read()
        for _ in range(20):
            time.sleep(SETTLE_SLEEP)
            now = self.read()
            if now == prev:
                return now
            prev = now
        return prev

    def settle(self, before: float) -> float:
        """Дождаться, пока биллинг учтёт вызов; вернуть дельту в USD."""
        for _ in range(SETTLE_TRIES):
            time.sleep(SETTLE_SLEEP)
            now = self.read()
            if now > before:
                return now - before
        return 0.0


def call(client, base, headers, model, messages, max_tokens):
    try:
        r = client.post(
            f"{base}/chat/completions",
            headers=headers,
            json={"model": model, "messages": messages, "max_tokens": max_tokens},
            timeout=300,
        )
    except Exception as e:
        return None, f"request failed: {type(e).__name__} {str(e)[:120]}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:180]}"
    try:
        body = r.json()
    except Exception:
        return None, f"non-JSON body: {r.text[:150]}"
    if not body.get("usage"):
        return None, "no usage in response"
    return body["usage"], None


def probe(client, base, headers, meter, model):
    row = {"model": model}

    # A: цена входа
    u0 = meter.stable()
    usage_a, err = call(
        client, base, headers, model,
        [{"role": "user", "content": "Reply with the single word OK.\n\n" + unique_text(IN_TOKENS_A)}],
        1,
    )
    if err:
        row["error"] = err
        return row
    cost_a = meter.settle(u0)

    # B: цена выхода
    u1 = meter.stable()
    usage_b, err = call(
        client, base, headers, model,
        [{"role": "user", "content": "Count from 1 to 400, one number per line, digits only."}],
        OUT_TOKENS_B,
    )
    if err:
        row["error"] = err
        row["cost_a_usd"] = cost_a
        return row
    cost_b = meter.settle(u1)

    ia, oa = usage_a["prompt_tokens"], usage_a["completion_tokens"]
    ib, ob = usage_b["prompt_tokens"], usage_b["completion_tokens"]
    row.update(
        cost_a_usd=cost_a, cost_b_usd=cost_b,
        usage_a={"in": ia, "out": oa, "cached": (usage_a.get("prompt_tokens_details") or {}).get("cached_tokens", 0)},
        usage_b={"in": ib, "out": ob, "cached": (usage_b.get("prompt_tokens_details") or {}).get("cached_tokens", 0)},
    )

    # Решаем систему: cost = in*pin/1e6 + out*pout/1e6
    det = ia * ob - ib * oa
    if det and cost_a and cost_b:
        pin = (cost_a * ob - cost_b * oa) * 1e6 / det
        pout = (cost_b * ia - cost_a * ib) * 1e6 / det
        row["in_usd_per_1m"] = round(pin, 4)
        row["out_usd_per_1m"] = round(pout, 4)
        if pin <= 0 or pout <= 0 or pin > 40 or pout / pin > 25:
            row["suspect"] = True  # окно поймало чужое списание — перемерить
    return row


def main() -> None:
    env = load_env()
    base = env["A6_BASE_URL"].rstrip("/")
    headers = {"Authorization": f"Bearer {env['A6_API_KEY']}"}

    catalog = json.loads((ROOT / "backend/app/data/a6_models.json").read_text(encoding="utf-8"))
    models = [m["id"] for m in catalog["models"]]
    if len(sys.argv) > 1:
        models = models[: int(sys.argv[1])]

    rows = []
    done: set[str] = set()
    if OUT.exists():  # возобновление: не переплачивать за уже измеренное
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        rows = [
            r for r in prev.get("rows", [])
            if r.get("in_usd_per_1m") is not None and not r.get("suspect")
        ]
        done = {r["model"] for r in rows}

    with httpx.Client(timeout=300) as client:
        meter = Meter(client, base, headers)
        start_balance = meter.read()
        todo = [m for m in models if m not in done]
        print(
            f"start total_usage=${start_balance:.4f}  todo={len(todo)}  resumed={len(done)}",
            flush=True,
        )
        for i, m in enumerate(todo, 1):
            t = time.time()
            row = probe(client, base, headers, meter, m)
            rows.append(row)
            tag = row.get("error") or (
                f"in=${row.get('in_usd_per_1m')}/1M out=${row.get('out_usd_per_1m')}/1M"
            )
            print(f"[{i}/{len(todo)}] {m:34} {tag}  ({time.time() - t:.0f}s)", flush=True)
            OUT.write_text(
                json.dumps(
                    {"measured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     "spent_usd": meter.read() - start_balance, "rows": rows},
                    ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(f"\ndone. spent=${meter.read() - start_balance:.4f} -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
