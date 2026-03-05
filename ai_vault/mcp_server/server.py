"""FastMCP server with 4 vault tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ai-vault")


def get_mcp_app():
    """Create the MCP ASGI sub-app for mounting in FastAPI."""
    # Import tools to register them
    import ai_vault.mcp_server.tools  # noqa: F401

    return mcp.sse_app()
