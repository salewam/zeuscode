# Good Output

## Мышление

Экран: список проектов. Subject — B2B кабинет, job — быстро найти проект и создать новый.
Signature: левая статусная полоса у строки (не card-grid). Не cream/terracotta и не indigo:
тёплый paper + ink + lime accent под продукт. States: loading skeleton rows, empty + CTA,
error + retry. Handoff — имена CTA и токены без перекраски frontend.

## Результат

```css path=/src/design/tokens.css
:root {
  --color-bg: #f6f1e8;
  --color-surface: #fffaf1;
  --color-text: #1f241d;
  --color-muted: #68705f;
  --color-accent: #8aa624;
  --color-danger: #9f3a2f;
  --border-subtle: #ded5c2;

  --font-body: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --radius-sm: 8px;
  --radius-md: 14px;
  --focus-ring: 2px solid var(--color-accent);
}

button:focus-visible,
a:focus-visible,
input:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 2px;
}
```

Layout notes:
- Page max-width: 1120px, centered, `24px` mobile gutters.
- Hero compact: title + one primary CTA, no stat badges.
- Project rows: status rail, not card shadows.
- Empty: short reason + one CTA.

### Handoff frontend
- Экран: список проектов
- Компоненты: page header, primary CTA «Новый проект», table/list rows, empty, error alert
- Состояния: loading → skeleton; empty → текст + CTA; error → alert + retry; ready → rows
- CTA / labels: «Новый проект», «Повторить», «Нет проектов»
- Не делать: indigo/purple, Inter, card soup, outline:none

Self-check:
- [x] Нет purple/indigo/Inter
- [x] Есть tokens + layout notes + Handoff
