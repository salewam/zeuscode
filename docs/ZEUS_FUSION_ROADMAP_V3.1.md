# Zeus Fusion — единый план внедрения v3.1

**Статус:** канонический продукт-спек / roadmap  
**Продукт:** ZeusCode · `zeus/fusion`  
**Дата:** 2026-07-22  
**Версия:** 3.1 (v3 + addendum A17–A19, B13–B14, C11–C14, D8, E16–E18, E3b, F1)

---

## 0. Цель

Один `zeus/fusion` в любом клиенте (Cursor / VS Code / Continue / TG / сайт / CLI):

> сам понимает задачу → сам выбирает силу и путь → сам проверяет → сам собирает → честно биллит → прозрачно объясняет цену → учится на фидбеке.

**Не цель:** второй OpenRouter на 400 моделей, свой RAG по репо на сервере, tab-autocomplete.

**Позиционирование:** не marketplace доступа, а **coding compound brain** — лучшее соотношение сила / цена / надёжность для кода.

---

## 1. Что уже есть (не ломаем)

| # | Возможность |
|---|---|
| 1 | `zeus/fusion` + режимы `simple` / `power` / `custom` |
| 2 | Auto-роутинг **1 ↔ 3** (никогда auto-2) |
| 3 | Flash-микроклассификатор + regex + guardrails |
| 4 | `task_kind` → выбор «головы» (`pick_leader`) |
| 5 | Полный контекст голове; сателлитам — сжатый бриф |
| 6 | Judge-синтез на full |
| 7 | Thinking SSE + keepalive |
| 8 | `sanitize_messages` (анти-бloat Cursor) |
| 9 | Prefs: TG Mini App + кабинет + `users.fusion_*` |
| 10 | Publish HTML + Zeus badge → `zeuscode.ru/go/…` |
| 11 | Каталог моделей / upstream / биллинг аккаунта |
| 12 | Legacy aliases: `zeus/fusion-fast`, `zeus/fusion-full`, `zeus.mode=fast\|full` |

---

## 2. Целевой пайплайн

```text
Клиент отключился? → cancel всех веток (не жечь $)
Баланс/квота исчерпаны mid-flight? → soft-stop + частичный billing

Запрос
  → precedence: zeus.* запроса > prefs аккаунта > default
  → feature flags / shadow / canary cohort
  → sticky session + prefix/prompt cache hint
  → scrub secrets/PII (политика)
  → classify: фаза + сложность + effort + confidence
       (flash → regex fallback; роутер упал ≠ 500)
       (опц. позже: MoR vote cost/quality/latency)
  → overflow-safe context (middle-out / weak-summary)
  → long-context: голова с достаточным окном
  → путь + timeout/concurrency budget:
        FAST        → 1 голова (health + failover)
        CASCADE     → cheap → MINI-VERIFIER → escalate
        RACE        → speculative parallel (интерактив)
        FULL        → панель A/B/C (роли, diversity, latency-homogeneous)
                      → aspect/mini-verify + rank-then-fuse
                      → structured judge (≠ клон панели) → финал
                      → (редко) MoA layer-2 на hard
        DUAL        → architect → editor
        TOOL-FULL   → agent/outer сам просит панель (фаза 5)
  → upstream reasoning_effort / thinking по политике effort
  → стрим thinking + answer
  → onestack: кто / почему / токены / ₽ по веткам
  → честный billing (все ветки + verifier + judge + cascade)
  → лог + metrics + 👍👎 → Elo (позже E3b trained router)
  → eval/canary; rollback при регрессии
```

### Зафиксированные правила

1. **Early-exit** только через mini-verifier / aspect-verifiers — не «голова сама сказала, что она отличная».
2. **Не ×3** полный Cursor-контекст — голова full, сателлиты brief.
3. **Tools** не стрипать только после Фазы 5 (до этого — chat path).
4. **Не** становиться marketplace на 400 моделей.
5. Публичный id **`zeus/fusion` стабилен**; фичи за flags / `zeus.*`.
6. Выкат: **shadow → 10% → 50% → 100% → rollback**.
7. Nested fusion (фаза 5) — **recursion guard**, один уровень.

---

## 3. Полный бэклог

### A. Роутинг и пути

| ID | Фича | Суть |
|---|---|---|
| A1 | Фазы кодинга | `chat / ui / plan / implement / debug / test / review / docs` |
| A2 | Cascade | cheap → verify → escalate в full |
| A3 | Speculative-race | parallel cheap+strong; первый годный; cancel второго |
| A4 | Sticky session | липкая голова/фаза/стек (`session_id`, TTL) |
| A5 | Effort | `low / med / high` отдельно от выбора модели |
| A6 | Cost↔quality слайдер | `0–10` в prefs / `zeus.tradeoff` |
| A7 | Presets | `coding-fast` / `coding-budget` / `coding-high` |
| A8 | Phase→model table | primary + fallback внутри simple/power |
| A9 | Plan≠Implement | сильный plan, дешевле execute (opusplan-паттерн) |
| A10 | Long-context routing | голова с нужным context window |
| A11 | Tool-triggered full | agent/outer может запросить панель |
| A12 | Prompt adaptation | короткий rewrite промпта под выбранную модель |
| A13 | Weak-model side tasks | саммари истории / мелочь не головой |
| A14 | Graceful degrade | classify/verify упал → regex/default, не 500 |
| A15 | Shadow mode | лог «куда бы пошли», ответ старый |
| A16 | Diversity panel | не 3 клона одного семейства |
| A17 | MoR (Mixture-of-Routers) | роутеры cost / quality / latency голосуют за путь |
| A18 | Upstream reasoning_effort | прокидывать thinking/effort в модели (Claude/Gemini и т.п.) |
| A19 | Context overflow strategy | middle-out / weak-summary; не молча резать критичное |

### B. Панель, судья, проверка

| ID | Фича | Суть |
|---|---|---|
| B1 | Роли A/B/C | ответ / альтернатива / критика |
| B2 | Structured judge | consensus / contradictions / unique / blind spots → финал |
| B3 | Mini-verifier | `{good_enough, confidence, reason}` для cascade и early-exit |
| B4 | Early-exit | только verifier ok **или** ветки почти клоны (similarity) |
| B5 | Rank-then-fuse | слабые ветки отбросить до синтеза |
| B6 | Умный бриф сателлитам | цель + ошибка/код + ограничения |
| B7 | Latency-homogeneous panel | никто один не гейтит весь fan-out |
| B8 | MoA layer-2 | второй refine только на hard |
| B9 | Architect→Editor dual-pass | думаем → потом аккуратные правки |
| B10 | Temperature / max_tokens по ролям | A свободнее, C строже |
| B11 | Optional web на панели | research / landing (flag) |
| B12 | Execution-aware verify | traceback/тесты → verify-ветка |
| B13 | Aspect-verifiers | отдельные проверки: корректность / полнота / security; голос |
| B14 | Judge anti-bias | судья ≠ простая копия сильнейшей панели; отдельная модель/промпт |

### C. Надёжность и runtime

| ID | Фича | Суть |
|---|---|---|
| C1 | Health-gate головы | жива + p50 latency; иначе #2 |
| C2 | Provider/model failover | цепочка fallback на ветке |
| C3 | Cancel on disconnect | клиент ушёл → стоп всех задач |
| C4 | Global timeout budget | лимит на весь fusion-запрос |
| C5 | Concurrency caps | защита от шторма 3×N |
| C6 | Retry / backoff | 429 / 5xx по веткам |
| C7 | Disaster path | все ветки мертвы → ясная ошибка + last-resort single |
| C8 | Feature flags / canary | 10% → 50% → 100% |
| C9 | Streaming | thinking сразу; финал стримом |
| C10 | Keepalive | усилить под длинный full |
| C11 | Prefix / prompt cache | sticky + cache-aware к upstream (agent loops) |
| C12 | Recursion guard | nested fusion max depth = 1 |
| C13 | Per-user rate limits | RPM/TPM; fair use |
| C14 | Dead-model sync | каталог: выкидывать/скипать upstream-dead (как codex-500) |

