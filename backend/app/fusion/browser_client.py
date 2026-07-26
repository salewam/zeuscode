"""DJARVIS-compatible browser client for Fusion critics.

Transport preference:
  1) unix socket → browser-daemon (same protocol as DJARVIS browser-cli)
  2) optional subprocess via JARVIS_BROWSER_CLI when socket is down

Public ops used by web_tools / critics:
  web_navigate, web_get_text, browser_fetch_text
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import socket
import subprocess
from typing import Any

log = logging.getLogger("zeus.fusion.browser")

_DEFAULT_SOCK = "/run/browser-daemon/daemon.sock"
_DEFAULT_CLI = "/usr/local/bin/browser-cli.py"


def _settings() -> dict[str, Any]:
    try:
        from app.config import get_settings

        s = get_settings()
        return {
            "enabled": bool(getattr(s, "WEB_BROWSER_ENABLED", True)),
            "sock": (getattr(s, "WEB_BROWSER_SOCK", "") or _DEFAULT_SOCK).strip(),
            "timeout": max(3.0, min(float(getattr(s, "WEB_BROWSER_TIMEOUT_S", 18) or 18), 45.0)),
            "cli": (getattr(s, "JARVIS_BROWSER_CLI", "") or _DEFAULT_CLI).strip(),
        }
    except Exception:  # noqa: BLE001
        return {
            "enabled": True,
            "sock": _DEFAULT_SOCK,
            "timeout": 18.0,
            "cli": _DEFAULT_CLI,
        }


def browser_available() -> bool:
    cfg = _settings()
    if not cfg["enabled"]:
        return False
    sock = cfg["sock"]
    try:
        if sock and os.path.exists(sock):
            return True
    except Exception:  # noqa: BLE001
        pass
    cli = cfg["cli"]
    return bool(cli and (os.path.isfile(cli) or shutil.which(cli)))


def _send_socket(cmd: str, params: dict[str, Any] | None, *, sock_path: str, timeout: float) -> dict[str, Any]:
    if not os.path.exists(sock_path):
        return {"success": False, "error": "daemon_not_running", "sock": sock_path}

    msg = json.dumps({"cmd": cmd, "params": params or {}}, ensure_ascii=False).encode("utf-8") + b"\n"
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(sock_path)
        sock.sendall(msg)
        buf = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            if b"\n" in buf:
                break
        sock.close()
        line = buf.split(b"\n", 1)[0]
        if not line:
            return {"success": False, "error": "empty_response"}
        data = json.loads(line.decode("utf-8"))
        return data if isinstance(data, dict) else {"success": False, "error": "bad_json"}
    except FileNotFoundError:
        return {"success": False, "error": "daemon_not_running"}
    except TimeoutError:
        return {"success": False, "error": "timeout"}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": str(e)[:200]}


def _send_cli(cmd: str, params: dict[str, Any] | None, *, cli: str, timeout: float) -> dict[str, Any]:
    """Subprocess fallback matching DJARVIS browser-cli.py argv shape."""
    if not cli or not (os.path.isfile(cli) or shutil.which(cli)):
        return {"success": False, "error": "cli_missing", "cli": cli}
    params = params or {}
    argv = [cli if os.path.isfile(cli) else shutil.which(cli) or cli, cmd]
    if cmd == "navigate":
        argv.append(str(params.get("url") or ""))
    elif cmd == "get-text":
        sel = str(params.get("selector") or "")
        if sel:
            argv.extend(["--selector", sel])
    elif cmd == "scroll":
        argv.append(str(params.get("direction") or "down"))
    elif cmd == "click-selector":
        argv.append(str(params.get("selector") or ""))
    else:
        # Unsupported via cheap CLI path — critics only need navigate/get-text
        return {"success": False, "error": f"cli_unsupported:{cmd}"}

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout + 5.0,
            check=False,
        )
        line = (proc.stdout or "").strip().splitlines()
        raw = line[-1] if line else ""
        if not raw:
            return {
                "success": False,
                "error": "cli_empty",
                "stderr": (proc.stderr or "")[:200],
            }
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"success": False, "error": "cli_bad_json"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout"}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": str(e)[:200]}


def _send_sync(cmd: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _settings()
    if not cfg["enabled"]:
        return {"success": False, "error": "browser_disabled"}

    sock_res = _send_socket(cmd, params, sock_path=cfg["sock"], timeout=cfg["timeout"])
    if sock_res.get("success"):
        sock_res["_transport"] = "socket"
        return sock_res
    # Retry via CLI only when daemon socket path is dead
    err = str(sock_res.get("error") or "")
    if err in {"daemon_not_running", "cli_missing"} or "No such file" in err:
        cli_res = _send_cli(cmd, params, cli=cfg["cli"], timeout=cfg["timeout"])
        if cli_res.get("success"):
            cli_res["_transport"] = "cli"
            return cli_res
        return {**cli_res, "socket_error": err, "_transport": "cli"}
    return {**sock_res, "_transport": "socket"}


async def browser_cmd(cmd: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return await asyncio.to_thread(_send_sync, cmd, params)


async def web_navigate(url: str) -> dict[str, Any]:
    """Plan API: open URL in headless Chrome via DJARVIS daemon/cli."""
    u = (url or "").strip()
    if not u.startswith("http"):
        return {"ok": False, "degraded": True, "url": u, "error": "bad_url", "backend": "browser"}
    if not browser_available():
        return {"ok": False, "degraded": True, "url": u, "error": "unavailable", "backend": "browser"}
    nav = await browser_cmd("navigate", {"url": u})
    return {
        "ok": bool(nav.get("success")),
        "degraded": not bool(nav.get("success")),
        "url": u,
        "final_url": nav.get("url") or u,
        "backend": "browser",
        "transport": nav.get("_transport"),
        "error": None if nav.get("success") else str(nav.get("error") or "navigate_failed")[:200],
        "raw": {k: v for k, v in nav.items() if k != "_transport"},
    }


async def web_get_text(*, selector: str = "", max_chars: int = 2500) -> dict[str, Any]:
    """Plan API: read visible text from the current page."""
    if not browser_available():
        return {"ok": False, "degraded": True, "text": "", "error": "unavailable", "backend": "browser"}
    gt = await browser_cmd("get-text", {"selector": selector or ""})
    raw = str(gt.get("text") or gt.get("content") or "")
    text = " ".join(raw.split())[: max(200, int(max_chars))]
    return {
        "ok": bool(gt.get("success") and text),
        "degraded": not bool(text),
        "text": text,
        "url": gt.get("url") or "",
        "backend": "browser",
        "transport": gt.get("_transport"),
        "error": None if gt.get("success") else str(gt.get("error") or "get_text_failed")[:200],
    }


async def browser_fetch_text(url: str, *, max_chars: int = 2500) -> dict[str, Any]:
    """Navigate once + get-text. Truncate hard. No snapshot/screenshot."""
    nav = await web_navigate(url)
    if not nav.get("ok"):
        return {
            "ok": False,
            "degraded": True,
            "url": url,
            "text": "",
            "backend": "browser",
            "error": nav.get("error") or "navigate_failed",
        }

    gt = await web_get_text(max_chars=max_chars)
    if not gt.get("ok"):
        return {
            "ok": False,
            "degraded": True,
            "url": url,
            "text": "",
            "backend": "browser",
            "error": gt.get("error") or "get_text_failed",
        }

    return {
        "ok": True,
        "degraded": False,
        "url": url,
        "text": gt.get("text") or "",
        "backend": "browser",
        "final_url": gt.get("url") or nav.get("final_url") or url,
        "transport": gt.get("transport") or nav.get("transport"),
    }
