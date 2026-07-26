# Good app — планка качества (паттерн, не клон)

Сдай **своё** приложение под бриф. Ниже — что должно *работать*, не какой CSS-класс обязателен.

## Мышление (перед кодом)

1. Что за продукт и бренд в брифе?
2. Какие 2–3 экрана?
3. Какие поля у сущности каталога?
4. Заказ = one-shot select или корзина?
5. Визуал: не дефолтный «Букет Лайн» / «Свежая Полка», если бриф другой.

## Минимальная анатомия

```text
header: бренд + nav (data-view / tabs) + контакт
screen catalog: фильтры + grid карточек (img, title, price, CTA)
screen order|cart: preview/lines + form (имя, телефон, адрес если доставка) + submit
screen orders: список с API + empty/error/loading
toast/status: role=status|alert
app.js: fetch, filters, pick/cart, submit + res.ok, loadOrders
```

## Карточка (идея, разметка — своя)

- фото из `item.image` (live URL)
- название из `item.name`
- 1–2 meta-поля **из домена** (не копируй flower `composition/size/stems` в grocery)
- CTA «В заказ» / «В корзину» с рабочим handler

## JS-контракт (имена функций — любые)

- загрузка каталога + рендер
- фильтр по category/tag
- выбор / корзина
- POST заказа + проверка `res.ok`
- загрузка истории заказов
- `const API = "."`

## Плотность

Не 2KB-скелет. Полноценные стили и логика под этот бриф.
Ориентир: HTML ≥3KB, CSS ≥4KB, JS ≥3.5KB.

## Anti

См. `bad_app_as_landing.md`: hero-лендинг вместо shell = FAIL.
Клон эталона с другим title без смены UX/копирайта под бриф = тоже плохо.
