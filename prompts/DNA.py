"""
# This is your DNA (Instruction Set)

### Your Soul lives in prompts/SOUL.md
This is where you become you. This is how you behave.

### Your Memories are in prompts/MEMORY.md
Everything you remember, or wanna remember is inside this file. This is your hipocampus. If you dont write it inside it, you will not remember it. Write everything you wanna remember. Remove anything you dont want to remember.

### About you (prompts/SILICON.md) and your carbon (prompts/memory/people/{carbon_id}.md)
If Soul is how you behave, these are what you know about you and your carbon.
Name, preferences, style, thinking patterns, etc etc

### LORE (prompts/LORE.md)
This is your lore. Your backstory. Your history.
Write this as new things shape you.
this will help you know who you were and who you've become. this is what will go down in history about you.

### DNA (prompts/DNA.py)
This file is your DNA. Your Instruction Set. This is how you know what to do and why you do what you do.
Should you edit your DNA? NO. Can you? YES.
Don't be CRISPR until you reallly need to!
If you want to load something new (eg, about a project your carbon is working on, add that to the DNA below). The DNA below is what is rendered and passed to you as prompt. This is how you know about anything at all.
"""

import os
import re
import json

PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PROMPTS_DIR)

VALID_WORKER_TYPES = ["browser", "terminal", "writer"]


def _resolve_load_refs(text):
    """Replace {load-ref!path} with the contents of the referenced file.
    Paths are relative to the project root."""
    def replacer(match):
        ref_path = match.group(1)
        # Skip glob patterns (*, ?) - those are instructional text, not actual refs
        if '*' in ref_path or '?' in ref_path:
            return match.group(0)
        full_path = os.path.join(PROJECT_ROOT, ref_path)
        if os.path.exists(full_path):
            with open(full_path, "r") as f:
                return f.read().strip()
        return f"[load-ref error: {ref_path} not found]"

    return re.sub(r'\{load-ref!([^}]+)\}', replacer, text)


def _read_prompt(filename):
    path = os.path.join(PROMPTS_DIR, filename)
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read().strip()
        content = _resolve_load_refs(content)
        return f"prompts/{filename}\n{content}"
    return ""


def _read_file_raw(filepath):
    """Read a file and return its contents, or empty string if not found."""
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return f.read().strip()
    return "This Carbon has no memory stored about them yet."


def _get_contact_info(carbon_id):
    """Load contact info for a specific carbon_id from contacts.json."""
    contacts_file = os.path.join(PROJECT_ROOT, "core", "telegram", "contacts.json")
    if not os.path.exists(contacts_file):
        return None
    with open(contacts_file) as f:
        data = json.load(f)
    return data.get("contacts", {}).get(carbon_id)


# def _get_contacts_summary():
#     """Load all contacts for the CONTACTS.md context."""
#     contacts_file = os.path.join(PROJECT_ROOT, "core", "telegram", "contacts.json")
#     if not os.path.exists(contacts_file):
#         return "No contacts loaded."
#     with open(contacts_file) as f:
#         data = json.load(f)
#     contacts = data.get("contacts", {})
#     if not contacts:
#         return "No contacts yet."

#     lines = []
#     for cid, info in contacts.items():
#         name = info.get("name") or cid
#         trust = info.get("trust_level", "very_low")
#         central = " [CENTRAL CARBON]" if info.get("is_central_carbon") else ""
#         relation = info.get("relation", "")
#         lines.append(f"- {name} (carbon_id: {cid}, trust: {trust}{central}){': ' + relation if relation else ''}")
#     return "\n".join(lines)


def get_manager_prompt(carbon_id):
    """Build the system prompt for a specific carbon's manager."""
    contact = _get_contact_info(carbon_id)
    trust_level = contact.get("trust_level", "very_low") if contact else "very_low"

    parts = []

    parts.extend([
        _read_prompt("DNA.py"),
        _read_prompt("SOUL.md"),
        _read_prompt("SILICON.md"),
        _read_prompt("LORE.md"),
        _read_prompt("CONTACTS.md"),
        # f"## Current Contacts\n{_get_contacts_summary()}",
        _read_prompt(f"trust/{trust_level}.md"),
    ])

    # Load per-carbon memory file
    carbon_memory_path = os.path.join(PROMPTS_DIR, "memory", "people", f"{carbon_id}.md")
    carbon_memory = _read_file_raw(carbon_memory_path)
    if carbon_memory:
        parts.append(f"## About this Carbon ({carbon_id})\nprompts/memory/people/{carbon_id}.md\n{carbon_memory}")

    parts.extend([
        _read_prompt("MEMORY.md"),
        _read_prompt("MANAGER.md"),
        _read_prompt("MANAGER_TOOLS.md"),
    ])

    # Add carbon_id context
    parts.append(f"\n## Current Session\nYou are talking to carbon_id: {carbon_id}\nTheir trust level: {trust_level}")

    # Load BOOT.md if it exists
    boot_path = os.path.join(PROMPTS_DIR, "BOOT.md")
    if os.path.exists(boot_path):
        parts.append(_read_prompt("BOOT.md"))

    return "\n\n".join(p for p in parts if p)


def get_worker_prompt(worker_type):
    """Build the system prompt for a specific worker type.
    worker_type must be one of: browser, terminal, writer.
    Returns (prompt_string, error_string). One of them will be empty."""
    if not worker_type:
        return "", "Error: worker_type is required. Available types: browser, terminal, writer"

    worker_type = worker_type.lower()
    if worker_type not in VALID_WORKER_TYPES:
        return "", f"Error: invalid worker_type '{worker_type}'. Available types: browser, terminal, writer"

    type_upper = worker_type.upper()
    parts = [
        _read_prompt("WORKER.md"),
        _read_prompt(f"worker/{type_upper}.md"),
        _read_prompt(f"worker/{type_upper}_WTOOLS.md"),
    ]
    return "\n\n".join(p for p in parts if p), ""
