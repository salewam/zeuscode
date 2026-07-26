---
title: Zeus Fusion — Coding Compound Brain
status: final
created: 2026-07-22
updated: 2026-07-22
workflowType: prd
workflowMode: BMAD PM / Update after VP Poor
project_name: ZeusCode (ultra-mode-mvp)
project_root: /Users/money/Desktop/Projects/ultra-mode-mvp
owner: Money
author: BMAD PM John
bmad:
  version: 6.10.0
  skill: bmad-prd
  agent: bmad-agent-pm
  intent: update
  working_mode: fast-path
  stakes: launch
  update_reason: Close VP#3 criticals (Effort +1; classify Phase for Path) + highs (routed_by, MoR scores, RACE terminal, lexicon→FULL)
sourceDocuments:
  - docs/ZEUS_FUSION_ROADMAP_V3.1.md
  - backend/app/fusion.py (brownfield baseline)
  - validation-report.md (VP re-validate 2026-07-22)
document_output_language: Russian
communication_language: Russian
---

# PRD: Zeus Fusion — Coding Compound Brain

## 0. Document Purpose

PRD для PM, архитектора и разработки ZeusCode. Переводит утверждённое ТЗ (`docs/ZEUS_FUSION_ROADMAP_V3.1.md`) в **продуктовые требования**: journeys, glossary, features с FR, metrics, non-goals. Это не roadmap и не sprint-plan — порядок внедрения остаётся в ТЗ / `addendum.md`.

Downstream: Architecture (CA) → Epics & Stories (CE).

**Updates 2026-07-22:** (1) post-VP holes. (2) post-re-VP Path structure. (3) post-VP#3 — Effort=+1 only; Path uses classify Phase; sticky=Leader only; routed_by split; MoR local scores; RACE both-fail; design lexicon→FULL.

---

## 1. Vision

Zeus Fusion — **одна умная модель для кодинга**: публичный id `zeus/fusion`. Разработчик подключает её в любом OpenAI-совместимом клиенте и получает compound-систему: сама понимает фазу и тяжесть задачи, выбирает дешёвый или сильный Path, при необходимости собирает несколько мнений, проверяет достаточность ответа и отдаёт один результат — с честным чеком и без сюрпризов по деньгам.

Рынок уже закрыл «доступ к моделям» (агрегаторы) и «трубу» (gateway). Zeus выигрывает как **coding compound brain**: меньше переплат на мелочах, больше силы на сложных задачах, стабильность в длинном диалоге, прозрачность «за что списали».

**Успех (измеримый):** на Eval Suite (FR-25) + shadow mix реальных coding-запросов Zeus Fusion бьёт одиночный named baseline frontier (см. §7 SM-V) по паре (quality pass-rate, $/1k) при фиксированном Effort=`med` и без Kill-Switch. Победа анекдотом не засчитывается.

---

## 2. Target User

### 2.1 Jobs To Be Done

- Получить верный код / план / ревью / фикс без ручного выбора модели каждый ход.
- Не жечь бюджет на chitchat и мелкий UI, но не проседать на рефакторинге и дебаге.
- Доверять, что система не «молчит», не отдаёт пустоту и не списывает ×3 втихую.
- Работать из Cursor / VS Code / Continue / TG / сайта с одним ключом и одними prefs.
- В контуре ZeusCode — без необходимости отдельного VPN/зарубежной карты для базового доступа.

### 2.2 Non-Users (v1)

- Команды, которым нужен только marketplace на сотни моделей без умного Path.
- Пользователи tab-autocomplete (другой продукт).
- Enterprise с обязательным BYOK / org-seats в v1. `[ASSUMPTION: BYOK = post-MVP]`

### 2.3 Key User Journeys

**UJ-1. Артём чинит баг в Cursor без выбора модели.**  
- **Persona + context:** фуллстек; Cursor; ключ Zeus; Product Mode `power`.  
- **Entry:** в чате уже код и traceback.  
- **Path:** «поправь это» → classify → Path по FR-28 → thinking → патч/объяснение.  
- **Climax:** ошибка закрыта; в Onestack видны Path, Leader, `routed_by`, ₽.  
- **Resolution:** продолжает диалог; Leader не прыгает без существенной смены Phase (FR-16).  
- **Edge:** Leader upstream 500 → failover, не пустой ответ (FR-15).

**UJ-2. Марина готовит лендинг через prefs в Telegram.**  
- **Persona:** делает лендинги; часто настраивает режим в TG Mini App.  
- **Entry:** Product Mode + Effort (+ Kill-Switch при желании).  
- **Path:** в IDE «сделай лендинг для СТО» → fixture-класс F2/F10 (CASCADE) при `power`+light; при `simple` тоже CASCADE (не FULL). HTML + publish.  
- **Climax:** сайт на `zeuscode.ru/go/…` с badge.  
- **Edge:** Kill-Switch → FAST (F7).  
- **Note:** Tradeoff/Preset UI — v1.x (не MVP journey).

**UJ-3. Серёжа проверяет списание и даёт фидбек.**  
- **Persona:** следит за бюджетом API.  
- **Entry:** кабинет / Onestack после тяжёлого запроса.  
- **Path:** breakdown веток → 👎 «ответ слабый» → событие в routing log (MVP: log-only; Elo writeback = v1.x).  
- **Climax:** доверие к биллингу по billable states (FR-19).  
- **Edge:** disconnect mid-Panel → cancel + billing только за `completed` / `partial_stream` / `cancelled_with_usage`.

