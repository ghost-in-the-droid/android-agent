"""Creator routes: LLM chat, chat-stream (SSE), ollama-models."""

import json
import os
import subprocess

from fastapi import APIRouter, Body, HTTPException
from starlette.responses import StreamingResponse

router = APIRouter(prefix="/api/creator", tags=["creator"])


def _build_creator_system_prompt(data: dict) -> str:
    """Build system prompt with full device + skills context.

    Uses shared device_context functions for all screen understanding.
    """
    from gitd.services.device_context import (
        get_phone_state, get_screen_tree, get_screen_xml,
    )

    backend = data.get("backend", "openrouter")
    context = data.get("context", {})
    system = """You are a mobile automation agent that controls Android devices via ADB.
You help users create automation skills by proposing step-by-step plans and executing them.

## Your capabilities (via ADB):
- **tap(x, y)** -- tap at screen coordinates
- **long_press(x, y, duration_ms)** -- long press
- **swipe(x1, y1, x2, y2)** -- swipe gesture
- **type(text)** -- type text into focused input (ASCII). Use type_unicode for emoji/CJK.
- **back** -- press Android back button
- **home** -- press home button
- **launch(package)** -- open an app by package name
- **wait(seconds)** -- pause between actions
- **screenshot** -- capture current screen
- **get_screen_tree** -- LLM-readable UI hierarchy with element indices
- **get_elements** -- interactive elements as JSON with bounds + centers
- **ocr_screen** -- OCR all visible text (for canvas/image content)
- **ocr_region(x1,y1,x2,y2)** -- OCR a specific screen region
- **classify_screen** -- detect screen type (home, search, dialog, error, etc.)

## Rules:
- Do NOT create/write files. Only describe plans as JSON.
- Each step MUST have an "action" and "description" field.
- Use element_idx to reference screen elements when overlay is active.
"""

    device_serial = context.get("device", "")
    if device_serial:
        # Phone state
        try:
            state = get_phone_state(device_serial)
            if state:
                system += f"\n\n## Current app: {state.get('currentApp', '')} ({state.get('packageName', '')})"
                if state.get("keyboardVisible"):
                    system += " [KEYBOARD OPEN]"
        except Exception:
            pass

        # Screen tree (LLM-readable hierarchy)
        if backend == "claude-code":
            try:
                tree = get_screen_tree(device_serial)
                if tree and tree != "(empty screen)":
                    system += f"\n\n## Screen hierarchy:\n{tree}"
                    # Also save raw XML for Claude Code to Read if needed
                    state_dir = "/tmp/creator_state"
                    os.makedirs(state_dir, exist_ok=True)
                    xml = get_screen_xml(device_serial)
                    if xml:
                        with open(f"{state_dir}/screen.xml", "w") as f:
                            f.write(xml)
            except Exception:
                pass

    # Interactive elements from frontend (already parsed)
    if context.get("elements"):
        system += f"\n\n## Interactive elements ({len(context['elements'])} total):\n"
        for e in context["elements"][:40]:
            label = e.get("text") or e.get("content_desc") or e.get("resource_id") or ""
            bounds = e.get("bounds", {})
            system += f"  [{e.get('idx')}] {label} ({e.get('class', '')}) bounds=[{bounds.get('x1', 0)},{bounds.get('y1', 0)}][{bounds.get('x2', 0)},{bounds.get('y2', 0)}]\n"

    if context.get("plan"):
        plan = context["plan"]
        system += f"\n\n## Active Plan: {plan.get('name', 'unnamed')}"
        system += f"\n  Progress: step {plan.get('currentStep', 0) + 1} of {plan.get('totalSteps', '?')}"
        system += "\n  Steps:"
        for i, s in enumerate(plan.get("steps", [])):
            status = s.get("_status", "pending")
            icon = "[OK]" if status == "completed" else ("[FAIL]" if status == "current" else "[ ]")
            system += f"\n    {icon} Step {i + 1}: [{s.get('action', '')}] {s.get('goal', s.get('description', ''))}"

    if context.get("error_context"):
        system += f"\n\n## STEP FAILED -- Error context:\n{context['error_context']}\n"

    if context.get("action_history"):
        system += "\n\n## Recent actions:\n"
        for a in context["action_history"][-15:]:
            system += f"  - {a}\n"

    system += "\n\nWhen the user asks to automate something, propose the skill spec as JSON."
    return system


