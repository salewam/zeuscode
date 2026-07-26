# Addendum — Role Routing + Verify/Escalate

Технический слой. Источник: `docs/TZ_ZEUS_ROLE_ROUTING_VERIFY.md` + решения владельца 2026-07-24/25.  
Нормативный канон пайплайна: **§M**; DeepSeek: **§N**.

## A. AS-IS

Gateway, публичный id **`zeuscode`** (legacy `zeus/fusion`), TG режимы simple/power/custom, панели, classifier, pick_leader, Paths (внутр.), Mini-Verifier, Brief, FusionResult, `model_power.power_score`.

## B. Продуктовые режимы TG (не трогать UX)

| id | UI | Стек |
|----|-----|------|
| simple | Пользовательский | deepseek-v4-flash · gemini-3-pro · claude-haiku-4-5 |
| power | Продвинутый | claude-opus-4-8 · deepseek-v4-pro · gemini-3.1-pro |
| custom | Набор | ≤3 выбранных юзером — **не подменяем** |

Доработка = Roles/Gate/Soft-Stop/Pipeline v1 **внутри** стеков. **Новых кнопок Path нет.**

## C. Двухступенчатая таблица (канон)

### C1. task_kind → role

| task_kind | default_doer_role |
|-----------|-------------------|
| light, code, general, architecture, review, tests | doer_logic |
| ui | doer_ui |

По триггеру: `log_analyst` (логи), `mini_verifier`; large+2nd: `architect`, `test_author`; escalate/conflict: `judge_fix`.

### C2. role × mode → model (+ score)

| role | simple primary / fallback | power primary / fallback | score gate |
|------|---------------------------|--------------------------|------------|
| router | flash / gemini-2.5-flash | flash / gemini-2.5-flash | — |
| architect | max≥950 in stack / skip | opus-4-8 / skip if none ≥950 | **≥950** |
| test_author | max≥950 / skip | opus-4-8 / skip | **≥950** |
| doer_logic | gemini-3-pro / flash | **opus-4-8** / v4-pro | power: топ-doer OK (1Б); Pipeline куски — mid предпочтительно |
| doer_ui | haiku / gemini-3-pro | gemini-3.1-pro / opus-4-8 | mid ok |
| log_analyst | **deepseek-v4-flash** / v4-pro | **deepseek-v4-pro** / flash | cheap |
| mini_verifier | flash / haiku | flash / haiku | cheap |
| judge_fix | max power_score(stack) | max power_score(stack) | prefer ≥950 |
| test_executor | script | script | n/a |

custom: только выбранные юзером; куратор = max power_score(выбранных). Architect/test_author полного Pipeline v1 — только если куратор (или кто-то в наборе) ≥950; иначе §E решение A (`fallback_single`). Не автодобавлять модели.

### C3. Ориентиры power_score (snapshot)

| Score | Примеры | Типичные Roles |
|------:|---------|----------------|
| ≥950 | opus-4-8, gpt-5.5, gpt-5.6-sol | architect, test_author, conflict merge, escalate |
| 850–949 | gemini-3.1-pro, gpt-5.4, sonnet-класс | doer_ui / doer_logic |
| 750–849 | deepseek-v4-pro, mid | doer_logic mid, log_analyst power |
| ≤749 | v4-flash, haiku, small flash | router, mini_verifier, log_analyst simple |

`TEST_AUTHOR_MIN` default = **950** (`model_power.py`).

## D. Soft-Stop selection (decided)

1. Кандидаты с непустым текстом и billable usage.  
2. Победитель = max `power_score(model)`.  
3. Tie → последний ответ этой модели.  
4. В текст — короткая строка «проверка не пройдена».  
5. Onestack: gate=RED, soft_stop=true, soft_stop_model, escalate_count.

## E. Pipeline аварии + решение A (куратор)

| Сбой / условие | Действие |
|----------------|----------|
| Architect fail (timeout / bad JSON / 0 components) | `pipeline=fallback_single`: куратор = max power_score(stack) + Mini + Log(по триггеру) + escalate≤2 |
| Один Doer fail | escalate только failed; keep ok |
| Всё RED после escalate | Soft-Stop §D |
| **Нет модели ≥950 в стеке** | **A+2А:** Pipeline v1 off. Куратор = max power_score(выбор юзера). Пишет **полный ответ сразу** (без отдельного Brief). Затем Mini → Log только если модель log есть в стеке (5Б) → Escalate≤2 при RED. Mid-параллель запрещена. Модели не докидываем. |

Куратор всегда из выбора пользователя / пресета — не подсунутый с нашей стороны.

## F. Gate signals

| Signal | Hot | Studio |
|--------|-----|--------|
| traceback / log.critical / mini / parse | critical | critical |
| tests_failed (A or B check) | N/A if skipped | critical if run |
| build_failed | always N/A | critical if probe run |
| lint | not critical | not critical |

## G. FR-16 backlog (не MVP)

Клиенты: unknown, OpenCode, Cline, Kilo, Codex, Claude Code, OmniRoute, Continue, Goose, Crush, OpenHands, Windsurf, Zed, LibreChat, Open WebUI, Aider, openai_any, Cursor, Roo legacy.  
Прогон руками — отдельный спринт.

## G2. FR-17 — TG connect docs

Источник: `docs/CLIENT_API_CONNECT_RESEARCH.md`.

