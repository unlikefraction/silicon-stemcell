import os
import json
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests
from core.telegram.config import BOT_TOKEN, API_BASE, FILE_API_BASE, CONTACTS_FILE, MEDIA_DIR, OPENAI_KEY

VALID_TRUST_LEVELS = ["very_low", "low", "ok", "high", "very_high", "ultimate"]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".webm", ".m4v"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".wma"}

RICH_MEDIA_RE = re.compile(r'\[(file|voice)=(.+?)\]')


def _load_contacts():
    if os.path.exists(CONTACTS_FILE):
        with open(CONTACTS_FILE) as f:
            return json.load(f)
    return {"last_update_id": 0, "contacts": {}}


def _save_contacts(data):
    with open(CONTACTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _get_carbon_id_by_telegram_userid(contacts_data, telegram_userid):
    for carbon_id, info in contacts_data.get("contacts", {}).items():
        if info.get("telegram_userid") == telegram_userid:
            return carbon_id
    return None


def _create_new_contact(contacts_data, telegram_userid, first_name):
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


# --- Media download ---

def _ensure_media_dir():
    os.makedirs(MEDIA_DIR, exist_ok=True)


def _download_telegram_file(file_id, ext="", subfolder=""):
    try:
        resp = requests.get(f"{API_BASE}/getFile", params={"file_id": file_id}, timeout=15)
        data = resp.json()
        if not data.get("ok"):
            return None

        file_path = data["result"]["file_path"]
        download_url = f"{FILE_API_BASE}/{file_path}"

        if not ext:
            _, ext = os.path.splitext(file_path)
        if ext and not ext.startswith("."):
            ext = "." + ext

        save_dir = os.path.join(MEDIA_DIR, subfolder) if subfolder else MEDIA_DIR
        os.makedirs(save_dir, exist_ok=True)

        timestamp = int(time.time() * 1000)
        local_filename = f"{timestamp}_{file_id[:8]}{ext}"
        local_path = os.path.join(save_dir, local_filename)

        file_resp = requests.get(download_url, timeout=60)
        if file_resp.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(file_resp.content)
            return local_path
    except Exception as e:
        print(f"[Telegram] Error downloading file {file_id}: {e}", flush=True)
    return None


def _transcribe_voice(local_path):
    if not OPENAI_KEY:
        return None
    try:
        with open(local_path, "rb") as audio_file:
            resp = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {OPENAI_KEY}"},
                files={"file": (os.path.basename(local_path), audio_file)},
                data={"model": "whisper-1"},
                timeout=60,
            )
        if resp.status_code == 200:
            text = resp.json().get("text", "").strip()
            return text if text else None
    except Exception as e:
        print(f"[Telegram] Whisper transcription error: {e}", flush=True)
    return None


def _extract_media_from_message(msg):
    media = []

    if msg.get("photo"):
        largest = max(msg["photo"], key=lambda p: p.get("file_size", 0))
        media.append({"type": "photo", "file_id": largest["file_id"], "ext": ".jpg"})

    if msg.get("video"):
        mime = msg["video"].get("mime_type", "video/mp4")
        ext = ".mp4" if "mp4" in mime else ".mkv"
        media.append({"type": "video", "file_id": msg["video"]["file_id"], "ext": ext})

    if msg.get("video_note"):
        media.append({"type": "video_note", "file_id": msg["video_note"]["file_id"], "ext": ".mp4"})

    if msg.get("voice"):
        media.append({"type": "voice", "file_id": msg["voice"]["file_id"], "ext": ".ogg"})

    if msg.get("audio"):
        mime = msg["audio"].get("mime_type", "audio/mpeg")
        ext = ".mp3" if "mpeg" in mime else ".ogg" if "ogg" in mime else ".m4a"
        media.append({"type": "audio", "file_id": msg["audio"]["file_id"], "ext": ext,
                       "title": msg["audio"].get("title", ""), "performer": msg["audio"].get("performer", "")})

    if msg.get("document"):
        doc = msg["document"]
        fname = doc.get("file_name", "")
        _, ext = os.path.splitext(fname) if fname else ("", "")
        media.append({"type": "document", "file_id": doc["file_id"], "ext": ext,
                       "file_name": fname, "mime_type": doc.get("mime_type", "")})

    if msg.get("sticker"):
        sticker = msg["sticker"]
        ext = ".webp" if not sticker.get("is_animated") else ".tgs"
        media.append({"type": "sticker", "file_id": sticker["file_id"], "ext": ext,
                       "emoji": sticker.get("emoji", "")})

    return media


