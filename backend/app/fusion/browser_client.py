"""DJARVIS-compatible browser client for Fusion critics.

Transport preference:
  1) unix socket → browser-daemon (same protocol as DJARVIS browser-cli)
  2) optional subprocess via JARVIS_BROWSER_CLI when socket is down

Public ops used by web_tools / critics / vision:
  web_navigate, web_get_text, browser_fetch_text,
  web_click, web_screenshot
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger("zeus.fusion.browser")

_DEFAULT_SOCK_CANDIDATES = (
    "/run/browser-daemon/daemon.sock",
    "/tmp/browser-daemon/daemon.sock",
    str(Path.home() / ".cache" / "browser-daemon" / "daemon.sock"),
)
_DEFAULT_CLI_CANDIDATES = (
    "/usr/local/bin/browser-cli.py",
    str(Path(__file__).resolve().parents[4] / "DJARVIS" / "browser-service" / "browser-cli.py"),
    str(Path.home() / "Desktop" / "Projects" / "DJARVIS" / "browser-service" / "browser-cli.py"),
)


def _first_existing(paths: tuple[str, ...] | list[str]) -> str:
    for p in paths:
        if p and os.path.exists(p):
            return p
    return (paths[0] if paths else "") or ""


def _settings() -> dict[str, Any]:
    try:
        from app.config import get_settings

        s = get_settings()
        sock_cfg = (getattr(s, "WEB_BROWSER_SOCK", "") or "").strip()
        cli_cfg = (getattr(s, "JARVIS_BROWSER_CLI", "") or "").strip()
        sock = sock_cfg if sock_cfg and os.path.exists(sock_cfg) else _first_existing(
            (sock_cfg, *_DEFAULT_SOCK_CANDIDATES) if sock_cfg else _DEFAULT_SOCK_CANDIDATES
        )
        cli = cli_cfg if cli_cfg and (os.path.isfile(cli_cfg) or shutil.which(cli_cfg)) else _first_existing(
            (cli_cfg, *_DEFAULT_CLI_CANDIDATES) if cli_cfg else _DEFAULT_CLI_CANDIDATES
        )
        return {
            "enabled": bool(getattr(s, "WEB_BROWSER_ENABLED", True)),
            "sock": sock or sock_cfg or _DEFAULT_SOCK_CANDIDATES[0],
            "timeout": max(3.0, min(float(getattr(s, "WEB_BROWSER_TIMEOUT_S", 18) or 18), 45.0)),
            "cli": cli or cli_cfg or _DEFAULT_CLI_CANDIDATES[0],
        }
    except Exception:  # noqa: BLE001
        return {
            "enabled": True,
            "sock": _first_existing(_DEFAULT_SOCK_CANDIDATES) or _DEFAULT_SOCK_CANDIDATES[0],
            "timeout": 18.0,
            "cli": _first_existing(_DEFAULT_CLI_CANDIDATES) or _DEFAULT_CLI_CANDIDATES[0],
        }


def browser_available() -> bool:
    """True only if daemon socket is up, or CLI exists and is executable.

    A non-executable CLI path must not count as available — research would
    waste seconds on Permission denied browser SERP fallbacks.
    """
    cfg = _settings()
    if not cfg["enabled"]:
        return False
    sock = cfg["sock"]
    try:
        if sock and os.path.exists(sock):
            return True
    except Exception:  # noqa: BLE001
        pass
    cli = (cfg.get("cli") or "").strip()
    if not cli:
        return False
    resolved = cli if os.path.isfile(cli) else (shutil.which(cli) or "")
    return bool(resolved and os.access(resolved, os.X_OK))


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
    elif cmd in ("screenshot", "snapshot"):
        path = str(params.get("path") or params.get("file") or "")
        if path:
            argv.extend(["--path", path])
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
    """Navigate once + get-text. Truncate hard."""
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


async def web_click(selector: str) -> dict[str, Any]:
    """Click element by CSS selector (UI verify loop)."""
    sel = (selector or "").strip()
    if not sel:
        return {"ok": False, "degraded": True, "error": "empty_selector", "backend": "browser"}
    if not browser_available():
        return {"ok": False, "degraded": True, "error": "unavailable", "backend": "browser"}
    res = await browser_cmd("click-selector", {"selector": sel})
    return {
        "ok": bool(res.get("success")),
        "degraded": not bool(res.get("success")),
        "selector": sel,
        "backend": "browser",
        "transport": res.get("_transport"),
        "error": None if res.get("success") else str(res.get("error") or "click_failed")[:200],
        "raw": {k: v for k, v in res.items() if k != "_transport"},
    }


async def web_screenshot(*, path: str = "") -> dict[str, Any]:
    """Capture page screenshot for vision role (TZ §3.3 / H6).

    DJARVIS daemon writes PNG to ``path`` and returns ``{success, path, size_bytes}``.
    We read the file into ``image_b64`` for the vision role.
    """
    if not browser_available():
        return {
            "ok": False,
            "degraded": True,
            "error": "unavailable",
            "backend": "browser",
            "image_b64": None,
        }
    out_path = path or f"/tmp/zeus_shot_{os.getpid()}.png"
    params: dict[str, Any] = {"path": out_path}
    res = await browser_cmd("screenshot", params)
    image = (
        res.get("image")
        or res.get("png")
        or res.get("data")
        or res.get("base64")
        or res.get("image_b64")
    )
    if isinstance(image, str) and image.startswith("data:"):
        if "," in image:
            image = image.split(",", 1)[1]
    file_path = str(res.get("path") or out_path or "")
    if (not image or not isinstance(image, str)) and file_path and os.path.isfile(file_path):
        try:
            image = base64.b64encode(Path(file_path).read_bytes()).decode("ascii")
        except OSError as e:
            log.warning("screenshot read fail path=%s err=%s", file_path, e)
    ok = bool(res.get("success") and image)
    return {
        "ok": ok,
        "degraded": not ok,
        "backend": "browser",
        "transport": res.get("_transport"),
        "image_b64": image if isinstance(image, str) and image else None,
        "path": file_path or None,
        "size_bytes": res.get("size_bytes"),
        "error": None if ok else str(res.get("error") or "screenshot_failed")[:200],
        "raw": {
            k: v
            for k, v in res.items()
            if k not in ("_transport", "image", "png", "data", "base64", "image_b64")
        },
    }


async def ui_verify_loop(
    url: str,
    *,
    click_selector: str = "",
) -> dict[str, Any]:
    """Navigate → screenshot → optional click → screenshot again."""
    nav = await web_navigate(url)
    if not nav.get("ok"):
        return {
            "ok": False,
            "degraded": True,
            "error": nav.get("error") or "navigate_failed",
            "shots": [],
        }
    before = await web_screenshot()
    shots = [before]
    clicked = None
    if click_selector:
        clicked = await web_click(click_selector)
        after = await web_screenshot()
        shots.append(after)
    return {
        "ok": bool(before.get("ok")),
        "degraded": not bool(before.get("ok")),
        "url": nav.get("final_url") or url,
        "click": clicked,
        "shots": shots,
        "ui_report": {
            "url": nav.get("final_url") or url,
            "before_ok": bool(before.get("ok")),
            "after_ok": bool(shots[-1].get("ok")) if len(shots) > 1 else None,
            "clicked": bool(clicked and clicked.get("ok")) if clicked else None,
        },
    }