@router.post("/chat", summary="Skill Creator LLM Chat")
def api_creator_chat(data: dict = Body({})):
    """LLM chat endpoint for Skill Creator."""
    backend = data.get("backend", "openrouter")
    model = data.get("model", "")
    message = data.get("message", "")
    context = data.get("context", {})

    if not message:
        raise HTTPException(status_code=400, detail="message required")

    system = _build_creator_system_prompt(data)

    try:
        if backend == "ollama":
            import requests as _req

            base = data.get("base_url", "http://localhost:11434")
            r = _req.post(
                f"{base}/api/chat",
                json={
                    "model": model or "llama3",
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": message}],
                    "stream": False,
                },
                timeout=60,
            )
            resp = r.json()
            reply = resp.get("message", {}).get("content", "")

        elif backend == "claude":
            import anthropic

            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
            screenshot_b64 = context.get("screenshot_b64")
            user_content = [{"type": "text", "text": message}]
            if screenshot_b64:
                user_content.append(
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": screenshot_b64}}
                )
            resp = client.messages.create(
                model=model or "claude-sonnet-4-20250514",
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            )
            reply = resp.content[0].text

        elif backend == "claude-code":
            state_dir = "/tmp/creator_state"
            os.makedirs(state_dir, exist_ok=True)
            sandbox_rules = f"\n\n## SANDBOX RULES:\n1. Workspace: {state_dir}/ -- ONLY write files there\n2. May READ any project file\n3. FORBIDDEN: writing outside {state_dir}/\n4. PRIMARY output: JSON skill spec"
            full_prompt = f"{system}\n{sandbox_rules}\n\n---\nUser: {message}"
            proc = subprocess.run(
                [
                    "claude",
                    "--print",
                    "--model",
                    model or "sonnet",
                    "--allowedTools",
                    "Read,Grep,Glob,Bash(cat:*),Bash(head:*),Bash(tail:*),Bash(ls:*),Bash(wc:*)",
                    "--dangerously-skip-permissions",
                ],
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=state_dir,
                env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
            )
            reply = proc.stdout.strip()
            if not reply and proc.stderr:
                reply = f"Error: {proc.stderr.strip()}"

        else:  # openrouter
            from openai import OpenAI

            client = OpenAI(
                api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                base_url="https://openrouter.ai/api/v1",
            )
            user_content = message
            screenshot_b64 = context.get("screenshot_b64")
            if screenshot_b64:
                user_content = [
                    {"type": "text", "text": message},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{screenshot_b64}"}},
                ]
            resp = client.chat.completions.create(
                model=model or "anthropic/claude-sonnet-4",
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user_content}],
                max_tokens=2048,
            )
            reply = resp.choices[0].message.content

        return {"reply": reply, "backend": backend, "model": model}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat-stream", summary="Skill Creator Streaming Chat")
def api_creator_chat_stream(data: dict = Body({})):
    """Streaming LLM chat -- returns SSE with tokens as they arrive."""
    backend = data.get("backend", "openrouter")
    model = data.get("model", "")
    message = data.get("message", "")

    if not message:
        raise HTTPException(status_code=400, detail="message required")

    system = _build_creator_system_prompt(data)

    def generate():
        try:
            if backend == "claude-code":
                state_dir = "/tmp/creator_state"
                os.makedirs(state_dir, exist_ok=True)
                sandbox_rules = f"\n\n## SANDBOX RULES:\n1. Workspace: {state_dir}/ -- ONLY write there\n2. May READ any project file"
                full_prompt = f"{system}\n{sandbox_rules}\n\n---\nUser: {message}"
                proc = subprocess.Popen(
                    [
                        "claude",
                        "--print",
                        "--model",
                        model or "sonnet",
                        "--output-format",
                        "stream-json",
                        "--verbose",
                        "--allowedTools",
                        "Read,Grep,Glob,Bash(cat:*),Bash(head:*),Bash(tail:*),Bash(ls:*),Bash(wc:*)",
                        "--dangerously-skip-permissions",
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                    cwd=state_dir,
                    env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
                )
                proc.stdin.write(full_prompt)
                proc.stdin.close()
                full = ""
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        if chunk.get("type") == "assistant":
                            for c in chunk.get("message", {}).get("content", []):
                                if c.get("type") == "text" and c.get("text"):
                                    full += c["text"]
                                    yield f"data: {json.dumps({'token': c['text']})}\n\n"
                        elif chunk.get("type") == "result":
                            result = chunk.get("result", "")
                            if result and not full:
                                full = result
                            yield f"data: {json.dumps({'done': True, 'full': full or result})}\n\n"
                    except json.JSONDecodeError:
                        continue
                proc.wait()
                if full:
                    yield f"data: {json.dumps({'done': True, 'full': full})}\n\n"

            elif backend == "openrouter":
                from openai import OpenAI

                client = OpenAI(
                    api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                    base_url="https://openrouter.ai/api/v1",
                )
                stream = client.chat.completions.create(
                    model=model or "anthropic/claude-sonnet-4",
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": message}],
                    max_tokens=2048,
                    stream=True,
                )
                full = ""
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        full += token
                        yield f"data: {json.dumps({'token': token})}\n\n"
                yield f"data: {json.dumps({'done': True, 'full': full})}\n\n"

            elif backend == "ollama":
                import requests as _req

                base = data.get("base_url", "http://localhost:11434")
                r = _req.post(
                    f"{base}/api/chat",
                    json={
                        "model": model or "llama3",
                        "messages": [{"role": "user", "content": message}],
                        "stream": True,
                    },
                    timeout=60,
                    stream=True,
                )
                full = ""
                for line in r.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full += token
                            yield f"data: {json.dumps({'token': token})}\n\n"
                        if chunk.get("done"):
                            yield f"data: {json.dumps({'done': True, 'full': full})}\n\n"

            elif backend == "claude":
                import anthropic

                client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
                full = ""
                with client.messages.stream(
                    model=model or "claude-sonnet-4-20250514",
                    max_tokens=2048,
                    messages=[{"role": "user", "content": message}],
                ) as stream:
                    for text_chunk in stream.text_stream:
                        full += text_chunk
                        yield f"data: {json.dumps({'token': text_chunk})}\n\n"
                yield f"data: {json.dumps({'done': True, 'full': full})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/ollama-models", summary="List Available Ollama Models")
def api_ollama_models():
    """List available Ollama models."""
    try:
        import requests as _req

        r = _req.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        return {"models": models}
    except Exception:
        return {"models": [], "error": "Ollama not available"}
