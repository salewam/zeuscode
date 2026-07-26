# ТЗ: Zeus Role Routing + Verify/Escalate

**Продукт:** ZeusCode (`zeuscode.ru`)  
**Публичная модель:** `zeuscode` (legacy alias: `zeus/fusion`)  
**Дата:** 2026-07-24  
**Статус:** спецификация к внедрению (AS-IS → TO-BE)  
**Связанные артефакты:**
- Spine: `_bmad-output/planning-artifacts/architecture/architecture-ZeusCode-2026-07-22/ARCHITECTURE-SPINE.md`
- Roadmap: `docs/ZEUS_FUSION_ROADMAP_V3.1.md`
- Схемы (Canvas): `zeus-role-model-architecture`, `zeus-multi-agent-task-scheme`, `zeus-verify-escalate-scheme`

---

## 0. Цель одной фразой

Сделать так, чтобы `zeus/fusion` **сам** понимал тип и размер задачи, **ставил подходящие нейронки на роли**, **проверял результат железом + дешёвым разбором логов**, и при провале **усиливал стек** — без конструктора комбо для пользователя («одна кнопка» = один ключ / один model id).

**Не цель:** marketplace на 400 моделей, Combo Studio как у Omni, обязательный human-in-the-loop на каждый Cursor-запрос.

---

## 1. Проблема

1. Верификация кода/логов у человека и агентов съедает в разы больше времени, чем написание.
2. Дорогие модели часто вызываются на мелочи (логи, 3 строки) → дорого и медленно.
3. Несколько одинаковых агентов без ролей → хаос и потеря контроля.
4. Конкурент (Omni Combo) даёт ручной ранг «ум × цена»; Zeus выигрывает простотой, но внутри должен быть **явный role→model алгоритм**, иначе качество/маржа плавают.

**Ожидаемый эффект (гипотеза продукта):** до ×4 к скорости полезной работы за счёт (а) дешёвых специалистов на рутину, (б) параллели ролей на большой задаче, (в) автоматической проверки вместо ручного «проморгал».

---

## 2. AS-IS — что уже есть в продукте

### 2.1. Поверхность продукта

| Компонент | Статус | Где |
|-----------|--------|-----|
| OpenAI-compatible gateway | Есть | `POST /v1/chat/completions` |
| Публичный id `zeus/fusion` + aliases | Есть | `routers/chat.py`, catalog |
| Режимы `simple` / `power` / `custom` | Есть | prefs TG + `zeus.mode` |
| Prepaid баланс ₽, usage logs | Есть | `cost.py`, `UsageLog` |
| TG bot + Mini App (ключ, режимы, советник) | Есть | `telegram_*`, `/tg` |
| Studio / Ultra оркестрация | Есть (отдельный контур) | `orchestrate.py` |
| Publish HTML | Есть | `publish.py` |

### 2.2. Fusion-мозг (уже реализовано)

| Возможность | Статус | Детали / файлы |
|-------------|--------|----------------|
| Панель **simple** | Есть | `deepseek-v4-flash` + `gemini-3-pro` + `claude-haiku-4-5` (`_monolith.py`) |
| Панель **power** | Есть | `claude-opus-4-8` + `deepseek-v4-pro` + `gemini-3.1-pro` |
| Классификатор задачи | Есть | Flash micro-classifier JSON → regex fallback; `task_kind` ∈ `{light, ui, tests, review, architecture, code, general}` |
| Выбор силы стека 1↔3 | Есть | `stack: fast\|full` (auto никогда не даёт ровно 2) |
| `pick_leader` по `task_kind` | Есть | бонусы `_TASK_BONUS` (ui→haiku/gemini, light→flash, architecture→opus, …) |
| Sticky session (leader/stack) | Есть | `fusion/session.py`; Path **не** из sticky |
| Paths FAST/CASCADE/RACE/FULL | Есть (каркас + частичная реализация) | `fusion/policy.py`, `panel.py`, `_monolith.py` |
| Mini-Verifier | Есть | `fusion/verify.py`: JSON `{good_enough, confidence, reason}`; default model `deepseek-v4-flash`; fail/degrade → escalate |
| Satellite Brief (не ×3 полный контекст) | Есть | `fusion/brief.py` |
| Honest billing / FusionResult | Есть (частично) | `fusion/types.py`, `chat.py` `_charge_amounts`; AD-8/14 |
| Kill / shadow / canary flags | Есть каркас | `fusion/metrics.py`, settings |
| Aspect-verifiers / Judge на FULL | Есть зачатки | `verify.py`, `judge.py` |

