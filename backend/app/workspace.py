"""Per-project workspace on disk — source of truth for Studio files."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.config import get_settings

settings = get_settings()

_ROOT = Path(__file__).resolve().parents[2]
WORKSPACES = _ROOT / "data" / "workspaces"
SKIP_NAMES = {".git", ".onestack", ".zeuscode", "__pycache__", "node_modules", ".DS_Store"}


def workspace_root(user_id: int, project_id: int) -> Path:
    return WORKSPACES / str(user_id) / str(project_id)


def ensure_workspace(user_id: int, project_id: int, *, title: str = "project") -> Path:
    root = workspace_root(user_id, project_id)
    root.mkdir(parents=True, exist_ok=True)
    git_dir = root / ".git"
    if not git_dir.exists():
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "studio@zeuscode.local"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "ZeusCode Studio"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        readme = root / "README.md"
        if not readme.exists():
            readme.write_text(
                f"# {title}\n\nWorkspace ZeusCode Studio.\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "chore: init workspace"],
                cwd=root,
                check=True,
                capture_output=True,
            )
    return root


def resolve_path(root: Path, rel: str) -> Path:
    """Jail path under workspace root. Raises ValueError if escape attempted."""
    clean = (rel or "").replace("\\", "/").lstrip("/")
    if ".." in clean.split("/"):
        raise ValueError("Path escapes workspace")
    target = (root / clean).resolve()
    root_res = root.resolve()
    if not str(target).startswith(str(root_res)):
        raise ValueError("Path escapes workspace")
    return target


def list_tree(root: Path, *, max_files: int = 2000) -> list[dict[str, Any]]:
    """Flat sorted file list with relative paths."""
    if not root.exists():
        return []
    out: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_NAMES and not d.startswith(".")]
        for name in filenames:
            if name.startswith(".") and name not in {".gitignore", ".env.example"}:
                continue
            full = Path(dirpath) / name
            try:
                rel = "/" + str(full.relative_to(root)).replace("\\", "/")
            except ValueError:
                continue
            out.append(
                {
                    "path": rel,
                    "name": name,
                    "type": "file",
                    "size": full.stat().st_size if full.is_file() else 0,
                }
            )
            if len(out) >= max_files:
                return sorted(out, key=lambda x: x["path"])
    return sorted(out, key=lambda x: x["path"])


def paths_to_tree(paths: list[str]) -> list[dict[str, Any]]:
    tree_dict: dict = {}

    def insert(tree: dict, parts: list[str]) -> None:
        if not parts:
            return
        head, *rest = parts
        if head not in tree:
            tree[head] = {}
        insert(tree[head], rest)

    for path in paths:
        parts = [p for p in path.strip("/").split("/") if p]
        insert(tree_dict, parts)

    def to_list(d: dict, prefix: str = "") -> list[dict]:
        items = []
        for name, child in sorted(d.items()):
            p = f"{prefix}/{name}"
            if child:
                items.append({"name": name, "path": p, "type": "dir", "children": to_list(child, p)})
            else:
                items.append({"name": name, "path": p, "type": "file", "children": []})
        return items

    return to_list(tree_dict)


def read_file(root: Path, rel: str, *, max_bytes: int = 1_500_000) -> dict[str, Any]:
    target = resolve_path(root, rel)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(rel)
    data = target.read_bytes()
    if len(data) > max_bytes:
        raise ValueError(f"File too large ({len(data)} bytes)")
    try:
        text = data.decode("utf-8")
        binary = False
    except UnicodeDecodeError:
        text = ""
        binary = True
    return {
        "path": "/" + str(target.relative_to(root)).replace("\\", "/"),
        "content": text,
        "binary": binary,
        "size": len(data),
    }


def write_file(root: Path, rel: str, content: str) -> dict[str, Any]:
    target = resolve_path(root, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {
        "path": "/" + str(target.relative_to(root)).replace("\\", "/"),
        "size": target.stat().st_size,
    }


def delete_file(root: Path, rel: str) -> None:
    target = resolve_path(root, rel)
    if target.exists() and target.is_file():
        target.unlink()


def apply_artifacts(root: Path, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Write orchestrator artifacts (path + content) into workspace."""
    written: list[dict[str, Any]] = []
    for a in artifacts or []:
        path = (a.get("path") or "").strip()
        content = a.get("content")
        if not path or content is None:
            continue
        # strip leading /src/ convention → keep as relative under workspace
        rel = path.lstrip("/")
        try:
            info = write_file(root, rel, str(content))
            written.append({**info, "role": a.get("role") or "", "language": a.get("language") or ""})
        except ValueError:
            continue
    return written


def remove_workspace(user_id: int, project_id: int) -> None:
    root = workspace_root(user_id, project_id)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


def find_preview_entry(root: Path) -> str | None:
    """Return relative path to a sensible HTML entry, if any."""
    candidates = [
        "index.html",
        "src/frontend/index.html",
        "src/index.html",
        "public/index.html",
        "frontend/index.html",
    ]
    for c in candidates:
        if (root / c).is_file():
            return c
    for p in root.rglob("index.html"):
        if any(part in SKIP_NAMES for part in p.parts):
            continue
        try:
            return str(p.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
    return None
