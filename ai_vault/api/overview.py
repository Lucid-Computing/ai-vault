"""Dashboard overview endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_vault.api.schemas import OverviewResponse
from ai_vault.db import get_session
from ai_vault.models import ActivityLog, ApprovalRequest, VaultResource

router = APIRouter(tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(session: AsyncSession = Depends(get_session)):
    # Total resources
    total = (await session.execute(select(func.count()).select_from(VaultResource))).scalar() or 0

    # By level
    level_stmt = (
        select(VaultResource.access_level, func.count())
        .group_by(VaultResource.access_level)
    )
    level_result = await session.execute(level_stmt)
    by_level = dict(level_result.all())

    # By type
    type_stmt = (
        select(VaultResource.resource_type, func.count())
        .group_by(VaultResource.resource_type)
    )
    type_result = await session.execute(type_stmt)
    by_type = dict(type_result.all())

    # Pending approvals count
    pending = (
        await session.execute(
            select(func.count())
            .select_from(ApprovalRequest)
            .where(ApprovalRequest.status == "pending")
        )
    ).scalar() or 0

    # Total accesses (all time)
    total_accesses = (
        await session.execute(
            select(func.coalesce(func.sum(VaultResource.access_count), 0))
        )
    ).scalar() or 0

    # Recent activity count (last 24h)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = (
        await session.execute(
            select(func.count())
            .select_from(ActivityLog)
            .where(ActivityLog.timestamp >= cutoff)
        )
    ).scalar() or 0

    # Top 5 most accessed resources
    top_stmt = (
        select(VaultResource)
        .where(VaultResource.access_count > 0)
        .order_by(VaultResource.access_count.desc())
        .limit(5)
    )
    top_result = await session.execute(top_stmt)
    top_resources = top_result.scalars().all()

    # Pending approval list (up to 5)
    pending_stmt = (
        select(ApprovalRequest)
        .where(ApprovalRequest.status == "pending")
        .order_by(ApprovalRequest.requested_at.desc())
        .limit(5)
    )
    pending_result = await session.execute(pending_stmt)
    pending_list = pending_result.scalars().all()

    # Recent activity entries (last 10)
    activity_stmt = (
        select(ActivityLog)
        .order_by(ActivityLog.timestamp.desc())
        .limit(10)
    )
    activity_result = await session.execute(activity_stmt)
    recent_activities = activity_result.scalars().all()

    return OverviewResponse(
        total_resources=total,
        resources_by_level=by_level,
        resources_by_type=by_type,
        pending_approvals=pending,
        total_accesses=total_accesses,
        recent_activity_count=recent,
        top_resources=top_resources,
        pending_approval_list=pending_list,
        recent_activities=recent_activities,
    )
