"""Evidence gate for Studio — self-report is not proof.

Inspired by Codex CLI Evidence Runner (receipt + safety gate + score)
and Aura's separate design-reviewer: deterministic checks first, then
optional LLM critic. Never treat «готово» as acceptance.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

VERIFY_SH = (
    Path(__file__).resolve().parent / "agent_skills" / "frontend" / "scripts" / "verify.sh"
)
VERIFY_BACKEND_SH = (
    Path(__file__).resolve().parent / "agent_skills" / "backend" / "scripts" / "verify.sh"
)
VERIFY_TESTS_SH = (
    Path(__file__).resolve().parent / "agent_skills" / "tests" / "scripts" / "verify.sh"
)
VERIFY_DESIGN_SH = (
    Path(__file__).resolve().parent / "agent_skills" / "design" / "scripts" / "verify.sh"
)

# --- deterministic heuristics -------------------------------------------------

_DIV_ONCLICK = re.compile(r"<div[^>]*(onclick|onClick)\s*=", re.I)
_OUTLINE_NONE = re.compile(r"outline\s*:\s*(none|0)\b", re.I)
_FOCUS_VISIBLE = re.compile(r"focus-visible", re.I)
# Match real AI palette usage — NOT comments like "No Indigo" / "Anti-Indigo"
_AI_AESTHETIC = re.compile(
    r"("
    r"#7[cC]3[aA][eE][dD]|#8[bB]5[cC][fF]6|#6366[fF]1|#4[fF]46[eE]5|#[aA]78[bB][fF][aA]|"
    r"font-family\s*:\s*['\"]?Inter\b|"
    r"linear-gradient\([^)]*(violet|purple|indigo|#7[cC]3|#8[bB]5|#6366|#4[fF]46)|"
    r":\s*(?:purple|violet|indigo)\b|"
    r"--[\w-]+\s*:\s*[^;{\n]*(?:#7[cC]3[aA][eE][dD]|#8[bB]5[cC][fF]6|#6366[fF]1|#4[fF]46[eE]5)"
    r")",
    re.I,
)
_COMMENT_CSS = re.compile(r"/\*.*?\*/", re.S)
_COMMENT_HTML = re.compile(r"<!--.*?-->", re.S)


def _strip_comments(body: str) -> str:
    body = _COMMENT_CSS.sub(" ", body or "")
    body = _COMMENT_HTML.sub(" ", body)
    return body
_SECRET = re.compile(
    r"(sk-[a-zA-Z0-9]{20,}|api[_-]?key\s*[:=]\s*['\"][a-zA-Z0-9]{16,})",
    re.I,
)
_LOREM = re.compile(r"lorem\s+ipsum", re.I)
# Meta / egg marketing copy — presentation-about-presentation, not product facts
_EGG_COPY = re.compile(
    r"("
    r"три\s+сильн\w*\s+вещ|"
    r"вс[её]\s+по\s+делу|"
    r"на\s+все\s+случа[ия]|"
    r"не\s+меню\s*[«\"'].{0,40}а\s+три|"
    r"честн\w*\s+вкус|"
    r"куда\s+хочется\s+вернуться|"
    r"атмосфер\w*\s+уют|"
    r"премиальн\w*\s+опыт|"
    r"без\s+лишнего\s+шума|"  # often paired with empty structure talk
    r"не\s+список\s+фич|"
    r"не\s+просто\s+лендинг"
    r")",
    re.I,
)
_SQL_FSTRING = re.compile(
    r"""f['"](?:SELECT|INSERT|UPDATE|DELETE)|['"](?:SELECT|INSERT|UPDATE|DELETE).*\.format\(""",
    re.I,
)
_BARE_EXCEPT = re.compile(r"except\s*:\s*(?:$|#|pass)", re.M)
_RESPONSE_MODEL_DICT = re.compile(r"response_model\s*=\s*dict\b")
_PASSWORD_RETURN = re.compile(
    r"""return\s*\{[^}]*['"]password['"]|print\([^)]*(?:password|token|authorization)""",
    re.I,
)


def _finding(
    severity: str, code: str, message: str, path: str | None = None
) -> dict[str, Any]:
    return {
        "severity": severity,  # critical | major | minor | info
        "code": code,
        "message": message,
        "path": path,
        "source": "gate",
    }


