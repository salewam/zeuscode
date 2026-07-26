# Bakeoff after quality pack (retries / live refs / mobile gate)

## Crew
- ok, `ui_author_critics_web`
- Author: gemini-3.1-pro (Opus preferred failed after retries — upstream still flaky)
- Live competitor refs via browser: abcp.ru, part-kom.ru, fitauto.ru
- Mobile must_fix + mobile_fix pass enabled in pipeline

## Solo Opus
- Failed again (upstream 500 on long HTML)

## Takeaway
Items 1/4/5 are live in code. Honest Opus-vs-crew bakeoff still blocked by Claude upstream.
