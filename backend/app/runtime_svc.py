"""Preview HTTP server + PTY terminal sessions per project workspace."""

from __future__ import annotations

import asyncio
import os
import signal
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.workspace import find_preview_entry


@dataclass
class PreviewProc:
    port: int
    pid: int
    process: asyncio.subprocess.Process
    entry: str | None = None


_previews: dict[int, PreviewProc] = {}
_terms: dict[str, Any] = {}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def start_preview(project_id: int, root: Path) -> dict[str, Any]:
    await stop_preview(project_id)
    entry = find_preview_entry(root)
    # Serve workspace root so relative assets work; entry is for UI hint
    port = _free_port()
    proc = await asyncio.create_subprocess_exec(
        "python3",
        "-m",
        "http.server",
        str(port),
        "--bind",
        "127.0.0.1",
        cwd=str(root),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    _previews[project_id] = PreviewProc(port=port, pid=proc.pid or 0, process=proc, entry=entry)
    await asyncio.sleep(0.25)
    return {
        "ok": True,
        "port": port,
        "url": f"/projects/{project_id}/preview/",
        "entry": entry,
        "direct": f"http://127.0.0.1:{port}/" + (entry or ""),
    }


async def stop_preview(project_id: int) -> dict[str, Any]:
    info = _previews.pop(project_id, None)
    if not info:
        return {"ok": True, "stopped": False}
    try:
        info.process.terminate()
        try:
            await asyncio.wait_for(info.process.wait(), timeout=2)
        except asyncio.TimeoutError:
            info.process.kill()
    except ProcessLookupError:
        pass
    return {"ok": True, "stopped": True}


def preview_info(project_id: int) -> dict[str, Any] | None:
    info = _previews.get(project_id)
    if not info:
        return None
    if info.process.returncode is not None:
        _previews.pop(project_id, None)
        return None
    return {
        "port": info.port,
        "url": f"/projects/{project_id}/preview/",
        "entry": info.entry,
        "direct": f"http://127.0.0.1:{info.port}/" + (info.entry or ""),
    }


def get_preview_port(project_id: int) -> int | None:
    info = preview_info(project_id)
    return info["port"] if info else None


@dataclass
class TermSession:
    master_fd: int
    pid: int
    project_id: int
    buffer: bytearray = field(default_factory=bytearray)


def spawn_shell(project_id: int, root: Path) -> TermSession:
    import pty

    master, slave = pty.openpty()
    pid = os.fork()
    if pid == 0:
        os.close(master)
        os.setsid()
        os.dup2(slave, 0)
        os.dup2(slave, 1)
        os.dup2(slave, 2)
        if slave > 2:
            os.close(slave)
        os.chdir(str(root))
        os.environ["TERM"] = "xterm-256color"
        os.execvp(os.environ.get("SHELL", "/bin/zsh"), [os.environ.get("SHELL", "/bin/zsh"), "-l"])
    os.close(slave)
    os.set_blocking(master, False)
    sess = TermSession(master_fd=master, pid=pid, project_id=project_id)
    key = f"{project_id}:{pid}"
    _terms[key] = sess
    return sess


def kill_term(sess: TermSession) -> None:
    try:
        os.kill(sess.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        os.close(sess.master_fd)
    except OSError:
        pass
    for k, v in list(_terms.items()):
        if v is sess:
            _terms.pop(k, None)
