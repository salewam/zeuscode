# Клиенты ZeusCode — список на тестирование

Источник: TG-бот (`frontend/tg-platforms.js`, `ZC_PLATFORM_ORDER`).  
Дата: 2026-07-26.

---

## Что тестируем (смысл)

ZeusCode даёт **мозг по API**. Клиент на компе даёт **руки** (файлы, терминал, tools).

| Где | Что проверяем |
|-----|----------------|
| **TG Mini App** | ключ, Base URL, режим «Модели» (Пользовательский / Продвинутый / Набор), копирование, онбординг, rotate ключа |
| **Клиент** | подключение, чат, stream, tools, файлы, консоль, git, спец-протокол клиента |
| **Логи Zeus** | нет 401/502 лавиной, нет `Tool type or function is null`, модель и запрос видны |

Не путаем:
- режим нейронок выбирается в **миниаппе**, в клиенте почти всегда model = `zeuscode` (или id соло-модели);
- Studio / скиллы сайта — **не** этот прогон;
- «нет доступа к консоли» = сломались tools у клиента, не «консоль Zeus».

### Что люди уже ломали (обязательно повторить)

| Функция | Кто трогал | Зачем в чеклисте |
|---------|------------|------------------|
| Ключ + URL из бота | почти все | блок 1 |
| Режимы Модели (power/simple/custom) | многие | блок 2 |
| Связка `zeuscode` / fusion | основной трафик | 2.1–2.3 |
| Соло-модели (gemini, gpt-5.x, fable, grok…) | Глеб, RootExploit… | 2.4–2.5 |
| Tools / agent loop | Глеб Cline/Codex | блок 5 |
| Терминал + `git pull` | Глеб | блок 7 |
| Онбординг клиента в боте | OpenCode/Codex/Cline клики | 1.5, 12 |

---

## Клиенты: список + что проверяем у каждого

Легенда блоков: **1** подключение · **2** модели · **3** чат · **4** stream · **5** tools · **6** файлы · **7** shell/git · **8** спец · **9** биллинг · **10** устойчивость · **11** логи · **12** миниапп (раз на lab)

| # | Название | id | Тип | Блоки | Smoke | Полный | Статус | Дата | Заметки |
|---|----------|-----|-----|-------|-------|--------|--------|------|---------|
| 1 | OpenCode | `opencode` | CLI агент | 1–7, 9–11 | ☐ | ☐ | installed | 2026-07-26 | v1.18.5 на сервере · ключ `zeus_jzWQphq…` · playground готов · API smoke OK |
| 2 | Codex | `codex` | CLI · responses | 1–7, **8.1**, 9–11 | ☐ | ☐ | pending | | очередь #2 · болел у Глеба |
| 3 | Cline | `cline` | VS Code агент | 1–7, 9–11 | ☐ | ☐ | pending | | очередь #3 · болел у Глеба |
| 4 | Kilo Code | `kilo` | VS Code / JB | 1–7, 9–11 | ☐ | ☐ | pending | | |
| 5 | Claude Code | `claude` | CLI · Anthropic | 1–7, **8.2**, 9–11 | ☐ | ☐ | pending | | base **без** `/v1` |
| 6 | Continue | `continue` | VS Code чат/агент | 1–7, 9–11 | ☐ | ☐ | pending | | |
| 7 | Aider | `aider` | CLI git | 1–7, **8.5**, 9–11 | ☐ | ☐ | pending | | model `openai/zeuscode` |
| 8 | OmniRoute | `omniroute` | gateway | 1–4, **8.3**, 10–11 | ☐ | ☐ | pending | | |
| 9 | Goose | `goose` | CLI / desktop | 1–7, 9–11 | ☐ | ☐ | pending | | |
| 10 | Crush | `crush` | CLI TUI | 1–7, 9–11 | ☐ | ☐ | pending | | |
| 11 | OpenHands | `openhands` | CLI / UI | 1–7, 9–11 | ☐ | ☐ | pending | | |
| 12 | Cursor | `cursor` | IDE | 1–7, **8.4**, 9–11 | ☐ | ☐ | pending | | model именно `zeuscode` |
| 13 | Zed | `zed` | IDE | 1–7, 9–11 | ☐ | ☐ | pending | | |
| 14 | Windsurf | `windsurf` | IDE → Cline/Kilo | 1–7, 9–11 | ☐ | ☐ | pending | | по сути повтор Cline/Kilo |
| 15 | LibreChat | `librechat` | web чат | **1–4, 10–11** | ☐ | ☐ | pending | | без shell/files |
| 16 | Open WebUI | `openwebui` | web чат | **1–4, 10–11** | ☐ | ☐ | pending | | без shell/files |