**UJ-4. Ops катит новую Path-политику без регрессии.**  
- **Persona:** Money / ops.  
- **Entry:** Shadow → Canary 10%.  
- **Path:** Eval + escalate% + 👎 (blocking counters) → 50% → 100% или rollback.  
- **Climax:** фича в проде без просадки Eval.

---

## 3. Glossary

- **Fusion** — продукт и публичный model id `zeus/fusion`.  
- **Product Mode** — `simple` | `power` | `custom`: какой стек моделей у аккаунта.  
- **Path** — способ исполнения MVP: `FAST` | `CASCADE` | `RACE` | `FULL`.  
  - `DUAL` — v1.x (Phase 3).  
  - `TOOL-FULL` — **reserved/v2** (не в MVP enum клиентам).  
- **Complexity band** — `light` | `med` | `heavy` (выход classify рядом с Phase).  
- **Phase** — тип задачи: `chat` | `ui` | `plan` | `implement` | `debug` | `test` | `review` | `docs`.  
- **Leader** — модель с полным контекстом клиента.  
- **Panel** — до трёх моделей на `FULL` (ветки A/B/C).  
- **Satellite** — ветка Panel без полного контекста.  
- **Brief** — сжатое задание для Satellite.  
- **Mini-Verifier** — дешёвая проверка `{good_enough, confidence, reason}`; арбитр cascade-stop и early-exit вместе с Aspect-Verifiers и near-duplicate (FR-12).  
- **Aspect-Verifier** — MVP v1: аспекты `correctness` | `completeness` (опц. позже `security`); must-fail → no early-exit / escalate-safe.  
- **Structured Judge** — анализ Panel (consensus / contradictions / unique / blind spots) → финальный ответ.  
- **Effort** — `low` | `med` | `high`: глубина работы, ортогональна Product Mode.  
- **Sticky Session** — удержание Leader/Phase/стека по `session_id` (TTL).  
- **Shadow Mode** — лог «куда бы пошли» vs frozen baseline router version; ответ пользователю = текущий serving path.  
- **Canary** — выкат 10% → 50% → 100% с rollback.  
- **Onestack** — meta ответа: Path, Phase, Leader, ветки, tokens, ₽, `routed_by`, reason.  
- **Soft-Stop** — останов незавершённых веток при нуле баланса/квоты + частичный billing.  
- **Kill-Switch** — prefs «всегда одна модель» → Path=`FAST` only.  
- **Tradeoff** — cost↔quality `0–10` (**v1.x**, не MVP).  
- **Preset** — `coding-fast` | `coding-budget` | `coding-high` (**v1.x**, не MVP).  
- **MoR blend** — MVP: три score (cost/quality/latency) с фиксированными весами → tip в Path-policy; не отдельный «vote engine».  
- **Eval Suite** — набор промптов для регрессии роутинга/качества.  
- **Billable state** — `completed` | `partial_stream` | `cancelled_no_tokens` | `cancelled_with_usage`.  
- **Model family** — `(provider, base_family)` из Architecture map (anti-clone Panel).

---

## 4. Features

### 4.1 Единый вход Fusion

**Description:** Один публичный model id; поведение задаётся prefs и per-request overrides. Realizes UJ-1, UJ-2.

#### FR-1: Stable public model id
Клиент вызывает `zeus/fusion` как стабильный публичный id.  
**Consequences:**
- Breaking rename без versioned alias запрещён.
- Legacy `zeus/fusion-fast` / `zeus/fusion-full` продолжают работать по FR-37.

#### FR-2: Request precedence, pipeline, and clamps
**Value precedence:** per-request `zeus.*` > account prefs > product default.

**Pipeline order (не conflict):** scrub → classify → Effort band-bump (FR-5) → FR-28 policy (inputs = **classify** Phase + post-Effort complexity) → MoR escalate post-pass → Product Mode clamp → execute. Sticky применяется к **Leader/stack**, не к Path Phase.

**Conflict clamps (выше бьёт ниже; применяются к final Path):**
1. Kill-Switch → FAST only  
2. Explicit forced Path (`zeus.mode` / legacy alias) — разные `routed_by` (FR-37)  
3. Product Mode Path clamp (FR-3)  
4. (v1.x) Tradeoff/Preset Path clamp — слот после forced Path  
5. Sticky Session удерживает Leader/stack (и sticky Phase meta), **не** подменяет classify Phase в FR-28; не блокирует verify-fail escalate  

**Consequences:**
- Явный forced mode не перебивается prefs (кроме Kill-Switch).
- Effort — только +1 band transform перед FR-28 (не floor).
- Path Phase = classify Phase всегда (плюс design-lexicon override в FR-28).
- Нет `zeus.*` → account prefs.

#### FR-3: Product modes
Пользователь выбирает Product Mode `simple` | `power` | `custom`.  
**Path clamps (MVP):**
- `simple`: final Path ∈ {`FAST`, `CASCADE`} unless forced/legacy `full`. Если policy/MoR дали `RACE`/`FULL` → clamp в `CASCADE`, `routed_by=mode_simple_clamp`.  
- `power`: полный enum `FAST|CASCADE|RACE|FULL`.  
- `custom`: как `power` для Path; состав Panel — FR-34.  

**Consequences:**
- `custom` — 1…3 ready chat-модели; при ровно 2: **не** Auto-Panel-of-2 — A+B без C (FR-34), либо FAST/CASCADE на 1 Leader, либо Kill-Switch/FAST.
- Auto на `simple`/`power` никогда не собирает Panel ровно из 2.

---

### 4.2 Classify задачи

**Description:** Перед исполнением система определяет Phase, complexity band, confidence. Realizes UJ-1.

