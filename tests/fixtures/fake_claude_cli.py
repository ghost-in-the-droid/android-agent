#!/usr/bin/env python3
"""Stand-in for ``claude -p --output-format stream-json``: reads the prompt on stdin, writes a canned
transcript. Env: FAKE_CLAUDE_PROMPT_LOG (append the prompt + argv), FAKE_CLAUDE_RATE_LIMIT=1 (emit a
rate-limit error result), FAKE_CLAUDE_MODEL (model name in the assistant message).
"""

import json
import os
import sys

prompt = sys.stdin.read()
log = os.environ.get("FAKE_CLAUDE_PROMPT_LOG")
if log:
    with open(log, "a") as fh:
        fh.write(json.dumps({"argv": sys.argv[1:], "prompt": prompt, "home": os.path.expanduser("~")}) + "\n")
model = os.environ.get("FAKE_CLAUDE_MODEL", "claude-haiku-4-5-20251001")
print(json.dumps({"type": "system", "subtype": "init", "model": model, "cwd": os.path.expanduser("~") + "/work"}))
print(
    json.dumps(
        {
            "type": "assistant",
            "message": {
                "model": model,
                "content": [
                    {"type": "text", "text": "Looking at the screen."},
                    {"type": "tool_use", "name": "mcp__ghost__screenshot", "input": {}},
                    {"type": "tool_use", "name": "mcp__ghost__tap", "input": {"x": 1, "y": 2}},
                ],
            },
        }
    )
)
print(
    json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok someone@example.com"}]}})
)
if os.environ.get("FAKE_CLAUDE_RATE_LIMIT") == "1":
    print(
        json.dumps(
            {
                "type": "result",
                "subtype": "error_during_execution",
                "is_error": True,
                "num_turns": 1,
                "result": "Rate limit reached for this account.",
                "usage": {"input_tokens": 5, "output_tokens": 1},
            }
        )
    )
    sys.exit(1)
print(
    json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "num_turns": 2,
            "duration_ms": 1234,
            "result": "DONE",
            "usage": {
                "input_tokens": 10,
                "cache_creation_input_tokens": 100,
                "cache_read_input_tokens": 50,
                "output_tokens": 20,
            },
        }
    )
)
