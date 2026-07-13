# Tests — Definition of Done

Задача не сдана, пока пункты не закрыты или `N/A` + причина в Мышлении.

## A. Scope

- [ ] Тесты покрывают формулировку задачи (не «весь CRUD»)
- [ ] Не добавлены endpoints/поля вне контракта команды
- [ ] Один ход = один набор тестов на срез

## B. Contract alignment

- [ ] path/method совпадают с backend или явным допущением
- [ ] Ожидаемые status codes совпадают (404 vs 403 — как у backend)
- [ ] JSON keys совпадают с схемами backend/UI

## C. Coverage minimum

- [ ] Happy path с assert на status + ключевое поле
- [ ] ≥1 негатив (401/404/422 — что есть в контракте)
- [ ] Нет `@pytest.mark.skip`

## D. Safety

- [ ] Нет SQL f-string / `.format` SQL в тестах
- [ ] Нет секретов
- [ ] Нет production-роутера «вместо тестов»

## E. Artifact

- [ ] `path=/src/tests/...`
- [ ] ## Мышление + ## Результат

## H. Режим

| Режим | Минимум |
|--------|---------|
| light | A + C (happy+1) + E |
| standard | A–E |
| ultra+ | + anti-patterns жёстко |
