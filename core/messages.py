import os
import json
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANAGER_MESSAGES_FILE = os.path.join(PROJECT_ROOT, "manager_messages.json")


def _load_manager_messages():
    if os.path.exists(MANAGER_MESSAGES_FILE):
        with open(MANAGER_MESSAGES_FILE) as f:
            return json.load(f)
    return {}


def _save_manager_messages(messages):
    with open(MANAGER_MESSAGES_FILE, "w") as f:
        json.dump(messages, f, indent=2)


def send_manager_message(from_carbon_id, to_carbon_id, message):
    """Queue a message from one manager to another. Delivered on next event loop tick."""
    messages = _load_manager_messages()
    if to_carbon_id not in messages:
        messages[to_carbon_id] = []
    messages[to_carbon_id].append({
        "from_carbon_id": from_carbon_id,
        "message": message,
        "timestamp": time.time(),
    })
    _save_manager_messages(messages)
    return "Done. Message queued for delivery to the other manager."


def check_manager_messages():
    """Check for pending inter-manager messages. Returns {carbon_id: context_string}."""
    messages = _load_manager_messages()
    if not messages:
        return {}

    result = {}
    for carbon_id, msgs in messages.items():
        if not msgs:
            continue
        parts = []
        for m in msgs:
            parts.append(f"Message from manager of {m['from_carbon_id']}:\n{m['message']}")
        result[carbon_id] = "Inter-manager messages:\n" + "\n---\n".join(parts)

    # Clear delivered messages
    _save_manager_messages({})
    return result
