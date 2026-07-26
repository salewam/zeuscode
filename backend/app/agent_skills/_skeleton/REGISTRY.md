# Product Registry

Добавляй строку = новый тип продукта. Детали — в `products/<id>.md` (копия PRODUCT_FORM).

| id | title | статус | pack / зоны | команда (коротко) | verify |
|----|-------|--------|-------------|-------------------|--------|
| `landing` | Лендинг / сайт услуг | **есть** (frontend+backend+design+tests) | `/src/frontend` `/src/backend` `/src/design` `/src/tests` | design→fe∥be→tests→review | verify.sh + browser smoke |
| app | Веб-приложение | **на тестах** (intent wired) | design+fe+be+tests | intake→design→(fe∥be)→tests→review | UI smoke + pytest + wrong_product_shape + missing_state |
| `crm` | CRM / кабинет | каркас | fe+be+tests | design→fe∥be→tests | API+UI smoke |
| `deck` | Презентация | каркас | `/src/deck` (+ media) | presentation→media?→review | slide count + export |
| `pdf` | PDF / документ | каркас | `/src/docs` | document→review | файл открывается |
| `media` | Картинки / обложки | каркас | `/assets/generated` | media→review | файл есть, размер ок |
| `mobile` | Мобилка (пока PWA) | позже | frontend | как app + mobile DoD | viewport smoke |

## Статусы

- **есть** — уже в проде / почти  
- **каркас** — форма есть, скилл тонкий, добить на тестах  
- **позже** — не трогаем, пока не закрыты каркасы выше  

## Как добавить «что угодно»

1. Новая строка в таблице.  
2. `cp PRODUCT_FORM.md products/<id>.md` и заполни.  
3. Если нужен новый агент — скопируй `SKILL_PACK_TEMPLATE` → `../<pack>/`.  
4. В коде оркестратора (потом): intent `<id>` → team из формы §4.  
5. Первый тест → правки checklist/anti/verify.
