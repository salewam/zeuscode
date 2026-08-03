#!/usr/bin/env python3
"""LiveCodeBench code-generation via ZeusCode → LCB custom_evaluator.

Loads problems from HuggingFace (no torch in this process), generates with Zeus,
evaluates with LiveCodeBench's own venv.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LCB = ROOT / ".cache" / "world_bench" / "LiveCodeBench"
OUT = ROOT / "_bmad-output" / "implementation-artifacts" / "world-bench" / "livecodebench"


def _chat(base: str, key: str, prompt: str, timeout: float) -> tuple[str, float, int]:
    body = {
        "model": "zeuscode",
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a competitive programmer. Write a correct Python 3 solution. "
                    "Output ONLY code in a ```python fence. No explanations."
                ),
            },
            {"role": "user", "content": prompt},
        ],
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
            status = int(resp.status)
    except urllib.error.HTTPError as e:
        status = int(e.code)
        raw = e.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return f"# ERROR: {e}", round(time.perf_counter() - t0, 3), 0
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:2000], round(time.perf_counter() - t0, 3), status
    ch = (data.get("choices") or [{}])[0]
    content = str((ch.get("message") or {}).get("content") or "")
    return content, round(time.perf_counter() - t0, 3), status


def extract_python(text: str) -> str:
    if "```python" in text:
        return text.split("```python", 1)[1].split("```", 1)[0].strip()
    if "```" in text:
        return text.split("```", 1)[1].split("```", 1)[0].strip()
    return text.strip()


def load_problems(limit: int) -> list[dict[str, str]]:
    from datasets import load_dataset

    # Lite codegen set used by LCB
    for name, conf in (
        ("livecodebench/code_generation_lite", "release_v5"),
        ("livecodebench/code_generation_lite", None),
        ("livecodebench/code_generation", None),
    ):
        try:
            if conf:
                ds = load_dataset(name, conf, split="test", trust_remote_code=True)
            else:
                ds = load_dataset(name, split="test", trust_remote_code=True)
            break
        except Exception as e:  # noqa: BLE001
            last = e
            ds = None
    else:
        raise RuntimeError(f"cannot load LiveCodeBench dataset: {last}")

    items: list[dict[str, str]] = []
    for i, row in enumerate(ds):
        qid = str(row.get("question_id") or row.get("id") or f"q{i}")
        prompt = str(
            row.get("question_content")
            or row.get("question")
            or row.get("problem")
            or row.get("prompt")
            or ""
        )
        if not prompt:
            continue
        # Prefer contest-style statement
        starter = row.get("starter_code") or ""
        if starter:
            prompt = prompt + "\n\nStarter code:\n" + str(starter)
        items.append({"question_id": qid, "prompt": prompt})
        if limit and len(items) >= limit:
            break
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("ZEUS_PERF_BASE", "http://127.0.0.1:8080"))
    ap.add_argument("--key", default=os.environ.get("ZEUS_PERF_KEY", ""))
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--release", default="release_v5")
    ap.add_argument("--skip-eval", action="store_true")
    args = ap.parse_args()
    if not args.key:
        kp = Path("/tmp/zeus_bench.key")
        args.key = kp.read_text().strip() if kp.exists() else ""
    if not args.key:
        print("need --key", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    print("[lcb] loading problems…", flush=True)
    items = load_problems(args.limit)
    print(f"[lcb] n={len(items)} generating via Zeus…", flush=True)

    custom: list[dict[str, Any]] = []
    meta: list[dict[str, Any]] = []
    for i, it in enumerate(items, 1):
        print(f"[lcb] {i}/{len(items)} {it['question_id']} …", flush=True)
        raw, lat, status = _chat(args.base, args.key, it["prompt"], args.timeout)
        code = extract_python(raw)
        custom.append({"question_id": it["question_id"], "code_list": [code]})
        meta.append(
            {
                "question_id": it["question_id"],
                "latency_s": lat,
                "http_status": status,
                "code_chars": len(code),
            }
        )

    out_json = OUT / f"zeus_lcb_{args.release}_n{len(items)}.json"
    out_json.write_text(json.dumps(custom, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / f"zeus_lcb_{args.release}_n{len(items)}_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[lcb] wrote {out_json}", flush=True)

    if args.skip_eval:
        return 0

    venv_py = LCB / ".venv" / "bin" / "python"
    if not venv_py.exists():
        print(f"[lcb] missing {venv_py}; generations saved only", file=sys.stderr)
        return 1

    cmd = [
        str(venv_py),
        "-m",
        "lcb_runner.runner.custom_evaluator",
        "--custom_output_file",
        str(out_json),
        "--scenario",
        "codegeneration",
        "--release_version",
        args.release,
    ]
    print("[lcb] evaluating…", flush=True)
    r = subprocess.run(cmd, cwd=str(LCB), capture_output=True, text=True, timeout=900)
    (OUT / "last_eval_stdout.txt").write_text(r.stdout or "", encoding="utf-8")
    (OUT / "last_eval_stderr.txt").write_text(r.stderr or "", encoding="utf-8")
    print((r.stdout or "")[-4000:])
    if r.returncode != 0:
        print((r.stderr or "")[-3000:], file=sys.stderr)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
