import subprocess
import os
import json
import re
import time
import uuid
import platform
import shutil

from prompts.DNA import get_manager_prompt

IS_WINDOWS = platform.system() == "Windows"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(PROJECT_ROOT, "sessions")

# On Windows, find the full path to claude so we don't need shell=True
# (which has an 8191 char command line limit via cmd.exe)
CLAUDE_CMD = "claude"
if IS_WINDOWS:
    _claude_path = shutil.which("claude") or shutil.which("claude.cmd")
    if _claude_path:
        CLAUDE_CMD = _claude_path


def _get_session_id(carbon_id):
    """Get session UUID for a specific carbon."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    session_file = os.path.join(SESSIONS_DIR, f"{carbon_id}.txt")
    if os.path.exists(session_file):
        with open(session_file) as f:
            return f.read().strip()
    # Create a new session for this carbon
    return new_session(carbon_id)


def new_session(carbon_id):
    """Generate a new session UUID for a specific carbon."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    new_id = str(uuid.uuid4())
    session_file = os.path.join(SESSIONS_DIR, f"{carbon_id}.txt")
    with open(session_file, "w") as f:
        f.write(new_id)
    return new_id


def _write_prompt_file(carbon_id, prompt):
    """Write the system prompt to a file and return the path."""
    prompt_file = os.path.join(SESSIONS_DIR, f"{carbon_id}_prompt.md")
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    return prompt_file


def _is_rate_limit(text):
    """Check if text indicates an API rate limit."""
    lower = text.lower()
    return any(p in lower for p in [
        "rate limit", "rate_limit", "usage limit",
        "too many requests", "quota exceeded", "overloaded",
    ])


def _display_stream_event(event, tag):
    """Print a stream-json event to terminal."""
    t = event.get("type", "")

    if t == "system" and event.get("subtype") == "init":
        model = event.get("model", "")
        sid = event.get("session_id", "")[:8]
        print(f"  [{tag}] session {sid} | {model}", flush=True)

    elif t == "assistant":
        content = event.get("message", {}).get("content", [])
        for block in content:
            bt = block.get("type", "")
            if bt == "text":
                txt = block.get("text", "").strip()
                if txt:
                    preview = txt[:150].replace("\n", " ")
                    if len(txt) > 150:
                        preview += "…"
                    print(f"  [{tag}] {preview}", flush=True)
            elif bt == "tool_use":
                name = block.get("name", "?")
                print(f"  [{tag}] tool: {name}", flush=True)

    elif t == "result":
        cost = event.get("cost_usd")
        duration = event.get("duration_ms")
        subtype = event.get("subtype", "")
        parts = [f"  [{tag}] done"]
        if subtype and subtype != "success":
            parts[0] += f" ({subtype})"
        if cost is not None:
            parts.append(f"${cost:.4f}")
        if duration is not None:
            parts.append(f"{duration / 1000:.1f}s")
        print(" ".join(parts), flush=True)


def _run_streaming(cmd, input_text, tag, timeout=120, on_tools=None):
    """Run claude CLI with stream-json, show events on terminal.
    on_tools(tools_list) is called for tool JSON found in intermediate assistant texts.
    Returns (result_text, rate_limit_msg_or_None, returncode, executed_tools)."""
    print(f"  [{tag}] launching: {' '.join(cmd[:6])}...", flush=True)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=PROJECT_ROOT,
    )

    if input_text:
        try:
            proc.stdin.write(input_text)
        except BrokenPipeError:
            print(f"  [{tag}] stdin broken pipe", flush=True)
    proc.stdin.close()

    result_text = ""
    rate_limit_msg = None
    all_texts = []  # fallback if no result event
    raw_lines = []  # collect all raw output for debugging
    executed_tools = []  # tool specs already executed mid-stream
    deadline = time.time() + timeout

    while True:
        if time.time() > deadline:
            proc.kill()
            proc.wait()
            raise subprocess.TimeoutExpired(cmd, timeout)

        line = proc.stdout.readline()
        if not line:
            break

        raw_lines.append(line.rstrip())
        line = line.strip()
        if not line:
            continue

        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            # Not JSON — could be plain text output
            print(f"  [{tag}] (raw) {line[:200]}", flush=True)
            all_texts.append(line)
            if _is_rate_limit(line):
                rate_limit_msg = line
            continue

        _display_stream_event(event, tag)

        etype = event.get("type", "")

        if etype == "result":
            result_text = event.get("result", "")
            # Also check error field for messages like "No conversation found"
            error_text = event.get("error", "")
            if error_text and not result_text:
                result_text = error_text
            if not result_text:
                # Dump the full event so we can see what's in it
                print(f"  [{tag}] result event: {json.dumps(event)[:300]}", flush=True)
            if result_text and _is_rate_limit(result_text):
                rate_limit_msg = result_text

        elif etype == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    txt = block.get("text", "").strip()
                    if txt:
                        all_texts.append(txt)
                        if _is_rate_limit(txt):
                            rate_limit_msg = txt

                        # Try to parse as tool JSON and execute mid-stream
                        if on_tools:
                            tools_data = parse_manager_output(txt)
                            if tools_data and "tools" in tools_data:
                                tools_list = tools_data["tools"]
                                on_tools(tools_list)
                                executed_tools.extend(tools_list)

    stderr = proc.stderr.read()
    rc = proc.wait()

    if stderr:
        print(f"  [{tag}] stderr: {stderr.strip()[:300]}", flush=True)
        if _is_rate_limit(stderr):
            if not rate_limit_msg:
                rate_limit_msg = stderr.strip()

    if not result_text and not all_texts:
        print(f"  [{tag}] empty output (rc={rc}, {len(raw_lines)} lines)", flush=True)

    # If no result event, fall back to last assistant text
    if not result_text and all_texts:
        result_text = all_texts[-1]

    return result_text, rate_limit_msg, rc, executed_tools, stderr.strip() if stderr else ""


