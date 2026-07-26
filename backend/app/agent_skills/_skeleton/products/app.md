# Product Form — app (wired)

Статус: **на тестах** (intent + brief + gates wired).

| Поле | Значение |
|------|----------|
| id | app |
| title_ru | Веб-приложение |
| одним предложением | Несколько экранов + данные + одно ключевое действие |
| MVP | 1) 2–3 экрана 2) ключевое действие e2e 3) данные сохраняются |
| зоны | design, frontend, backend, tests |
| pipeline | intake → design → (fe∥be) → tests → synth → verify → review |
| verify | browser_smoke · api/local · pytest · wrong_product_shape · missing_state |

## Wired в коде

- `skills.py` — INTENT `app`, infer, app-shell refs/examples
- `brief_expand.py` — niche/fallback app brief (`product_id=app`)
- `evidence.py` — `_app_quality_findings`
- refs: `frontend/references/app-shell.md`
- examples: `good_app.md`, `bad_app_as_landing.md`

## Ещё на тестах

- [ ] live прогон в Studio
- [ ] 3 кейса verify зелёные
- [ ] reviewer калибровка
- [ ] можно юзерам
