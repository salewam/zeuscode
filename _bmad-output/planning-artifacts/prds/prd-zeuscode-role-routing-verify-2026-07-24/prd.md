---
title: ZeusCode — Role Routing + Verify/Escalate
status: final
created: 2026-07-24
updated: 2026-07-25
decisions_locked: 2026-07-24
finalized: 2026-07-24
decisions_amended: 2026-07-25
decisions_amended_connect_docs: 2026-07-25
decisions_amended_owner_vp3: 2026-07-25
decisions_amended_pipeline_v1: 2026-07-25
decisions_amended_fallback_curator: 2026-07-25
decisions_amended_vp5_locks: 2026-07-25
product: ZeusCode
public_model: zeuscode
source_tz: docs/TZ_ZEUS_ROLE_ROUTING_VERIFY.md
client_connect_research: docs/CLIENT_API_CONNECT_RESEARCH.md
pipeline_canon: addendum.md §M
parent_prd: _bmad-output/planning-artifacts/prds/prd-zeuscode-fusion-2026-07-22/prd.md
stakes: launch-increment
working_mode: fast-path
validation_grade_pre_decisions: Poor
product_invariant: no-new-buttons-anywhere
---

# PRD: Zeus Role Routing + Verify/Escalate

*Инкремент поверх Zeus Fusion. Источник идеи: `docs/TZ_ZEUS_ROLE_ROUTING_VERIFY.md`. Канон пайплайна: `addendum.md` §J–N.*

## 0. Document Purpose

Этот PRD для PM, архитектора и разработки: фиксирует **что** должен уметь продукт в инкременте Role Routing + Verify/Escalate. Технический «как» — в `addendum.md`. Базовый Fusion PRD остаётся родительским; этот документ не заменяет Spine AD-1…AD-18, а расширяет compound brain (публичный id **`zeuscode`**, legacy alias `zeus/fusion`) и Studio.

**Инварианты владельца (2026-07-25):**
1. **Нигде нет новых кнопок** — нет ручек Path/каскад/гонка/«усилить» сверх трёх режимов TG «Модели».
2. **Публичный model id = `zeuscode`** везде в narrative и клиентах.
3. **Дорогой multi-role конвейер — не default**; только large + второй сигнал (Pipeline v1).
4. **Custom / режимы:** юзер сам выбирает пресет платформы (simple/power) **или** свой Набор ≤3 — набор не подменяем.
5. **Куратор стека** = модель с max `power_score` в выбранном стеке; если нет ≥950 → полный Pipeline v1 не стартует, куратор ведёт `fallback_single` (решение A, 2026-07-25).
6. **VP5 locks (2026-07-25):** power doer может быть топ (opus); куратор в fallback = один полный ответ без отдельного Brief-шага; RED→fix один круг, затем Escalate≤2 global; merge = file-aware, конфликт → сильная; Log Analyst только если DeepSeek (или log-capable) есть в выбранном стеке — иначе skip.
7. **FR-16** (живой прогон клиентов) — отдельно, не gate.

Глоссарий обязателен: FRs используют термины §3 дословно.

## 1. Vision

ZeusCode — один ключ и один model id (**`zeuscode`**). Система сама понимает масштаб задачи, ставит нейронки на роли по `power_score`, проверяет результат и при нужде усиливает стек — без Combo Studio.

Снаружи: ключ + `zeuscode` в клиенте, режим в Telegram «Модели». **Новых кнопок нет.**

Внутри два режима стоимости:
- **Small (default):** 1–2 Doer + Mini-Verifier; DeepSeek Log Analyst только при traceback.
- **Large (редко), есть ≥950:** Pipeline v1 — Architect Brief → Test Author → mid Doers → один RED→fix → merge → DeepSeek по логам.
- **Large, нет ≥950:** куратор = самая сильная из выбранных юзером (пресет или Набор) ведёт одна (`fallback_single`) — набор не расширяем.

На hot path Gate = Log Analyst (JSON) + Mini-Verifier (+ контрактные тесты, если Layer B применим). Скриптовый Test Executor — Studio/workspace.

Гипотеза ×4 — `[ASSUMPTION]`, не exit criterion MVP.

## 2. Target User

### 2.1 Jobs To Be Done

- Писать/чинить код через один Zeus-ключ, не выбирая модель вручную.
- Мелочь не жжёт топ-стек; большая фича поднимает роли умно и не разоряет.
- Не бояться «тихо сломалось» — логи + проверки ловят RED.
- UX проще Omni; маржа живая.