def _process_media(msg):
    _ensure_media_dir()
    media_items = _extract_media_from_message(msg)
    if not media_items:
        return ""

    parts = []
    for item in media_items:
        mtype = item["type"]
        local_path = _download_telegram_file(item["file_id"], item.get("ext", ""), subfolder=mtype)

        if mtype == "voice":
            if local_path:
                text = _transcribe_voice(local_path)
                if text:
                    parts.append(f"[Voice message transcription]: {text}")
                else:
                    parts.append(f"[Audio message couldn't be transcribed] (saved at: {local_path})")
            else:
                parts.append("[Audio message couldn't be downloaded]")

        elif mtype == "audio":
            if local_path:
                title = item.get("title", "")
                performer = item.get("performer", "")
                label = f"{performer} - {title}" if performer and title else title or "audio"
                text = _transcribe_voice(local_path)
                if text:
                    parts.append(f"[Audio: {label}] (saved at: {local_path})\n[Transcription]: {text}")
                else:
                    parts.append(f"[Audio: {label}] (saved at: {local_path})")
            else:
                parts.append("[Audio file couldn't be downloaded]")

        elif mtype == "photo":
            if local_path:
                parts.append(f"[Photo received] (@{local_path})")
            else:
                parts.append("[Photo couldn't be downloaded]")

        elif mtype in ("video", "video_note"):
            label = "Video" if mtype == "video" else "Video note"
            if local_path:
                parts.append(f"[{label} received] (saved at: {local_path})")
            else:
                parts.append(f"[{label} couldn't be downloaded]")

        elif mtype == "document":
            fname = item.get("file_name", "file")
            if local_path:
                parts.append(f"[File received: {fname}] (@{local_path})")
            else:
                parts.append(f"[File '{fname}' couldn't be downloaded]")

        elif mtype == "sticker":
            emoji = item.get("emoji", "")
            if local_path:
                parts.append(f"[Sticker {emoji}] (saved at: {local_path})")
            else:
                parts.append(f"[Sticker {emoji}]")

    return "\n".join(parts)


# --- Outgoing: TTS and file sending ---

def _text_to_speech(text):
    """Convert text to speech using OpenAI TTS. Returns path to .ogg file or None."""
    if not OPENAI_KEY:
        return None
    try:
        resp = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {OPENAI_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "tts-1",
                "input": text,
                "voice": "alloy",
                "response_format": "opus",
            },
            timeout=60,
        )
        if resp.status_code == 200:
            tts_dir = os.path.join(MEDIA_DIR, "tts")
            os.makedirs(tts_dir, exist_ok=True)
            timestamp = int(time.time() * 1000)
            path = os.path.join(tts_dir, f"tts_{timestamp}.ogg")
            with open(path, "wb") as f:
                f.write(resp.content)
            return path
    except Exception as e:
        print(f"[Telegram] TTS error: {e}", flush=True)
    return None


def _send_file_to_chat(chat_id, path):
    """Send a file to a Telegram chat, auto-detecting type from extension."""
    path = os.path.expanduser(path.strip())
    if not os.path.isabs(path):
        path = os.path.abspath(path)

    if not os.path.exists(path):
        return f"Error: File not found: {path}"

    _, ext = os.path.splitext(path)
    ext = ext.lower()

    if ext in IMAGE_EXTS:
        method, field = "sendPhoto", "photo"
    elif ext in VIDEO_EXTS:
        method, field = "sendVideo", "video"
    elif ext in AUDIO_EXTS:
        method, field = "sendAudio", "audio"
    else:
        method, field = "sendDocument", "document"

    try:
        with open(path, "rb") as f:
            files = {field: (os.path.basename(path), f)}
            resp = requests.post(f"{API_BASE}/{method}", data={"chat_id": chat_id}, files=files, timeout=120)
        result = resp.json()
        if result.get("ok"):
            return "Sent"
        return f"Error sending file: {result.get('description', result)}"
    except Exception as e:
        return f"Error sending file: {e}"


def _send_voice_to_chat(chat_id, ogg_path):
    """Send a voice message (.ogg) to a Telegram chat."""
    try:
        with open(ogg_path, "rb") as f:
            files = {"voice": (os.path.basename(ogg_path), f)}
            resp = requests.post(f"{API_BASE}/sendVoice", data={"chat_id": chat_id}, files=files, timeout=60)
        result = resp.json()
        if result.get("ok"):
            return "Sent"
        return f"Error sending voice: {result.get('description', result)}"
    except Exception as e:
        return f"Error sending voice: {e}"