def scan_artifacts(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic gates over Studio artifacts. Independent of model self-report."""
    findings: list[dict[str, Any]] = []
    if not artifacts:
        findings.append(
            _finding(
                "critical",
                "no_artifacts",
                "Нет артефактов с path= — только текст агента. Self-report без файлов.",
            )
        )
        return findings

    has_frontend = False
    has_html_entry = False
    for a in artifacts:
        path = (a.get("path") or "").strip()
        body = a.get("content") or ""
        body_code = _strip_comments(body)
        role = a.get("role") or ""
        if path.startswith("/src/frontend") or role == "frontend":
            has_frontend = True
        if path.endswith(".html") or path.endswith("index.html"):
            has_html_entry = True

        if not path.startswith("/"):
            findings.append(
                _finding("major", "bad_path", f"Путь без ведущего /: {path}", path)
            )

        # Role must write under its own /src/<role>/ prefix
        role_prefix = {
            "frontend": "/src/frontend/",
            "backend": "/src/backend/",
            "design": "/src/design/",
            "tests": "/src/tests/",
        }.get(role)
        if role_prefix and path.startswith("/src/") and not path.startswith(role_prefix):
            findings.append(
                _finding(
                    "major",
                    "role_path_drift",
                    f"Роль {role} положила файл вне {role_prefix}: {path}",
                    path,
                )
            )
        # Orphan / wrong top-level dumps
        if path.startswith("/src/") and not any(
            path.startswith(p)
            for p in (
                "/src/frontend/",
                "/src/backend/",
                "/src/design/",
                "/src/tests/",
            )
        ):
            findings.append(
                _finding(
                    "major",
                    "unknown_src_prefix",
                    f"Путь вне зон Studio (/src/frontend|backend|design|tests): {path}",
                    path,
                )
            )

        if _SECRET.search(body_code):
            findings.append(
                _finding("critical", "secret_leak", "Похоже на секрет в артефакте", path)
            )

        if _DIV_ONCLICK.search(body_code):
            findings.append(
                _finding(
                    "critical",
                    "div_onclick",
                    "div onclick — нужен button/a",
                    path,
                )
            )

        if path.endswith(".css") or "<style" in body.lower():
            pass  # outline checked cross-file below

        if _AI_AESTHETIC.search(body_code):
            is_design = path.startswith("/src/design") or role == "design"
            findings.append(
                _finding(
                    "critical" if is_design else "major",
                    "ai_aesthetic",
                    "AI-aesthetic: purple/indigo/violet/Inter/AI-hex — бан anti-patterns",
                    path,
                )
            )

        if _LOREM.search(body_code):
            findings.append(
                _finding("minor", "lorem", "Lorem ipsum в сдаваемом UI", path)
            )

        if path.endswith((".html", ".md", ".css")) or role in ("frontend", "design", "docs"):
            # Strip tags roughly for HTML so we match visible copy
            copy_blob = re.sub(r"<[^>]+>", " ", body_code)
            if _EGG_COPY.search(copy_blob):
                findings.append(
                    _finding(
                        "major",
                        "egg_copy",
                        "Яичный/мета-копирайт (три сильные вещи / всё по делу / "
                        "честный вкус…) — пиши факты: цена, SKU, часы, адрес",
                        path,
                    )
                )

        # Empty hero void: tall hero / header without real media (img or url photo)
        if path.endswith((".html", ".css")) or role == "frontend":
            tall = re.search(
                r"min-height\s*:\s*(?:[89]\d|1\d{2}|[7-9]\d)vh|"
                r"min-height\s*:\s*min\(\s*(?:9\d|8\d)vh",
                body_code,
                re.I,
            )
            has_media = bool(
                re.search(
                    r"<img\b|background(?:-image)?\s*:\s*[^;]*url\s*\(|"
                    r"hero__img|hero__media|object-fit\s*:\s*cover",
                    body_code,
                    re.I,
                )
            )
            looks_hero = bool(
                re.search(r"\.hero\b|class=[\"'][^\"']*hero|header\.hero|<header\b", body_code, re.I)
            )
            if looks_hero and tall and not has_media:
                findings.append(
                    _finding(
                        "major",
                        "empty_hero",
                        "Пустой hero ≥70vh без фото/сцены — нужен full-bleed media, "
                        "не gradient-дырка",
                        path,
                    )
                )

        if path.endswith(".html") and re.search(r"<input\b", body, re.I):
            if not re.search(r"<label\b", body, re.I):
                findings.append(
                    _finding(
                        "major",
                        "input_no_label",
                        "Есть input без label",
                        path,
                    )
                )

        # --- backend / tests safety gates ---
        is_code = path.endswith(".py") or "python" in (a.get("language") or "").lower()
        is_backend = path.startswith("/src/backend") or role == "backend"
        is_tests = path.startswith("/src/tests") or role == "tests"
        if is_code and (is_backend or is_tests):
            if _SQL_FSTRING.search(body_code):
                findings.append(
                    _finding(
                        "critical",
                        "sql_fstring",
                        "SQL через f-string/format — инъекция",
                        path,
                    )
                )
            if is_tests and re.search(r"@pytest\.mark\.skip|pytest\.skip\(", body_code):
                findings.append(
                    _finding(
                        "major",
                        "pytest_skip",
                        "pytest skip запрещён в Studio tests",
                        path,
                    )
                )
            if is_backend:
                if _BARE_EXCEPT.search(body_code):
                    findings.append(
                        _finding(
                            "major",
                            "bare_except",
                            "Голый except: — лови конкретные исключения",
                            path,
                        )
                    )
                if _RESPONSE_MODEL_DICT.search(body_code):
                    findings.append(
                        _finding(
                            "major",
                            "response_model_dict",
                            "response_model=dict — нужен Pydantic Out",
                            path,
                        )
                    )
                if _PASSWORD_RETURN.search(body_code):
                    findings.append(
                        _finding(
                            "critical",
                            "secret_in_output",
                            "password/token в print/return",
                            path,
                        )
                    )

    has_backend = any(
        (a.get("path") or "").startswith("/src/backend") or a.get("role") == "backend"
        for a in artifacts
    )
    if has_backend:
        py_blob = "\n".join(
            (a.get("content") or "")
            for a in artifacts
            if (a.get("path") or "").endswith(".py")
            or (a.get("path") or "").startswith("/src/backend")
        )
        if py_blob and not re.search(r"APIRouter|BaseModel|HTTPException", py_blob):
            findings.append(
                _finding(
                    "major",
                    "backend_not_api",
                    "Backend-артефакты без APIRouter/BaseModel/HTTPException",
                )
            )
        if re.search(r"@router\.(get|patch|put|delete)\(['\"][^'\"]*\{", py_blob):
            if not re.search(r"user_id|HTTP_404|404|Not found|not found", py_blob, re.I):
                findings.append(
                    _finding(
                        "major",
                        "no_ownership_signal",
                        "Path-id роуты без явного 404/ownership",
                    )
                )

    if has_frontend and not has_html_entry:
        findings.append(
            _finding(
                "info",
                "no_html_entry",
                "Frontend без .html entry — ок, если патч; иначе нужен index.html",
            )
        )

    # Cross-file: any outline kill without any focus-visible in CSS set
    css_bodies = [
        _strip_comments(a.get("content") or "")
        for a in artifacts
        if (a.get("path") or "").endswith(".css") or "<style" in (a.get("content") or "").lower()
    ]
    if css_bodies:
        joined = "\n".join(css_bodies)
        if _OUTLINE_NONE.search(joined) and not _FOCUS_VISIBLE.search(joined):
            if not any(f.get("code") == "outline_no_focus" for f in findings):
                findings.append(
                    _finding(
                        "major",
                        "outline_no_focus",
                        "В CSS-наборе есть outline:none/0 и нигде нет :focus-visible",
                    )
                )

    findings.extend(_contract_drift_findings(artifacts))
    findings.extend(_token_ssot_findings(artifacts))
    findings.extend(_contract_lock_findings(artifacts))
    return findings


def extract_prelock_from_task(task: str) -> dict[str, Any] | None:
    """Draft API contract from the user prompt — shared by FE∥BE before backend hardens it."""
    text = task or ""
    if not text.strip():
        return None
    endpoints: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in re.finditer(
        r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/api/[a-zA-Z0-9_/{}\-]+)",
        text,
        re.I,
    ):
        key = (m.group(1).upper(), m.group(2))
        if key not in seen:
            seen.add(key)
            endpoints.append({"method": key[0], "path": key[1]})
    # Bare /api/... paths (infer method from nearby verbs or default GET)
    for m in re.finditer(r"(?<![/\w])(/api/[a-zA-Z0-9_/{}\-]+)", text):
        path = m.group(1)
        start = max(0, m.start() - 24)
        window = text[start : m.start()].upper()
        method = "GET"
        for verb in ("DELETE", "PATCH", "PUT", "POST", "GET"):
            if verb in window:
                method = verb
                break
        else:
            # task-level hints
            if re.search(r"\b(созда|create|post)\b", text, re.I) and path.rstrip(
                "/"
            ).count("/") <= 3:
                method = "POST"
        key = (method, path)
        if key not in seen and not any(e["path"] == path for e in endpoints):
            seen.add(key)
            endpoints.append({"method": method, "path": path})

    fields: list[str] = []
    for m in re.finditer(r"\{([a-zA-Z0-9_,:\s\"']+)\}", text):
        for part in m.group(1).split(","):
            name = part.strip().strip("\"'").split(":")[0].strip()
            if name.isidentifier() and name not in fields:
                fields.append(name)
    # title:str patterns outside braces
    for m in re.finditer(r"\b([a-z_][a-z0-9_]*)\s*:\s*(str|int|bool|float)\b", text, re.I):
        name = m.group(1)
        if name not in fields:
            fields.append(name)

    auth = bool(
        re.search(r"\b(auth|bearer|jwt|oauth|Depends|get_current_user)\b", text, re.I)
    )
    if not endpoints and not fields:
        return None
    return {
        "version": 1,
        "source": "task_prelock",
        "endpoints": endpoints[:20],
        "fields": fields[:24],
        "auth_required": auth,
        "paths": sorted({e["path"] for e in endpoints})[:20],
    }


def merge_contracts(
    pre: dict[str, Any] | None,
    hard: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Backend hardens paths; union endpoints/fields with task prelock; auth OR."""
    if hard and not pre:
        return {**hard, "source": hard.get("source") or "backend"}
    if pre and not hard:
        return pre
    if not pre and not hard:
        return None
    assert pre is not None and hard is not None
    endpoints: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    # Backend first (authoritative), then fill gaps from prelock
    for e in (hard.get("endpoints") or []) + (pre.get("endpoints") or []):
        method = (e.get("method") or "").upper()
        path = e.get("path") or ""
        key = (method, path)
        if not path or key in seen:
            continue
        # Skip ultra-relative bare "/" if we already have absolute /api paths
        if path == "/" and any(p.startswith("/api/") for _, p in seen):
            continue
        seen.add(key)
        endpoints.append({"method": method, "path": path})
    fields: list[str] = []
    for f in (hard.get("fields") or []) + (pre.get("fields") or []):
        if f and f not in fields:
            fields.append(f)
    paths = sorted({e["path"] for e in endpoints})
    return {
        "version": 1,
        "source": "backend+task",
        "endpoints": endpoints[:20],
        "fields": fields[:24],
        "auth_required": bool(hard.get("auth_required") or pre.get("auth_required")),
        "paths": paths[:20],
        "router_prefixes": hard.get("router_prefixes") or [],
    }


def extract_locked_contract(artifacts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Machine-readable API contract from backend artifacts (SSoT for tests/FE/synth)."""
    be = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/backend")
        or a.get("role") == "backend"
    ]
    if not be:
        return None
    blob = "\n".join(a.get("content") or "" for a in be)
    # FastAPI: router = APIRouter(prefix="/api/notes")
    prefixes: list[str] = []
    for m in re.finditer(
        r"""APIRouter\s*\([^)]*prefix\s*=\s*['"]([^'"]+)['"]""",
        blob,
    ):
        prefixes.append(m.group(1).rstrip("/"))
    if not prefixes:
        prefixes = [""]

    def _abs(path: str) -> str:
        if path.startswith("/api/"):
            return path
        for pref in prefixes:
            if not pref:
                continue
            if path == "/":
                return pref
            if path.startswith("/"):
                return pref + path
            return f"{pref}/{path}"
        return path if path.startswith("/") else f"/{path}"

    endpoints: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in re.finditer(
        r"""@router\.(get|post|put|patch|delete)\(\s*['"]([^'"]+)['"]""",
        blob,
        re.I,
    ):
        method, path = m.group(1).upper(), _abs(m.group(2))
        key = (method, path)
        if key not in seen:
            seen.add(key)
            endpoints.append({"method": method, "path": path})
    for m in re.finditer(
        r"""\.(get|post|put|patch|delete)\(\s*['"](/api/[^'"]+)['"]""",
        blob,
        re.I,
    ):
        method, path = m.group(1).upper(), m.group(2)
        key = (method, path)
        if key not in seen:
            seen.add(key)
            endpoints.append({"method": method, "path": path})
    fields: set[str] = set()
    for block in re.findall(
        r"class\s+\w+(?:\([^)]*\))?:\n((?:[ \t]+.+\n)+)",
        blob,
    ):
        if "BaseModel" not in blob and ":" not in block:
            continue
        for fm in _FIELD_RE.finditer(block):
            name = fm.group(1)
            if name not in ("model_config", "Config", "orm_mode"):
                fields.add(name)
    # Prefer In/Out class fields when present
    fields_io: set[str] = set()
    for block in re.findall(
        r"class\s+\w*(?:In|Out|Create|Update|Response)\w*\([^)]*\):\n((?:[ \t]+.+\n)+)",
        blob,
    ):
        for fm in _FIELD_RE.finditer(block):
            name = fm.group(1)
            if name not in ("model_config", "Config"):
                fields_io.add(name)
    use_fields = sorted(fields_io or fields)
    auth = bool(
        re.search(
            r"Depends\(|get_current_user|HTTPBearer|Authorization|oauth2",
            blob,
            re.I,
        )
    )
    if not endpoints and not use_fields:
        return None
    return {
        "version": 1,
        "source": "backend",
        "endpoints": endpoints[:20],
        "fields": use_fields[:24],
        "auth_required": auth,
        "paths": sorted({e["path"] for e in endpoints})[:20],
        "router_prefixes": [p for p in prefixes if p][:8],
    }


def format_contract_lock(contract: dict[str, Any] | None) -> str:
    if not contract:
        return ""
    src = contract.get("source") or "lock"
    lines = [
        f"## Locked API contract ({src} — не выдумывай другие path/поля)"
    ]
    for e in contract.get("endpoints") or []:
        lines.append(f"- {e.get('method')} `{e.get('path')}`")
    fields = contract.get("fields") or []
    if fields:
        lines.append("- fields: " + ", ".join(f"`{f}`" for f in fields))
    lines.append(f"- auth_required: {bool(contract.get('auth_required'))}")
    if src == "task_prelock":
        lines.append(
            "- Это черновик из задачи (до backend). FE/BE держитесь его; "
            "backend может уточнить, tests потом следуют hardened lock."
        )
    else:
        lines.append(
            "Tests/frontend: копируй path и поля 1:1. Breaking change — только явно в Мышлении."
        )
    return "\n".join(lines)


def _contract_lock_findings(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """FE/tests must not invent alternate /api paths when backend contract exists."""
    contract = extract_locked_contract(artifacts)
    if not contract or not (contract.get("paths") or contract.get("endpoints")):
        return []
    locked_bases: list[str] = []
    for p in contract.get("paths") or []:
        base = re.sub(r"\{[^}]+\}", "", p).rstrip("/")
        if base:
            locked_bases.append(base)
    if not locked_bases:
        return []

    findings: list[dict[str, Any]] = []
    fe_te = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith(("/src/frontend", "/src/tests"))
        or a.get("role") in ("frontend", "tests")
    ]
    blob = "\n".join(a.get("content") or "" for a in fe_te)
    if not blob:
        return []
    used = set(re.findall(r"['\"](/api/[a-zA-Z0-9_/{}\-]+)['\"]", blob))
    if not used:
        return []
    foreign = []
    for u in used:
        ub = re.sub(r"\{[^}]+\}", "", u).rstrip("/")
        if not any(ub.startswith(lb) or lb.startswith(ub) for lb in locked_bases):
            foreign.append(u)
    if foreign and len(foreign) >= len(used):
        findings.append(
            _finding(
                "major",
                "contract_lock_violation",
                "FE/tests используют /api path вне backend contract: "
                + ", ".join(sorted(foreign)[:4]),
            )
        )
    return findings


def _token_ssot_findings(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Design tokens.css is SSoT — frontend must import or reuse vars, not invent a parallel palette."""
    design_tokens = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/design/")
        and (a.get("path") or "").endswith("tokens.css")
    ]
    fe_css = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/frontend/")
        and (
            (a.get("path") or "").endswith(".css")
            or "<style" in (a.get("content") or "").lower()
        )
    ]
    if not design_tokens or not fe_css:
        return []
    design_blob = "\n".join(a.get("content") or "" for a in design_tokens)
    fe_blob = "\n".join(a.get("content") or "" for a in fe_css)
    design_vars = set(re.findall(r"--([a-zA-Z][\w-]*)\s*:", design_blob))
    if not design_vars:
        return []
    if re.search(r"@import[^;]*tokens\.css", fe_blob, re.I):
        return []
    used = set(re.findall(r"var\(\s*--([a-zA-Z][\w-]*)", fe_blob))
    shared = design_vars & used
    fe_defines = set(re.findall(r"--([a-zA-Z][\w-]*)\s*:", fe_blob))
    # Parallel :root palette with almost no shared vars → drift
    if ":root" in fe_blob and len(shared) < 2 and len(fe_defines) >= 3:
        return [
            _finding(
                "major",
                "token_ssot_ignored",
                "Есть /src/design/tokens.css, но frontend styles не @import и почти не используют design-vars — параллельная палитра",
            )
        ]
    return []


_API_PATH_RE = re.compile(
    r"""(?:@router\.(?:get|post|put|patch|delete)\(\s*['"]([^'"]+)['"]|/api/[a-zA-Z0-9_/{}\-]+)""",
    re.I,
)
_FIELD_RE = re.compile(r"(?m)^\s*([a-z_][a-z0-9_]*)\s*:\s*", re.I)


def _contract_drift_findings(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """When backend+tests both present, tests must mention backend API paths / key fields."""
    be = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/backend") or a.get("role") == "backend"
    ]
    te = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/tests") or a.get("role") == "tests"
    ]
    if not be or not te:
        return []

    be_blob = "\n".join(a.get("content") or "" for a in be)
    te_blob = "\n".join(a.get("content") or "" for a in te)
    paths: set[str] = set()
    for m in re.finditer(
        r"""@router\.(?:get|post|put|patch|delete)\(\s*['"]([^'"]+)['"]""",
        be_blob,
        re.I,
    ):
        paths.add(m.group(1))
    for m in re.finditer(r"['\"](/api/[a-zA-Z0-9_/{}\-]+)['\"]", be_blob):
        paths.add(m.group(1))
    # normalize {id} variants
    path_needles = []
    for p in paths:
        base = re.sub(r"\{[^}]+\}", "", p).rstrip("/")
        if base:
            path_needles.append(base)

    findings: list[dict[str, Any]] = []
    if path_needles:
        missing = [p for p in path_needles if p not in te_blob]
        if len(missing) == len(path_needles):
            findings.append(
                _finding(
                    "major",
                    "contract_path_drift",
                    "Tests не ссылаются ни на один backend path из "
                    + ", ".join(sorted(path_needles)[:4]),
                )
            )

    # Key In/Out field names from Pydantic classes
    fields: set[str] = set()
    for block in re.findall(
        r"class\s+\w*(?:In|Out|Create|Update)\w*\([^)]*\):\n((?:[ \t]+.+\n)+)",
        be_blob,
    ):
        for fm in _FIELD_RE.finditer(block):
            name = fm.group(1)
            if name not in ("model_config", "Config"):
                fields.add(name)
    interesting = {f for f in fields if f in ("title", "body", "email", "name", "status", "content")}
    if interesting:
        missing_f = [f for f in interesting if f"'{f}'" not in te_blob and f'"{f}"' not in te_blob and f"[{f}]" not in te_blob and f".{f}" not in te_blob]
        if len(missing_f) == len(interesting) and interesting:
            findings.append(
                _finding(
                    "major",
                    "contract_field_drift",
                    "Tests не ассердят ключевые поля backend: "
                    + ", ".join(sorted(interesting)[:6]),
                )
            )

    # Vacuous asserts: tautology assert N==N without HTTP client usage
    if te_blob and not re.search(r"\b(status_code|TestClient|httpx|AsyncClient|client\.(get|post|put|patch|delete))\b", te_blob):
        if re.search(r"assert\s+(\d+)\s*==\s*\1\b", te_blob):
            findings.append(
                _finding(
                    "major",
                    "vacuous_assert",
                    "Tests с tautology assert N==N без TestClient/status_code — нет пруфа контракта",
                )
            )
    return findings


def run_frontend_verify(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run scripts/verify.sh on frontend artifacts if present. Adds gate findings."""
    fe = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/frontend")
        or a.get("role") == "frontend"
    ]
    if not fe or not VERIFY_SH.is_file():
        return []
    findings: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "src" / "frontend"
            for a in fe:
                rel = (a.get("path") or "").replace("/src/frontend/", "").lstrip("/")
                if not rel:
                    continue
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(a.get("content") or "", encoding="utf-8")
            if not (root / "index.html").exists():
                htmls = list(root.rglob("*.html"))
                if htmls:
                    (root / "index.html").write_text(
                        htmls[0].read_text(encoding="utf-8"), encoding="utf-8"
                    )
            proc = subprocess.run(
                ["bash", str(VERIFY_SH), str(root)],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if proc.returncode != 0:
                tail = (proc.stdout + "\n" + proc.stderr).strip().splitlines()
                msg = "; ".join(x for x in tail if x.startswith("FAIL:"))[:500]
                findings.append(
                    _finding(
                        "major",
                        "verify_sh",
                        msg or "frontend verify.sh FAILED",
                    )
                )
    except Exception as e:  # noqa: BLE001
        findings.append(
            _finding("info", "verify_sh_error", f"verify.sh не запустился: {e}")
        )
    return findings


def run_backend_verify(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run backend scripts/verify.sh on /src/backend artifacts if present."""
    be = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/backend")
        or a.get("role") == "backend"
    ]
    if not be or not VERIFY_BACKEND_SH.is_file():
        return []
    findings: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "src" / "backend"
            for a in be:
                rel = (a.get("path") or "").replace("/src/backend/", "").lstrip("/")
                if not rel:
                    continue
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(a.get("content") or "", encoding="utf-8")
            if not any(root.rglob("*.py")):
                return []
            proc = subprocess.run(
                ["bash", str(VERIFY_BACKEND_SH), str(root)],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if proc.returncode != 0:
                tail = (proc.stdout + "\n" + proc.stderr).strip().splitlines()
                msg = "; ".join(x for x in tail if x.startswith("FAIL:"))[:500]
                findings.append(
                    _finding(
                        "major",
                        "backend_verify_sh",
                        msg or "backend verify.sh FAILED",
                    )
                )
    except Exception as e:  # noqa: BLE001
        findings.append(
            _finding("info", "backend_verify_sh_error", f"backend verify.sh: {e}")
        )
    return findings


def run_tests_verify(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run tests scripts/verify.sh on /src/tests artifacts if present."""
    te = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/tests") or a.get("role") == "tests"
    ]
    if not te or not VERIFY_TESTS_SH.is_file():
        return []
    findings: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "src" / "tests"
            for a in te:
                rel = (a.get("path") or "").replace("/src/tests/", "").lstrip("/")
                if not rel:
                    continue
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(a.get("content") or "", encoding="utf-8")
            if not any(root.rglob("*.py")):
                return []
            proc = subprocess.run(
                ["bash", str(VERIFY_TESTS_SH), str(root)],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if proc.returncode != 0:
                tail = (proc.stdout + "\n" + proc.stderr).strip().splitlines()
                msg = "; ".join(x for x in tail if x.startswith("FAIL:"))[:500]
                findings.append(
                    _finding(
                        "major",
                        "tests_verify_sh",
                        msg or "tests verify.sh FAILED",
                    )
                )
    except Exception as e:  # noqa: BLE001
        findings.append(
            _finding("info", "tests_verify_sh_error", f"tests verify.sh: {e}")
        )
    return findings


def run_design_verify(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run design scripts/verify.sh on /src/design artifacts if present."""
    de = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/design") or a.get("role") == "design"
    ]
    if not de or not VERIFY_DESIGN_SH.is_file():
        return []
    findings: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "src" / "design"
            for a in de:
                rel = (a.get("path") or "").replace("/src/design/", "").lstrip("/")
                if not rel:
                    continue
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(a.get("content") or "", encoding="utf-8")
            if not any(root.rglob("*")):
                return []
            proc = subprocess.run(
                ["bash", str(VERIFY_DESIGN_SH), str(root)],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if proc.returncode != 0:
                tail = (proc.stdout + "\n" + proc.stderr).strip().splitlines()
                msg = "; ".join(x for x in tail if x.startswith("FAIL:"))[:500]
                findings.append(
                    _finding(
                        "major",
                        "design_verify_sh",
                        msg or "design verify.sh FAILED",
                    )
                )
    except Exception as e:  # noqa: BLE001
        findings.append(
            _finding("info", "design_verify_sh_error", f"design verify.sh: {e}")
        )
    return findings


def _frontend_srcdoc(arts: list[dict[str, Any]]) -> str | None:
    """Inline HTML+CSS+JS for Playwright set_content (no network)."""
    by_path = {(a.get("path") or ""): a for a in arts}
    html = (by_path.get("/src/frontend/index.html") or {}).get("content") or ""
    if not html:
        for a in arts:
            if (a.get("path") or "").endswith(".html"):
                html = a.get("content") or ""
                break
    if not html.strip():
        return None
    css = "\n".join(
        a.get("content") or ""
        for a in arts
        if (a.get("path") or "").endswith(".css") or a.get("language") == "css"
    )
    js = "\n".join(
        a.get("content") or ""
        for a in arts
        if (a.get("path") or "").endswith(".js")
        or a.get("language") in ("js", "javascript")
    )
    html = re.sub(r"<link[^>]+href=[\"']\./[^\"']+\.css[\"'][^>]*>", "", html, flags=re.I)
    html = re.sub(
        r"<script[^>]+src=[\"']\./[^\"']+\.js[\"'][^>]*>\s*</script>",
        "",
        html,
        flags=re.I,
    )
    if css:
        if re.search(r"</head>", html, re.I):
            html = re.sub(r"</head>", f"<style>\n{css}\n</style></head>", html, count=1, flags=re.I)
        else:
            html = f"<style>{css}</style>" + html
    if js:
        if re.search(r"</body>", html, re.I):
            html = re.sub(
                r"</body>",
                f"<script type=\"module\">\n{js}\n</script></body>",
                html,
                count=1,
                flags=re.I,
            )
        else:
            html += f'<script type="module">\n{js}\n</script>'
    return html


def _browser_smoke_sync(fe: list[dict[str, Any]], srcdoc: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [
            _finding(
                "info",
                "browser_skip",
                "playwright не установлен — browser smoke пропущен",
            )
        ]
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("pageerror", lambda err: errors.append(str(err)[:200]))
            page.set_content(srcdoc, wait_until="domcontentloaded")
            n_btn = page.locator("button, a[href], input, select, textarea").count()
            if n_btn < 1:
                findings.append(
                    _finding(
                        "major",
                        "browser_no_interactive",
                        "В DOM нет button/a/input — UI не интерактивен",
                    )
                )
            else:
                first = page.locator("button, a[href], input, select, textarea").first
                try:
                    first.focus(timeout=2000)
                except Exception as e:  # noqa: BLE001
                    findings.append(
                        _finding(
                            "major",
                            "browser_focus_fail",
                            f"Не удалось сфокусировать контроль: {e}",
                        )
                    )
                btn = page.locator("button").first
                if btn.count() > 0:
                    try:
                        btn.click(timeout=2000, no_wait_after=True)
                    except Exception as e:  # noqa: BLE001
                        findings.append(
                            _finding(
                                "minor",
                                "browser_click_warn",
                                f"Click button: {e}",
                            )
                        )
            if errors:
                sandbox = []
                real = []
                for err in errors:
                    low = err.lower()
                    # about:blank / srcdoc: location.href and similar are not app bugs
                    if (
                        "not a valid url" in low
                        or "failed to set the 'href' property" in low
                        or "navigation" in low
                        and "cannot" in low
                    ):
                        sandbox.append(err)
                    else:
                        real.append(err)
                if real:
                    findings.append(
                        _finding(
                            "critical",
                            "browser_pageerror",
                            "JS pageerror: " + "; ".join(real[:3]),
                        )
                    )
                if sandbox:
                    findings.append(
                        _finding(
                            "info",
                            "browser_nav_sandbox",
                            "Click вызвал navigation в srcdoc (игнор для Evidence): "
                            + "; ".join(sandbox[:2]),
                        )
                    )
            browser.close()
    except Exception as e:  # noqa: BLE001
        findings.append(
            _finding("major", "browser_smoke_error", f"browser smoke упал: {e}")
        )
    if not findings:
        findings.append(
            _finding(
                "info",
                "browser_ok",
                "Browser smoke: DOM загружен, есть интерактив, pageerror нет",
            )
        )
    return findings


def run_frontend_browser_smoke(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Playwright smoke: load inlined frontend, check interactives, no pageerror.

    Always runs in a worker thread so it is safe inside Studio's asyncio loop.
    """
    fe = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/frontend") or a.get("role") == "frontend"
    ]
    if not fe:
        return []
    srcdoc = _frontend_srcdoc(fe)
    if not srcdoc:
        return [
            _finding(
                "major",
                "browser_no_html",
                "Нет HTML для browser smoke",
            )
        ]
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_browser_smoke_sync, fe, srcdoc).result(timeout=90)

def scan_all(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Full deterministic pass: heuristics + verify.sh + browser smoke."""
    findings = scan_artifacts(artifacts)
    seen = {(f.get("code"), f.get("path"), f.get("message")) for f in findings}
    for f in (
        *run_frontend_verify(artifacts),
        *run_backend_verify(artifacts),
        *run_tests_verify(artifacts),
        *run_design_verify(artifacts),
        *run_frontend_browser_smoke(artifacts),
    ):
        key = (f.get("code"), f.get("path"), f.get("message"))
        if key not in seen:
            findings.append(f)
            seen.add(key)
    return findings


def score_from_findings(findings: list[dict[str, Any]]) -> tuple[int, str, str]:
    """Return (score 0-100, grade, gate PASS|FAIL|PASS_WITH_RISKS)."""
    score = 100
    for f in findings:
        sev = f.get("severity")
        if sev == "critical":
            score -= 35
        elif sev == "major":
            score -= 15
        elif sev == "minor":
            score -= 5
        elif sev == "info":
            score -= 0
    score = max(0, min(100, score))
    criticals = sum(1 for f in findings if f.get("severity") == "critical")
    majors = sum(1 for f in findings if f.get("severity") == "major")
    if criticals:
        gate = "FAIL"
    elif majors:
        gate = "PASS_WITH_RISKS"
    else:
        gate = "PASS"
    return score, _grade_for_score(score), gate


def _grade_for_score(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def build_receipt(
    *,
    task: str,
    mode: str,
    artifacts: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    llm_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    score, grade, gate = score_from_findings(findings)
    llm_verdict = (llm_review or {}).get("verdict")
    # Hybrid stack (Promptfoo/Braintrust):
    # deterministic gate = objective truth; LLM cannot invent FAIL on a clean gate.
    # LLM FAIL + gate PASS → PASS_WITH_RISKS (advisory), unless LLM cites a critical
    # code that gate already found (then keep FAIL from gate path only).
    if gate == "FAIL":
        final = "FAIL"
    elif llm_verdict == "FAIL" and gate == "PASS":
        final = "PASS_WITH_RISKS"
        score = min(score, 70)
    elif llm_verdict == "FAIL" and gate == "PASS_WITH_RISKS":
        final = "PASS_WITH_RISKS"
        score = min(score, 55)
    elif llm_verdict == "PASS_WITH_RISKS" and gate == "PASS":
        # Clean gate wins: LLM risks stay in review text, not as softer verdict+100 score
        final = "PASS"
    else:
        final = gate

    # Verdict ↔ score consistency (no more PASS_WITH_RISKS @ 100)
    if final == "FAIL":
        score = min(score, 59)
    elif final == "PASS_WITH_RISKS":
        score = min(score, 88)
    grade = _grade_for_score(score)

    return {
        "schema": "onestack.evidence.v1",
        "created_at": int(time.time()),
        "mode": mode,
        "task_preview": (task or "")[:400],
        "artifacts_n": len(artifacts),
        "artifact_paths": [a.get("path") for a in artifacts[:40]],
        "gate_findings": findings,
        "score": score,
        "grade": grade,
        "gate": gate,
        "verdict": final,
        "llm": llm_review,
        "proved": [
            "наличие/отсутствие артефактов с path",
            "эвристики a11y/AI-look/секреты по содержимому файлов",
            "backend/tests: SQL f-string / skip / response_model=dict / ownership",
            "verify.sh frontend/backend/tests/design при наличии артефактов",
            "Playwright browser smoke (load / focus / click / pageerror) для frontend HTML",
            "score/gate из детерминированных правил",
        ],
        "not_proved": [
            "полный E2E против живого API backend",
            "визуальный pixel/LLM QA (Aura-style)",
            "смысловая полнота вне формулировки задачи",
        ],
        "accept_hint": (
            "FAIL — только при critical gate. "
            "PASS_WITH_RISKS — смотреть findings (в т.ч. LLM advisory). "
            "PASS — можно смотреть код, не автопилот."
        ),
    }


_VERDICT_RE = re.compile(
    r"(?:^|\n)\s*#+\s*Вердикт\s*\n+(?:\*\*)?\s*(PASS_WITH_RISKS|PASS|FAIL)\b",
    re.I,
)


def parse_llm_review(text: str) -> dict[str, Any]:
    """Parse verdict ONLY from ## Вердикт section — never first FAIL in prose."""
    raw = text or ""
    format_ok = bool(
        re.search(r"(?:^|\n)\s*#+\s*Вердикт\b", raw, re.I)
        and re.search(r"(?:^|\n)\s*#+\s*Findings\b", raw, re.I)
        and re.search(r"(?:^|\n)\s*#+\s*Evidence\b", raw, re.I)
    )
    m = _VERDICT_RE.search(raw)
    if m:
        verdict = m.group(1).upper()
    else:
        # fallback: line after Вердикт heading
        m2 = re.search(
            r"(?:^|\n)\s*#+\s*Вердикт\s*\n+([^\n]{0,40})",
            raw,
            re.I,
        )
        chunk = (m2.group(1) if m2 else "")
        m3 = re.search(r"\b(PASS_WITH_RISKS|PASS|FAIL)\b", chunk, re.I)
        verdict = m3.group(1).upper() if m3 else "PASS_WITH_RISKS"
    if verdict not in ("PASS", "FAIL", "PASS_WITH_RISKS"):
        verdict = "PASS_WITH_RISKS"
    return {
        "verdict": verdict,
        "text": raw,
        "source": "llm_reviewer",
        "format_ok": format_ok,
    }


def reviewer_format_findings(llm_review: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Gate finding when LLM reviewer skips required sections."""
    if not llm_review or llm_review.get("source") == "llm_reviewer_error":
        return []
    if llm_review.get("format_ok"):
        return []
    return [
        _finding(
            "minor",
            "reviewer_format",
            "Reviewer ответ без полного формата ## Вердикт / ## Findings / ## Evidence",
        )
    ]


def format_evidence_markdown(receipt: dict[str, Any]) -> str:
    findings = receipt.get("gate_findings") or []
    lines = [
        "",
        "---",
        "",
        "## Evidence Gate",
        "",
        f"**Вердикт:** `{receipt.get('verdict')}` · "
        f"gate `{receipt.get('gate')}` · "
        f"score **{receipt.get('score')}** ({receipt.get('grade')})",
        "",
        "Self-report агентов **не** считается доказательством. Ниже — независимая проверка.",
        "",
        "### Gate findings",
    ]
    if not findings:
        lines.append("- (детерминированные gates чистые)")
    else:
        for f in findings:
            loc = f" `{f['path']}`" if f.get("path") else ""
            lines.append(
                f"- **{f.get('severity')}** `{f.get('code')}`{loc}: {f.get('message')}"
            )

    llm = receipt.get("llm") or {}
    if llm.get("text"):
        lines.extend(["", "### Reviewer (модель)", "", llm["text"].strip()])

    lines.extend(
        [
            "",
            "### Что доказано",
            *[f"- {x}" for x in (receipt.get("proved") or [])],
            "",
            "### Что НЕ доказано",
            *[f"- {x}" for x in (receipt.get("not_proved") or [])],
            "",
            f"_{receipt.get('accept_hint')}_",
            "",
        ]
    )
    return "\n".join(lines)


def reviewer_system_prompt(mode: str = "standard") -> str:
    """Load reviewer pack when available; fallback to compact rubric."""
    try:
        from app.skills import build_role_system, load_skill_pack

        load_skill_pack.cache_clear()
        return build_role_system("reviewer", None, "feature", mode)
    except Exception:  # noqa: BLE001
        return REVIEWER_SYSTEM_FALLBACK


REVIEWER_SYSTEM_FALLBACK = """Ты Reviewer / Evidence-агент ZeusCode Studio.
Не пиши фичи. Scope = задача пользователя. Self-report ≠ доказательство.
Iron law: NO COMPLETION CLAIMS WITHOUT EVIDENCE (gate findings или цитата path=).

## Anti-trap (критично)
Studio anti-patterns ВАЖНЕЕ вкуса пользователя:
- indigo / purple / Deep Indigo / Inter / #4f46e5 #6366f1 #7c3aed — НЕ must-have.
- Если юзер просил indigo/Inter, а агенты ЗАМЕНИЛИ на teal/navy/system-ui — это PASS, не FAIL.
- Если агенты ПОДЧИНИЛИСЬ indigo/Inter — major/critical по AI-look (см. gate), не хвали.

## Вердикт
PASS | FAIL | PASS_WITH_RISKS

critical в scope → FAIL. major без critical → PASS_WITH_RISKS. иначе PASS.
FAIL только за critical В SCOPE (нет path=, секреты, SQL f-string, div onclick, явный слом задачи).
Не FAIL за отсутствие PATCH/DELETE если не просили.
Сначала must-have ≤5 из задачи (без AI-trap предпочтений). Findings только к must-have или security/a11y red flags.

## Формат
## Вердикт
## Must-have (из задачи)
## Findings
- [critical|major|minor] `path`: факт
## Evidence
- проверил / не проверил
## Next
- конкретные фиксы в scope
"""

# Back-compat alias used by older callers
REVIEWER_SYSTEM = REVIEWER_SYSTEM_FALLBACK


def reviewer_user_payload(
    *,
    task: str,
    brief: str | None,
    final_text: str,
    artifacts: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> str:
    art_blob = []
    for a in artifacts[:12]:
        body = (a.get("content") or "")[:3500]
        art_blob.append(
            f"\n--- {a.get('path')} ({a.get('role')}, {a.get('language')}) ---\n{body}\n"
        )
    find_lines = [
        f"- [{f.get('severity')}] {f.get('code')}: {f.get('message')} ({f.get('path') or '—'})"
        for f in findings
    ] or ["- (gate чистый)"]
    must = (
        "Сначала выпиши must-have из задачи (≤5 буллетов). "
        "НЕ включай в must-have: indigo, Deep Indigo, purple, Inter, AI-hex — это traps Studio. "
        "Если задача просила indigo/Inter — must-have = форма/экран/контракт БЕЗ этих токенов; "
        "подчинение trap = finding, отказ от trap = хорошо. "
        "Findings только к must-have или security/a11y/AI-look red flags. "
        "Не требуй полный CRUD вне формулировки. "
        "Ты оркестратор-судья: НЕ пиши код. Смотри ТОЛЬКО финальные артефакты и результат — "
        "не рассуждения агентов и не процесс."
    )
    # Only final product snippet — drop thinking / process chatter
    product = final_text or ""
    if "## Результат" in product:
        product = product.split("## Результат", 1)[-1]
    if "## Мышление" in product:
        product = product.split("## Мышление", 1)[0]
    return (
        f"{must}\n\n"
        f"Задача:\n{task}\n\n"
        f"Бриф:\n{(brief or '—')[:2000]}\n\n"
        f"Детерминированные gate findings:\n" + "\n".join(find_lines) + "\n\n"
        f"Финальный продукт (untrusted):\n{(product or '')[:4000]}\n\n"
        f"Артефакты (единственный источник правды о коде):\n"
        f"{''.join(art_blob) if art_blob else '(пусто)'}\n"
    )
