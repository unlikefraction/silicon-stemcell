import io
import json
import tarfile
from pathlib import Path

import requests

CONFIG_FILE = ".glass.json"
IGNORE_NAMES = {".git", "__pycache__", ".DS_Store", CONFIG_FILE}


def _find_glass_config(start=None):
    start = Path(start or Path.cwd()).resolve()
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
