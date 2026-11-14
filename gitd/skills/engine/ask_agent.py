"""Pluggable bounded single-answer Ghost Claude Code provider hook."""
import json
import shutil
from .ask import NO_ANSWER


class AskAgent:
    def answer(self, prompt, attachments, schema, device_serial, *, timeout_s=0, max_turns=3):
        if not shutil.which('claude'):
            return NO_ANSWER
        from gitd.services.agent_chat_claude_code import answer_claude_code
        bounded = ('Return exactly one JSON value matching the schema. Do not use tools.\n' +
                   json.dumps({'prompt': prompt, 'schema': schema, 'attachments': attachments}))
        try:
            return answer_claude_code(bounded, timeout_s=timeout_s, max_turns=min(max_turns, 3))
        except (RuntimeError, ValueError, OSError, __import__('subprocess').TimeoutExpired):
            return NO_ANSWER


ask_agent = AskAgent()
