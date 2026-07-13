"""Template: service layer for business rules / transactions."""

from sqlalchemy.ext.asyncio import AsyncSession

# from app.models import Resource, User


async def create_resource(
    db: AsyncSession,
    *,
    user_id: int,
    title: str,
):
    """Create resource owned by user. Raises domain errors for the router to map."""
    # item = Resource(title=title.strip(), user_id=user_id)
    # db.add(item)
    # await db.commit()
    # await db.refresh(item)
    # return item
    raise NotImplementedError("Wire model + commit")


async def get_owned_resource(
    db: AsyncSession,
    *,
    user_id: int,
    resource_id: int,
):
    """Return resource or None if missing / not owned."""
    # item = await db.get(Resource, resource_id)
    # if not item or item.user_id != user_id:
    #     return None
    # return item
    raise NotImplementedError("Wire ownership lookup")
