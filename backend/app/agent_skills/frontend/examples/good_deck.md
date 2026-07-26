# Good example — HTML deck (презентация)

8 слайдов, **разные** remote фото, факты. Путь: `/src/deck/`.

```html path=/src/deck/index.html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Питч — Проект</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <main class="deck">
    <section class="slide slide--hero" style="--bg:url('https://images.unsplash.com/photo-1522071820081-009f0129c71c?auto=format&fit=crop&w=1600&q=80')">
      <p class="brand">Проект</p>
      <h1>Оффер одной строкой</h1>
      <p>1 факт: срок / рынок / результат</p>
    </section>
    <section class="slide">
      <h2>Проблема</h2>
      <ul><li>Боль 1</li><li>Боль 2</li><li>Боль 3</li></ul>
    </section>
    <section class="slide slide--photo" style="--bg:url('https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=1600&q=80')">
      <h2>Решение</h2>
      <ul><li>Что</li><li>Для кого</li><li>Чем лучше</li></ul>
    </section>
    <section class="slide">
      <h2>Как работает</h2>
      <ol><li>Шаг 1</li><li>Шаг 2</li><li>Шаг 3</li></ol>
    </section>
    <section class="slide slide--photo" style="--bg:url('https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=1600&q=80')">
      <h2>Доказательства</h2>
      <p class="stat">N клиентов · X недель до запуска</p>
      <blockquote>Короткий отзыв с именем.</blockquote>
    </section>
    <section class="slide">
      <h2>Оффер</h2>
      <p>Пакет от N ₽ · что входит · срок</p>
    </section>
    <section class="slide">
      <h2>Почему мы</h2>
      <ul><li>Факт 1</li><li>Факт 2</li><li>Факт 3</li></ul>
    </section>
    <section class="slide">
      <h2>Дальше</h2>
      <a class="btn" href="tel:+74952113456">+7 (495) 211-34-56</a>
      <p>Созвон · ответ в будни до 18:00</p>
    </section>
  </main>
  <script src="app.js"></script>
</body>
</html>
```

```css path=/src/deck/styles.css
:root { --ink:#111; --paper:#f7f5f0; --accent:#b45309; --focus:#b45309; }
* { box-sizing: border-box; }
body { margin: 0; font-family: Georgia, system-ui, sans-serif; color: var(--ink); background: #111; }
.slide { min-height: 100vh; padding: 3rem 1.5rem; display: flex; flex-direction: column; justify-content: center; background: var(--paper); }
.slide--hero, .slide--photo {
  color: #fff;
  background-image: linear-gradient(rgba(0,0,0,.55), rgba(0,0,0,.45)), var(--bg);
  background-size: cover; background-position: center;
}
.btn { display: inline-block; padding: .9rem 1.4rem; background: var(--accent); color: #fff; text-decoration: none; border-radius: 4px; font-weight: 700; }
:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }
```

```js path=/src/deck/app.js
const slides = [...document.querySelectorAll(".slide")];
let i = 0;
const go = (n) => { i = Math.max(0, Math.min(slides.length - 1, n)); slides[i].scrollIntoView({ behavior: "smooth" }); };
window.addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); go(i + 1); }
  if (e.key === "ArrowUp" || e.key === "ArrowLeft") { e.preventDefault(); go(i - 1); }
});
```
