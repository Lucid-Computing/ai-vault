"""Tests for MCP client manager (parse_server_params, ToolCallResult)."""

from __future__ import annotations

import json

import pytest

from ai_vault.mcp_client.manager import ToolCallResult, parse_server_params


class TestParseServerParams:
    def test_minimal_config(self):
        config = json.dumps({"command": "echo"})
        params = parse_server_params(config)
        assert params.command == "echo"
        assert params.args == []
        assert params.env is None

    def test_full_config(self):
        config = json.dumps({
            "command": "npx",
            "args": ["@modelcontextprotocol/server-slack"],
            "env": {"SLACK_TOKEN": "xoxb-test"},
            "cwd": "/tmp",
        })
        params = parse_server_params(config)
        assert params.command == "npx"
        assert params.args == ["@modelcontextprotocol/server-slack"]
        assert params.env == {"SLACK_TOKEN": "xoxb-test"}
        assert params.cwd == "/tmp"

    def test_config_with_multiple_args(self):
        config = json.dumps({
            "command": "python",
            "args": ["-m", "my_mcp_server", "--port", "9000"],
        })
        params = parse_server_params(config)
        assert params.command == "python"
        assert params.args == ["-m", "my_mcp_server", "--port", "9000"]

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Invalid server config JSON"):
            parse_server_params("not json")

    def test_missing_command_raises(self):
        with pytest.raises(ValueError, match="'command' field"):
            parse_server_params(json.dumps({"args": ["hello"]}))

    def test_non_object_raises(self):
        with pytest.raises(ValueError, match="'command' field"):
            parse_server_params(json.dumps(["echo", "hello"]))

    def test_empty_object_raises(self):
        with pytest.raises(ValueError, match="'command' field"):
            parse_server_params(json.dumps({}))


class TestToolCallResult:
    def test_default_values(self):
        result = ToolCallResult(success=True)
        assert result.success is True
        assert result.content == []
        assert result.is_error is False
        assert result.execution_time_ms == 0
        assert result.error_message is None

    def test_error_result(self):
        result = ToolCallResult(
            success=False,
            is_error=True,
            error_message="Connection refused",
            execution_time_ms=50,
        )
        assert result.success is False
        assert result.is_error is True
        assert result.error_message == "Connection refused"

    def test_content_result(self):
        result = ToolCallResult(
            success=True,
            content=[{"type": "text", "text": "Hello, world!"}],
            execution_time_ms=120,
        )
        assert len(result.content) == 1
        assert result.content[0]["text"] == "Hello, world!"
