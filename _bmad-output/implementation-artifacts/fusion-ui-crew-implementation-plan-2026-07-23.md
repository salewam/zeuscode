# План внедрения: Fusion UI Crew (Author + Critics + Web)

Дата: 2026-07-23  
Статус: фаза 1 — **задеплоено на prod**, bakeoff прошёл (см. ниже)

## Цель

Связка на сайтах/UI не хуже самой сильной модели, а лучше:  
**Author (max power-score) → 2 Critics с вебом → Author revise → Gate.**

## Фазы

### Фаза 1 — каркас ✅ код
| # | Артефакт | Статус |
|---|----------|--------|
| 1 | `backend/app/fusion/model_power.py` | ✅ |
| 2 | `backend/app/fusion/web_tools.py` (Tavily / DDG + fetch) | ✅ |
| 3 | `backend/app/fusion/ui_crew.py` | ✅ |
| 4 | Роутинг FULL в `_monolith.py` → `execute_ui_crew` | ✅ |
| 5 | Флаги в `config.py`: `FUSION_UI_CREW_ENABLED`, `WEB_RESEARCH_*`, `TAVILY_API_KEY` | ✅ |
| 6 | `backend/tests/test_fusion_ui_crew.py` (6 passed) | ✅ |
| 7 | Deploy + Motohaus bakeoff crew vs solo | ✅ деплой; bakeoff `ui-crew-20260723-124023` |
| 8 | Author failover по power ladder при upstream fail | ✅ |

**Как включается:** FULL + (`task_kind=ui|design` или HTML/«сайт»/landing в тексте) + `FUSION_UI_CREW_ENABLED=true`.

**Сигналы в ответе:** `onestack.routed_by` ∈ `ui_author_critics_web` | `ui_author_rollback` | `ui_author_only`; `onestack.ui_crew.{author,critics,web,critique_merged}`.

### Фаза 2 — DJARVIS browser (дешёвый режим) ✅
На Zeus уже был `browser-daemon` (`/run/browser-daemon/daemon.sock`).

| Правило дешевизны | Как |
|---|---|
| По умолчанию без браузера | DDG/Tavily → Jina/httpx |
| Браузер только escalate | если текст thin/пустой, ≤ `WEB_BROWSER_MAX_PAGES=1` |
| Команды | только `navigate` + `get-text` (без snapshot/screenshot) |
| Токены критикам | compress craft-сигналов, budget ~2800 символов на весь pack |
| Общий pack | один research на оба критика |

Файлы: `browser_client.py`, обновлённый `web_tools.py`.  
Smoke prod: `browser_used=0`, 2 refs через Jina, `prompt_chars≈2400`.

### Фаза 3 — калибровка
- Bakeoff МоторХаус crew vs solo Author
- Подкрутка power-score и рубрики craft
- Сохранять branch texts в usage для аудита

## Критерий готовности фазы 1 (прод)
- В `onestack`: `ui_crew.author`, `critics`, `routed_by=ui_author_critics_web|ui_author_rollback`
- Финал от Author, не Gemini rewrite
- `web.refs_used` непустой при живом вебе (или `web.degraded=true`)
- Gate откатывает битый revise

## Bakeoff 2026-07-23 12:40 (prod)

Артефакты: `_bmad-output/.../bakeoff-sto-2026-07-23/ui-crew-20260723-124023/`

| | Fusion UI Crew | Solo Opus |
|--|----------------|-----------|
| ok | ✅ | ❌ upstream 500 на длинном HTML |
| routed_by | `ui_author_critics_web` | — |
| author | `gemini-3.1-pro` (failover: Opus author упал 500) | — |
| critics | Opus + DeepSeek | — |
| web | DDG+Jina, 3 refs | — |
| size | ~34 KB HTML | — |
| live | https://zeuscode.ru/go/site-06ac/ | — |

Вывод: пайплайн Author→Critics→Revise на проде живой; финал пишет Author (не judge-rewrite). Сравнение «crew vs соло Opus» пока блокирует нестабильный Claude upstream на больших ответах — failover спасает crew.
