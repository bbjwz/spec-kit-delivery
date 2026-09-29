from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


def now() -> str:
    return datetime.now(UTC).isoformat()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(root: Path, relative: str | Path) -> Path:
    root = root.resolve()
    path = root / relative
    # Reject symlinks even when their targets currently remain inside the root.
    if not path.resolve().is_relative_to(root):
        raise ValueError(f"path escapes root: {relative}")
    current = path
    while current != root:
        if current.is_symlink():
            raise ValueError(f"symlink is not evidence: {relative}")
        current = current.parent
    return path


def write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".delivery-")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read(path: Path) -> Any:
    return yaml.safe_load(path.read_text())


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def normalized_document(name: str, text: str) -> str:
    if name.endswith("tasks.md"):
        return re.sub(r"(?m)^(\s*- )\[[ xX]\]", r"\1[ ]", text)
    return text


def documents(feature: Path) -> dict[str, str]:
    return {
        name: normalized_document(name, (feature / name).read_text()) for name in ("spec.md", "plan.md", "tasks.md")
    }


def source_manifest(root: Path) -> dict[str, str]:
    """Include tracked and nonignored source, including dirty/untracked edits.

    Only generated delivery outputs are excluded. Baselines and policy ARE source.
    """
    raw = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    manifest = {}
    for name in sorted(set(raw.split("\0")) - {""}):
        parts = Path(name).parts
        if "delivery" in parts:
            suffix = parts[parts.index("delivery") + 1 :]
            if suffix and suffix[0] in {"runs", "presentations", "verification.json"}:
                continue
        path = inside(root, name)
        if path.is_dir():
            raise ValueError(f"submodules/directories require explicit evidence: {name}")
        if not path.exists():
            manifest[name] = "DELETED"
        elif name.endswith("tasks.md"):
            manifest[name] = digest(normalized_document(name, path.read_text()))
        else:
            manifest[name] = file_hash(path)
    return manifest


def feature_dir(root: Path, selected: str | None) -> Path:
    value = selected or os.environ.get("SPECIFY_FEATURE_DIRECTORY")
    pointer = root / ".specify/feature.json"
    if not value and pointer.exists():
        pointer_data = read(pointer)
        value = pointer_data.get("feature_directory") or pointer_data.get("feature_dir")
    if not value:
        branch = git(root, "branch", "--show-current")
        candidate = root / "specs" / branch
        if candidate.is_dir():
            value = str(candidate)
    if not value:
        candidates = list((root / "specs").glob("*/tasks.md"))
        if len(candidates) == 1:
            value = str(candidates[0].parent)
    if not value:
        raise ValueError("select the active feature with --feature specs/<feature>")
    result = inside(root, value)
    if not result.is_relative_to(root / "specs"):
        raise ValueError("feature must be under specs/")
    inside(root, result / "delivery")
    return result