### 2.3. Чего нет (разрывы относительно целевой архитектуры)

| Разрыв | Почему больно |
|--------|----------------|
| Нет явной таблицы **Role → Model** в конфиге | Логика размазана по `_TASK_BONUS` + хардкод панелей |
| Нет роли **Log Analyst** (DeepSeek → JSON по логам) | Логи либо ест дорогая голова, либо не разбираются системно |
| Нет **Test Executor** (скрипт) в hot path Fusion | «Проверка» часто только LLM-verifier, не exit codes |
| Нет **Test Planner** | Неясно, какой минимум unit/integration гонять |
| Нет **Planner/Decompose** на компоненты большой задачи | На full сейчас скорее панель A/B/C, не «5–6 ролей по артефактам» |
| Finding state machine + human gate | Не нужны в Cursor hot path; нет и в Studio как продукта |
| Автопополнение баланса | Блокер GTM, вне scope этого ТЗ, но влияет на использование |

---

## 3. TO-BE — целевая архитектура

### 3.1. Принципы (инварианты)

1. **LLM не финалит качество.** Истина = Gate (скрипт + строгий JSON отчётов). Leader self-score запрещён (AD-5).
2. **Роль ≠ модель.** Роль стабильна; модель в роли можно менять конфигом.
3. **Малая задача ≠ большая.** Малая: 1–2 модели. Большая: 4–6 **разных** ролей, не 6 клонов.
4. **Сначала дёшево, потом сильнее.** Ошибка роутера лечится escalate, не «идеальным первым выбором».
5. **Горячий путь Cursor** остаётся одним `chat/completions`. Тяжёлый decompose/test-runner — Studio или удлиненный FULL path с бюджетом.
6. **Не ломать spine:** Policy → Execute → Bill; Path ∈ `{FAST,CASCADE,RACE,FULL}`; Bill только из `FusionResult`.

### 3.2. Роли системы

| ID роли | Ответственность | Тип | Выход |
|---------|-----------------|-----|-------|
| `router` | Классификация размера/типа задачи | LLM (дешёвый) | `{stack, task_kind, confidence, size}` |
| `planner` | Разрез большой задачи на компоненты | LLM | `components[]` |
| `doer_logic` | Backend / бизнес-логика / багфикс | LLM | patch / answer |
| `doer_ui` | UI / вёрстка / лендинг | LLM | patch / answer |
| `log_analyst` | Разбор логов / traceback | LLM (дешёвый) | JSON report |
| `test_planner` | Минимальный набор проверок | LLM или правила | `{unit, integration, …}` |
| `test_executor` | Запуск команд | **Скрипт** | PASSED/FAILED + logs |
| `mini_verifier` | Дешёвая оценка ответа vs goal | LLM | `{good_enough, confidence}` |
| `judge_fix` | Синтез / починка после RED | LLM (сильный) | final answer / patch |
| `gate` | GREEN/RED решение | **Код** | escalate \| done |

### 3.3. Таблица Role → Model (v1, Zeus-каталог)

| Роль / task_kind | Primary | Fallback | Примечание |
|------------------|---------|----------|------------|
| `router` | `deepseek-v4-flash` | `gemini-2.5-flash` | Уже так |
| `light` | `deepseek-v4-flash` | `claude-haiku-4-5` | Мелочь |
| `log_analyst` | `deepseek-v4-flash` | `deepseek-v4-pro` | Строгий JSON |
| `ui` (simple) | `gemini-3-pro` | `claude-haiku-4-5` | UI mid |
| `ui` (power) | `gemini-3.1-pro` | `claude-opus-4-8` | Дизайн/фронт |
| `code` / `doer_logic` (simple) | `gemini-3-pro` | `deepseek-v4-pro` | |
| `code` / `doer_logic` (power) | `claude-opus-4-8` | `deepseek-v4-pro` | |
| `architecture` | `claude-opus-4-8` | `gemini-3.1-pro` | |
| `review` | `gemini-3.1-pro` | `claude-opus-4-8` | |
| `tests` (генерация тестов) | `deepseek-v4-pro` | `gemini-3.1-pro` | |
| `test_executor` | — | — | pytest / npm / ruff |
| `mini_verifier` | `deepseek-v4-flash` | `claude-haiku-4-5` | env `ZEUS_FUSION_MINI_MODEL` |
| `judge_fix` | `claude-opus-4-8` | `gemini-3.1-pro` | Только после RED |

> UI ≠ «всегда Claude». Claude — сильный fallback/код; primary UI в v1 = Gemini class (согласовано с панелями и рыночными сигналами). Таблица версионируется (`role_model_table_v1`).

