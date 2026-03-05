"""MCP client manager for forwarding tool calls to downstream MCP servers."""

from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client


@dataclass
class ToolCallResult:
    """Result of calling a downstream MCP tool."""

    success: bool
    content: list[dict[str, Any]] = field(default_factory=list)
    is_error: bool = False
    execution_time_ms: int = 0
    error_message: Optional[str] = None


def parse_server_params(mcp_server_url: str) -> StdioServerParameters:
    """Parse stored JSON config into StdioServerParameters.

    The mcp_server_url field stores a JSON object like:
        {"command": "npx", "args": ["@modelcontextprotocol/server-slack"], "env": {"TOKEN": "x"}}

    Args:
        mcp_server_url: JSON string with command, args, and optional env/cwd.

    Returns:
        StdioServerParameters ready for stdio_client.

    Raises:
        ValueError: If JSON is invalid or missing required fields.
    """
    try:
        config = json.loads(mcp_server_url)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid server config JSON: {e}") from e

    if not isinstance(config, dict) or "command" not in config:
        raise ValueError("Server config must be a JSON object with at least a 'command' field")

    return StdioServerParameters(
        command=config["command"],
        args=config.get("args", []),
        env=config.get("env"),
        cwd=config.get("cwd"),
    )


async def call_downstream_tool(
    server_params: StdioServerParameters,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> ToolCallResult:
    """Spawn a downstream MCP server, call a tool, and return the result.

    Uses stdio_client to spawn the server process, initialize it,
    call the specified tool, then tear down cleanly.

    Args:
        server_params: Connection parameters for the downstream server.
        tool_name: Name of the tool to call on the downstream server.
        arguments: Arguments to pass to the tool.

    Returns:
        ToolCallResult with the downstream response.
    """
    start = time.monotonic()
    errlog = io.StringIO()

    try:
        async with stdio_client(server_params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)

                elapsed_ms = int((time.monotonic() - start) * 1000)

                content = []
                for item in result.content:
                    if hasattr(item, "text"):
                        content.append({"type": "text", "text": item.text})
                    elif hasattr(item, "data"):
                        content.append({"type": item.type, "data": item.data})
                    else:
                        content.append({"type": str(item.type)})

                return ToolCallResult(
                    success=not result.isError,
                    content=content,
                    is_error=result.isError or False,
                    execution_time_ms=elapsed_ms,
                )

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        stderr_output = errlog.getvalue().strip()
        error_msg = str(e)
        if stderr_output:
            error_msg += f"\nServer stderr: {stderr_output}"

        return ToolCallResult(
            success=False,
            is_error=True,
            execution_time_ms=elapsed_ms,
            error_message=error_msg,
        )