#### FR-4: Phase classification and signals
Каждому запросу назначаются `classify_phase`, `complexity_band ∈ {light,med,heavy}`, `confidence ∈ [0,1]`.  
**Minimum signals (продукт; Arch реализует scoring):**
- follow-up + code fence / diff markers  
- error_trace / stacktrace keywords  
- user message length / multi-file hints  
- Phase lexicon (plan/review/debug/implement verbs)  
- last_assistant continuity (для sticky Leader hint; **не** Path Phase)  

**Consequences:**
- FR-28 Path inputs = `classify_phase` + post-Effort complexity + confidence (+ design-lexicon flag).
- Sticky Phase **не** подменяет `classify_phase` в Path-policy.
- Сбой classify ≠ HTTP 500; fallback Path = `CASCADE` + `routed_by=classify_fallback_cascade` (не FAST, кроме Kill-Switch).

#### FR-5: Effort control
Пользователь задаёт Effort `low|med|high` (prefs или request).  
**Consequences:**
- Effort не заменяет Product Mode.
- `[ASSUMPTION: Effort мапится в upstream reasoning_effort где поддерживается.]`
- **Единственный band transform:** Effort=`high` → complexity **+1** (cap `heavy`) перед FR-28. Нет отдельного floor ≥`med`.
- Effort=`low|med` → band без сдвига (classify as-is).

#### FR-6: Tradeoff and presets — v1.x
Tradeoff 0–10 и Presets `coding-*` — **вне MVP** (ТЗ Phase 3).  
**Consequences:**
- В MVP API/UI не требуют Tradeoff/Preset для Done.
- Kill-Switch остаётся MVP (FR-2/FR-28).
- Когда появятся: clamp Path по слоту FR-2 #4 (после forced Path, до Effort band effects).

---

### 4.3 Paths исполнения

**Description:** Система выбирает Path по FR-28 в пределах timeout/concurrency budget. Realizes UJ-1, UJ-3.

#### FR-28: Path selection policy (MVP contract)

**Control flow (единственный):**  
1) Inputs: `policy_phase = classify_phase`; если `design_lexicon` → `policy_phase := plan` (Path-only override)  
2) `policy_path` = first-match по таблице (MoR **не** в таблице)  
3) MoR post-pass: escalate **ровно 0 или 1** ступень `FAST→CASCADE→RACE→FULL`  
4) Product Mode clamp (FR-3) → serving Path  

Sticky Leader/stack **не** меняет `policy_phase`.

**`routed_by` (MVP closed set — не Arch-invented):**  
`kill_switch` | `forced_fast` | `forced_full` | `legacy_fast_alias` | `legacy_full_alias` | `mode_ignored` | `mode_simple_clamp` | `classify_fallback_cascade` | `policy_heavy_full` | `policy_chat_light` | `policy_light_cascade` | `policy_race_borderline` | `policy_default_cascade` | `policy_design_lexicon_full` | `mor_escalate_<from>_to_<to>` | `cascade_escalate_stronger` | `cascade_escalate_full` | `race_escalate_full` | `race_soft_stop` | `race_disaster` | `compat_1to3_*`

**Policy table (first-match → `policy_path`):**

| Priority | Predicate | Path | `routed_by` |
|---|---|---|---|
| 1 | Kill-Switch ON | FAST | `kill_switch` |
| 2 | `zeus.mode=fast` (не alias) | FAST | `forced_fast` |
| 3 | `zeus.mode=full` (не alias) | FULL | `forced_full` |
| 4 | legacy `zeus/fusion-fast` | FAST | `legacy_fast_alias` |
| 5 | legacy `zeus/fusion-full` | FULL | `legacy_full_alias` |
| 6 | `design_lexicon` ∨ `policy_phase` ∈ {plan, review} ∨ complexity=`heavy` ∨ (`policy_phase`=`debug` ∧ complexity≥`med`) | FULL | `policy_design_lexicon_full` если lexicon else `policy_heavy_full` |
| 7 | `policy_phase`=`chat` ∧ complexity=`light` ∧ confidence≥0.70 | FAST | `policy_chat_light` |
| 8 | complexity=`light` ∧ `policy_phase` ∈ {ui, docs, test, implement} ∧ confidence≥0.60 | CASCADE | `policy_light_cascade` |
| 9 | interactive=`true` ∧ complexity∈{light,med} ∧ `policy_phase` ∈ {chat, ui, implement, test} ∧ confidence<0.70 | RACE | `policy_race_borderline` |
| 10 | Default | CASCADE | `policy_default_cascade` |

**design_lexicon (v1 frozen list, id=`lexicon_v1` in baseline_id):**  
`спроектируй|спроектировать|architecture|design the system|ревью PR|code review|спроектируй модуль`. Расширение списка = новый lexicon id + Eval (не silent Arch grow).

**Interactive hint:** `interactive=true` iff **все**:
- `policy_phase` ∈ {chat, ui, implement, test}  
- complexity ∈ {light, med}  
- `design_lexicon` = false  
- ∧ (`is_follow_up_short` ∨ (`stream=true` ∧ user_chars < 400))  

`interactive=false` если `policy_phase` ∈ {plan, review, debug} ∨ complexity=`heavy` ∨ Kill-Switch ∨ `design_lexicon`.  
`is_follow_up_short` = есть last_assistant ∧ user_chars < 280 ∧ нет нового traceback.

