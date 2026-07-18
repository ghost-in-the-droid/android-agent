# Claude Code → Your Phone — commands from this demo
# https://ghostinthedroid.com/features/mcp-server/

claude --print --output-format=stream-json --verbose --include-partial-messages --permission-mode bypassPermissions "Check in the reddit app what's on r/LocalLLaMA. Use the ASUS phone." < /dev/null 2>&1 | python3 scripts/showcase/claude_streamer.py
