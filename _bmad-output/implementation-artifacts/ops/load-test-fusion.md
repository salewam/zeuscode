# Fusion Path — Load Test Stub (NFR7 / Story 4.9)

Record signed results here before canary 100%. Script stub below is intentionally dry-run safe.

## Profiles

| Profile | Path | Concurrency | Global timeout | Notes |
|---------|------|-------------|----------------|-------|
| L-FAST | FAST | 20 | `FUSION_GLOBAL_TIMEOUT_S` | chitchat / trivial UI |
| L-CASCADE | CASCADE | 10 | same | mid complexity |
| L-RACE | RACE | `FUSION_RACE_CONCURRENCY` | same | hard compare prompts |
| L-FULL | FULL | `FUSION_PANEL_CONCURRENCY` | same | landing / architecture |

## Stub command

```bash
# From repo root — dry-run (no upstream flood)
python backend/scripts/load_test_fusion_stub.py --profile all --dry-run

# Live (ops only; requires UPSTREAM_API_KEY + test key)
python backend/scripts/load_test_fusion_stub.py --profile FAST --requests 50 --concurrency 10
```

## Sign-off template

- Date:
- Baseline id:
- Canary pct before test:
- Results attached: `yes/no`
- p95 latency FAST/CASCADE/RACE/FULL:
- Error rate:
- Billing drift observed: `yes/no`
- Approver:
