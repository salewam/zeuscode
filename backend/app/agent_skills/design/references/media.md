# Design — Media / фото для лендингов

Пустой hero = FAIL. Для consumer-лендинга (кофейня, салон, магазин, услуга)
**обязан** быть предметный visual plane, не gradient-дыра.

## Как «находить» фото (без стока-абстракции)

1. Определи **сюжет** из задачи: продукт в руках, интерьер места, деталь ремесла.
2. Собери Unsplash Source URL:
   ```text
   https://images.unsplash.com/photo-{ID}?auto=format&fit=crop&w=2000&q=80
   ```
   Или поиск-запрос в Мышлении: `coffee cup latte art overhead`, `cafe interior warm wood`,
   `barber shop chair`, `bakery bread closeup` — конкретный noun, не `abstract gradient`.
3. В **Handoff frontend** укажи:
   - сюжет одним предложением
   - готовый URL **или** `path=/src/frontend/assets/hero-….jpg`
   - object-position (куда смотрит кадр)
   - veil: тёмный градиент снизу/слева для читаемости текста
4. Frontend **скачивает** фото в `/src/frontend/assets/` (локальный файл).
   Внешний-only Unsplash хрупкий (блокировки/CDN) → локальная копия обязательна для сдачи.

## Бан

- Hero только `linear-gradient` / blur blobs
- Stock «business handshake» / «random laptop» вне брифа
- Inset rounded photo card вместо full-bleed на промо-лендинге
- `min-height: 80vh+` без `<img>` / `url(assets/…)`

## Чеклист Handoff

- [ ] Сюжет media назван
- [ ] URL или local path дан
- [ ] Full-bleed + veil описаны
- [ ] Явно: «не оставлять пустое поле»
