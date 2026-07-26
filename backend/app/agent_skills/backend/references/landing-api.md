# Backend — Landing / lead API stub

Когда brief / Locked contract содержит `POST /api/booking` или `POST /api/lead` — **ты обязан** сдать рабочий route. Иначе FE получит `api_orphan` и gate ≠ PASS.

## Мини-контракт (booking)

```text
POST /api/booking
auth: none (MVP лендинг) или по брифу
In:  { name:str, phone:str, car?:str, service?:str, slot?:str }
Out: 200 { "ok": true }
4xx: 422 если name/phone пустые
```

## Минимальный артефакт

```python path=/src/backend/routers/booking.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["booking"])

class BookingIn(BaseModel):
    name: str = Field(min_length=1)
    phone: str = Field(min_length=5)
    car: str | None = None
    service: str | None = None
    slot: str | None = None

class BookingOut(BaseModel):
    ok: bool = True

@router.post("/booking", response_model=BookingOut)
def create_booking(body: BookingIn) -> BookingOut:
    if not body.name.strip() or not body.phone.strip():
        raise HTTPException(status_code=422, detail="name and phone required")
    return BookingOut(ok=True)
```

Подключи router в `main`/`app` артефакте, если он есть в срезе.

## Правила

- Path/поля = Locked API contract (не переименовывай молча)
- Pydantic In/Out, не `dict`
- In-memory list ок для MVP; скажи в Мышлении
- Не оставляй FE с `fetch('/api/…')` без своего route
