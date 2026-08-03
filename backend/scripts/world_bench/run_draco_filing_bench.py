#!/usr/bin/env python3
"""DRACO (Perplexity) against ZeusCode — generate + rubric-judge.

Dataset: https://huggingface.co/datasets/perplexity-ai/draco
Method (aligned with paper/OpenRouter):
  1) answer each research task via Zeus /v1
  2) grade each rubric criterion MET/UNMET via judge LLM
  3) weighted mean → percent score

Usage:
  PYTHONPATH=backend .venv/bin/python backend/scripts/world_bench/run_draco_zeus.py \\
    --base http://127.0.0.1:8080 --key \"$(cat /tmp/zeus_bench.key)\" \\
    --limit 5 --judge-via zeus
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / ".cache" / "world_bench"
OUT = ROOT / "_bmad-output" / "implementation-artifacts" / "world-bench" / "draco"
DATASET_PATH = CACHE / "draco" / "test.jsonl"


def _http_json(
    url: str,
    *,
    key: str,
    body: dict[str, Any],
    timeout: float,
) -> tuple[int, dict[str, Any], float]:
    req = urllib.request.Request(
        url,
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
        return 0, {"error": str(e)}, round(time.perf_counter() - t0, 3)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw": raw[:2000]}
    return status, data, round(time.perf_counter() - t0, 3)


def _chat_content(data: dict[str, Any]) -> str:
    ch = (data.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    return str(msg.get("content") or "")


def download_draco() -> Path:
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DATASET_PATH.exists() and DATASET_PATH.stat().st_size > 1000:
        return DATASET_PATH
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        repo_id="perplexity-ai/draco",
        filename="test.jsonl",
        repo_type="dataset",
        local_dir=str(DATASET_PATH.parent),
    )
    p = Path(path)
    if p.resolve() != DATASET_PATH.resolve():
        DATASET_PATH.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    return DATASET_PATH


def load_tasks(limit: int | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with DATASET_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if limit and len(rows) >= limit:
                break
    return rows


def extract_query(task: dict[str, Any]) -> str:
    # Official HF schema: problem / answer(rubric JSON) / domain
    if task.get("problem"):
        return str(task["problem"])
    for k in ("query", "prompt", "question", "task", "user_query"):
        if task.get(k):
            return str(task[k])
    return json.dumps(task, ensure_ascii=False)[:4000]


def extract_rubric(task: dict[str, Any]) -> list[dict[str, Any]]:
    """DRACO stores expert rubric in the `answer` JSON string (sections→criteria)."""
    raw = task.get("answer") or task.get("rubric") or task.get("criteria") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    out: list[dict[str, Any]] = []
    if isinstance(raw, dict) and isinstance(raw.get("sections"), list):
        for s in raw["sections"]:
            axis = str((s or {}).get("id") or (s or {}).get("title") or "")
            for i, c in enumerate((s or {}).get("criteria") or []):
                if not isinstance(c, dict):
                    continue
                text = (
                    c.get("requirement")
                    or c.get("description")
                    or c.get("criterion")
                    or c.get("text")
                    or ""
                )
                try:
                    weight = float(c.get("weight", 1.0))
                except (TypeError, ValueError):
                    weight = 1.0
                out.append(
                    {
                        "id": str(c.get("id") or f"{axis}_{i}"),
                        "text": str(text),
                        "weight": weight,
                        "axis": axis,
                    }
                )
        return out
    rub = raw if isinstance(raw, list) else (
        (raw.get("criteria") or raw.get("items") or []) if isinstance(raw, dict) else []
    )
    for i, c in enumerate(rub):
        if isinstance(c, str):
            out.append({"id": f"c{i}", "text": c, "weight": 1.0, "axis": ""})
            continue
        if not isinstance(c, dict):
            continue
        text = (
            c.get("criterion")
            or c.get("text")
            or c.get("description")
            or c.get("requirement")
            or ""
        )
        try:
            weight = float(c.get("weight", c.get("points", 1.0)))
        except (TypeError, ValueError):
            weight = 1.0
        out.append(
            {
                "id": str(c.get("id") or f"c{i}"),
                "text": str(text),
                "weight": weight,
                "axis": str(c.get("axis") or c.get("category") or ""),
            }
        )
    return out


def zeus_answer(
    *,
    base: str,
    key: str,
    query: str,
    timeout: float,
    retries: int = 2,
) -> tuple[str, dict[str, Any]]:
    """Call ZeusCode power+research; retry on empty / 5xx / 429 (A6 flakiness)."""
    body = {
        "model": "zeuscode",
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a deep research assistant. Produce a thorough, "
                    "well-structured research report with citations/URLs where possible. "
                    "Be accurate; do not invent facts."
                ),
            },
            {"role": "user", "content": query},
        ],
        "zeus": {
            "mode": "power",
            "thinking": True,
                # Force research×3→Opus 4.6 glue (no GPT doer) on every DRACO task
                "research": True,
        },
    }
    ans = ""
    meta: dict[str, Any] = {}
    attempts = max(1, int(retries) + 1)
    for attempt in range(1, attempts + 1):
        status, data, lat = _http_json(
            base.rstrip("/") + "/v1/chat/completions",
            key=key,
            body=body,
            timeout=timeout,
        )
        ans = _chat_content(data) if status == 200 else ""
        onestack = data.get("onestack") if isinstance(data.get("onestack"), dict) else {}
        meta = {
            "http_status": status,
            "latency_s": lat,
            "error": data.get("error") or data.get("detail"),
            "onestack": onestack,
            "research_ok": onestack.get("research_ok"),
            "research_meta": onestack.get("research_meta"),
            "empty_guard": data.get("_empty_guard"),
            "gen_attempts": attempt,
        }
        if ans.strip() and status == 200:
            return ans, meta
        if attempt < attempts:
            # 502/503/429/empty — back off and retry whole Zeus turn
            delay = min(20.0, 2.5 * attempt)
            print(
                f"         retry gen {attempt}/{attempts - 1} "
                f"status={status} chars={len(ans)} sleep={delay:.1f}s",
                flush=True,
            )
            time.sleep(delay)
    return ans, meta


def judge_criterion(
    *,
    base: str,
    key: str,
    query: str,
    answer: str,
    criterion: str,
    timeout: float,
    judge_model: str,
) -> dict[str, Any]:
    prompt = (
        "You are an evaluation judge for DRACO-style rubrics.\n"
        "Given the user research query, the system answer, and ONE criterion, "
        "decide if the criterion is MET or UNMET.\n"
        "Reply with JSON only: {\"verdict\":\"MET\"|\"UNMET\",\"reason\":\"...\"}\n\n"
        f"QUERY:\n{query}\n\n"
        f"ANSWER:\n{answer[:12000]}\n\n"
        f"CRITERION:\n{criterion}\n"
    )
    body: dict[str, Any] = {
        "model": judge_model,
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    if judge_model == "zeuscode":
        # Never spin research/power crew for rubric judging — kills throughput.
        body["zeus"] = {
            "mode": "power",
            "thinking": False,
            "research": False,
            "skip_research": True,
            "clarify": False,
        }
    status, data, lat = 0, {}, 0.0
    text = ""
    for attempt in range(3):
        status, data, lat = _http_json(
            base.rstrip("/") + "/v1/chat/completions",
            key=key,
            body=body,
            timeout=timeout,
        )
        text = _chat_content(data) if status == 200 else ""
        if status == 200 and text.strip():
            break
        time.sleep(1.5 * (attempt + 1))
    verdict = "UNMET"
    reason = text[:300]
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            j = json.loads(m.group(0))
            v = str(j.get("verdict") or "").upper()
            if v in ("MET", "UNMET"):
                verdict = v
            reason = str(j.get("reason") or reason)[:300]
        except json.JSONDecodeError:
            pass
    elif "MET" in text.upper() and "UNMET" not in text.upper():
        verdict = "MET"
    return {
        "verdict": verdict,
        "reason": reason,
        "http_status": status,
        "latency_s": lat,
    }


def score_task(criteria_results: list[dict[str, Any]], rubric: list[dict[str, Any]]) -> float:
    if not rubric:
        return 0.0
    tw = sum(float(c.get("weight") or 1.0) for c in rubric) or 1.0
    got = 0.0
    for c, r in zip(rubric, criteria_results):
        if r.get("verdict") == "MET":
            got += float(c.get("weight") or 1.0)
    return 100.0 * got / tw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("ZEUS_PERF_BASE", "http://127.0.0.1:8080"))
    ap.add_argument("--key", default=os.environ.get("ZEUS_PERF_KEY", ""))
    ap.add_argument("--limit", type=int, default=5, help="0 = all 100 (expensive)")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--judge-timeout", type=float, default=90.0)
    ap.add_argument(
        "--judge-model",
        default="deepseek-v4-flash",
        help="Judge model id (prefer flash: deepseek-v4-flash / gemini-3-flash-preview). Avoid zeuscode.",
    )
    ap.add_argument(
        "--max-criteria",
        type=int,
        default=12,
        help="Cap criteria/task; 0 = ALL criteria (full DRACO)",
    )
    ap.add_argument("--skip-judge", action="store_true")
    ap.add_argument("--download-only", action="store_true")
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Resume from inference_checkpoint.jsonl (skip done ids)",
    )
    ap.add_argument(
        "--checkpoint",
        default="",
        help="Checkpoint jsonl path (default: OUT/inference_checkpoint.jsonl)",
    )
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    ckpt_path = Path(args.checkpoint) if args.checkpoint else (OUT / "inference_checkpoint.jsonl")
    print("[draco] downloading dataset…", flush=True)
    download_draco()
    if args.download_only:
        print(f"[draco] saved {DATASET_PATH}", flush=True)
        return 0

    if not args.key:
        key_path = Path("/tmp/zeus_bench.key")
        if key_path.exists():
            args.key = key_path.read_text(encoding="utf-8").strip()
    if not args.key:
        print("need --key", file=sys.stderr)
        return 2

    limit = None if args.limit == 0 else max(1, args.limit)
    tasks = load_tasks(limit)
    print(
        f"[draco] FULL tasks={len(tasks)} judge={args.judge_model} "
        f"max_criteria={'ALL' if args.max_criteria == 0 else args.max_criteria} "
        f"resume={args.resume}",
        flush=True,
    )

    # peek schema
    sample = {k: type(v).__name__ for k, v in tasks[0].items()} if tasks else {}
    (OUT / "schema_sample.json").write_text(
        json.dumps({"keys": sample, "task0_preview": {k: str(tasks[0].get(k))[:200] for k in list(tasks[0])[:20]}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    results: list[dict[str, Any]] = []
    done_ids: set[str] = set()
    pending_judge: dict[str, dict[str, Any]] = {}
    if args.resume and ckpt_path.exists():
        for line in ckpt_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row0 = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = str(row0.get("id") or "")
            if not rid:
                continue
            # finished scoring — but empty fail (0 chars) is retriable
            if row0.get("score_pct") is not None:
                ans0 = str(row0.get("answer") or "").strip()
                chars0 = int(row0.get("answer_chars") or 0)
                if not ans0 and chars0 <= 0:
                    print(
                        f"[draco] resume: will retry empty fail {rid[:8]}…",
                        flush=True,
                    )
                    continue
                # Judge transport death: all UNMET + empty reasons / http 0 → rejudge
                crit0 = row0.get("criteria") or []
                if ans0 and crit0:
                    empty_r = sum(1 for c in crit0 if not str(c.get("reason") or "").strip())
                    bad_http = sum(1 for c in crit0 if int(c.get("http_status") or 0) == 0)
                    if empty_r >= max(3, len(crit0) // 2) or bad_http >= max(3, len(crit0) // 2):
                        print(
                            f"[draco] resume: will rejudge dead-judge row {rid[:8]}… "
                            f"(empty_reason={empty_r} http0={bad_http})",
                            flush=True,
                        )
                        row0 = dict(row0)
                        row0["score_pct"] = None
                        row0["criteria"] = []
                        pending_judge[rid] = row0
                        continue
                results.append(row0)
                done_ids.add(rid)
            elif row0.get("answer"):
                # answer saved, judge incomplete — resume scoring only
                pending_judge[rid] = row0
        print(
            f"[draco] resume: loaded {len(done_ids)} done, "
            f"{len(pending_judge)} pending_judge from {ckpt_path}",
            flush=True,
        )

    def _flush_ckpt() -> None:
        ckpt_path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n",
            encoding="utf-8",
        )

    for i, task in enumerate(tasks, 1):
        tid = str(task.get("id") or task.get("task_id") or f"t{i}")
        if tid in done_ids:
            print(f"[draco] {i}/{len(tasks)} {tid} SKIP (resume)", flush=True)
            continue
        query = extract_query(task)
        rubric_all = extract_rubric(task)
        if args.max_criteria == 0:
            rubric = rubric_all
        else:
            rubric = rubric_all[: max(1, args.max_criteria)]
        print(f"[draco] {i}/{len(tasks)} {tid} rubric={len(rubric)}/{len(rubric_all)} …", flush=True)
        if tid in pending_judge:
            row = pending_judge[tid]
            answer = str(row.get("answer") or "")
            print(
                f"         reuse saved answer chars={len(answer)} (skip gen)",
                flush=True,
            )
        else:
            answer, meta = zeus_answer(
                base=args.base, key=args.key, query=query, timeout=args.timeout
            )
            row = {
                "id": tid,
                "query": query[:500],
                "answer_chars": len(answer),
                "answer": answer,
                "gen": meta,
                "rubric_n": len(rubric),
                "rubric_total": len(rubric_all),
                "criteria": [],
                "score_pct": None,
            }
            # save answer before slow judge so resume can skip regen
            results.append(row)
            _flush_ckpt()
            results.pop()
        if answer and not args.skip_judge and rubric:
            crit_out = []
            for ci, c in enumerate(rubric, 1):
                if ci == 1 or ci % 10 == 0 or ci == len(rubric):
                    print(f"         judge {ci}/{len(rubric)}…", flush=True)
                j = judge_criterion(
                    base=args.base,
                    key=args.key,
                    query=query,
                    answer=answer,
                    criterion=c["text"],
                    timeout=args.judge_timeout,
                    judge_model=args.judge_model,
                )
                crit_out.append({**c, **j})
            row["criteria"] = crit_out
            row["score_pct"] = round(score_task(crit_out, rubric), 2)
            print(f"         score={row['score_pct']}%", flush=True)
        elif not answer:
            row["score_pct"] = 0.0
            print("         FAIL empty answer", flush=True)
        results.append(row)
        done_ids.add(tid)
        _flush_ckpt()
        # live summary
        scored = [r["score_pct"] for r in results if r.get("score_pct") is not None]
        if scored:
            print(
                f"         running_mean={sum(scored)/len(scored):.2f}% "
                f"({len(scored)}/{len(tasks)})",
                flush=True,
            )

    scored = [r["score_pct"] for r in results if r.get("score_pct") is not None]
    tag = "full100" if args.limit == 0 else f"limit{args.limit}"
    summary = {
        "benchmark": "DRACO",
        "system": "zeuscode/power",
        "tag": tag,
        "n_tasks_requested": len(tasks),
        "n_tasks": len(results),
        "n_scored": len(scored),
        "mean_score_pct": round(sum(scored) / len(scored), 2) if scored else None,
        "judge_model": args.judge_model,
        "max_criteria": args.max_criteria,
        "openrouter_chart_peer_r2": 68.5,
        "note": (
            "Full DRACO = 100 tasks, all rubric criteria, 1× LLM judge pass "
            "(OpenRouter used Gemini ×3 — we use 1 pass)."
            if args.limit == 0
            else "Partial run (--limit>0)."
        ),
        "tasks": [
            {
                "id": r["id"],
                "score_pct": r["score_pct"],
                "answer_chars": r["answer_chars"],
                "latency_s": (r.get("gen") or {}).get("latency_s"),
            }
            for r in results
        ],
    }
    out_path = OUT / f"draco_zeus_{tag}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    full_path = OUT / f"draco_zeus_{tag}_full.json"
    full_path.write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    # also always write latest pointer
    (OUT / "draco_zeus_LATEST.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[draco] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
