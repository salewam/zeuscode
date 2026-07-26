# Good example — лендинг СТО (ПЛАНКА КАЧЕСТВА ДЛЯ АВТО-НИШИ)

**Это один пример для автосервиса.** Не сдавай «МоторХаус» / эти классы / эту палитру другим брендам и нишам.
Структура ниже — ориентир плотности. Бренд/адрес/H1/отзывы/прайс/IA — **только** из UNIQUE брифа.
Другая ниша (кофе, клиника, SaaS) → свой каркас, см. `uniqueness.md`.

Must для авто-примера: живой hero-фото, визуальный ряд, услуги с фактами, форма без лжи.
```html path=/src/frontend/index.html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>МоторХаус — Автосервис полного цикла в Москве</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <header class="top">
    <a class="brand" href="#top">МоторХаус</a>
    <nav class="top__nav">
      <a href="#vitrine">Бокс</a>
      <a href="#services">Услуги</a>
      <a href="#booking">Запись</a>
      <a class="tel" href="tel:+74951204567">+7 (495) 120-45-67</a>
    </nav>
  </header>

  <main>
    <section class="hero" id="top">
      <div class="hero__inner">
        <p class="eyebrow">Каширское ш., 31с1 · запись на сегодня</p>
        <h1>Все виды ремонта и ТО — один бокс</h1>
        <p class="lead">Диагностика, ходовая, шины, электрика, кузов. Мастер перезвонит за 15 минут — смета до старта работ.</p>
        <div class="hero__cta">
          <a class="btn" href="#booking">Записаться на ремонт</a>
          <a class="btn btn--ghost" href="tel:+74951204567">Позвонить мастеру</a>
        </div>
      </div>
    </section>

    <section id="vitrine" class="wrap">
      <h2>Бокс и работы</h2>
      <p class="sub">Реальный бокс на Каширском — кадры участка, не абстрактный градиент.</p>
      <div class="vitrine">
        <figure>
          <img src="https://images.unsplash.com/photo-1486006920555-c77dcf18193c?auto=format&fit=crop&w=1000&q=80" alt="Работы в боксе" width="800" height="520" loading="lazy" />
          <figcaption>Работы в боксе</figcaption>
        </figure>
        <figure>
          <img src="https://images.unsplash.com/photo-1558618666-fcd25c85cd64?auto=format&fit=crop&w=1000&q=80" alt="Шиномонтаж" width="800" height="520" loading="lazy" />
          <figcaption>Шины и диски</figcaption>
        </figure>
        <figure>
          <img src="https://images.unsplash.com/photo-1487754180451-c456f719a1fc?auto=format&fit=crop&w=1000&q=80" alt="Инструменты" width="800" height="520" loading="lazy" />
          <figcaption>Верстак и инструмент</figcaption>
        </figure>
      </div>
    </section>

    <section id="services" class="wrap">
      <h2>Услуги и цены</h2>
      <p class="sub">Цены «от» — точная смета после осмотра, без скрытых доплат в разговоре.</p>
      <div class="grid">
        <article>
          <h3>Диагностика</h3>
          <p>Компьютерная диагностика + осмотр на подъёмнике. Отчёт с кодами ошибок и рекомендациями — на руки.</p>
          <ul><li>сканер OBD</li><li>осмотр ходовой</li><li>письменный отчёт</li></ul>
          <p class="price">от 1 500 ₽</p>
        </article>
        <article>
          <h3>ТО по регламенту</h3>
          <p>Плановое ТО по карте завода: масло, фильтры, жидкости. Подбираем расходники под марку — без «универсального» масла наугад.</p>
          <ul><li>масло + фильтр</li><li>проверка уровней</li><li>сброс сервиса</li></ul>
          <p class="price">от 4 500 ₽</p>
        </article>
        <article>
          <h3>Ходовая / тормоза</h3>
          <p>Стук, увод, скрип колодок — диагностируем и меняем узлы. Запчасти отдельно; цену работ фиксируем до старта.</p>
          <ul><li>диагностика подвески</li><li>тормоза</li><li>сход-развал по запросу</li></ul>
          <p class="price">от 2 500 ₽</p>
        </article>
        <article>
          <h3>Шиномонтаж</h3>
          <p>Сезонная переобувка R15–R21, балансировка, проверка давления. Хранение комплекта — по договорённости.</p>
          <ul><li>монтаж/демонтаж</li><li>балансировка</li><li>вентиль</li></ul>
          <p class="price">от 1 800 ₽</p>
        </article>
        <article>
          <h3>Электрика</h3>
          <p>Не заводится, сел аккумулятор, ошибки ECU, генератор, стартер. Ищем причину прибором, не меняем «всё подряд».</p>
          <ul><li>поиск обрыва</li><li>генератор/стартер</li><li>работа с ECU</li></ul>
          <p class="price">от 2 000 ₽</p>
        </article>
        <article>
          <h3>Кузов / полировка</h3>
          <p>Локальный ремонт после ДТП или сколов: шпаклёвка, покраска элемента, полировка. Оценка после осмотра.</p>
          <ul><li>осмотр + смета</li><li>локальный ремонт</li><li>полировка</li></ul>
          <p class="price">от 5 000 ₽</p>
        </article>
      </div>
    </section>

    <section id="steps" class="wrap band">
      <h2>Как записаться</h2>
      <ol class="steps">
        <li><strong>Заявка</strong> — форма ниже, 1 минута</li>
        <li><strong>Звонок мастера</strong> — обычно до 15 минут в рабочие часы</li>
        <li><strong>Слот в боксе</strong> — приезжаете к назначенному времени</li>
      </ol>
    </section>

    <section id="why" class="wrap why">
      <div class="why__media">
        <img src="https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?auto=format&fit=crop&w=1200&q=80" alt="Диагностика автомобиля" width="900" height="600" loading="lazy" />
      </div>
      <div class="why__copy">
        <h2>Почему МоторХаус</h2>
        <ul class="facts">
          <li>90 дней гарантии на выполненные работы</li>
          <li>Оригинал или проверенный аналог — на ваш выбор</li>
          <li>Фотоотчёт по запросу в мессенджер</li>
        </ul>
        <a class="btn" href="#booking">Оставить заявку</a>
      </div>
    </section>

    <section id="reviews" class="wrap band">
      <h2>Отзывы</h2>
      <div class="reviews">
        <blockquote>
          <p>Сделали ходовую за день, цену назвали до начала работ — без сюрпризов на кассе.</p>
          <cite>Игорь · Toyota Camry</cite>
        </blockquote>
        <blockquote>
          <p>Записался вечером через форму — утром уже приняли на подъёмник, без очереди.</p>
          <cite>Марина · Kia Rio</cite>
        </blockquote>
        <blockquote>
          <p>По электрике нашли проблему с генератором за час, поставили оригинал.</p>
          <cite>Алексей · VW Polo</cite>
        </blockquote>
      </div>
    </section>

    <section id="faq" class="wrap">
      <h2>Частые вопросы</h2>
      <details open><summary>Можно приехать без записи?</summary><p>Да. Онлайн-слот быстрее: мастер обычно отвечает за 15 минут.</p></details>
      <details><summary>Чьи запчасти ставите?</summary><p>Оригинал или аналог на выбор — фиксируем в заказ-наряде.</p></details>
      <details><summary>Какая гарантия?</summary><p>90 дней на работы; по запчастям — условия поставщика.</p></details>
    </section>

    <section id="booking" class="wrap booking">
      <div>
        <h2>Запись на сервис</h2>
        <p class="sub">Ответим в рабочие часы. Поля как в API booking.</p>
      </div>
      <form id="booking-form" novalidate>
        <label for="name">Имя</label>
        <input id="name" name="name" autocomplete="name" required />
        <label for="phone">Телефон</label>
        <input id="phone" name="phone" type="tel" autocomplete="tel" required />
        <label for="car">Марка / модель</label>
        <input id="car" name="car" required />
        <label for="service">Услуга</label>
        <select id="service" name="service" required>
          <option>Диагностика</option>
          <option>ТО по регламенту</option>
          <option>Ходовая / тормоза</option>
          <option>Шиномонтаж</option>
          <option>Электрика</option>
          <option>Кузов / полировка</option>
        </select>
        <label for="slot">Удобный слот</label>
        <input id="slot" name="slot" placeholder="Завтра 14:00" required />
        <button type="submit" class="btn">Отправить заявку</button>
        <p id="form-msg" role="alert" hidden></p>
      </form>
    </section>
  </main>

  <footer class="foot">
    <div class="wrap foot__inner">
      <p><strong>МоторХаус</strong> · Москва, Каширское ш., 31с1</p>
      <p>Пн–Сб 09:00–21:00 · Вс 10:00–18:00</p>
      <a class="tel" href="tel:+74951204567">+7 (495) 120-45-67</a>
    </div>
  </footer>
  <script src="app.js"></script>
</body>
</html>
```

