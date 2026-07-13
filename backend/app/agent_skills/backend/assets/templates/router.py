"""Template: FastAPI router for one resource.

Adapt names/paths. Keep handlers thin; put rules in service if needed.
Do NOT ship a raw dict response model — wire a real Out schema.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

# Greenfield Studio (/src/backend):
#   from schemas.resource import ResourceCreate, ResourceOut
#   from deps import get_current_user
#   from db import get_db
#   from models import User, Resource
# ZeusCode cabinet:
#   from app.schemas... / app.deps / app.db

from schemas.resource import ResourceCreate, ResourceOut

router = APIRouter(prefix="/api/resources", tags=["resources"])


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ResourceCreate,
    # db: AsyncSession = Depends(get_db),
    # user: User = Depends(get_current_user),
):
    # item = Resource(title=body.title.strip(), user_id=user.id)
    # db.add(item); await db.commit(); await db.refresh(item)
    # return item
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Template only — replace with create + commit",
    )


@router.get("/{item_id}", response_model=ResourceOut)
async def get_item(
    item_id: int,
    # db: AsyncSession = Depends(get_db),
    # user: User = Depends(get_current_user),
):
    # item = await db.get(Resource, item_id)
    # if not item or item.user_id != user.id:
    #     raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    # return item
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Template only — replace with ownership get",
    )
