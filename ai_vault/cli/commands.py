"""CLI command implementations."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def _run_async(coro):
    """Run an async coroutine from sync CLI context."""
    return asyncio.run(coro)


def init_command(
    vault_dir: Optional[Path] = typer.Option(None, "--dir", help="Vault directory"),
):
    """Initialize the AI Vault (create DB, encryption key, config)."""
    from ai_vault.encryption import generate_encryption_key

    vault_dir = vault_dir or Path.home() / ".ai-vault"
    vault_dir.mkdir(parents=True, exist_ok=True)

    env_file = vault_dir / ".env"
    db_path = vault_dir / "vault.db"

    # Generate encryption key if not exists
    if not env_file.exists():
        key = generate_encryption_key()
        env_file.write_text(f"AI_VAULT_ENCRYPTION_KEY={key}\n")
        os.chmod(str(env_file), 0o600)
        console.print(f"[green]Generated encryption key[/green] → {env_file}")
    else:
        console.print(f"[yellow]Encryption key already exists[/yellow] → {env_file}")

    # Set up environment for DB init
    os.environ["AI_VAULT_VAULT_DIR"] = str(vault_dir)
    # Load the key into env
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

    # Init DB
    async def _init_db():
        from ai_vault.db import get_engine, init_db, reset_engine

        reset_engine()
        engine = get_engine(f"sqlite+aiosqlite:///{db_path}")
        await init_db(engine)
        await engine.dispose()

    _run_async(_init_db())

    # Set file permissions
    if db_path.exists():
        os.chmod(str(db_path), 0o600)

    console.print(f"[green]Database initialized[/green] → {db_path}")
    console.print(f"\n[bold]AI Vault ready![/bold] Add resources with: ai-vault add NAME --value VALUE")


def add_command(
    name: str = typer.Argument(help="Resource name"),
    value: Optional[str] = typer.Option(None, "--value", "-v", help="Secret value"),
    resource_type: str = typer.Option("secret", "--type", "-t", help="Resource type: secret, file, mcp_tool"),
    level: str = typer.Option("red", "--level", "-l", help="Access level: red, yellow, green"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Description"),
    file_path: Optional[str] = typer.Option(None, "--path", "-p", help="File path (for file type)"),
):
    """Add a resource to the vault."""
    from ai_vault.settings import get_settings

    if resource_type not in ("secret", "file", "mcp_tool"):
        console.print(f"[red]Invalid type:[/red] {resource_type}. Must be secret, file, or mcp_tool")
        raise typer.Exit(1)

    if level not in ("red", "yellow", "green"):
        console.print(f"[red]Invalid level:[/red] {level}. Must be red, yellow, or green")
        raise typer.Exit(1)

    async def _add():
        from ai_vault.db import get_engine, get_session_factory, init_db, reset_engine
        from ai_vault.encryption import encrypt
        from ai_vault.models import VaultResource

        settings = get_settings()
        reset_engine()
        engine = get_engine(settings.database_url)
        factory = get_session_factory(engine)

        async with factory() as session:
            encrypted_value = None
            if value and resource_type == "secret":
                encrypted_value = encrypt(value)

            resource = VaultResource(
                name=name,
                resource_type=resource_type,
                access_level=level,
                encrypted_value=encrypted_value,
                file_path=file_path,
                description=description,
            )
            session.add(resource)
            try:
                await session.commit()
            except Exception as e:
                if "UNIQUE" in str(e).upper():
                    console.print(f"[red]Resource '{name}' already exists[/red]")
                    raise typer.Exit(1)
                raise

            level_colors = {"red": "red", "yellow": "yellow", "green": "green"}
            color = level_colors.get(level, "white")
            console.print(f"[{color}]●[/{color}] Added [{color}]{name}[/{color}] ({resource_type}, {level})")

        await engine.dispose()

    _run_async(_add())


def list_command(
    resource_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
    level: Optional[str] = typer.Option(None, "--level", "-l", help="Filter by access level"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List vault resources."""
    import json

    async def _list():
        from sqlalchemy import select

        from ai_vault.db import get_engine, get_session_factory, reset_engine
        from ai_vault.models import VaultResource
        from ai_vault.settings import get_settings

        settings = get_settings()
        reset_engine()
        engine = get_engine(settings.database_url)
        factory = get_session_factory(engine)

        async with factory() as session:
            stmt = select(VaultResource).order_by(VaultResource.name)
            if resource_type:
                stmt = stmt.where(VaultResource.resource_type == resource_type)
            if level:
                stmt = stmt.where(VaultResource.access_level == level)

            result = await session.execute(stmt)
            resources = result.scalars().all()

            if json_output:
                data = [
                    {
                        "name": r.name,
                        "type": r.resource_type,
                        "level": r.access_level,
                        "description": r.description,
                        "access_count": r.access_count,
                    }
                    for r in resources
                ]
                console.print(json.dumps(data, indent=2))
            else:
                if not resources:
                    console.print("[dim]No resources found. Add one with: ai-vault add NAME --value VALUE[/dim]")
                    return

                table = Table(title="Vault Resources")
                table.add_column("Name", style="bold")
                table.add_column("Type")
                table.add_column("Level")
                table.add_column("Description")
                table.add_column("Accesses", justify="right")

                level_colors = {"red": "red", "yellow": "yellow", "green": "green"}
                for r in resources:
                    color = level_colors.get(r.access_level, "white")
                    table.add_row(
                        r.name,
                        r.resource_type,
                        f"[{color}]●[/{color}] {r.access_level}",
                        r.description or "",
                        str(r.access_count),
                    )

                console.print(table)

        await engine.dispose()

    _run_async(_list())


