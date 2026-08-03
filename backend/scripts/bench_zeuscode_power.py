#!/usr/bin/env python3
"""Real ZeusCode power-mode benchmark.

Measures latency / pass-rate / branches / escalate / estimated ₽ across N runs.
Saves and compares baselines.

Examples:
  # Structural (no network): crew + escalate invariants
  python scripts/bench_zeuscode_power.py --structural

  # Live bench, 3 runs per case, save baseline
  python scripts/bench_zeuscode_power.py --live \\
      --base \"$ZEUS_PERF_BASE\" --key \"$ZEUS_PERF_KEY\" \\
      --runs 3 --save-baseline power_v1

  # Compare against saved baseline
  python scripts/bench_zeuscode_power.py --live \\
      --base \"$ZEUS_PERF_BASE\" --key \"$ZEUS_PERF_KEY\" \\
      --runs 3 --compare power_v1
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

CASES_PATH = BACKEND / "tests" / "bench" / "power_cases.json"
LADDER_PATH = BACKEND / "tests" / "bench" / "research_ladder.json"
BASELINE_DIR = BACKEND / "tests" / "bench" / "baselines"
REPORT_DIR = ROOT / "_bmad-output" / "implementation-artifacts" / "bench-power"

POWER_CREW = [
    "claude-opus-4-6",
    "gpt-5.4",
    "deepseek-v4-pro",
    "gemini-3.1-pro",
]


def _load_ladder() -> dict[str, Any]:
    return json.loads(LADDER_PATH.read_text(encoding="utf-8"))


def _canon_model(mid: str, aliases: dict[str, Any]) -> str | None:
    m = (mid or "").strip().lower()
    if not m:
        return None
    if m in aliases:
        a = aliases[m]
        return None if a is None else str(a).lower()
    return m


def _crew_set(models: list[str], aliases: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for m in models:
        c = _canon_model(m, aliases)
        if c:
            out.add(c)
    return out


def ladder_composition_peer(
    crew: list[str] | None = None,
) -> dict[str, Any]:
    """Where our panel sits on the research chart by model membership."""
    ladder = _load_ladder()
    aliases = ladder.get("aliases") or {}
    crew = list(crew or ladder.get("zeus_power_crew") or POWER_CREW)
    ours = _crew_set(crew, aliases)
    rungs = list(ladder.get("rungs") or [])
    scored: list[dict[str, Any]] = []
    for i, r in enumerate(rungs, start=1):
        theirs = _crew_set(list(r.get("models") or []), aliases)
        if not theirs:
            continue
        inter = ours & theirs
        union = ours | theirs
        jaccard = (len(inter) / len(union)) if union else 0.0
        # Prefer covering their core models (ignore our flash mini)
        cover = (len(inter) / len(theirs)) if theirs else 0.0
        scored.append(
            {
                "step": i,
                "id": r["id"],
                "label": r["label"],
                "kind": r.get("kind"),
                "research_score": r.get("score"),
                "jaccard": round(jaccard, 3),
                "cover": round(cover, 3),
                "overlap": sorted(inter),
                "missing_from_us": sorted(theirs - ours),
                "extra_in_us": sorted(ours - theirs),
            }
        )
    scored.sort(key=lambda x: (-x["cover"], -x["jaccard"], -float(x["research_score"] or 0)))
    best = scored[0] if scored else None
    # Nearest-above / nearest-below by research score among fusion peers with cover>=0.66
    fusion_peers = [s for s in scored if s.get("kind") == "fusion" and s["cover"] >= 0.66]
    peer_score = float((best or {}).get("research_score") or 0)
    return {
        "our_crew": crew,
        "our_crew_canonical": sorted(ours),
        "best_peer": best,
        "fusion_peers_cover66": fusion_peers[:5],
        "composition_step": (best or {}).get("step"),
        "composition_research_score": peer_score,
        "plain_ru": _plain_step_ru(best, crew),
        "all_rungs": [
            {
                "step": i,
                "label": r["label"],
                "score": r["score"],
                "kind": r["kind"],
            }
            for i, r in enumerate(rungs, start=1)
        ],
    }


def _plain_step_ru(best: dict[str, Any] | None, crew: list[str]) -> str:
    if not best:
        return "Не удалось сопоставить связку с графиком."
    return (
        f"По составу моделей твоя связка ближе всего к ступени "
        f"#{best['step']} «{best['label']}» (~{best['research_score']}% на их бенче). "
        f"Перекрытие core: {int(best['cover']*100)}%. "
        f"Отличия: у нас gpt-5.4 вместо gpt-5.5, плюс DeepSeek Pro как doer/mini."
    )


def ladder_measured_projection(report: dict[str, Any]) -> dict[str, Any]:
    """Project our live pass_rate onto 40–72% research axis (orientation only).

    Calibration: research fusion tops ~69, solos ~43–60.
    We map pass_rate 0→43 (floor flash solo), 1.0→68.5 (Opus+GPT+Gem peer).
    Then damp by timeout/empty rate and escalate.
    """
    ladder = _load_ladder()
    rungs = list(ladder.get("rungs") or [])
    floor = 43.0
    ceiling = 68.5  # R2 peer — honest target for our composition
    pr = float(report.get("pass_rate") or 0)
    runs = list(report.get("runs") or [])
    n = len(runs) or 1
    timed = sum(
        1
        for r in runs
        if r.get("error") == "timed out" or float(r.get("latency_s") or 0) >= 179
    )
    empty = sum(1 for r in runs if not r.get("answer_chars"))
    esc = float(report.get("escalate_rate") or 0)
    timeout_rate = timed / n
    empty_rate = empty / n

    raw = floor + pr * (ceiling - floor)
    # Penalties: timeouts & empties drag toward solo-floor
    raw -= 12.0 * timeout_rate
    raw -= 8.0 * empty_rate
    raw -= 3.0 * esc
    projected = max(floor, min(ceiling + 1.0, raw))

    # Which rung are we nearest to after projection?
    nearest = min(
        (
            {
                "step": i,
                "label": r["label"],
                "score": float(r["score"]),
                "delta": abs(float(r["score"]) - projected),
            }
            for i, r in enumerate(rungs, start=1)
        ),
        key=lambda x: x["delta"],
    )
    # Steps above floor solo flash
    step_from_bottom = sum(1 for r in rungs if float(r["score"]) <= projected)

    return {
        "pass_rate": pr,
        "timeout_rate": round(timeout_rate, 3),
        "empty_rate": round(empty_rate, 3),
        "escalate_rate": esc,
        "projected_research_score": round(projected, 2),
        "nearest_rung": nearest,
        "steps_from_bottom": step_from_bottom,
        "steps_total": len(rungs),
        "calibration": {
            "floor": floor,
            "ceiling": ceiling,
            "note": "Orientation only — not Artificial Analysis official score",
        },
        "plain_ru": (
            f"По нашему live-бенчу проекция ≈ {projected:.1f}% на шкале исследования "
            f"(рядом со ступенью #{nearest['step']} «{nearest['label']}» ~{nearest['score']}%). "
            f"Таймауты {timeout_rate:.0%}, пустые {empty_rate:.0%}."
        ),
    }


def build_ladder_report(
    *,
    live_report: dict[str, Any] | None = None,
    crew: list[str] | None = None,
) -> dict[str, Any]:
    comp = ladder_composition_peer(crew)
    measured = (
        ladder_measured_projection(live_report)
        if live_report and live_report.get("mode") == "live"
        else None
    )
    peer = comp.get("best_peer") or {}
    gap = None
    if measured and peer.get("research_score") is not None:
        gap = round(
            float(peer["research_score"])
            - float(measured["projected_research_score"]),
            2,
        )
    return {
        "mode": "ladder",
        "composition": comp,
        "measured": measured,
        "gap_to_composition_peer_pp": gap,
        "verdict_ru": _ladder_verdict(comp, measured, gap),
    }


def _ladder_verdict(
    comp: dict[str, Any],
    measured: dict[str, Any] | None,
    gap: float | None,
) -> str:
    peer = comp.get("best_peer") or {}
    lines = [
        comp.get("plain_ru") or "",
    ]
    if measured:
        lines.append(measured.get("plain_ru") or "")
        if gap is not None:
            if gap <= 2:
                lines.append(
                    f"По качеству почти на уровне состава (разрыв {gap} п.п.)."
                )
            elif gap <= 8:
                lines.append(
                    f"Состав топ-2/топ-3, но live пока ниже на {gap} п.п. — "
                    f"обычно latency/timeouts/leader на мелочи, не «слабые модели»."
                )
            else:
                lines.append(
                    f"Большой разрыв {gap} п.п.: связка по бумаге сильная, "
                    f"исполнение (таймауты/Opus 500/роутинг) тянет вниз."
                )
    else:
        lines.append("Live-отчёт не передан — только ступень по составу моделей.")
    return " ".join(x for x in lines if x)


def _load_suite() -> dict[str, Any]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def _percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    if len(ys) == 1:
        return round(ys[0], 3)
    k = (p / 100) * (len(ys) - 1)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return round(ys[lo], 3)
    w = k - lo
    return round(ys[lo] * (1 - w) + ys[hi] * w, 3)


def _prices() -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    try:
        from app.catalog import public_catalog

        for m in public_catalog():
            p = m.get("pricing") or {}
            out[str(m["id"])] = (
                float(p.get("input_per_1m") or 0),
                float(p.get("output_per_1m") or 0),
            )
    except Exception:  # noqa: BLE001
        pass
    return out


def _rub_from_usage(
    *,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    prices: dict[str, tuple[float, float]],
) -> float:
    inn, outt = prices.get(model_id, (0.0, 0.0))
    return (prompt_tokens / 1_000_000) * inn + (completion_tokens / 1_000_000) * outt


def _extract_answer(data: dict[str, Any]) -> str:
    ch = (data.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for p in c:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text") or ""))
            elif isinstance(p, str):
                parts.append(p)
        return "".join(parts)
    return str(c or "")


def _score_run(
    case: dict[str, Any],
    *,
    status: int,
    latency_s: float,
    answer: str,
    onestack: dict[str, Any],
    data: dict[str, Any],
    prices: dict[str, tuple[float, float]],
    forbid_models: list[str],
    full_crew: bool = False,
) -> dict[str, Any]:
    oracle = case.get("oracle") or {}
    branches = onestack.get("branches") or []
    if not isinstance(branches, list):
        branches = []
    routed_by = str(onestack.get("routed_by") or "")
    # Only models that actually ran (branches) — not role-table assignments
    models_seen: list[str] = []
    for b in branches:
        if isinstance(b, dict) and b.get("model_id"):
            models_seen.append(str(b["model_id"]))
    mbr = onestack.get("models_by_role") or {}
    if not isinstance(mbr, dict):
        mbr = {}

    pt = ct = 0
    usage = data.get("usage") or {}
    if isinstance(usage, dict):
        pt = int(usage.get("prompt_tokens") or 0)
        ct = int(usage.get("completion_tokens") or 0)
    rub = 0.0
    if branches:
        for b in branches:
            if not isinstance(b, dict):
                continue
            rub += _rub_from_usage(
                model_id=str(b.get("model_id") or ""),
                prompt_tokens=int(b.get("prompt_tokens") or 0),
                completion_tokens=int(b.get("completion_tokens") or 0),
                prices=prices,
            )
    elif pt or ct:
        leader = str(onestack.get("leader") or models_seen[0] if models_seen else "")
        rub = _rub_from_usage(
            model_id=leader,
            prompt_tokens=pt,
            completion_tokens=ct,
            prices=prices,
        )

    bill = data.get("onestack_billing") or onestack.get("billing") or {}
    if isinstance(bill, dict) and bill.get("charged_rub") is not None:
        try:
            rub = float(bill["charged_rub"])
        except (TypeError, ValueError):
            pass

    # FULL-crew blast: aspects inflate branch count; allow up to timeout budget
    max_lat = float(oracle.get("max_latency_s") or 1e9)
    max_br = int(oracle.get("max_branches") or 99)
    if full_crew:
        max_lat = max(max_lat, 300.0)
        max_br = max(max_br, 16)

    checks: dict[str, bool] = {
        "http_200": status == 200,
        "non_empty": (not oracle.get("non_empty")) or bool(answer.strip()),
        "min_chars": len(answer.strip()) >= int(oracle.get("min_answer_chars") or 0),
        "code_fence": (not oracle.get("expect_code_fence"))
        or bool(re.search(r"```", answer)),
        "latency": latency_s <= max_lat,
        "max_branches": len(branches) <= max_br or not branches,
        "forbid_escalate": (not oracle.get("forbid_escalate"))
        or ("escalate_stronger" not in routed_by and "escalate_full" not in routed_by),
        "forbid_models": not any(m in forbid_models for m in models_seen),
        "no_clarifier": "clarifier_" not in routed_by,
    }
    must_any = oracle.get("must_contain_any") or []
    if must_any:
        low = answer.lower()
        checks["must_contain"] = any(str(x).lower() in low for x in must_any)
    else:
        checks["must_contain"] = True

    real_models = sorted(
        {m for m in models_seen if m and not str(m).startswith("aspect:")}
    )

    return {
        "pass": all(checks.values()),
        "checks": checks,
        "latency_s": round(latency_s, 3),
        "http_status": status,
        "answer_chars": len(answer),
        "path": onestack.get("path") or onestack.get("policy_path"),
        "routed_by": routed_by,
        "pipeline": onestack.get("pipeline"),
        "leader": onestack.get("leader"),
        "branch_n": len(branches),
        "models_seen": sorted(set(models_seen)),
        "real_models": real_models,
        "models_by_role": mbr if isinstance(mbr, dict) else {},
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "rub": round(rub, 4),
        "escalate_from": onestack.get("escalate_from"),
    }


def run_structural() -> dict[str, Any]:
    from app.fusion.policy import cascade_escalate_action
    from app.fusion.roles import assign_role_model, resolve_stack

    stack = resolve_stack("power")
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
    checks = {
        "stack_eq_crew": stack == POWER_CREW,
        "no_gpt55": "gpt-5.5" not in stack,
        "architect_opus": role_map["architect"] == "claude-opus-4-6",
        "test_author_gpt54": role_map["test_author"] == "gpt-5.4",
        "doer_logic_ds": role_map["doer_logic"] == "deepseek-v4-pro",
        "doer_ui_gem": role_map["doer_ui"] == "gemini-3.1-pro",
        "mini_pro": role_map["mini_verifier"] == "deepseek-v4-pro",
        "no_cascade_ladder": esc.action == "keep",
    }
    return {
        "mode": "structural",
        "pass": all(checks.values()),
        "checks": checks,
        "stack": stack,
        "role_map": role_map,
        "cascade": {"action": esc.action, "routed_by": esc.routed_by},
    }


def _post_chat(
    *,
    base: str,
    key: str,
    prompt: str,
    timeout: float,
    full_crew: bool = False,
) -> tuple[int, dict[str, Any], float]:
    # full_crew: force FULL path with entire power-5 panel answering together
    if full_crew:
        body = {
            "model": "zeuscode",
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "models": list(POWER_CREW),
            "zeus": {
                "mode": "full",
                "thinking": False,
                "clarify": False,
                "models": list(POWER_CREW),
            },
        }
    else:
        body = {
            "model": "zeuscode",
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "zeus": {"mode": "power", "thinking": False, "clarify": False},
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
        return 0, {"error": str(e)}, round(time.perf_counter() - t0, 3)
    lat = round(time.perf_counter() - t0, 3)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"error": "bad_json", "raw": raw[:800]}
    if not isinstance(data, dict):
        data = {"error": "not_object"}
    return status, data, lat


def run_live(
    *,
    base: str,
    key: str,
    runs: int,
    timeout: float,
    case_ids: set[str] | None = None,
    full_crew: bool = False,
) -> dict[str, Any]:
    suite = _load_suite()
    cases = suite["cases"]
    if case_ids:
        cases = [c for c in cases if c["id"] in case_ids]
    gates = suite.get("gates") or {}
    forbid_models = list(gates.get("forbid_models") or [])
    prices = _prices()

    runs_out: list[dict[str, Any]] = []
    for case in cases:
        for i in range(1, runs + 1):
            print(
                f"[bench] {case['id']} run {i}/{runs}"
                f"{' FULL-CREW-5' if full_crew else ''} …",
                flush=True,
            )
            status, data, lat = _post_chat(
                base=base,
                key=key,
                prompt=str(case["prompt"]),
                timeout=timeout,
                full_crew=full_crew,
            )
            answer = _extract_answer(data) if status == 200 else ""
            os_meta = data.get("onestack") if isinstance(data.get("onestack"), dict) else {}
            scored = _score_run(
                case,
                status=status,
                latency_s=lat,
                answer=answer,
                onestack=os_meta,
                data=data,
                prices=prices,
                forbid_models=forbid_models,
                full_crew=full_crew,
            )
            runs_out.append(
                {
                    "case_id": case["id"],
                    "bucket": case.get("bucket"),
                    "run": i,
                    **scored,
                    "error": data.get("error") or data.get("detail"),
                }
            )

    summary = _summarize(
        suite_id=str(suite["suite_id"]) + ("_fullcrew" if full_crew else ""),
        runs=runs_out,
        gates=gates,
        n_runs=runs,
    )
    summary["full_crew"] = full_crew
    summary["power_crew"] = list(POWER_CREW)
    return summary


def _summarize(
    *,
    suite_id: str,
    runs: list[dict[str, Any]],
    gates: dict[str, Any],
    n_runs: int,
) -> dict[str, Any]:
    lats = [float(r["latency_s"]) for r in runs if r.get("latency_s") is not None]
    rubs = [float(r["rub"]) for r in runs]
    passes = [bool(r.get("pass")) for r in runs]
    escalate_hits = sum(
        1
        for r in runs
        if "escalate_stronger" in str(r.get("routed_by") or "")
        or "escalate_full" in str(r.get("routed_by") or "")
    )
    by_case: dict[str, list[dict[str, Any]]] = {}
    by_bucket: dict[str, list[dict[str, Any]]] = {}
    for r in runs:
        by_case.setdefault(str(r["case_id"]), []).append(r)
        by_bucket.setdefault(str(r.get("bucket") or "na"), []).append(r)

    case_summary = []
    for cid, rows in by_case.items():
        cl = [float(x["latency_s"]) for x in rows]
        case_summary.append(
            {
                "case_id": cid,
                "bucket": rows[0].get("bucket"),
                "pass_rate": round(sum(1 for x in rows if x.get("pass")) / len(rows), 3),
                "p50_latency_s": _percentile(cl, 50),
                "p95_latency_s": _percentile(cl, 95),
                "mean_rub": round(statistics.mean([float(x["rub"]) for x in rows]), 4),
                "mean_branches": round(
                    statistics.mean([float(x.get("branch_n") or 0) for x in rows]), 2
                ),
            }
        )

    bucket_summary = []
    for b, rows in by_bucket.items():
        bl = [float(x["latency_s"]) for x in rows]
        bucket_summary.append(
            {
                "bucket": b,
                "n": len(rows),
                "pass_rate": round(sum(1 for x in rows if x.get("pass")) / len(rows), 3),
                "p50_latency_s": _percentile(bl, 50),
                "p95_latency_s": _percentile(bl, 95),
                "mean_rub": round(statistics.mean([float(x["rub"]) for x in rows]), 4),
            }
        )

    pass_rate = (sum(1 for p in passes if p) / len(passes)) if passes else 0.0
    p95 = _percentile(lats, 95)
    escalate_rate = (escalate_hits / len(runs)) if runs else 0.0
    mean_rub = statistics.mean(rubs) if rubs else 0.0

    gate_checks = {
        "min_pass_rate": pass_rate >= float(gates.get("min_pass_rate") or 0),
        "max_p95_latency_s": (p95 or 0) <= float(gates.get("max_p95_latency_s") or 1e9),
        "max_escalate_rate": escalate_rate <= float(gates.get("max_escalate_rate") or 1),
        "max_mean_rub_per_case": mean_rub
        <= float(gates.get("max_mean_rub_per_case") or 1e9),
    }

    return {
        "mode": "live",
        "suite_id": suite_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_runs_per_case": n_runs,
        "n_total_runs": len(runs),
        "pass_rate": round(pass_rate, 3),
        "p50_latency_s": _percentile(lats, 50),
        "p95_latency_s": p95,
        "mean_rub": round(mean_rub, 4),
        "total_rub": round(sum(rubs), 4),
        "escalate_rate": round(escalate_rate, 3),
        "gate_checks": gate_checks,
        "pass": all(gate_checks.values()) and pass_rate > 0,
        "cases": case_summary,
        "buckets": bucket_summary,
        "runs": runs,
    }


def _save_baseline(name: str, report: dict[str, Any]) -> Path:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    # Store compact baseline (no full answer bodies)
    slim = {k: v for k, v in report.items() if k != "runs"}
    slim["runs_compact"] = [
        {
            "case_id": r["case_id"],
            "run": r["run"],
            "pass": r["pass"],
            "latency_s": r["latency_s"],
            "rub": r["rub"],
            "path": r.get("path"),
            "routed_by": r.get("routed_by"),
            "branch_n": r.get("branch_n"),
            "checks": r.get("checks"),
        }
        for r in report.get("runs") or []
    ]
    path = BASELINE_DIR / f"{name}.json"
    path.write_text(json.dumps(slim, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _compare(baseline_name: str, report: dict[str, Any]) -> dict[str, Any]:
    path = BASELINE_DIR / f"{baseline_name}.json"
    if not path.exists():
        return {"ok": False, "error": f"baseline missing: {path}"}
    base = json.loads(path.read_text(encoding="utf-8"))
    deltas = {
        "pass_rate_pp": round(
            float(report.get("pass_rate") or 0) - float(base.get("pass_rate") or 0), 3
        ),
        "p95_latency_s": round(
            float(report.get("p95_latency_s") or 0)
            - float(base.get("p95_latency_s") or 0),
            3,
        ),
        "mean_rub": round(
            float(report.get("mean_rub") or 0) - float(base.get("mean_rub") or 0), 4
        ),
        "escalate_rate_pp": round(
            float(report.get("escalate_rate") or 0)
            - float(base.get("escalate_rate") or 0),
            3,
        ),
    }
    # Regression: pass_rate drop > 5pp OR p95 +30% OR escalate up
    base_p95 = float(base.get("p95_latency_s") or 0) or 1.0
    ok = (
        deltas["pass_rate_pp"] >= -0.05
        and float(report.get("p95_latency_s") or 0) <= base_p95 * 1.30
        and deltas["escalate_rate_pp"] <= 0.05
    )
    return {
        "ok": ok,
        "baseline": baseline_name,
        "baseline_pass_rate": base.get("pass_rate"),
        "baseline_p95_latency_s": base.get("p95_latency_s"),
        "deltas": deltas,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="ZeusCode power real benchmark")
    ap.add_argument("--structural", action="store_true", help="Crew/role invariants only")
    ap.add_argument("--live", action="store_true", help="Hit /v1 with real models")
    ap.add_argument(
        "--ladder",
        action="store_true",
        help="Map crew + optional live report onto research fusion ladder",
    )
    ap.add_argument(
        "--from-report",
        default="",
        help="Live JSON report path for --ladder projection",
    )
    ap.add_argument(
        "--full-crew",
        action="store_true",
        help="Force FULL path: all 5 power models answer each case",
    )
    ap.add_argument("--base", default=os.environ.get("ZEUS_PERF_BASE", ""))
    ap.add_argument("--key", default=os.environ.get("ZEUS_PERF_KEY", ""))
    ap.add_argument("--runs", type=int, default=3, help="Repeats per case (live)")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--case", action="append", default=[], help="Filter case id (repeatable)")
    ap.add_argument("--save-baseline", default="", help="Save baseline name")
    ap.add_argument("--compare", default="", help="Compare to baseline name")
    ap.add_argument("--out", default="", help="Write full JSON report")
    args = ap.parse_args()

    if not args.live and not args.structural and not args.ladder:
        args.structural = True

    report: dict[str, Any]
    if args.ladder and not args.live:
        live = None
        if args.from_report:
            live = json.loads(Path(args.from_report).read_text(encoding="utf-8"))
        report = build_ladder_report(live_report=live)
    elif args.live:
        if not args.base or not args.key:
            print(
                "LIVE requires --base and --key (or ZEUS_PERF_BASE / ZEUS_PERF_KEY)",
                file=sys.stderr,
            )
            return 2
        ids = set(args.case) if args.case else None
        report = run_live(
            base=args.base,
            key=args.key,
            runs=max(1, args.runs),
            timeout=args.timeout,
            case_ids=ids,
            full_crew=bool(args.full_crew),
        )
        report["ladder"] = build_ladder_report(live_report=report)
        if args.save_baseline:
            p = _save_baseline(args.save_baseline, report)
            report["baseline_saved"] = str(p)
        if args.compare:
            report["compare"] = _compare(args.compare, report)
            if not report["compare"].get("ok"):
                report["pass"] = False
    else:
        report = run_structural()
        report["ladder"] = build_ladder_report()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    default_out = REPORT_DIR / f"bench_{report.get('mode')}_{stamp}.json"
    out_path = Path(args.out) if args.out else default_out
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Human summary
    if report.get("mode") == "ladder":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if report.get("mode") == "structural":
        print(
            json.dumps(
                {
                    "mode": "structural",
                    "pass": report.get("pass"),
                    "checks": report.get("checks"),
                    "role_map": report.get("role_map"),
                    "ladder": (report.get("ladder") or {}).get("verdict_ru"),
                    "report": str(out_path),
                    "note": "Structural only. For real bench: --live --base --key --runs 3",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        ladder = report.get("ladder") or {}
        summary = {
            "mode": "live",
            "pass": report.get("pass"),
            "pass_rate": report.get("pass_rate"),
            "p50_latency_s": report.get("p50_latency_s"),
            "p95_latency_s": report.get("p95_latency_s"),
            "mean_rub": report.get("mean_rub"),
            "total_rub": report.get("total_rub"),
            "escalate_rate": report.get("escalate_rate"),
            "gate_checks": report.get("gate_checks"),
            "cases": report.get("cases"),
            "ladder_step": (ladder.get("composition") or {}).get("composition_step"),
            "ladder_peer": ((ladder.get("composition") or {}).get("best_peer") or {}).get(
                "label"
            ),
            "ladder_projected": ((ladder.get("measured") or {}).get("projected_research_score")),
            "ladder_verdict_ru": ladder.get("verdict_ru"),
            "compare": report.get("compare"),
            "baseline_saved": report.get("baseline_saved"),
            "report": str(out_path),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
