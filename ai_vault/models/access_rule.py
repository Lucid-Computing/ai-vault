"""AccessRule model — YELLOW-level access rules for resources."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_vault.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class AccessRule(Base):
    """A rule that governs access to a YELLOW resource.

    Rule types:
    - ``approve_each_use``: Requires human approval for every access.
    - ``max_uses_per_hour``: Rate limits access (requires ``max_uses``).
    - ``purpose_required``: Caller must provide a non-empty purpose string.
    - ``time_window``: Access only allowed during specified UTC hours.

    All enabled rules for a resource are AND-ed: every rule must pass.
    """

    __tablename__ = "access_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vault_resources.id", ondelete="CASCADE"), nullable=False
    )
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Rate limit params
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Time window params (UTC hours 0-23)
    allowed_start_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allowed_end_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # Relationship
    resource: Mapped["VaultResource"] = relationship(  # noqa: F821
        "VaultResource", back_populates="rules"
    )

    def __repr__(self) -> str:
        return f"<AccessRule type={self.rule_type!r} enabled={self.enabled}>"