def claude_code(text, carbon_id, on_tools=None):
    """Invoke the Manager via claude CLI with streaming JSON.
    on_tools(tools_list) is called for mid-stream tool JSON in assistant texts.
    Returns (raw_text_output, rate_limit_message_or_None, executed_tools)."""
    session_id = _get_session_id(carbon_id)
    system_prompt = get_manager_prompt(carbon_id)
    prompt_file = _write_prompt_file(carbon_id, system_prompt)
    tag = f"manager:{carbon_id}"

    # Stream with --resume
    cmd = [
        CLAUDE_CMD, "-p",
        "--resume", session_id,
        "--system-prompt-file", prompt_file,
        "--dangerously-skip-permissions",
        "--output-format=stream-json",
        "--verbose",
    ]

    try:
        result_text, rate_limit, rc, executed_tools, stderr_text = _run_streaming(cmd, text, tag, on_tools=on_tools)
        if rc == 0 and result_text.strip():
            return result_text.strip(), rate_limit, executed_tools
        # Session not found — check stderr or result for the specific message
        check_text = f"{stderr_text} {result_text}".lower()
        if rc != 0 and "no" in check_text and "found" in check_text and session_id.lower() in check_text:
            print(f"  [{tag}] session {session_id} not found, starting fresh...", flush=True)
            new_session(carbon_id)
            notify_msg = "Manager session not found – send a message to start a new one."
            return f'{{"tools": [{{"tool": "reply", "message": "{notify_msg}"}}, {{"tool": "do_nothing"}}]}}', None, []
    except subprocess.TimeoutExpired:
        return '{"tools": [{"tool": "reply", "message": "Manager timed out. Please try again."}, {"tool": "do_nothing"}]}', None, []
    except Exception:
        pass

    # Fallback: plain text mode with current session
    print(f"  [{tag}] retrying without stream-json...", flush=True)
    session_id = _get_session_id(carbon_id)  # re-read in case new_session was called above
    cmd_fallback = [
        CLAUDE_CMD, "-p",
        "--resume", session_id,
        "--system-prompt-file", prompt_file,
        "--dangerously-skip-permissions",
    ]

    try:
        result = subprocess.run(
            cmd_fallback,
            input=text,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
        )
        output = result.stdout.strip()
        rl = output if (output and _is_rate_limit(output)) else None
        return output, rl, []
    except subprocess.TimeoutExpired:
        return '{"tools": [{"tool": "reply", "message": "Manager timed out. Please try again."}, {"tool": "do_nothing"}]}', None, []
    except Exception as e:
        return f'{{"tools": [{{"tool": "reply", "message": "Manager error: {e}"}}, {{"tool": "do_nothing"}}]}}', None, []


def parse_manager_output(output):
    """Extract the tools JSON from manager's text output.
    The manager outputs a JSON block like: {"tools": [...]}
    This may be surrounded by other text or markdown code blocks."""

    print(f"[DEBUG] Raw manager output:\n{output}\n", flush=True)

    if not output:
        return None

    # Strip markdown code blocks if present (```json ... ``` or ``` ... ```)
    cleaned = re.sub(r'```(?:json)?\s*', '', output)
    cleaned = re.sub(r'```', '', cleaned)

    # Try to find a JSON object with "tools" key
    # Look for the outermost { ... } that contains "tools"
    for text in [cleaned, output]:
        brace_depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == '{':
                if brace_depth == 0:
                    start = i
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
                if brace_depth == 0 and start != -1:
                    candidate = text[start:i+1]
                    try:
                        parsed = json.loads(candidate)
                        if "tools" in parsed:
                            return parsed
                    except (json.JSONDecodeError, ValueError):
                        pass
                    start = -1

    # Fallback: try the whole output as JSON
    for text in [cleaned, output]:
        try:
            parsed = json.loads(text.strip())
            if "tools" in parsed:
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    return None
