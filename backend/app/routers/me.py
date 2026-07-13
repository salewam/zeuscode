from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import UsageLog, User

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/usage")
async def usage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    result = await db.execute(
        select(UsageLog)
        .where(UsageLog.user_id == user.id)
        .order_by(UsageLog.id.desc())
        .limit(min(limit, 200))
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "model": r.model,
            "mode": r.mode,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "cost_user_rub": round(r.cost_user_usd, 4),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
