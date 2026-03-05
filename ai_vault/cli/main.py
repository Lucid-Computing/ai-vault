"""AI Vault CLI entry point."""

from __future__ import annotations

import typer

from ai_vault.cli.commands import (
    add_command,
    add_tool_command,
    allow_command,
    delete_command,
    get_command,
    import_env_command,
    import_from_claude_command,
    init_command,
    list_command,
    serve_command,
    setup_command,
)

app = typer.Typer(
    name="ai-vault",
    help="Local-first AI resource access manager.",
    no_args_is_help=True,
)

app.command("init")(init_command)
app.command("add")(add_command)
app.command("add-tool")(add_tool_command)
app.command("list")(list_command)
app.command("get")(get_command)
app.command("delete")(delete_command)
app.command("allow")(allow_command)
app.command("serve")(serve_command)
app.command("import-env")(import_env_command)
app.command("import-from-claude")(import_from_claude_command)
app.command("setup")(setup_command)


if __name__ == "__main__":
    app()
