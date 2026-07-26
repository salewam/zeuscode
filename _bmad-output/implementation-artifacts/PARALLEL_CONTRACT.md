# Parallel epic agents — file ownership (2026-07-22)

Story **1.1 DONE** on disk: `backend/app/fusion/` package + `_monolith.py` + stubs + `types.py`.

## Shared (read-only unless noted)

| Path | Rule |
|---|---|
| `backend/app/fusion/types.py` | **Frozen** — FusionResult / BranchUsage / PathName. Do not reshape without sync. |
| `backend/app/fusion/__init__.py` | Append re-exports only; do not reorder monolith move. |
| `_bmad-output/planning-artifacts/epics.md` | Requirements source |
| `…/ARCHITECTURE-SPINE.md` | AD-1…AD-18 |

## Ownership

### Agent A — Epic 1 (Stories 1.2–1.4)
- `backend/app/fusion/_monolith.py` (handoff fields, scrub-once call site, Brief helper)
- `backend/app/routers/chat.py` (consume FusionResult / billable states / Onestack path fields)
- `backend/tests/test_fusion_result*.py`, `test_fusion_scrub*.py`, `test_fusion_onestack*.py`
- May add `backend/app/fusion/brief.py` if needed

### Agent B — Epic 2 (Stories 2.1–2.5)
- `backend/app/fusion/policy.py` (full)
- `backend/app/fusion/verify.py` (Mini-Verifier only; leave Aspect stubs for Epic 3)
- `backend/tests/test_fusion_policy*.py`, `backend/tests/fixtures/fusion_policy/**`
- Hook into `_monolith` **only** via thin calls at classify/resolve points; mark with `# EPIC2-HOOK`

### Agent C — Epic 3 (Stories 3.1–3.5)
- `backend/app/fusion/panel.py` (RACE/FULL/Soft-Stop/cancel)
- `backend/app/fusion/judge.py`
- Aspect parts of `verify.py` under `# EPIC3-ASPECT` sections only
- `backend/tests/test_fusion_panel*.py`, `test_fusion_judge*.py`

### Agent D — Epic 4 (Stories 4.1–4.9)
- `backend/app/fusion/session.py`, `metrics.py`
- Prefs: `routers/me.py`, `tg_miniapp.py`, `telegram_bot.py` prefs surfaces (Effort/Kill-Switch) — **coordinate** if touching same lines as A
- DB: sticky session table in `models.py` / `db.py` migrations-style init
- Eval/ops: `backend/tests/eval/**`, `docs/` or `_bmad-output/implementation-artifacts/ops/**`
- Observability helpers in metrics; do not break chat billing

## Hard rules

1. `fusion/*` never imports `routers.*`
2. Do not delete `_monolith` wholesale
3. Keep `from app.fusion import run_fusion|iter_fusion|…` working
4. Prefer additive Onestack fields
5. When done: list files changed + pytest commands run in a short REPORT.md under `_bmad-output/implementation-artifacts/reports/epic-N.md`