def get_command(
    name: str = typer.Argument(help="Resource name"),
    reveal: bool = typer.Option(False, "--reveal", "-r", help="Decrypt and show value"),
):
    """Get a resource's details (optionally decrypt value)."""

    async def _get():
        from sqlalchemy import select

        from ai_vault.db import get_engine, get_session_factory, reset_engine
        from ai_vault.encryption import decrypt, DecryptionError
        from ai_vault.models import VaultResource
        from ai_vault.settings import get_settings

        settings = get_settings()
        reset_engine()
        engine = get_engine(settings.database_url)
        factory = get_session_factory(engine)

        async with factory() as session:
            stmt = select(VaultResource).where(VaultResource.name == name)
            result = await session.execute(stmt)
            resource = result.scalar_one_or_none()

            if not resource:
                console.print(f"[red]Resource '{name}' not found[/red]")
                raise typer.Exit(1)

            level_colors = {"red": "red", "yellow": "yellow", "green": "green"}
            color = level_colors.get(resource.access_level, "white")

            console.print(f"\n[bold]{resource.name}[/bold]")
            console.print(f"  Type:    {resource.resource_type}")
            console.print(f"  Level:   [{color}]●[/{color}] {resource.access_level}")
            if resource.description:
                console.print(f"  Desc:    {resource.description}")
            if resource.service:
                console.print(f"  Service: {resource.service}")
            console.print(f"  Accesses: {resource.access_count}")

            if reveal and resource.encrypted_value:
                try:
                    value = decrypt(resource.encrypted_value)
                    console.print(f"  Value:   [dim]{value}[/dim]")
                except DecryptionError:
                    console.print(f"  Value:   [red]<decryption failed>[/red]")
            elif resource.encrypted_value:
                console.print(f"  Value:   [dim]<encrypted — use --reveal to show>[/dim]")

            if resource.file_path:
                console.print(f"  Path:    {resource.file_path}")

        await engine.dispose()

    _run_async(_get())


