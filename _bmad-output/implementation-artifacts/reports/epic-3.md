# Epic 3 report — Strong Multi-Model Path (Agent C)

**Date:** 2026-07-22  
**Stories:** 3.1–3.5  
**Status:** implemented (unit-tested, mocked upstream)

## Delivered

| Story | What shipped |
|---|---|
| **3.1 RACE** | `panel.execute_race` — parallel cheap+strong; first годный (Mini pass or degrade→first-complete strong); loser cancelled with honest billable state; both-fail terminal `race_escalate_full` / `race_soft_stop` / `race_disaster` |
| **3.2 FULL** | `panel.execute_full` — Leader full context + satellite Brief (goal/last_assistant/errors); diversity gate (3× same `model_family` forbidden unless ops exception); Aspects **before** τ; near-duplicate early-exit (`τ=0.92` token Jaccard); no Leader self-score exit |
| **3.3 Judge** | `judge.rank_then_fuse_plan` + `run_structured_judge` — top-K (`K=2` if Δ≥0.15 else top-3); structured consensus/contradictions/unique/blind_spots; 1 success ⇒ no Judge; anti-bias oracle (contradictions ∧ overlap≥0.95) |
| **3.4 Soft-Stop** | `soft_stop_pick` order: verifier confidence → first-complete → Leader-partial; cancel mid-flight via `cancel_event`; billable states on branches |
| **3.5 Prompt adapt** | `adapt_prompt_for_family` — system/hint layer only; user requirements untouched; separate from Soft-Stop |

## Files changed

- `backend/app/fusion/panel.py` — RACE/FULL executors, Brief, Soft-Stop, prompt adapt, path override helper, completion bridge
- `backend/app/fusion/judge.py` — rank-then-fuse + Structured Judge + anti-bias
- `backend/app/fusion/verify.py` — `# EPIC3-ASPECT` block (Aspects v1 + near-duplicate); Mini-Verifier from Epic 2 preserved
- `backend/app/fusion/_monolith.py` — thin `# EPIC3-HOOK` when Path is `RACE`/`FULL` (`zeus.path` or policy/clf `path`)
- `backend/app/fusion/__init__.py` — append re-exports `panel`, `judge`
- `backend/tests/test_fusion_panel.py` — new
- `backend/tests/test_fusion_judge.py` — new
- `_bmad-output/implementation-artifacts/reports/epic-3.md` — this report

## Integration notes

- Hook activates on Path override (`zeus.path` ∈ {RACE,FULL}) or Epic 2 clf/policy `path`.
- Legacy `fast|full` stack routing unchanged when Path override absent.
- Mini-Verifier: calls `verify.mini_verify` / `run_mini_verifier` if present; else degrade path (FR-9).
- Chat billing remains owned by Epic 1 / routers — panel emits `BranchUsage` + optional `_fusion_result` only.
- `fusion/*` ↛ `routers.*` (verified).

## Pytest

```bash
PYTHONPATH=backend .venv/bin/python -m pytest \
  backend/tests/test_fusion_panel.py \
  backend/tests/test_fusion_judge.py \
  backend/tests/test_fusion_routing.py -q
```

**Result (this agent):** `44 passed` (panel + judge + routing).

Also spot-checked with policy/result/scrub when present — keep green before merge if parallel agents moved those files.