### Не тестируем как отдельные клиенты

| Название | id | Почему |
|----------|-----|--------|
| Не знаю где | `unknown` | Онбординг → Continue |
| Любой OpenAI-compatible | `openai_any` | Универсальный гайд, не программа |
| Roo Code (legacy) | `roo` | Закрыт · лучше Kilo / Cline |

---

## Очередь прогона

1. OpenCode  
2. Codex  
3. Cline  
4. Kilo Code  
5. Claude Code  
6. Continue  
7. Aider  
8. OmniRoute  
9. Goose  
10. Crush  
11. OpenHands  
12. Cursor  
13. Zed  
14. Windsurf  
15. LibreChat  
16. Open WebUI  

Приоритет по живым жалобам/трафику: **Codex → Cline → OpenCode → Claude Code → Cursor**, остальное по списку.

---

## Откуда гоняем

```
TG Mini App     → ключ zeus_… + режим «Модели»
      ↓
Клиент          → Base URL + ключ + model (zeuscode или соло)
      ↓
Playground      → /opt/zeus-client-lab/playground/ (git + файлы)
      ↓
Задачи чеклиста → см. блоки ниже
      ↓
Логи Zeus       → product_usage_events + nginx UA
      ↓
Эта таблица     → Smoke/Полный ☐ + Статус + Заметки
```

Playground минимум: `README.md`, `src/hello.py`, файл с кириллицей в имени, git init + remote для pull.

---

## Окружение на сервере (что ставить)

Прод сейчас: **Ubuntu 24.04**, Node 20, Python 3.12, git.  
**Нет** GUI/desktop, **нет** Docker, RAM ~**3.7 GB** (уже почти забит Zeus) — тяжёлые IDE на этот же бокс опасно.

Рекомендация: lab-каталог на этом сервере для **CLI**, а GUI/IDE — отдельная машина (Windows/Mac ноут или VPS с ≥8 GB RAM).

### A. База lab (на Linux-сервере) — обязательно

```bash
sudo mkdir -p /opt/zeus-client-lab/{playground,reports,bin,configs}
sudo apt-get update
sudo apt-get install -y git curl ca-certificates build-essential \
  python3-venv python3-pip jq ripgrep unzip
# Node 20 уже есть — ок для OpenCode / части CLI
```

+ отдельный smoke-ключ Zeus с маленьким бюджетом  
+ playground git-репо  
+ в `~/.bashrc` lab-юзера: `export ZEUS_BASE=https://zeuscode.ru/v1` и путь к ключу (не в git)

### B. CLI-клиенты — ставятся на этот Linux

| Клиент | Как поставить (ориентир) | Нужно сверх базы |
|--------|--------------------------|------------------|
| **OpenCode** | официальный install / npm | Node 20+ |
| **Codex CLI** | `npm i -g @openai/codex` или бинарь OpenAI | Node; config `wire_api=responses` |
| **Claude Code** | официальный `claude` CLI | Node; `ANTHROPIC_BASE_URL` без `/v1` |
| **Aider** | `pipx install aider-chat` | pipx / venv |
| **Goose** | официальный install script | обычно свой бинарь |
| **Crush** | `go install` или релиз Charm | Go **или** готовый binary |
| **OmniRoute** | их install / docker-compose | лучше **отдельный** хост или Docker; на 3.7GB рядом с Zeus тесно |

Не ставить всё сразу — по очереди клиента из списка, после PASS можно не держать демон.

### C. VS Code-агенты (Cline / Kilo / Continue) — code-server

На **этом** сервере с 3.7GB RAM — только если освободить память или взять другой VPS ≥8GB:

```bash
# code-server (браузерный VS Code)
curl -fsSL https://code-server.dev/install.sh | sh
# затем в UI: Extensions → Cline / Kilo Code / Continue
# Base URL + zeus_ ключ по гайду бота
```

Альтернатива проще: тот же Cline/Continue на **твоём ноуте/Windows**, ключ на `zeuscode.ru` — результат тот же для протокола.

### D. Тяжёлые IDE / web — НЕ на прод 3.7GB

| Клиент | Где крутить | Окружение |
|--------|-------------|-----------|
| **Cursor** | desktop Windows/Mac | установка Cursor |
| **Zed** | Linux desktop / Mac | пакет Zed |
| **Windsurf** | desktop | Windsurf + Cline/Kilo внутри |
| **LibreChat** | VPS с Docker, ≥8GB | Docker Compose |
| **Open WebUI** | VPS с Docker | Docker |
| **OpenHands** | VPS с Docker | Docker |

