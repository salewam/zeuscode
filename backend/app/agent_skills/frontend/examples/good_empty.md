# Frontend — эталон empty + list states

Дополнение к `good_output.md` (логин). Копируй планку, не контент.

---

## Задача
«Список проектов: empty state с CTA. Vanilla.»

## Мышление
Один экран empty. CTA «Создать проект» = `<button>`. Токены без indigo. Handoff: click → `POST /api/projects` или navigate `/projects/new` (допущение).

## Результат

```html path=/src/frontend/index.html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Проекты</title>
  <link rel="stylesheet" href="./tokens.css" />
  <link rel="stylesheet" href="./styles.css" />
</head>
<body>
  <main class="page">
    <h1>Проекты</h1>
    <section class="empty" aria-labelledby="empty-title" id="list-root" data-state="empty">
      <h2 id="empty-title">Пока нет проектов</h2>
      <p>Создайте первый — чаты и файлы появятся здесь.</p>
      <button type="button" class="btn" id="create-project">Создать проект</button>
    </section>
  </main>
  <script type="module" src="./app.js"></script>
</body>
</html>
```

```css path=/src/frontend/tokens.css
:root {
  --color-bg: #12141a;
  --color-text: #eef1f6;
  --color-muted: #9aa3b2;
  --color-accent: #2dd4bf; /* teal, не indigo */
  --color-accent-ink: #042f2e;
  --font-sans: ui-sans-serif, system-ui, sans-serif;
  --space-2: 8px;
  --space-4: 16px;
  --space-5: 24px;
  --radius-sm: 6px;
  --focus-ring: 2px solid var(--color-accent);
}
```

```css path=/src/frontend/styles.css
body { margin: 0; font-family: var(--font-sans); background: var(--color-bg); color: var(--color-text); }
.page { max-width: 40rem; margin: 0 auto; padding: var(--space-5) var(--space-4); }
.empty p { color: var(--color-muted); }
.btn {
  min-height: 44px; border: 0; border-radius: var(--radius-sm);
  background: var(--color-accent); color: var(--color-accent-ink);
  font: inherit; font-weight: 600; cursor: pointer; padding: var(--space-2) var(--space-4);
}
.btn:focus-visible, a:focus-visible {
  outline: var(--focus-ring); outline-offset: 2px;
}
```

```js path=/src/frontend/app.js
document.getElementById("create-project")?.addEventListener("click", () => {
  // Studio Evidence smoke кликает button в srcdoc — не делай hard navigation.
  // Реальный роут пометь data-*; router подключит frontend в продукте.
  const btn = document.getElementById("create-project");
  if (btn) btn.dataset.intent = "/projects/new";
});
```

Самопроверка: path=, empty+CTA, teal не indigo, focus-visible есть, нет outline:none.
