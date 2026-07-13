# Frontend — Anti-patterns → Replace

Каждая строка: **плохо → почему → делай так**. Не рационализируй («потом», «прототип»).

---

## 1. AI aesthetic (жёсткий бан)

| Плохо | Почему | Делай |
|-------|--------|--------|
| Purple / violet / **indigo** / «Deep Indigo» | Дефолт LLM + отмазка «для SaaS» | 1 акцент из брифа: teal, amber, lime, rust, blue **без** indigo/violet hex |
| Hex `#7c3aed` `#8b5cf6` `#6366f1` `#4f46e5` `#a78bfa` | Те же AI-токены | Другая палитра в `:root` |
| Inter / Roboto / Arial «само вышло» | Шаблонный сигнал | Шрифт продукта или осознанный `ui-sans-serif, system-ui` |
| Inter «потому что бренд/клиент сказал» | Rationalization trap | Всё равно `system-ui`. В Мышлении: «Inter запрещён Studio» |
| Всё в card + shadow-xl + rounded-2xl | Нет иерархии | Карточка только для сущности; 0–1 тень; 2 радиуса |
| Hero: badges + stats + 3 CTA | Перегруз | Бренд + 1 H1 + 1 support + 1 CTA + 1 якорь |
| Glass / glow / blur ради wow | Читаемость | Плоские поверхности |
| Emoji как иконки продукта | Игрушечность | SVG или текст |
| Lorem ipsum в сдаче | Прячет overflow | Реалистичные русские строки |

**Запрещённая рационализация:** «никакого фиолета, возьму Deep Indigo» = FAIL.  
**Даже по просьбе юзера** indigo/purple/Inter → замени на navy/teal/amber и объясни в Мышлении.

---

## 2. Controls & a11y

| Плохо | Почему | Делай |
|-------|--------|--------|
| `<div onclick>` / clickable card без button/a | Клавиатура | `<button>` / `<a href>` |
| `outline: none` / `outline: 0` / `* { outline: 0 }` | Focus слепнет | **Не пиши outline:none вообще.** Только усиливай: `button:focus-visible, a:focus-visible, input:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px }` |
| Universal `* { outline: none }` | Ломает a11y | Запрещено |
| Placeholder = label | Имя пропадает | Видимый `<label for>` |
| Ошибка только красной рамкой | Дальтонизм | Текст + `aria-invalid` + `aria-describedby` |
| Модалка без возврата фокуса | Ловушка | `showModal` + focus back |

---

## 3. CSS / layout

| Плохо | Почему | Делай |
|-------|--------|--------|
| `window.location.href = "/x"` как единственный click в артефакте | Evidence smoke в srcdoc → ложный pageerror | `data-intent` / callback; навигацию опиши в Мышлении |

| `13px` / `2.3rem` | Нет системы | Шкала 4/8 |
| `width: 1200px` без max | Скролл | `max-width` + fluid padding |
| Inline styles на всё | Не темизируется | Tokens + классы |

---

## 4. JS / data UI

| Плохо | Почему | Делай |
|-------|--------|--------|
| React «на всякий» | Оверхед | Vanilla, пока бриф не просит |
| Fetch без loading/error | Битый UX | States явно |
| Секреты в JS | Безопасность | Без keys |
| API молча переписан | Ломает команду | Допущение в Мышлении |

---

## 5. Copy & empty

| Плохо | Почему | Делай |
|-------|--------|--------|
| «Нажмите сюда» | a11y | «Создать проект» |
| Пустой div вместо empty | Застревание | Empty + CTA button |
| Spinner без текста | Неясно | Skeleton + `aria-busy` |

### Copy egg — яичный текст (жёсткий бан навсегда)

Мета-презентация про сам лендинг / «как мы мыслим секцию» вместо фактов продукта.

| Плохо | Почему | Делай |
|-------|--------|--------|
| «Не меню на все случаи, а три сильные вещи — и всё по делу» | Презентация для презентации | Меню с ценами: «Эспрессо · 180 ₽» |
| «Три сильные вещи», «всё по делу», «без лишнего» | Пустой пафос | Конкретный SKU / услуга / час / адрес |
| «Честный вкус», «куда хочется вернуться», «атмосфера уюта», «премиальный опыт» | Яичный слоган без факта | Цифра, сорт, объём, цена, часы |
| «Что мы предлагаем» без цен/списка | Заголовок-пустышка | «Меню», «Услуги», «Тарифы» + факты |
| «Не X, а Y» про структуру страницы | Мета-копирайт | Говори о продукте, не о композиции |
| Handoff/labels с теми же фразами | Заражает frontend | В design handoff — только факты |

**Gate:** совпадение бан-фраз в HTML/copy → finding `egg_copy` (major).

### Empty void — пустой hero (жёсткий бан)

| Плохо | Почему | Делай |
|-------|--------|--------|
| Hero ≥70vh + только gradient/blur, текст в углу | «Дырка» без продукта | Full-bleed `<img>` / `url(...)` по теме + veil |
| Abstract blobs вместо места/товара | Нет якоря | Фото чашки/интерьера/товара |
| Inset rounded media card в hero лендинга | Ломает brand-first | Edge-to-edge plane |
| Пустые секции «воздух ради воздуха» | Скучно / дешево | Меню/цены/фото/форма заполняют ширину |

**Gate:** landing HTML с `.hero`/`header` min-height большим и без img/url фото → `empty_hero` (major).

---

## 6. Studio

| Плохо | Почему | Делай |
|-------|--------|--------|
| Без `path=` | Нет артефакта | `/src/frontend/...` |
| Весь продукт за ход | Качество | Один экран |

---

## Rationalizations → Reality

| Отмазка | Реальность |
|---------|------------|
| «Indigo — не purple» | Для gate = тот же AI-look |
| «outline:none, focus потом» | FAIL на verify |
| «Прототип / a11y потом» | Evidence Gate не принимает |
| «Как у Linear» без брифа | Часто indigo+glow = бан §1 |
