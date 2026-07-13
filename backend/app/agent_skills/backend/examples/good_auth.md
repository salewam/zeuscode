# Backend — эталон auth (login без enumeration)

Дополнение к `good_output.md`. Планка, не копипаста.

---

## Задача

«POST /api/auth/login {email, password} → token. Не палить, существует ли email.»

---

## Мышление

Один endpoint login. In: email+password. Out: `{access_token, token_type}`. Неверный email или пароль → **одинаковый** 401 `Invalid email or password`. Пароль только через verify(hash). Секрет JWT из env. Frontend: поле error одно на обе ошибки.

## Результат

```python path=/src/backend/schemas/auth.py
from pydantic import BaseModel, EmailStr, Field


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

```python path=/src/backend/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import User
from schemas.auth import LoginIn, TokenOut
from security import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid email or password",
        )
    return TokenOut(access_token=create_access_token(user.id))
```

- [x] единый 401 message
- [x] нет password в ответе
- [x] Pydantic + path=