| Канон | Значение |
|-------|----------|
| Base URL | `https://zeuscode.ru/v1` |
| Key | `zeus_…` |
| Model | `zeuscode` |
| Mode UX | только TG «Модели» |

Исключения: Claude base без `/v1`; Aider/OpenHands `openai/zeuscode`; OpenCode `zeuscode/zeuscode`; Cursor → Cline/Kilo.  
Код: `tg-platforms.js`, generators `tg-miniapp.js` / `app.js`. Запрет UI: `zeuscode-simple|power|custom`.

## H. Phases

1. role_models + score gates + Onestack `pipeline`  
2. DeepSeek log_analyst + Gate  
3. Soft-Stop power_score  
4. **Pipeline v1** (FR-18) + fallback_single  
5. Studio test executor Layer A  
6. FR-17 connect docs (уже начато)  
7. Later: FR-16 matrix  

## I. Spine

Конфликт с AD → Spine. Path внутренний; продукт = simple/power/custom. **Новых кнопок нет.**

## J. Verify layers — score gate

| Layer | Что | Кто | Когда |
|-------|-----|-----|-------|
| A | Существующие тесты allowlist | Test Executor script | Studio/workspace |
| B | Контрактные тесты на куски | Test Author ≥950 | Pipeline v1 + есть ≥950 |
| C | Log JSON | **DeepSeek** | traceback/error only |
| D | Mini-Verifier | cheap | hot Gate |

Custom без ≥950 → B skipped.

## K. Path lattice (без UX)

| Условие | Serving Path | Заметки |
|---------|--------------|---------|
| kill-switch | FAST | без Pipeline v1 |
| mode=simple | FAST / cheap CASCADE | без Pipeline v1 |
| power/custom + small | CASCADE, 1–2 Doer + verify | Pipeline v1 **OFF** |
| power/custom + large + 2nd + есть ≥950 | FULL / Pipeline v1 §M | ≤3 куска; не RACE v1 |
| power/custom + large + 2nd + нет ≥950 | FAST-ish / fallback_single | куратор = max score стека (§E A) |
| power/custom + large + **нет** 2nd | CASCADE | `pipeline=small`; Pipeline v1 OFF |
| forced alias | как в коде | не новый UX |

## L. Merge (решение 4Б — file-aware)

1. Default: **file-aware** сборка по Brief (пути файлов / патчи / порядок применения) — не prose-concat.  
2. Конфликт файла / сломанный стык API → один вызов сильной (≥950 если есть, иначе куратор).  
3. Без конфликта лишний топ-merge не зовём.  
4. `max_escalate=2` **global** (после test-fix цикла — см. FR-7 / 3А).

## M. Pipeline v1 (owner locked) — нормативный канон

**Цель:** test-first качество без 8–12 вызовов на каждую фразу. Кнопок нет.

### Триггер полного Pipeline v1
`size=large` **и** второй сигнал **и** mode ∈ {power, custom} **и** в стеке есть модель ≥950.  
Иначе: small path; или large без ≥950 → **§E решение A** (куратор / fallback_single). Simple — Pipeline v1 никогда.

### Шаги (large + есть ≥950)

| # | Роль | Score | Вход | Выход |
|---|------|------:|------|-------|
| 1 | Architect | ≥950 | задача | Brief ≤3 куска + API/файлы + acceptance |
| 2 | Test Author | ≥950 | Brief | контрактные тесты на кусок |
| 3 | Doers || mid | Brief + свой кусок + свои тесты; **не** чужой код | код куска |
| 4 | Test check | ≥950 | тесты + результаты | GREEN/RED + кому fix (**один** раз) |
| 5 | Fix doers | mid | только RED | допил (1 цикл; escalate отдельно — 3А) |
| 6 | Merge | file-aware; сильная если конфликт (4Б) | куски | единый ответ |
| 7 | Log Analyst | DeepSeek если в стеке (5Б) | FR-5 trigger | JSON → Gate / escalate |

**Лимиты:** один RED→fix→recheck; затем Escalate≤2 global (3А).  
**Нет ≥950:** §E A+2А — куратор полный ответ один; без автодобавления.

**Бюджет вызовов:** small 2–4 · fallback_single ~2–4 · large v1 ~6–8 · потолок ~8–9.

## N. DeepSeek Log Analyst — контракт пользы

| | |
|--|--|
| **Задача** | Разбор traceback/error — не надзор за Doers |
| **Когда** | В стеке есть log-модель (simple/power=DeepSeek; custom=DeepSeek среди ≤3) **и** traceback / Exception / error / RED+runtime |
| **Когда НЕ** | Нет DeepSeek/log в выбранном стеке (**5Б** skip); чистый UI; chitchat; GREEN без логов |
| **Вход** | goal + хвост логов + файлы + short last_assistant |
| **Выход** | `{critical, summary, fix_hint, confidence}` |
| **Кому** | Gate (`critical`→RED); judge_fix (`fix_hint`); опц. строка юзеру |
| **Кому НЕ** | Не менеджерит doers; не пишет тесты; не ломает Brief |
| **Модель** | deepseek-v4-flash (simple) / deepseek-v4-pro (power) |
| **Польза** | Дешёво ловит «тихо упало»; не жжёт топ на логи |

Битый JSON / нет `critical` → RED (safe degrade).
