"""ZeusCode — автогенерация конфигов для окон разработки.

База данных: 45 окон разработки с официальной документацией.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Загружаем базу данных окон из исследования
_RESEARCH_PATH = Path(__file__).parent.parent.parent / "ai_windows_research.json"
_WINDOWS_DB = None


def _load_windows_db() -> dict:
    """Загружает базу данных окон разработки из JSON."""
    global _WINDOWS_DB
    if _WINDOWS_DB is not None:
        return _WINDOWS_DB

    if not _RESEARCH_PATH.exists():
        # Fallback если файл не найден
        _WINDOWS_DB = {"categories": {}}
        return _WINDOWS_DB

    with open(_RESEARCH_PATH, "r", encoding="utf-8") as f:
        _WINDOWS_DB = json.load(f)

    return _WINDOWS_DB


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
        "ключ", "key", "api", "setup", "connect", "интеграция",
        "настройка", "инструкция"
    ]

    is_setup_request = any(kw in text_lower for kw in setup_keywords)
    if not is_setup_request:
        return None

    # Загружаем базу окон
    db = _load_windows_db()

    # Собираем все окна из всех категорий
    all_windows = []
    for category_windows in db.get("categories", {}).values():
        all_windows.extend(category_windows)

    # Ищем упоминание окна по имени и алиасам
    for window in all_windows:
        window_id = window.get("id", "")
        window_name = window.get("name", "").lower()

        # Проверяем основное имя
        if window_name and window_name in text_lower:
            return window_id

        # Проверяем ID
        if window_id and window_id in text_lower:
            return window_id

        # Проверяем алиасы (если есть)
        aliases = window.get("aliases", [])
        for alias in aliases:
            if alias.lower() in text_lower:
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
            "docs_url": str,  # ссылка на документацию
            "website": str,  # официальный сайт
        }
    """
    db = _load_windows_db()

    # Ищем окно в базе
    window_data = None
    for category_windows in db.get("categories", {}).values():
        for window in category_windows:
            if window.get("id") == window_id:
                window_data = window
                break
        if window_data:
            break

    if not window_data:
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
            "docs_url": "",
            "website": "",
        }

    # Генерируем конфиг на основе данных из базы
    title = window_data.get("name", window_id.title())
    config_format = window_data.get("config_format", "ui_settings")
    config_location = window_data.get("config_location", "")
    setup_steps = window_data.get("setup_steps", [])
    config_example = window_data.get("config_example", {})
    docs_url = window_data.get("docs_url", "")
    website = window_data.get("website", "")
    notes = window_data.get("notes", "")

    # Формируем текст конфига в зависимости от формата
    if config_format == "json" and config_example:
        # JSON конфиг с примером
        example_str = json.dumps(config_example, indent=2, ensure_ascii=False)
        # Подставляем реальные значения
        example_str = example_str.replace('"api_url": "https://api.groq.com/openai/v1"', f'"api_url": "{base_url}"')
        example_str = example_str.replace('"apiBase": "http://localhost:11434/v1"', f'"apiBase": "{base_url}"')
        example_str = example_str.replace('"base_url": "https://api.openai.com/v1"', f'"base_url": "{base_url}"')
        example_str = example_str.replace('"apiKey": "sk-..."', f'"apiKey": "{api_key}"')
        example_str = example_str.replace('"api_key": "..."', f'"api_key": "{api_key}"')

        config_text = f"""# {config_location}

{example_str}

# Замени URL и ключ на свои значения
# Base URL: {base_url}
# API Key: {api_key}
# Model: gpt-5.5"""

    elif config_format == "yaml":
        config_text = f"""# {config_location}

models:
  - title: ZeusCode
    provider: openai
    model: gpt-5.5
    apiBase: {base_url}
    apiKey: {api_key}

# Сохрани и перезапусти окно"""

    elif config_format == "env_vars":
        config_text = f"""# Переменные окружения

export OPENAI_API_BASE={base_url}
export OPENAI_API_KEY={api_key}
export OPENAI_MODEL=gpt-5.5

# Linux/macOS: добавь в ~/.bashrc или ~/.zshrc
# Windows: установи через System Properties → Environment Variables"""

    else:
        # UI Settings
        config_text = f"""# {config_location}

Provider: OpenAI Compatible
Base URL: {base_url}
API Key: {api_key}
Model: gpt-5.5

# Открой настройки и укажи эти параметры"""

    # Адаптируем шаги под наши значения
    adapted_steps = []
    for step in setup_steps:
        # Подставляем реальные значения в шаги
        step = step.replace("https://your-gateway.com/v1", base_url)
        step = step.replace("http://localhost:11434/v1", base_url)
        step = step.replace("custom base URL", f"Base URL: {base_url}")
        step = step.replace("custom API key", f"API Key: {api_key}")
        step = step.replace("Enter custom base URL", f"Enter: {base_url}")
        step = step.replace("Enter custom API key", f"Enter: {api_key}")
        adapted_steps.append(step)

    # Если шагов нет — создаём базовые
    if not adapted_steps:
        adapted_steps = [
            f"Открой {title}",
            "Найди настройки AI/Models",
            "Добавь Custom Provider",
            f"Base URL: {base_url}",
            f"API Key: {api_key}",
            "Model: gpt-5.5",
            "Сохрани и начни кодить!",
        ]

    return {
        "window": window_id,
        "title": title,
        "config": config_text,
        "steps": adapted_steps,
        "docs_url": docs_url,
        "website": website,
        "notes": notes,
    }


def format_setup_message(window_config: dict) -> str:
    """Форматирует конфиг и инструкцию для отправки в Telegram."""
    title = window_config["title"]
    config = window_config["config"]
    steps = window_config["steps"]
    docs_url = window_config.get("docs_url", "")
    website = window_config.get("website", "")
    notes = window_config.get("notes", "")

    steps_text = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps))

    message = f"""<b>🛠 Настройка {title}</b>

<b>📋 Конфиг:</b>
<pre>{config}</pre>

<b>📝 Шаги:</b>
{steps_text}"""

    if notes:
        message += f"\n\n<b>ℹ️ Заметки:</b>\n{notes[:300]}"

    if website:
        message += f"\n\n<b>🌐 Сайт:</b> {website}"

    if docs_url:
        message += f"\n<b>📚 Документация:</b> {docs_url}"

    message += f"\n\n✅ Готово! Используй модель <b>gpt-5.5</b> в {title}"

    return message


def get_all_supported_windows() -> list[dict]:
    """Возвращает список всех поддерживаемых окон из базы данных."""
    db = _load_windows_db()
    all_windows = []

    for category, windows in db.get("categories", {}).items():
        for window in windows:
            all_windows.append({
                "id": window.get("id"),
                "name": window.get("name"),
                "category": category,
                "website": window.get("website"),
            })

    return all_windows