### D. Деньги, данные, безопасность

| ID | Фича | Суть |
|---|---|---|
| D1 | Честный billing по веткам | A/B/C + verifier + judge + cascade attempts |
| D2 | Частичный billing при фейле | не терять учёт середины |
| D3 | Маржа на verifier/cascade | заложена в экономику |
| D4 | Прозрачный чек | onestack + UI: кто / почему / токены / ₽ |
| D5 | Secret / PII scrub | ключи, токены, ПДн до upstream |
| D6 | Политика логов | TTL, opt-out хранения промптов на ключе |
| D7 | Anti skills-bloat | запрет ×3 skills dump; жёсткий sanitize |
| D8 | Soft-stop mid-panel | нулевой баланс / квота → остановить оставшиеся ветки, отдать лучшее что есть + частичный billing |

### E. Обучение, качество, продукт

| ID | Фича | Суть |
|---|---|---|
| E1 | Логи роутинга | path, phase, leader, source, latency, tokens, $ |
| E2 | Фидбек 👍👎 / regen | TG + кабинет |
| E3 | Elo / win-rate | `фаза × модель` → подкрутка головы |
| E3b | Trained router (опц.) | RouteLLM/BERT/MF на своих preference-логах после накопления данных |
| E4 | Eval suite | 50–100 промптов; PR + ночной прогон |
| E5 | Observability | trace_id, % escalate, verifier false-OK, p95, $/1k |
| E6 | Алерты | spike $, spike escalate, verifier always-OK, error rate, dead models |
| E7 | Дашборд | % fast/cascade/full/race, цена, p95, cancel savings |
| E8 | TG / кабинет UX | effort, слайдер, presets, 👎, статус пути, история ₽ |
| E9 | Kill-switch | «всегда 1 модель» |
| E10 | Custom-panel rules | роли / dual-pass / verify для custom 2–3 |
| E11 | Доки клиентов | Cursor / VS Code / Continue / raw API |
| E12 | API stability | `zeus/fusion` + контракт `onestack` / `zeus.*` |
| E13 | Multimodal pass-through | images/скрины багов |
| E14 | Agent / tools path | не стрипать `tool_calls`; роут шагов агента |
| E15 | Publish сохранить | HTML go-links + badge |
| E16 | Precedence rules | request `zeus.*` > account prefs > product default |
| E17 | Legacy aliases | `fusion-fast` / `fusion-full` / forced modes не ломать |
| E18 | Load test + incident runbook | ёмкость, алерты, кто что делает при outage |

### F. Опционально позже (не блокирует ядро)

| ID | Фича | Суть |
|---|---|---|
| F1 | BYOK | свой upstream key, политика данных |
| F2 | Semantic cache (только chat/docs) | строгий namespace; **никогда** default на codegen |
| F3 | Team / org seats | общие prefs, лимиты, счета |
| F4 | Budget panel + frontier judge preset | явный OR-style `general-budget` аналог |

---

## 4. Фазы внедрения

### Фаза 0 — Фундамент (нед. 1–2)

Без этого нельзя безопасно катить умные пути.

| Must | ID |
|---|---|
| Логи роутинга | E1 |
| Честный + частичный billing, прозрачный чек | D1, D2, D4 |
| Soft-stop при нуле баланса (каркас) | D8 |
| Health-gate | C1 |
| Timeout + concurrency budget | C4, C5 |
| Feature flags / canary | C8 |
| Shadow mode | A15 |
| Eval baseline | E4 |
| Metrics + trace_id | E5 |
| Streaming thinking / keepalive | C9, C10 |
| Anti-bloat контроль | D7 |
| Precedence + legacy aliases зафиксировать | E16, E17 |
| Dead-model sync (минимум) | C14 |

