"""Approval request endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_vault.api.schemas import ApprovalDecision, ApprovalResponse
from ai_vault.db import get_session
from ai_vault.models import ActivityLog, ApprovalRequest

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(ApprovalRequest).order_by(ApprovalRequest.requested_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)

    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
async def approve_request(
    approval_id: str,
    decision: ApprovalDecision = ApprovalDecision(),
    session: AsyncSession = Depends(get_session),
):
    approval = await session.get(ApprovalRequest, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail=f"Request already {approval.status}")

    approval.status = "approved"
    approval.resolved_at = datetime.now(timezone.utc)
    approval.decision_reason = decision.reason

    # Log the approval
    log = ActivityLog(
        action="approval_granted",
        resource_name=approval.resource_name,
        resource_id=approval.resource_id,
        caller="web-ui",
        success=True,
        details={"approval_id": approval.id, "reason": decision.reason},
    )
    session.add(log)
    await session.commit()
    await session.refresh(approval)
    return approval


@router.post("/{approval_id}/deny", response_model=ApprovalResponse)
async def deny_request(
    approval_id: str,
    decision: ApprovalDecision = ApprovalDecision(),
    session: AsyncSession = Depends(get_session),
):
    approval = await session.get(ApprovalRequest, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail=f"Request already {approval.status}")

    approval.status = "denied"
    approval.resolved_at = datetime.now(timezone.utc)
    approval.decision_reason = decision.reason

    # Log the denial
    log = ActivityLog(
        action="approval_denied",
        resource_name=approval.resource_name,
        resource_id=approval.resource_id,
        caller="web-ui",
        success=True,
        details={"approval_id": approval.id, "reason": decision.reason},
    )
    session.add(log)
    await session.commit()
    await session.refresh(approval)
    return approval
