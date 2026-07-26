"""Allowlist Test Executor — Layer A (Epic 5 / FR-9/10 / NFR-6).

Only allowlisted pytest-style targets under a Studio workspace may run.
Hot path without workspace → skipped (``tests_failed=None`` / N/A).
``fusion/*`` must not import ``routers.*``.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Binary heads allowed as argv[0] (basename only — no absolute attacker paths)
_ALLOWED_BINARIES = frozenset({"pytest", "python", "python3"})

# pytest flags we explicitly permit (no --rootdir / --override-ini / -c / -p)
_ALLOWED_FLAGS = frozenset(
    {
        "-q",
        "-v",
        "-vv",
        "--tb=line",
        "--tb=short",
        "--tb=no",
        "-x",
        "--maxfail=1",
        "--maxfail=2",
        "--maxfail=3",
        "-k",
        "-m",
    }
)

DEFAULT_PYTEST_TARGETS = (
    "tests",
    "tests/",
    "test",
    "test/",
)

_META_RE = re.compile(r"[;&|`$<>\n\r]")
_SAFE_PATH_RE = re.compile(r"^[\w./\-]+$")
_SAFE_EXPR_RE = re.compile(r"^[\w\-]+$")  # for -k / -m expressions after flag


@dataclass
class ExecutorResult:
    skipped: bool
    reason: str
    exit_code: int | None = None
    tests_failed: bool | None = None  # None = N/A (not run)
    stdout: str = ""
    stderr: str = ""
    cmd: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def default_allowlist() -> tuple[str, ...]:
    raw = (os.environ.get("ZEUS_TEST_EXECUTOR_ALLOWLIST") or "").strip()
    if not raw:
        return DEFAULT_PYTEST_TARGETS
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return tuple(parts) if parts else DEFAULT_PYTEST_TARGETS


def _under_workspace(workspace: Path, rel: str) -> bool:
    """True iff rel resolves strictly inside workspace (no prefix sibling escape)."""
    try:
        ws = workspace.resolve()
        candidate = (ws / rel).resolve()
        return candidate == ws or str(candidate).startswith(str(ws) + os.sep)
    except Exception:  # noqa: BLE001
        return False


def workspace_from_zeus(zeus: dict[str, Any] | None) -> Path | None:
    """Resolve Studio workspace path from zeus prefs; None → hot skip."""
    if not isinstance(zeus, dict):
        return None
    for key in ("workspace_path", "studio_workspace", "workspace"):
        raw = str(zeus.get(key) or "").strip()
        if raw:
            p = Path(raw).expanduser()
            if p.is_dir():
                return p.resolve()
    try:
        uid = int(zeus.get("user_id") or 0)
        pid = int(zeus.get("project_id") or 0)
    except (TypeError, ValueError):
        return None
    if uid > 0 and pid > 0:
        try:
            from app.workspace import workspace_root

            root = workspace_root(uid, pid)
            if root.is_dir():
                return root.resolve()
        except Exception:  # noqa: BLE001
            return None
    return None


def studio_test_requested(zeus: dict[str, Any] | None) -> bool:
    """True when Studio publish / explicit test run is requested."""
    if not isinstance(zeus, dict):
        return False
    if zeus.get("studio_test") or zeus.get("run_tests") or zeus.get("test_target"):
        return True
    if zeus.get("studio_publish") or zeus.get("publish"):
        return True
    return bool(str(zeus.get("workspace_path") or "").strip()) and bool(
        zeus.get("studio") or zeus.get("studio_gate")
    )


def _normalize_target(target: str | None) -> str:
    t = (target or "tests").strip() or "tests"
    while t.startswith("./"):
        t = t[2:]
    return t.lstrip("/")


def is_allowlisted_target(target: str, *, allowlist: tuple[str, ...] | None = None) -> bool:
    """Target must match allowlist entry (exact or prefix under that entry)."""
    allowed = allowlist or default_allowlist()
    t = _normalize_target(target)
    if _META_RE.search(t) or ".." in t.split("/"):
        return False
    if not _SAFE_PATH_RE.match(t.rstrip("/")) and t not in ("", "pytest"):
        return False
    for a in allowed:
        a_norm = _normalize_target(a).rstrip("/")
        t_norm = t.rstrip("/")
        if t_norm == a_norm or t_norm.startswith(a_norm + "/"):
            return True
        if t_norm in ("", "pytest") and a_norm in ("tests", "test"):
            return True
    return False


def build_pytest_cmd(
    target: str,
    *,
    python_bin: str | None = None,
) -> list[str]:
    """Build argv for allowlisted pytest run (no shell)."""
    t = _normalize_target(target)
    if t in ("", "pytest"):
        t = "tests"
    # Only bare interpreter names — never absolute attacker-supplied paths
    py = (python_bin or os.environ.get("ZEUS_TEST_EXECUTOR_PYTHON") or "python").strip()
    if Path(py).name.lower() not in _ALLOWED_BINARIES or "/" in py or "\\" in py:
        py = "python"
    return [py, "-m", "pytest", "-q", "--tb=line", t]


def validate_cmd(cmd: list[str], *, workspace: Path) -> str | None:
    """Return reject reason or None if OK."""
    if not cmd:
        return "empty_cmd"
    # argv[0] must be a bare binary name (no path)
    head = cmd[0]
    if "/" in head or "\\" in head:
        return "binary_path_rejected"
    if Path(head).name.lower() not in _ALLOWED_BINARIES:
        return "binary_not_allowlisted"

    expect_expr_for: str | None = None
    saw_pytest = False
    path_seen = False

    for i, arg in enumerate(cmd):
        if i == 0:
            continue
        if _META_RE.search(arg):
            return "shell_meta_rejected"

        if expect_expr_for:
            if not _SAFE_EXPR_RE.match(arg):
                return "unsafe_expr"
            expect_expr_for = None
            continue

        if arg in ("-m",) and i == 1 and Path(cmd[0]).name.lower() in ("python", "python3"):
            # python -m pytest …
            continue
        if arg == "pytest":
            saw_pytest = True
            continue

        if arg.startswith("-"):
            # flags with values attached: --tb=line already in allow set
            if arg in _ALLOWED_FLAGS:
                if arg in ("-k", "-m"):
                    expect_expr_for = arg
                continue
            # reject absolute-path flag values and unknown flags
            if "=" in arg:
                key, _, val = arg.partition("=")
                if key in ("--tb",) and f"{key}={val}" in _ALLOWED_FLAGS:
                    continue
                if key.startswith("--maxfail") and f"{key}={val}" in _ALLOWED_FLAGS:
                    continue
                return "unsafe_flag"
            return "unsafe_flag"

        # path-like positional
        if ".." in arg.split("/"):
            return "path_escape"
        if not _SAFE_PATH_RE.match(arg):
            return "unsafe_path"
        if not _under_workspace(workspace, arg):
            return "path_escape"
        path_seen = True

    if expect_expr_for:
        return "missing_flag_value"
    if not saw_pytest and "pytest" not in " ".join(cmd):
        return "not_pytest"
    # NFR-6: bare `python -m pytest` without path must still hit default allowlisted target
    if not path_seen:
        return "missing_allowlisted_target"
    return None


def parse_cmd_string(raw: str) -> list[str] | None:
    """Parse a user/studio command string; reject shell forms."""
    text = (raw or "").strip()
    if not text or _META_RE.search(text):
        return None
    try:
        parts = shlex.split(text)
    except ValueError:
        return None
    return parts or None


def _reject(
    reason: str,
    *,
    cmd: list[str] | None = None,
    studio_requested: bool = False,
    meta: dict[str, Any] | None = None,
) -> ExecutorResult:
    """Non-allowlisted / unsafe → reject.

    When Studio explicitly requested tests, rejection is critical (tests_failed=True)
    so Gate cannot silently GREEN (FR-10/11). Hot skip stays N/A.
    """
    return ExecutorResult(
        skipped=True,
        reason=reason,
        tests_failed=True if studio_requested else None,
        cmd=list(cmd or []),
        meta={"layer": "A", **(meta or {})},
    )


def run_test_executor(
    *,
    workspace: Path | None,
    target: str | None = None,
    cmd: list[str] | None = None,
    timeout_s: float | None = None,
    dry_run: bool = False,
    runner: Any | None = None,
    studio_requested: bool = False,
) -> ExecutorResult:
    """Run Layer A tests. Non-allowlisted → reject. No workspace → skip (N/A)."""
    if workspace is None or not Path(workspace).is_dir():
        return ExecutorResult(
            skipped=True,
            reason="no_workspace",
            tests_failed=None,
            meta={"layer": "A"},
        )

    ws = Path(workspace).resolve()
    allow = default_allowlist()
    tgt = _normalize_target(target or "tests")

    if cmd is None:
        if not is_allowlisted_target(tgt, allowlist=allow):
            return _reject(
                "target_not_allowlisted",
                studio_requested=studio_requested,
                meta={"target": tgt, "allowlist": list(allow)},
            )
        argv = build_pytest_cmd(tgt)
    else:
        argv = list(cmd)
        path_args = [
            a
            for a in argv[1:]
            if not a.startswith("-")
            and a not in ("pytest", "-m")
            and Path(a).name.lower() not in _ALLOWED_BINARIES
        ]
        # B2 fix: no path args → force default allowlisted target into cmd
        if not path_args:
            if not is_allowlisted_target("tests", allowlist=allow):
                return _reject(
                    "target_not_allowlisted",
                    cmd=argv,
                    studio_requested=studio_requested,
                )
            argv = list(argv) + ["tests"]
            path_args = ["tests"]
        if not any(is_allowlisted_target(a, allowlist=allow) for a in path_args):
            return _reject(
                "target_not_allowlisted",
                cmd=argv,
                studio_requested=studio_requested,
                meta={"target": path_args},
            )

    reject = validate_cmd(argv, workspace=ws)
    if reject:
        return _reject(
            reject,
            cmd=argv,
            studio_requested=studio_requested,
        )

    if dry_run:
        return ExecutorResult(
            skipped=False,
            reason="dry_run",
            exit_code=0,
            tests_failed=False,
            cmd=argv,
            meta={"layer": "A", "dry_run": True},
        )

    timeout = timeout_s
    if timeout is None:
        try:
            timeout = float(os.environ.get("ZEUS_TEST_EXECUTOR_TIMEOUT") or "120")
        except ValueError:
            timeout = 120.0

    run = runner or subprocess.run
    try:
        proc = run(
            argv,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        rc = getattr(proc, "returncode", 1)
        code = int(rc) if rc is not None else 1
        out = str(getattr(proc, "stdout", "") or "")
        err = str(getattr(proc, "stderr", "") or "")
        failed = code != 0
        return ExecutorResult(
            skipped=False,
            reason="ok" if not failed else "tests_failed",
            exit_code=code,
            tests_failed=failed,
            stdout=out[-4000:],
            stderr=err[-4000:],
            cmd=argv,
            meta={"layer": "A", "cwd": str(ws)},
        )
    except subprocess.TimeoutExpired:
        return ExecutorResult(
            skipped=False,
            reason="timeout",
            exit_code=124,
            tests_failed=True,
            cmd=argv,
            meta={"layer": "A"},
        )
    except Exception as e:  # noqa: BLE001
        return ExecutorResult(
            skipped=False,
            reason=f"executor_error:{type(e).__name__}",
            exit_code=1,
            tests_failed=True,
            cmd=argv,
            stderr=str(e)[:400],
            meta={"layer": "A"},
        )


def executor_signal_for_gate(result: ExecutorResult) -> bool | None:
    """Map executor result → GateSignals.tests_failed (None = N/A)."""
    if result.skipped and result.tests_failed is not True:
        return None
    if result.tests_failed is None:
        return None
    return bool(result.tests_failed)


def run_layer_a_for_request(
    zeus: dict[str, Any] | None,
    *,
    runner: Any | None = None,
    dry_run: bool = False,
) -> ExecutorResult:
    """Studio/workspace Layer A entry. Hot without workspace → skip (FR-9/10)."""
    ws = workspace_from_zeus(zeus)
    if ws is None:
        return ExecutorResult(
            skipped=True,
            reason="no_workspace",
            tests_failed=None,
            meta={"layer": "A"},
        )
    requested = studio_test_requested(zeus)
    if not requested:
        return ExecutorResult(
            skipped=True,
            reason="hot_path_no_studio_test",
            tests_failed=None,
            meta={"layer": "A", "workspace": str(ws)},
        )
    z = zeus if isinstance(zeus, dict) else {}
    raw_cmd = z.get("test_cmd") or z.get("studio_test_cmd")
    cmd = parse_cmd_string(str(raw_cmd)) if raw_cmd else None
    if raw_cmd and cmd is None:
        return _reject("shell_meta_rejected", studio_requested=True)
    target = str(z.get("test_target") or z.get("studio_pytest") or "tests")
    return run_test_executor(
        workspace=ws,
        target=target,
        cmd=cmd,
        dry_run=dry_run,
        runner=runner,
        studio_requested=True,
    )
