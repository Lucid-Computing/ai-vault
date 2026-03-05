"""Application settings via pydantic-settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


def _default_vault_dir() -> Path:
    return Path.home() / ".ai-vault"


class Settings(BaseSettings):
    """AI Vault configuration.

    Reads from environment variables prefixed with ``AI_VAULT_``.
    """

    vault_dir: Path = _default_vault_dir()
    db_path: Optional[Path] = None
    encryption_key: Optional[str] = None
    host: str = "127.0.0.1"
    port: int = 8484

    model_config = {"env_prefix": "AI_VAULT_"}

    @property
    def resolved_db_path(self) -> Path:
        if self.db_path:
            return self.db_path
        return self.vault_dir / "vault.db"

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.resolved_db_path}"


def get_settings() -> Settings:
    """Build settings, loading .env from vault dir if it exists."""
    vault_dir = Path(os.getenv("AI_VAULT_VAULT_DIR", str(_default_vault_dir())))
    env_file = vault_dir / ".env"

    if env_file.exists():
        # Load env file manually so pydantic-settings picks up the values
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k and k not in os.environ:
                    os.environ[k] = v

    return Settings()
