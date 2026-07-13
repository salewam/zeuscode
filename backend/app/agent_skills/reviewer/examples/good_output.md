# Reviewer — эталон вердикта

## Задача
POST+GET tasks with auth.

## Вердикт
PASS_WITH_RISKS

## Findings
- [major] `/src/tests/test_x.py`: ожидает 403, backend даёт 404 ownership — поправить тест
- [minor] `/src/backend/schemas/tasks.py`: `user_id` в Out не обязателен для UI

## Evidence
- проверил: path-артефакты backend+tests, статусы в коде
- не проверил: живой HTTP, pytest runtime

## Next
- Выровнять тест на 404
- Не требовать PATCH — вне задачи
