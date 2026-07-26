# KIE Rate Limit Evidence — 2026-07-22

## Setup
- Zeus prod: `zeuscode.ru` → upstream `https://api.kie.ai`
- Burst: **40 parallel** `POST /v1/chat/completions` with `gemini-2.5-flash`
- Result: **35× HTTP 200**, **5× HTTP 429**

## KIE response body (verbatim)
```json
{"code": 429, "msg": "Your call frequency is too high. Please try again later.", "data": null}
```

## Zeus journal lines (tag `UPSTREAM_RATE_LIMIT`)
See `kie-rate-limit-journal.txt`.

Example:
```
UPSTREAM_RATE_LIMIT status=429 url=https://api.kie.ai/gemini-2.5-flash/v1/chat/completions ts=1784721380 body={"code": 429, "msg": "Your call frequency is too high. Please try again later.", "data": null}
```

## Ask for KIE support
Please raise account rate limits. Current published limit (~20 new generations / 10s) is insufficient for Zeus Fusion compound routing (multi-model panel / Cursor Agent bursts). Credits available; failures are frequency 429s, not balance.

## Reproduce on server
```bash
journalctl -u zeuscode --since '1 hour ago' | grep UPSTREAM_RATE_LIMIT
```