На текущем прод-сервере их **не ставим** рядом с Zeus — риск OOM.

### E. Карта «клиент → машина»

| # | Клиент | Машина |
|---|--------|--------|
| 1 | OpenCode | Linux lab (этот сервер) |
| 2 | Codex | Linux lab |
| 3 | Cline | code-server (отдельный VPS) **или** Windows/ноут |
| 4 | Kilo | то же |
| 5 | Claude Code | Linux lab |
| 6 | Continue | code-server / ноут |
| 7 | Aider | Linux lab |
| 8 | OmniRoute | отдельный хост / Docker |
| 9 | Goose | Linux lab |
| 10 | Crush | Linux lab |
| 11 | OpenHands | Docker-хост ≥8GB |
| 12 | Cursor | desktop |
| 13 | Zed | desktop |
| 14 | Windsurf | desktop |
| 15 | LibreChat | Docker-хост |
| 16 | Open WebUI | Docker-хост |
| — | Миниапп блок 12 | браузер / Telegram |

### F. Минимальный старт (чтобы начать завтра)

На текущем сервере хватит:

1. `/opt/zeus-client-lab` + playground  
2. OpenCode  
3. Codex CLI  
4. Claude Code  
5. Aider (`pipx`)  

Cline/Cursor — с твоей Windows-машины (как у Глеба), без установки IDE на прод.

---

## Полный чеклист (что проверяем)

### 1. Подключение — все клиенты

| # | Что проверяем | Ожидание | Какой баг ловим |
|---|---------------|----------|-----------------|
| 1.1 | Base URL из гайда бота (`…/v1`; Claude — **без** `/v1`) | чат живой | двойной `/v1/v1`, кривой URL |
| 1.2 | Ключ `zeus_…` | HTTP 200 | 401 auth |
| 1.3 | Неверный ключ | понятный 401 | 500 вместо 401 |
| 1.4 | `GET /v1/models` (если клиент тянет) | есть `zeuscode` + каталог | пустой/битый список |
| 1.5 | Copy URL/ключ из miniapp → вставка | совпадает с гайдом | рассинхрон UI и доки |

### 2. Модели и режимы miniapp — все

| # | Что проверяем | Ожидание | Какой баг ловим |
|---|---------------|----------|-----------------|
| 2.1 | TG **Пользовательский** → client model=`zeuscode` | ответ, в логах fusion | pref не подхватился |
| 2.2 | TG **Продвинутый** → `zeuscode` | другой стек/лидер | pref игнор |
| 2.3 | TG **Набор** (2–3 модели) → `zeuscode` | custom panel жив | custom сломан |
| 2.4 | Соло `gemini-2.5-flash` | короткий OK | solo routing |
| 2.5 | Соло тяжёлая (`claude-opus-4-8` / `gpt-5.6-terra`) | OK или явная ошибка Кие | тихий 502 |
| 2.6 | Модель `no-such-model` | 4xx | crash 500 |
| 2.7 | Регистр имени модели | каноникализация | case bugs |

### 3. Простой чат — все

| # | Что проверяем | Ожидание | Какой баг ловим |
|---|---------------|----------|-----------------|
| 3.1 | «Ответь одним словом: OK» | `OK` | базовый chat |
| 3.2 | Кириллица + эмодзи | нормальный ответ | encoding |
| 3.3 | Диалог 3+ реплики | контекст держится | history trim |
| 3.4 | Пустое / пробел | отказ или мягкая ошибка | crash |
| 3.5 | Очень длинный промпт (50–100KB) | ответ или явный context error | OOM / молчаливый 502 |

### 4. Streaming — кто умеет

| # | Что проверяем | Ожидание | Какой баг ловим |
|---|---------------|----------|-----------------|
| 4.1 | Stream ON, длинный ответ | токены потоком | SSE / nginx buffer |
| 4.2 | Стоп mid-stream | клиент жив, следующий запрос ок | keep-alive half-close |
| 4.3 | Stream OFF | цельный ответ | non-stream path |

### 5. Tools / agent loop — только агенты (не LibreChat/WebUI)

| # | Что проверяем | Ожидание | Какой баг ловим |
|---|---------------|----------|-----------------|
| 5.1 | Прочитай файл / вызови tool | tool → результат → финал | **Tool type null** |
| 5.2 | Read + shell подряд | оба ок | tool_calls array |
| 5.3 | tool_choice / forced tool | не 502 | normalize tool_choice |
| 5.4 | Ход с `role=tool` в истории | 200 | sanitize history |
| 5.5 | Parallel tool_calls (если шлёт) | не ломает Кие | parallel tools |
| 5.6 | Битая schema tools от клиента | мы чиним → 200 | regression |

