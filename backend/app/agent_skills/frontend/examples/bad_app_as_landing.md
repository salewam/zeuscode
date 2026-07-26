# Bad: «приложение», а сдали пустышку / лендинг

## wrong_product_shape
Запросили app (каталог + заказ), сдали hero-лендинг без `app-nav` / `data-screen`.

## thin_catalog
Каталог рендерит только `<h3>Имя</h3><p>цена</p>` — **нет** `<img>`, **нет** кнопки «В заказ», **нет** состава.

## dead_select
В форме есть `<select id="bouquet_id">`, но JS **никогда** не пишет `options` из GET /api/….

## thin_styles
`styles.css` на ~10–15 строк, `font-family: sans-serif`, без tokens / grid / card media.

## missing_json_headers
`fetch('/api/orders', { method:'POST', body: JSON.stringify(...) })` без `Content-Type: application/json`.

## Прочие FAIL
- `alert('Заказ оформлен')` → `fake_alert_success`
- `onclick="..."` → `inline_onclick`
- React без просьбы → `react_without_ask`
- Нет empty/error → `missing_state`