**Done:** каждый запрос оставляет след и $; мёртвая голова не роняет всё; baseline eval; флаги; aliases живы.

---

### Фаза 1 — Умный путь запроса (нед. 3–4)

| Must | ID |
|---|---|
| Фазы | A1 |
| Cascade | A2 |
| Mini-verifier | B3 |
| Sticky session | A4 |
| Effort | A5 |
| Long-context (база) | A10 |
| Overflow strategy (v1) | A19 |
| Graceful degrade | A14 |
| Failover головы | C2 |
| Cancel on disconnect | C3 |
| Retry/backoff | C6 |
| Disaster path | C7 |
| Rate limits (база) | C13 |
| Маржа verifier | D3 |
| Secret scrub (keys/bearer) | D5 |
| Prefs: effort + kill-switch | E8, E9 |
| Speculative-race (borderline) | A3 |
| Prefix/prompt cache hint (v1) | C11 |
| reasoning_effort passthrough (v1) | A18 |

**Done:** cascade+verify в проде (canary→100%); sticky; disconnect не жжёт $; classify/verify ≠ 500.

---

### Фаза 2 — Сильная панель (нед. 5–6)

| Must | ID |
|---|---|
| Роли A/B/C | B1 |
| Structured judge | B2 |
| Judge anti-bias | B14 |
| Early-exit через verifier / clone-detect | B4 |
| Rank-then-fuse | B5 |
| Aspect-verifiers (v1: 2–3 аспекта) | B13 |
| Умный бриф | B6 |
| Latency-homogeneous preset | B7 |
| Temp/max_tokens по ролям | B10 |
| Diversity panel | A16 |
| Custom-panel rules | E10 |
| Стрим финала | C9 |
| Prompt adaptation v1 | A12 |
| MoR v1 (простые веса) | A17 |

**Done:** full сильнее single на architecture/review; early-exit режет $ без роста 👎.

---

### Фаза 3 — Coding moat (нед. 7–9)

| Must | ID |
|---|---|
| Architect→Editor | B9 |
| Phase→model table | A8 |
| Plan≠Implement | A9 |
| Cost↔quality слайдер | A6 |
| Presets coding-* | A7 |
| MoA layer-2 на hard | B8 |
| Optional web flag | B11 |
| Weak-model side tasks | A13 |
| Полный UX (слайдер, presets, путь, ₽) | E8 |
| Доки клиентов | E11 |
| F4 budget+frontier preset (если готов) | F4 |

**Done:** сложный implement = dual-pass; слайдер/preset дают ощутимый эффект.

---

### Фаза 4 — Обучение, доверие, ops (∥ к 2–3, ~2 нед.)

| Must | ID |
|---|---|
| Фидбек 👍👎 / regen | E2 |
| Elo | E3 |
| Алерты | E6 |
| Дашборд | E7 |
| Политика логов | D6 |
| API contract freeze | E12 |
| Publish regression guard | E15 |
| Load test + runbook | E18 |
| Ночной/PR eval | E4 |
| Dead-model алерты | C14, E6 |

**Done:** голова крутится данными; алерты живые; инцидент не «все разбежались».

---

### Фаза 5 — Agent-ready (после стабильного chat)

| Must | ID |
|---|---|
| Tools path | E14 |
| Tool-triggered full | A11 |
| Recursion guard | C12 |
| Execution-aware verify | B12 |
| Multimodal images | E13 |
| Роут шагов агента | classify / edit / test разными моделями |
| Cache-aware sticky для agent loops | C11 усиление |

**Done:** Zeus usable в Agent mode, не только Chat.

---

### Фаза 6 — Опциональный потолок (по данным)

| When | ID |
|---|---|
| Накопили preference-логи | E3b trained router |
| Enterprise спрос | F1 BYOK, F3 teams |
| Доказанный safe chat-повтор | F2 semantic cache (docs/chat only) |

---

