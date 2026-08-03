# ZeusCode — план починки мозга

Статус: draft · Jul 2026  
Продукт в речи: **ZeusCode** (не «Fusion»). Руки = Cursor/omp. Мозг+касса = наш API.

---

## 0. Честно про роутинг сегодня

| Вопрос | Ответ |
|--------|--------|
| Насколько «умный»? | **Средне.** Это правила + regex + длина текста, не отдельная «думающая» модель. LLM-классификатор **выключен** (скорость). |
| Что ловит хорошо | Привет / короткое / «поменяй цвет» → 1 модель. «Архитектура / рефактор / лендинг» → полный стек. |
| Где ошибается | Короткая, но жёсткая задача («почини race в auth») может уйти в 1 модель. Длинный текст без тяжёлых слов — тоже часто в дешёвый путь. |
| Страховка | CASCADE: дешёвая → mini-проверка → если слабо, поднимаем сильнее. Kill → всегда 1 дешёвая. |
| На всех режимах? | **Да:** simple / power / custom. Отличается **какие** модели в стеке и clamp на simple. |

Цель улучшения роутинга (после распила): короткие hard-сигналы (auth/race/security/traceback) → не FAST; опционально LLM classify только на borderline.

---

## 1. Как работают режимы (простыми словами)

### Power (по умолчанию)
Сейчас стек **ровно 3**, не 5–7:
`claude-opus-4-8` · `gpt-5.5` · `deepseek-v4-pro`

- Мелочь → 1 из них  
- Обычное → CASCADE (1 + проверка, при нужде escalate)  
- Тяжёлое → FULL (до 3 сразу + verify/judge)

### Simple
Тот же умный 1↔N, но **дешёвый** стек:
`deepseek-v4-flash` · `gemini-3-pro` · `claude-haiku-4-5`

И clamp: даже «тяжёлое» **не** уходит в RACE/FULL → остаётся **CASCADE внутри cheap** (чтобы не жечь деньги). Escalate = следующая модель из cheap-стека, не Opus.

### Custom
Тот же роутинг 1↔N, модели выбирает юзер.  
**Сейчас лимит = 3** (`_MAX_PANEL = 3`) — как у power.  
**Цель:** custom max = power stack size (когда поднимем power до 5–7).

---

## 2. Power = фиксированный экипаж из 5 моделей (без CASCADE escalate)

**Решение (2026-07-27):** убрать CASCADE «дешёвая → mini → сильнее» на обычных задачах.
Вместо эскалации — **фиксированные роли → фиксированные модели**.
Custom max = тот же пул из 5.

Цены ₽/1M (Polza, каталог на момент плана):

| Модель | in / out |
|--------|----------|
| deepseek-v4-flash | 19 / 39 |
| gemini-2.5-flash | 12 / 104 |
| deepseek-v4-pro | 76 / 302 |
| gemini-3.1-pro | 69 / 483 |
| gpt-5.4 | 98 / 781 |
| claude-opus-4-8 | 138 / 138 |
| gpt-5.5 | 510 / 3060 ← **не брать в power** (дорого) |

### Роли power (фиксировано)

| Роль | Модель | Должность (что делает) | Токены |
|------|--------|------------------------|--------|
| **Architect** | `claude-opus-4-8` | Короткий Brief: куски, файлы, acceptance. Не пишет весь код. | Мало out |
| **Test Author** | `gpt-5.4` | Контрактные тесты на куски (не opus — в 5× дешевле 5.5). | Средне |
| **Doer logic** | `deepseek-v4-pro` | Backend/баги/логика — основной объём кода. | Много, но дёшево |
| **Doer UI** | `gemini-3.1-pro` | Вёрстка/лендинг/UI. | Много, дешевле Opus |
| **Mini / Gate** | `deepseek-v4-flash` | `good_enough` JSON. Не пишет код. | Очень дёшево |
| **Judge fix** *(только RED)* | `claude-opus-4-8` | Одна попытка починить. Та же модель что Architect — 5 уникальных ID. | Редко |

Пул power-5:  
`opus-4-8 · gpt-5.4 · deepseek-v4-pro · gemini-3.1-pro · deepseek-v4-flash`

### Когда кого звать (после live-bench 2026-07-27)

