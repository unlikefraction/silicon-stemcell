import subprocess
import os
import json
import re
import uuid

from prompts.DNA import get_manager_prompt

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(PROJECT_ROOT, "sessions")


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
    with open(prompt_file, "w") as f:
        f.write(prompt)
    return prompt_file


def claude_code(text, carbon_id):
    """Invoke the Manager via claude CLI for a specific carbon. Returns the raw text output."""
    session_id = _get_session_id(carbon_id)
    system_prompt = get_manager_prompt(carbon_id)
    prompt_file = _write_prompt_file(carbon_id, system_prompt)

    # Try resuming existing session first
    cmd = [
        "claude", "-p",
        "--resume", session_id,
        "--system-prompt-file", prompt_file,
        "--dangerously-skip-permissions",
    ]

    try:
        result = subprocess.run(
            cmd,
            input=text,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, Exception):
        pass

    # Fall back to starting with session-id (new session with that ID)
    cmd_fallback = [
        "claude", "-p",
        "--session-id", session_id,
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
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return '{"tools": [{"tool": "reply", "message": "Manager timed out. Please try again."}, {"tool": "do_nothing"}]}'
    except Exception as e:
        return f'{{"tools": [{{"tool": "reply", "message": "Manager error: {e}"}}, {{"tool": "do_nothing"}}]}}'


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
