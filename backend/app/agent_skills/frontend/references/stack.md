# Frontend — Stack

Бриф побеждает этот файл **кроме** AI-aesthetic бана: purple/indigo/violet/Inter/#4f46e5/#6366f1
нельзя даже если бриф просит «как Linear». Замени акцент и объясни в Мышлении.

---

## Decision tree

```text
1. Бриф/задача явно: React | Vue | Next | Svelte | …
   → этот стек; не миксуй с «ванилью ради ванили»
2. Правим кабинет ZeusCode (app.html / app.css)
   → существующие CSS variables, IBM Plex, lime accent; не новая тема
3. Иначе (страница, форма, MVP UI, лендинг фичи)
   → Default stack
```

---

## Default stack

| Слой | Выбор | Запрет без запроса |
|------|--------|-------------------|
| Markup | HTML5 semantic | div-soup, clickable div |
| CSS | Custom properties + plain CSS | Bootstrap 3/4, случайный Tailwind |
| JS | ES modules, без фреймворка | jQuery, Moment.js |
| Icons | Inline SVG / текст | emoji как UI, icon-font ради 2 иконок |
| Fonts | Из брифа, или осознанный `ui-sans-serif, system-ui` | Inter/Roboto «потому что дефолт» |
| Build | Не обязателен | Webpack «для одной страницы» |
| UI kits | Нет | MUI/Chakra/Ant «ускорить» |

### Artifact layout

```text
/src/frontend/
  index.html
  tokens.css      # :root
  styles.css      # layout + components
  app.js          # optional
```

Templates: `../assets/templates/` (`page.html`, `tokens.css`, `styles.css`, `app.js`, `form.html`).

---

## React path (только если выбран)

Коллокация:

```text
/src/frontend/components/Thing/
  Thing.tsx
  Thing.module.css   # или tokens + CSS modules / существующий DS
```

Правила:
- composition > mega-props
- container (data/state) vs presentation (render)
- state: local → lift → URL → server cache → global store (в этом порядке)
- не prop-drill > 3 уровней без причины

Не тащи Redux/Zustand на один toggle.

---

## CSS architecture (default)

1. **tokens** — color, space, radius (≤2), type, focus
2. **base** — reset минимальный, body, focus-visible
3. **layout** — shell, main, stack/cluster
4. **components** — button, field, empty, dialog
5. **utilities** — редко

Spacing scale: `4 8 12 16 24 32 48 64`  
Breakpoints check: `320 / 768 / 1024` (+ 1440 если desktop-heavy)

---

## API on the client

- Относительные `/api/...` или URL из брифа
- Никогда secrets в бандле
- Fetch → всегда думай loading/error/empty
- Ошибки: текст для человека, не сырой stack

---

## ZeusCode cabinet vs user product

| Контекст | Тема |
|----------|------|
| Кабинет / Studio shell ZeusCode | Сохрани terminal look, lime, Plex |
| Продукт из задачи пользователя | Тема из брифа; **не** копируй lime ZeusCode без запроса |
