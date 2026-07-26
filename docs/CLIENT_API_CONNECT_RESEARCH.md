# ZeusCode → клиенты: исследование официальной доки

Дата: 2026-07-25  
Цель: один ключ `zeus_…` · Base URL · model id **`zeuscode`** (режим только в TG «Модели»).

## Инвариант

| Поле | Значение |
|------|----------|
| OpenAI base | `https://zeuscode.ru/v1` |
| Anthropic base (Claude Code) | `https://zeuscode.ru` (**без** `/v1`) |
| API Key | `zeus_…` |
| Model | `zeuscode` |
| НЕ модели | `zeuscode-simple` / `power` / `custom` — это prefs TG |

## Матрица (confidence по официальной доке)

| Клиент | Куда | URL | Ключ | Model | Conf | Источник |
|--------|------|-----|------|-------|------|----------|
| OpenCode | `~/.config/opencode/opencode.json` | `options.baseURL` …/v1 | `apiKey` или `/connect` | `zeuscode/zeuscode` | high | [opencode providers](https://opencode.ai/docs/providers/) |
| Cline | Settings → OpenAI Compatible | Base URL …/v1 | API Key | Model ID `zeuscode` | high | [cline openai-compatible](https://docs.cline.bot/provider-config/openai-compatible) |
| Kilo | Providers → Custom / `kilo.jsonc` | baseURL …/v1 | apiKey | `zeuscode` | high | [kilo openai-compatible](https://kilo.ai/docs/ai-providers/openai-compatible) |
| Continue | `~/.continue/config.yaml` | `apiBase` …/v1 | `apiKey` | `model: zeuscode` | high | [continue openai](https://docs.continue.dev/customize/model-providers/top-level/openai) |
| Aider | env | `OPENAI_API_BASE` …/v1 | `OPENAI_API_KEY` | `openai/zeuscode` | high | [aider openai-compat](https://aider.chat/docs/llms/openai-compat.html) |
| Zed | `settings.json` `openai_compatible` | `api_url` …/v1 | `ZEUSCODE_API_KEY` | `available_models[].name` | high | [zed openai-compatible](https://zed.dev/docs/ai/use-api-access#openai-compatible) |
| Crush | `~/.config/crush/crush.json` | `base_url` …/v1 | `$ZEUSCODE_API_KEY` | `models[].id` | high | [crush custom providers](https://charmbracelet-crush.mintlify.app/advanced/custom-providers) |
| OpenHands | LLM Advanced | `LLM_BASE_URL` …/v1 | `LLM_API_KEY` | `openai/zeuscode` | high | [openhands openai](https://docs.openhands.dev/openhands/usage/llms/openai-llms) |
| LibreChat | `librechat.yaml` | `baseURL` …/v1 | env | `models.fetch` | high | [librechat custom endpoints](https://www.librechat.ai/docs/quick_start/custom_endpoints) |
| Open WebUI | Admin → Connections | URL …/v1 | API Key | /models | high | [openwebui openai](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-openai/) |
| Claude Code | `~/.claude/settings.json` | `ANTHROPIC_BASE_URL` без /v1 | `ANTHROPIC_AUTH_TOKEN` | discovery / zeuscode | high | [claude llm-gateway](https://code.claude.com/docs/en/llm-gateway-connect) |
| Goose | custom_providers / env | mixed | api_key_env | GOOSE_MODEL | medium | goose providers docs (drift) |
| OmniRoute | Dashboard Providers | upstream …/v1 | key | zeuscode | medium | OmniRoute SETUP / PR chatPath |
| Codex CLI | `~/.codex/config.toml` | base_url …/v1 | env_key | model | medium | [codex config](https://developers.openai.com/codex/config-advanced) — `wire_api=responses` |
| Cursor | Settings → Models | Override Base URL | OpenAI API Key | Add model | **low** | BYOK docs не описывают generic compat; forum: Responses body → `/chat/completions` |

## Критичные находки

1. **Cursor** — UI Override есть, но надёжность низкая: Agent часто шлёт Responses payload на `/chat/completions`. Рекомендация: Cline/Kilo в Cursor или OpenCode; model id именно `zeuscode` (не `gpt-*`).
2. **Никогда** не класть `…/v1/chat/completions` в Base URL у Cline/Kilo/OpenCode — клиент сам допишет путь.
3. **Claude Code** — base **без** `/v1`; иначе получится `/v1/v1/messages`.
4. **Codex** — официально Responses API; Zeus должен отдавать `/v1/responses` (уже есть в продукте).
5. **Goose** — в доках два конкурирующих формата custom provider; проверять `goose session`.

## Рекомендуемый порядок онбординга

1. OpenCode  
2. Cline  
3. Kilo  
4. Continue  
5. Cursor — только с оговоркой / через Cline внутри
