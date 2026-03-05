"""Aggregate API router."""

from __future__ import annotations

from fastapi import APIRouter

from ai_vault.api.activity import router as activity_router
from ai_vault.api.approvals import router as approvals_router
from ai_vault.api.overview import router as overview_router
from ai_vault.api.resources import router as resources_router
from ai_vault.api.rules import router as rules_router

api_router = APIRouter()

api_router.include_router(resources_router)
api_router.include_router(rules_router)
api_router.include_router(activity_router)
api_router.include_router(approvals_router)
api_router.include_router(overview_router)
