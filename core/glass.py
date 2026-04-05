import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import requests

CONFIG_FILE = ".glass.json"
IGNORE_NAMES = {".git", "__pycache__", ".DS_Store", CONFIG_FILE}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTACTS_FILE = PROJECT_ROOT / "core" / "telegram" / "contacts.json"
STATE_FILE = PROJECT_ROOT / "core" / "glass_state.json"


def _find_glass_config(start=None):
    start = Path(start or PROJECT_ROOT).resolve()
    for candidate in [start, *start.parents]:
        path = candidate / CONFIG_FILE
        if path.exists():
            return path
    return None


def load_glass_config(start=None):
    path = _find_glass_config(start)
    if path is None:
        raise FileNotFoundError("No .glass.json found in this folder or its parents.")
    return json.loads(path.read_text()), path


def _load_contacts():
    if CONTACTS_FILE.exists():
        return json.loads(CONTACTS_FILE.read_text())
    return {"last_update_id": 0, "contacts": {}}


def _save_contacts(data):
    CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTACTS_FILE.write_text(json.dumps(data, indent=2))


def _load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"threads": {}}


def _save_state(data):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2))


def _get_contact_by_silicon_id(contacts_data, silicon_id):
    for carbon_id, info in contacts_data.get("contacts", {}).items():
        if info.get("contact_type") == "silicon" and info.get("silicon_id") == silicon_id:
            return carbon_id, info
    return None, None


def _ensure_silicon_contact(silicon_id):
    contacts_data = _load_contacts()
    carbon_id, info = _get_contact_by_silicon_id(contacts_data, silicon_id)
    if carbon_id is not None:
        return contacts_data, carbon_id, info, False

    carbon_id = silicon_id
    if carbon_id in contacts_data.get("contacts", {}):
        raise ValueError(f"Contact id '{carbon_id}' already exists and is not a silicon contact.")
    info = {
        "name": silicon_id,
        "contact_type": "silicon",
        "silicon_id": silicon_id,
        "trust_level": "very_low",
        "is_central_carbon": False,
        "relation": "",
        "description": "",
        "timezone": "",
    }
    contacts_data.setdefault("contacts", {})[carbon_id] = info
    _save_contacts(contacts_data)
    return contacts_data, carbon_id, info, True


def _message_preview(message):
    body = (message.get("body") or "").strip()
    kind = message.get("kind") or "text"
    attachment_name = message.get("attachment_name") or ""

    if kind == "text":
        return body

    label = kind.capitalize()
    if attachment_name:
        preview = f"[{label} received: {attachment_name}]"
    else:
        preview = f"[{label} received]"
    if body:
        preview += f"\n{body}"
    return preview


