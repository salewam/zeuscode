# Frontend — Definition of Done

Задача **не сдана**, пока пункты не закрыты или явно `N/A` + причина в ## Мышление.

Планка по режиму — в конце. Источники: Addy Osmani frontend-ui-engineering / DoD, WCAG 2.2 AA, контракт ZeusCode Studio.

---

## A. Acceptance

- [ ] UI закрывает формулировку задачи (не «похожую»)
- [ ] Happy path воспроизводим по шагам из запроса
- [ ] Один ход = один главный экран/компонент (нет «всего продукта»)

## B. States (обязательно для списков / async / форм)

- [ ] **loading** — skeleton или явный busy (кнопка disabled + текст / `aria-busy`)
- [ ] **empty** — заголовок + зачем пусто + CTA (`<button>` / `<a>`)
- [ ] **error** — человеческий текст + next action (retry / назад), `role="alert"` где уместно
- [ ] **ready** — контент без маскировки ошибок

## C. Semantics & controls

- [ ] Действия = `<button>`, навигация = `<a href>`
- [ ] Нет основного UX на `<div onclick>` / clickable card без кнопки внутри
- [ ] Один `h1` на страницу; уровни без прыжка `h1`→`h3`
- [ ] Формы: `<label for>` (или `aria-label`); ошибки связаны через `aria-describedby` / `aria-invalid`
- [ ] Icon-only control имеет `aria-label`

## D. Accessibility

- [ ] Tab доходит до всех действий; Enter/Space на кнопках
- [ ] `:focus-visible` виден (нет голого `outline: none`)
- [ ] Контраст текста ≈ 4.5:1 (крупный ≈ 3:1)
- [ ] Состояние не только цветом
- [ ] `prefers-reduced-motion` учтён, если есть анимация
- [ ] Hit target ≥ 24×24 CSS px (лучше ~44×44 на тач)
- [ ] Диалог: focus внутрь при открытии, возврат фокуса при закрытии, Esc/`close`

Детали: `a11y.md`.

## E. Layout & visual system

- [ ] Mobile-first; нет горизонтального скролла от фиксированных ширин
- [ ] Мысленно/в CSS: 320 / 768 / 1024
- [ ] Spacing из шкалы 4/8 — нет `13px` / `2.3rem`
- [ ] Цвета/радиусы/шрифт через токены (`:root`), не россыпь hex
- [ ] Максимум 2 радиуса в системе
- [ ] Нет AI-aesthetic (см. `anti-patterns.md`)
- [ ] Нет яичного copy (три сильные вещи / всё по делу / честный вкус / мета «не X, а Y»)
- [ ] Лендинг/оффер: факты (цена, SKU, часы, адрес), не презентация про секцию
- [ ] Нет empty void: hero с фото/сценой (не gradient-only дыра ≥70vh)

## F. Code artifact

- [ ] Fenced blocks с `path=/src/frontend/...`
- [ ] Есть entry (`index.html` или явно указанный)
- [ ] Нет секретов / API keys в клиенте
- [ ] Минимум зависимостей; UI-kit только по брифу
- [ ] Реалистичный русский copy (не lorem)
- [ ] Файл UI не комбайн 400+ строк без разбиения

## G. Studio handoff

- [ ] В ## Мышлении: ожидаемый API (method, path, JSON, ошибки) или явное допущение
- [ ] Стабильные accessible names для tests
- [ ] Design-токены не переписаны молча; конфликт назван

## H. Режимная планка

| Режим | Минимум |
|--------|---------|
| light | A + C (базово) + F (path) + happy; states можно кратко описать |
| standard | A–G без диалог-ловушек если диалога нет; B обязательно если async/список |
| ultra | A–G полностью + anti-patterns жёстко + готовность к склейке |
| premium | ultra + сверка с `examples/good_output.md` + a11y.md self-check |

## Ещё не done (стоп-фразы)

- «стили потом» / «a11y потом» / «это прототип»
- красивое описание без кода с `path=`
- empty экран без CTA
- фиолетовый градиент / Inter «по умолчанию» без брифа