**MoR scores (local MVP, A17-v1; no LLM):**  
`B = {light:0.35, med:0.55, heavy:0.80}`  
`s_quality = clamp01(B[complexity] + 0.15·[Effort=high] + 0.20·(1−confidence))`  
`s_cost = clamp01(1 − s_quality)`  
`s_latency = 0.70 if interactive else 0.40`  
`dominant = argmax(s_*)` (ties → quality > latency > cost).  
`tip_escalate = 1` iff `dominant=quality` ∧ `s_quality≥0.60` ∧ `policy_path≠FULL` ∧ not Kill-Switch ∧ not forced/legacy Path; else `0`.  
`mor_path = escalate_one(policy_path)` if tip_escalate else `policy_path`.  
`escalate_one`: FAST→CASCADE, CASCADE→RACE, RACE→FULL, FULL→FULL.

**Fixtures (один Expected Path):**

| # | Given | Expected Path |
|---|---|---|
| F1 | chitchat, light, conf≥0.7, power, Effort=med | FAST |
| F2 | CSS/UI tweak, light, conf≥0.6, power, Effort=med | CASCADE |
| F3 | sticky Leader from implement + follow-up «поправь отступы»; classify=implement, light, conf≥0.6 | CASCADE (sticky≠Path) |
| F4 | traceback + classify=debug, complexity≥med, power | FULL |
| F5 | «спроектируй модуль auth»; classify may be implement+med; design_lexicon=true | FULL |
| F6 | refactor 1 file, med, conf=0.65, interactive=false, Effort=med | CASCADE |
| F7 | Kill-Switch + review request | FAST |
| F8a | `zeus.mode=full` | FULL (`forced_full`) |
| F8b | `zeus/fusion-full` alias | FULL (`legacy_full_alias`) |
| F9 | classify fail/timeout | CASCADE |
| F10 | implement light «добавь кнопку», conf≥0.6 | CASCADE |
| F11 | follow-up short, med, conf=0.50, interactive=true, power | RACE |
| F12 | review PR diff, heavy | FULL |
| F13 | implement, heavy, conf=0.40, stream=true | FULL |
| F14 | chitchat, classify light conf=0.75, Effort=high → post-Effort=`med` (не FAST); tip from local scores | CASCADE |
| F15 | simple + F5 (lexicon) without forced/legacy full | CASCADE (`mode_simple_clamp`) |
| F16 | classify=implement+med, Effort=high → complexity=`heavy`, power | FULL |
| F17 | sticky meta=implement; classify=`review` conf=0.65 → Path uses classify (не sticky) | FULL |
| I1 | follow-up 120 chars, ui, light → interactive=true | gate |
| I2 | «спроектируй…» → design_lexicon; interactive=false; Path FULL (power) | gate+Path |
| I3 | stream=true, 900 chars, med → interactive=false | gate |
| R1 | RACE both verifier-fail, power, complexity=med | FULL (`race_escalate_full`) |
| R2 | RACE both-fail, simple | Soft-Stop / CASCADE terminal (`race_soft_stop`) |

#### FR-7: FAST
Одна Leader; нет Panel/Judge.  
**Consequences:** thinking/status виден клиенту; failover по FR-15.

#### FR-8: CASCADE
Сначала дешёвая модель → Mini-Verifier → escalate только при fail/low confidence.  
**Consequences:**
- Stop на cheap только при `good_enough` ∧ `confidence ≥ threshold`.
- `[ASSUMPTION: default threshold = 0.8; owner = Money/ops; меняется через flag + Eval.]`
- **Escalate map (deterministic)** при Mini-Verifier fail:

| Condition | Action |
|---|---|
| Kill-Switch | one `stronger_leader` retry → stop (never Panel) |
| Product Mode=`simple` | one `stronger_leader` → stop (never FULL) |
| complexity=`heavy` ∨ Phase ∈ {plan, review, debug} | → FULL if mode allows; else stronger_leader→stop |
| complexity=`med` ∧ mode∈{power,custom} | stronger_leader once; if still fail → FULL |
| complexity=`light` | stronger_leader once → stop |

- `stronger_leader` = next id в ops-ordered fallback list для Product Mode (список обязателен в Architecture; пустой = fail Done).
- Onestack: `path` = **final** execution Path; `policy_path` + `escalate_from` если escalate; `routed_by` ∈ {`cascade_escalate_stronger`,`cascade_escalate_full`}.

#### FR-9: RACE
Borderline/interactive: parallel cheap+strong; первый годный; остальное cancel.  
**Consequences:**
- «Годный» = Mini-Verifier pass **или** (verifier degrade → first-complete strong).
- Cancelled branch billing = FR-19 states (не «best-effort»).
- Kill-Switch → FAST; Product Mode=`simple` clamp → CASCADE (не RACE).
- **Both-fail terminal:** если ни одна ветка не годный (verifier fail / error / timeout):
  1) mode∈{power,custom} ∧ complexity≥`med` → escalate FULL (`race_escalate_full`);
  2) иначе Soft-Stop pick по FR-14 (`race_soft_stop`);
  3) если нет partial → structured disaster error (`race_disaster`).

#### FR-10: FULL (Panel)
Тяжёлые задачи — Panel ≤3 с ролями A ответ / B альтернатива / C критика.  
**Consequences:**
- Leader = полный контекст; Satellites = Brief (last_assistant + errors + goal; не history×3).
- **Diversity:** запрещены 3 модели одного `model_family` без явного ops exception flag.
- **Order:** Aspect-Verifiers (FR-31) **до** near-duplicate early-exit. Aspect must-fail ⇒ нельзя early-exit по τ.
- **Near-duplicate early-exit:** similarity ≥ `[ASSUMPTION: τ=0.92]` между успешными ветками → можно stop без полного Judge cost path (Arch выбирает metric; PRD фиксирует τ intent).
- Latency-homogeneous preset Panel — MVP (B7).
- Role `temperature` / `max_tokens` различаются по A/B/C (B10) — значения в Architecture, наличие обязательно.
- **Rank-then-fuse (B5):** ветки ранжируются; в Judge уходит **top-K** (`[ASSUMPTION: K=2]` если rank-1 − rank-3 ≥ `[ASSUMPTION: Δ=0.15]`, иначе top-3). Ветки ниже cutoff отбрасываются до синтеза.
- 1 successful branch → final = that branch (no Judge). 0 success → FR-14 / disaster.

