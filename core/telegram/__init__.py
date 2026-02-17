import os
import json
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests
from core.telegram.config import BOT_TOKEN, API_BASE, CONTACTS_FILE

VALID_TRUST_LEVELS = ["very_low", "low", "ok", "high", "very_high", "ultimate"]


def _load_contacts():
    if os.path.exists(CONTACTS_FILE):
        with open(CONTACTS_FILE) as f:
            return json.load(f)
    return {"last_update_id": 0, "contacts": {}}


def _save_contacts(data):
    with open(CONTACTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _get_carbon_id_by_telegram_userid(contacts_data, telegram_userid):
    """Reverse lookup: telegram user ID -> carbon_id."""
    for carbon_id, info in contacts_data.get("contacts", {}).items():
        if info.get("telegram_userid") == telegram_userid:
            return carbon_id
    return None


def _create_new_contact(contacts_data, telegram_userid, first_name):
    """Create a new contact entry for an unknown user.
    If no contacts exist yet, the first user becomes central carbon with ultimate trust."""
    carbon_id = str(telegram_userid)
    is_first_user = len(contacts_data.get("contacts", {})) == 0

    contacts_data["contacts"][carbon_id] = {
        "name": first_name or "",
        "carbon_id": carbon_id,
        "telegram_userid": telegram_userid,
        "trust_level": "ultimate" if is_first_user else "very_low",
        "is_central_carbon": is_first_user,
        "relation": "",
        "description": "",
        "timezone": "",
    }
    _save_contacts(contacts_data)
    return carbon_id, is_first_user


def get_unread_messages():
    """Check for new messages from all users via Telegram.
    Returns dict: {carbon_id: context_string} or empty dict."""
    contacts_data = _load_contacts()
    params = {"timeout": 0}
    if contacts_data["last_update_id"]:
        params["offset"] = contacts_data["last_update_id"] + 1

    retries = 3
    for attempt in range(retries):
        try:
            resp = requests.get(f"{API_BASE}/getUpdates", params=params, timeout=20)
            data = resp.json()
            break
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            return {}

    if not data.get("ok") or not data.get("result"):
        return {}

    # Group messages by carbon_id
    messages_by_carbon = {}  # carbon_id -> {"messages": [...], "is_new": bool}
    new_users = set()

    for update in data["result"]:
        contacts_data["last_update_id"] = update["update_id"]

        msg = update.get("message") or update.get("edited_message")
        if not msg:
            continue

        user_id = msg.get("from", {}).get("id")
        text = msg.get("text", "")
        first_name = msg.get("from", {}).get("first_name", "")

        if not user_id:
            continue

        # Look up or create contact
        carbon_id = _get_carbon_id_by_telegram_userid(contacts_data, user_id)
        is_new = False
        if carbon_id is None:
            carbon_id, is_first_user = _create_new_contact(contacts_data, user_id, first_name)
            is_new = True
            new_users.add(carbon_id)
            if is_first_user:
                _send_single_message(user_id, f"Hello {first_name}! I'm Silicon. You're my first Carbon -- that makes you the central one. Give me a moment to get ready...")
            else:
                _send_single_message(user_id, f"Hello {first_name}! I'm Silicon. Give me a moment...")

        if carbon_id not in messages_by_carbon:
            messages_by_carbon[carbon_id] = {"messages": [], "is_new": carbon_id in new_users}

        # Format timestamp using carbon's timezone from contacts
        msg_date = msg.get("date")
        timestamp = ""
        if msg_date:
            dt = datetime.fromtimestamp(msg_date, tz=timezone.utc)
            contact_tz = contacts_data.get("contacts", {}).get(carbon_id, {}).get("timezone", "")
            if contact_tz:
                try:
                    local_dt = dt.astimezone(ZoneInfo(contact_tz))
                    tz_name = local_dt.strftime("%Z")
                    timestamp = local_dt.strftime(f"[%b %d, %I:%M %p {tz_name}]")
                except Exception:
                    timestamp = dt.strftime("[%b %d, %I:%M %p UTC]")
            else:
                timestamp = dt.strftime("[%b %d, %I:%M %p UTC]")

        # Handle reply-to
        reply_to = msg.get("reply_to_message")
        formatted = ""
        if timestamp:
            formatted += f"{timestamp} "
        if reply_to:
            tagged_text = reply_to.get("text", "")
            if tagged_text:
                formatted += f"Tagged:\n> {tagged_text}\n\nReply:\n"

        if text.strip() == "/new":
            messages_by_carbon[carbon_id]["messages"].append("[COMMAND: NEW_SESSION]")
        elif text.strip() == "/start":
            messages_by_carbon[carbon_id]["messages"].append("[COMMAND: START]")
        elif text.strip():
            messages_by_carbon[carbon_id]["messages"].append(formatted + text)

    _save_contacts(contacts_data)

    # Format: {carbon_id: "context string"}
    result = {}
    for carbon_id, msg_data in messages_by_carbon.items():
        msgs = msg_data["messages"]
        if not msgs:
            continue

        contact = contacts_data["contacts"].get(carbon_id, {})
        name = contact.get("name") or carbon_id

        if msg_data["is_new"]:
            if contact.get("is_central_carbon"):
                prefix = f"FIRST USER (Central Carbon, ultimate trust) - First time message from {name} (telegram_userid: {contact.get('telegram_userid')}, carbon_id: {carbon_id}):"
            else:
                prefix = f"NEW USER - First time message from {name} (telegram_userid: {contact.get('telegram_userid')}, carbon_id: {carbon_id}):"
        else:
            prefix = f"Messages from {name} (carbon_id: {carbon_id}):"

        result[carbon_id] = prefix + "\n" + "\n---\n".join(msgs)

    return result


def reply_user(message, carbon_id, parse_mode=None):
    """Send a message to a specific carbon via Telegram."""
    contacts_data = _load_contacts()
    contact = contacts_data.get("contacts", {}).get(carbon_id)

    if not contact:
        return f"Error: carbon_id '{carbon_id}' not found in contacts"

    chat_id = contact.get("telegram_userid")
    if not chat_id:
        return f"Error: No telegram_userid for carbon_id '{carbon_id}'"

    MAX_LEN = 4096
    chunks = []
    if len(message) <= MAX_LEN:
        chunks = [message]
    else:
        current = ""
        for line in message.split("\n"):
            if len(current) + len(line) + 1 > MAX_LEN:
                if current:
                    chunks.append(current)
                current = line[:MAX_LEN]
            else:
                current = current + "\n" + line if current else line
        if current:
            chunks.append(current)

    for chunk in chunks:
        status = _send_single_message(chat_id, chunk, parse_mode)
        if "Error" in status:
            return status

    return "Message sent"


def _send_single_message(chat_id, text, parse_mode=None):
    """Send a single message chunk to Telegram."""
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        resp = requests.post(f"{API_BASE}/sendMessage", json=payload, timeout=10)
        result = resp.json()
        if result.get("ok"):
            return "Message sent"
        if parse_mode:
            payload.pop("parse_mode", None)
            resp = requests.post(f"{API_BASE}/sendMessage", json=payload, timeout=10)
            result = resp.json()
            if result.get("ok"):
                return "Message sent"
        return f"Error sending message: {result}"
    except Exception as e:
        return f"Error sending message: {e}"


def get_contacts():
    """Get all contacts data. Used by other modules."""
    return _load_contacts()


def get_contact(carbon_id):
    """Get a specific contact by carbon_id."""
    data = _load_contacts()
    return data.get("contacts", {}).get(carbon_id)
