"""MCP tools for AI Vault.

Five tools:
- vault_get_resource: Retrieve a resource value (RED=denied, GREEN=value, YELLOW=rules)
- vault_list_available: List non-RED resources (names/types only, no values)
- vault_check_status: Check approval status or resource access level
- vault_declare_access: Dry-run policy check for a list of resources
- vault_call_tool: Call a downstream MCP tool through the vault's policy proxy
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_vault.db import get_session_factory
from ai_vault.encryption import decrypt, DecryptionError
from ai_vault.mcp_client.manager import call_downstream_tool, parse_server_params
from ai_vault.models import ActivityLog, ApprovalRequest, VaultResource
from ai_vault.mcp_server.server import mcp
from ai_vault.policy.engine import PolicyEngine
from ai_vault.policy.types import AccessLevel, DecisionType


async def _get_session() -> AsyncSession:
    factory = get_session_factory()
    return factory()


@mcp.tool()
async def vault_get_resource(name: str, purpose: str = "") -> dict:
    """Get a resource from the vault.

    For GREEN resources, returns the value immediately.
    For YELLOW resources, evaluates rules and may require approval.
    For RED resources (or nonexistent), returns a generic "not found".

    Args:
        name: The resource name to retrieve.
        purpose: Why you need access (required by some YELLOW rules).
    """
    session = await _get_session()
    try:
        engine = PolicyEngine(session)
        decision = await engine.evaluate(name, purpose=purpose, caller="mcp-client")
        await session.commit()

        if decision.allowed and decision.value:
            try:
                decrypted = decrypt(decision.value)
            except DecryptionError:
                decrypted = decision.value
            return {
                "status": "granted",
                "name": name,
                "value": decrypted,
            }
        elif decision.pending:
            return {
                "status": "pending_approval",
                "name": name,
                "approval_id": decision.approval_id,
                "message": "Approval required. Use vault_check_status to poll.",
            }
        else:
            return {
                "status": "denied",
                "name": name,
                "message": decision.reason,
            }
    finally:
        await session.close()


@mcp.tool()
async def vault_list_available(resource_type: Optional[str] = None) -> dict:
    """List resources available to you (GREEN and YELLOW only).

    RED resources are invisible and never shown.
    Returns names, types, and access levels — never secret values.

    Args:
        resource_type: Optional filter by type (secret, file, mcp_tool).
    """
    session = await _get_session()
    try:
        stmt = select(VaultResource).where(
            VaultResource.access_level.in_(["green", "yellow"])
        )
        if resource_type:
            stmt = stmt.where(VaultResource.resource_type == resource_type)
        stmt = stmt.order_by(VaultResource.name)

        result = await session.execute(stmt)
        resources = result.scalars().all()

        return {
            "resources": [
                {
                    "name": r.name,
                    "type": r.resource_type,
                    "access_level": r.access_level,
                    "description": r.description,
                    "service": r.service,
                }
                for r in resources
            ],
            "count": len(resources),
        }
    finally:
        await session.close()


@mcp.tool()
async def vault_check_status(
    approval_id: Optional[str] = None,
    resource_name: Optional[str] = None,
) -> dict:
    """Check the status of an approval request or resource.

    Provide either approval_id (to check a pending approval) or
    resource_name (to check current access level).

    Args:
        approval_id: ID from a pending approval request.
        resource_name: Name of a resource to check access level.
    """
    session = await _get_session()
    try:
        if approval_id:
            approval = await session.get(ApprovalRequest, approval_id)
            if not approval:
                return {"status": "not_found", "message": "Approval request not found"}

            result = {
                "approval_id": approval.id,
                "resource_name": approval.resource_name,
                "status": approval.status,
                "purpose": approval.purpose,
                "requested_at": approval.requested_at.isoformat() if approval.requested_at else None,
            }

            if approval.status == "approved":
                # Fetch the resource and return its value
                stmt = select(VaultResource).where(
                    VaultResource.id == approval.resource_id
                )
                res = await session.execute(stmt)
                resource = res.scalar_one_or_none()
                if resource and resource.encrypted_value:
                    try:
                        result["value"] = decrypt(resource.encrypted_value)
                    except DecryptionError:
                        result["value"] = resource.encrypted_value

            return result

        elif resource_name:
            stmt = select(VaultResource).where(VaultResource.name == resource_name)
            res = await session.execute(stmt)
            resource = res.scalar_one_or_none()

            if not resource or resource.access_level == "red":
                return {"status": "not_found", "message": "Resource not found"}

            return {
                "name": resource.name,
                "type": resource.resource_type,
                "access_level": resource.access_level,
                "description": resource.description,
                "access_count": resource.access_count,
            }

        return {"status": "error", "message": "Provide either approval_id or resource_name"}
    finally:
        await session.close()


@mcp.tool()
async def vault_declare_access(resources: list[str], purpose: str = "") -> dict:
    """Declare intent to access resources (dry-run policy check).

    Returns the would-be access decision for each resource without
    actually creating approvals or consuming rate limits.

    Args:
        resources: List of resource names to check.
        purpose: Why you need access to these resources.
    """
    session = await _get_session()
    try:
        results = []
        for name in resources:
            stmt = select(VaultResource).where(VaultResource.name == name)
            res = await session.execute(stmt)
            resource = res.scalar_one_or_none()

            if not resource or resource.access_level == "red":
                results.append({"name": name, "would_grant": False, "reason": "Resource not found"})
            elif resource.access_level == "green":
                results.append({"name": name, "would_grant": True, "access_level": "green"})
            else:
                # YELLOW — just report status, don't evaluate fully
                results.append({
                    "name": name,
                    "would_grant": "conditional",
                    "access_level": "yellow",
                    "message": "Rules will be evaluated on actual access",
                })

        return {"resources": results, "purpose": purpose}
    finally:
        await session.close()


async def _get_mcp_tool_resource(
    session: AsyncSession, tool_name: str
) -> VaultResource | None:
    """Look up an mcp_tool resource by name or mcp_tool_name."""
    # First try exact name match
    stmt = select(VaultResource).where(
        VaultResource.name == tool_name,
        VaultResource.resource_type == "mcp_tool",
    )
    result = await session.execute(stmt)
    resource = result.scalar_one_or_none()
    if resource:
        return resource

    # Fallback: match by mcp_tool_name field
    stmt = select(VaultResource).where(
        VaultResource.mcp_tool_name == tool_name,
        VaultResource.resource_type == "mcp_tool",
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


@mcp.tool()
async def vault_call_tool(
    tool_name: str,
    arguments: Optional[dict[str, Any]] = None,
    purpose: str = "",
) -> dict:
    """Call a downstream MCP tool through the vault's policy proxy.

    The vault checks RED/YELLOW/GREEN access before forwarding the call
    to the downstream MCP server. Activity is logged for audit.

    Args:
        tool_name: Name of the registered MCP tool to call.
        arguments: Arguments to pass to the downstream tool.
        purpose: Why you need to call this tool (required by some YELLOW rules).
    """
    session = await _get_session()
    try:
        # 1. Evaluate policy
        engine = PolicyEngine(session)
        decision = await engine.evaluate(tool_name, purpose=purpose, caller="mcp-client")
        await session.commit()

        if decision.pending:
            return {
                "status": "pending_approval",
                "tool_name": tool_name,
                "approval_id": decision.approval_id,
                "message": "Approval required before calling this tool. Use vault_check_status to poll.",
            }

        if not decision.allowed:
            return {
                "status": "denied",
                "tool_name": tool_name,
                "message": decision.reason,
            }

        # 2. Fetch the resource to get server connection info
        resource = await _get_mcp_tool_resource(session, tool_name)
        if not resource or not resource.mcp_server_url:
            return {
                "status": "error",
                "tool_name": tool_name,
                "message": "Tool resource found but missing server configuration (mcp_server_url).",
            }

        # 3. Parse server params and call downstream
        try:
            server_params = parse_server_params(resource.mcp_server_url)
        except ValueError as e:
            return {
                "status": "error",
                "tool_name": tool_name,
                "message": f"Invalid server configuration: {e}",
            }

        # The actual tool name on the downstream server may differ from the vault name
        downstream_tool_name = resource.mcp_tool_name or tool_name

        result = await call_downstream_tool(server_params, downstream_tool_name, arguments)

        # 4. Log the tool invocation
        log = ActivityLog(
            action="tool_invoked",
            resource_name=tool_name,
            resource_id=resource.id,
            caller="mcp-client",
            success=result.success,
            details={
                "downstream_tool": downstream_tool_name,
                "argument_keys": list((arguments or {}).keys()),
                "execution_time_ms": result.execution_time_ms,
                "is_error": result.is_error,
            },
        )
        session.add(log)
        await session.commit()

        # 5. Return result
        if result.success:
            return {
                "status": "success",
                "tool_name": tool_name,
                "content": result.content,
                "execution_time_ms": result.execution_time_ms,
            }
        else:
            return {
                "status": "error",
                "tool_name": tool_name,
                "error": result.error_message or "Tool call failed",
                "content": result.content,
                "execution_time_ms": result.execution_time_ms,
            }

    finally:
        await session.close()
