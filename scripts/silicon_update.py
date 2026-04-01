#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple


META_DIR_NAME = ".silicon-upstream"
BASE_DIR_NAME = "base"
META_FILE_NAME = "meta.json"

IGNORE_EXACT = {
    ".DS_Store",
    ".glass.json",
    ".restart_pending",
    ".silicon.err.log",
    ".silicon.log",
    ".silicon.pid",
    "core/cron/checkbacks.json",
    "core/cron/history.json",
    "core/telegram/contacts.json",
    "env.py",
    "manager_messages.json",
    "worker/outputs/_active_workers.json",
    "worker/outputs/_archive_meta.json",
    "worker/outputs/_browser_queue.json",
    "worker/outputs/_worker_registry.json",
}

IGNORE_PREFIXES = {
    ".git/",
    ".silicon-upstream/",
    "__pycache__/",
    "core/telegram/media/",
    "sessions/",
    "worker/outputs/",
}

TEXT_EXTENSIONS = {
    ".json", ".md", ".py", ".ps1", ".sh", ".txt", ".toml", ".yaml", ".yml", ".gitignore"
}


def normalize_rel(path: Path) -> str:
    return path.as_posix()


def should_ignore(rel: str) -> bool:
    if rel in IGNORE_EXACT:
        return True
    return any(rel.startswith(prefix) for prefix in IGNORE_PREFIXES)


def collect_files(root: Path) -> dict[str, Path]:
    files = {}
    if not root.exists():
        return files
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = normalize_rel(path.relative_to(root))
        if should_ignore(rel):
            continue
        files[rel] = path
    return files


def read_bytes(path: Optional[Path]) -> Optional[bytes]:
    if not path or not path.exists():
        return None
    return path.read_bytes()


def is_text_path(path: Path, blob: Optional[bytes] = None) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    if blob is None:
        blob = read_bytes(path)
    if blob is None:
        return False
    try:
        blob.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def write_file(path: Path, data: bytes, mode_source: Optional[Path] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mode_source and mode_source.exists():
        os.chmod(path, mode_source.stat().st_mode)


def replace_dir_contents(dst: Path, src: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for rel, src_path in collect_files(src).items():
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, target)


def save_meta(target: Path, source: Path) -> None:
    meta_dir = target / META_DIR_NAME
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "source": str(source),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (meta_dir / META_FILE_NAME).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def git_merge_file(local: bytes, base: bytes, upstream: bytes, rel: str) -> Tuple[bool, bytes]:
    with tempfile.TemporaryDirectory(prefix="silicon-merge-") as tmp:
        tmp_path = Path(tmp)
        local_path = tmp_path / "local"
        base_path = tmp_path / "base"
        upstream_path = tmp_path / "upstream"
        local_path.write_bytes(local)
        base_path.write_bytes(base)
        upstream_path.write_bytes(upstream)
        proc = subprocess.run(
            ["git", "merge-file", "-p", str(local_path), str(base_path), str(upstream_path)],
            capture_output=True,
        )
        if proc.returncode == 0:
            return True, proc.stdout
        return False, proc.stdout


def snapshot(source: Path, target: Path) -> int:
    base_dir = target / META_DIR_NAME / BASE_DIR_NAME
    replace_dir_contents(base_dir, source)
    save_meta(target, source)
    print(f"Snapshot refreshed from {source}")
    return 0


def update(source: Path, target: Path) -> int:
    upstream_files = collect_files(source)
    base_dir = target / META_DIR_NAME / BASE_DIR_NAME
    base_files = collect_files(base_dir)
    target_files = collect_files(target)

    writes: list[tuple[Path, bytes, Path]] = []
    added = 0
    updated = 0
    merged = 0
    kept_local = 0
    conflicts: list[str] = []

    git_available = shutil.which("git") is not None

    for rel, upstream_path in sorted(upstream_files.items()):
        local_path = target / rel
        base_path = base_dir / rel

        upstream_bytes = read_bytes(upstream_path)
        local_bytes = read_bytes(local_path)
        base_bytes = read_bytes(base_path)

        if local_bytes is None:
            writes.append((local_path, upstream_bytes, upstream_path))
            added += 1
            continue

        if local_bytes == upstream_bytes:
            continue

        if base_bytes is None:
            conflicts.append(rel)
            continue

        if local_bytes == base_bytes:
            writes.append((local_path, upstream_bytes, upstream_path))
            updated += 1
            continue

        if upstream_bytes == base_bytes:
            kept_local += 1
            continue

        if git_available and is_text_path(local_path, local_bytes) and is_text_path(base_path, base_bytes) and is_text_path(upstream_path, upstream_bytes):
            ok, merged_bytes = git_merge_file(local_bytes, base_bytes, upstream_bytes, rel)
            if ok:
                writes.append((local_path, merged_bytes, upstream_path))
                merged += 1
                continue

        conflicts.append(rel)

    if conflicts:
        print("Update aborted. Merge conflicts detected in these files:", file=sys.stderr)
        for rel in conflicts:
            print(f"  - {rel}", file=sys.stderr)
        print("No files were changed.", file=sys.stderr)
        return 2

    for path, data, mode_source in writes:
        write_file(path, data, mode_source)

    replace_dir_contents(base_dir, source)
    save_meta(target, source)

    print(f"Updated safely: {updated} replaced, {merged} auto-merged, {added} added, {kept_local} kept-local.")
    if not writes:
        print("Already up to date or all local changes were preserved without upstream edits.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("snapshot", "update"):
        p = sub.add_parser(name)
        p.add_argument("--source", required=True)
        p.add_argument("--target", required=True)

    args = parser.parse_args()
    source = Path(args.source).resolve()
    target = Path(args.target).resolve()

    if not source.exists():
        print(f"Source not found: {source}", file=sys.stderr)
        return 1
    if not target.exists():
        print(f"Target not found: {target}", file=sys.stderr)
        return 1

    if args.cmd == "snapshot":
        return snapshot(source, target)
    return update(source, target)


if __name__ == "__main__":
    raise SystemExit(main())
