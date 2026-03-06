# AI Vault

**A firewall for your AI agent's resource access.**

AI Vault sits between Claude (or any MCP client) and your resources — secrets, API keys, MCP tools — giving you visibility and control over what your AI agent can access. Every access is logged, and you decide what's allowed.

```
Claude Code  →  AI Vault  →  Secrets, API Keys, MCP Tools
                   ↓
              Dashboard at
           localhost:8484
```

![AI Vault Dashboard](docs/dashboard.png)

## Why?

AI agents are getting access to more and more: your API keys, database credentials, MCP tools that can search the web, run code, or hit external APIs. But today there's no easy way to see what your agent accessed, control which secrets it can read, or block specific tools without removing them entirely.

AI Vault adds a control layer for everything your AI touches:

- **🔴 Blocked** — Resource is invisible to the AI. Access denied, attempt logged.
- **🟡 Ask** — Requires your approval before each use.
- **🟢 Open** — Works freely. Every access is still logged.

This applies to **secrets** (API keys, tokens, credentials), **MCP tools** (web search, code execution, GitHub), and **files**.

## What You Can Manage

| Resource Type | Examples | What Vault Does |
|--------------|----------|----------------|
| **Secrets** | API keys, tokens, database passwords | Encrypted at rest (AES-256-GCM), access-controlled per key, every read logged |
| **MCP Tools** | GitHub, Brave Search, Puppeteer, custom tools | Proxied through vault, per-tool access levels, full call audit trail |
| **Files** | Config files, credentials files | Access-controlled, read attempts logged |

## Quick Start

**Prerequisites:** Python 3.11+, Node.js 18+ (for UI build)

```bash
# Clone and install
git clone https://github.com/Lucid-Computing/ai-vault.git
cd ai-vault
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Build the dashboard UI
cd ui && npm install && npm run build && cd ..

# One-command setup: imports your existing MCP tools + configures Claude
ai-vault setup

# Restart Claude Code to pick up the new config
```

That's it. Your existing MCP servers are imported into the vault, and the dashboard is available at **http://localhost:8484** whenever Claude Code is running.

## What happens after setup?

1. **All your existing MCP tools** are imported into the vault (default: Ask level)
2. **Claude's config** (`~/.claude.json`) is updated to route through AI Vault
3. A **backup** of your original config is saved at `~/.claude.json.pre-vault-backup`
4. The **Web UI** starts automatically alongside the MCP server — no extra terminal needed

## Dashboard

The dashboard at `localhost:8484` shows:

- **Pending Approvals** — approve or deny access requests with one click
- **Most Accessed** — see which resources your AI uses most
- **Recent Activity** — full audit trail of every access, tool call, and approval
- **Resource Management** — add, edit, or remove secrets, tools, and files

## Managing Secrets

Store API keys and credentials in the vault instead of `.env` files or plaintext configs. The AI can request access, but you control who sees what.

```bash
# Add secrets with access control
ai-vault add OPENAI_API_KEY --value "sk-..." --level green    # AI can read freely
ai-vault add PROD_DB_PASSWORD --value "..." --level red       # AI never sees this
ai-vault add STRIPE_SECRET --value "sk_live_..." --level yellow  # AI must ask first
```

When Claude needs a secret, it calls `vault_get_resource` — the vault checks the access level, logs the attempt, and returns the value (or blocks it).

## Managing MCP Tools

After setup, add new MCP tools through the vault instead of editing `~/.claude.json` directly:

**Via CLI:**
```bash
ai-vault add-tool github --command npx --arg "-y" --arg "@modelcontextprotocol/server-github"
ai-vault add-tool brave-search --command npx --arg "-y" --arg "@modelcontextprotocol/server-brave-search" --env "BRAVE_API_KEY=your-key"
```

**Via Dashboard:**
1. Open http://localhost:8484/resources
2. Click **+ Add Resource** → select **MCP Tool**
3. Fill in the command, arguments, and access level

The vault manages MCP server lifecycle — it starts downstream servers on demand, proxies tool calls, and shuts them down when idle.

## CLI Reference

```bash
ai-vault setup                    # One-command setup (init + import + configure)
ai-vault list                     # List all resources
ai-vault add NAME --value SECRET  # Add a secret
ai-vault add-tool NAME -c CMD     # Register an MCP tool
ai-vault delete NAME              # Delete a resource
ai-vault serve                    # Start the web UI standalone
ai-vault import-from-claude       # Import MCP servers from ~/.claude.json
```

## Architecture

AI Vault runs as a single process that serves two interfaces:

- **MCP stdio** — Claude Code talks to this (launched automatically)
- **HTTP on :8484** — Dashboard, REST API, and the approval UI

All data is stored locally in `~/.ai-vault/vault.db` (SQLite). Secrets are encrypted with AES-256-GCM. Nothing leaves your machine.

```
~/.ai-vault/
├── .env          # Encryption key (chmod 600)
└── vault.db      # SQLite database (encrypted secrets, access logs, policies)
```

## How It Works

When Claude requests any resource through the vault:

1. **Policy check** — Is the resource 🔴 blocked, 🟡 ask, or 🟢 open?
2. **If open** — Returns the secret / proxies the tool call, logs it
3. **If ask** — Creates an approval request, waits for you to allow/deny in the dashboard
4. **If blocked** — Returns an error to Claude, logs the attempt

## Undoing Setup

```bash
# Restore your original Claude config
cp ~/.claude.json.pre-vault-backup ~/.claude.json
# Restart Claude Code
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests (126 passing)
pytest

# Run the UI in dev mode
cd ui && npm run dev
```

## License

MIT

---

<p align="center">
  Built by the team behind <a href="https://lucid.observer">Lucid Observer</a> — AI agent observability for teams.
</p>
