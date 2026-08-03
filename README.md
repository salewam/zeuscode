# ZeusCode

Агрегатор нейросетей для кодинга. Ultra Mode = 4 дешёвых агента параллельно + синтез.

## Что внутри

- Кабинет: студия, модели, ключи, биллинг
- API OpenAI-compatible `/v1`
- API-ключи `zeus_...` (старые `osk_...` тоже принимаются)
- Модели: `gemini-2.5-flash`, `gemini-3-flash`, **`ultra-mode`**, Claude и др.
- Студия с workspace, GitHub, preview, fork

## Запуск

```bash
cd ultra-mode-mvp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# заполни .env (A6_API_KEY, A6_BASE_URL)
chmod +x scripts/run_api.sh
./scripts/run_api.sh
```

Открой http://127.0.0.1:8080 и http://127.0.0.1:8080/app

```bash
# 1. Health
curl http://127.0.0.1:8080/health

# 2. Регистрация → получи токен кабинета
# 3. Ultra Mode (Bearer = zeus_...)
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer zeus_..." \
  -H "Content-Type: application/json" \
  -d '{"model":"ultra-mode","messages":[{"role":"user","content":"Сделай todo api"}]}'
```

В Cursor / VS Code: base URL `http://127.0.0.1:8080/v1`, API key = `zeus_...`, model = `ultra-mode`.
