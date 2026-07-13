"""Git operations inside a project workspace."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


class GitError(RuntimeError):
    pass


def _run(root: Path, *args: str, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        env=env,
    )
    if check and result.returncode != 0:
        msg = (result.stderr or result.stdout or "git failed").strip()
        raise GitError(msg[:800])
    return result


def status(root: Path) -> dict[str, Any]:
    if not (root / ".git").exists():
        return {
            "branch": None,
            "dirty": False,
            "ahead": 0,
            "behind": 0,
            "files": [],
            "remote": None,
        }
    branch = _run(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    porcelain = _run(root, "status", "--porcelain").stdout
    files = []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        code = line[:2]
        path = line[3:].strip()
        files.append({"status": code.strip(), "path": path})
    ahead = behind = 0
    remote = None
    rem = _run(root, "remote", "get-url", "origin", check=False)
    if rem.returncode == 0:
        remote = rem.stdout.strip()
        ab = _run(root, "rev-list", "--left-right", "--count", f"HEAD...@{{u}}", check=False)
        if ab.returncode == 0:
            parts = ab.stdout.strip().split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])
    return {
        "branch": branch,
        "dirty": bool(files),
        "ahead": ahead,
        "behind": behind,
        "files": files,
        "remote": remote,
    }


def diff(root: Path, *, staged: bool = False) -> str:
    args = ["diff", "--no-color"]
    if staged:
        args.append("--cached")
    return _run(root, *args, check=False).stdout or ""


def commit(root: Path, message: str) -> dict[str, Any]:
    msg = (message or "").strip() or "chore: studio update"
    _run(root, "add", "-A")
    st = _run(root, "status", "--porcelain")
    if not st.stdout.strip():
        return {"ok": True, "empty": True, "message": "Nothing to commit"}
    _run(root, "commit", "-m", msg)
    sha = _run(root, "rev-parse", "HEAD").stdout.strip()
    return {"ok": True, "empty": False, "sha": sha, "message": msg}


def set_remote(root: Path, url: str) -> None:
    existing = _run(root, "remote", check=False).stdout
    if "origin" in existing.split():
        _run(root, "remote", "set-url", "origin", url)
    else:
        _run(root, "remote", "add", "origin", url)


def push(root: Path, *, token: str | None = None, branch: str | None = None) -> dict[str, Any]:
    st = status(root)
    br = branch or st.get("branch") or "main"
    env = None
    remote = st.get("remote") or ""
    if token and "github.com" in remote:
        # rewrite remote with token for this push only via GIT_ASKPASS-less URL
        m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote)
        if m:
            repo_path = m.group(1)
            url = f"https://x-access-token:{token}@github.com/{repo_path}.git"
            env = {**dict(**{k: v for k, v in __import__("os").environ.items()}), "GIT_TERMINAL_PROMPT": "0"}
            r = subprocess.run(
                ["git", "push", "-u", url, br],
                cwd=root,
                capture_output=True,
                text=True,
                env=env,
            )
            if r.returncode != 0:
                raise GitError((r.stderr or r.stdout or "push failed").strip()[:800])
            return {"ok": True, "branch": br}
    _run(root, "push", "-u", "origin", br, env=env)
    return {"ok": True, "branch": br}


def pull(root: Path, *, token: str | None = None) -> dict[str, Any]:
    st = status(root)
    br = st.get("branch") or "main"
    remote = st.get("remote") or ""
    if token and "github.com" in remote:
        m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote)
        if m:
            repo_path = m.group(1)
            url = f"https://x-access-token:{token}@github.com/{repo_path}.git"
            env = {**dict(**{k: v for k, v in __import__("os").environ.items()}), "GIT_TERMINAL_PROMPT": "0"}
            r = subprocess.run(
                ["git", "pull", url, br],
                cwd=root,
                capture_output=True,
                text=True,
                env=env,
            )
            if r.returncode != 0:
                raise GitError((r.stderr or r.stdout or "pull failed").strip()[:800])
            return {"ok": True}
    _run(root, "pull", "--ff-only")
    return {"ok": True}


def clone_into(root: Path, clone_url: str, *, token: str | None = None) -> None:
    """Clone repo into empty-ish workspace (replace contents)."""
    if root.exists():
        for child in root.iterdir():
            if child.name == ".onestack":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        root.mkdir(parents=True, exist_ok=True)
    url = clone_url
    if token and "github.com" in clone_url and "x-access-token" not in clone_url:
        url = clone_url.replace("https://", f"https://x-access-token:{token}@")
    parent = root.parent
    tmp = parent / f".clone_{root.name}"
    if tmp.exists():
        shutil.rmtree(tmp)
    r = subprocess.run(
        ["git", "clone", url, str(tmp)],
        capture_output=True,
        text=True,
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "GIT_TERMINAL_PROMPT": "0"},
    )
    if r.returncode != 0:
        raise GitError((r.stderr or r.stdout or "clone failed").strip()[:800])
    for child in tmp.iterdir():
        dest = root / child.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        shutil.move(str(child), str(dest))
    shutil.rmtree(tmp, ignore_errors=True)
    # ensure identity
    subprocess.run(
        ["git", "config", "user.email", "studio@zeuscode.local"],
        cwd=root,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "ZeusCode Studio"],
        cwd=root,
        capture_output=True,
    )


def create_worktree(root: Path, name: str, branch: str | None = None) -> Path:
    """Create isolated worktree under .onestack/forks/<name>."""
    forks = root / ".onestack" / "forks"
    forks.mkdir(parents=True, exist_ok=True)
    dest = forks / name
    if dest.exists():
        # remove old worktree registration if present
        _run(root, "worktree", "remove", "--force", str(dest), check=False)
        shutil.rmtree(dest, ignore_errors=True)
    br = branch or f"fork/{name}"
    # create new branch from HEAD
    _run(root, "branch", "-f", br, "HEAD", check=False)
    _run(root, "worktree", "add", "-B", br, str(dest), "HEAD")
    return dest


def remove_worktree(root: Path, name: str) -> None:
    dest = root / ".onestack" / "forks" / name
    _run(root, "worktree", "remove", "--force", str(dest), check=False)
    shutil.rmtree(dest, ignore_errors=True)


def copy_tree_files(src: Path, dst: Path) -> list[str]:
    """Copy all non-git files from src into dst (overwrite). Returns relative paths."""
    written: list[str] = []
    skip_dirs = {".git", ".onestack", "node_modules", "__pycache__"}
    for dirpath, dirnames, filenames in __import__("os").walk(src):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        for name in filenames:
            if name == ".git" or name.startswith(".git"):
                continue
            full = Path(dirpath) / name
            if not full.is_file():
                continue
            rel = full.relative_to(src)
            # never overwrite .git in destination
            if rel.parts and rel.parts[0] in skip_dirs:
                continue
            target = dst / rel
            if target.exists() and target.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(full.read_bytes())
            written.append("/" + str(rel).replace("\\", "/"))
    return written
