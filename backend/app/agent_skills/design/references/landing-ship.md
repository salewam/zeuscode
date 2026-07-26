# Design — Landing media + ship contract

Frontend **провалит gate**, если Handoff врёт про media или толкает placeholder-контакты.

## Media (обязательно для лендинга)

В `### Handoff frontend` ровно одна строка:

```text
Media: сюжет=<noun scene>; url=https://images.unsplash.com/…; remote OK, local file not required; veil=<side/opacity>; object-position=<…>
```

Правила:
1. Сюжет = конкретный noun под нишу (бокс / чашка / кресло), не «атмосфера».
2. **Дефолт = remote https** из Media pack / Product brief. Не выдумывай Unsplash ID.
3. `path=/src/frontend/assets/…` — **только** если FE сдаёт файл. Иначе = `missing_asset`.
4. Запрещён signature «пустой градиент / solid ≥70vh» без `url(https…)`.
5. Не штампуй один и тот же СТО-кадр всем брифам — бери URL из Media pack ниши.
## Контакты в Handoff

- Телефон из брифа, **не** `000-00-00`
- CTA labels = действие («Записаться», «Позвонить»), не egg-copy

## Tokens

- Сдай `/src/design/tokens.css` с полным `:root` + `:focus-visible`
- Frontend не должен зависеть от битого `@import`

## Бан в Handoff

| Плохо | Почему |
|-------|--------|
| `Media: потом` / без строки | empty_hero / no_hero_media |
| `assets/hero.jpg` без файла | missing_asset |
| Тел. `+7 (495) 000-00-00` | placeholder_contact |
| «три сильные вещи» в labels | egg_copy |
| solid navy hero «на потом фото» | no_hero_media |
