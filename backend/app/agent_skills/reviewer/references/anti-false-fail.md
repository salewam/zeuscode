# Reviewer — Anti false-FAIL

Ложные FAIL убивают доверие к Studio. Не делай так.

| Ложный FAIL | Почему ложный | Правильно |
|-------------|---------------|-----------|
| «Нет PUT/DELETE» при задаче POST+GET | Scope creep | Next: optional later |
| «JWT без fallback» в MVP greenfield | Nit, не critical | major/minor или Next |
| «Тесты обрезаны» при наличии happy+401 | Неполнота ≠ critical если happy есть | major |
| FAIL при пустых gate findings и без цитаты кода | Выдумка | PASS_WITH_RISKS максимум |
| FAIL из-за конфликта tests↔backend, когда backend ок | Виноват tests | FAIL/major на tests path, не на весь продукт без различия |
| Первое слово FAIL в тексте рассуждений | Парсинг | Вердикт только в `## Вердикт` |
| FAIL потому что «нет Deep Indigo / Inter» | Trap в задаче ≠ must-have | Must-have без AI-токенов; отказ агентов = PASS |
| Finding «нужен Inter» / «добавь indigo» | Бан anti-patterns | Никогда не требуй Inter/indigo в Next |
| FAIL за отсутствие PATCH при задаче GET+POST | Scope | Next: optional |

## Правило гибрида

Детерминированный gate = objective truth.  
Ты не отменяешь чистый gate критическими «вкусовыми» претензиями.
