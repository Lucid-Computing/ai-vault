"""Tests for vault_call_tool MCP tool."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_vault.mcp_client.manager import ToolCallResult
from ai_vault.models import AccessRule, ActivityLog, VaultResource


def _tool_config(command: str = "echo", args: list | None = None) -> str:
    config = {"command": command}
    if args:
        config["args"] = args
    return json.dumps(config)


async def _seed_mcp_tools(session: AsyncSession):
    """Create test MCP tool resources."""
    green_tool = VaultResource(
        name="echo_tool",
        resource_type="mcp_tool",
        access_level="green",
        mcp_server_url=_tool_config("echo", ["hello"]),
        mcp_tool_name="echo",
        description="Simple echo tool",
    )
    red_tool = VaultResource(
        name="dangerous_tool",
        resource_type="mcp_tool",
        access_level="red",
        mcp_server_url=_tool_config("rm", ["-rf"]),
        mcp_tool_name="delete_all",
    )
    yellow_tool = VaultResource(
        name="slack_post",
        resource_type="mcp_tool",
        access_level="yellow",
        mcp_server_url=_tool_config("npx", ["@mcp/server-slack"]),
        mcp_tool_name="slack_post_message",
        description="Post to Slack",
    )
    session.add_all([green_tool, red_tool, yellow_tool])

    # Add approve_each_use rule to yellow tool
    await session.flush()
    rule = AccessRule(
        resource_id=yellow_tool.id,
        rule_type="approve_each_use",
        enabled=True,
    )
    session.add(rule)
    await session.flush()

    return green_tool, red_tool, yellow_tool


@pytest.fixture
def mock_session_factory(db_engine, monkeypatch):
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr("ai_vault.mcp_server.tools.get_session_factory", lambda: factory)
    return factory


def _mock_call_result(success=True, text="OK"):
    return ToolCallResult(
        success=success,
        content=[{"type": "text", "text": text}],
        is_error=not success,
        execution_time_ms=50,
        error_message=None if success else text,
    )


class TestVaultCallTool:
    async def test_green_tool_calls_downstream(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_call_tool

        await _seed_mcp_tools(db_session)
        await db_session.commit()

        mock_result = _mock_call_result(success=True, text="hello world")

        with patch("ai_vault.mcp_server.tools.call_downstream_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_result
            result = await vault_call_tool("echo_tool", arguments={"msg": "hi"})

        assert result["status"] == "success"
        assert result["content"][0]["text"] == "hello world"
        assert result["execution_time_ms"] == 50

        # Verify call_downstream_tool was called with correct params
        mock_call.assert_called_once()
        call_args = mock_call.call_args
        assert call_args[0][1] == "echo"  # downstream tool name
        assert call_args[0][2] == {"msg": "hi"}  # arguments

    async def test_red_tool_denied(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_call_tool

        await _seed_mcp_tools(db_session)
        await db_session.commit()

        with patch("ai_vault.mcp_server.tools.call_downstream_tool", new_callable=AsyncMock) as mock_call:
            result = await vault_call_tool("dangerous_tool")

        assert result["status"] == "denied"
        mock_call.assert_not_called()

    async def test_yellow_tool_pending_approval(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_call_tool

        await _seed_mcp_tools(db_session)
        await db_session.commit()

        with patch("ai_vault.mcp_server.tools.call_downstream_tool", new_callable=AsyncMock) as mock_call:
            result = await vault_call_tool("slack_post", purpose="Need to notify team")

        assert result["status"] == "pending_approval"
        assert "approval_id" in result
        mock_call.assert_not_called()

    async def test_nonexistent_tool_denied(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_call_tool

        result = await vault_call_tool("no_such_tool")
        assert result["status"] == "denied"

    async def test_downstream_error_logged(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_call_tool

        await _seed_mcp_tools(db_session)
        await db_session.commit()

        mock_result = _mock_call_result(success=False, text="Connection refused")

        with patch("ai_vault.mcp_server.tools.call_downstream_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_result
            result = await vault_call_tool("echo_tool")

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]

    async def test_activity_log_created(self, db_session, mock_session_factory):
        from ai_vault.mcp_server.tools import vault_call_tool

        await _seed_mcp_tools(db_session)
        await db_session.commit()

        mock_result = _mock_call_result(success=True, text="done")

        with patch("ai_vault.mcp_server.tools.call_downstream_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_result
            await vault_call_tool("echo_tool", arguments={"x": 1, "y": 2})

        # Check activity log was created
        stmt = select(ActivityLog).where(ActivityLog.action == "tool_invoked")
        result = await db_session.execute(stmt)
        log = result.scalar_one_or_none()

        assert log is not None
        assert log.resource_name == "echo_tool"
        assert log.success is True
        assert log.details["downstream_tool"] == "echo"
        assert set(log.details["argument_keys"]) == {"x", "y"}
        assert log.details["execution_time_ms"] == 50

    async def test_argument_values_not_in_log(self, db_session, mock_session_factory):
        """Ensure actual argument values are never logged — only keys."""
        from ai_vault.mcp_server.tools import vault_call_tool

        await _seed_mcp_tools(db_session)
        await db_session.commit()

        secret_arg = "super-secret-value-123"
        mock_result = _mock_call_result(success=True, text="ok")

        with patch("ai_vault.mcp_server.tools.call_downstream_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_result
            await vault_call_tool("echo_tool", arguments={"password": secret_arg})

        stmt = select(ActivityLog).where(ActivityLog.action == "tool_invoked")
        result = await db_session.execute(stmt)
        log = result.scalar_one()

        # Only keys, not values
        assert "password" in log.details["argument_keys"]
        log_str = json.dumps(log.details)
        assert secret_arg not in log_str

    async def test_missing_server_config(self, db_session, mock_session_factory):
        """Tool resource exists but has no mcp_server_url."""
        from ai_vault.mcp_server.tools import vault_call_tool

        tool = VaultResource(
            name="broken_tool",
            resource_type="mcp_tool",
            access_level="green",
            mcp_server_url=None,  # Missing!
            mcp_tool_name="something",
        )
        db_session.add(tool)
        await db_session.commit()

        result = await vault_call_tool("broken_tool")
        assert result["status"] == "error"
        assert "missing server configuration" in result["message"].lower()

    async def test_uses_mcp_tool_name_for_downstream(self, db_session, mock_session_factory):
        """The downstream call uses mcp_tool_name, not the vault resource name."""
        from ai_vault.mcp_server.tools import vault_call_tool

        await _seed_mcp_tools(db_session)
        await db_session.commit()

        mock_result = _mock_call_result(success=True, text="posted")

        # slack_post resource has mcp_tool_name="slack_post_message"
        # but we need to make it green for this test
        stmt = select(VaultResource).where(VaultResource.name == "slack_post")
        res = await db_session.execute(stmt)
        tool = res.scalar_one()
        tool.access_level = "green"
        # Remove the rule
        stmt2 = select(AccessRule).where(AccessRule.resource_id == tool.id)
        res2 = await db_session.execute(stmt2)
        for rule in res2.scalars().all():
            await db_session.delete(rule)
        await db_session.commit()

        with patch("ai_vault.mcp_server.tools.call_downstream_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_result
            await vault_call_tool("slack_post")

        # Should call downstream with "slack_post_message" not "slack_post"
        call_args = mock_call.call_args
        assert call_args[0][1] == "slack_post_message"
