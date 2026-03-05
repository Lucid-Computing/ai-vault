"""Tests for CLI commands."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_vault.cli.main import app

runner = CliRunner()


@pytest.fixture
def vault_dir(tmp_path, monkeypatch):
    """Set up a temporary vault directory."""
    vd = tmp_path / ".ai-vault"
    monkeypatch.setenv("AI_VAULT_VAULT_DIR", str(vd))
    return vd


class TestInit:
    def test_creates_db_and_key(self, vault_dir):
        result = runner.invoke(app, ["init", "--dir", str(vault_dir)])
        assert result.exit_code == 0
        assert (vault_dir / ".env").exists()
        assert (vault_dir / "vault.db").exists()
        assert "AI_VAULT_ENCRYPTION_KEY" in (vault_dir / ".env").read_text()

    def test_idempotent(self, vault_dir):
        runner.invoke(app, ["init", "--dir", str(vault_dir)])
        result = runner.invoke(app, ["init", "--dir", str(vault_dir)])
        assert result.exit_code == 0
        assert "already exists" in result.output


class TestAddAndList:
    def test_add_and_list(self, vault_dir):
        runner.invoke(app, ["init", "--dir", str(vault_dir)])
        result = runner.invoke(app, ["add", "MY_KEY", "--value", "sk-1234", "--level", "green"])
        assert result.exit_code == 0
        assert "MY_KEY" in result.output

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "MY_KEY" in result.output

    def test_add_duplicate_fails(self, vault_dir):
        runner.invoke(app, ["init", "--dir", str(vault_dir)])
        runner.invoke(app, ["add", "DUP", "--value", "val1", "--level", "green"])
        result = runner.invoke(app, ["add", "DUP", "--value", "val2", "--level", "red"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_list_json(self, vault_dir):
        runner.invoke(app, ["init", "--dir", str(vault_dir)])
        runner.invoke(app, ["add", "JSON_KEY", "--value", "val", "--level", "green"])

        result = runner.invoke(app, ["list", "--json"])
        assert result.exit_code == 0
        assert '"name": "JSON_KEY"' in result.output


class TestGet:
    def test_get_shows_metadata(self, vault_dir):
        runner.invoke(app, ["init", "--dir", str(vault_dir)])
        runner.invoke(app, ["add", "GET_TEST", "--value", "secret-val", "--level", "green", "--desc", "Test key"])

        result = runner.invoke(app, ["get", "GET_TEST"])
        assert result.exit_code == 0
        assert "GET_TEST" in result.output
        assert "green" in result.output
        assert "secret-val" not in result.output  # Not revealed

    def test_get_with_reveal(self, vault_dir):
        runner.invoke(app, ["init", "--dir", str(vault_dir)])
        runner.invoke(app, ["add", "REVEAL_TEST", "--value", "my-secret", "--level", "green"])

        result = runner.invoke(app, ["get", "REVEAL_TEST", "--reveal"])
        assert result.exit_code == 0
        assert "my-secret" in result.output

    def test_get_nonexistent(self, vault_dir):
        runner.invoke(app, ["init", "--dir", str(vault_dir)])
        result = runner.invoke(app, ["get", "NOPE"])
        assert result.exit_code == 1


class TestAllow:
    def test_changes_level(self, vault_dir):
        runner.invoke(app, ["init", "--dir", str(vault_dir)])
        runner.invoke(app, ["add", "ALLOW_TEST", "--value", "val", "--level", "red"])

        result = runner.invoke(app, ["allow", "ALLOW_TEST", "--level", "green"])
        assert result.exit_code == 0
        assert "green" in result.output


class TestDelete:
    def test_delete_resource(self, vault_dir):
        runner.invoke(app, ["init", "--dir", str(vault_dir)])
        runner.invoke(app, ["add", "DEL_ME", "--value", "val", "--level", "green"])

        result = runner.invoke(app, ["delete", "DEL_ME", "--force"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

        # Verify it's gone
        result = runner.invoke(app, ["get", "DEL_ME"])
        assert result.exit_code == 1

    def test_delete_nonexistent(self, vault_dir):
        runner.invoke(app, ["init", "--dir", str(vault_dir)])
        result = runner.invoke(app, ["delete", "NOPE", "--force"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_delete_with_confirmation(self, vault_dir):
        runner.invoke(app, ["init", "--dir", str(vault_dir)])
        runner.invoke(app, ["add", "CONFIRM_DEL", "--value", "val", "--level", "red"])

        # Deny confirmation
        result = runner.invoke(app, ["delete", "CONFIRM_DEL"], input="n\n")
        assert result.exit_code == 0
        assert "Cancelled" in result.output

        # Resource should still exist
        result = runner.invoke(app, ["get", "CONFIRM_DEL"])
        assert result.exit_code == 0

        # Accept confirmation
        result = runner.invoke(app, ["delete", "CONFIRM_DEL"], input="y\n")
        assert result.exit_code == 0
        assert "Deleted" in result.output


class TestImportEnv:
    def test_import_env_file(self, vault_dir, tmp_path):
        runner.invoke(app, ["init", "--dir", str(vault_dir)])

        env_file = tmp_path / "test.env"
        env_file.write_text("API_KEY=sk-1234\nDB_URL=postgres://localhost\n# comment\n\nEMPTY=")

        result = runner.invoke(app, ["import-env", str(env_file)])
        assert result.exit_code == 0
        assert "3 secrets" in result.output

        result = runner.invoke(app, ["list"])
        assert "API_KEY" in result.output
        assert "DB_URL" in result.output


class TestImportFromClaude:
    def test_import_servers(self, vault_dir, tmp_path):
        import json

        runner.invoke(app, ["init", "--dir", str(vault_dir)])

        claude_cfg = tmp_path / "claude.json"
        claude_cfg.write_text(json.dumps({
            "mcpServers": {
                "my-server": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y", "@example/mcp"],
                    "env": {"TOKEN": "abc"}
                },
                "other-server": {
                    "command": "python",
                    "args": ["-m", "mcp_server"]
                }
            }
        }))

        result = runner.invoke(app, ["import-from-claude", "--config", str(claude_cfg)])
        assert result.exit_code == 0
        assert "my-server" in result.output
        assert "other-server" in result.output
        assert "Imported 2" in result.output

        # Verify they're in the vault
        result = runner.invoke(app, ["list", "--type", "mcp_tool"])
        assert "my-server" in result.output
        assert "other-server" in result.output

    def test_skip_existing(self, vault_dir, tmp_path):
        import json

        runner.invoke(app, ["init", "--dir", str(vault_dir)])

        # Pre-add one server
        runner.invoke(app, ["add-tool", "my-server", "--command", "echo", "--level", "green"])

        claude_cfg = tmp_path / "claude.json"
        claude_cfg.write_text(json.dumps({
            "mcpServers": {
                "my-server": {"command": "npx", "args": ["-y", "@example/mcp"]},
                "new-server": {"command": "python"}
            }
        }))

        result = runner.invoke(app, ["import-from-claude", "--config", str(claude_cfg)])
        assert result.exit_code == 0
        assert "Skip" in result.output
        assert "Imported 1" in result.output
        assert "skipped 1" in result.output

    def test_config_not_found(self, vault_dir, tmp_path):
        runner.invoke(app, ["init", "--dir", str(vault_dir)])
        result = runner.invoke(app, ["import-from-claude", "--config", str(tmp_path / "nope.json")])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_empty_servers(self, vault_dir, tmp_path):
        import json

        runner.invoke(app, ["init", "--dir", str(vault_dir)])

        claude_cfg = tmp_path / "claude.json"
        claude_cfg.write_text(json.dumps({"mcpServers": {}}))

        result = runner.invoke(app, ["import-from-claude", "--config", str(claude_cfg)])
        assert result.exit_code == 0
        assert "No mcpServers" in result.output

    def test_custom_level(self, vault_dir, tmp_path):
        import json

        runner.invoke(app, ["init", "--dir", str(vault_dir)])

        claude_cfg = tmp_path / "claude.json"
        claude_cfg.write_text(json.dumps({
            "mcpServers": {
                "srv": {"command": "echo"}
            }
        }))

        result = runner.invoke(app, ["import-from-claude", "--config", str(claude_cfg), "--level", "green"])
        assert result.exit_code == 0

        result = runner.invoke(app, ["get", "srv"])
        assert "green" in result.output


class TestSetup:
    def test_full_setup(self, vault_dir, tmp_path):
        import json

        # Create a fake claude config with MCP servers
        claude_cfg = tmp_path / "claude.json"
        claude_cfg.write_text(json.dumps({
            "numStartups": 5,
            "mcpServers": {
                "my-tool": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y", "my-tool"],
                    "env": {}
                }
            },
            "userID": "test-user"
        }))

        result = runner.invoke(app, [
            "setup",
            "--dir", str(vault_dir),
            "--config", str(claude_cfg),
        ])
        assert result.exit_code == 0
        assert "Setup complete" in result.output

        # Vault was initialized
        assert (vault_dir / "vault.db").exists()

        # MCP server was imported
        result = runner.invoke(app, ["list", "--type", "mcp_tool"])
        assert "my-tool" in result.output

        # Claude config was updated
        updated = json.loads(claude_cfg.read_text())
        assert "ai-vault" in updated["mcpServers"]
        assert len(updated["mcpServers"]) == 1
        # Other keys preserved
        assert updated["numStartups"] == 5
        assert updated["userID"] == "test-user"

        # Backup was created
        backup = tmp_path / ".claude.json.pre-vault-backup"
        assert backup.exists()
        backup_data = json.loads(backup.read_text())
        assert "my-tool" in backup_data["mcpServers"]

    def test_setup_skip_import(self, vault_dir, tmp_path):
        import json

        claude_cfg = tmp_path / "claude.json"
        claude_cfg.write_text(json.dumps({
            "mcpServers": {
                "something": {"command": "echo"}
            }
        }))

        result = runner.invoke(app, [
            "setup",
            "--dir", str(vault_dir),
            "--config", str(claude_cfg),
            "--skip-import",
        ])
        assert result.exit_code == 0

        # Tool was NOT imported
        result = runner.invoke(app, ["list", "--type", "mcp_tool"])
        assert "something" not in result.output

    def test_setup_idempotent(self, vault_dir, tmp_path):
        import json

        claude_cfg = tmp_path / "claude.json"
        claude_cfg.write_text(json.dumps({
            "mcpServers": {
                "tool1": {"command": "echo"}
            }
        }))

        # First setup
        runner.invoke(app, ["setup", "--dir", str(vault_dir), "--config", str(claude_cfg)])

        # Second setup - should not fail
        result = runner.invoke(app, ["setup", "--dir", str(vault_dir), "--config", str(claude_cfg)])
        assert result.exit_code == 0
        assert "Already configured" in result.output

    def test_setup_no_config(self, vault_dir, tmp_path):
        result = runner.invoke(app, [
            "setup",
            "--dir", str(vault_dir),
            "--config", str(tmp_path / "nonexistent.json"),
        ])
        assert result.exit_code == 0
        # Vault still initialized even without config
        assert (vault_dir / "vault.db").exists()
