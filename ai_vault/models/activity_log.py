"""ActivityLog model — append-only audit trail."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ai_vault.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class ActivityLog(Base):
    """An immutable audit log entry.

    Records every access attempt and administrative action on vault resources.
    """

    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_name: Mapped[str] = mapped_column(String(200), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    caller: Mapped[str | None] = mapped_column(String(200), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<ActivityLog action={self.action!r} resource={self.resource_name!r} success={self.success}>"
