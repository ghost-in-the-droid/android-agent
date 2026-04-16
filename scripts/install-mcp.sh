#!/usr/bin/env bash
# Ghost in the Droid — MCP Server Installer
# Gives any AI agent 35 Android automation tools.
#
# Usage:
#   bash <(curl -sSL https://raw.githubusercontent.com/ghost-in-the-droid/android-agent/main/scripts/install-mcp.sh)
#
# What it does:
#   1. Clones the repo (or updates if already cloned)
#   2. Creates a Python venv and installs dependencies
#   3. Registers the MCP server with your AI client
#
set -euo pipefail

REPO="https://github.com/ghost-in-the-droid/android-agent.git"
DIR="$HOME/ghost-in-the-droid"

echo "👻 Ghost in the Droid — MCP Installer"
echo ""

# ── Prerequisites ──────────────────────────────────────────────────────────

check() { command -v "$1" &>/dev/null; }

if ! check python3; then echo "❌ python3 not found. Install Python 3.10+."; exit 1; fi
if ! check adb; then echo "⚠️  adb not found. Install Android platform-tools for device control."; fi
if ! check git; then echo "❌ git not found."; exit 1; fi

# ── Clone / Update ─────────────────────────────────────────────────────────

if [ -d "$DIR" ]; then
    echo "📂 Found $DIR — pulling latest..."
    cd "$DIR" && git pull --quiet
else
    echo "📥 Cloning to $DIR..."
    git clone --quiet "$REPO" "$DIR"
    cd "$DIR"
fi

# ── Python Venv + Install ──────────────────────────────────────────────────

if [ ! -d ".venv" ]; then
    echo "🐍 Creating Python venv..."
    python3 -m venv .venv
fi

echo "📦 Installing dependencies..."
.venv/bin/pip install -q -e ".[all]"

# Verify MCP server loads
TOOL_COUNT=$(.venv/bin/python -c "from gitd.mcp_server import mcp; print(len(mcp._tool_manager.list_tools()))" 2>/dev/null || echo "0")
if [ "$TOOL_COUNT" = "0" ]; then
    echo "❌ MCP server failed to load. Check Python 3.10+ and try again."
    exit 1
fi

echo "✅ MCP server ready — $TOOL_COUNT tools"

# ── Register with AI Client ────────────────────────────────────────────────

MCP_CMD="$DIR/.venv/bin/python"
MCP_ARGS="-m gitd.mcp_server"

if check claude; then
    echo ""
    echo "🔌 Registering with Claude Code..."
    claude mcp add android-agent -- "$MCP_CMD" $MCP_ARGS 2>/dev/null && \
        echo "✅ Claude Code: android-agent MCP registered" || \
        echo "⚠️  claude mcp add failed — add manually (see below)"
fi

# ── Done ───────────────────────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "👻 Ghost in the Droid — $TOOL_COUNT MCP tools installed"
echo ""
echo "If auto-registration didn't work, add manually:"
echo ""
echo "  Claude Code:"
echo "    claude mcp add android-agent -- $MCP_CMD $MCP_ARGS"
echo ""
echo "  Claude Desktop / Cursor / Windsurf — add to config:"
echo "    {\"mcpServers\":{\"android-agent\":{\"command\":\"$MCP_CMD\",\"args\":[\"-m\",\"gitd.mcp_server\"]}}}"
echo ""
echo "  VS Code Copilot (.vscode/mcp.json):"
echo "    {\"servers\":{\"android-agent\":{\"command\":\"$MCP_CMD\",\"args\":[\"-m\",\"gitd.mcp_server\"]}}}"
echo ""
echo "Start the dashboard:  cd $DIR && .venv/bin/python run.py"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
