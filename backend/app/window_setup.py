"""ZeusCode — автогенерация конфигов для окон разработки."""

from __future__ import annotations

import re

# Детектор упоминаний окон разработки
WINDOW_PATTERNS = {
    "cursor": r"\b(cursor|курсор)\b",
    "vscode": r"\b(vscode|vs\s*code|visual\s*studio\s*code|висуал|вскод)\b",
    "windsurf": r"\b(windsurf|виндсурф)\b",
    "jetbrains": r"\b(jetbrains|pycharm|webstorm|intellij|idea|пайчарм|вебшторм)\b",
    "continue": r"\b(continue|континю)\b",
    "cline": r"\b(cline|клайн|kilo)\b",
    "aider": r"\b(aider|айдер)\b",
    "claude_code": r"\b(claude\s*code|клод\s*код)\b",
    "orca": r"\b(orca|орка)\b",
    "zed": r"\b(zed|зед)\b",
    "neovim": r"\b(neovim|nvim|нео?вим)\b",
    "vim": r"\b(vim|вим)\b",
}


def detect_window_request(text: str) -> str | None:
    """Определяет запрос о подключении окна разработки.

    Возвращает:
    - None если это не запрос о подключении
    - window_id если распознано окно (cursor, vscode, windsurf и т.д.)
    """
    text_lower = text.lower()

    # Ключевые слова запроса о подключении
    setup_keywords = [
        "как подключить", "подключить", "настроить", "установить",
        "как использовать", "как работать", "конфиг", "config",
        "ключ", "key", "api", "setup", "connect"
    ]

    is_setup_request = any(kw in text_lower for kw in setup_keywords)
    if not is_setup_request:
        return None

    # Ищем упоминание окна
    for window_id, pattern in WINDOW_PATTERNS.items():
        if re.search(pattern, text_lower, re.IGNORECASE):
            return window_id

    return None