### 2.2 Non-Users (v1)

- Ручной Combo Studio; human-approve на каждый completion; «прокси на 400 моделей».

### 2.3 Key User Journeys

**UJ-1. Артём чинит ImportError (small + logs).**
- Режим power; в контексте traceback.
- Router → `size=small`; **полный Pipeline v1 не стартует**.
- Mid Doer правит → **DeepSeek Log Analyst** → JSON → Mini-Verifier → Gate.
- Edge: битый JSON логов → RED → escalate (≤2 global), не тихий GREEN.
- Realizes FR-1, FR-3, FR-5…FR-8, FR-18.

**UJ-2. Марина собирает лендинг (large + 2nd signal).**
- «Сделай лендинг для СТО» → large + lexicon.
- **Pipeline v1:** Architect (≥950) Brief ≤3 куска → Test Author (≥950) контрактные тесты → doers параллель (без чужого кода) → один test-check RED→fix → **file-aware merge** (сильная при конфликте, 4Б) → DeepSeek только если модель log в стеке и есть ошибка (5Б).
- Нет кнопки «запустить панель». Onestack: roles, models_by_role, gate, pipeline=v1.
- Edge: «поменяй цвет» → small, не Pipeline v1.
- Realizes FR-9, FR-12, FR-13, FR-18.

**UJ-3. Денис настраивает в TG, кодит в клиенте.**
- Prefs: simple/power/custom → Base URL + key + **`zeuscode`** по гайду FR-17.
- В пикере нет Zeus Simple/Power/Custom. Кнопок Path нет.
- Realizes FR-4, FR-15, FR-17.

## 3. Glossary

- **Role** — функция: `router`, `architect`, `test_author`, `doer_ui`, `doer_logic`, `log_analyst`, `mini_verifier`, `judge_fix`, …
- **Role→Model Table** — `task_kind→role`, затем `role×mode→model` (+ score gates).
- **Router** — `size`, `stack`, `task_kind`, `confidence`, `roles[]`.
- **Size** — `small` | `large`.
- **task_kind** — `light` | `ui` | `tests` | `review` | `architecture` | `code` | `general`.
- **Architect** — Role ≥950: пишет **Brief** (куски, API/файлы, acceptance); на merge только при конфликте.
- **Brief (Architecture)** — общий контракт для doers: ≤3 куска, имена, acceptance one-liners. Doers видят Brief, не чужой код.
- **Test Author** — Role ≥950 (`TEST_AUTHOR_MIN`): короткие **контрактные** тесты на кусок; один цикл проверки.
- **Doer** — `doer_logic` / `doer_ui`; пишет код куска (в power preset может быть топ/opus — 1Б; в Pipeline v1 куски предпочтительно mid).
- **Log Analyst** — **DeepSeek**: traceback → `{critical, summary, fix_hint, confidence}` → Gate / escalate. Не менеджер процесса.
- **Test Executor** — скрипт allowlist (не LLM).
- **Mini-Verifier** — дешёвый `good_enough` + `confidence`.
- **Gate** — GREEN/RED по applicable critical signals.
- **Escalate / Soft-Stop** — усиление ≤2 global; затем лучший partial + явный RED.
- **Pipeline v1** — канон large-path при наличии ≥950 (addendum M). Default на small **запрещён**.
- **Куратор (curator)** — модель с max `power_score` в стеке, который выбрал юзер (simple/power/custom). Курирует задачу; при отсутствии ≥950 ведёт `fallback_single`.
- **power_score** — сила модели из `fusion/model_power.py`.
- **TEST_AUTHOR_MIN** — порог (default **950**) для полного Pipeline v1 (Architect / Test Author / conflict-merge).
- **Path** — внутренний `FAST|CASCADE|RACE|FULL`; юзер не выбирает.
- **Hot path / Studio path / Client surface / Prefs surface** — как ранее.
- **Onestack** — мета: roles, models, gate, pipeline, ₽.

## 4. Features

### 4.1 Role→Model Routing

**Description:** Классификация + назначение моделей по таблице и score. Prefs в TG; в IDE без Combo. Small — минимум Doers; large+2nd — Pipeline v1. Realizes UJ-1…3.

#### FR-1: Классификация Size и task_kind

