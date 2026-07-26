# Fusion Path — Incident Runbook (NFR7 / PRD §6.4)

Use before and during canary→100% Path rollout.

## Rollback (first 5 minutes)

1. Set env `FUSION_KILL_SWITCH=true` (or account `fusion_kill_switch=1`) → serving Path clamps to **FAST**.
2. Set `FUSION_CANARY_PCT=0` and/or `FUSION_SHADOW_MODE=true` to stop candidate serving while keeping shadow logs.
3. Redeploy previous known-good baseline (`FUSION_BASELINE_ID` pinned).
4. Confirm `fusion.observe` / Onestack: escalate% and `routed_by` return to baseline shape.

## Verifier always-OK

**Signal:** Mini-Verifier / Aspect reports OK for long streak (`verifier_ok_streak` ≥ 50) while quality/thumbs-down worsen.

**Actions:**
- Freeze canary (`FUSION_CANARY_PCT=0`).
- Diff verifier prompts vs last Eval pass.
- Check Soft-Stop / cancel paths are not short-circuiting verifier.

## Billing drift

**Signal:** `fusion.billing_drift` or UsageLog totals ≠ `FusionResult.branches` billable states.

**Actions:**
- Freeze Path canary.
- Reconcile `completed` / `partial_stream` / `cancelled_*` against charges.
- Do **not** invent Path from token heuristics (AD-8 / AD-14).

## Dead Leader / dead models

**Signal:** repeated upstream failures for a Leader id (`fusion.dead_model`).

**Actions:**
- Mark model unhealthy; sticky may rotate on next `pick_leader`.
- Optional: clear sticky rows for affected sessions (`fusion_sticky_sessions`).
- If panel-wide outage → Kill-Switch FAST until catalog healthy.

## Shadow compare mismatch storm

**Signal:** high `fusion.shadow mismatch=true` rate vs `baseline_id`.

**Actions:**
- Keep serving on baseline (shadow already does).
- Block canary increase until Eval suite + per-bucket bar pass (AD-13).

## Contacts / artifacts

- Eval harness: `backend/tests/eval/harness.py`
- Publish gate: `backend/scripts/check_publish_regression.py`
- Load test stub: `ops/load-test-fusion.md`
- Alert stubs: `app.fusion.metrics.ALERT_STUBS`
