"""Tests for the policy engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_vault.models import AccessRule, ActivityLog, ApprovalRequest, VaultResource
from ai_vault.policy.engine import PolicyEngine
from ai_vault.policy.types import DecisionType


async def _create_resource(
    session: AsyncSession,
    name: str = "test_resource",
    resource_type: str = "secret",
    access_level: str = "green",
    encrypted_value: str | None = "encrypted-secret-data",
) -> VaultResource:
    r = VaultResource(
        name=name,
        resource_type=resource_type,
        access_level=access_level,
        encrypted_value=encrypted_value,
    )
    session.add(r)
    await session.flush()
    return r


async def _add_rule(
    session: AsyncSession,
    resource_id: str,
    rule_type: str,
    enabled: bool = True,
    **kwargs,
) -> AccessRule:
    rule = AccessRule(
        resource_id=resource_id,
        rule_type=rule_type,
        enabled=enabled,
        **kwargs,
    )
    session.add(rule)
    await session.flush()
    return rule


class TestRedAccess:
    async def test_red_always_denied(self, db_session: AsyncSession):
        await _create_resource(db_session, "secret_red", access_level="red")
        engine = PolicyEngine(db_session)

        decision = await engine.evaluate("secret_red")
        assert decision.denied
        assert decision.reason == "Resource not found"  # No information leakage

    async def test_red_with_purpose_still_denied(self, db_session: AsyncSession):
        await _create_resource(db_session, "locked", access_level="red")
        engine = PolicyEngine(db_session)

        decision = await engine.evaluate("locked", purpose="I really need it", caller="claude")
        assert decision.denied


class TestGreenAccess:
    async def test_green_always_allowed(self, db_session: AsyncSession):
        await _create_resource(db_session, "open_key", access_level="green",
                               encrypted_value="enc-value-123")
        engine = PolicyEngine(db_session)

        decision = await engine.evaluate("open_key")
        assert decision.allowed
        assert decision.value == "enc-value-123"

    async def test_green_updates_access_count(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "counter_test", access_level="green")
        assert r.access_count == 0
        assert r.last_accessed_at is None

        engine = PolicyEngine(db_session)
        await engine.evaluate("counter_test")

        await db_session.refresh(r)
        assert r.access_count == 1
        assert r.last_accessed_at is not None

    async def test_green_multiple_accesses_increment(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "multi_access", access_level="green")
        engine = PolicyEngine(db_session)

        await engine.evaluate("multi_access")
        await engine.evaluate("multi_access")
        await engine.evaluate("multi_access")

        await db_session.refresh(r)
        assert r.access_count == 3


class TestYellowNoRules:
    async def test_yellow_no_rules_denied(self, db_session: AsyncSession):
        await _create_resource(db_session, "no_rules", access_level="yellow")
        engine = PolicyEngine(db_session)

        decision = await engine.evaluate("no_rules")
        assert decision.denied
        assert "no rules" in decision.reason.lower()


class TestYellowApproveEachUse:
    async def test_creates_approval(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "needs_approval", access_level="yellow")
        await _add_rule(db_session, r.id, "approve_each_use")

        engine = PolicyEngine(db_session)
        decision = await engine.evaluate("needs_approval", purpose="API call", caller="claude")

        assert decision.pending
        assert decision.approval_id is not None

        # Verify approval was created
        approval = await db_session.get(ApprovalRequest, decision.approval_id)
        assert approval is not None
        assert approval.status == "pending"
        assert approval.purpose == "API call"
        assert approval.caller == "claude"


class TestYellowPurposeRequired:
    async def test_with_purpose_allowed(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "purpose_ok", access_level="yellow")
        await _add_rule(db_session, r.id, "purpose_required")

        engine = PolicyEngine(db_session)
        decision = await engine.evaluate("purpose_ok", purpose="Need for API integration")
        assert decision.allowed

    async def test_without_purpose_denied(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "purpose_needed", access_level="yellow")
        await _add_rule(db_session, r.id, "purpose_required")

        engine = PolicyEngine(db_session)
        decision = await engine.evaluate("purpose_needed", purpose="")
        assert decision.denied
        assert "purpose" in decision.reason.lower()

    async def test_whitespace_only_purpose_denied(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "ws_purpose", access_level="yellow")
        await _add_rule(db_session, r.id, "purpose_required")

        engine = PolicyEngine(db_session)
        decision = await engine.evaluate("ws_purpose", purpose="   ")
        assert decision.denied


class TestYellowRateLimit:
    async def test_under_limit_allowed(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "rate_ok", access_level="yellow")
        await _add_rule(db_session, r.id, "max_uses_per_hour", max_uses=5)

        engine = PolicyEngine(db_session)
        decision = await engine.evaluate("rate_ok", purpose="test")
        assert decision.allowed

    async def test_at_limit_denied(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "rate_exceeded", access_level="yellow")
        await _add_rule(db_session, r.id, "max_uses_per_hour", max_uses=3)

        # Simulate 3 prior grants
        for _ in range(3):
            log = ActivityLog(
                action="access_granted",
                resource_name=r.name,
                resource_id=r.id,
                success=True,
            )
            db_session.add(log)
        await db_session.flush()

        engine = PolicyEngine(db_session)
        decision = await engine.evaluate("rate_exceeded")
        assert decision.denied
        assert "rate limit" in decision.reason.lower()


class TestYellowTimeWindow:
    async def test_inside_window_allowed(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "time_ok", access_level="yellow")
        await _add_rule(db_session, r.id, "time_window", allowed_start_hour=0, allowed_end_hour=23)

        engine = PolicyEngine(db_session)
        decision = await engine.evaluate("time_ok")
        assert decision.allowed

    async def test_outside_window_denied(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "time_bad", access_level="yellow")
        # Window is 2-3 UTC — very narrow, unlikely to be now
        await _add_rule(db_session, r.id, "time_window", allowed_start_hour=2, allowed_end_hour=3)

        # Mock the current hour to be outside the window
        mock_dt = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        with patch("ai_vault.policy.engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            engine = PolicyEngine(db_session)
            decision = await engine.evaluate("time_bad")
            assert decision.denied
            assert "10" not in decision.reason or "2:00-3:00" in decision.reason

    async def test_inside_window_with_mock(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "time_exact", access_level="yellow")
        await _add_rule(db_session, r.id, "time_window", allowed_start_hour=9, allowed_end_hour=17)

        mock_dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        with patch("ai_vault.policy.engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            engine = PolicyEngine(db_session)
            decision = await engine.evaluate("time_exact")
            assert decision.allowed


class TestYellowMultipleRules:
    async def test_all_pass(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "multi_pass", access_level="yellow")
        await _add_rule(db_session, r.id, "purpose_required")
        await _add_rule(db_session, r.id, "max_uses_per_hour", max_uses=100)

        engine = PolicyEngine(db_session)
        decision = await engine.evaluate("multi_pass", purpose="testing")
        assert decision.allowed

    async def test_one_fails(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "multi_fail", access_level="yellow")
        await _add_rule(db_session, r.id, "purpose_required")
        await _add_rule(db_session, r.id, "max_uses_per_hour", max_uses=100)

        engine = PolicyEngine(db_session)
        # No purpose → purpose_required fails
        decision = await engine.evaluate("multi_fail", purpose="")
        assert decision.denied

    async def test_disabled_rule_skipped(self, db_session: AsyncSession):
        r = await _create_resource(db_session, "disabled_rule", access_level="yellow")
        await _add_rule(db_session, r.id, "purpose_required", enabled=False)
        await _add_rule(db_session, r.id, "max_uses_per_hour", max_uses=100, enabled=True)

        engine = PolicyEngine(db_session)
        # Purpose is empty but that rule is disabled
        decision = await engine.evaluate("disabled_rule", purpose="")
        assert decision.allowed


class TestNonexistentResource:
    async def test_unknown_resource_denied(self, db_session: AsyncSession):
        engine = PolicyEngine(db_session)
        decision = await engine.evaluate("does_not_exist")
        assert decision.denied
        assert "not found" in decision.reason.lower()


class TestActivityLogging:
    async def test_green_access_logged(self, db_session: AsyncSession):
        from sqlalchemy import select

        await _create_resource(db_session, "logged_green", access_level="green")
        engine = PolicyEngine(db_session)
        await engine.evaluate("logged_green", caller="test-agent")

        stmt = select(ActivityLog).where(ActivityLog.resource_name == "logged_green")
        result = await db_session.execute(stmt)
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].action == "access_granted"
        assert logs[0].caller == "test-agent"
        assert logs[0].success is True

    async def test_red_access_logged(self, db_session: AsyncSession):
        from sqlalchemy import select

        await _create_resource(db_session, "logged_red", access_level="red")
        engine = PolicyEngine(db_session)
        await engine.evaluate("logged_red")

        stmt = select(ActivityLog).where(ActivityLog.resource_name == "logged_red")
        result = await db_session.execute(stmt)
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].action == "access_blocked"
        assert logs[0].success is False
