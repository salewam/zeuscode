# UI Crew bakeoff — 2026-07-23

## Result
- **Fusion UI Crew OK** — `routed_by=ui_author_critics_web`
- Author: **gemini-3.1-pro** (Opus author attempt failed upstream 500 → failover)
- Critics: claude-opus-4-8 + deepseek-v4-pro
- Web: duckduckgo_html + jina, 3 refs
- Live: https://zeuscode.ru/go/site-06ac/
- Solo Opus: failed (upstream 500 on long HTML)

## Takeaway
Crew path is live on prod. Strongest-author intent held via power scores + failover; final HTML comes from Author revise, not Gemini judge mash.