#### FR-11: DUAL (Architect→Editor) — v1.x
Два прохода на `implement` / тяжёлом `debug` — **вне MVP** (ТЗ Phase 3 / B9).  
**Consequences:**
- MVP Done не требует DUAL.
- Когда включён: один финальный ответ пользователю; Plan≠Implement tables (A8/A9) в том же релизе.

#### FR-12: Early-exit
Досрочный выход только через Mini-Verifier, Aspect-Verifiers (FR-31), или near-duplicate (FR-10).  
**Consequences:**
- Самооценка Leader запрещена.
- Precedence: Aspect must-check → затем Mini-Verifier / near-duplicate.

#### FR-13: Structured Judge
При ≥2 разных успешных ветках — structured analysis, затем финал.  
**Consequences:**
- В анализе: consensus / contradictions / unique / blind spots.
- **Anti-bias oracle (primary):** при non-empty `contradictions` token-overlap финала с rank-1 веткой ≥ `[ASSUMPTION: 0.95]` → тест падает. Cosine — secondary diagnostic only.
- При согласии веток допускается короткий fuse.

#### FR-14: Soft-Stop and cancel
Disconnect или нулевой баланс/квота → останов незавершённых веток.  
**Consequences:**
- Disconnect → cancel in-flight; billable states по FR-19.
- Soft-Stop selection (лучший частичный):  
  1) max Mini-Verifier `confidence` среди веток со state `completed`/`partial_stream`, иначе  
  2) first-complete, иначе  
  3) Leader-partial.  
- Пользователю не пустой ответ, если есть хоть один partial_stream/completed.

#### FR-31: Aspect-Verifiers v1 (MVP)
Обязательны на FULL и на CASCADE→FULL escalate; опционально flag на прочих CASCADE. Аспекты: `correctness` + `completeness`.  
**Consequences:**
- Fail любого must-аспекта → no early-exit / escalate-safe (до near-duplicate).
- `security` — optional flag, не blocker MVP Done.
- Degrade Aspect-Verifier ≠ user 500; fallback на Mini-Verifier only + alert.

#### FR-32: Prompt adaptation v1 (MVP)
Короткий rewrite system/user hint под выбранную Leader/Satellite family.  
**Consequences:** не меняет user intent; регрессия publish (FR-26) — blocker на релизах adaptation.

#### FR-34: Custom-panel rules (MVP)
Для Product Mode `custom`: явные правила сборки Panel из выбранных ready models.  
**Consequences:**
- 1 model → FAST-equivalent.
- 2 models → A+B без C (не «auto-2» на simple/power).
- 3 models → A/B/C.
- Dead models excluded (FR-15).

---

### 4.4 Надёжность и runtime

#### FR-15: Leader health and failover
Учёт health Leader; при провале — fallback по ops-ordered ready list Product Mode.  
**Consequences:**
- Try next ready model; empty ответ при наличии ready fallback недопустим.
- Если ready list пуст → structured disaster error (FR-29).
- Dead models вне ready Panel.

#### FR-16: Sticky Session
`session_id` удерживает **Leader + stack** (+ sticky Phase meta для UX) на TTL.  
**Path Phase всегда = classify** (FR-28); sticky Phase **не** вход Path-policy.  
**Substantial change** (обновляет sticky meta / может сменить Leader affinity): classify_phase ≠ sticky meta ∧ (confidence≥0.70 ∨ strong signal: traceback/new file set / explicit «другая задача»).  
**Consequences:** sticky не блокирует Path FULL на новом classify=review/plan; не блокирует verify-fail escalate.  
`[ASSUMPTION: TTL 5–15 мин inactivity.]`  
`[ASSUMPTION: transport = header X-Zeus-Session-Id; fallback body zeus.session_id.]`

#### FR-17: Control-plane degrade
| Component | Degrade | `routed_by` / note |
|---|---|---|
| Classify | Path=`CASCADE` | `classify_fallback_cascade` |
| Mini-Verifier | no early-exit; CASCADE/RACE escalate-safe | alert |
| Aspect | fallback Mini only | alert |
| MoR scores | tip_escalate=0 | policy `routed_by` |
Аномальная частота degrade алертится (E6).

#### FR-18: Rollout safety
Новые Path-политики: Shadow → Canary → rollback по Eval/алертам.  
**Consequences:**
- `baseline_id` = immutable router config hash.
- Первый Fusion-policy canary: baseline = legacy auto 1↔3 behavior.
- Последующие canaries: baseline = previous 100% serving policy hash.
- Shadow логирует candidate vs baseline; ответ пользователю = serving path (не меняется в Shadow).

#### FR-29: Runtime budgets (MVP presence)
На каждом запросе обязательны:
- global timeout  
- concurrency caps (Panel/RACE)  
- retry/backoff на transient upstream  
- disaster path → non-empty structured error (не silent empty)  
- streaming thinking + keepalive  
- rate limits (base)  
- long-context Leader selection + overflow strategy (middle-out / weak-summary; не молча резать traceback/errors)  
- prefix/prompt-cache hint где поддерживается  