**Consequences:**
- Выход: `size`, `stack`, `task_kind`, `confidence`, `roles[]`.
- `confidence < 0.6` → `size=large` как ярлык риска; **Pipeline v1 / Decompose только со вторым сигналом** (architecture lexicon / multi-file / landing-с-нуля / явный heavy). Иначе single-Doer + verify (анти cost-bomb).
- Router fail → fallback внутри режима, не 500.
- Chitchat / trivial UI без ошибки → small.
- Эвристики large: architecture/migrate/multi-file/landing; `context_chars > 4000` на рабочем запросе.

#### FR-2: Двухступенчатая Role→Model Table + score gates

**Consequences:**
1. `task_kind → default_doer_role` (+ verify/planner по триггеру).
2. `role × product_mode → primary/fallback` из стека TG; затем **score gate** (addendum J): Architect/Test Author/conflict-merge только если есть модель ≥ `TEST_AUTHOR_MIN` в стеке.
- UI: power `doer_ui` = gemini-3.1-pro (fb opus); simple = haiku primary.
- **Power doer_logic primary = opus-4-8** (решение 1Б): топ **может** быть обычным Doer в пресете power; cost-инвариант «топ только arch/tests» **не** применяется к power preset doers. В Pipeline v1 mid-doers по-прежнему предпочтительны для параллельных кусков, но primary таблицы power остаётся opus.
- Unhealthy → fallback.
- Onestack: `role_table=v1`, `models_by_role`, `product_mode`, `pipeline` ∈ {`small`,`v1`,`fallback_single`}.
- Custom: только модели юзера; не автодобавляем. **Куратор** = max `power_score` в наборе/пресете. Нет ≥950 → Pipeline v1 off → `fallback_single` (FR-18.8).

#### FR-3: Лимит Doers на small

**Consequences:**
- Doer-LLM ≤ 2 на small; `log_analyst` + `mini_verifier` вне cap.
- «Поменяй цвет» без traceback → нет Planner / Pipeline v1.

#### FR-4: Продуктовые режимы TG — единственный UX

| id | UI | Стек |
|----|-----|------|
| `simple` | Пользовательский | deepseek-v4-flash · gemini-3-pro · claude-haiku-4-5 |
| `power` | Продвинутый | claude-opus-4-8 · deepseek-v4-pro · gemini-3.1-pro |
| `custom` | Набор | ≤3 выбранных юзером |

**Consequences:**
- Публичный id = **`zeuscode`**; legacy aliases резолвятся; в пикере нет `zeuscode-simple|power|custom`.
- **Кнопок Path/каскад/гонка/усилить нет** (addendum K).
- simple — без Pipeline v1; power/custom — Pipeline v1 только large+2nd.
- **custom:** не подменяем набор.
- Kill-switch → FAST, без Decompose/Pipeline v1.
- Sticky не определяет Path.

### 4.2 Verify Gate + Log Analyst (DeepSeek)

**Description:** Gate не доверяет self-score Doer. DeepSeek разбирает логи по триггеру; Mini-Verifier — hot path. Realizes UJ-1.

#### FR-5: Log Analyst = DeepSeek JSON-контракт

**Consequences:**
- Вызов **только** если (a) в выбранном стеке есть модель для роли `log_analyst` (simple/power = DeepSeek; custom = только если DeepSeek/log-capable id есть среди ≤3) **и** (b) есть traceback / Exception / error-хвост / RED+runtime (addendum N).  
- **Решение 5Б:** в Наборе **без** DeepSeek → Log Analyst **skip** (не подставляем чужую модель). Gate тогда без `log_report` (N/A).
- Модель при наличии: DeepSeek v4-flash (simple) / v4-pro (power); в custom — выбранный юзером DeepSeek-id если есть.
- JSON: `{critical: bool, summary, fix_hint, confidence}`; битый / нет `critical` → RED.
- Вход = brief (логи + goal + файлы), не весь репо.
- Получатели: **Gate** (`critical`→RED); **judge_fix** (`fix_hint` в escalate); опц. одна строка юзеру.
- Не менеджерит Doers, не пишет тесты, не переписывает Brief.
- Branch `role=log_analyst` в FusionResult.

#### FR-6: Единый Gate

**Consequences:**
- Critical: traceback / `log_report.critical` / Mini-Verifier fail / parse degrade.
- `tests_failed` — только если executor/Layer B check запущен; иначе N/A.
- `build_failed` — только Studio если probe; hot всегда N/A.
- `lint_failed` — не critical v1.
- Mini passed ≡ `good_enough ∧ confidence ≥ τ` (τ=0.8).
- GREEN = все applicable critical зелёные; self-score Doer не форсит GREEN.