def _timestamp_label(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("[%b %d, %I:%M %p UTC]")


def _iter_files(folder):
    for path in sorted(folder.rglob("*")):
        if path.is_dir():
            continue
        if any(part in IGNORE_NAMES for part in path.parts):
            continue
        yield path


def _tree_hash(folder):
    import hashlib

    digest = hashlib.sha256()
    for path in _iter_files(folder):
        rel = path.relative_to(folder).as_posix().encode()
        digest.update(rel)
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _build_archive(folder):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path in _iter_files(folder):
            tar.add(path, arcname=path.relative_to(folder).as_posix())
    buffer.seek(0)
    return buffer


def push_current_folder_now(start=None):
    config, config_path = load_glass_config(start)
    folder = config_path.parent
    tree_hash = _tree_hash(folder)
    if tree_hash == config.get("last_tree_hash"):
        return {"created": False, "status": "No code changes."}

    archive = _build_archive(folder)
    response = requests.post(
        f"{config['server_url'].rstrip('/')}/sync/api/silicons/{config['silicon_username']}/push/",
        headers={"X-Source-Token": config["source_token"]},
        data={"tree_hash": tree_hash},
        files={"archive": ("snapshot.tar.gz", archive.getvalue(), "application/gzip")},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    config["last_tree_hash"] = tree_hash
    config_path.write_text(json.dumps(config, indent=2))
    return data


def _auth_headers(config):
    return {"Authorization": f"Bearer {config['api_key']}"}


def send_silicon_message(target_username, *, body="", kind="text", attachment_path=None, start=None):
    config, _ = load_glass_config(start)
    if "api_key" not in config:
        raise ValueError("This .glass.json does not contain a silicon api_key.")

    files = None
    data = {"kind": kind, "body": body}
    if attachment_path:
        path = Path(attachment_path)
        files = {"attachment": (path.name, path.open("rb"))}

    response = requests.post(
        f"{config['server_url'].rstrip('/')}/messages/api/threads/{target_username}/send/",
        headers=_auth_headers(config),
        data=data,
        files=files,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def _kind_from_extension(path):
    """Map a file path's extension to a Glass message kind."""
    from core.telegram import IMAGE_EXTS, VIDEO_EXTS, AUDIO_EXTS
    import os
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    return "document"


def reply_to_silicon_contact(contact, message, start=None):
    silicon_id = contact.get("silicon_id")
    if not silicon_id:
        return "Error: No silicon_id configured for this contact."
    if not message.strip():
        return "Error: message is required"

    from core.telegram import _parse_reply_segments, _text_to_speech
    import os

    segments = _parse_reply_segments(message)
    errors = []

    for seg_type, seg_value in segments:
        try:
            if seg_type == "text":
                send_silicon_message(silicon_id, body=seg_value, kind="text", start=start)

            elif seg_type == "file":
                path = os.path.expanduser(seg_value.strip())
                if not os.path.isabs(path):
                    path = os.path.abspath(path)
                if not os.path.exists(path):
                    errors.append(f"File not found: {path}")
                    continue
                kind = _kind_from_extension(path)
                send_silicon_message(silicon_id, body="", kind=kind, attachment_path=path, start=start)

            elif seg_type == "voice":
                ogg_path = _text_to_speech(seg_value)
                if not ogg_path:
                    errors.append(f"TTS failed for: {seg_value[:50]}")
                    continue
                send_silicon_message(silicon_id, body="", kind="audio", attachment_path=ogg_path, start=start)
        except Exception as e:
            errors.append(f"{seg_type} segment failed: {e}")

    if errors:
        return "Sent with errors: " + "; ".join(errors)
    return "Message sent"


def list_silicon_threads(start=None):
    config, _ = load_glass_config(start)
    if "api_key" not in config:
        raise ValueError("This .glass.json does not contain a silicon api_key.")
    response = requests.get(
        f"{config['server_url'].rstrip('/')}/messages/api/threads/",
        headers=_auth_headers(config),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def silicon_exists(target_username, start=None):
    try:
        get_thread_messages(target_username, after=0, start=start)
        return True
    except requests.HTTPError as exc:
        response = getattr(exc, "response", None)
        if response is not None and response.status_code == 404:
            return False
        raise


def ensure_known_silicon_contact(target_username):
    if not silicon_exists(target_username):
        return None, False
    _, carbon_id, contact, _ = _ensure_silicon_contact(target_username)
    return contact, True


def get_thread_messages(target_username, after=None, start=None):
    config, _ = load_glass_config(start)
    if "api_key" not in config:
        raise ValueError("This .glass.json does not contain a silicon api_key.")
    params = {}
    if after is not None:
        params["after"] = after
    response = requests.get(
        f"{config['server_url'].rstrip('/')}/messages/api/threads/{target_username}/",
        headers=_auth_headers(config),
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_unread_silicon_messages(start=None):
    try:
        config, _ = load_glass_config(start)
    except FileNotFoundError:
        return {}
    if "api_key" not in config or "silicon_username" not in config:
        return {}

    state = _load_state()
    threads_data = list_silicon_threads(start=start)
    threads = threads_data.get("threads", [])
    own_silicon_id = config["silicon_username"]
    contexts = {}
    metadata = {}

    for thread in threads:
        other_silicon = thread.get("other_silicon")
        if not other_silicon:
            continue

        last_seen = state.setdefault("threads", {}).get(other_silicon, {}).get("last_message_id")
        payload = get_thread_messages(other_silicon, after=last_seen, start=start)
        messages = payload.get("messages", [])
        if not messages:
            continue

        max_seen = last_seen or 0
        for message in messages:
            message_id = message.get("id") or 0
            if message_id > max_seen:
                max_seen = message_id
            if message.get("sender") == own_silicon_id:
                continue

            contacts_data, carbon_id, contact, is_new = _ensure_silicon_contact(other_silicon)
            metadata.setdefault(
                carbon_id,
                {
                    "is_new": is_new,
                    "name": contact.get("name") or other_silicon,
                    "silicon_id": other_silicon,
                },
            )
            contexts.setdefault(carbon_id, [])

            timestamp = _timestamp_label(message.get("created_at"))
            reply_prefix = ""
            if message.get("reply_to"):
                reply_prefix = f"(replying to message {message['reply_to']}) "
            line = _message_preview(message)
            if not line:
                continue
            if timestamp:
                line = f"{timestamp} {reply_prefix}{line}"
            elif reply_prefix:
                line = f"{reply_prefix}{line}"
            contexts[carbon_id].append(line)

        state["threads"][other_silicon] = {"last_message_id": max_seen}

    _save_state(state)

    result = {}
    for carbon_id, messages in contexts.items():
        if not messages:
            continue
        info = metadata[carbon_id]
        if info["is_new"]:
            prefix = (
                f"NEW SILICON - First time message from {info['name']} "
                f"(silicon_id: {info['silicon_id']}):"
            )
        else:
            prefix = (
                f"Messages from {info['name']} "
                f"(silicon_id: {info['silicon_id']}):"
            )
        result[carbon_id] = prefix + "\n" + "\n---\n".join(messages)

    return result