| Задача | Кто | Не делать |
|--------|-----|-----------|
| Мелочь | flash + mini | FULL / clarifier / UI Crew |
| Код / фикс | deepseek-pro + mini | escalate на Opus |
| Обычный UI / hero / цвет | gemini-3.1 + mini | UI Crew (critics+web) |
| Лендинг с нуля | UI Crew (дорого, ок) | — |
| Архитектура / review (конкретно) | Opus brief → gpt-5.4 tests → doers → mini | auto-clarifier |
| «сделай фичу» без деталей | clarifier спросит | сразу FULL-5 |

**Bench lessons:** clarifier на ясном ТЗ — зло; UI Crew на «цвет кнопки» — 250s/$$$ .
**Запрещено в power:** CASCADE ladder. RED → один Judge → Soft-Stop.

Код (Sprint C):
- `_POWER_PANEL` / `roles._PRESET_STACKS` / `_ROLE_MODE_TABLE` → таблица выше  
- `execute_cascade` escalate → выкл для power (или path только FAST/fixed-pipeline)  
- `_MAX_PANEL = 5`, custom = 5  
- убрать `gpt-5.5` из power preset

---

## 3. Удалить Studio (второй мозг)

Studio = вкладка «студия» в `/app` + `orchestrate.py`, не весь кабинет.

Убрать:
- `orchestrate.py`, `ultra.py`
- routers: `projects`, `studio_fs`, (github если только для студии)
- studio-* / ultra-mode из каталога и `chat.py`
- UI вкладки projects / studio shell в `app.js` / `app.html`
- связанный FS/git/preview/skills bake (по списку файлов)

Оставить:
- кабинет: keys, billing, models, usage, ZeusCode prefs  
- TG Mini App  
- `/v1` ZeusCode + solo модели  
- publish, если нужен ZeusCode HTML gate

---

## 4. Распил огромного файла мозга (`_monolith.py` ~3.2k)

Поведение для юзера **не меняется**. Только раскладка кода.

| Новый модуль | Что забирает |
|--------------|--------------|
| `zeus_route.py` (или `fusion/route.py`) | classify, resolve_routing, product mode, panel pick |
| `zeus_execute.py` | вызов panel CASCADE/RACE/FULL, clarifier hook |
| `zeus_pack.py` | build result, onestack meta, scrub |
| `_monolith.py` → тонкий `iter_zeus` / facade | склеивает шаги, реэкспорт для совместимости |

Порядок:
1. Вынести чистые функции без смены сигнатур (тесты зелёные)  
2. Перенести `iter_fusion` тело по шагам  
3. Обновить `__init__.py` реэкспорты  
4. Позже: публичный rename Fusion→ZeusCode в API meta (отдельный спринт)

---

## 5. Порядок работ (спринты)

| Sprint | Что | Done when |
|--------|-----|-----------|
| **A** | Правило имени ZeusCode + этот план | alwaysApply rule + doc |
| **B** | Вырезать Studio | нет `/projects` complete, нет вкладки студии, `/v1` без studio-* |
| **B.1** ✅ | API+UI cut | routers projects/studio_fs/github сняты; studio-* → 410; вкладка студии скрыта |
| **C** ✅ | power-5 fixed crew + no CASCADE ladder | `bench_zeuscode_power.py` (real bench) + custom max=5 |
| **D** | Распил `_monolith` → route/execute/pack | LOC monolith < ~800; suite green |
| **E** | Роутинг hard-signals | короткие security/race/traceback не уходят в FAST зря |
| **F** | (опц.) rename пакета fusion→zeuscode | import path + docs |

Не трогать в A–E: verify, kill, billing, роли смысла.

---

## 6. Критерии «готово»

- [ ] В речи и UI: ZeusCode, не Fusion  
- [ ] Studio path мёртв  
- [ ] custom лимит = power лимит (≥5)  
- [ ] Мозг разбит на route / execute / pack  
- [ ] Типичный turn: 1–2 LLM; тяжёлый: стек; simple: cheap CASCADE  
- [ ] Тесты fusion/zeus зелёные  

---

## 7. Открытый вопрос к тебе

Power сейчас **3**. Поднимаем до **5** (таблица выше) или сразу до **7**?  
От ответа зависит Sprint C.
