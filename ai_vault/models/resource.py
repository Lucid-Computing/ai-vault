"""VaultResource model — unified storage for secrets, files, and MCP tools."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_vault.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class VaultResource(Base):
    """A resource managed by the vault.

    Resource types:
    - ``secret``: An encrypted secret value (API key, token, password).
    - ``file``: A reference to a local file or directory path.
    - ``mcp_tool``: A reference to an MCP server tool.

    Access levels:
    - ``red``: Invisible to AI, always denied.
    - ``yellow``: Rules evaluated; all enabled rules must pass.
    - ``green``: Auto-granted, no friction.
    """

    __tablename__ = "vault_resources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    access_level: Mapped[str] = mapped_column(String(10), nullable=False, default="red")

    # Secret-specific
    encrypted_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    # File-specific
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # MCP tool-specific
    mcp_server_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mcp_tool_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Metadata
    service: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    rules: Mapped[list["AccessRule"]] = relationship(  # noqa: F821
        "AccessRule", back_populates="resource", cascade="all, delete-orphan"
    )
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(  # noqa: F821
        "ApprovalRequest", back_populates="resource", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<VaultResource name={self.name!r} type={self.resource_type} level={self.access_level}>"
