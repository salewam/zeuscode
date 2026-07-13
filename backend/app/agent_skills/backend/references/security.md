# Backend — Security (минимум в каждом ответе)

Аналог frontend `a11y.md`: без этого среза API **не** premium/ultra-ready.

Self-report «безопасно» ≠ доказательство. Ниже — проверяемые правила.

---

## 1. Secrets

- [ ] Нет `sk-`, `api_key = "..."`, паролей, private key в коде артефакта
- [ ] Секреты только `os.environ` / settings; в примере — плейсхолдер `settings.SECRET`
- [ ] `.env` не коммить; в артефакте Studio — не клади реальные значения

## 2. AuthN / AuthZ

- [ ] Мутации и чтение чужих данных требуют идентификации
- [ ] Проверка ownership на каждый id из path/query
- [ ] Предпочтительно **404** на чужой ресурс (не палить id), если бриф не требует 403
- [ ] Роли/scopes — только если задача про admin; не выдумывай RBAC «на вырост»

## 3. Credentials

- [ ] Пароль: hash (bcrypt/argon2/passlib), никогда в ответе API
- [ ] Login: единое сообщение при неверном email/пароле
- [ ] Токены: expiry; не логировать raw Bearer
- [ ] Reset/change password — отдельные потоки, не «пришлите пароль в чат»

## 4. Injection & input

- [ ] ORM / bound params; запрет f-string SQL
- [ ] Path/query/body валидируются типами и границами
- [ ] File upload (если есть): размер, content-type, не exec
- [ ] SSRF: не fetch URL из пользователя без allowlist (если задача про webhook/proxy)

## 5. Transport & browser

- [ ] HTTPS предполагается на проде; не требуй `verify=False` в клиентах
- [ ] CORS: явные origin; `*` + credentials = FAIL или `PASS_WITH_RISKS` с пометкой
- [ ] Cookies session: `HttpOnly` + `Secure` + `SameSite` если cookie-auth

## 6. Abuse basics

- [ ] List endpoints: лимит размера ответа
- [ ] Дорогие операции: не открывай без auth
- [ ] Rate limit — упомяни в Мышлении как follow-up, если режим light; в ultra+ заложи заглушку/зависимость только если бриф просит

## 7. Error & log hygiene

- [ ] Клиенту — короткий `detail`, не traceback
- [ ] В логах — request id / user id, не password/token
- [ ] Не возвращай сырые DB constraint strings как UX

---

## Quick threat questions (Мышление, 1 строка)

1. Кто может вызвать этот метод без auth?
2. Можно ли подставить чужой `{id}`?
3. Что утечёт при копипасте ответа в чат/лог?

Если на 1–2 ответ «да, дыра» — не сдавай.