Числовые бюджеты — Architecture/ops; **отсутствие механизма = fail Done**.

---

### 4.5 Деньги, прозрачность, безопасность

#### FR-19: Honest branch billing and billable states
Каждый upstream/control вызов имеет billable state:
| State | Биллинг |
|---|---|
| `completed` | полные usage |
| `partial_stream` | фактически полученные tokens |
| `cancelled_no_tokens` | ₽ = 0 |
| `cancelled_with_usage` | reported usage до cancel |

Биллятся: ветки, Mini-Verifier, Aspect-Verifier, Judge, cascade attempts, prompt-adapt call если отдельный.  
Control-plane: classify / MoR scoring — bill **только** если отдельный upstream LLM call; regex/local classify и local MoR score = ₽0; факт отражается в Onestack.  
**Consequences:**
- Drift tolerance: integer tokens exact match в ledger; ₽ within 1 minor currency unit.
- Запрещён acceptance language «best-effort billing».
- Частичный billing mid-fail обязателен.

#### FR-20: Onestack transparency
В ответе Onestack: `path` (**final** execution), `policy_path`, optional `escalate_from`, Phase=`classify_phase`, complexity (post-Effort), Leader, ветки, tokens, ₽, `routed_by`, reason, billable breakdown.  
**Consequences:** API всегда; human UI в кабинете; TG — в той же продуктовой волне prefs.  
SM-1 считает по final `path`.  
`[ASSUMPTION: имена моделей в UI анонимизированы A/B/C для пользователя; ops видит raw.]`

#### FR-21: Secret/PII scrub
Перед upstream — маскирование очевидных секретов; политика ПДн расширяема.  
**MVP minimum:** API keys, bearer tokens, private key blocks, email-like secrets regex.  
**Consequences:** не ломает обычный код-контекст; opt-out хранения сырых промптов — на уровне ключа/аккаунта.

#### FR-22: Anti-bloat
Полный Cursor/skills dump не уходит всем веткам Panel.  
**Consequences:** Satellites только Brief; Leader сохраняет полезный coding-контекст.

---

### 4.6 Prefs, фидбек, качество

#### FR-23: Preference surfaces (MVP)
Product Mode, Effort, Kill-Switch, custom models — TG Mini App + кабинет.  
**Consequences:** один аккаунт → одни prefs для всех клиентов с ключом. Realizes UJ-2.  
Tradeoff/Preset surfaces — v1.x с FR-6.

#### FR-24: Feedback
👍/👎 и/или regen логируются с routing context.  
**MVP:** log-only schema (не требует Elo writeback для Done).  
**v1.x:** Elo `Phase × model` влияет на Leader pick (canary).  
**Consequences:** маркетинг «учится» допустим только после v1.x writeback; MVP = «собираем сигнал».

#### FR-25: Eval Suite gate
Изменения Path проходят Eval Suite до 100% Canary.  
**Consequences:**
- Suite size `[ASSUMPTION: N≥50]` prompts; buckets + fixtures F1–F17, I1–I3, R1–R2.
- **Pass oracle (per prompt):** (a) Path match если tagged fixture; (b) non-empty final; (c) code bucket → fenced code когда задача просит код; (d) `min(correctness, completeness) ≥ 3` на frozen LLM-judge (fixed judge model id в baseline); (e) нет billing ledger violation.
- Per-bucket pass bar `[ASSUMPTION: ≥ baseline − 2pp]` и shadow-delta gate на Path distribution.
- Baseline snapshot: router `baseline_id`, `lexicon_v1`, SM-V frontier id, judge id — до canary.
- Регрессия блокирует rollout.

---

### 4.7 Publish

#### FR-26: HTML publish continuity
Полный HTML лендинг/приложение может публиковаться на `zeuscode.ru/go/…` с badge.  
**Consequences:** publish regression — blocker релиза, затрагивающего Judge, system prompts, Brief, sanitize, **или** prompt adaptation (FR-32).

---

### 4.8 Agent path (v2 capability)

#### FR-27: Agent/tools readiness
В v2 Fusion не уничтожает `tool_calls`; появляются `TOOL-FULL`, execution-aware verify, recursion guard.  
**Consequences:** MVP chat path может сохранять текущий sanitize tools; agent — отдельный major после стабилизации chat Paths.  
`TOOL-FULL` не экспонируется в MVP Onestack Path enum.

#### FR-37: Legacy mode compatibility matrix
| Legacy / request | Serving Path | `routed_by` |
|---|---|---|
| `zeus/fusion` auto | FR-28 | policy_* / mor_* / clamps |
| `zeus/fusion-fast` | FAST | `legacy_fast_alias` (**не** `forced_fast`) |
| `zeus/fusion-full` | FULL | `legacy_full_alias` (**не** `forced_full`) |
| `zeus.mode=fast` | FAST | `forced_fast` |
| `zeus.mode=full` | FULL | `forced_full` |
| historic auto 1↔3 (no new flags) | FR-28 | `compat_1to3_*` |

**Consequences:** aliases не ломать; Shadow `baseline_id` per FR-18; коды не коллизят с FR-28.  
**Forced mode enum (MVP):** `zeus.mode` ∈ {`fast`, `full`} only. Unknown → ignore + `mode_ignored`. CASCADE/RACE — policy-only.  
**`zeus.thinking`:** MVP = passthrough hint в upstream reasoning если модель поддерживает; иначе ignore (не отдельный Path).

---

## 5. Non-Goals (Explicit)

