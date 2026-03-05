"""Activity log endpoints (read-only)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_vault.api.schemas import ActivityResponse
from ai_vault.db import get_session
from ai_vault.models import ActivityLog

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("", response_model=list[ActivityResponse])
async def list_activity(
    resource_name: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(limit)
    if resource_name:
        stmt = stmt.where(ActivityLog.resource_name == resource_name)
    if action:
        stmt = stmt.where(ActivityLog.action == action)

    result = await session.execute(stmt)
    return result.scalars().all()
