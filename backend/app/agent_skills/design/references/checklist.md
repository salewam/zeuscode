# Design — Definition of Done

Задача не сдана, пока контракт нельзя отдать frontend без расшифровки.

## Acceptance

- [ ] Есть `## Мышление` и `## Результат`
- [ ] Есть fenced block с `path=/src/design/...`
- [ ] Указан главный визуальный якорь экрана
- [ ] Иерархия заголовков, текста и CTA понятна
- [ ] Состояния UI названы: loading / empty / error / ready, если применимо
- [ ] Handoff/labels без яичного copy (факты продукта, не «три сильные вещи»)

## Tokens

- [ ] Цвета вынесены в CSS variables
- [ ] Spacing на шкале 4/8: `4 8 12 16 24 32 48 64`
- [ ] Радиусы ограничены 1–2 значениями
- [ ] Focus-ring задан через токен
- [ ] Контраст основного текста не зависит от декоративного цвета

## Layout Contract

- [ ] Mobile-first
- [ ] Есть max-width / grid / rhythm notes
- [ ] Компоненты названы так, чтобы frontend мог повторить структуру
- [ ] Нет лишней дизайн-системы поверх задачи
- [ ] Есть блок `### Handoff frontend` (states + CTA/labels)

## Process

- [ ] В Мышлении: subject + signature + почему не AI-default
- [ ] Не сдан cream/acid/broadsheet/indigo кластер без явного брифа

## Anti-AI Gate

- [ ] Нет `#7c3aed`, `#4f46e5`, `#6366f1`
- [ ] Нет Inter как дефолта
- [ ] Нет generic purple/indigo SaaS aesthetic
- [ ] Нет glass/glow/card soup без смысла
