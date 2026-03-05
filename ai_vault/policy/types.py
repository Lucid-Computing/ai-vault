"""Policy engine types and enums."""

from __future__ import annotations

from enum import Enum
from typing import Optional


class AccessLevel(str, Enum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"


class RuleType(str, Enum):
    APPROVE_EACH_USE = "approve_each_use"
    MAX_USES_PER_HOUR = "max_uses_per_hour"
    PURPOSE_REQUIRED = "purpose_required"
    TIME_WINDOW = "time_window"


class DecisionType(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    PENDING_APPROVAL = "pending_approval"


class Decision:
    """Result of a policy evaluation."""

    __slots__ = ("type", "reason", "approval_id", "value")

    def __init__(
        self,
        type: DecisionType,
        reason: str = "",
        approval_id: Optional[str] = None,
        value: Optional[str] = None,
    ):
        self.type = type
        self.reason = reason
        self.approval_id = approval_id
        self.value = value

    @property
    def allowed(self) -> bool:
        return self.type == DecisionType.ALLOW

    @property
    def denied(self) -> bool:
        return self.type == DecisionType.DENY

    @property
    def pending(self) -> bool:
        return self.type == DecisionType.PENDING_APPROVAL

    def __repr__(self) -> str:
        return f"<Decision {self.type.value}: {self.reason}>"
