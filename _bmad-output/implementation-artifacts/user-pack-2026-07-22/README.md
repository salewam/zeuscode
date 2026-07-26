# User pack — прогон 2026-07-22

Простыми словами: прогнал 12 обычных пользовательских задач на проде `zeus/fusion`.

## Итог
- Успешно: **12/12**
- Ошибок/429: **0** / **0**
- KIE до: **879.06**
- KIE после: **870.94**
- Потрачено примерно: **8.12 ₽/credits**
- Sticky leaders: ['gemini-3.1-pro', 'gemini-3.1-pro']

## Кейсы
| # | ok | Path | Leader | сек | кусок ответа |
|---|---|---|---|---|---|
| u01_hi | True | CASCADE | claude-haiku-4-5 | 12.995 | Привет! Да, я на связи.   Я Claude, ассистент от Anthropic. Я готов помочь вам с |
| u02_css | True | CASCADE | claude-haiku-4-5 | 15.552 | ```css .button-primary {   background-color: #0066cc;   color: white;   padding: |
| u03_bugfix | True | CASCADE | gemini-3.1-pro | 13.745 | ```javascript // Вариант 1: вернет undefined вместо падения users.map(u => u.nam |
| u04_python | True | CASCADE | gemini-3.1-pro | 11.475 | ```python def chunk_list(items, size):     return [items[i:i + size] for i in ra |
| u05_sql_review | True | CASCADE | gemini-3.1-pro | 12.283 | ### Как правильно (Параметризованный запрос)  Для **SQLite / pyodbc**: ```python |
| u06_api_design | True | CASCADE | gemini-3.1-pro | 13.275 | ### Поля модели (Заметка) *   `id` (string/uuid) — уникальный идентификатор *    |
| u07_refactor | True | CASCADE | claude-haiku-4-5 | 19.926 | # Упрощение кода  Вот упрощенный вариант:  ```python def f(x):     return bool(x |
| u08_explain | True | CASCADE | claude-haiku-4-5 | 17.302 | # Webhook и Retry  **Webhook** — это механизм, когда одно приложение отправляет  |
| u09_sticky_a | True | CASCADE | gemini-3.1-pro | 10.353 | Название проекта **NovaBoard** подтверждаю. Это Kanban-доска на FastAPI. Готов п |
| u10_sticky_b | True | FULL | gemini-3.1-pro | 46.696 | Так как история предыдущей переписки недоступна, я использую пример стандартного |
| u11_hard | True | FULL | deepseek-v4-pro | 48.405 | Таблица `outgoing_webhooks` хранит задачи: поля `id`, `url`, `payload`, `status` |
| u12_ui_copy | True | CASCADE | claude-haiku-4-5 | 14.952 | # Варианты CTA для AI-кодинг инструмента  ## Вариант 1 (Прямой и активный) **"На |

Полные ответы: `results/u*.json`