def generate_window_config(window_id: str, api_key: str, base_url: str = "https://zeuscode.ru/v1") -> dict:
    """Генерирует конфиг и инструкцию для конкретного окна.

    Returns:
        {
            "window": str,
            "title": str,
            "config": str,  # готовый текст конфига
            "steps": list[str],  # шаги установки
        }
    """

    configs = {
        "cursor": {
            "title": "Cursor",
            "config": f"""# Cursor Settings → Models → Add Model
Provider: OpenAI Compatible
Base URL: {base_url}
API Key: {api_key}
Model: gpt-5.5

# В чате Cursor выбери модель gpt-5.5""",
            "steps": [
                "Открой Cursor → Settings (⌘,)",
                "Вкладка Models → Add Model",
                "Provider: OpenAI Compatible",
                f"Base URL: {base_url}",
                f"API Key: {api_key}",
                "Model: gpt-5.5",
                "Сохрани → в чате выбери модель gpt-5.5",
            ],
        },
        "vscode": {
            "title": "VS Code (Continue)",
            "config": f"""# ~/.continue/config.json
{{
  "models": [
    {{
      "title": "ZeusCode",
      "provider": "openai",
      "model": "gpt-5.5",
      "apiBase": "{base_url}",
      "apiKey": "{api_key}"
    }}
  ]
}}""",
            "steps": [
                "Установи расширение Continue для VS Code",
                "Открой Continue (Ctrl+L / ⌘L)",
                "Local Config → шестерёнка → config.json",
                "Вставь конфиг выше",
                "Сохрани (⌘S) → в чате выбери ZeusCode",
            ],
        },
        "windsurf": {
            "title": "Windsurf",
            "config": f"""# Windsurf Settings → AI Providers
Provider: OpenAI Compatible
Name: ZeusCode
Base URL: {base_url}
API Key: {api_key}
Model: gpt-5.5

# В Cascade или Cline выбери gpt-5.5""",
            "steps": [
                "Открой Windsurf → Settings",
                "AI Providers → Add Provider",
                "Provider: OpenAI Compatible",
                f"Base URL: {base_url}",
                f"API Key: {api_key}",
                "Model: gpt-5.5",
                "В Cascade/Cline выбери gpt-5.5",
            ],
        },
        "jetbrains": {
            "title": "JetBrains (PyCharm/WebStorm/IntelliJ)",
            "config": f"""# Settings → Tools → OpenAI → Custom Provider
Base URL: {base_url}
API Key: {api_key}
Model: gpt-5.5

# Для Kilo Code плагина:
Settings → Kilo → Custom Provider
Base URL: {base_url}
API Key: {api_key}""",
            "steps": [
                "Открой Settings (⌘,)",
                "Tools → OpenAI (или установи плагин Kilo Code)",
                "Add Custom Provider",
                f"Base URL: {base_url}",
                f"API Key: {api_key}",
                "Model: gpt-5.5",
                "Сохрани → используй в AI Assistant",
            ],
        },
        "continue": {
            "title": "Continue",
            "config": f"""# ~/.continue/config.json
{{
  "models": [
    {{
      "title": "ZeusCode",
      "provider": "openai",
      "model": "gpt-5.5",
      "apiBase": "{base_url}",
      "apiKey": "{api_key}"
    }}
  ]
}}""",
            "steps": [
                "Открой Continue в VS Code/JetBrains",
                "Local Config → шестерёнка",
                "Вставь конфиг выше в config.json",
                "Сохрани → выбери ZeusCode в чате",
            ],
        },
        "cline": {
            "title": "Cline",
            "config": f"""# Cline Settings
Provider: OpenAI Compatible
Base URL: {base_url}
API Key: {api_key}
Model: gpt-5.5""",
            "steps": [
                "Открой Cline в VS Code/Windsurf",
                "Settings → Custom Provider",
                f"Base URL: {base_url}",
                f"API Key: {api_key}",
                "Model: gpt-5.5",
            ],
        },
        "aider": {
            "title": "Aider",
            "config": f"""# ~/.aider.conf.yml
openai-api-base: {base_url}
openai-api-key: {api_key}
model: openai/gpt-5.5

# Или в терминале:
export OPENAI_API_BASE={base_url}
export OPENAI_API_KEY={api_key}
aider --model openai/gpt-5.5""",
            "steps": [
                "Создай файл ~/.aider.conf.yml",
                "Вставь конфиг выше",
                "ИЛИ экспортируй переменные в терминале",
                "Запусти: aider --model openai/gpt-5.5",
            ],
        },
        "claude_code": {
            "title": "Claude Code",
            "config": f"""# ~/.claude/config.json
{{
  "providers": [
    {{
      "name": "zeuscode",
      "type": "openai",
      "baseURL": "{base_url}",
      "apiKey": "{api_key}",
      "models": ["gpt-5.5"]
    }}
  ]
}}""",
            "steps": [
                "Создай файл ~/.claude/config.json",
                "Вставь конфиг выше",
                "Запусти claude code",
                "Выбери модель gpt-5.5",
            ],
        },
        "orca": {
            "title": "Orca",
            "config": f"""# ~/.config/claude-code/config.json
{{
  "provider": "openai",
  "apiBaseUrl": "{base_url}",
  "apiKey": "{api_key}",
  "defaultModel": "gpt-5.5"
}}

# Установка + настройка одной командой:
# macOS:
brew install --cask stablyai/orca/orca && \\
mkdir -p ~/.config/claude-code && \\
cat > ~/.config/claude-code/config.json << 'EOF'
{{
  "provider": "openai",
  "apiBaseUrl": "{base_url}",
  "apiKey": "{api_key}",
  "defaultModel": "gpt-5.5"
}}
EOF""",
            "steps": [
                "Установи Orca: brew install --cask stablyai/orca/orca",
                "ИЛИ скачай с https://github.com/stablyai/orca",
                "Создай ~/.config/claude-code/config.json",
                "Вставь конфиг выше",
                "Открой Orca → готово!",
            ],
        },
        "zed": {
            "title": "Zed",
            "config": f"""# Zed Settings → AI → Custom Provider
Provider: OpenAI Compatible
Base URL: {base_url}
API Key: {api_key}
Model: gpt-5.5""",
            "steps": [
                "Открой Zed → Settings",
                "AI → Add Custom Provider",
                f"Base URL: {base_url}",
                f"API Key: {api_key}",
                "Model: gpt-5.5",
                "Используй в Agent panel",
            ],
        },
        "neovim": {
            "title": "Neovim",
            "config": f"""-- Для плагина codecompanion.nvim или avante.nvim
require('codecompanion').setup({{
  adapters = {{
    zeuscode = function()
      return require('codecompanion.adapters').extend('openai', {{
        env = {{
          url = '{base_url}',
          api_key = '{api_key}',
        }},
        schema = {{
          model = {{ default = 'gpt-5.5' }},
        }},
      }})
    end,
  }},
}})""",
            "steps": [
                "Установи плагин codecompanion.nvim или avante.nvim",
                "Добавь конфиг в init.lua",
                "Перезагрузи Neovim",
                "Используй :CodeCompanion или :Avante",
            ],
        },
        "vim": {
            "title": "Vim",
            "config": f"""\" Для плагина vim-ai или chatgpt.vim
let g:vim_ai_api_base = '{base_url}'
let g:vim_ai_api_key = '{api_key}'
let g:vim_ai_model = 'gpt-5.5'""",
            "steps": [
                "Установи плагин vim-ai или chatgpt.vim",
                "Добавь конфиг в .vimrc",
                "Перезагрузи Vim",
                "Используй команды плагина",
            ],
        },
    }

    if window_id not in configs:
        # Универсальный fallback
        return {
            "window": window_id,
            "title": window_id.title(),
            "config": f"""# OpenAI-совместимый провайдер
Base URL: {base_url}
API Key: {api_key}
Model: gpt-5.5

# Найди в настройках своего окна:
# - Custom Provider / OpenAI Compatible
# - Вставь Base URL, API Key, Model
# - Сохрани и используй""",
            "steps": [
                "Открой настройки своего окна",
                "Найди Custom Provider или OpenAI Compatible",
                f"Base URL: {base_url}",
                f"API Key: {api_key}",
                "Model: gpt-5.5",
                "Сохрани и начни кодить!",
            ],
        }

    cfg = configs[window_id]
    return {
        "window": window_id,
        "title": cfg["title"],
        "config": cfg["config"],
        "steps": cfg["steps"],
    }


def format_setup_message(window_config: dict) -> str:
    """Форматирует конфиг и инструкцию для отправки в Telegram."""
    title = window_config["title"]
    config = window_config["config"]
    steps = window_config["steps"]

    steps_text = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps))

    return f"""<b>🛠 Настройка {title}</b>

<b>📋 Конфиг:</b>
<pre>{config}</pre>

<b>📝 Шаги:</b>
{steps_text}

✅ Готово! Теперь в {title} используй модель <b>gpt-5.5</b>"""
