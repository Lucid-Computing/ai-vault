"""Tests for MCP tools."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_vault.encryption import encrypt
from ai_vault.models import AccessRule, VaultResource
from ai_vault.policy.types import DecisionType

# We test the tool functions directly (they're just async functions)
# by setting up the DB and calling them with a patched session factory.

TEST_KEY = "test-key-do-not-use-in-production-1234567890"


async def _seed_resources(session: AsyncSession):
    """Create test resources: one green, one red, one yellow."""
    green = VaultResource(
        name="GREEN_KEY",
        resource_type="secret",
        access_level="green",
        encrypted_value=encrypt("sk-green-1234", key=TEST_KEY),
        description="A green API key",
    )
    red = VaultResource(
        name="RED_SECRET",
        resource_type="secret",
        access_level="red",
        encrypted_value=encrypt("super-secret", key=TEST_KEY),
    )
    yellow = VaultResource(
        name="YELLOW_TOKEN",
        resource_type="secret",
        access_level="yellow",
        encrypted_value=encrypt("tok-yellow-5678", key=TEST_KEY),
        description="Needs approval",
    )
    session.add_all([green, red, yellow])

    # Add approve_each_use rule to yellow
    await session.flush()
    rule = AccessRule(
        resource_id=yellow.id,
        rule_type="approve_each_use",
        enabled=True,
    )
    session.add(rule)
    await session.flush()

    return green, red, yellow


@pytest.fixture
def mock_session_factory(db_engine, monkeypatch):
    """Patch get_session_factory to return sessions backed by test engine."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        bind=db_engine,
        expire_on_commit=False,
    )
    monkeypatch.setattr("ai_vault.mcp_server.tools.get_session_factory", lambda: factory)
    return factory


class TestVaultGetResource:
    async def test_green_returns_value(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_get_resource

        await _seed_resources(db_session)
        await db_session.commit()

        result = await vault_get_resource("GREEN_KEY")
        assert result["status"] == "granted"
        assert result["value"] == "sk-green-1234"

    async def test_red_returns_denied(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_get_resource

        await _seed_resources(db_session)
        await db_session.commit()

        result = await vault_get_resource("RED_SECRET")
        assert result["status"] == "denied"
        assert "value" not in result

    async def test_yellow_creates_approval(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_get_resource

        await _seed_resources(db_session)
        await db_session.commit()

        result = await vault_get_resource("YELLOW_TOKEN", purpose="Need for staging")
        assert result["status"] == "pending_approval"
        assert "approval_id" in result

    async def test_nonexistent_returns_denied(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_get_resource

        result = await vault_get_resource("DOES_NOT_EXIST")
        assert result["status"] == "denied"
        assert "value" not in result


class TestVaultListAvailable:
    async def test_excludes_red(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_list_available

        await _seed_resources(db_session)
        await db_session.commit()

        result = await vault_list_available()
        names = [r["name"] for r in result["resources"]]
        assert "GREEN_KEY" in names
        assert "YELLOW_TOKEN" in names
        assert "RED_SECRET" not in names

    async def test_no_values_in_list(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_list_available

        await _seed_resources(db_session)
        await db_session.commit()

        result = await vault_list_available()
        for r in result["resources"]:
            assert "value" not in r
            assert "encrypted_value" not in r

    async def test_filter_by_type(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_list_available

        await _seed_resources(db_session)
        # Add a file resource
        f = VaultResource(
            name="config_file",
            resource_type="file",
            access_level="green",
            file_path="/tmp/config.json",
        )
        db_session.add(f)
        await db_session.commit()

        result = await vault_list_available(resource_type="file")
        assert result["count"] == 1
        assert result["resources"][0]["name"] == "config_file"


class TestVaultCheckStatus:
    async def test_check_pending_approval(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_check_status, vault_get_resource

        await _seed_resources(db_session)
        await db_session.commit()

        # Create a pending approval
        get_result = await vault_get_resource("YELLOW_TOKEN", purpose="test")
        approval_id = get_result["approval_id"]

        result = await vault_check_status(approval_id=approval_id)
        assert result["status"] == "pending"
        assert result["resource_name"] == "YELLOW_TOKEN"

    async def test_check_resource_by_name(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_check_status

        await _seed_resources(db_session)
        await db_session.commit()

        result = await vault_check_status(resource_name="GREEN_KEY")
        assert result["access_level"] == "green"

    async def test_check_red_resource_not_found(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_check_status

        await _seed_resources(db_session)
        await db_session.commit()

        result = await vault_check_status(resource_name="RED_SECRET")
        assert result["status"] == "not_found"


class TestVaultDeclareAccess:
    async def test_dry_run(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_declare_access

        await _seed_resources(db_session)
        await db_session.commit()

        result = await vault_declare_access(
            resources=["GREEN_KEY", "RED_SECRET", "YELLOW_TOKEN"],
            purpose="testing",
        )
        resources = {r["name"]: r for r in result["resources"]}

        assert resources["GREEN_KEY"]["would_grant"] is True
        assert resources["RED_SECRET"]["would_grant"] is False
        assert resources["YELLOW_TOKEN"]["would_grant"] == "conditional"
