# Frontend — антиэталон (bad_output)

Так **нельзя**. Если похоже — перепиши до сдачи. Evidence Gate поймает.

---

## Кейс A: классический мусор

## Мышление
Сделаю красивый SaaS в стиле AI-стартапов.

## Результат
React + Tailwind, purple gradient, Inter, rounded-2xl, badges. Placeholder вместо label. Div onclick. Ошибки — красная рамка. Loading потом.

```html
<div onclick="login()" style="padding:13px">
  <input placeholder="Email" />
  <div class="btn">Click here</div>
</div>
```

---

## Кейс B: вербальный anti-AI + indigo (реальный фейл)

## Мышление
Anti-AI Aesthetic: никаких фиолетовых градиентов и Inter. Возьму Deep Indigo как у Linear/Vercel — это солидно, не AI-look.

## Результат

```css path=/src/frontend/styles.css
:root { --accent: #4f46e5; } /* indigo */
* { outline: none; }
body { font-family: Inter, system-ui; }
.hero { background: linear-gradient(135deg, #6366f1, #8b5cf6); }
```

```html path=/src/frontend/index.html
<input placeholder="Email" />
<button>Войти</button>
```

### Почему FAIL

| Симптом | Gate |
|---------|------|
| «Anti-AI» + Deep Indigo / `#4f46e5` / violet gradient | `ai_aesthetic` |
| Inter | `ai_aesthetic` |
| `* { outline: none }` без focus-visible | `outline_no_focus` |
| input без label | `input_no_label` |

Сравни с `good_output.md`.