def allow_command(
    name: str = typer.Argument(help="Resource name"),
    level: str = typer.Option(..., "--level", "-l", help="New access level: red, yellow, green"),
    rule: Optional[str] = typer.Option(None, "--rule", "-r", help="Add rule: approve_each_use, max_uses_per_hour, purpose_required, time_window"),
    max_uses: Optional[int] = typer.Option(None, "--max-uses", help="Max uses per hour (for max_uses_per_hour rule)"),
):
    """Change a resource's access level and optionally add rules."""
    if level not in ("red", "yellow", "green"):
        console.print(f"[red]Invalid level:[/red] {level}")
        raise typer.Exit(1)

    async def _allow():
        from sqlalchemy import select

        from ai_vault.db import get_engine, get_session_factory, reset_engine
        from ai_vault.models import AccessRule, VaultResource
        from ai_vault.settings import get_settings

        settings = get_settings()
        reset_engine()
        engine = get_engine(settings.database_url)
        factory = get_session_factory(engine)

        async with factory() as session:
            stmt = select(VaultResource).where(VaultResource.name == name)
            result = await session.execute(stmt)
            resource = result.scalar_one_or_none()

            if not resource:
                console.print(f"[red]Resource '{name}' not found[/red]")
                raise typer.Exit(1)

            resource.access_level = level

            if rule:
                new_rule = AccessRule(
                    resource_id=resource.id,
                    rule_type=rule,
                    enabled=True,
                    max_uses=max_uses,
                )
                session.add(new_rule)

            await session.commit()

            level_colors = {"red": "red", "yellow": "yellow", "green": "green"}
            color = level_colors.get(level, "white")
            console.print(f"[{color}]●[/{color}] {name} → {level}")
            if rule:
                console.print(f"  + Rule: {rule}")

        await engine.dispose()

    _run_async(_allow())


def serve_command(
    port: int = typer.Option(8484, "--port", "-p", help="Server port"),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host (default: localhost only)"),
    mcp_only: bool = typer.Option(False, "--mcp", help="MCP-only mode (stdio transport for Claude Desktop)"),
):
    """Start the AI Vault server (API + MCP + Web UI)."""
    if mcp_only:
        # Stdio MCP mode for Claude Desktop/Code
        # IMPORTANT: No stdout output allowed — it corrupts the JSON-RPC stream
        import logging
        logging.disable(logging.CRITICAL)

        from ai_vault.mcp_server.server import mcp
        import ai_vault.mcp_server.tools  # noqa: F401

        from ai_vault.settings import get_settings
        from ai_vault.db import get_engine, init_db, reset_engine

        settings = get_settings()
        reset_engine()

        async def _init():
            engine = get_engine(settings.database_url)
            await init_db(engine)

        _run_async(_init())

        # Also start the Web UI server in a background thread
        # so the dashboard is available at localhost:8484 without extra steps
        import threading

        def _start_web_ui():
            import uvicorn
            os.environ["AI_VAULT_HOST"] = host
            os.environ["AI_VAULT_PORT"] = str(port)
            from ai_vault.main import create_app
            app = create_app()
            uvicorn.run(app, host=host, port=port, log_level="error")

        web_thread = threading.Thread(target=_start_web_ui, daemon=True)
        web_thread.start()

        mcp.run(transport="stdio")
    else:
        console.print(f"[bold]Starting AI Vault server on {host}:{port}...[/bold]")
        console.print(f"  Web UI:  http://{host}:{port}/")
        console.print(f"  API:     http://{host}:{port}/api/")
        console.print(f"  MCP:     http://{host}:{port}/mcp/")

        import uvicorn

        # Set settings for the app
        os.environ["AI_VAULT_HOST"] = host
        os.environ["AI_VAULT_PORT"] = str(port)

        from ai_vault.main import create_app

        app = create_app()
        uvicorn.run(app, host=host, port=port, log_level="info")


