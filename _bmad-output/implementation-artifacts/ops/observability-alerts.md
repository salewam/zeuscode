# Fusion observability alerts (NFR3 / Story 4.8)

## Per-request

- Every fusion request gets `trace_id` (`app.fusion.metrics.new_trace_id` / `ensure_trace_id`).
- Emit via `observe_request(path, phase, routed_by, escalate_from, trace_id)`.
- Shadow: `log_shadow_compare(candidate_path, serving_path, baseline_id, …)`.

## Counters (in-process MVP)

`snapshot_metrics()` exposes:

- Path rates by Phase (`path_by_phase`)
- escalate%
- `routed_by` histogram
- verifier always-OK streak, billing drift, dead models, shadow mismatch

Wire to Onestack exporters later; stubs live in `ALERT_STUBS`.

## Min alerts

| Alert | Threshold | Severity | Action |
|-------|-----------|----------|--------|
| verifier_always_ok | streak ≥ 50 | page | rollback canary; check verifier wiring |
| billing_drift | ≥ 1 | page | freeze canary; reconcile FusionResult vs UsageLog |
| dead_models | ≥ 3 events | ticket | unhealthy Leader; sticky rotate |

See also `incident-runbook-fusion.md`.
