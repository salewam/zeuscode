# Backend — эталон (good_output)

Копируй **структуру и планку**, не контент один-в-один.
Импорты ниже — **greenfield Studio** (`/src/backend/...`). Для кабинета ZeusCode бери `app.*`.

---

## Задача

«API проектов: создать и получить свой проект. Auth Bearer. Стек по умолчанию.»

---

## Мышление

Срез `/api/projects`: `POST` create (201) и `GET /{id}` (200). Auth: Bearer + `get_current_user`. Body: `{title: 1..200}`. Out: `{id, title, created_at}`. Чужой/отсутствующий id → 404 «Project not found» (не 403). Риск: без ownership утечёт чужой проект — закрываю `user_id`. Frontend/tests: те же поля и статусы.

## Результат

```python path=/src/backend/schemas/projects.py
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ProjectOut(BaseModel):
    id: int
    title: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

```python path=/src/backend/routers/projects.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from deps import get_current_user
from models import Project, User
from schemas.projects import ProjectCreate, ProjectOut

router = APIRouter(prefix="/api/projects", tags=["projects"])


async def _owned_project(
    db: AsyncSession, user: User, project_id: int
) -> Project:
    project = await db.get(Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = Project(title=body.title.strip(), user_id=user.id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _owned_project(db, user, project_id)
```

- [x] path=/src/backend/...
- [x] Pydantic In/Out
- [x] 201 + 404 ownership
- [x] нет секретов
- [x] контракт в Мышлении
