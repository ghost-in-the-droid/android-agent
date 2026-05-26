# Ghost in the Droid — Agent Tool Rules

## MCP Tool: open_camera

For ANY task involving taking a photo, selfie, video, or opening the camera:

1. Load the tool: `ToolSearch({"query": "select:mcp__android-agent__open_camera"})`
2. Call it: `mcp__android-agent__open_camera(device=<serial>, mode=<mode>, timer_s=<seconds>)`

**modes:** `photo` (rear photo), `video` (rear video), `selfie` (front photo), `selfie_video` (front video)  
**timer_s:** `0` (off), `2`, `3`, `5`, `10`

This single call opens the correct camera mode AND sets the timer. Do NOT:
- use `launch_app` for camera tasks
- check `list_skills` for a camera skill
- tap camera UI manually to switch modes or set timers

## MCP Tool: speak_text

To make the phone speak text aloud:

1. `ToolSearch({"query": "select:mcp__android-agent__speak_text"})`
2. `mcp__android-agent__speak_text(device=<serial>, text="...", rate=1.0)`

Works from PC and on-device — always emits audio from the phone.

## MCP Tools: lead lookup (marketing agent)

**Do not ask another agent / the user for lead info — query the DB directly.**

To look up everything about an influencer (followers, niche, our outreach
history, their reply, conversation state):

1. `ToolSearch({"query": "select:mcp__android-agent__lookup_lead"})`
2. `mcp__android-agent__lookup_lead(handle="bajapawsllc")` — with or without `@`

To get the daily priority list (all influencers with unread replies):

1. `ToolSearch({"query": "select:mcp__android-agent__list_unread_leads"})`
2. `mcp__android-agent__list_unread_leads()` — no args

Output is plain text formatted for the LLM to read directly. Includes profile
URL, follower counts, engagement ratio, source hashtag, outreach status,
strategy used, and the latest message exchanged.

## Reply detection cadence

The phone's TikTok inbox is scanned automatically every hour at :30
(8:30–22:30) on the ASUS as `@<our-product>`. Data lives in:
- `inbox_snapshots` — one row per scan with rollup counts
- `inbox_replies`  — one row per conversation, updated each scan

Use `list_unread_leads` to query that data through MCP instead of writing SQL.

## General rule

All `mcp__android-agent__*` tools are already loaded by the MCP server. To use any of them:
`ToolSearch({"query": "select:mcp__android-agent__<tool_name>"})` then call it directly.
