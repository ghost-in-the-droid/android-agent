---
title: "MCP Clients"
description: Every tested MCP client that can drive Ghost — Claude Code, Cursor, Windsurf, Zed, Continue, Cline, Codex, Claude Desktop, Cherry Studio, and ChatGPT — with the exact config for each.
---

The [MCP Server](../mcp-server/) page covers *what* Ghost exposes (41 tools). This page covers *who can call it* — every MCP client we've wired up, and the exact config for each.

## Ghost's two transports

Every client below connects through one of these:

| Transport | How to point a client at Ghost |
|---|---|
| **stdio** | Run the command `android-agent-mcp` (equivalently `python3 -m gitd.mcp_server`) |
| **streamable HTTP** | URL `http://localhost:8002/mcp` — start the server first with `python3 -m gitd.mcp_server` |

stdio is the simplest and works everywhere (the client launches Ghost as a subprocess). HTTP is for clients that prefer a running server, or when Ghost lives on another machine.

## Compatibility matrix

| Client | MCP | stdio | HTTP | Config location |
|---|---|:--:|:--:|---|
| [Claude Code](#claude-code) | ✅ | ✅ | ✅ | `.mcp.json` / `~/.claude.json` |
| [Cursor](#cursor) | ✅ | ✅ | ✅ | `.cursor/mcp.json` |
| [Windsurf](#windsurf) | ✅ | ✅ | ✅ | `~/.codeium/windsurf/mcp_config.json` |
| [Zed](#zed) | ✅ | ✅ | ✅ | `settings.json` |
| [Continue](#continue) | ✅ | ✅ | ✅ | `~/.continue/config.yaml` |
| [Cline](#cline) | ✅ | ✅ | ✅ | `cline_mcp_settings.json` (via UI) |
| [Codex CLI](#codex-cli) | ✅ | ✅ | ⚠️ | `~/.codex/config.toml` |
| [Claude Desktop](#claude-desktop) | ✅ | ✅ | — | `claude_desktop_config.json` |
| [Cherry Studio](#cherry-studio) | ✅ | ✅ | ✅ | UI / JSON import |
| [ChatGPT](#chatgpt--gpt-actions) | ✅ | ❌ | 🌐 | Web UI (remote HTTPS only) |
| [GPT Actions](#chatgpt--gpt-actions) | ❌ OpenAPI | — | — | GPT builder UI |
| [OpenClaw](#openclaw) | ⚠️ unconfirmed | ❓ | ❓ | `~/.openclaw/openclaw.json` |
| [Any spec-conformant client](#custom-clients) | ✅ | ✅ | ✅ | client-specific |

⚠️ = works but flagged (see the client's section). 🌐 = remote HTTPS only, needs a public tunnel.

The most common shape — used by Claude Code, Cursor, Windsurf, Cline, Cherry Studio, and Claude Desktop — is a single `mcpServers` object:

```json
{
  "mcpServers": {
    "android-agent": {
      "command": "android-agent-mcp"
    }
  }
}
```

The sections below note where a client deviates from that (Zed, Codex, and Continue each use a different shape).

## Claude Code

Native MCP support over stdio and streamable HTTP. Easiest path — one command:

```bash
# stdio (recommended)
claude mcp add --transport stdio android-agent --scope project -- android-agent-mcp

# or HTTP
claude mcp add --transport http android-agent http://localhost:8002/mcp
```

`--scope project` writes a shareable `.mcp.json` at your repo root; the default `local` scope writes to `~/.claude.json`. Everything after `--` is the server command.

Docs: [code.claude.com/docs/en/mcp](https://code.claude.com/docs/en/mcp)

## Cursor

stdio, SSE, and streamable HTTP. Add `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global — project wins on conflict):

```json
{ "mcpServers": { "android-agent": { "command": "android-agent-mcp" } } }
```

For HTTP, use a `"url": "http://localhost:8002/mcp"` entry instead of `command`. Manage it under **Settings → MCP / Tools**.

Docs: [cursor.com/docs/mcp](https://cursor.com/docs/mcp)

## Windsurf

stdio, streamable HTTP, and SSE. Edit `~/.codeium/windsurf/mcp_config.json` (or **Cascade panel → MCPs → Configure**), then restart:

```json
{ "mcpServers": { "android-agent": { "command": "android-agent-mcp" } } }
```

⚠️ **Copy-paste trap:** for a remote/HTTP server Windsurf uses the key **`serverUrl`**, *not* `url`. Config supports `${env:VAR}` and `${file:/path}` interpolation.

Docs: [docs.windsurf.com/windsurf/cascade/mcp](https://docs.windsurf.com/windsurf/cascade/mcp) (now served from docs.devin.ai after the Cognition acquisition)

## Zed

stdio and remote URL. Open settings (`zed: open settings`) and add under **`context_servers`** — Zed does **not** use the `mcpServers` key:

```json
{
  "context_servers": {
    "android-agent": {
      "command": "android-agent-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

Zed restarts the server automatically on save. If your build rejects the entry, add `"source": "custom"` as the first field (present on some builds, absent from the current docs).

Docs: [zed.dev/docs/ai/mcp](https://zed.dev/docs/ai/mcp)

## Continue

stdio, SSE, and streamable HTTP. Continue uses **YAML**, and `mcpServers` is a **list** whose entries carry a `name`:

```yaml
name: Ghost Config
version: 0.0.1
schema: v1
mcpServers:
  - name: Android Agent
    type: stdio          # optional — stdio is the default
    command: android-agent-mcp
```

Global config lives at `~/.continue/config.yaml`; per-workspace files go in `.continue/mcpServers/*.yaml`. For HTTP, use `type: streamable-http` + `url: http://localhost:8002/mcp`.

Docs: [docs.continue.dev/customize/deep-dives/mcp](https://docs.continue.dev/customize/deep-dives/mcp)

## Cline

stdio, streamable HTTP (recommended for remote), and legacy SSE. Open the **MCP Servers panel → Configure → Configure MCP Servers** to edit `cline_mcp_settings.json` (stored in the extension's globalStorage — no fixed path):

```json
{
  "mcpServers": {
    "android-agent": {
      "command": "android-agent-mcp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

For HTTP, swap in `"type": "streamableHttp", "url": "http://localhost:8002/mcp"`.

Docs: [docs.cline.bot/mcp/mcp-overview](https://docs.cline.bot/mcp/mcp-overview)

## Codex CLI

stdio and streamable HTTP. Codex uses **TOML** at `~/.codex/config.toml`, one table per server:

```toml
[mcp_servers.android-agent]
command = "android-agent-mcp"
```

⚠️ Open issues report streamable-HTTP init bugs in Codex — **stdio is the reliable path today**. For HTTP, use `url = "http://localhost:8002/mcp"` in the table.

Docs: [developers.openai.com/codex/mcp](https://developers.openai.com/codex/mcp)

## Claude Desktop

The JSON config is **stdio-only** — connect Ghost via its stdio transport. (Remote HTTP servers go through Claude Desktop's Connectors / Extensions UI, not this file.) Open **Settings → Developer → Edit Config** and add:

```json
{ "mcpServers": { "android-agent": { "command": "android-agent-mcp" } } }
```

Config path: macOS `~/Library/Application Support/Claude/claude_desktop_config.json`, Windows `%APPDATA%\Claude\claude_desktop_config.json`. Restart Claude Desktop after editing.

Docs: [modelcontextprotocol.io/quickstart/user](https://modelcontextprotocol.io/quickstart/user)

## Cherry Studio

stdio, SSE, and streamable HTTP — both Ghost transports work directly, no tunnel. Add via **Settings → MCP Servers → Add Server** (form or *Import from JSON*):

```json
{ "mcpServers": { "android-agent": { "transport": "stdio", "command": "android-agent-mcp" } } }
```

Gotcha: a stdio MCP server must **never log to stdout** — it corrupts the JSON-RPC stream. Ghost logs to stderr, so it's fine.

Docs: [docs.cherry-ai.com/docs/en-us/advanced-basic/mcp/config](https://docs.cherry-ai.com/docs/en-us/advanced-basic/mcp/config)

## ChatGPT / GPT Actions

Two different, remote-only mechanisms — **neither can use Ghost's local stdio transport**, so you'll need to expose Ghost over public HTTPS (OpenAI's Secure MCP Tunnel, ngrok, or Cloudflare Tunnel).

- **ChatGPT (Developer Mode)** — ChatGPT supports custom **MCP** servers, but **remote HTTPS only** (SSE / streamable HTTP, no stdio). Enable **Settings → Apps & Connectors → Advanced → Developer Mode**, then add a connector pointing at your public `…/mcp` URL. See [developers.openai.com/apps-sdk](https://developers.openai.com/apps-sdk/deploy/connect-chatgpt).
- **GPT Actions** — **not MCP at all.** Actions are REST integrations described by an **OpenAPI** schema. To use Ghost here you'd put a public HTTPS OpenAPI wrapper in front of Ghost's REST layer (port 5055) and paste the schema into the GPT builder under **Configure → Actions**. See [developers.openai.com/api/docs/actions](https://developers.openai.com/api/docs/actions/introduction).

## OpenClaw

⚠️ **Client support unconfirmed.** OpenClaw officially runs *as* an MCP **server** (`openclaw mcp serve`) — the reverse of what you'd need. Whether it can act as an MCP **client** that connects out to Ghost is **not reliably documented** (the core feature request was closed "not planned"; a community add-on exists but isn't confirmed merged). We're leaving a concrete snippet out until it's verified against the source. If client support lands, config lives in `~/.openclaw/openclaw.json`.

Docs: [docs.openclaw.ai/cli/mcp](https://docs.openclaw.ai/cli/mcp)

## Custom clients

Ghost is a standard [Model Context Protocol](https://modelcontextprotocol.io/) server, so **any spec-conformant client** works. Point it at:

- **stdio** — spawn `android-agent-mcp`
- **HTTP** — connect to `http://localhost:8002/mcp`

Then call `tools/list` to discover all 41 tools. See the [testing snippet](../mcp-server/#testing) on the MCP Server page for a raw JSON-RPC handshake you can adapt.

## Copy-paste traps (read before you file a bug)

- **Windsurf** uses `serverUrl` for remote servers, not `url`.
- **Zed** uses `context_servers`, not `mcpServers`.
- **Continue** `mcpServers` is a YAML **list** with `name` keys, not an object.
- **Claude Desktop** JSON is **stdio-only**; remote servers go through its Connectors UI.
- **ChatGPT** cannot use stdio at all — it needs a public HTTPS `/mcp` endpoint.
- **GPT Actions** is OpenAPI, not MCP — different integration entirely.

## Related

- [MCP Server](../mcp-server/) — the 41 tools every client above can call
- [How Ghost Compares](../how-ghost-compares/) — where Ghost sits versus cloud alternatives
- [LLM Providers](../llm-providers/) — the models that reason over these tools
