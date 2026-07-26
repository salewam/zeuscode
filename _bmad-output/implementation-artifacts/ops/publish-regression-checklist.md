# Publish regression checklist (FR26)

Run when a release touches Judge, system prompts, Brief, sanitize, or prompt adaptation.

1. `python backend/scripts/check_publish_regression.py` → must PASS.
2. Manual: publish sample HTML via `POST /api/publish` → URL under `zeuscode.ru/go/…` (or local `/go/`).
3. Confirm page contains `zeus-badge` / «Сделано на ZeusCode».
4. Fail release if gate or manual check fails.

Gate is also enforced in-process when `FUSION_PUBLISH_REGRESSION_GATE=true` (default).