#### FR-7: Escalate ≤2 global + Soft-Stop

**Consequences:**
- `max_escalate=2` **на весь запрос** (в т.ч. multi-doer).
- **Порядок (решение 3А):** (1) один цикл Test Author RED→fix→recheck **не** тратит escalate-бюджет; (2) если после этого Gate всё ещё RED → Escalate/`judge_fix` до 2 раз; (3) исчерпание → Soft-Stop. Escalate не заменяет и не удваивает test-fix цикл.
- `judge_fix` = max `power_score` в стеке режима.
- Soft-Stop: HTTP 200, непустое тело = max power_score (tie→latest); короткая строка «проверка не пройдена»; Onestack `gate=RED`, `soft_stop=true`, …
- `fix_hint` Log Analyst → escalate prompt (если Log был).
- Бесконечный цикл запрещён.

#### FR-8: Mini-Verifier

**Consequences:**
- Hot path без executor: GREEN требует Mini passed.
- Degrade Mini → RED.

### 4.3 Tests + Studio + Onboarding docs

#### FR-9: Test layers A/B + score gate

**Consequences:**
- **Layer A:** rule-based allowlist существующих тестов (script executor).
- **Layer B (Test Author):** только Pipeline v1 (large+2nd) **и** модель ≥950 в стеке; пишет короткие контрактные тесты на кусок Brief; &lt;950 не назначаются.
- Нет ≥950 в стеке → Layer B skipped; Gate = A + Mini + Log(если FR-5 доступен).
- small / hot без workspace → executor + Layer B skipped.
- lint не RED alone.

#### FR-10: Test Executor = script

**Consequences:** exit≠0 → `tests_failed` когда запущен; вне allowlist запрещено; hot без workspace → skipped.

#### FR-11: Studio Gate

**Consequences:** падающий pytest в Studio → RED → Escalate если бюджет есть.

#### FR-16: Multi-client e2e — DEFERRED

`[NON-GOAL for MVP]` — отдельный прогон командой. Список клиентов в addendum G.

#### FR-17: TG connect docs = research

Канон: Base `https://zeuscode.ru/v1` · key `zeus_…` · model **`zeuscode`** · режим в TG.  
Исключения: Claude без `/v1`; Aider/OpenHands `openai/zeuscode`; OpenCode `zeuscode/zeuscode`; Cursor → Cline/Kilo caveat.  
Источник: `docs/CLIENT_API_CONNECT_RESEARCH.md`. Нет Simple/Power/Custom в пикерах. FR-17 ≠ e2e (FR-16).

### 4.4 Pipeline v1 — Large test-first (MVP)

**Description:** Практичный недорогой конвейер на large. Канон addendum M. Realizes UJ-2.

#### FR-18: Pipeline v1 — обязательный канон large

**Consequences (testable):**
1. **Триггер:** только `size=large` + второй сигнал + mode ∈ {power, custom}. Иначе pipeline запрещён.
2. **Architect (≥950):** Brief с `components[]` ≤ **3**; поля `{id, role, goal, acceptance_one_liner, files_hint?}`. Общий контракт API/файлов обязателен.
3. **Test Author (≥950):** контрактные тесты **на кусок**; не гигантский suite.
4. **Doers (mid 800–920):** параллель; вход = Brief + свой кусок + свои тесты; **нет** чужого кода doers.
5. **Один** цикл: Test Author check → RED→fix только RED-кусков → recheck (решение 3А; escalate после — см. FR-7). Второго test-менеджерского круга нет.
6. **Merge (решение 4Б):** file-aware сборка артефактов по Brief (пути/патчи, не prose-concat). Конфликт файла / сломанный стык API → один вызов сильной (≥950 если есть, иначе куратор).
7. **Log Analyst:** по FR-5; в custom без DeepSeek — skip (5Б).
8. **Нет модели ≥950 (решение A + 2А):** Pipeline v1 **не стартует**. Куратор = max `power_score` выбранного стека; `pipeline=fallback_single`: куратор **сразу пишет полный ответ** (без отдельного Brief/Architect-шага) → Mini-Verifier → Log только если доступен по FR-5 → Escalate≤2 при RED. Mid-параллель запрещена. Модели не докидываем.
9. Бюджет вызовов-ориентир: small 2–4; large Pipeline v1 ~6–8; fallback_single ~2–4; потолок large+логи+конфликт ~8–9. Default 8–12-call поток — **defect**.
10. Onestack: `pipeline=v1` | `small` | `fallback_single`; поле `curator_model` = id куратора.

