#!/usr/bin/env python3
"""Load-test stub for Fusion Path profiles (Story 4.9). Dry-run by default."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

PROFILES = {
    "FAST": {"path": "FAST", "concurrency": 20, "prompt": "привет"},
    "CASCADE": {"path": "CASCADE", "concurrency": 10, "prompt": "опиши README для fusion"},
    "RACE": {"path": "RACE", "concurrency": 3, "prompt": "сравни три подхода к sticky Leader"},
    "FULL": {"path": "FULL", "concurrency": 3, "prompt": "сделай лендинг для автосервиса"},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="all", help="FAST|CASCADE|RACE|FULL|all")
    ap.add_argument("--requests", type=int, default=10)
    ap.add_argument("--concurrency", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--live", action="store_true", help="Disable dry-run (ops only)")
    args = ap.parse_args()
    dry = not args.live
    names = list(PROFILES) if args.profile.upper() == "ALL" else [args.profile.upper()]
    from app.fusion.metrics import runtime_budgets_from_settings

    budgets = runtime_budgets_from_settings()
    report = {"dry_run": dry, "budgets": budgets.__dict__, "profiles": []}
    for name in names:
        if name not in PROFILES:
            print(f"unknown profile {name}", file=sys.stderr)
            return 2
        p = dict(PROFILES[name])
        if args.concurrency:
            p["concurrency"] = args.concurrency
        started = time.time()
        if dry:
            # Presence check only — no upstream flood
            ok = True
            errors = 0
        else:
            ok = False
            errors = args.requests
            print("LIVE mode not implemented in stub — record results manually", file=sys.stderr)
        report["profiles"].append(
            {
                "name": name,
                "path": p["path"],
                "concurrency": p["concurrency"],
                "requests": args.requests,
                "ok": ok,
                "errors": errors,
                "elapsed_s": round(time.time() - started, 3),
            }
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if dry else 1


if __name__ == "__main__":
    raise SystemExit(main())
