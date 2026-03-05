"""CRUD endpoints for vault resources."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_vault.api.schemas import ResourceCreate, ResourceResponse, ResourceUpdate
from ai_vault.db import get_session
from ai_vault.encryption import encrypt
from ai_vault.models import VaultResource

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=list[ResourceResponse])
async def list_resources(
    resource_type: Optional[str] = Query(None),
    access_level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(VaultResource).order_by(VaultResource.name)
    if resource_type:
        stmt = stmt.where(VaultResource.resource_type == resource_type)
    if access_level:
        stmt = stmt.where(VaultResource.access_level == access_level)
    if search:
        stmt = stmt.where(VaultResource.name.ilike(f"%{search}%"))

    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ResourceResponse, status_code=201)
async def create_resource(
    data: ResourceCreate,
    session: AsyncSession = Depends(get_session),
):
    encrypted_value = None
    if data.value and data.resource_type == "secret":
        encrypted_value = encrypt(data.value)

    resource = VaultResource(
        name=data.name,
        resource_type=data.resource_type,
        access_level=data.access_level,
        encrypted_value=encrypted_value,
        file_path=data.file_path,
        mcp_server_url=data.mcp_server_url,
        mcp_tool_name=data.mcp_tool_name,
        service=data.service,
        description=data.description,
        tags=data.tags,
    )
    session.add(resource)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        if "UNIQUE" in str(e).upper():
            raise HTTPException(status_code=409, detail=f"Resource '{data.name}' already exists")
        raise

    await session.refresh(resource)
    return resource


@router.get("/{resource_id}", response_model=ResourceResponse)
async def get_resource(
    resource_id: str,
    session: AsyncSession = Depends(get_session),
):
    resource = await session.get(VaultResource, resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource


@router.patch("/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    resource_id: str,
    data: ResourceUpdate,
    session: AsyncSession = Depends(get_session),
):
    resource = await session.get(VaultResource, resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(resource, key, value)

    await session.commit()
    await session.refresh(resource)
    return resource


@router.delete("/{resource_id}", status_code=204)
async def delete_resource(
    resource_id: str,
    session: AsyncSession = Depends(get_session),
):
    resource = await session.get(VaultResource, resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    await session.delete(resource)
    await session.commit()