```css path=/src/frontend/styles.css
:root {
  --asphalt: #1a1c1e;
  --shop: #f3f1ec;
  --band: #e4e0d6;
  --amber: #c47a2c;
  --amber-hover: #a86520;
  --metal: #c5c9ce;
  --card: #ffffff;
  --focus: #c47a2c;
  --radius: 10px;
  --max: 1100px;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--shop);
  color: var(--asphalt);
  font-family: system-ui, sans-serif;
  line-height: 1.55;
}
.top {
  position: sticky; top: 0; z-index: 20;
  display: flex; justify-content: space-between; align-items: center;
  gap: 1rem; padding: .85rem 1.25rem;
  background: rgba(243,241,236,.94); backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--metal);
}
.brand {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 1.35rem; font-weight: 700; text-decoration: none; color: inherit;
}
.top__nav { display: flex; flex-wrap: wrap; gap: .85rem 1.1rem; align-items: center; font-size: .95rem; }
.top__nav a { color: var(--asphalt); text-decoration: none; font-weight: 600; }
.top__nav a:hover { color: var(--amber); }
.tel, .top__nav a.tel { color: var(--amber); font-weight: 700; text-decoration: none; }
.hero {
  min-height: 78vh;
  display: flex; align-items: center;
  color: #fff;
  background:
    linear-gradient(90deg, rgba(26,28,30,.78) 0%, rgba(26,28,30,.4) 45%, rgba(26,28,30,.12) 100%),
    url("https://images.unsplash.com/photo-1486262715619-67b85e0b08d3?auto=format&fit=crop&w=2000&q=80")
      center 40% / cover no-repeat;
}
.hero__inner { padding: 4rem 1.25rem; max-width: 40rem; }
.eyebrow { letter-spacing: .04em; text-transform: uppercase; font-size: .78rem; opacity: .85; margin: 0 0 .75rem; }
.hero h1 {
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(2rem, 5vw, 3.1rem);
  line-height: 1.15; margin: 0 0 .75rem;
}
.lead { font-size: 1.1rem; opacity: .92; margin: 0 0 1.5rem; }
.hero__cta { display: flex; flex-wrap: wrap; gap: .75rem; }
.btn {
  display: inline-block; padding: .95rem 1.55rem;
  background: var(--amber); color: #fff; border: 0; border-radius: var(--radius);
  font-weight: 700; text-decoration: none; cursor: pointer;
  transition: background .15s ease, transform .15s ease;
}
.btn:hover { background: var(--amber-hover); transform: translateY(-1px); }
.btn--ghost { background: transparent; border: 1px solid rgba(255,255,255,.85); color: #fff; }
.btn--ghost:hover { background: rgba(255,255,255,.12); }
.wrap { width: min(100% - 2rem, var(--max)); margin: 0 auto; padding: 3.25rem 0; }
.band { background: var(--band); width: 100%; }
.band > .wrap, .band.wrap { width: min(100% - 2rem, var(--max)); }
h2 { font-family: Georgia, serif; font-size: clamp(1.5rem, 3vw, 2rem); margin: 0 0 .5rem; }
.sub { margin: 0 0 1.5rem; color: #4b5563; max-width: 40rem; }
.vitrine {
  display: grid; gap: 1rem;
  grid-template-columns: repeat(3, 1fr);
}
.vitrine img {
  width: 100%; height: 280px; object-fit: cover;
  border-radius: var(--radius); display: block;
}
.vitrine figcaption { font-size: .85rem; margin-top: .4rem; color: #4b5563; }
.grid {
  display: grid; gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}
.grid article {
  background: var(--card); padding: 1.25rem 1.35rem;
  border: 1px solid var(--band); border-radius: var(--radius);
  transition: transform .15s ease, box-shadow .15s ease;
}
.grid article:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(26,28,30,.08); }
.grid article h3 { margin: 0 0 .5rem; font-size: 1.1rem; }
.grid article p { margin: 0; }
.grid article ul { margin: .65rem 0 0; padding-left: 1.1rem; color: #4b5563; font-size: .92rem; }
.price { font-weight: 800; color: var(--amber); margin: .75rem 0 0; }
.steps { margin: 0; padding-left: 1.2rem; display: grid; gap: .65rem; }
.why { display: grid; grid-template-columns: 1.1fr 1fr; gap: 2rem; align-items: center; }
.why__media img {
  width: 100%; height: 340px; object-fit: cover;
  border-radius: var(--radius); display: block;
}
.facts { margin: 0 0 1.25rem; padding-left: 1.1rem; }
.reviews { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
blockquote {
  margin: 0; padding: 1.1rem 1.2rem; background: var(--card);
  border-left: 3px solid var(--amber); border-radius: 0 var(--radius) var(--radius) 0;
}
blockquote p { margin: 0 0 .75rem; }
cite { font-style: normal; font-size: .9rem; color: #4b5563; }
details { border-bottom: 1px solid var(--metal); padding: .85rem 0; }
summary { cursor: pointer; font-weight: 600; }
.booking form { display: grid; gap: .65rem; max-width: 28rem; }
label { font-weight: 600; font-size: .9rem; }
input, select {
  padding: .75rem .85rem; border: 1px solid var(--metal);
  border-radius: var(--radius); background: #fff; font: inherit;
}
#form-msg { margin-top: .75rem; font-weight: 600; }
.foot {
  background: var(--asphalt); color: #f3f1ec; padding: 2rem 0;
}
.foot__inner { display: grid; gap: .35rem; }
.foot .tel { color: #f0b36a; }
button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible {
  outline: 2px solid var(--focus); outline-offset: 2px;
}
@media (max-width: 640px) {
  .hero { min-height: 70vh; }
  .vitrine, .why { grid-template-columns: 1fr; }
  .top__nav a:not(.tel):not(.btn) { display: none; }
}
```

```js path=/src/frontend/app.js
const form = document.getElementById("booking-form");
const msg = document.getElementById("form-msg");
form?.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.hidden = false;
  msg.textContent = "Отправляем…";
  const data = Object.fromEntries(new FormData(form).entries());
  try {
    const res = await fetch("/api/booking", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("fail");
    msg.textContent = "Заявка принята. Мастер перезвонит.";
    form.reset();
  } catch {
    msg.textContent = "Не удалось отправить. Позвоните +7 (495) 120-45-67";
  }
});
```
