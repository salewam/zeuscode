# Bad Output

## Мышление

Сделаю современный SaaS UI в стиле AI.

## Результат

```css path=/src/design/tokens.css
:root {
  --color-primary: #7c3aed;
  --color-secondary: #4f46e5;
  --font-body: Inter, sans-serif;
}

.card {
  box-shadow: 0 30px 80px rgba(124, 58, 237, 0.35);
  backdrop-filter: blur(24px);
}
```

Проблемы:
- запрещенные AI hex
- Inter по умолчанию
- glow/glass вместо иерархии
- нет layout notes и состояний
