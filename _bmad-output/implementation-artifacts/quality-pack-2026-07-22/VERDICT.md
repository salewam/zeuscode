# Zeus Fusion — Quality Evidence Pack Verdict

**Date:** 2026-07-22  
**Pack:** `_bmad-output/implementation-artifacts/quality-pack-2026-07-22/`

## 1. Вердикт одной фразой

**READY_WITH_GAPS**

Сервис на проде отвечает и маршрутизирует `zeus/fusion` по Path; до «готово катить canary→100% / считать compound brain доказанным» не хватает live eval, стабильного Kill-Switch и теней на реальном флаге.

## 2. Что реально работает для пользователя

- Прод `zeuscode.ru` health + `zeus/fusion` → ответы 200.
- Chitchat → **FAST**; code/UI/arch/review → **CASCADE** с escalate; `effort=high` дошёл до **FULL**.
- Sticky session: 3 хода, Leader стабильно `gemini-3.1-pro` (Path при этом может эскалировать — правильно).
- Onestack на non-stream: `path`, `policy_path`, `leader`, `routed_by`, `trace_id`, `fusion_result`.
- Publish regression gate: PASS.
- Fusion unit suite: **149 passed**.
- Rate-limit от KIE теперь видно в journal (`UPSTREAM_RATE_LIMIT`) — можно тащить в саппорт.

## 3. Что собрано, но не доказано на живом трафике

- Offline Eval N=50: suite ok, но **path pass_rate 70%** (oracle soft / offline predict).
- Shadow mode: unit PASS; **на проде флаг не включали** → live Shadow NOT_PROVEN.
- Soft-Stop / cancel billing: только abort SSE симуляция.
- Mini/Aspects quality: эскалации есть, качество verify — NOT_PROVEN.
- Local `smoke_fusion_stack.py`: **BLOCKED** — `DEEPSEEK_API_KEY not configured` на локальном run (прод ходит через KIE adapters).
- Live Eval runner N≥20 на реальных моделях: **не реализован как отдельный harness** (offline only).

## 4. Дыры P0 / P1 / P2

### P0
1. **Kill-Switch live FAIL** — `502 Fusion fast: нет ответа (deepseek-v4-flash: cancelled)` при `kill_switch=true`.
2. **KIE frequency cap** — compound/Agent bursts → 429; без очереди/backoff на старты generation сервис «ломается» под нагрузкой Cursor Agent.

### P1
3. Offline eval path_match слабый (architecture/review/sticky buckets).
4. Stream ответы без стабильного Onestack в SSE (метаданные часто null в парсере pack).
5. Shadow/canary не прогнаны на prod flag.
6. `credits_consumed` / billing transparency в pack часто null — дожать Bill→клиент поля.

### P2
7. Local smoke script не использует prod-ready panel (ждёт DEEPSEEK_API_KEY).
8. Cancel mid-stream proof неполный (нет UsageLog assert).
9. Frozen `bucket_pass_rates` пустой — canary bars только documented.

## 5. Сравнение с архитектурой (% закрытия MVP FR)

| Срез | Оценка |
|---|---|
| Код эпиков 1–4 / AD spine | ~**85%** собрано |
| Автотесты fusion | **149/149** |
| Live user-facing proof (12 кейсов) | **11/12 ok** |
| MVP FR live-proven | ~**55%** |
| MVP FR implemented (code+tests) | ~**70–75%** |
| Canary→100% readiness | **NOT READY** |

Deferred by design: FR6 / FR11 / FR27 — не считаются дырами MVP.

## 6. Топ-5 следующих действий (качество сервиса)

1. **Починить Kill-Switch FAST path** (не cancelled flash → 502); добавить live gate-тест.
2. **Upstream scheduler**: семафор ≤~15–18 gen/10s + retry/backoff на KIE 429.
3. **Live Eval ≥20** на реальных моделях; заморозить `bucket_pass_rates`.
4. **Включить Shadow** на малом % и смотреть candidate vs serving + 👎.
5. **Дожать SSE Onestack** (path/leader/trace в финальном chunk) + Soft-Stop billing assert.

## 7. Что докинуть руками владельцу (для ещё более жёсткой оценки)

- 10 своих реальных Cursor-диалогов с 👍/👎.
- Подтверждение, какой Zeus API key в Cursor (не KIE).
- Опционально: апрув на включение `FUSION_SHADOW_MODE` на проде на 24ч.
- Письмо/тикет в KIE с `kie-rate-limit-evidence.md` + journal.

---

## A — Автоматика (кратко)

| Step | Result |
|---|---|
| pytest fusion* | **149 passed** → `artifacts/pytest-fusion.txt` |
| offline eval | n=50, pass_rate=70%, ok=True (documented bars) → `artifacts/eval-*` |
| publish regression | **PASS** |
| smoke_fusion_stack | **BLOCKED** local: DEEPSEEK_API_KEY missing |
| invariants | sticky/shadow/kill/budgets/no-routers → `artifacts/invariants-check.json` |

## B — Live (кратко)

| Metric | Value |
|---|---|
| Cases | 12 |
| ok / fail | 11 / 1 |
| Sticky leaders | gemini-3.1-pro × 3 |
| Kill-switch | FAIL 502 |
| Shadow live | NOT_PROVEN (flag off) |

Details: `live/summary.json`, per-case `live/*.json`.

## TL;DR

**Прод живой и в основном отвечает умно (FAST/CASCADE/FULL + sticky).**  
Не ready без оговорок: Kill-Switch падает, KIE rate limit душит Agent, live eval/shadow не доказаны.  
Вердикт: **READY_WITH_GAPS**.