- Marketplace на сотни моделей.
- Server-side RAG / загрузка репозитория на Zeus.
- Tab-autocomplete routing.
- Semantic cache по умолчанию для codegen.
- Early-exit по самооценке Leader.
- Полный клон Claude Code в MVP.
- BYOK, org seats, trained RouteLLM — не MVP.
- DUAL / Tradeoff / Presets / MoA layer-2 / optional web Panel — не MVP (v1.x+).
- Weak-model side tasks (A13) как отдельный product path — не MVP (overflow/weak-summary в FR-29 ≠ A13).
- Client docs pack (E11) — не blocker MVP Done (canary exit может требовать минимальный README).
- Elo writeback в routing — не MVP (log-only).
- Экспорт `TOOL-FULL` в клиентский Path enum — не MVP.

---

## 6. MVP Scope

### 6.1 Definition (honest)

**Product MVP** = ТЗ **Фазы 0–1 полностью** + **Фаза 2 с явным include/exclude** ниже.  
**MVP Done ≠ Canary 100%.** Canary exit — §6.4.

### 6.2 In Scope (MVP Done)

| Area | FR / TZ | Notes |
|---|---|---|
| Foundation Phase 0 | FR-15,19,20,18,29,22,1,2,37 | logs, billing, soft-stop, health, budgets, flags, shadow, eval baseline, stream, aliases |
| Smart path Phase 1 | FR-4,5,7,8,9,12,16,17,21,23,28,29 | phases, cascade, race, mini-verify, sticky, effort, cancel, degrade, scrub, kill-switch, path-policy |
| Strong panel Phase 2 include | FR-10,13,14,31,32,34 + B1,B2,B4,B5,B6,B7,B10,B14,A12,A16,E10 | roles, judge, early-exit, rank-then-fuse, brief, latency preset, role temps, diversity, custom-panel, prompt adapt |
| MoR v1 | FR-28 MoR post-pass (A17) | tip_escalate 0|1; не vote engine |
| Aspect v1 | FR-31 (B13) | correctness + completeness |
| Prefs MVP | FR-23 | Product Mode, Effort, Kill-Switch, custom |
| Publish continuity | FR-26 / E15 | regression gate |
| Feedback MVP | FR-24 / E2 | log-only |
| Eval gate | FR-25 / E4 | N≥50 + fixtures + pass oracle |
| Min alerts | E6 subset | verifier always-OK, billing drift, dead models (для §6.4) |

### 6.3 Out of Scope for MVP

| Item | TZ | Почему |
|---|---|---|
| DUAL Architect→Editor | B9 / Phase 3 | v1.x FR-11 |
| Tradeoff + Presets UX | A6–A7 / Phase 3 | v1.x FR-6 |
| Phase→model tables polish / Plan≠Implement full | A8–A9 | v1.x with DUAL |
| Weak-model side tasks | A13 / Phase 3 | later; ≠ FR-29 overflow |
| Client docs pack | E11 / Phase 3 | not MVP Done blocker |
| Full dashboard | E7 | later; min alerts in §6.2 |
| MoA layer-2 | B8 | hard-only later |
| Optional web на Panel | B11 | later |
| Aspect `security` must | B13+ | optional flag |
| Full MoR vote engine | A17+ | MVP = post-pass tip only |
| Elo writeback | E3 | v1.x; MVP log-only |
| FR-27 Agent/tools | Phase 5 | v2 |
| Multimodal images | — | v2 |
| BYOK / teams / trained router / semantic cache | — | later |

### 6.4 Canary exit criteria (→100%)

Отдельно от MVP Done. Блокируют 100%:
- FR-25 Eval bars + Path fixtures F1–F17 / I1–I3 / R1–R2  
- SM-C1 / SM-C3  
- E6 min alerts live  
- E15 publish regression green на last prompt-touching release  
- E18 load test + incident runbook signed  
- SM-V baseline id записан в eval snapshot  

---

## 7. Success Metrics

**Primary**
- **SM-1:** Доля final Path ∈ {FAST, CASCADE} ↑ vs baseline **stratified by Phase**; RACE share reportится отдельно и `[ASSUMPTION: RACE ≤ 25% soft cap per Phase]` — рост FAST+CASCADE не засчитывается при SM-C1 violation или RACE cap breach. → FR-7, FR-8, FR-9, FR-28  
- **SM-2:** Eval Suite no regress на canary→100% (FR-25 bars). → FR-25, FR-18  
- **SM-3:** Billing drift ≤ 1 minor unit; token ledger exact. → FR-19, FR-14  
- **SM-V (Vision):** Eval pass-rate (FR-25 oracle) ≥ single-frontier baseline ∧ $/1k ≤ baseline при Effort=med, no Kill-Switch. `[ASSUMPTION: frontier baseline model_id = power-mode Leader for Phase=implement at eval baseline snapshot; id frozen in eval_baseline.json before canary.]`

**Secondary**
- **SM-4:** p95 latency FAST ↓ vs baseline. → FR-7, FR-9  
- **SM-5:** Пустые ответы при down Leader → 0 при наличии ready fallback. → FR-15  
- **SM-6:** Cancel/Soft-Stop savings $ > 0 на disconnect cohort. → FR-14  

**Counter-metrics (blocking на canary→100%)**
- **SM-C1:** 👎 rate на hard Phases (`plan`,`review`,`debug` ∧ complexity≥med) не выше baseline + `[ASSUMPTION: +2pp]`.  
- **SM-C2:** Не максимизировать Panel winrate ценой p95 и $/1k на light.  
- **SM-C3:** Не отключать Mini-Verifier ради latency (alert = rollback candidate).

---

## 8. Cross-Cutting NFRs

Числа — Architecture; наличие — FR-29 / observability ниже.

