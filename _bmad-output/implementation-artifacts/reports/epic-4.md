# Epic 4 Report — Sticky Prefs & Safe Ship (Agent D)

**Date:** 2026-07-22  
**Stories:** 4.1–4.9  
**Contract:** `_bmad-output/implementation-artifacts/PARALLEL_CONTRACT.md`

## Status

Implemented at pragmatic MVP depth. Sticky store, prefs, shadow/canary flags, eval harness (N≥50), runtime budgets in Settings, feedback ingest (no Elo), publish regression gate, observability helpers, canary-exit ops stubs.

## Story map

| Story | Deliverable |
|-------|-------------|
| 4.1 Sticky | `FusionStickySession` table + `fusion/session.py` CRUD; key from `X-Zeus-Session-Id` / `zeus.session_id`; Path never sticky |
| 4.2 Prefs | `users.fusion_effort`, `users.fusion_kill_switch`; surfaces: `/me/fusion`, `/tg/fusion`, bot `/effort` `/kill`; applied via `apply_user_fusion_pref` EPIC4-HOOK |
| 4.3 Shadow/canary | Settings flags + `resolve_serving_path` / `log_shadow_compare` / `baseline_id` (`lexicon_v1` embedded) |
| 4.4 Eval | `backend/tests/eval/` — 50 fixtures, `eval_baseline.json`, offline pass-oracle harness |
| 4.5 Runtime | Settings fields + `RuntimeBudgets` / `structured_disaster_error` |
| 4.6 Feedback | `FusionFeedbackEvent` + `POST /me|/tg|/v1/fusion/feedback` (`elo_writeback: false`) |
| 4.7 Publish gate | `fusion/publish_gate.py` hooked in publish router + `scripts/check_publish_regression.py` |
| 4.8 Observability | `trace_id`, `observe_request`, counters, `ALERT_STUBS` + ops alert doc |
| 4.9 Canary ops | load-test stub + incident runbook under `implementation-artifacts/ops/` |

## Files changed / added

### Fusion (owned)
- `backend/app/fusion/session.py`
- `backend/app/fusion/metrics.py`
- `backend/app/fusion/publish_gate.py`
- `backend/app/fusion/__init__.py` (additive re-exports)
- `backend/app/fusion/_monolith.py` (thin `# EPIC4-HOOK` in `apply_user_fusion_pref` only)

### DB / config
- `backend/app/models.py` — sticky + feedback tables; user effort/kill columns
- `backend/app/db.py` — additive SQLite column ensures
- `backend/app/config.py` — shadow/canary/kill/budgets/publish-gate settings

### Prefs / API surfaces
- `backend/app/routers/me.py`
- `backend/app/routers/tg_miniapp.py`
- `backend/app/routers/auth.py` (read-only effort/kill in `/me`)
- `backend/app/routers/fusion_feedback.py` **(new)**
- `backend/app/routers/publish.py` (gate hook)
- `backend/app/main.py` (include feedback router)
- `backend/app/telegram_bot.py` (`/effort`, `/kill`, pref summary)

### Eval / scripts / ops
- `backend/tests/eval/**` (generator, harness, baseline, 50 fixtures)
- `backend/tests/test_fusion_epic4.py`
- `backend/scripts/check_publish_regression.py`
- `backend/scripts/load_test_fusion_stub.py`
- `_bmad-output/implementation-artifacts/ops/incident-runbook-fusion.md`
- `_bmad-output/implementation-artifacts/ops/load-test-fusion.md`
- `_bmad-output/implementation-artifacts/ops/publish-regression-checklist.md`
- `_bmad-output/implementation-artifacts/ops/observability-alerts.md`

## Chat.py

**Not edited** (Agent A). Sticky/shadow/observe are callable helpers for chat to wire later:
- `extract_session_id` / `get_sticky` / `put_sticky` / `sticky_leader_hint`
- `resolve_serving_path` / `log_shadow_compare` / `observe_request` / `ensure_trace_id`

Kill-Switch + Effort already apply when chat calls existing `apply_user_fusion_pref`.

## Hard rules

- `fusion/*` does not import `routers.*` (verified)
- Product modes simple/power/custom unchanged when kill off
- No Elo writeback on feedback

## Pytest

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_fusion_routing.py tests/test_fusion_epic4.py -q
# 40 passed
```

Also ran:
- `python scripts/check_publish_regression.py` → PASS
- `python scripts/load_test_fusion_stub.py --profile all --dry-run` → OK
- `python tests/eval/generate_fixtures.py` → 50 fixtures

## Follow-ups (not blockers for Epic 4 MVP)

- Chat/policy wire sticky read at start + `put_sticky` at request end with actual Leader
- Chat call `observe_request` / shadow compare on each fusion completion
- Live load-test against upstream + signed results in ops doc
- Onestack export of in-process metrics counters
