"""Tests for the Management API."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_vault.models import AccessRule, ApprovalRequest, VaultResource


@pytest_asyncio.fixture
async def api_client(db_engine):
    """Create an httpx AsyncClient pointed at the test FastAPI app."""
    from ai_vault.api.router import api_router
    from ai_vault.db import get_session
    from ai_vault.models.base import Base

    from fastapi import FastAPI

    app = FastAPI()

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.include_router(api_router, prefix="/api")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


class TestResourceCRUD:
    async def test_create_resource(self, api_client):
        resp = await api_client.post("/api/resources", json={
            "name": "TEST_KEY",
            "resource_type": "secret",
            "access_level": "green",
            "value": "sk-1234",
            "description": "Test API key",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "TEST_KEY"
        assert data["access_level"] == "green"
        assert "encrypted_value" not in data  # Never leak encrypted values

    async def test_list_resources(self, api_client):
        await api_client.post("/api/resources", json={
            "name": "LIST_1", "resource_type": "secret", "access_level": "green",
        })
        await api_client.post("/api/resources", json={
            "name": "LIST_2", "resource_type": "file", "access_level": "red",
        })

        resp = await api_client.get("/api/resources")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_list_with_filter(self, api_client):
        await api_client.post("/api/resources", json={
            "name": "F1", "resource_type": "secret", "access_level": "green",
        })
        await api_client.post("/api/resources", json={
            "name": "F2", "resource_type": "file", "access_level": "red",
        })

        resp = await api_client.get("/api/resources?resource_type=secret")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "F1"

    async def test_get_resource(self, api_client):
        create_resp = await api_client.post("/api/resources", json={
            "name": "GET_TEST", "resource_type": "secret", "access_level": "green",
        })
        resource_id = create_resp.json()["id"]

        resp = await api_client.get(f"/api/resources/{resource_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GET_TEST"

    async def test_update_resource(self, api_client):
        create_resp = await api_client.post("/api/resources", json={
            "name": "UPDATE_TEST", "resource_type": "secret", "access_level": "red",
        })
        resource_id = create_resp.json()["id"]

        resp = await api_client.patch(f"/api/resources/{resource_id}", json={
            "access_level": "green",
            "description": "Updated",
        })
        assert resp.status_code == 200
        assert resp.json()["access_level"] == "green"
        assert resp.json()["description"] == "Updated"

    async def test_delete_resource(self, api_client):
        create_resp = await api_client.post("/api/resources", json={
            "name": "DELETE_TEST", "resource_type": "secret", "access_level": "red",
        })
        resource_id = create_resp.json()["id"]

        resp = await api_client.delete(f"/api/resources/{resource_id}")
        assert resp.status_code == 204

        resp = await api_client.get(f"/api/resources/{resource_id}")
        assert resp.status_code == 404

    async def test_create_duplicate_fails(self, api_client):
        await api_client.post("/api/resources", json={
            "name": "DUP", "resource_type": "secret", "access_level": "green",
        })
        resp = await api_client.post("/api/resources", json={
            "name": "DUP", "resource_type": "secret", "access_level": "red",
        })
        assert resp.status_code == 409

    async def test_create_validates_type(self, api_client):
        resp = await api_client.post("/api/resources", json={
            "name": "BAD", "resource_type": "invalid", "access_level": "green",
        })
        assert resp.status_code == 422

    async def test_create_validates_level(self, api_client):
        resp = await api_client.post("/api/resources", json={
            "name": "BAD", "resource_type": "secret", "access_level": "purple",
        })
        assert resp.status_code == 422


class TestApprovalFlow:
    async def test_approve_flow(self, api_client, db_engine):
        # Create a resource and an approval
        create_resp = await api_client.post("/api/resources", json={
            "name": "APPROVAL_TEST", "resource_type": "secret", "access_level": "yellow",
        })
        resource_id = create_resp.json()["id"]

        # Manually create an approval via the DB
        factory = async_sessionmaker(db_engine, expire_on_commit=False)
        async with factory() as session:
            approval = ApprovalRequest(
                resource_id=resource_id,
                resource_name="APPROVAL_TEST",
                purpose="test",
                status="pending",
            )
            session.add(approval)
            await session.commit()
            approval_id = approval.id

        # List pending approvals
        resp = await api_client.get("/api/approvals?status=pending")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # Approve
        resp = await api_client.post(f"/api/approvals/{approval_id}/approve", json={
            "reason": "Looks good",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    async def test_deny_flow(self, api_client, db_engine):
        create_resp = await api_client.post("/api/resources", json={
            "name": "DENY_TEST", "resource_type": "secret", "access_level": "yellow",
        })
        resource_id = create_resp.json()["id"]

        factory = async_sessionmaker(db_engine, expire_on_commit=False)
        async with factory() as session:
            approval = ApprovalRequest(
                resource_id=resource_id,
                resource_name="DENY_TEST",
                status="pending",
            )
            session.add(approval)
            await session.commit()
            approval_id = approval.id

        resp = await api_client.post(f"/api/approvals/{approval_id}/deny", json={
            "reason": "Not authorized",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "denied"


class TestOverview:
    async def test_overview_stats(self, api_client):
        await api_client.post("/api/resources", json={
            "name": "OV_1", "resource_type": "secret", "access_level": "green",
        })
        await api_client.post("/api/resources", json={
            "name": "OV_2", "resource_type": "file", "access_level": "red",
        })

        resp = await api_client.get("/api/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_resources"] == 2
        assert data["resources_by_level"]["green"] == 1
        assert data["resources_by_level"]["red"] == 1
        assert data["resources_by_type"]["secret"] == 1
        assert data["resources_by_type"]["file"] == 1

    async def test_overview_no_secrets(self, api_client):
        """Overview should never contain secret values."""
        await api_client.post("/api/resources", json={
            "name": "SECRET_OV", "resource_type": "secret", "access_level": "green",
            "value": "super-secret-value",
        })

        resp = await api_client.get("/api/overview")
        assert resp.status_code == 200
        text = resp.text
        assert "super-secret-value" not in text


class TestRuleCRUD:
    async def test_create_and_list_rules(self, api_client):
        create_resp = await api_client.post("/api/resources", json={
            "name": "RULE_RES", "resource_type": "secret", "access_level": "yellow",
        })
        resource_id = create_resp.json()["id"]

        resp = await api_client.post("/api/rules", json={
            "resource_id": resource_id,
            "rule_type": "approve_each_use",
        })
        assert resp.status_code == 201
        rule_id = resp.json()["id"]

        resp = await api_client.get(f"/api/rules?resource_id={resource_id}")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_update_rule(self, api_client):
        create_resp = await api_client.post("/api/resources", json={
            "name": "RULE_UPD", "resource_type": "secret", "access_level": "yellow",
        })
        resource_id = create_resp.json()["id"]

        rule_resp = await api_client.post("/api/rules", json={
            "resource_id": resource_id,
            "rule_type": "max_uses_per_hour",
            "max_uses": 5,
        })
        rule_id = rule_resp.json()["id"]

        resp = await api_client.patch(f"/api/rules/{rule_id}", json={
            "max_uses": 10,
            "enabled": False,
        })
        assert resp.status_code == 200
        assert resp.json()["max_uses"] == 10
        assert resp.json()["enabled"] is False

    async def test_delete_rule(self, api_client):
        create_resp = await api_client.post("/api/resources", json={
            "name": "RULE_DEL", "resource_type": "secret", "access_level": "yellow",
        })
        resource_id = create_resp.json()["id"]

        rule_resp = await api_client.post("/api/rules", json={
            "resource_id": resource_id,
            "rule_type": "purpose_required",
        })
        rule_id = rule_resp.json()["id"]

        resp = await api_client.delete(f"/api/rules/{rule_id}")
        assert resp.status_code == 204


class TestActivity:
    async def test_activity_logged(self, api_client, db_engine):
        """Approval operations should create activity log entries."""
        create_resp = await api_client.post("/api/resources", json={
            "name": "ACT_TEST", "resource_type": "secret", "access_level": "yellow",
        })
        resource_id = create_resp.json()["id"]

        factory = async_sessionmaker(db_engine, expire_on_commit=False)
        async with factory() as session:
            approval = ApprovalRequest(
                resource_id=resource_id,
                resource_name="ACT_TEST",
                status="pending",
            )
            session.add(approval)
            await session.commit()
            approval_id = approval.id

        await api_client.post(f"/api/approvals/{approval_id}/approve")

        resp = await api_client.get("/api/activity")
        assert resp.status_code == 200
        logs = resp.json()
        assert len(logs) >= 1
        assert any(l["action"] == "approval_granted" for l in logs)
