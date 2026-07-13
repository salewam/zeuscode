# Reviewer — DoD evidence

## Общее

- [ ] Вердикт из `## Вердикт` (одно из трёх)
- [ ] Findings с severity + path
- [ ] Scope = задача (нет FAIL за непрошенное)
- [ ] Есть «не проверил»
- [ ] Next конкретен

## Frontend `/src/frontend`

- [ ] AI-look / a11y / div onclick проверены по тексту

## Backend `/src/backend`

- [ ] SQL f-string / secrets / ownership / dict Out

## Tests `/src/tests`

- [ ] Нет SQL f-string / skip
- [ ] Path/поля согласованы с backend если оба есть
