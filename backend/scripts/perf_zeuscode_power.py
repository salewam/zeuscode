#!/usr/bin/env python3
"""ZeusCode power crew — perf / bench prep harness.

Dry-run (default): role→model map, expected LLM calls, rough ₽ estimate, no upstream.
Live: POST /v1/chat/completions with zeuscode + mode=power (needs BASE + KEY).

Usage:
  cd backend && ../.venv/bin/python scripts/perf_zeuscode_power.py
  ../.venv/bin/python scripts/perf_zeuscode_power.py --live \\
      --base https://api.example --key zeus_xxx
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Expected fixed crew (must match roles._PRESET_STACKS["power"])
POWER_CREW = [
    "claude-opus-4-6",
    "gpt-5.4",
    "deepseek-v4-pro",
    "gemini-3.1-pro",
]

CASES: list[dict[str, Any]] = [
    {
        "id": "P01_chitchat",
        "bucket": "light",
        "prompt": "привет",
        "expect_roles": ["doer_logic", "mini_verifier"],
        "max_llm_calls": 2,
    },
    {
        "id": "P02_trivial_ui",
        "bucket": "light",
        "prompt": "поменяй цвет кнопки на красный",
        "expect_roles": ["doer_ui", "mini_verifier"],
        "max_llm_calls": 2,
    },
    {
        "id": "P03_code_fix",
        "bucket": "code",
        "prompt": "почини ImportError в auth.py: отсутствует jwt",
        "expect_roles": ["doer_logic", "mini_verifier"],
        "max_llm_calls": 2,
        "forbid_escalate": True,
    },
    {
        "id": "P04_ui_landing",
        "bucket": "ui",
        "prompt": "сделай простой hero блок лендинга на html+css",
        "expect_roles": ["doer_ui", "mini_verifier"],
        "max_llm_calls": 3,
        "forbid_escalate": True,
    },
    {
        "id": "P05_architecture",
        "bucket": "heavy",
        "prompt": "спроектируй архитектуру API биллинга с миграцией и тестами",
        "expect_roles": [
            "architect",
            "test_author",
            "doer_logic",
            "mini_verifier",
        ],
        "max_llm_calls": 6,
        "pipeline": "v1",
    },
]


def _prices() -> dict[str, tuple[float, float]]:
    """₽ / 1M tokens from catalog when available."""
    out: dict[str, tuple[float, float]] = {}
    try:
        from app.catalog import public_catalog

        for m in public_catalog():
            p = m.get("pricing") or {}
            inn = float(p.get("input_per_1m") or 0)
            outt = float(p.get("output_per_1m") or 0)
            out[str(m["id"])] = (inn, outt)
    except Exception:  # noqa: BLE001
        pass
    return out


def _estimate_rub(
    model_id: str,
    *,
    prices: dict[str, tuple[float, float]],
    prompt_tok: int = 1200,
    completion_tok: int = 800,
) -> float:
    inn, outt = prices.get(model_id, (0.0, 0.0))
    return (prompt_tok / 1_000_000) * inn + (completion_tok / 1_000_000) * outt


def dry_run() -> dict[str, Any]:
    from app.fusion.policy import cascade_escalate_action
    from app.fusion.roles import (
        assign_role_model,
        resolve_roles,
        resolve_stack,
    )

    stack = resolve_stack("power")
    prices = _prices()
    assert stack == POWER_CREW, f"power stack drift: {stack}"

    role_map = {
        r: assign_role_model(r, "power", stack).model_id
        for r in (
            "architect",
            "test_author",
            "doer_logic",
            "doer_ui",
            "mini_verifier",
            "judge_fix",
        )
    }
    esc = cascade_escalate_action(
        kill_switch=False,
        product_mode="power",
        complexity="med",
        phase="implement",
    )

    cases_out = []
    for c in CASES:
        kind = {
            "light": "light",
            "code": "code",
            "ui": "ui",
            "heavy": "architecture",
        }[c["bucket"]]
        rr = resolve_roles(product_mode="power", task_kind=kind)
        models = [role_map[r] for r in c["expect_roles"] if role_map.get(r)]
        est = sum(_estimate_rub(m, prices=prices) for m in models if m)
        cases_out.append(
            {
                "id": c["id"],
                "bucket": c["bucket"],
                "task_kind": kind,
                "models_by_role": {
                    r: role_map.get(r) for r in c["expect_roles"]
                },
                "resolved_doer": rr.models_by_role.get(
                    rr.meta.get("doer_role", "doer_logic")
                ),
                "est_rub_stub": round(est, 4),
                "max_llm_calls": c["max_llm_calls"],
                "ok_roles": all(role_map.get(r) for r in c["expect_roles"]),
            }
        )

    return {
        "mode": "dry_run",
        "product": "zeuscode",
        "power_stack": stack,
        "role_map": role_map,
        "cascade_escalate": {"action": esc.action, "routed_by": esc.routed_by},
        "invariants": {
            "no_gpt_55": "gpt-5.5" not in stack,
            "fixed_no_escalate": esc.action == "keep",
            "crew_size": len(stack) == 4,
            "architect_opus": role_map["architect"] == "claude-opus-4-6",
            "test_author_gpt54": role_map["test_author"] == "gpt-5.4",
            "doer_logic_ds": role_map["doer_logic"] == "deepseek-v4-pro",
            "doer_ui_gem": role_map["doer_ui"] == "gemini-3.1-pro",
            "mini_pro": role_map["mini_verifier"] == "deepseek-v4-pro",
        },
        "cases": cases_out,
        "est_rub_suite_stub": round(
            sum(float(x["est_rub_stub"]) for x in cases_out), 4
        ),
    }


def live_run(*, base: str, key: str, timeout: float = 180.0) -> dict[str, Any]:
    results = []
    for c in CASES:
        body = {
            "model": "zeuscode",
            "stream": False,
            "messages": [{"role": "user", "content": c["prompt"]}],
            "zeus": {"mode": "power", "thinking": False},
        }
        req = urllib.request.Request(
            base.rstrip("/") + "/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
            raw = e.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            results.append(
                {
                    "id": c["id"],
                    "ok": False,
                    "error": str(e),
                    "latency_s": round(time.perf_counter() - t0, 3),
                }
            )
            continue
        lat = round(time.perf_counter() - t0, 3)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"raw": raw[:500]}
        os_meta = (data.get("onestack") or {}) if isinstance(data, dict) else {}
        answer = ""
        if isinstance(data, dict):
            ch = (data.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            answer = str(msg.get("content") or "")
        n_branches = len(os_meta.get("branches") or [])
        results.append(
            {
                "id": c["id"],
                "ok": status == 200 and bool(answer.strip()),
                "http_status": status,
                "latency_s": lat,
                "path": os_meta.get("path") or os_meta.get("policy_path"),
                "routed_by": os_meta.get("routed_by"),
                "pipeline": os_meta.get("pipeline"),
                "models_by_role": os_meta.get("models_by_role"),
                "branch_n": n_branches,
                "escalate_from": os_meta.get("escalate_from"),
                "answer_chars": len(answer),
                "forbid_escalate_ok": (
                    not c.get("forbid_escalate")
                    or os_meta.get("routed_by")
                    != "cascade_escalate_stronger"
                ),
            }
        )
    ok_n = sum(1 for r in results if r.get("ok"))
    return {
        "mode": "live",
        "base": base,
        "ok": ok_n,
        "n": len(results),
        "p50_latency_s": _percentile(
            [float(r["latency_s"]) for r in results if "latency_s" in r], 50
        ),
        "p95_latency_s": _percentile(
            [float(r["latency_s"]) for r in results if "latency_s" in r], 95
        ),
        "cases": results,
    }


def _percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    k = max(0, min(len(ys) - 1, int(round((p / 100) * (len(ys) - 1)))))
    return round(ys[k], 3)


def main() -> int:
    ap = argparse.ArgumentParser(description="ZeusCode power crew perf harness")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--base", default=os.environ.get("ZEUS_PERF_BASE", ""))
    ap.add_argument("--key", default=os.environ.get("ZEUS_PERF_KEY", ""))
    ap.add_argument(
        "--out",
        default="",
        help="Write JSON report path (default stdout only)",
    )
    args = ap.parse_args()

    if args.live:
        if not args.base or not args.key:
            print(
                "LIVE needs --base and --key (or ZEUS_PERF_BASE / ZEUS_PERF_KEY)",
                file=sys.stderr,
            )
            return 2
        report = live_run(base=args.base, key=args.key)
        ok = report.get("ok", 0) == report.get("n", -1)
    else:
        report = dry_run()
        inv = report.get("invariants") or {}
        ok = all(bool(v) for v in inv.values()) and all(
            c.get("ok_roles") for c in report.get("cases") or []
        )
        report["ok"] = ok

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
