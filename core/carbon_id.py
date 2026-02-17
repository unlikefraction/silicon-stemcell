import os
import re
import json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROMPTS_DIR = os.path.join(PROJECT_ROOT, "prompts")
SESSIONS_DIR = os.path.join(PROJECT_ROOT, "sessions")
CONTACTS_FILE = os.path.join(PROJECT_ROOT, "core", "telegram", "contacts.json")
MANAGER_MESSAGES_FILE = os.path.join(PROJECT_ROOT, "manager_messages.json")
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "worker", "outputs")
ACTIVE_FILE = os.path.join(OUTPUTS_DIR, "_active_workers.json")
BROWSER_QUEUE_FILE = os.path.join(OUTPUTS_DIR, "_browser_queue.json")
ARCHIVE_META_FILE = os.path.join(OUTPUTS_DIR, "_archive_meta.json")


def change_carbon_id(old_id, new_id):
    """Change a carbon's ID everywhere in the system.
    Uses exact slug-boundary matching so 'old_id' doesn't affect 'old_id_extra'.
    Returns status string."""

    # Validate new_id is a valid slug
    if not re.match(r'^[a-z0-9][a-z0-9_-]*$', new_id):
        return f"Error: '{new_id}' is not a valid carbon_id. Must start with alphanumeric, contain only lowercase letters, numbers, hyphens, and underscores."

    if new_id == old_id:
        return "Error: new carbon_id is the same as the current one."

    # Load contacts
    if not os.path.exists(CONTACTS_FILE):
        return "Error: contacts.json not found."

    with open(CONTACTS_FILE) as f:
        contacts_data = json.load(f)

    contacts = contacts_data.get("contacts", {})

    if old_id not in contacts:
        return f"Error: carbon_id '{old_id}' not found in contacts."

    if new_id in contacts:
        return f"Error: carbon_id '{new_id}' already exists."

    # 1. Update contacts.json
    contact = contacts.pop(old_id)
    contact["carbon_id"] = new_id
    contacts[new_id] = contact
    contacts_data["contacts"] = contacts
    with open(CONTACTS_FILE, "w") as f:
        json.dump(contacts_data, f, indent=2)

    # 2. Rename memory file
    old_memory = os.path.join(PROMPTS_DIR, "memory", "people", f"{old_id}.md")
    new_memory = os.path.join(PROMPTS_DIR, "memory", "people", f"{new_id}.md")
    if os.path.exists(old_memory):
        os.rename(old_memory, new_memory)

    # 3. Rename session file
    old_session = os.path.join(SESSIONS_DIR, f"{old_id}.txt")
    new_session_file = os.path.join(SESSIONS_DIR, f"{new_id}.txt")
    if os.path.exists(old_session):
        os.rename(old_session, new_session_file)

    # 4. Replace exact occurrences in all .md files inside prompts/
    # Slug-boundary-aware: won't match "old_id" inside "old_id_extra"
    pattern = re.compile(
        r'(?<![a-zA-Z0-9_-])' + re.escape(old_id) + r'(?![a-zA-Z0-9_-])'
    )
    for root, dirs, files in os.walk(PROMPTS_DIR):
        for fname in files:
            if fname.endswith('.md'):
                fpath = os.path.join(root, fname)
                with open(fpath, 'r') as f:
                    content = f.read()
                new_content = pattern.sub(new_id, content)
                if new_content != content:
                    with open(fpath, 'w') as f:
                        f.write(new_content)

    # 5. Update active workers
    if os.path.exists(ACTIVE_FILE):
        with open(ACTIVE_FILE) as f:
            active = json.load(f)
        changed = False
        for wid, info in active.items():
            if info.get("carbon_id") == old_id:
                info["carbon_id"] = new_id
                changed = True
        if changed:
            with open(ACTIVE_FILE, "w") as f:
                json.dump(active, f, indent=2)

    # 6. Update browser queue
    if os.path.exists(BROWSER_QUEUE_FILE):
        with open(BROWSER_QUEUE_FILE) as f:
            queue = json.load(f)
        changed = False
        for item in queue:
            if item.get("carbon_id") == old_id:
                item["carbon_id"] = new_id
                changed = True
        if changed:
            with open(BROWSER_QUEUE_FILE, "w") as f:
                json.dump(queue, f, indent=2)

    # 7. Update archive metadata
    if os.path.exists(ARCHIVE_META_FILE):
        with open(ARCHIVE_META_FILE) as f:
            meta = json.load(f)
        changed = False
        for aid, info in meta.items():
            if info.get("carbon_id") == old_id:
                info["carbon_id"] = new_id
                changed = True
        if changed:
            with open(ARCHIVE_META_FILE, "w") as f:
                json.dump(meta, f, indent=2)

    # 8. Update manager messages
    if os.path.exists(MANAGER_MESSAGES_FILE):
        with open(MANAGER_MESSAGES_FILE) as f:
            messages = json.load(f)
        changed = False
        if old_id in messages:
            messages[new_id] = messages.pop(old_id)
            changed = True
        for cid, msgs in messages.items():
            for m in msgs:
                if m.get("from_carbon_id") == old_id:
                    m["from_carbon_id"] = new_id
                    changed = True
        if changed:
            with open(MANAGER_MESSAGES_FILE, "w") as f:
                json.dump(messages, f, indent=2)

    return f"Done. carbon_id changed from '{old_id}' to '{new_id}' successfully."
