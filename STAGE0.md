# ZeusCode — Этап 0: Смоук upstream

**Дата:** 11 июля 2026  
**Статус:** каталог проверен; live Ultra Mode — через `UPSTREAM_API_KEY`

---

## Главный вывод

**Основной upstream хорошо тянет западный каталог + кэш, но НЕ закрывает Fusion-стек из поста.**

| Модель из Fusion-поста | Upstream №1 | Цена (in / out за 1M) |
|------------------------|-------------|------------------------|
| Gemini 3 Flash | ✅ есть | **$0.15 / $0.90** (−~официалки) |
| Kimi K2.6 | ❌ **нет** | — |
| DeepSeek V4 Pro | ❌ **нет** | — |

Qwen в этом каталоге есть только как **image**, не chat.  
GLM / Moonshot — не найдены в pricing API.

Значит для настоящего «Fable Killer» нужен **второй upstream** (DeepInfra / IKunCode / OpenRouter) только под Kimi + DeepSeek.  
Upstream №1 остаётся базой для Gemini / Claude / GPT / Grok и пополнения.

---

## Что есть на upstream №1 (полезное для ZeusCode)

### Дешёвые / рабочие для кодинга

| Модель | In $ | Out $ | Cache input $ | Заметка |
|--------|------|-------|---------------|---------|
| Gemini 2.5 Flash | 0.09 | 0.75 | — | самый дешёвый Google |
| Gemini 3 Flash | 0.15 | 0.90 | — | роль Frontend в Fusion |
| Claude Haiku 4.5 | 0.275 | 1.425 | — | дешёвый Anthropic |
| gpt-5.6-luna | 0.28 | 1.68 | 0.028 | есть **Cached Input** |
| grok-4-3 | 0.5 | 1.0 | 0.08 | кэш есть |
| Claude Sonnet 4.6 / 5 | 0.85 | 4.275 | — | mid |
| Claude Fable 5 | 4.0 | 20.0 | — | эталон «дорого» |
| gpt-5.5 / sol | 1.4 | 8.4 | 0.14 | кэш есть |

Кэш реально есть (Cached Input / Cache Writes) — это закрывает требование −90% на повторном контексте **для моделей, где строка Cached Input в прайсе**.

### API-форматы (важно для разработки)

Это **не один** OpenAI endpoint на всё. Разные семьи:

| Семья | Endpoint (относительно `UPSTREAM_BASE_URL`) | Формат |
|-------|---------------------------------------------|--------|
| Gemini | `/{model}/v1/chat/completions` | OpenAI chat |
| Claude | `/claude/v1/messages` | Anthropic Messages (`model` в body) |
| GPT / Codex / Grok | `/codex/v1/responses` (и аналоги) | свой Responses API |
| Base Claude Code | `ANTHROPIC_BASE_URL={UPSTREAM_BASE_URL}/claude` | как в гайде провайдера |

ZeusCode backend делает **адаптеры** → наружу один OpenAI-compatible `/v1/chat/completions`.

Auth: `Authorization: Bearer <UPSTREAM_API_KEY>`  
Кредиты: `GET {UPSTREAM_BASE_URL}/api/v1/chat/credit`

---

## Временный Ultra Mode только на upstream №1 (пока нет 2-го)

Пока нет DeepSeek/Kimi, smoke-пресет:

| Роль | Модель |
|------|--------|
| Frontend | Gemini 3 Flash |
| Backend | Gemini 2.5 Flash (или Pro) |
| Tests | Claude Haiku 4.5 |
| Docs | Claude Haiku 4.5 |
| Синтез | Gemini 3 Flash или Haiku |

Это **не** бенчмарк из поста, но проверяет оркестратор 4+1 и биллинг.

Целевой пресет (после 2-го ключа):

| Роль | Модель | Откуда |
|------|--------|--------|
| Frontend | Gemini 3 Flash | upstream №1 |
| Backend | DeepSeek V4 Pro | DeepInfra / IKunCode |
| Tests | Kimi K2.6 | IKunCode / OpenRouter |
| Docs | Kimi или Haiku | second / №1 |
| Синтез | DeepSeek V4 Pro | second |

---

## Live smoke (11 июля 2026) — только самая дешёвая

Модель: **gemini-2.5-flash** (`/gemini-2.5-flash/v1/chat/completions`)  
Баланс до: **80.0** → после: **79.59** (−**0.41** кредита)

| Метрика | Значение |
|---------|----------|
| 4 агента wall-time | **~5.1 с** (параллельно) |
| Синтез | **~5.1 с** |
| Всего ~ | **~10 с** |
| Токены (сумма) | ~4.7k total |
| Оценка $ по прайсу | **~$0.002** |
| Списание кредитов | **0.41** |

Все 5 вызовов **OK**. Артефакты: `stage0/out/`.

Вывод: Ultra Mode на самой дешёвой модели upstream №1 работает. Для Fusion из поста всё ещё нужен 2-й upstream (DeepSeek/Kimi).

---

## Чеклист этапа 0

- [x] Каталог chat-моделей снят через pricing API  
- [x] Подтверждено: нет DeepSeek / Kimi  
- [x] Зафиксированы endpoint-форматы  
- [x] Написан `stage0/smoke_ultra.py`  
- [x] Live-прогон на `gemini-2.5-flash` (самая дешёвая)  
- [ ] Решение по второму upstream (DeepInfra vs IKunCode)  
- [ ] (Опц.) отдельный тест prompt cache на gpt-5.6-luna / grok  

---

## Как прогнать smoke

```bash
cd /Users/money/Desktop/Projects/ultra-mode-mvp
cp .env.example .env   # впиши UPSTREAM_API_KEY и UPSTREAM_BASE_URL
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python stage0/smoke_ultra.py
```

Скрипт:
1. Проверяет баланс кредитов  
2. Шлёт 4 параллельных запроса (Gemini + Haiku)  
3. Делает синтез  
4. Печатает usage / время / оценку $  
5. Пишет сырой вывод в `stage0/out/`

---

## Решение, которое нужно от тебя

1. **Ключ upstream** в `.env` как `UPSTREAM_API_KEY` (+ `UPSTREAM_BASE_URL`) — прогоним live.  
2. Выбери второй upstream для DeepSeek/Kimi: **DeepInfra** (просто карта) или **IKunCode** (дешевле, USDT/Alipay).  
3. После live-замера зафиксируем trial ($1–3) и цену 1 Ultra-цикла для лендинга.
