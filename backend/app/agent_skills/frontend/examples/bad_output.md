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

---

## Кейс C: «красивый» лендинг который gate убивает (реальный фейл STO)

## Мышление
Сделаю автосервис: hero с фото, форма booking, успех даже если API упадёт — для демо ок.

## Результат

```css path=/src/frontend/styles.css
@import url('../design/tokens.css');
.hero {
  min-height: 80vh;
  background: linear-gradient(#0008,#0008), url('assets/hero-workshop.jpg');
}
```

```html path=/src/frontend/index.html
<a href="tel:+74950000000">+7 (495) 000-00-00</a>
<form id="booking-form">
  <label for="name">Имя</label><input id="name" name="name" />
  <button type="submit">Отправить</button>
</form>
```

```js path=/src/frontend/app.js
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const r = await fetch('/api/booking', { method: 'POST', body: '{}' });
    if (!r.ok) throw new Error('x');
  } catch (err) {
    status.textContent = 'Заявка отправлена. Мы свяжемся с вами.';
  }
});
```

### Почему FAIL (не PASS@100)

| Симптом | Gate |
|---------|------|
| `000-00-00` | `placeholder_contact` |
| `assets/hero-workshop.jpg` без файла | `missing_asset` |
| `@import` tokens без файла | `broken_css_import` |
| `fetch('/api/booking')` без backend | `api_orphan` |
| success в `catch` | `fake_form_success` |

**Правильно:** номер из брифа; remote https или реальный asset-файл; inline `:root`; backend route **или** offline без вранья; в catch — ошибка.
