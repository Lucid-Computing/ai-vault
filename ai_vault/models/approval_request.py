"""ApprovalRequest model — human-in-the-loop approval for YELLOW resources."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_vault.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class ApprovalRequest(Base):
    """A pending approval request for a YELLOW resource access.

    Lifecycle: pending -> approved | denied | expired
    """

    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vault_resources.id", ondelete="CASCADE"), nullable=False
    )
    resource_name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    caller: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)

    # Relationship
    resource: Mapped["VaultResource"] = relationship(  # noqa: F821
        "VaultResource", back_populates="approval_requests"
    )

    def __repr__(self) -> str:
        return f"<ApprovalRequest resource={self.resource_name!r} status={self.status}>"
