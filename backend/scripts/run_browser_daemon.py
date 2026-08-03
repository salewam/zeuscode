#!/usr/bin/env python3
"""Start DJARVIS browser-daemon with a Zeus-friendly socket path.

Default sock: /tmp/browser-daemon/daemon.sock (no root /run needed).
Point Zeus at it:
  WEB_BROWSER_SOCK=/tmp/browser-daemon/daemon.sock
  JARVIS_BROWSER_CLI=/path/to/DJARVIS/browser-service/browser-cli.py

Requires: nodriver + Chrome/Chromium on the host.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SOCK = os.environ.get("WEB_BROWSER_SOCK", "/tmp/browser-daemon/daemon.sock")
DJARVIS = Path(
    os.environ.get(
        "DJARVIS_BROWSER_SERVICE",
        str(Path.home() / "Desktop" / "Projects" / "DJARVIS" / "browser-service"),
    )
)


def main() -> int:
    if not (DJARVIS / "browser-daemon.py").is_file():
        print(f"browser-daemon.py not found under {DJARVIS}", file=sys.stderr)
        return 2
    Path(SOCK).parent.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(DJARVIS))
    import browser_daemon as bd  # type: ignore

    bd.SOCK_PATH = SOCK
    # Soften prod paths that may not exist on laptop
    for attr, default in (
        ("SESSIONS_DIR", str(Path(SOCK).parent / "sessions")),
        ("LOG_PATH", str(Path(SOCK).parent / "daemon.log")),
        ("ACTIVE_SESSION_PATH", str(Path(SOCK).parent / "active_session.txt")),
    ):
        if hasattr(bd, attr):
            p = Path(default)
            p.parent.mkdir(parents=True, exist_ok=True)
            if attr.endswith("DIR"):
                p.mkdir(parents=True, exist_ok=True)
            setattr(bd, attr, str(p if attr.endswith("DIR") else p))
    print(f"Starting browser-daemon on {SOCK}", flush=True)
    import asyncio

    asyncio.run(bd.main())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