def _send_text_chunked(chat_id, text, parse_mode=None):
    """Send a text message, splitting into chunks if over 4096 chars."""
    MAX_LEN = 4096
    if len(text) <= MAX_LEN:
        return _send_single_message(chat_id, text, parse_mode)

    chunks = []
    current = ""
    for line in text.split("\n"):
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
    return "Sent"


def _parse_reply_segments(message):
    """Parse a reply message into ordered segments.
    Returns list of ("text", content) | ("file", path) | ("voice", tts_text)."""
    segments = []
    last_end = 0

    for match in RICH_MEDIA_RE.finditer(message):
        start, end = match.span()

        # Text before this match
        text_before = message[last_end:start].strip()
        if text_before:
            segments.append(("text", text_before))

        seg_type = match.group(1)   # "file" or "voice"
        seg_value = match.group(2)  # path or tts text
        segments.append((seg_type, seg_value))

        last_end = end

    # Remaining text after last match
    text_after = message[last_end:].strip()
    if text_after:
        segments.append(("text", text_after))

    # No rich media found — whole message is text
    if not segments:
        segments.append(("text", message))

    return segments


# --- Public API ---

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

    messages_by_carbon = {}
    new_users = set()

    for update in data["result"]:
        contacts_data["last_update_id"] = update["update_id"]

        msg = update.get("message") or update.get("edited_message")
        if not msg:
            continue

        user_id = msg.get("from", {}).get("id")
        text = msg.get("text", "")
        caption = msg.get("caption", "")
        first_name = msg.get("from", {}).get("first_name", "")

        if not user_id:
            continue

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

        reply_to = msg.get("reply_to_message")
        formatted = ""
        if timestamp:
            formatted += f"{timestamp} "
        if reply_to:
            tagged_text = reply_to.get("text", "") or reply_to.get("caption", "")
            if tagged_text:
                formatted += f"Tagged:\n> {tagged_text}\n\nReply:\n"

        media_text = _process_media(msg)

        if text.strip() == "/new":
            messages_by_carbon[carbon_id]["messages"].append("[COMMAND: NEW_SESSION]")
        elif text.strip() == "/start":
            messages_by_carbon[carbon_id]["messages"].append("[COMMAND: START]")
        else:
            content_parts = []
            if text.strip():
                content_parts.append(text)
            if caption.strip():
                content_parts.append(caption)
            if media_text:
                content_parts.append(media_text)

            if content_parts:
                messages_by_carbon[carbon_id]["messages"].append(formatted + "\n".join(content_parts))

    _save_contacts(contacts_data)

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
    """Send a message to a carbon via Telegram.

    Supports rich media inline syntax:
      [file=/path/to/anything]  — sends photo/video/audio/doc based on extension
      [voice=text to speak]     — TTS via OpenAI, sent as voice bubble

    Text around rich media blocks is sent as separate text messages, in order.
    Unrecognized bracket patterns are left as-is (sent as plain text).
    """
    contacts_data = _load_contacts()
    contact = contacts_data.get("contacts", {}).get(carbon_id)

    if not contact:
        return f"Error: carbon_id '{carbon_id}' not found in contacts"

    chat_id = contact.get("telegram_userid")
    if not chat_id:
        return f"Error: No telegram_userid for carbon_id '{carbon_id}'"

    segments = _parse_reply_segments(message)
    errors = []

    for seg_type, seg_value in segments:
        if seg_type == "text":
            status = _send_text_chunked(chat_id, seg_value, parse_mode)
            if "Error" in status:
                errors.append(status)

        elif seg_type == "file":
            status = _send_file_to_chat(chat_id, seg_value)
            if "Error" in status:
                errors.append(status)

        elif seg_type == "voice":
            ogg_path = _text_to_speech(seg_value)
            if ogg_path:
                status = _send_voice_to_chat(chat_id, ogg_path)
                if "Error" in status:
                    errors.append(status)
            else:
                errors.append(f"TTS failed for: {seg_value[:50]}")

    if errors:
        return "Sent with errors: " + "; ".join(errors)
    return "Message sent"


def _send_single_message(chat_id, text, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        resp = requests.post(f"{API_BASE}/sendMessage", json=payload, timeout=10)
        result = resp.json()
        if result.get("ok"):
            return "Sent"
        if parse_mode:
            payload.pop("parse_mode", None)
            resp = requests.post(f"{API_BASE}/sendMessage", json=payload, timeout=10)
            result = resp.json()
            if result.get("ok"):
                return "Sent"
        return f"Error sending message: {result}"
    except Exception as e:
        return f"Error sending message: {e}"


def get_contacts():
    return _load_contacts()


def get_contact(carbon_id):
    data = _load_contacts()
    return data.get("contacts", {}).get(carbon_id)
