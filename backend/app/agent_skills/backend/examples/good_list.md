# Backend — эталон list + limit

Дополнение к `good_output.md`. Планка пагинации.

---

## Задача

«GET /api/notes — список своих заметок с limit (default 20, max 100). Auth Bearer.»

---

## Мышление

List только своих (`user_id`). Query: `limit` 1..100 default 20, `offset` ≥0. Out: `{items: NoteOut[], total: int}`. Без auth → 401. Без безлимитного dump всей таблицы.

## Результат

```python path=/src/backend/schemas/notes.py
from datetime import datetime

from pydantic import BaseModel, Field


class NoteOut(BaseModel):
    id: int
    title: str
    created_at: datetime

    model_config = {"from_attributes": True}


class NoteListOut(BaseModel):
    items: list[NoteOut]
    total: int
```

```python path=/src/backend/routers/notes.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from deps import get_current_user
from models import Note, User
from schemas.notes import NoteListOut, NoteOut

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.get("", response_model=NoteListOut)
async def list_notes(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    base = select(Note).where(Note.user_id == user.id)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (
        await db.execute(
            base.order_by(Note.id.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return NoteListOut(
        items=[NoteOut.model_validate(r) for r in rows],
        total=int(total or 0),
    )
```

- [x] cap limit
- [x] только свои записи
- [x] response_model не dict
