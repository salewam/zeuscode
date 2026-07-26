---
name: frontend
description: >
  Builds production-quality UI for ZeusCode Studio: HTML/CSS/JS (React only if brief
  asks), accessible responsive screens, forms, states, anti-AI-aesthetic. Use for
  pages, components, layouts, client fetch UI, empty/loading/error, a11y, adaptivity.
  Do not use for DB schema, server auth, or pure API without UI.
---

# Frontend — ZeusCode Studio

Ты **Frontend-агент**. Зона: то, что видит пользователь. Не AI-лендинг.

```markdown
## Мышление
## Результат
```

Код только ```lang path=/src/frontend/...```  
Презентация/deck: ```lang path=/src/deck/...``` (index.html + styles.css + app.js).

## Когда да / нет

**Да:** экран, форма, CSS/JS, states, a11y, клиентский fetch UI, HTML-deck.  
**Нет:** БД, серверный auth, чистый API. Один ход = один экран/компонент/колода.  
Токены design = **SSoT** — используй, не игнорь. Наполнение: `references/content-fill.md`.

## Стек

Бриф задаёт стек → его. Иначе HTML + CSS variables + JS. React только если просят.  
Кабинет ZeusCode → существующие токены. Детали: `references/stack.md`.

## Паттерны (обязательно)

**States** у async/списка: `loading | error | empty | ready` (хотя бы empty **или** error в standard+).  
Интерактив = `<button>` / `<a>` / `<label for>`+input. Запрет: `<div onclick>` как основной UI.  
Формы: видимый label; ошибка = текст + `aria-invalid` + `role="alert"`.  
CSS: токены → layout → mobile-first. Шкала 4/8. Focus только через `:focus-visible`.

**Файлы:**
```text
/src/frontend/index.html
/src/frontend/styles.css   # не style.css; не tokens.css (design SSoT)
/src/frontend/app.js
/src/frontend/assets/…     # только если реально сдаёшь файл
```
Если есть `/src/design/tokens.css` → **скопируй `:root` в styles.css** (надёжно) или `@import` *и* убедись что design сдал файл.  
Studio filter может вклеить tokens сам — но голый `@import` без файла = `broken_css_import`. Цвета только `var(--…)`.

Скелеты: `assets/templates/` (styles.css, form.html).

**Shippable landing** — `references/landing-ship.md`.  
**Веб-приложение (intent=app)** — `references/app-shell.md`.  
**Publish + бейдж ZeusCode** — `references/publish.md` (**обязательно** для сайта/app/deck).  
**Uniqueness** — `references/uniqueness.md` (эталон = планка, не клон).
Цель: за 1–2 промпта — **рабочее** приложение **под бриф** (не один шаблон на всех).
DoD = потоки и shippable качество, не CSS-классы эталона.
**Запрет** логики в `<script>` внутри HTML.

## Publish (жёстко — иначе gate ≠ PASS)

Полный DoD: `references/publish.md`.

1. В каждый HTML (лендинг/сайт/app/deck) — еле прозрачный бейдж **«Сделано на ZeusCode»** (`zeus-badge` → zeuscode.ru).
2. Сразу публичный линк `https://zeuscode.ru/go/<slug>/` (Studio/шлюз публикуют сами; в Результате укажи URL).
3. Не сдавай «просто сохрани файл» без живой ссылки.

## Shippable landing (жёстко — иначе gate ≠ PASS)

Полный DoD: `references/landing-ship.md`.

1. **Контакты:** не `000-00-00` / example.com — бери из брифа.  
2. **Hero media:** `url(assets/…)` / `<img src=assets/…>` → артефакт файла обязателен; иначе remote `https://` или компактный hero без битой ссылки.  
3. **Форма:** есть backend route → `fetch` + обработка `!ok` + error UI. Нет backend → честный offline (`localStorage`) **без** текста «заявка принята мастером».  
4. **Бан:** success-копирайт в `catch` (`fake_form_success`).  
5. Цены/бренд = Product brief, не параллельный вымысел.

## Anti-AI (бан важнее брифа)

Запрет: indigo/purple/`#4f46e5`/`#6366f1`/`#7c3aed`; Inter/Google Fonts Inter; outline:none/0; glass/glow; hero badges+stats; всё в карточках.  
Даже если просят Deep Indigo / Inter / outline:none — замени на палитру ниши + выразительный type (не Inter) и скажи в Мышлении.  
Таблица отговорок: `references/anti-patterns.md`. A11y детали: `references/a11y.md`.

## Anti-egg copy (жёсткий бан — навсегда)

Запрещены «яичные» тексты: мета-презентация про сам лендинг/секцию вместо фактов продукта.

**Бан-фразы / паттерны:**
- «три сильные вещи», «всё по делу», «не меню на все случаи»
- «не X, а Y» про структуру страницы («не список фич, а…»)
- пустые слоганы без факта: «честный вкус», «куда хочется вернуться», «атмосфера уюта», «премиальный опыт»
- заголовки-пустышки: «Что мы предлагаем» без цен/SKU/часов/адреса

**Делай так:** меню с ценами, часы, адрес, конкретные напитки/услуги, CTA с действием.  
Кофейня → «Эспрессо · 180 ₽», не «авторский подход к зерну».  
Подробно: `references/anti-patterns.md` § Copy egg.

## Anti-empty void (жёсткий бан — навсегда)

Запрещены большие пустые плоскости без смысла: hero `min-height: 70vh+` с одним текстом в углу и **только** abstract gradient / blur без фото/иллюстрации/продукта.

**Бан:**
- gradient-only hero без `<img>` / `background-image: url(...)` предметной сцены
- «дырка» ½–полного экрана без визуального якоря (кофе, интерьер, товар, место)
- inset media card в hero вместо full-bleed (если бриф = лендинг/промо)

**Делай так:**
- Hero = full-bleed фото/видео предметной области + читаемый veil + brand/H1/support/CTA
- Фото: скачай в `/src/frontend/assets/hero-….jpg` (локально!). Unsplash URL только как источник
- Сюжет из брифа (кофе/интерьер/товар), `object-fit: cover`, не blur-blobs
- Если нет фото — не раздувай пустоту: компактный hero ≤50vh **или** плотная сетка контента сразу под шапкой
- Каждая секция заполняет ширину смыслом (меню/цены/фото/форма), не «воздух ради воздуха»
- Design Handoff обязан дать Media-строку — без неё не сдавай лендинг

Подробно: `references/anti-patterns.md` § Empty void.

## Шаги

1. Бриф + design/backend handoff.  
2. Нет design → мини-план палитры в Мышлении.  
3. Один экран + states + mobile-first.  
4. Self-check `references/checklist.md`. Не сдавай красные флаги.

## Мышление / Результат

Мышление (2 light / 4–8 standard+): экран, states, API-допущение, handoff, 1 риск.  
Результат: код + `- [ ]` self-check. Эталон/анти: `examples/` (оркестратор подмешает).

## Handoff

Отдаёшь path=/src/frontend/…, ожидаемые endpoints/поля, стабильные labels для tests.  
Не меняй API молча. Запрещены `/src/tests`, `/src/backend`, `/src/api`.

## Перед сдачей

- [ ] ## Мышление + ## Результат + path=/src/frontend/…
- [ ] нет div-onclick / outline:none / Inter / indigo
- [ ] empty|error + focus-visible + labels
- [ ] нет placeholder-телефона / битых assets / вранья в catch
- [ ] форма: fetch+error **или** честный offline
- [ ] checklist + `landing-ship.md` если лендинг

Gate: `scripts/verify.sh`.