### 3.4. Потоки

#### A) Малая задача (hot path)

```
Запрос
  → router (size=small, task_kind)
  → doer = primary(task_kind)     # 1 модель
  → [если traceback/логи в контексте] log_analyst → JSON
  → test_executor (smoke, если workspace/Studio; иначе skip с флагом)
  → mini_verifier (chat path)
  → Gate
       GREEN → ответ + Onestack
       RED   → judge_fix (1 escalate) → снова проверки → ответ или Soft-Stop
```

#### B) Большая задача

```
Запрос
  → router (size=large)
  → planner → components[{id, role, files?, acceptance}]
  → параллельно по компонентам:
        doer_logic / doer_ui / … (brief, не полный dump)
  → test_planner → минимальный набор
  → test_executor (скрипт)
  → log_analyst (хвост логов)
  → Gate
       GREEN → judge (лёгкий синтез) → ответ
       RED   → judge_fix → цикл ≤ max_escalate (2)
```

#### C) Studio / publish (cold path, позже)

Finding SM (`CONFIRMED → … → RESOLVED`) и human gate — **только** здесь, не в каждом Cursor-completion.

### 3.5. Gate — когда проверка провалилась

**RED**, если любое из:

| Сигнал | Источник | Критичность |
|--------|----------|-------------|
| `tests_failed` | test_executor exit ≠ 0 | critical |
| `build_failed` | compile/tsc exit ≠ 0 | critical |
| `traceback_detected` | grep по логам | critical |
| `log_report.critical == true` | log_analyst JSON | critical |
| `mini_verifier.passed == false` | verify.py | critical |
| parse/schema degrade отчёта | парсер | critical (escalate-safe) |
| `lint_failed` | по политике проекта | medium (конфиг) |

**GREEN** только если все critical зелёные.

**Нужда усилить** = Gate RED и `escalate_count < max_escalate` (default 2).

Контракт `log_analyst`:

```json
{
  "critical": true,
  "summary": "ImportError in auth.py:42",
  "fix_hint": "add missing import jwt",
  "confidence": 0.86
}
```

Битый JSON / нет `critical` → RED.

---

## 4. Алгоритм роутера (нормативное поведение)

### 4.1. Входы

- Текст user (и короткий контекст: has_code_blocks, has_error_trace, context_chars, short_followup).
- Product mode: `simple` | `power` | `custom`.
- Prefs / `zeus.*` (precedence: request > user prefs > default) — AD-11.

### 4.2. Выходы

```json
{
  "size": "small" | "large",
  "stack": "fast" | "full",
  "task_kind": "light|ui|tests|review|architecture|code|general",
  "confidence": 0.0,
  "roles": ["doer_logic"],
  "routed_by": "policy_classify_v2"
}
```

### 4.3. Правила size

| Условие | size |
|---------|------|
| light / trivial UI / chitchat / короткий follow-up без ошибки | small |
| architecture, multi-file, landing «с нуля», migrate, RED в прошлой попытке | large |
| confidence &lt; 0.6 | large (безопаснее) |
| context_chars &gt; порога (напр. 4000+) и рабочий запрос | large |

Маппинг на Path (не ломая AD-15):

| size + сигналы | Path (serving) |
|----------------|----------------|
| small, без нужды панели | FAST или CASCADE |
| small + нужна проверка качества | CASCADE (cheap → mini → escalate) |
| large, интерактив | RACE или FULL |
| large, максимальное качество | FULL |

### 4.4. Назначение моделей

```
for role in active_roles:
    model = ROLE_MODEL_TABLE[mode][role].primary
    if unhealthy(model): model = fallback
leader = pick_leader(panel_or_roles, task_kind)  # совместимо с AD-16
```

Таблица выносится из хардкода `_TASK_BONUS` в конфиг/модуль `fusion/role_models.py` (единый источник правды). `_TASK_BONUS` может остаться адаптером на переходный период.

---

## 5. Объём работ по этапам

### Этап 0 — Документ и контракты (этот файл) ✅

- Зафиксировать роли, таблицу моделей, Gate, AS-IS/TO-BE.

### Этап 1 — Role Model Table + Router size (P0)

**Сделать:**
1. Модуль `backend/app/fusion/role_models.py`:
   - `ROLE_MODEL_TABLE_V1`
   - `resolve_model(role, mode, unhealthy=…)`
   - версия id в Onestack (`role_table=v1`)
2. Расширить classifier output полем `size` (или выводить из правил).
3. Прокинуть Onestack: `task_kind`, `size`, `roles[]`, `models_by_role{}`.
4. Тесты: таблица резолва; ui→gemini; light→flash; logs role→flash.

