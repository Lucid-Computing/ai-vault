"""Tests for database models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_vault.models import AccessRule, ActivityLog, ApprovalRequest, VaultResource


class TestVaultResource:
    async def test_create_secret(self, db_session: AsyncSession):
        r = VaultResource(
            name="MY_API_KEY",
            resource_type="secret",
            access_level="green",
            encrypted_value="encrypted-data-here",
            description="Test API key",
        )
        db_session.add(r)
        await db_session.commit()

        result = await db_session.get(VaultResource, r.id)
        assert result is not None
        assert result.name == "MY_API_KEY"
        assert result.resource_type == "secret"
        assert result.access_level == "green"
        assert result.encrypted_value == "encrypted-data-here"
        assert result.access_count == 0

    async def test_create_file(self, db_session: AsyncSession):
        r = VaultResource(
            name="config_file",
            resource_type="file",
            access_level="yellow",
            file_path="/home/user/.config/app.json",
        )
        db_session.add(r)
        await db_session.commit()

        result = await db_session.get(VaultResource, r.id)
        assert result.resource_type == "file"
        assert result.file_path == "/home/user/.config/app.json"

    async def test_create_mcp_tool(self, db_session: AsyncSession):
        r = VaultResource(
            name="github_search",
            resource_type="mcp_tool",
            access_level="green",
            mcp_server_url="http://localhost:3000",
            mcp_tool_name="search_repos",
        )
        db_session.add(r)
        await db_session.commit()

        result = await db_session.get(VaultResource, r.id)
        assert result.resource_type == "mcp_tool"
        assert result.mcp_tool_name == "search_repos"

    async def test_name_unique_constraint(self, db_session: AsyncSession):
        r1 = VaultResource(name="DUPLICATE", resource_type="secret", access_level="red")
        r2 = VaultResource(name="DUPLICATE", resource_type="secret", access_level="green")
        db_session.add(r1)
        await db_session.commit()
        db_session.add(r2)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_timestamps_auto_set(self, db_session: AsyncSession):
        r = VaultResource(name="ts_test", resource_type="secret", access_level="red")
        db_session.add(r)
        await db_session.commit()

        result = await db_session.get(VaultResource, r.id)
        assert result.created_at is not None
        assert result.updated_at is not None
        assert result.last_accessed_at is None

    async def test_tags_json(self, db_session: AsyncSession):
        r = VaultResource(
            name="tagged",
            resource_type="secret",
            access_level="green",
            tags=["production", "openai"],
        )
        db_session.add(r)
        await db_session.commit()

        result = await db_session.get(VaultResource, r.id)
        assert result.tags == ["production", "openai"]


class TestAccessRule:
    async def test_create_rule(self, db_session: AsyncSession):
        r = VaultResource(name="rule_test", resource_type="secret", access_level="yellow")
        db_session.add(r)
        await db_session.commit()

        rule = AccessRule(
            resource_id=r.id,
            rule_type="approve_each_use",
            enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()

        result = await db_session.get(AccessRule, rule.id)
        assert result.rule_type == "approve_each_use"
        assert result.enabled is True

    async def test_cascade_delete(self, db_session: AsyncSession):
        r = VaultResource(name="cascade_test", resource_type="secret", access_level="yellow")
        db_session.add(r)
        await db_session.commit()

        rule = AccessRule(resource_id=r.id, rule_type="purpose_required")
        db_session.add(rule)
        await db_session.commit()
        rule_id = rule.id

        # Delete the resource
        await db_session.delete(r)
        await db_session.commit()

        # Rule should be gone
        result = await db_session.get(AccessRule, rule_id)
        assert result is None

    async def test_rate_limit_rule(self, db_session: AsyncSession):
        r = VaultResource(name="rate_test", resource_type="secret", access_level="yellow")
        db_session.add(r)
        await db_session.commit()

        rule = AccessRule(
            resource_id=r.id,
            rule_type="max_uses_per_hour",
            max_uses=10,
        )
        db_session.add(rule)
        await db_session.commit()

        result = await db_session.get(AccessRule, rule.id)
        assert result.max_uses == 10

    async def test_time_window_rule(self, db_session: AsyncSession):
        r = VaultResource(name="time_test", resource_type="secret", access_level="yellow")
        db_session.add(r)
        await db_session.commit()

        rule = AccessRule(
            resource_id=r.id,
            rule_type="time_window",
            allowed_start_hour=9,
            allowed_end_hour=17,
        )
        db_session.add(rule)
        await db_session.commit()

        result = await db_session.get(AccessRule, rule.id)
        assert result.allowed_start_hour == 9
        assert result.allowed_end_hour == 17


class TestApprovalRequest:
    async def test_lifecycle_approve(self, db_session: AsyncSession):
        r = VaultResource(name="approval_test", resource_type="secret", access_level="yellow")
        db_session.add(r)
        await db_session.commit()

        req = ApprovalRequest(
            resource_id=r.id,
            resource_name=r.name,
            purpose="Need to call the API",
            caller="claude-desktop",
            status="pending",
        )
        db_session.add(req)
        await db_session.commit()

        assert req.status == "pending"
        assert req.resolved_at is None

        # Approve
        req.status = "approved"
        req.resolved_at = datetime.now(timezone.utc)
        req.decision_reason = "Looks good"
        await db_session.commit()

        result = await db_session.get(ApprovalRequest, req.id)
        assert result.status == "approved"
        assert result.resolved_at is not None

    async def test_lifecycle_deny(self, db_session: AsyncSession):
        r = VaultResource(name="deny_test", resource_type="secret", access_level="yellow")
        db_session.add(r)
        await db_session.commit()

        req = ApprovalRequest(
            resource_id=r.id,
            resource_name=r.name,
            status="pending",
        )
        db_session.add(req)
        await db_session.commit()

        req.status = "denied"
        req.resolved_at = datetime.now(timezone.utc)
        await db_session.commit()

        result = await db_session.get(ApprovalRequest, req.id)
        assert result.status == "denied"

    async def test_default_ttl(self, db_session: AsyncSession):
        r = VaultResource(name="ttl_test", resource_type="secret", access_level="yellow")
        db_session.add(r)
        await db_session.commit()

        req = ApprovalRequest(resource_id=r.id, resource_name=r.name)
        db_session.add(req)
        await db_session.commit()

        assert req.ttl_seconds == 300

    async def test_cascade_delete(self, db_session: AsyncSession):
        r = VaultResource(name="approval_cascade", resource_type="secret", access_level="yellow")
        db_session.add(r)
        await db_session.commit()

        req = ApprovalRequest(resource_id=r.id, resource_name=r.name)
        db_session.add(req)
        await db_session.commit()
        req_id = req.id

        await db_session.delete(r)
        await db_session.commit()

        result = await db_session.get(ApprovalRequest, req_id)
        assert result is None


class TestActivityLog:
    async def test_create_log(self, db_session: AsyncSession):
        log = ActivityLog(
            action="access_granted",
            resource_name="MY_KEY",
            resource_id="fake-uuid",
            caller="claude-desktop",
            success=True,
            details={"access_level": "green"},
        )
        db_session.add(log)
        await db_session.commit()

        result = await db_session.get(ActivityLog, log.id)
        assert result.action == "access_granted"
        assert result.success is True
        assert result.details == {"access_level": "green"}

    async def test_timestamp_auto_set(self, db_session: AsyncSession):
        log = ActivityLog(
            action="access_denied",
            resource_name="PROD_KEY",
            resource_id="fake-uuid",
            success=False,
        )
        db_session.add(log)
        await db_session.commit()

        assert log.timestamp is not None

    async def test_query_by_timestamp_range(self, db_session: AsyncSession):
        for i in range(5):
            log = ActivityLog(
                action=f"action_{i}",
                resource_name="test",
                resource_id="fake-uuid",
                success=True,
            )
            db_session.add(log)
        await db_session.commit()

        stmt = select(ActivityLog).order_by(ActivityLog.timestamp)
        result = await db_session.execute(stmt)
        logs = result.scalars().all()
        assert len(logs) == 5
