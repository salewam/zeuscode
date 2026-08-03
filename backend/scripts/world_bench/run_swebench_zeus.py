#!/usr/bin/env python3
"""SWE-bench Lite pilot: Zeus generates patches → official Docker harness eval.

Usage:
  export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock
  PYTHONPATH=backend .venv/bin/python backend/scripts/world_bench/run_swebench_zeus.py \\
    --limit 5 --max-workers 3
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SWE = ROOT / ".cache" / "world_bench" / "SWE-bench"
OUT = ROOT / "_bmad-output" / "implementation-artifacts" / "world-bench" / "swebench"


def _chat(base: str, key: str, messages: list[dict[str, str]], timeout: float) -> str:
    body = {
        "model": "zeuscode",
        "stream": False,
        "messages": messages,
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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return f"# HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}"
    except Exception as e:  # noqa: BLE001
        return f"# ERROR: {e}"
    ch = (data.get("choices") or [{}])[0]
    return str((ch.get("message") or {}).get("content") or "")


def extract_patch(text: str) -> str:
    """Best-effort extract unified diff from model output."""
    if "```diff" in text:
        return text.split("```diff", 1)[1].split("```", 1)[0].strip() + "\n"
    if "```patch" in text:
        return text.split("```patch", 1)[1].split("```", 1)[0].strip() + "\n"
    # raw diff starting with diff --git or ---
    m = re.search(r"(?ms)^(diff --git .*|--- .+)$", text)
    if m:
        return text[m.start() :].strip() + "\n"
    return text.strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("ZEUS_PERF_BASE", "http://127.0.0.1:8080"))
    ap.add_argument("--key", default=os.environ.get("ZEUS_PERF_KEY", ""))
    ap.add_argument("--limit", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--max-workers", type=int, default=3)
    ap.add_argument("--dataset", default="princeton-nlp/SWE-bench_Lite")
    ap.add_argument("--skip-eval", action="store_true")
    ap.add_argument("--run-id", default="zeuscode_power_lite")
    args = ap.parse_args()
    if not args.key:
        kp = Path("/tmp/zeus_bench.key")
        args.key = kp.read_text().strip() if kp.exists() else ""
    if not args.key:
        print("need --key", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault(
        "DOCKER_HOST", f"unix://{Path.home()}/.colima/default/docker.sock"
    )

    print(f"[swe] loading {args.dataset}…", flush=True)
    from datasets import load_dataset

    ds = load_dataset(args.dataset, split="test")
    rows = list(ds)[: max(1, args.limit)]
    preds_path = OUT / f"preds_{args.run_id}_n{len(rows)}.jsonl"
    meta: list[dict[str, Any]] = []

    with preds_path.open("w", encoding="utf-8") as fout:
        for i, row in enumerate(rows, 1):
            iid = str(row["instance_id"])
            problem = str(row.get("problem_statement") or "")
            hints = str(row.get("hints_text") or "")
            prompt = (
                f"You are fixing a GitHub issue in `{row.get('repo')}`.\n"
                f"Instance: {iid}\n"
                f"Base commit: {row.get('base_commit')}\n\n"
                f"## Issue\n{problem}\n\n"
                f"## Hints\n{hints}\n\n"
                "Return ONLY a unified git diff (patch) that fixes the issue. "
                "Use paths relative to repo root. No explanation."
            )
            print(f"[swe] {i}/{len(rows)} generate {iid} …", flush=True)
            t0 = time.perf_counter()
            raw = ""
            for attempt in range(1, 4):
                raw = _chat(
                    args.base,
                    args.key,
                    [
                        {
                            "role": "system",
                            "content": (
                                "You are a senior engineer. Reply with ONLY a valid "
                                "unified diff starting with 'diff --git'. No prose."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    args.timeout,
                )
                if raw.startswith("# HTTP") or raw.startswith("# ERROR"):
                    print(f"         attempt {attempt} fail: {raw[:120]}", flush=True)
                    time.sleep(2)
                    continue
                patch_try = extract_patch(raw)
                if patch_try.lstrip().startswith(("diff ", "--- a/", "--- ")):
                    raw = patch_try
                    break
                print(f"         attempt {attempt} not a diff ({len(raw)} chars)", flush=True)
            patch = extract_patch(raw) if not raw.lstrip().startswith("diff ") else raw
            if patch.startswith("# HTTP") or patch.startswith("# ERROR"):
                patch = ""  # empty → harness counts empty_patch, not garbage apply
            lat = round(time.perf_counter() - t0, 3)
            rec = {
                "instance_id": iid,
                "model_name_or_path": "zeuscode",
                "model_patch": patch,
            }
            fout.write(json.dumps(rec) + "\n")
            meta.append(
                {
                    "instance_id": iid,
                    "latency_s": lat,
                    "patch_chars": len(patch),
                    "looks_like_diff": patch.lstrip().startswith(("diff ", "---")),
                }
            )
            print(f"         patch_chars={len(patch)} lat={lat}s", flush=True)

    (OUT / f"meta_{args.run_id}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[swe] preds → {preds_path}", flush=True)

    if args.skip_eval:
        return 0

    py = SWE / ".venv" / "bin" / "python"
    if not py.exists():
        print(f"missing {py}", file=sys.stderr)
        return 1

    ids = [str(r["instance_id"]) for r in rows]
    cmd = [
        str(py),
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        args.dataset,
        "--predictions_path",
        str(preds_path),
        "--max_workers",
        str(args.max_workers),
        "--run_id",
        args.run_id,
        "--instance_ids",
        *ids,
    ]
    print("[swe] eval:", " ".join(cmd), flush=True)
    log_path = OUT / f"eval_{args.run_id}.log"
    with log_path.open("w", encoding="utf-8") as log:
        r = subprocess.run(
            cmd,
            cwd=str(SWE),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ},
        )
    print(f"[swe] eval exit={r.returncode} log={log_path}", flush=True)
    # print tail
    try:
        print(log_path.read_text(encoding="utf-8")[-4000:])
    except Exception:
        pass
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