- **Reliability:** control-plane degrade ≠ user 500; disaster path = structured error (FR-29).  
- **Performance:** global timeout; concurrency caps; stream thinking (FR-29).  
- **Observability:** `trace_id`, path rates by Phase, escalate%, verifier always-OK, dead models, `routed_by` histogram.  
- **Security:** secret scrub MVP minimum (FR-21); log TTL / opt-out.  
- **API stability:** `zeus/fusion` + additive Onestack.  
- **Rollout:** Shadow → Canary → rollback (FR-18).  
- **Ops:** load test + incident runbook до широкого rollout крупных Path.

---

## 9. Constraints and Guardrails

- Маржа на Mini-Verifier/Cascade заложена в экономику.  
- Semantic cache на codegen запрещён в MVP.  
- Логи промптов — с политикой хранения.  
- Продуктовая граница: coding compound brain, не general research mega-ensemble by default.
- Early-exit только verifier/aspect/near-duplicate.

---

## 10. API Contracts / Public Surface

- `/v1/chat/completions`, `model: "zeus/fusion"`.  
- Optional: `zeus.mode` ∈ {`fast`,`full`} (unknown ignored), `zeus.effort`, `zeus.thinking` (passthrough/ignore per FR-37); session: `X-Zeus-Session-Id` / `zeus.session_id`.  
- v1.x optional: `zeus.tradeoff`, `zeus.preset`.  
- Response meta: Onestack (`path`, `phase`, `complexity`, `leader`, `panel`, verifier/classifier, `usage_breakdown`, `routed_by`, billable states, mode clamps).  
- MVP Path enum в Onestack: `FAST|CASCADE|RACE|FULL` only.  
- Breaking Onestack в MVP — только additive.

---

## 11. Why Now

Агрегаторы дают доступ, OpenRouter Fusion/MoA — ансамбли, coding-агенты — фазы/effort. У Zeus уже есть 1↔3, classify, Leader/Brief, prefs и publish. Окно — собрать это в цельный coding brain раньше, чем рынок закрепит «auto» как commodity без честного биллинга и coding-фаз.

---

## 12. Open Questions

Только Arch/ops числа (не product Path brain):

1. Точные timeout/concurrency/rate-limit budgets (presence = FR-29).  
2. Similarity metric implementation для τ=0.92 (τ intent fixed).  
3. Concrete judge model id + power Leader id в первом `eval_baseline.json` (правило выбора зафиксировано в SM-V assumption).

---

## 13. Assumptions Index

- BYOK / org seats — post-MVP.  
- Mini-Verifier threshold default = 0.8; owner Money/ops.  
- Sticky TTL = 5–15 мин; sticky = Leader/stack only (не Path Phase).  
- Session transport = `X-Zeus-Session-Id` + body fallback.  
- Effort → upstream reasoning_effort где возможно.  
- Effort=high → complexity **+1 only** (no floor); before FR-28.  
- Path Phase = classify (+ design_lexicon → plan override).  
- Near-duplicate τ = 0.92; Aspects before τ exit.  
- Judge anti-bias primary = token-overlap 0.95 when contradictions.  
- MoR local scores (B/Effort/conf/interactive); tip iff quality dominant ∧ s_quality≥0.60; one step.  
- Rank-then-fuse K=2 when Δ≥0.15 else top-3.  
- Eval N≥50; `min(correctness,completeness)≥3`; per-bucket ≥ baseline−2pp; SM-C1 +2pp 👎.  
- SM-1 RACE soft cap 25% per Phase.  
- SM-V frontier = power Leader for implement at baseline snapshot.  
- `simple` Path clamp ∈ {FAST, CASCADE} unless forced/legacy full.  
- lexicon_v1 frozen in baseline_id.  
- UI model names = A/B/C; ops raw.  
- PII MVP minimum = keys/bearer/private-key/email-like.  
- ТЗ v3.1 — утверждённый источник; Fast path без отдельного JTBD-интервью.  
- Product MVP = Phase 0–1 + Phase 2 include (§6); MVP Done ≠ canary 100%.  
- TZ A2 MVP subset: light CASCADE may stop after stronger_leader (не всегда FULL).  
- DUAL / Tradeoff / Presets / A13 / E11 full = v1.x or later.  
- Feedback MVP = log-only; Elo writeback = v1.x.  
- Aspect v1 = correctness + completeness; required on FULL and CASCADE→FULL.  
- Unknown `zeus.mode` → ignore.

---

## 14. Rollout and Change Management

1. Shadow vs `baseline_id` (FR-18).  
2. Canary 10% → 50% → 100% only if §6.4 exit green.  
3. Rollback: Eval regress, SM-C1/C3, verifier always-OK, billing drift.  
4. Legacy aliases не ломать (FR-37).  
5. Publish regression на релизах Judge / prompts / Brief / sanitize / prompt-adapt.

---

## 15. Brownfield: ships today vs new

| Already in Zeus (baseline) | New for Product MVP |
|---|---|
| `zeus/fusion`, simple/power/custom | Path taxonomy + FR-28 policy→MoR→mode clamp |
| Auto 1↔3 | Mini-Verifier; Aspect v1; rank-then-fuse top-K |
| Flash classify + regex | complexity + interactive formula + fixtures |
| Leader + Brief + Judge | anti-bias oracle; diversity family map |
| Thinking SSE / sanitize / prefs / publish | Sticky, Soft-Stop, Onestack, Shadow/Canary, Eval oracle, FR-29, MoR post-pass, prompt adapt, custom-panel |

---

*PRD status: **final** (Update post-VP#3). Next: optional re-validate → `bmad-create-architecture` (CA) → CE.*
