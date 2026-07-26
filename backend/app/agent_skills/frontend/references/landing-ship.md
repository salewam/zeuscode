# Landing ship — DoD (жёстко)

Лендинг/сайт услуги **не сдан**, пока Evidence Gate не проходит эти коды:
`missing_asset` · `placeholder_contact` · `broken_css_import` · `api_orphan` · `fake_form_success`.

## Контакты

- Телефон реалистичный из брифа (`+7 (9xx) …`), **не** `000-00-00` / `555-01-01` / чужой штамп эталона
- `tel:` совпадает с видимым номером
- Адрес/часы — факты из брифа, не `example.com`

## Media / hero

- **Обязателен** remote `url(https://…)` или `<img src="https://…">` на `.hero` (иначе `no_hero_media`)
- СТО: бери URL из Product brief / design Handoff, не выдумывай
- Если в CSS `url('assets/…')` / `<img src="assets/…">` → **файл обязан** быть артефактом (иначе `missing_asset`)
- Предпочтение: remote Unsplash; не пиши локальный path «на бумаге»
- Hero не скелет: не один navy block без фото + без ≥4 секций (`thin_landing`)

## CSS / tokens

- Не оставляй `@import '../design/tokens.css'` как единственный источник палитры, если не уверен что design сдал tokens
- Надёжно: скопируй `:root` в `styles.css` **или** положи полный styles самодостаточным
- Studio filter вклеит tokens при наличии design — но preview ломается на голом `@import` без файла

## Форма + API

| Есть backend route | Делай |
|--------------------|--------|
| Да (`/api/booking` и т.п.) | `fetch` + `Content-Type: application/json` + ветка `!response.ok` → error UI |
| Нет | Offline-stub: `localStorage` / console; UI: «демо, заявка сохранена локально» — **не** «принята мастером» |

**Бан:** в `catch` показывать «Заявка принята/отправлена» / «мы свяжемся» как успех.  
**Бан:** `preventDefault` + success-текст без `fetch` и без честного offline-лейбла.

## Цены / бриф

- Цены и бренд из Product brief / Locked API — не выдумывай параллельный прайс
- Footer год = текущий (не 2024 «из привычки»)

## Наполнение (анти-скелет)

- ≥4 `<section>` (или смысловых блока: hero / услуги / шаги / форма / контакты)
- ≥4 услуги с ценой «от» если бриф СТО/услуга
- HTML лендинга не «пустая оболочка» (gate: `thin_landing`)

## Publish + Zeus badge (обязательно)

См. `publish.md`. Коротко:
- бейдж `Сделано на ZeusCode` (класс `zeus-badge`) внизу
- живая ссылка `https://zeuscode.ru/go/…/` в Результате
- без ссылки лендинг **не сдан**

## Self-check перед сдачей

- [ ] нет `000-00-00`
- [ ] hero с `url(https://…)` или img https
- [ ] нет `url(assets/…)` без артефакта файла
- [ ] ≥4 секции + услуги из брифа
- [ ] форма: fetch→ошибка **или** честный offline
- [ ] catch не врёт успехом
- [ ] есть `zeus-badge` / «Сделано на ZeusCode»
- [ ] есть / указан `zeuscode.ru/go/…`
