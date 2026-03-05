"""Policy engine — evaluates RED/YELLOW/GREEN access for vault resources."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_vault.models.access_rule import AccessRule
from ai_vault.models.activity_log import ActivityLog
from ai_vault.models.approval_request import ApprovalRequest
from ai_vault.models.resource import VaultResource
from ai_vault.policy.types import AccessLevel, Decision, DecisionType, RuleType


class PolicyEngine:
    """Evaluates access policies for vault resources.

    Flow:
    1. Look up resource by name.
    2. RED -> DENY (always, resource appears to not exist).
    3. GREEN -> ALLOW (always), update access metadata.
    4. YELLOW -> load enabled rules, evaluate each (AND logic):
       - approve_each_use: create ApprovalRequest, return PENDING_APPROVAL
       - max_uses_per_hour: count recent grants, deny if exceeded
       - purpose_required: check purpose is non-empty
       - time_window: check current UTC hour in range
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def evaluate(
        self,
        resource_name: str,
        purpose: str = "",
        caller: str = "",
    ) -> Decision:
        """Evaluate access to a resource.

        Args:
            resource_name: Name of the resource to access.
            purpose: Caller's stated reason for access.
            caller: Identity of the AI tool/agent requesting access.

        Returns:
            Decision with type, reason, and optional approval_id or value.
        """
        resource = await self._get_resource(resource_name)
        if resource is None:
            return Decision(DecisionType.DENY, reason="Resource not found")

        level = AccessLevel(resource.access_level)

        if level == AccessLevel.RED:
            await self._log(resource, "access_blocked", caller, success=False,
                            details={"reason": "red_resource"})
            return Decision(DecisionType.DENY, reason="Resource not found")

        if level == AccessLevel.GREEN:
            await self._update_access_metadata(resource)
            await self._log(resource, "access_granted", caller, success=True,
                            details={"access_level": "green"})
            return Decision(DecisionType.ALLOW, reason="Green resource — auto-granted",
                            value=resource.encrypted_value)

        # YELLOW — evaluate rules
        return await self._evaluate_yellow(resource, purpose, caller)

    async def _evaluate_yellow(
        self,
        resource: VaultResource,
        purpose: str,
        caller: str,
    ) -> Decision:
        """Evaluate YELLOW rules (AND logic, short-circuit on first failure)."""
        rules = await self._get_enabled_rules(resource.id)

        if not rules:
            await self._log(resource, "access_denied", caller, success=False,
                            details={"reason": "yellow_no_rules"})
            return Decision(DecisionType.DENY,
                            reason="Yellow resource with no rules configured — denied by default")

        for rule in rules:
            rule_type = RuleType(rule.rule_type)

            if rule_type == RuleType.PURPOSE_REQUIRED:
                if not purpose or not purpose.strip():
                    await self._log(resource, "access_denied", caller, success=False,
                                    details={"reason": "purpose_required", "rule_id": rule.id})
                    return Decision(DecisionType.DENY, reason="Purpose is required for this resource")

            elif rule_type == RuleType.MAX_USES_PER_HOUR:
                count = await self._count_recent_grants(resource.id, hours=1)
                max_uses = rule.max_uses or 0
                if count >= max_uses:
                    await self._log(resource, "access_denied", caller, success=False,
                                    details={"reason": "rate_limit_exceeded",
                                             "current": count, "max": max_uses})
                    return Decision(DecisionType.DENY,
                                    reason=f"Rate limit exceeded ({count}/{max_uses} per hour)")

            elif rule_type == RuleType.TIME_WINDOW:
                now_hour = datetime.now(timezone.utc).hour
                start = rule.allowed_start_hour
                end = rule.allowed_end_hour
                if start is not None and end is not None:
                    if start <= end:
                        in_window = start <= now_hour < end
                    else:
                        # Wraps midnight (e.g., 22-6)
                        in_window = now_hour >= start or now_hour < end
                    if not in_window:
                        await self._log(resource, "access_denied", caller, success=False,
                                        details={"reason": "time_window",
                                                 "current_hour": now_hour,
                                                 "allowed": f"{start}-{end}"})
                        return Decision(DecisionType.DENY,
                                        reason=f"Access only allowed during {start}:00-{end}:00 UTC")

            elif rule_type == RuleType.APPROVE_EACH_USE:
                approval = await self._create_approval(resource, purpose, caller)
                await self._log(resource, "approval_requested", caller, success=True,
                                details={"approval_id": approval.id})
                return Decision(DecisionType.PENDING_APPROVAL,
                                reason="Approval required for each use",
                                approval_id=approval.id)

        # All rules passed
        await self._update_access_metadata(resource)
        await self._log(resource, "access_granted", caller, success=True,
                        details={"access_level": "yellow", "rules_passed": len(rules)})
        return Decision(DecisionType.ALLOW,
                        reason="All yellow rules passed",
                        value=resource.encrypted_value)

    async def _get_resource(self, name: str) -> Optional[VaultResource]:
        stmt = select(VaultResource).where(VaultResource.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_enabled_rules(self, resource_id: str) -> list[AccessRule]:
        stmt = (
            select(AccessRule)
            .where(AccessRule.resource_id == resource_id, AccessRule.enabled == True)
            .order_by(AccessRule.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _count_recent_grants(self, resource_id: str, hours: int = 1) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(func.count())
            .select_from(ActivityLog)
            .where(
                ActivityLog.resource_id == resource_id,
                ActivityLog.action == "access_granted",
                ActivityLog.timestamp >= cutoff,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def _update_access_metadata(self, resource: VaultResource) -> None:
        resource.access_count += 1
        resource.last_accessed_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def _create_approval(
        self, resource: VaultResource, purpose: str, caller: str
    ) -> ApprovalRequest:
        approval = ApprovalRequest(
            resource_id=resource.id,
            resource_name=resource.name,
            purpose=purpose or None,
            caller=caller or None,
            status="pending",
        )
        self.session.add(approval)
        await self.session.flush()
        return approval

    async def _log(
        self,
        resource: VaultResource,
        action: str,
        caller: str,
        success: bool,
        details: Optional[dict] = None,
    ) -> None:
        log = ActivityLog(
            action=action,
            resource_name=resource.name,
            resource_id=resource.id,
            caller=caller or None,
            success=success,
            details=details,
        )
        self.session.add(log)
        await self.session.flush()