#### FR-12: Аварийный контракт Planner / Pipeline

**Consequences:**
- Авария Architect (timeout / invalid JSON / 0 components) → `pipeline=fallback_single`: куратор (max power_score стека) + Mini + Log(по триггеру) + Escalate≤2.
- Один Doer упал → keep ok; escalate только failed из остатка global бюджета.
- Всё RED после escalate → Soft-Stop FR-7.
- simple: Pipeline v1 нет.

#### FR-13: Параллель независимых Doers

**Consequences:** независимые куски без ожидания друг друга; concurrency AD-12; overlap start в trace.

### 4.5 Transparency + Prefs

#### FR-14: Onestack fields

`task_kind`, `size`, `role_table`, `roles[]`, `models_by_role`, `gate`, `escalate_count`, `gate_reasons`, `soft_stop`, `pipeline`, `curator_model`.  
TG v1 не обязан показывать roles после каждого запроса; обязан prefs до IDE.

#### FR-15: Honest billing

Каждая LLM-Role = FusionResult branch; `cancelled_no_tokens` не тарифицируется; Path в Onestack = final serving path.

## 5. Non-Goals (Explicit)

- Marketplace / Combo Studio UI / human-approve на каждый completion.
- Новые UX-кнопки Path/каскад/гонка/усилить.
- Полный test-first pipeline как default на mid/«сложную фразу».
- Автодобавление сильных моделей в custom набор.
- Mid-параллель на large без куратора / без ≥950 (вместо решения A).
- Prose-concat merge как канон (заменён на file-aware, 4Б).
- Подстановка DeepSeek в custom, если юзер его не выбрал (5Б).
- RACE как целевой serving Role Routing v1.
- Log Analyst как процесс-менеджер Doers.
- FR-16 e2e 18 клиентов как gate этого MVP.
- Elo writeback; A6 failover; CryptoBot; server RAG; Path→«9 этапов».

## 6. MVP Scope

### 6.1 In Scope

- TG modes only + **нет новых кнопок** (FR-4).
- Role Table + score gates (FR-1…3).
- DeepSeek Log Analyst + Gate + Escalate≤2 + Soft-Stop (FR-5…8).
- **Pipeline v1** (FR-18) + аварии (FR-12/13).
- Test layers A/B + Studio executor (FR-9…11).
- `zeuscode` + FR-17 connect docs.
- Spine regression AD-5/7/8/14/15.

### 6.2 Out of Scope for MVP

- FR-16 живой прогон клиентов.
- Новые продуктовые Path-ручки; Combo UI; lint-as-critical; RACE-first large.

## 7. Success Metrics

**Primary**
- **SM-1:** small без Escalate (GREEN first) ≥ 70% на light/ui trivia. → FR-3, FR-6, FR-18 trigger.
- **SM-2:** traceback → Log Analyst влияет на Gate = 100% фикстур. → FR-5.
- **SM-3:** 0 infinite-escalate за 14d prod. → FR-7.

**Secondary**
- **SM-4:** median ₽ light ≤ baseline FAST+flash +15%.
- **SM-5:** Studio pytest fail → Escalate или Soft-Stop 100% e2e.
- **SM-6:** large landing eval: Pipeline v1 с Brief≤3 + финал GREEN или Soft-Stop непустой ≥ 80%; доля large-запросов с `pipeline=v1` без 2nd signal = **0** на eval. → FR-18.
- **SM-7 (deferred):** FR-16.
- **SM-8:** гайды ZC_PLATFORM_ORDER = FR-17 канон, без simple/power/custom ids.
- **SM-9:** на small eval p95 число LLM-вызовов ≤ 4 (исключая forced alias). → cost canon.

**Counter-metrics**
- **SM-C1:** не максимизировать Roles/запрос.
- **SM-C2:** не резать Router latency ценой ложных GREEN.

## 8. Cross-Cutting NFRs

