# Frontend — эталон (good_output)

Копируй **структуру и планку**, не контент один-в-один.

---

## Задача

«Экран входа: email + пароль, Войти. Loading и error. Стек по умолчанию. Не кабинет ZeusCode — нейтральный тёмный продукт.»

---

## Мышление

Один экран `/src/frontend/`. Vanilla + токены. Состояния: default, loading (disabled + «Входим…»), error (`role="alert"`). API-допущение: `POST /api/auth/login` `{email,password}` → 200 redirect `/app`, 401 — «Неверный email или пароль». Labels видимые. Mobile-first. Отдаю backend контракт; tests смогут найти кнопку «Войти» и поля по label.

## Результат

```html path=/src/frontend/index.html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Вход</title>
  <link rel="stylesheet" href="./tokens.css" />
  <link rel="stylesheet" href="./styles.css" />
</head>
<body>
  <a class="skip-link" href="#main">К содержимому</a>
  <main id="main" class="auth">
    <h1 class="auth__title">Вход</h1>
    <p class="auth__lead">Войдите, чтобы продолжить работу.</p>
    <form class="auth__form" id="login-form" novalidate>
      <div class="field">
        <label for="email">Email</label>
        <input id="email" name="email" type="email" autocomplete="username" required />
      </div>
      <div class="field">
        <label for="password">Пароль</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required />
      </div>
      <p class="form-error" id="form-error" role="alert" hidden></p>
      <button type="submit" class="btn" id="submit-btn">Войти</button>
    </form>
  </main>
  <script type="module" src="./app.js"></script>
</body>
</html>
```

```css path=/src/frontend/tokens.css
:root {
  --color-bg: #12141a;
  --color-surface: #1c212b;
  --color-border: #2e3645;
  --color-text: #eef1f6;
  --color-muted: #9aa3b2;
  --color-accent: #3d9cf0;
  --color-accent-ink: #0b1220;
  --color-danger: #f07178;
  --font-sans: "Source Sans 3", ui-sans-serif, system-ui, sans-serif;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --radius-sm: 6px;
  --radius-md: 12px;
  --focus-ring: 2px solid var(--color-accent);
  --focus-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

```css path=/src/frontend/styles.css
*, *::before, *::after { box-sizing: border-box; }

body {
  margin: 0;
  min-height: 100dvh;
  font-family: var(--font-sans);
  color: var(--color-text);
  background:
    radial-gradient(900px 480px at 0% 0%, #1a2438 0%, transparent 55%),
    var(--color-bg);
  line-height: 1.5;
}

.skip-link {
  position: absolute;
  left: -999px;
  top: 0;
  background: var(--color-accent);
  color: var(--color-accent-ink);
  padding: var(--space-2) var(--space-3);
  z-index: 10;
}
.skip-link:focus { left: var(--space-2); top: var(--space-2); }

.auth {
  max-width: 22.5rem;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4);
}

.auth__title {
  margin: 0 0 var(--space-2);
  font-size: 1.75rem;
  line-height: 1.2;
}
.auth__lead {
  margin: 0 0 var(--space-5);
  color: var(--color-muted);
}

.field {
  display: grid;
  gap: var(--space-1);
  margin-bottom: var(--space-4);
}
.field label {
  font-size: 0.875rem;
  color: var(--color-muted);
}
.field input {
  min-height: 44px;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  font: inherit;
}
.field input:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
}

.form-error {
  margin: 0 0 var(--space-3);
  color: var(--color-danger);
  font-size: 0.875rem;
}
.form-error[hidden] { display: none; }

.btn {
  width: 100%;
  min-height: 44px;
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--color-accent);
  color: var(--color-accent-ink);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.btn:disabled { opacity: 0.65; cursor: not-allowed; }
.btn:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 3px;
}
```

```js path=/src/frontend/app.js
const form = document.getElementById("login-form");
const errEl = document.getElementById("form-error");
const btn = document.getElementById("submit-btn");

function showError(msg) {
  errEl.hidden = !msg;
  errEl.textContent = msg || "";
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  showError("");
  btn.disabled = true;
  btn.textContent = "Входим…";
  const body = {
    email: form.email.value.trim(),
    password: form.password.value,
  };
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      showError(
        res.status === 401
          ? "Неверный email или пароль."
          : "Не удалось войти. Попробуйте ещё раз."
      );
      return;
    }
    window.location.href = "/app";
  } catch {
    showError("Сеть недоступна. Проверьте соединение.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Войти";
  }
});
```

Самопроверка:
- [ ] ## Мышление / ## Результат + path=
- [ ] labels, focus-visible, alert на ошибке
- [ ] loading + error
- [ ] не purple/Inter AI-look

Почему эталон: короткий handoff, полный рабочий код, состояния, a11y, своя палитра (не lime кабинета и не фиолет).