## 5. Сознательно НЕ делаем

| Не делаем | Почему |
|---|---|
| Каталог 400 моделей | не moat |
| Semantic cache на codegen | риск неверного кода |
| Загрузка репо на Zeus | контекст уже в IDE |
| Early-exit без verifier | враньё «отлично» |
| Всегда 3+ модели на всё | дорого |
| Tab-autocomplete роутер | другой продукт |
| Полный клон Claude Code в фазе 1 | слишком рано |
| Semantic cache без namespace | опасно кросс-юзерам |

---

## 6. Метрики успеха

| Метрика | Цель |
|---|---|
| % stop на FAST / CASCADE | ↑ без роста 👎 |
| % 👎 / regen на hard | ↓ |
| p95 latency лёгких | ↓ |
| $/1k запросов | ↓ при том же или лучшем eval |
| Eval suite | no regress |
| Пустые ответы при down головы | → ~0 |
| Verifier always-OK | алерт |
| Cancel savings | измеримо > 0 |
| Billing drift (факт vs сумма веток) | → 0 |
| Soft-stop корректность | нет «съели $ после нуля» |
| Dead models в панели | → 0 в ready |

---

## 7. Где меняем инфру

| Зона | Ответственность |
|---|---|
| `backend/app/fusion.py` | пути, verify, роли, judge, sticky, dual-pass, MoR, budgets |
| `backend/app/upstream.py` | health, cancel, retry, stream, temp, reasoning_effort, cache hints |
| `backend/app/routers/chat.py` | session_id, effort, flags, precedence, disconnect, onestack |
| `backend/app/models.py` / `db.py` | logs, elo, feedback, flags, rate limits |
| billing routers | D1–D3, D8 |
| TG Mini App + `me` / `tg_miniapp` | E8–E9, слайдер, presets, 👎 |
| `sanitize_messages` / skills | D7, E13 |
| `kie_sync` / catalog | C14 |
| `scripts/eval_fusion*` + CI | E4 |
| docs / runbook | E11, E18 |
| `publish.py` | E15 |
| alerts / dashboard | E5–E7 |

---

## 8. Порядок выката

```text
shadow → canary 10% → 50% → 100% → rollback по eval / алертам
```

Обязательный canary для: cascade, early-exit, dual-pass, structured judge, MoR, aspect-verifiers, agent tools path.

---

## 9. Сводка ID (полный индекс)

| Группа | ID |
|---|---|
| Роутинг | **A1–A19** |
| Панель / verify | **B1–B14** |
| Runtime | **C1–C14** |
| Деньги / безопасность | **D1–D8** |
| Продукт / обучение | **E1–E18** (+ **E3b**) |
| Later | **F1–F4** |

**Фазы:** `0 → 1 → 2 → 3 → 4(∥) → 5 → 6(опц.)`

---

## 10. Definition of Done для всего продукта

Zeus Fusion v3.1 считается реализованным, когда:

1. Любой клиент работает через один `zeus/fusion`.
2. Пути FAST / CASCADE / RACE / FULL / DUAL живут под флагами и метриками.
3. Early-exit и cascade опираются на verifier, не на самооценку головы.
4. Биллинг сходится с суммой веток; disconnect и soft-stop не жгут лишнее.
5. Eval + Elo + алерты крутятся; регрессии ловятся до 100% раскатки.
6. Agent/tools — отдельный стабильный path, не ломающий chat.
7. Publish, legacy aliases и anti-bloat не деградировали.

---

## 11. Следующий конкретный шаг

**Начать Фазу 0 в коде:**

1. Таблица/лог `fusion_route_events` (E1)  
2. Расширить `onestack` cost breakdown (D4)  
3. Health-gate + failover каркас (C1, C2)  
4. Feature flag wrapper + shadow (C8, A15)  
5. Скрипт `scripts/eval_fusion_suite.py` + 30 seed-кейсов (E4)  

---

*Конец документа v3.1 — канон для планирования и внедрения.*