- **NFR-1:** Router ≤ 2.5s.
- **NFR-2:** Log Analyst ≤ ~400 tokens out; brief in.
- **NFR-3:** small p95 ≤ FAST+30%.
- **NFR-4:** scrub секретов (AD-17).
- **NFR-5:** kill-switch → FAST, no Pipeline v1.
- **NFR-6:** Test Executor allowlist only.
- **NFR-7:** все LLM-вызовы в FusionResult.
- **NFR-8:** Pipeline v1 не стартует без large+2nd (hard).
- **NFR-9:** нет новых UI-кнопок Path/mode beyond TG three.

## 9. Constraints and Guardrails

- Safety: allowlist executor.
- Cost: Mini cheap; Log только если модель в стеке (5Б); custom не докидываем модели. В **power preset** opus **может** быть doer (1Б). В Pipeline v1 параллельные куски — предпочтительно mid; Architect/Test Author/conflict-merge — ≥950 когда есть.
- Privacy: brief без секретов.
- Product: нет Combo; нет кнопок.

## 10. Why Now

Агентные IDE размножают фоновые агенты; верификация bottleneck. У Zeus уже есть classifier, панели, Mini-Verifier, `power_score`. Разрыв до Role Table + Pipeline v1 + DeepSeek-логов — небольшой по коду, большой по марже и качеству.

## 11. API Contracts / Public Surface

- Model id: **`zeuscode`** (+ legacy aliases).
- Hot: OpenAI `chat/completions`; Claude Code: Anthropic `/v1/messages` (base без `/v1`).
- Onestack additive (+ `pipeline`).
- Connect: FR-17 / research doc.
- Role table version в `role_table`, не в model id.

## 12. Risk and Mitigations

| Риск | Митигация |
|------|-----------|
| Дорогой pipeline на мелочи | FR-18 trigger hard; SM-9 |
| Мёртвые LLM-тесты | только ≥950; короткие контракты; Layer A |
| Расхождение API у изолированных doers | обязательный Architecture Brief |
| Custom/стек без ≥950 | куратор = max score → fallback_single (A); не автодобавлять |
| Vision overclaim Gate | hot = Mini+Log; scripts = Studio |
| Cursor BYOK хрупкий | FR-17 Cline/Kilo; FR-16 later |
| Planner fail | FR-12 fallback_single |
| Billing drift | AD-14; ветки Roles |

## 13. Open Questions

Нет блокирующих. FR-16 — backlog. Порог 950 калибруется без UX (`[ASSUMPTION]`).

## 14. Decided + Assumptions

**Decided (2026-07-24…25, Pipeline v1 locked)**
- TG modes only; **кнопок Path нет**.
- Публичный id **`zeuscode`**.
- Small cap ≤2 Doer; verify вне cap.
- Hot Gate = Mini + Log(если доступен); tests N/A if skipped.
- Soft-Stop = max power_score + строка человеку.
- Role table два шага + score gates.
- **Pipeline v1** (FR-18 / M): large+2nd + есть ≥950; Brief ≤3; Test Author ≥950; doers изолированы; один RED→fix затем Escalate≤2 (3А); **file-aware merge**, конфликт → сильная (4Б); default дорогой поток запрещён.
- **Решение A + 2А:** нет ≥950 → куратор пишет **полный ответ один** (без Brief-шага) → Mini → Log? → Escalate; mid-параллель запрещена; модели не докидываем.
- **1Б:** power doer_logic primary = opus допустим.
- **5Б:** нет DeepSeek в выбранном стеке → Log Analyst skip.
- Custom / режимы: юзер выбирает пресет или Набор; руки прочь.
- FR-16 later; FR-17 in scope; lint не critical; kill-switch без Pipeline v1.
- UI: power Gemini-strong UI + opus logic; simple haiku.
- low-conf → large label; Pipeline только со 2nd; Path внутренняя; RACE не цель v1.

**Assumptions**
- `[ASSUMPTION]` ×4 — гипотеза.
- `[ASSUMPTION]` TEST_AUTHOR_MIN=950 по snapshot model_power; сдвиг без UX.
- `[ASSUMPTION]` SM-4 baseline с eval.

## 15. Dependencies

- Fusion PRD + Spine AD-1…18.
- `docs/TZ_ZEUS_ROLE_ROUTING_VERIFY.md`.
- `docs/CLIENT_API_CONNECT_RESEARCH.md`.
- `backend/app/fusion/model_power.py`.
- TG onboarding (`tg-platforms.js`, generators).
- Addendum §J–N = нормативные таблицы для реализации.