def add_tool_command(
    name: str = typer.Argument(help="Tool name (used as vault resource name)"),
    command: str = typer.Option(..., "--command", "-c", help="Server command (e.g. npx, python)"),
    arg: Optional[list[str]] = typer.Option(None, "--arg", "-a", help="Server command arguments (repeatable)"),
    tool: Optional[str] = typer.Option(None, "--tool", "-T", help="Downstream tool name (defaults to NAME)"),
    level: str = typer.Option("yellow", "--level", "-l", help="Access level: red, yellow, green"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Description"),
    env: Optional[list[str]] = typer.Option(None, "--env", "-e", help="Environment vars as KEY=VALUE (repeatable)"),
):
    """Register an MCP tool for policy-controlled access."""
    import json as _json

    if level not in ("red", "yellow", "green"):
        console.print(f"[red]Invalid level:[/red] {level}. Must be red, yellow, or green")
        raise typer.Exit(1)

    # Build the server config JSON
    server_config: dict = {"command": command}
    if arg:
        server_config["args"] = list(arg)
    if env:
        env_dict = {}
        for item in env:
            if "=" not in item:
                console.print(f"[red]Invalid env format:[/red] '{item}'. Use KEY=VALUE")
                raise typer.Exit(1)
            k, v = item.split("=", 1)
            env_dict[k.strip()] = v.strip()
        server_config["env"] = env_dict

    mcp_server_url = _json.dumps(server_config)

    async def _add():
        from ai_vault.db import get_engine, get_session_factory, reset_engine
        from ai_vault.models import VaultResource
        from ai_vault.settings import get_settings

        settings = get_settings()
        reset_engine()
        engine = get_engine(settings.database_url)
        factory = get_session_factory(engine)

        async with factory() as session:
            resource = VaultResource(
                name=name,
                resource_type="mcp_tool",
                access_level=level,
                mcp_server_url=mcp_server_url,
                mcp_tool_name=tool or name,
                description=description,
            )
            session.add(resource)
            try:
                await session.commit()
            except Exception as e:
                if "UNIQUE" in str(e).upper():
                    console.print(f"[red]Resource '{name}' already exists[/red]")
                    raise typer.Exit(1)
                raise

            level_colors = {"red": "red", "yellow": "yellow", "green": "green"}
            color = level_colors.get(level, "white")
            console.print(f"[{color}]●[/{color}] Added tool [{color}]{name}[/{color}] ({level})")
            console.print(f"  Server: {command} {' '.join(arg or [])}")
            console.print(f"  Tool:   {tool or name}")

        await engine.dispose()

    _run_async(_add())


def delete_command(
    name: str = typer.Argument(help="Resource name to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """Delete a resource from the vault."""

    async def _delete():
        from sqlalchemy import select

        from ai_vault.db import get_engine, get_session_factory, reset_engine
        from ai_vault.models import VaultResource
        from ai_vault.settings import get_settings

        settings = get_settings()
        reset_engine()
        engine = get_engine(settings.database_url)
        factory = get_session_factory(engine)

        async with factory() as session:
            stmt = select(VaultResource).where(VaultResource.name == name)
            result = await session.execute(stmt)
            resource = result.scalar_one_or_none()

            if not resource:
                console.print(f"[red]Resource '{name}' not found[/red]")
                raise typer.Exit(1)

            if not force:
                level_colors = {"red": "red", "yellow": "yellow", "green": "green"}
                color = level_colors.get(resource.access_level, "white")
                console.print(f"  [{color}]●[/{color}] {resource.name} ({resource.resource_type}, {resource.access_level})")
                if not typer.confirm("Delete this resource?"):
                    console.print("[dim]Cancelled[/dim]")
                    raise typer.Exit(0)

            await session.delete(resource)
            await session.commit()
            console.print(f"[green]Deleted[/green] {name}")

        await engine.dispose()

    _run_async(_delete())


def import_env_command(
    file: Path = typer.Argument(help="Path to .env file"),
    level: str = typer.Option("red", "--level", "-l", help="Default access level for imported vars"),
):
    """Import variables from a .env file as vault secrets."""
    if not file.exists():
        console.print(f"[red]File not found:[/red] {file}")
        raise typer.Exit(1)

    async def _import():
        from ai_vault.db import get_engine, get_session_factory, init_db, reset_engine
        from ai_vault.encryption import encrypt
        from ai_vault.models import VaultResource
        from ai_vault.settings import get_settings

        settings = get_settings()
        reset_engine()
        engine = get_engine(settings.database_url)
        await init_db(engine)
        factory = get_session_factory(engine)

        count = 0
        async with factory() as session:
            for line in file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'\"")

                if not key:
                    continue

                encrypted = encrypt(value)
                resource = VaultResource(
                    name=key,
                    resource_type="secret",
                    access_level=level,
                    encrypted_value=encrypted,
                    description=f"Imported from {file.name}",
                )
                session.add(resource)
                count += 1

            try:
                await session.commit()
                console.print(f"[green]Imported {count} secrets[/green] from {file} as [{level}]{level}[/{level}]")
            except Exception as e:
                if "UNIQUE" in str(e).upper():
                    console.print("[red]Some variable names already exist in vault[/red]")
                    raise typer.Exit(1)
                raise

        await engine.dispose()

    _run_async(_import())


def import_from_claude_command(
    level: str = typer.Option("yellow", "--level", "-l", help="Default access level for imported tools"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to claude config (default: ~/.claude.json)"),
):
    """Import MCP servers from Claude Code config as vault tools."""
    import json as _json

    if level not in ("red", "yellow", "green"):
        console.print(f"[red]Invalid level:[/red] {level}. Must be red, yellow, or green")
        raise typer.Exit(1)

    config_path = config or Path.home() / ".claude.json"
    if not config_path.exists():
        console.print(f"[red]Config not found:[/red] {config_path}")
        raise typer.Exit(1)

    try:
        data = _json.loads(config_path.read_text())
    except _json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON:[/red] {e}")
        raise typer.Exit(1)

    servers = data.get("mcpServers", {})
    if not servers:
        console.print("[yellow]No mcpServers found in config[/yellow]")
        raise typer.Exit(0)

    async def _import():
        from sqlalchemy import select

        from ai_vault.db import get_engine, get_session_factory, init_db, reset_engine
        from ai_vault.models import VaultResource
        from ai_vault.settings import get_settings

        settings = get_settings()
        reset_engine()
        engine = get_engine(settings.database_url)
        await init_db(engine)
        factory = get_session_factory(engine)

        imported = 0
        skipped = 0

        async with factory() as session:
            for name, server_cfg in servers.items():
                # Check if already exists
                stmt = select(VaultResource).where(VaultResource.name == name)
                result = await session.execute(stmt)
                if result.scalar_one_or_none():
                    console.print(f"  [yellow]Skip[/yellow] {name} (already exists)")
                    skipped += 1
                    continue

                # Build server config JSON
                server_json = {}
                if "command" in server_cfg:
                    server_json["command"] = server_cfg["command"]
                if "args" in server_cfg:
                    server_json["args"] = server_cfg["args"]
                if "env" in server_cfg:
                    server_json["env"] = server_cfg["env"]

                resource = VaultResource(
                    name=name,
                    resource_type="mcp_tool",
                    access_level=level,
                    mcp_server_url=_json.dumps(server_json),
                    mcp_tool_name=name,
                    description=f"Imported from {config_path.name}",
                )
                session.add(resource)
                imported += 1

                level_colors = {"red": "red", "yellow": "yellow", "green": "green"}
                color = level_colors.get(level, "white")
                console.print(f"  [{color}]●[/{color}] {name}")

            await session.commit()

        await engine.dispose()

        console.print(f"\n[green]Imported {imported} tool(s)[/green]", end="")
        if skipped:
            console.print(f", [yellow]skipped {skipped}[/yellow]")
        else:
            console.print()

    _run_async(_import())


def setup_command(
    level: str = typer.Option("yellow", "--level", "-l", help="Default access level for imported tools"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to Claude config (default: ~/.claude.json)"),
    vault_dir: Optional[Path] = typer.Option(None, "--dir", help="Vault directory (default: ~/.ai-vault)"),
    skip_import: bool = typer.Option(False, "--skip-import", help="Skip importing existing MCP servers"),
):
    """One-command setup: init vault, import MCP servers, configure Claude to use AI Vault.

    This command:
    1. Initializes the vault (creates DB + encryption key)
    2. Imports your existing MCP servers from Claude's config
    3. Backs up your Claude config
    4. Configures Claude to use AI Vault as the sole MCP server

    After setup, all MCP tool access goes through the vault's policy proxy.
    Run 'ai-vault serve' to start the Web UI for managing access levels.
    """
    import json as _json
    import shutil

    config_path = config or Path.home() / ".claude.json"
    vd = vault_dir or Path.home() / ".ai-vault"

    # --- Step 1: Init vault ---
    console.print("\n[bold]Step 1:[/bold] Initialize vault")
    init_command(vault_dir=vd)

    # --- Step 2: Import existing MCP servers ---
    if not skip_import and config_path.exists():
        console.print("\n[bold]Step 2:[/bold] Import existing MCP servers")
        try:
            data = _json.loads(config_path.read_text())
        except _json.JSONDecodeError:
            console.print("[yellow]Could not parse Claude config, skipping import[/yellow]")
            data = {}

        servers = data.get("mcpServers", {})
        if servers:
            # Call import directly instead of via typer to avoid re-parsing args
            import_from_claude_command(level=level, config=config_path)
        else:
            console.print("  [dim]No existing MCP servers to import[/dim]")
    else:
        console.print("\n[bold]Step 2:[/bold] [dim]Skipped import[/dim]")

    # --- Step 3: Configure Claude to use AI Vault ---
    console.print("\n[bold]Step 3:[/bold] Configure Claude Code")

    # Find our own binary path
    ai_vault_bin = Path(sys.argv[0]).resolve()
    if not ai_vault_bin.exists():
        # Fallback: derive from the venv
        ai_vault_bin = Path(sys.executable).parent / "ai-vault"

    if not config_path.exists():
        console.print(f"  [yellow]Claude config not found at {config_path}[/yellow]")
        vault_entry = {
            "type": "stdio",
            "command": str(ai_vault_bin),
            "args": ["serve", "--mcp"],
        }
        console.print(f"  Add this to your Claude config's mcpServers:")
        console.print(f"  [dim]{_json.dumps({'ai-vault': vault_entry}, indent=2)}[/dim]")
        return

    try:
        claude_data = _json.loads(config_path.read_text())
    except _json.JSONDecodeError:
        console.print(f"  [red]Could not parse {config_path}[/red]")
        raise typer.Exit(1)

    old_servers = claude_data.get("mcpServers", {})

    # Check if already configured
    if "ai-vault" in old_servers and len(old_servers) == 1:
        console.print("  [green]Already configured![/green]")
        _print_setup_summary(ai_vault_bin, vd)
        return

    # Backup
    backup_path = config_path.parent / ".claude.json.pre-vault-backup"
    if not backup_path.exists():
        shutil.copy2(str(config_path), str(backup_path))
        console.print(f"  Backed up → {backup_path}")
    else:
        console.print(f"  [dim]Backup already exists → {backup_path}[/dim]")

    # Replace mcpServers with just ai-vault
    claude_data["mcpServers"] = {
        "ai-vault": {
            "type": "stdio",
            "command": str(ai_vault_bin),
            "args": ["serve", "--mcp"],
        }
    }

    config_path.write_text(_json.dumps(claude_data, indent=2) + "\n")
    console.print("  [green]Updated mcpServers → ai-vault only[/green]")

    _print_setup_summary(ai_vault_bin, vd)


def _print_setup_summary(ai_vault_bin: Path, vault_dir: Path):
    """Print the post-setup summary."""
    console.print("\n[bold green]Setup complete![/bold green]\n")
    console.print("  [bold]What happened:[/bold]")
    console.print("  1. Vault initialized at [dim]~/.ai-vault/[/dim]")
    console.print("  2. Existing MCP servers imported into vault")
    console.print("  3. Claude configured to route all tool access through AI Vault")
    console.print()
    console.print("  [bold]Next steps:[/bold]")
    console.print(f"  • Restart Claude Code to pick up the new config")
    console.print(f"  • Run [bold]{ai_vault_bin} serve[/bold] to open the Web UI")
    console.print(f"  • Manage access levels at [bold]http://127.0.0.1:8484[/bold]")
    console.print()
    console.print("  [bold]To undo:[/bold]")
    console.print(f"  • Restore backup: [dim]cp ~/.claude.json.pre-vault-backup ~/.claude.json[/dim]")