**Не делать:** decompose на 6 агентов, finding SM.

**Критерии приёмки:**
- [ ] Для `task_kind=light` в simple primary doer = `deepseek-v4-flash`
- [ ] Для `task_kind=ui` в power leader/ui-role = `gemini-3.1-pro` (если в панели)
- [ ] Onestack содержит `role_table` и `models_by_role`
- [ ] Sticky/Path инварианты не нарушены (тесты epic)

### Этап 2 — Log Analyst (P0)

**Сделать:**
1. `fusion/log_analyst.py`: вызов primary log model, парсер JSON, degrade→RED.
2. Триггеры вызова: наличие traceback/error в контексте **или** RED от mini_verifier **или** RED от test_executor.
3. Brief: только хвост логов + goal + список файлов (не весь репо).
4. Биллинг ветки `role=log_analyst` в FusionResult.branches.
5. `fix_hint` передаётся в `judge_fix` / escalate prompt.

**Критерии приёмки:**
- [ ] На фикстуре с ImportError → `critical=true`, escalate срабатывает
- [ ] Битый JSON → RED, не GREEN
- [ ] Ветка биллится; `cancelled_no_tokens` не тарифицируется

### Этап 3 — Gate унификация (P0)

**Сделать:**
1. `fusion/gate.py`: чистая функция `evaluate_gate(signals) -> Green|Red`.
2. Свести mini_verifier + log_analyst (+ опц. lint flag) в один Gate.
3. `max_escalate` в Settings (default 2).
4. Метрика: `gate_red_total`, `escalate_total`, `gate_green_first`.

**Критерии приёмки:**
- [ ] Unit-тесты на комбинации сигналов
- [ ] Leader не может форсировать GREEN
- [ ] После max_escalate — Soft-Stop / structured partial, не бесконечный цикл

### Этап 4 — Test Planner + Test Executor в Studio (P0/P1)

**Сделать:**
1. `test_executor`: runner команд в workspace (allowlist: `pytest`, `npm test`, `ruff`, …), timeout, capture logs.
2. `test_planner`: правила v1 (без LLM):  
   - small → smoke/lint optional  
   - code touch → unit  
   - large → unit + integration если есть  
3. Связка с Gate: exit ≠ 0 → RED.
4. В чистом Cursor-chat без workspace — executor = `skipped`, Gate не требует tests (только mini+logs).

**Критерии приёмки:**
- [ ] Studio: падающий pytest → RED → escalate
- [ ] Chat без workspace не 500 из‑за отсутствия executor
- [ ] Команды вне allowlist запрещены

### Этап 5 — Planner / Decompose для large (P1)

**Сделать:**
1. `planner` роль: JSON components max 6.
2. Параллельный execute ролей с Brief (AD-4).
3. Синтез через judge только после Gate или при конфликте веток.
4. Eval-фикстуры: large landing → ui+logic; «поправь импорт» → small, 1 модель.

**Критерии приёмки:**
- [ ] small никогда не поднимает ≥4 LLM-ролей
- [ ] large поднимает ≥3 ролей при полном path
- [ ] Сателлиты не получают полный Cursor dump

### Этап 6 — Обучение роутера / таблица (P2)

- Логировать: task_kind, size, escalate_from, gate reason, 👍👎.
- Раз в цикл — пересмотр ROLE_MODEL_TABLE (не online Elo writeback).
- Finding SM + human — только publish/merge Studio (отдельное ТЗ).

---

## 6. Изменения в данных и API

### 6.1. Onestack (ответ клиенту / мета)

Добавить поля (обратно совместимо):

```json
{
  "path": "CASCADE",
  "task_kind": "ui",
  "size": "small",
  "role_table": "v1",
  "roles": ["router", "doer_ui", "mini_verifier"],
  "models_by_role": {
    "doer_ui": "gemini-3.1-pro",
    "mini_verifier": "deepseek-v4-flash"
  },
  "gate": "GREEN",
  "escalate_count": 0,
  "gate_reasons": []
}
```

### 6.2. Usage / branches

Каждая LLM-роль = branch с `role`, `model`, `billable_state`, usage.

### 6.3. Config / env

| Переменная | Default | Смысл |
|------------|---------|-------|
| `ZEUS_FUSION_MINI_MODEL` | `deepseek-v4-flash` | mini_verifier |
| `ZEUS_FUSION_LOG_MODEL` | `deepseek-v4-flash` | log_analyst |
| `ZEUS_FUSION_MAX_ESCALATE` | `2` | лимит кругов |
| `ZEUS_FUSION_ROLE_TABLE` | `v1` | версия таблицы |
| `ZEUS_FUSION_TEST_EXECUTOR` | `0` в chat / `1` в Studio | включение скриптов |

