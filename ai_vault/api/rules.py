"""CRUD endpoints for access rules."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_vault.api.schemas import RuleCreate, RuleResponse, RuleUpdate
from ai_vault.db import get_session
from ai_vault.models import AccessRule

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_model=list[RuleResponse])
async def list_rules(
    resource_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(AccessRule)
    if resource_id:
        stmt = stmt.where(AccessRule.resource_id == resource_id)
    stmt = stmt.order_by(AccessRule.created_at)

    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=RuleResponse, status_code=201)
async def create_rule(
    data: RuleCreate,
    session: AsyncSession = Depends(get_session),
):
    rule = AccessRule(
        resource_id=data.resource_id,
        rule_type=data.rule_type,
        enabled=data.enabled,
        max_uses=data.max_uses,
        allowed_start_hour=data.allowed_start_hour,
        allowed_end_hour=data.allowed_end_hour,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: str,
    data: RuleUpdate,
    session: AsyncSession = Depends(get_session),
):
    rule = await session.get(AccessRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)

    await session.commit()
    await session.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    session: AsyncSession = Depends(get_session),
):
    rule = await session.get(AccessRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    await session.delete(rule)
    await session.commit()