### 6. Файлы — только агенты

| # | Что проверяем | Ожидание | Какой баг ловим |
|---|---------------|----------|-----------------|
| 6.1 | Прочитать `README.md` | цитата с диска | read tool |
| 6.2 | Создать `notes/test.txt` | файл есть | write |
| 6.3 | Правка файла | diff применён | edit / apply_patch |
| 6.4 | Кириллица в имени/теле | ок | path encoding |
| 6.5 | Картинка/бинарник (если умеет) | по доке клиента | multimodal |

### 7. Консоль / git — только агенты (жалобы юзеров)

| # | Что проверяем | Ожидание | Какой баг ловим |
|---|---------------|----------|-----------------|
| 7.1 | `pwd` + `ls` через tool | реальный вывод, не «нет доступа» | shell / tools fail |
| 7.2 | `echo hello > out.txt` | файл на диске | shell write |
| 7.3 | `git status` | статус репо | git |
| 7.4 | `git pull` / fetch | успех или понятная сеть-ошибка | кейс Глеба |
| 7.5 | Команда с exit≠0 | агент видит stderr/code | error handling |
| 7.6 | `sleep 15` | не обрыв по таймауту | timeouts |

### 8. Спец-протоколы — по клиенту

| # | Клиент | Что проверяем | Какой баг ловим |
|---|--------|---------------|-----------------|
| 8.1 | Codex | `/v1/responses` + SSE lifecycle | responses bridge, 401/502 |
| 8.2 | Claude Code | `/v1/messages`, base без `/v1`, tools | anthropic compat |
| 8.3 | OmniRoute | Zeus как provider, chatPath completions | keep-alive 502 |
| 8.4 | Cursor | Agent + model `zeuscode` (не gpt-*) | Responses→completions |
| 8.5 | Aider | `openai/zeuscode`, commit-цикл | model prefix |

### 9. Деньги / лимиты — выборочно (1–2 клиента за сессию)

| # | Что проверяем | Ожидание | Какой баг ловим |
|---|---------------|----------|-----------------|
| 9.1 | Списание после чата | spent/balance двигается | биллинг |
| 9.2 | budget=0 / exhausted | понятный отказ | soft lock |
| 9.3 | Пачка быстрых запросов | 429 или очередь | rate limit / death |

### 10. Устойчивость — все

| # | Что проверяем | Ожидание | Какой баг ловим |
|---|---------------|----------|-----------------|
| 10.1 | После 502 — повтор | текст ошибки / ретрай | UX ошибок |
| 10.2 | Два чата параллельно | оба живут | session clash |
| 10.3 | Смена модели mid-session | ок | sticky state |
| 10.4 | Rotate ключа в miniapp | старый 401, новый 200 | key rotate |

### 11. Логи Zeus — после каждого блока

- нет лавины 401/502  
- нет `Tool type or function is null`  
- видны model + prompt_preview  
- (когда будет) `meta.client` из User-Agent  

### 12. Миниапп — один раз на lab-сессию

| # | Что проверяем |
|---|---------------|
| 12.1 | Онбординг learn для выбранного клиента |
| 12.2 | Copy `base_url` / `api_key` |
| 12.3 | pref: Пользовательский → Продвинутый → Набор |
| 12.4 | Advisor: «куда ключ в VS Code» |
| 12.5 | key_rotate → новый ключ в клиенте |

---

## Smoke vs полный

| Режим | Время | Пункты |
|-------|-------|--------|
| **Smoke** | ~10 мин | 1.1–1.2, 2.1, 2.4, 3.1, 4.1, 5.1, 6.1, 7.1, 11 |
| **Полный (агент)** | ~45–90 мин | все применимые 1–11 + свой 8.x |
| **Чат-only** (LibreChat, Open WebUI) | ~20 мин | 1–4, 10–11 |

---

## Шаблон отчёта по клиенту

```markdown
### <Название> — YYYY-MM-DD
- Машина: …
- Ключ prefix: zeus_…
- Режим miniapp: simple | power | custom
- Smoke: PASS / FAIL
- Полный: PASS / FAIL / partial
- FAIL пункты: (номера + цитата ошибки + время)
- Логи Zeus: ок / проблемы
- Фикс нужен: наш gateway / гайд бота / клиент
```

Отчёты класть в `/opt/zeus-client-lab/reports/<id>-YYYY-MM-DD.md` и коротко дублировать в колонку **Заметки** таблицы выше.