---

## 7. Нефункциональные требования

| ID | Требование |
|----|------------|
| NFR-1 | Router timeout ≤ 2.5s (как сейчас) |
| NFR-2 | Log analyst max_tokens небольшой (≤400), input = хвост логов |
| NFR-3 | small path p95 не хуже текущего FAST более чем на +30% за счёт лишних ролей |
| NFR-4 | Никогда не списывать `cancelled_no_tokens` |
| NFR-5 | Секреты scrub до Policy (AD-17) |
| NFR-6 | Kill-switch → FAST, без decompose |
| NFR-7 | Все новые ветки в FusionResult (AD-14) |

---

## 8. Риски и митигации

| Риск | Митигация |
|------|-----------|
| Роутер ошибся → слабая модель | Gate + escalate (обязательны) |
| 5–6 ролей на мелочи | Жёсткий size=small cap на число LLM-ролей (≤2 + verifier) |
| Test executor опасен на prod host | Allowlist команд, workspace sandbox, только Studio flag |
| Рост $ на verify | Дешёвые flash-модели; не вызывать log_analyst без сигнала ошибки |
| Расхождение с Omni «комбо» | Не делать UI конструктора; таблица внутри |

---

## 9. Критерии готовности продукта (Definition of Done v1)

v1 Role Routing считается готовым, когда:

1. Таблица Role→Model в коде/конфиге, версия в Onestack.
2. Малая задача: 1 doer + mini_verifier; escalate ≤2 при RED.
3. Log analyst вызывается на traceback/RED и влияет на Gate.
4. Studio: test_executor падает → RED → escalate.
5. Chat без workspace не ломается.
6. Прогнан набор регрессий Fusion (epic tests) + новые unit на gate/role_models/log_analyst.
7. Документация для саппорта: «какие модели на какие роли» = этот файл §3.3.

---

## 10. Вне scope этого ТЗ

- CryptoBot / карточные платежи  
- Multi-upstream A6 failover (отдельное ТЗ на маржу)  
- Finding SM + human decision на каждый запрос  
- Marketplace / Combo Studio UI  
- Online Elo writeback в роутер  
- Замена Path-таксономии на «9 этапов друга» как serving model  

---

## 11. Трассировка к уже принятым AD

| AD | Как соблюдаем |
|----|----------------|
| AD-1 Gateway+Path | Роли живут внутри Execute; Edge не ветвится |
| AD-3 Policy order | size/task_kind в Policy; escalate только в Execute |
| AD-4 Brief | сателлиты/log_analyst на brief |
| AD-5 Stop authority | только Gate/verifiers/τ |
| AD-7 Sticky | не хранит stage pipeline |
| AD-8/14 Billing | ветки ролей в FusionResult |
| AD-15 Path enum | size маппится на Path, не заменяет Path |
| AD-16 Leader | один mutator pick_leader / escalate end |

---

## 12. Порядок внедрения (рекомендуемый спринт)

| День / спринт | Этап | Результат |
|---------------|------|-----------|
| S1 | Этап 1 + 3 | Таблица ролей + единый Gate |
| S1–S2 | Этап 2 | Log Analyst в CASCADE/RED |
| S2 | Этап 4 | Test Executor в Studio |
| S3 | Этап 5 | Decompose large |
| Later | Этап 6 | Подкрутка таблицы по метрикам |

---

## 13. Формулировка для команды (user stories)

1. **Как** пользователь Cursor, **я хочу** писать в `zeus/fusion` без выбора модели, **чтобы** система сама ставила дешёвую модель на мелочь и сильную на архитектуру.
2. **Как** пользователь, **я хочу** чтобы при ошибках в логах дешёвая модель разобрала traceback, **чтобы** дорогая модель чинила точечно, а не «думала с нуля».
3. **Как** продукт, **мы хотим** Gate на скриптах и JSON, **чтобы** не принимать «я молодец» от кодера.
4. **Как** Studio-пользователь, **я хочу** падение pytest → автоэскалацию, **чтобы** не ловить красные тесты глазами.

---

**Владелец продукта:** утверждает §3.3 (таблица моделей) и max_escalate.  
**Владелец инженерии:** этапы 1–5, тесты, Onestack.  
**Следующий шаг после аппрува ТЗ:** начать Этап 1 (`role_models.py` + Onestack поля).
