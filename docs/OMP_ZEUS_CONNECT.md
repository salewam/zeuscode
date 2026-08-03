# Подключить omp (oh-my-pi) к ZeusCode

omp — локальный coding CLI. Zeus — prepaid API с Role Routing.  
Схема: **omp = руки (tools), Zeus = мозг + биллинг**.

## 1. Ключ Zeus

1. Открой TG Mini App / кабинет Zeus.
2. Создай API-ключ.
3. Режим: **power** (Opus · GPT-5.5 · DeepSeek) или свой custom.

## 2. Конфиг omp

В `~/.omp/agent/models.yml` (или через `/model` → custom OpenAI-compatible):

```yaml
providers:
  zeus:
    api: openai-completions
    baseUrl: https://YOUR_ZEUS_HOST/v1
    apiKey: YOUR_ZEUS_KEY
    models:
      - id: zeuscode
        name: ZeusCode
        contextWindow: 200000
        maxTokens: 16384

modelRoles:
  default: zeus/zeuscode
  # Опционально те же алиасы — на стороне Zeus роли крутятся сами
  smol: zeus/zeuscode
  slow: zeus/zeuscode
  plan: zeus/zeuscode
  designer: zeus/zeuscode
  advisor: zeus/zeuscode
```

Либо одним флагом:

```bash
omp --model zeus/zeuscode
```

Base URL и ключ можно задать как у OpenAI-compatible провайдера в `omp setup`.

## 3. Что происходит

| Слой | Кто |
|------|-----|
| Правки файлов, LSP, bash | **omp** на твоей машине |
| Clarifier → ТЗ → план → small/v1/verify | **Zeus** на сервере |
| Списание токенов | **Zeus** prepaid |

Внутри Zeus публичная модель всегда `zeuscode`. Роли (smol/slow/plan/…) маппятся на стек автоматически — см. `GET /me/fusion` → `model_aliases`.

## 4. Роли (как Ctrl+P в omp)

| Alias | Zeus (power) типично |
|-------|----------------------|
| default / task | doer (Opus) |
| smol / tiny / commit | DeepSeek / mini |
| slow / plan | Architect Opus/GPT |
| designer | GPT → Opus (UI) |
| advisor | Judge Opus/GPT |

Точные id: `GET /me/fusion` → `alias_cards`.

## 5. Диалог перед кодом

На крупных задачах Zeus спросит уточнения → соберёт ТЗ → покажет **план** → после «да» / «делай» пойдёт в разработку.

План сохраняется как артефакт `zeus://plan` в sticky (`plan_artifact`) и в Onestack — не только текстом в чате.

После ответа doer крутится **Advisor** (read-only): `nit` / `concern` / `blocker` в thinking + `onestack.advisor`. Ответ **не переписывает** (это делают Gate/Judge).

Пропуск: `без уточнений` / `сразу делай` в первом сообщении, или `без плана` на шаге плана.  
Advisor off: `zeus.advisor=false`.

## 6. Ограничения

- Zeus chat **не** крутит локальные tools omp — tools делает omp, текст/код приходит от Zeus.
- Если клиент шлёт OpenAI `tools` напрямую в Zeus API, Fusion уходит в solo-coder (см. chat remount).
- Для полного «агент правит репозиторий» оставляй tools в omp, а модель — Zeus.
