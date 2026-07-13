# Design — Stack

Дефолт: design contract light, не Figma-spec и не полный Aura.

## Артефакты

- `tokens.css` — базовые CSS variables
- layout notes — структура, max-width, rhythm, responsive behavior
- state notes — loading / empty / error / ready
- handoff — что frontend обязан сохранить

## Формат кода

```css path=/src/design/tokens.css
:root {
  --color-bg: #f7f4ee;
}
```

Не добавляй JS, API и тесты в design pack.
