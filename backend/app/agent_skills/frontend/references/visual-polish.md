# Visual polish — качество CSS (не один шаблон)

Контент есть — страница всё равно «черновик», если нет ритма и иерархии.
Гейты качества: motion, mobile, readable type, не AI-purple.
**Вкус:** `taste.md` + `uniqueness.md` — палитра и каркас **из брифа**.

## Принципы (адаптируй под нишу)

### 1) Палитра отрасли — своя
Выбери 4–6 токенов под продукт (кофейня ≠ СТО ≠ клиника ≠ SaaS).  
**Бан всем:** indigo/`#4f46e5`, Inter, glass/glow.  
**Бан для авто-ниши:** чистый SaaS-slate `#f8fafc` как «бокс».  
Для СТО можно asphalt/amber — **только если бриф про авто**.

```css
:root {
  --bg: …;
  --ink: …;
  --accent: …;
  --muted: …;
  --card: …;
  --focus: …;
}
body { background: var(--bg); color: var(--ink); font-family: /* выразительный стек, не Inter */; }
```

### 2) Header читаемый
Sticky *или* другой явный chrome — ок, если бренд и навигация не теряются.  
Type для brand/H1 — намеренный (serif *или* display sans), не default-only.

### 3) Hero с атмосферой
Full-bleed / сильный якорь + veil, чтобы текст читался. Не плоский `rgba(0,0,0,.6)` на всё без фото.

### 4) Motion (минимум 2)
`transition` + `:hover` на CTA и ключевых карточках (или иной явный motion).

### 5) Mobile
`@media (max-width: 640px)` — стек, читаемые отступы, не ломается.

### 6) Ссылки не browser-blue
Явный color у nav/tel из токенов.

## Self-check
- [ ] палитра UNIQUE под бриф (не чужой СТО-штамп на кофейне)
- [ ] header/бренд читаются
- [ ] hero с media + читаемый текст
- [ ] ≥2 motion
- [ ] есть mobile breakpoint
- [ ] нет indigo/Inter
