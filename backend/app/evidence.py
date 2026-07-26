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
    findings.extend(_landing_quality_findings(artifacts))
    findings.extend(_app_quality_findings(artifacts))
    return findings


_PLACEHOLDER_CONTACT = re.compile(
    r"("
    r"\+7\s*\(\s*495\s*\)\s*000[-\s]?00[-\s]?00|"
    r"8\s*\(\s*495\s*\)\s*000[-\s]?00[-\s]?00|"
    r"\+7\s*\(\s*000\s*\)|"
    r"555[-\s]?01[-\s]?01|"
    r"your@email\.com|"
    r"example\.com|"
    r"xxx[-\s]?xx[-\s]?xx"
    r")",
    re.I,
)
_FAKE_SUCCESS_COPY = re.compile(
    r"(заявк\w*\s+(принят|отправлен)|успешн\w*\s+отправлен|мы\s+свяжемся)",
    re.I,
)
_CSS_IMPORT_RE = re.compile(
    r"""@import\s+(?:url\(\s*['"]?([^'")\s]+)['"]?\s*\)|['"]([^'"]+)['"])\s*;?""",
    re.I,
)
_ASSET_URL_RE = re.compile(
    r"""(?:url\(\s*['"]?([^'")]+)['"]?\s*\)|(?:src|href)\s*=\s*['"]([^'"]+)['"])""",
    re.I,
)
_FETCH_API_RE = re.compile(
    r"""fetch\s*\(\s*['"`](/api/[a-zA-Z0-9_/{}\-]+)['"`]""",
    re.I,
)


def _artifact_paths(artifacts: list[dict[str, Any]]) -> set[str]:
    return {(a.get("path") or "").strip() for a in artifacts if (a.get("path") or "").strip()}


def _resolve_fe_rel(ref: str, from_path: str = "/src/frontend/styles.css") -> str | None:
    """Resolve relative asset/import path to absolute /src/... workspace path."""
    ref = (ref or "").strip()
    if not ref or ref.startswith(("data:", "http://", "https://", "blob:", "#", "mailto:", "tel:")):
        return None
    if ref.startswith("//"):
        return None
    if ref.startswith("/src/"):
        return ref.split("?", 1)[0].split("#", 1)[0]
    if ref.startswith("/api/"):
        return None
    # root-absolute under frontend mount (e.g. /assets/x.jpg served from FE)
    if ref.startswith("/") and not ref.startswith("/src/"):
        rel = ref.lstrip("/")
        return f"/src/frontend/{rel}".split("?", 1)[0]
    base_dir = from_path.rsplit("/", 1)[0]  # /src/frontend or /src/design
    parts = base_dir.strip("/").split("/") + ref.split("/")
    out: list[str] = []
    for p in parts:
        if p in ("", "."):
            continue
        if p == "..":
            if out:
                out.pop()
            continue
        out.append(p)
    return ("/" + "/".join(out)).split("?", 1)[0].split("#", 1)[0]


def _backend_api_paths(artifacts: list[dict[str, Any]]) -> set[str]:
    """Collect absolute /api/... paths from FastAPI routers (incl. prefix + relative)."""
    be_blob = "\n".join(
        a.get("content") or ""
        for a in artifacts
        if (a.get("path") or "").startswith("/src/backend") or a.get("role") == "backend"
    )
    paths: set[str] = set()
    if not be_blob.strip():
        return paths

    # prefix="/api" or prefix='/api/shop' (slash after api optional)
    prefixes: list[str] = []
    for m in re.finditer(
        r"""(?:APIRouter\s*\([^)]*)?prefix\s*=\s*['"](/api(?:/[^'"]*)?)['"]""",
        be_blob,
        re.I,
    ):
        prefixes.append(m.group(1).rstrip("/"))
    if not prefixes:
        prefixes = [""]

    def _abs(route: str) -> str:
        route = (route or "").strip()
        if not route:
            return ""
        if route.startswith("/api"):
            return route.rstrip("/") or "/api"
        for pref in prefixes:
            if not pref:
                continue
            if route == "/":
                return pref
            return (pref + (route if route.startswith("/") else f"/{route}")).rstrip(
                "/"
            ) or pref
        return route if route.startswith("/") else f"/{route}"

    for m in re.finditer(
        r"""@router\.(?:get|post|put|patch|delete)\(\s*['"]([^'"]+)['"]""",
        be_blob,
        re.I,
    ):
        abs_p = _abs(m.group(1))
        if abs_p:
            paths.add(abs_p)
    for m in re.finditer(r"""['"](/api/[a-zA-Z0-9_/{}\-]+)['"]""", be_blob):
        paths.add(m.group(1).rstrip("/"))
    for pref in prefixes:
        if pref:
            paths.add(pref)
    return paths


def _path_covered(used: str, known: set[str]) -> bool:
    ub = re.sub(r"\{[^}]+\}", "", used).rstrip("/")
    for k in known:
        kb = re.sub(r"\{[^}]+\}", "", k).rstrip("/")
        if ub == kb or ub.startswith(kb + "/") or kb.startswith(ub + "/"):
            return True
    return False


def _is_app_shell_blob(fe_blob: str) -> bool:
    """True when FE is a multi-screen app (not a marketing landing)."""
    if not fe_blob:
        return False
    multi = len(re.findall(r"data-screen\s*=", fe_blob, re.I)) >= 2
    nav = bool(
        re.search(
            r"data-view\s*=|data-nav\s*=|class=[\"'][^\"']*app-nav|class=[\"'][^\"']*\btabs\b",
            fe_blob,
            re.I,
        )
    )
    catalog_api = bool(
        re.search(
            r"/api/(bouquets|products|items|catalog|orders)|addToCart|data-pick|order-preview",
            fe_blob,
            re.I,
        )
    )
    return (multi and nav) or (multi and catalog_api) or (nav and catalog_api)


def _landing_quality_findings(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hard gates for shippable landings: assets, contacts, API, fake success, CSS imports."""
    findings: list[dict[str, Any]] = []
    paths = _artifact_paths(artifacts)
    fe_arts = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/frontend") or a.get("role") == "frontend"
    ]
    if not fe_arts:
        return findings

    fe_blob = "\n".join(a.get("content") or "" for a in fe_arts)
    fe_code = _strip_comments(fe_blob)

    # --- placeholder contacts ---
    copy_blob = re.sub(r"<[^>]+>", " ", fe_code)
    if _PLACEHOLDER_CONTACT.search(copy_blob) or _PLACEHOLDER_CONTACT.search(fe_code):
        findings.append(
            _finding(
                "major",
                "placeholder_contact",
                "Плейсхолдер-контакт (000-00-00 / example.com) — нужны реалистичные данные",
            )
        )

    # --- missing local assets ---
    missing: list[str] = []
    for a in fe_arts:
        apath = (a.get("path") or "").strip()
        body = a.get("content") or ""
        if not (apath.endswith((".html", ".css")) or "<style" in body.lower()):
            continue
        for m in _ASSET_URL_RE.finditer(body):
            ref = (m.group(1) or m.group(2) or "").strip()
            # skip stylesheet/script self-links and pure anchors
            if not ref or ref.startswith(("#", "data:", "http://", "https://", "mailto:", "tel:")):
                continue
            if re.search(r"\.(css|js)(\?|$)", ref, re.I) and not re.search(
                r"\.(png|jpe?g|webp|gif|svg|avif|ico|woff2?|ttf|mp4|webm)(\?|$)",
                ref,
                re.I,
            ):
                # css/js handled by broken_css_import / bundling; skip non-media
                if "assets/" not in ref and not re.search(
                    r"\.(png|jpe?g|webp|gif|svg|avif)(\?|$)", ref, re.I
                ):
                    continue
            resolved = _resolve_fe_rel(ref, apath if apath.endswith(".css") else "/src/frontend/index.html")
            if not resolved:
                continue
            # only flag media-like or explicit assets/ paths
            if not (
                "/assets/" in resolved
                or re.search(r"\.(png|jpe?g|webp|gif|svg|avif|ico|woff2?|ttf)(\?|$)", resolved, re.I)
            ):
                continue
            if resolved not in paths and not any(
                p == resolved or p.endswith("/" + resolved.rsplit("/", 1)[-1]) for p in paths
            ):
                missing.append(f"{ref} → {resolved}")
    if missing:
        uniq = sorted(set(missing))[:4]
        findings.append(
            _finding(
                "major",
                "missing_asset",
                "Локальный media-ассет в CSS/HTML отсутствует в артефактах: "
                + "; ".join(uniq),
            )
        )

    # --- broken @import (path not in artifacts) ---
    broken_imports: list[str] = []
    for a in fe_arts:
        apath = (a.get("path") or "").strip()
        if not apath.endswith(".css"):
            continue
        body = a.get("content") or ""
        for m in _CSS_IMPORT_RE.finditer(body):
            ref = (m.group(1) or m.group(2) or "").strip()
            if not ref or ref.startswith(("http://", "https://", "data:")):
                continue
            resolved = _resolve_fe_rel(ref, apath)
            if not resolved:
                continue
            if resolved not in paths:
                broken_imports.append(f"{ref} → {resolved}")
    if broken_imports:
        findings.append(
            _finding(
                "major",
                "broken_css_import",
                "@import указывает на файл вне артефактов (preview/srcdoc сломается): "
                + "; ".join(sorted(set(broken_imports))[:3]),
            )
        )

    # --- API orphan: FE fetch('/api/...') without matching backend route ---
    used_apis = set(_FETCH_API_RE.findall(fe_blob))
    # also catch template literals lightly already in regex; add quoted paths in fetch alternatives
    used_apis |= set(
        re.findall(
            r"""(?:fetch|axios\.(?:post|get|put|patch|delete))\(\s*['"`](/api/[^'"`]+)['"`]""",
            fe_blob,
            re.I,
        )
    )
    if used_apis:
        be_paths = _backend_api_paths(artifacts)
        has_backend = any(
            (a.get("path") or "").startswith("/src/backend") or a.get("role") == "backend"
            for a in artifacts
        )
        orphans = [u for u in used_apis if not _path_covered(u, be_paths)]
        if orphans and (not has_backend or not be_paths or len(orphans) == len(used_apis)):
            findings.append(
                _finding(
                    "major",
                    "api_orphan",
                    "Frontend вызывает "
                    + ", ".join(sorted(orphans)[:4])
                    + " без backend route в артефактах — форма мёртвая",
                )
            )

    # --- fake form success: catch shows success, or success copy without fetch ---
    js_blobs = [
        a.get("content") or ""
        for a in fe_arts
        if (a.get("path") or "").endswith(".js")
        or (a.get("language") or "") in ("js", "javascript")
    ]
    js_all = "\n".join(js_blobs)
    if js_all.strip():
        has_fetch = bool(re.search(r"\bfetch\s*\(", js_all))
        # catch block containing success copy
        for m in re.finditer(r"catch\s*\([^)]*\)\s*\{(.{0,400})\}", js_all, re.S):
            block = m.group(1)
            if _FAKE_SUCCESS_COPY.search(block) and not re.search(
                r"(error|ошибк|не\s+удалось|позвоните)", block, re.I
            ):
                findings.append(
                    _finding(
                        "major",
                        "fake_form_success",
                        "В catch формы показывается успех — враньё пользователю при ошибке API",
                    )
                )
                break
        # success UI text but no fetch at all + preventDefault form handler
        if (
            not has_fetch
            and _FAKE_SUCCESS_COPY.search(js_all)
            and re.search(r"preventDefault|booking-form|submit", js_all, re.I)
        ):
            findings.append(
                _finding(
                    "major",
                    "fake_form_success",
                    "Форма показывает «заявка принята/отправлена» без fetch — фейковый success",
                )
            )

    # --- skeleton / empty media (cheap-model traps) ---
    # App-shell ≠ landing: never fail shop apps on hero/vitrine/FAQ/services
    if not _is_app_shell_blob(fe_blob):
        findings.extend(_landing_skeleton_findings(fe_arts, fe_blob, fe_code))
        findings.extend(_deck_content_findings(artifacts))
    elif re.search(r"\bdeck\b|слайд|pitch", fe_blob, re.I):
        findings.extend(_deck_content_findings(artifacts))

    return findings


def _app_quality_findings(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gates for web apps: shell nav, multi-screen, states — not marketing landing."""
    findings: list[dict[str, Any]] = []
    fe_arts = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/frontend") or a.get("role") == "frontend"
    ]
    if not fe_arts:
        return findings

    fe_blob = "\n".join(a.get("content") or "" for a in fe_arts)
    fe_low = fe_blob.lower()

    # Activate only when task looks like an app (signals in FE or brief notes in html/js)
    app_signal = bool(
        re.search(
            r"data-nav|data-screen|app-nav|app-shell|app-bar|"
            r"product_id[\"']?\s*:\s*[\"']app|"
            r"интент:\s*приложен",
            fe_blob,
            re.I,
        )
    )
    # Or: has SPA-ish multi main/section + fetch list/create, and NOT classic landing
    multi_screen = len(re.findall(r"data-screen\s*=", fe_blob, re.I)) >= 2
    has_nav = bool(
        re.search(
            r"class=[\"'][^\"']*app-nav|data-nav\s*=|data-view\s*=",
            fe_blob,
            re.I,
        )
    )
    landing_heavy = _looks_like_landing(fe_blob) and bool(
        re.search(r"\bhero\b|#services|отзыв", fe_low)
    )
    catalogish = bool(
        re.search(
            r"/api/(bouquets|products|items|catalog)|каталог|букет|товар",
            fe_low,
        )
    )

    if not (app_signal or multi_screen or has_nav):
        # Heuristic: brief-like comments asking for app without shell → still skip
        # unless landing-shaped with zero app chrome while mentioning «приложение» in title
        if re.search(r"<title>[^<]*(приложен|app|задач|кабинет)", fe_low) and landing_heavy:
            findings.append(
                _finding(
                    "critical",
                    "wrong_product_shape",
                    "Похоже на приложение по title, но сдан лендинг (hero/услуги) без app-nav",
                )
            )
        return findings

    if landing_heavy and not (has_nav or multi_screen):
        findings.append(
            _finding(
                "critical",
                "wrong_product_shape",
                "App-задача сдана как лендинг: hero/услуги без app-shell (nav + экраны)",
            )
        )

    if not has_nav and not multi_screen:
        findings.append(
            _finding(
                "major",
                "wrong_product_shape",
                "Нет app-nav / data-nav и нет ≥2 data-screen — это не app-shell",
            )
        )

    # States: empty or error marker somewhere in JS/HTML
    has_state = bool(
        re.search(
            r"(empty|пуст[оа]|ошибк|error|loading|загрузк|role=[\"']status|role=[\"']alert)",
            fe_low,
        )
    )
    if (has_nav or multi_screen) and not has_state:
        findings.append(
            _finding(
                "major",
                "missing_state",
                "App-shell без empty/error/loading status на главном потоке",
            )
        )

    # Flash traps: alert success / inline onclick / fetch without !ok
    if re.search(
        r"""alert\s*\(\s*['\"`][^'\"`]*(?:заказ|сохран|принят|успех|оформлен|отправлен)""",
        fe_blob,
        re.I,
    ):
        findings.append(
            _finding(
                "major",
                "fake_alert_success",
                "alert() с текстом успеха — вместо role=status/alert и проверки res.ok",
            )
        )

    if re.search(r"""\sonclick\s*=\s*['\"]""", fe_blob):
        findings.append(
            _finding(
                "major",
                "inline_onclick",
                "inline onclick=\"…\" — используй button + addEventListener",
            )
        )

    # React/SPA stack without brief ask (default for app is vanilla)
    if re.search(
        r"from ['\"]react['\"]|react-dom|createRoot\s*\(|@tanstack/react-query",
        fe_blob,
    ) and not re.search(r"(?i)react|jsx|next\.js", "\n".join(
        a.get("content") or "" for a in artifacts if "brief" in (a.get("path") or "").lower()
    )):
        # brief is not an artifact — check HTML/JS comments / title only weak; always flag for app shell
        if has_nav or multi_screen or app_signal:
            findings.append(
                _finding(
                    "major",
                    "react_without_ask",
                    "React/Query без просьбы в brief — для app default HTML+CSS+JS",
                )
            )

    # fetch POST/GET then success without res.ok / !r.ok nearby (heuristic)
    if re.search(r"fetch\s*\(", fe_blob) and re.search(
        r"""alert\s*\(|['\"]заявка принят|['\"]заказ оформлен|['\"]сохранено""",
        fe_blob,
        re.I,
    ):
        if not re.search(r"\.ok\b|!res\.ok|!r\.ok|status\s*===?\s*20", fe_blob):
            findings.append(
                _finding(
                    "major",
                    "fake_form_success",
                    "Есть fetch и success-копирайт, но нет проверки res.ok",
                )
            )

    # --- density traps (Flash ships 2KB shells that "pass" nav checks) ---
    css_len = sum(
        len(a.get("content") or "")
        for a in fe_arts
        if (a.get("path") or "").endswith(".css")
    )
    if (has_nav or multi_screen or app_signal) and css_len and css_len < 3500:
        findings.append(
            _finding(
                "critical" if catalogish else "major",
                "thin_styles",
                f"styles.css слишком тонкий ({css_len}B < 3500) — скелет, не продукт",
            )
        )

    if catalogish and (has_nav or multi_screen or app_signal):
        # Brand/header chrome — any brand mark, not etalon class names
        if not re.search(
            r"class=[\"'][^\"']*\bbrand\b|<header\b|app-nav|data-view\s*=",
            fe_blob,
            re.I,
        ):
            findings.append(
                _finding(
                    "critical",
                    "thin_app_chrome",
                    "Нет header/brand/nav chrome — app-shell пустой",
                )
            )
        if not re.search(r"data-filter|class=[\"'][^\"']*\bfilters\b|chip", fe_blob, re.I):
            findings.append(
                _finding(
                    "critical",
                    "missing_filters",
                    "Каталог без фильтров — chips должны совпадать с seed",
                )
            )
        if not re.search(
            r"order-preview|cart-badge|class=[\"'][^\"']*\bpreview\b|order-layout|cart-lines",
            fe_blob,
            re.I,
        ):
            findings.append(
                _finding(
                    "critical",
                    "missing_order_preview",
                    "Нет экрана заказа/корзины (preview или cart lines)",
                )
            )
        js_len = sum(
            len(a.get("content") or "")
            for a in fe_arts
            if (a.get("path") or "").endswith(".js")
        )
        if js_len and js_len < 3200:
            findings.append(
                _finding(
                    "critical",
                    "thin_app_js",
                    f"app.js слишком тонкий ({js_len}B < 3200) — нет рабочих потоков",
                )
            )
        html_len = sum(
            len(a.get("content") or "")
            for a in fe_arts
            if (a.get("path") or "").endswith((".html", ".htm"))
        )
        if html_len and html_len < 2800:
            findings.append(
                _finding(
                    "critical",
                    "thin_app_html",
                    f"index.html слишком тонкий ({html_len}B < 2800) — скелет",
                )
            )
        # Behavioral JS DoD (function names are free)
        has_fetch = bool(re.search(r"\bfetch\s*\(", fe_blob))
        has_orders = bool(re.search(r"loadOrders|/api/orders", fe_blob, re.I))
        has_cta = bool(
            re.search(r"addToCart|data-pick|dataset\.pick|В корзину|В заказ", fe_blob, re.I)
        )
        has_ok = bool(re.search(r"\.ok\b|!res\.ok|!r\.ok", fe_blob))
        if js_len >= 3200 and not (has_fetch and has_orders and has_cta and has_ok):
            findings.append(
                _finding(
                    "critical",
                    "thin_app_js",
                    "app.js без рабочего контракта: fetch + CTA/корзина + orders + res.ok",
                )
            )
        # Cards built in JS without <img and without pick/order CTA
        builds_list = bool(
            re.search(
                r"innerHTML\s*=|\.map\s*\(|createElement\s*\(\s*['\"]div",
                fe_blob,
            )
        )
        has_img_in_card = bool(
            re.search(
                r"""<img\b|innerHTML[^;]*img|\.image\b|image_url|b\.image|item\.image""",
                fe_blob,
            )
        )
        has_pick_cta = bool(
            re.search(
                r"data-pick|в заказ|в корзину|выбрать|data-id\s*=",
                fe_low,
            )
        )
        if builds_list and (not has_img_in_card or not has_pick_cta):
            findings.append(
                _finding(
                    "major",
                    "thin_catalog",
                    "Каталог без img из API и/или без CTA «В заказ» — thin_catalog",
                )
            )
        # CTA rendered but never wired
        if re.search(r"data-id\s*=", fe_blob) and not re.search(
            r"dataset\.id|getAttribute\(\s*['\"]data-id['\"]|\[data-id\]|data-pick",
            fe_blob,
        ):
            findings.append(
                _finding(
                    "major",
                    "dead_pick_cta",
                    "Кнопка data-id в каталоге без обработчика click — CTA мёртвая",
                )
            )

        has_select = bool(re.search(r"<select\b", fe_blob, re.I))
        fills_select = bool(
            re.search(
                r"""(?:bouquet_id|item_id|product_id|productSelect|bouquetSelect)"""
                r"""[^;]{0,120}innerHTML|"""
                r"""select[^;]{0,40}innerHTML|innerHTML\s*=\s*[^;]*<option|"""
                r"""syncHiddenSelect|fillSelect""",
                fe_blob,
                re.I,
            )
        )
        # Cart apps may hide select and drive orders from cart[] — OK
        cart_ok = bool(re.search(r"addToCart|cart-badge", fe_blob))
        if has_select and not fills_select and not cart_ok:
            findings.append(
                _finding(
                    "major",
                    "dead_select",
                    "Есть <select>, но options не наполняются из API — форма мертва",
                )
            )

        # Delivery shop without address field
        if re.search(r"доставк|delivery|адрес", fe_low) and not re.search(
            r"name=[\"']address[\"']|id=[\"']address[\"']|\baddress\b",
            fe_blob,
            re.I,
        ):
            findings.append(
                _finding(
                    "major",
                    "missing_address_field",
                    "Доставка в задаче, но в форме нет поля address",
                )
            )

        # GET /api/orders used or promised → need orders screen
        be_blob = "\n".join(
            a.get("content") or ""
            for a in artifacts
            if (a.get("path") or "").startswith("/src/backend")
        )
        if re.search(r"""@router\.get\(\s*['\"]/?orders['\"]""", be_blob) or re.search(
            r"""fetch\s*\(\s*['\"]/api/orders['\"]""", fe_blob
        ):
            if not re.search(
                r"""data-screen\s*=\s*['\"]orders['\"]|data-nav\s*=\s*['\"]orders['\"]|"""
                r"""id=['\"]view-orders['\"]|id=['\"]screen-orders['\"]""",
                fe_blob,
                re.I,
            ):
                findings.append(
                    _finding(
                        "major",
                        "missing_orders_screen",
                        "Есть GET /api/orders, но нет экрана orders в app-shell",
                    )
                )

    # Required mystery headers on public shop API
    be_all = "\n".join(
        a.get("content") or ""
        for a in artifacts
        if (a.get("path") or "").startswith("/src/backend")
    )
    if be_all and re.search(r"Header\s*\(\s*\.\.\.\s*\)", be_all):
        findings.append(
            _finding(
                "major",
                "mystery_auth_header",
                "Backend требует Header(...) без brief auth — публичная форма сломается",
            )
        )

    # POST fetch without JSON content-type
    if re.search(r"""fetch\s*\([^)]*method\s*:\s*['\"]POST['\"]""", fe_blob, re.I):
        post_blocks = re.findall(
            r"fetch\s*\(\s*[^)]+?\{.{0,280}?method\s*:\s*['\"]POST['\"].{0,280}?\}",
            fe_blob,
            re.I | re.S,
        )
        for block in post_blocks[:4]:
            if "JSON.stringify" in block and not re.search(
                r"Content-Type|application/json", block, re.I
            ):
                findings.append(
                    _finding(
                        "major",
                        "missing_json_headers",
                        "POST + JSON.stringify без Content-Type: application/json",
                    )
                )
                break

    # Backend catalog seed too thin / no images / contract drift
    be_arts = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/backend") or a.get("role") == "backend"
    ]
    if be_arts and catalogish:
        be_all = "\n".join(a.get("content") or "" for a in be_arts)
        unsplash_n = len(
            re.findall(r"https://images\.unsplash\.com/|\"image(?:_url)?\"\s*:\s*\"https://", be_all)
        )
        seed_objs = len(re.findall(r"""['\"]id['\"]\s*:""", be_all))
        if unsplash_n < 4 and seed_objs >= 1:
            findings.append(
                _finding(
                    "critical",
                    "thin_catalog_seed",
                    f"Backend seed: мало remote image URL ({unsplash_n} < 4) для каталога",
                )
            )
        has_name = bool(re.search(r"""['\"]name['\"]\s*:""", be_all))
        has_title_only = bool(re.search(r"""['\"]title['\"]\s*:""", be_all)) and not has_name
        if has_title_only:
            findings.append(
                _finding(
                    "critical",
                    "seed_title_not_name",
                    "Seed с title без name — FE/orders ждут name → null в карточках и заказах",
                )
            )
        has_desc = bool(
            re.search(r"""['\"](?:desc|description|composition)['\"]\s*:""", be_all)
        )
        if seed_objs >= 2 and not has_desc:
            findings.append(
                _finding(
                    "critical",
                    "thin_catalog_fields",
                    "Seed без desc/description/composition — карточки тощие (только title+цена)",
                )
            )
        # Filters in FE must match seed tag OR category values
        chips = {
            c
            for c in re.findall(r"""data-filter=["']([^"']+)["']""", fe_blob, re.I)
            if c.lower() not in ("all", "все", "*")
        }
        seed_facets = {
            v
            for v in re.findall(
                r"""['\"](?:category|tag|tags)['\"]\s*:\s*['\"]([^'\"]+)['\"]""",
                be_all,
            )
            if v.strip()
        }
        if chips and seed_facets and not chips.issubset(seed_facets):
            missing = sorted(chips - seed_facets)
            findings.append(
                _finding(
                    "critical",
                    "filter_seed_mismatch",
                    "Фильтры FE не совпадают с seed category/tag: "
                    f"chips={sorted(chips)} seed={sorted(seed_facets)} "
                    f"лишние={missing} — клик даёт пустой каталог",
                )
            )
        elif chips and not seed_facets and seed_objs >= 2:
            findings.append(
                _finding(
                    "critical",
                    "filter_seed_mismatch",
                    f"FE filters {sorted(chips)} есть, но в seed нет category/tag полей",
                )
            )
        # Dead / unverified Unsplash IDs → blank cards (Flash invents photo-IDs)
        try:
            from app.media_packs import allowlisted_image_ids

            grocery = bool(
                re.search(r"PRODUCTS\s*=|/api/products|Овощи", be_all)
            )
            allowed = allowlisted_image_ids("grocery" if grocery else "flowers")
            seed_ids = set(
                re.findall(r"images\.unsplash\.com/photo-([0-9a-zA-Z_-]+)", be_all, re.I)
            )
            bad = seed_ids - allowed
            if seed_ids and bad and len(bad) >= max(1, len(seed_ids) // 2):
                findings.append(
                    _finding(
                        "critical",
                        "dead_catalog_images",
                        f"Seed image IDs не из media pack grocery/flowers ({sorted(bad)[:4]}) — "
                        "часто 404 → серые карточки без фото",
                    )
                )
        except Exception:  # noqa: BLE001
            pass

    # Products shop must have cart UX (not only one-shot order)
    if catalogish and re.search(r"/api/products|магазин продукт|Свежая Полка", fe_blob, re.I):
        if not re.search(r"addToCart|cart-badge|В корзину", fe_blob):
            findings.append(
                _finding(
                    "critical",
                    "missing_cart",
                    "Продуктовый магазин без корзины (addToCart / cart-badge / «В корзину»)",
                )
            )
        if re.search(
            r"\$\{[^}]*\.composition\}[^$]*\$\{[^}]*\.size\}[^$]*\$\{[^}]*\.stems\}",
            fe_blob,
        ):
            findings.append(
                _finding(
                    "major",
                    "flower_meta_on_products",
                    "Карточки рендерят composition/size/stems → undefined на продуктах",
                )
            )

    # Inline JS in HTML breaks app.js (second loadOrders / «История недоступна»)
    html_only = "\n".join(
        a.get("content") or ""
        for a in fe_arts
        if (a.get("path") or "").endswith((".html", ".htm"))
    )
    if re.search(
        r"<script\b(?![^>]*\bsrc=)[^>]*>[\s\S]{80,}?</script>",
        html_only,
        re.I,
    ):
        findings.append(
            _finding(
                "critical",
                "inline_script_in_html",
                "Логика в <script> внутри index.html — дублирует/ломает app.js. "
                "Только <script src=\"app.js\">",
            )
        )

    return findings


def _looks_like_landing(fe_blob: str) -> bool:
    return bool(
        re.search(
            r"booking|запис|услуг|#services|hero|/api/booking|/api/lead|"
            r"прайс|автосервис|шиномонтаж|лендинг",
            fe_blob,
            re.I,
        )
    )


def _landing_skeleton_findings(
    fe_arts: list[dict[str, Any]], fe_blob: str, fe_code: str
) -> list[dict[str, Any]]:
    """Fail navy-void / 2KB shells that previously scored PASS@100."""
    findings: list[dict[str, Any]] = []
    if not _looks_like_landing(fe_blob):
        return findings

    has_hero = bool(
        re.search(
            r"""class=["'][^"']*\bhero\b|\.hero\b|<section[^>]*\bhero\b""",
            fe_blob,
            re.I,
        )
    )
    has_http_media = bool(
        re.search(
            r"""(?:src\s*=\s*['"]https?://)|(?:url\s*\(\s*['"]?https?://)""",
            fe_blob,
            re.I,
        )
    )
    has_img = bool(re.search(r"<img\b", fe_blob, re.I))
    if has_hero and not has_http_media and not has_img:
        findings.append(
            _finding(
                "major",
                "no_hero_media",
                "Hero без remote https фото и без <img> — solid/gradient void "
                "(нужен url(https://…) из брифа/media.md)",
            )
        )

    html_len = sum(
        len(a.get("content") or "")
        for a in fe_arts
        if (a.get("path") or "").endswith((".html", ".htm"))
    )
    sections = len(re.findall(r"<section\b", fe_blob, re.I))
    service_cards = len(
        re.findall(r"""<article\b|class=["'][^"']*\bcard\b""", fe_blob, re.I)
    )
    price_hits = len(re.findall(r"от\s*[\d\s]{2,}|\d[\d\s]{2,}\s*₽", fe_blob, re.I))

    thin_reasons: list[str] = []
    if html_len and html_len < 6000:
        thin_reasons.append(f"HTML {html_len}B < 6000")
    if sections < 7:
        thin_reasons.append(f"section={sections} < 7")
    if service_cards < 5 and price_hits < 5:
        thin_reasons.append(
            f"услуг/карточек мало (cards={service_cards}, prices={price_hits})"
        )
    if thin_reasons:
        findings.append(
            _finding(
                "major",
                "thin_landing",
                "Скелет лендинга: "
                + "; ".join(thin_reasons)
                + " — добери плотность и факты из брифа "
                "(эталон good_* = планка качества, не клон бренда/layout)",
            )
        )

    if not re.search(r"zeus-badge|сделано на zeuscode|made with zeuscode", fe_blob, re.I):
        findings.append(
            _finding(
                "major",
                "missing_zeus_badge",
                "Нет бейджа «Сделано на ZeusCode» (zeus-badge) — см. frontend/references/publish.md",
            )
        )

    # Real photos somewhere (not CSS-only void) — any gallery, not forced #vitrine
    img_https = len(
        re.findall(r"""<img\b[^>]*\bsrc\s*=\s*['"]https?://""", fe_blob, re.I)
    )
    if img_https < 2 and not has_http_media:
        findings.append(
            _finding(
                "major",
                "weak_media",
                f"Мало живого media: {img_https}× <img https> — нужен предметный якорь "
                "(hero/галерея/витрина под нишу, не пустой градиент)",
            )
        )
    elif img_https < 2 and has_http_media:
        # CSS backgrounds count as media; only warn softly if zero imgs
        pass

    # Fat service cards: paragraph + includes list
    articles = re.findall(r"<article\b[\s\S]*?</article>", fe_blob, re.I)
    fat_services = 0
    for art in articles:
        plain = re.sub(r"<[^>]+>", " ", art)
        plain = re.sub(r"\s+", " ", plain).strip()
        has_list = bool(re.search(r"<ul\b", art, re.I))
        if len(plain) >= 140 and has_list:
            fat_services += 1
        elif len(plain) >= 180:
            fat_services += 1
    # Only when there are many empty articles (template-y) — don't force «exactly 5 fat»
    if len(articles) >= 4 and fat_services < 2:
        findings.append(
            _finding(
                "major",
                "thin_services",
                f"Карточки пустые: {fat_services}/{len(articles)} с нормальным текстом — "
                "факты/цена из brief, не egg-copy",
            )
        )

    # Same Unsplash photo-ID used 2+ times → no variety
    ids = re.findall(
        r"images\.unsplash\.com/photo-([0-9a-zA-Z_-]+)",
        fe_blob,
        re.I,
    )
    unique_ids = set(ids)
    if has_http_media or has_img:
        if len(unique_ids) < 3:
            findings.append(
                _finding(
                    "major",
                    "duplicate_media",
                    "Нужно ≥3 разных Unsplash photo-ID (hero + витрина). "
                    "Сейчас: "
                    + (", ".join(sorted(x[:24] for x in unique_ids)[:4]) or "нет ID"),
                )
            )
        else:
            from collections import Counter

            dup = [i for i, n in Counter(ids).items() if n >= 3]
            if dup:
                findings.append(
                    _finding(
                        "minor",
                        "duplicate_media",
                        "Частый повтор photo-ID: " + ", ".join(x[:20] for x in dup[:2]),
                    )
                )

    has_btn = bool(
        re.search(r"""class=["'][^"']*\bbtn\b|\.btn\s*\{""", fe_blob, re.I)
    )
    if not has_btn:
        findings.append(
            _finding(
                "major",
                "weak_cta",
                "Нет CTA-кнопки class=btn — главный CTA не должен быть голой ссылкой",
            )
        )

    has_reviews = bool(re.search(r"<blockquote\b", fe_blob, re.I))
    has_faq = bool(
        re.search(r"<details\b|id=[\"']faq[\"']|часто задаваем", fe_blob, re.I)
    )
    if not has_reviews or not has_faq:
        missing = []
        if not has_reviews:
            missing.append("отзывы <blockquote>")
        if not has_faq:
            missing.append("FAQ <details>")
        findings.append(
            _finding(
                "major",
                "thin_copy",
                "Неполное наполнение: нет "
                + " и ".join(missing)
                + " — вставь тексты из brief (content-fill)",
            )
        )

    has_brand = bool(
        re.search(
            r"""class=["'][^"']*\bbrand\b|<header\b[\s\S]{0,400}<strong""",
            fe_blob,
            re.I,
        )
    )
    if not has_brand:
        findings.append(
            _finding(
                "minor",
                "weak_brand",
                "В шапке слабо виден бренд (class=brand) — добавь имя из brief",
            )
        )

    # --- visual polish (quality, not one typeface/chrome stamp) ---
    css_blob = "\n".join(
        a.get("content") or ""
        for a in fe_arts
        if (a.get("path") or "").endswith(".css")
    )
    if not re.search(r"position\s*:\s*sticky", css_blob, re.I):
        findings.append(
            _finding(
                "minor",
                "no_sticky",
                "Нет sticky header — ок, если chrome читаемый; иначе visual-polish",
            )
        )
    if not re.search(
        r"Georgia|Times New Roman|ui-serif|serif|Playfair|Fraunces|Cormorant|"
        r"Manrope|Syne|Outfit|DM Sans|Space Grotesk",
        css_blob,
        re.I,
    ):
        findings.append(
            _finding(
                "minor",
                "weak_type",
                "Слабо задан display-type — выбери выразительный стек под нишу (не Inter)",
            )
        )
    if not re.search(r"\btransition\s*:", css_blob, re.I) or not re.search(
        r":hover", css_blob, re.I
    ):
        findings.append(
            _finding(
                "major",
                "no_motion",
                "Нет transition + :hover на интерактиве — минимум 2 motion (visual-polish)",
            )
        )
    if not re.search(r"@media\s*\([^)]*max-width", css_blob, re.I):
        findings.append(
            _finding(
                "major",
                "no_mobile",
                "Нет @media (max-width: …) — мобильный блок обязателен (visual-polish)",
            )
        )
    # SaaS slate palette on STO/landing (do NOT match translateY via bare "slate")
    if re.search(
        r"(автосервис|моторхаус|сто|шиномонтаж|booking|/api/booking)",
        fe_blob,
        re.I,
    ) and re.search(
        r"#f8fafc|#f1f5f9|#e2e8f0|#64748b|#f8f9fb|#f8f9fa|--color-bg\s*:\s*#f8fafc|\bslate-\d+\b",
        css_blob,
        re.I,
    ):
        findings.append(
            _finding(
                "major",
                "saas_palette",
                "SaaS-slate палитра (#f8fafc) на авто-нише — возьми палитру отрасли из brief "
                "(для СТО часто тёмный бокс/янтарь, но не догма)",
            )
        )
    # Hero veil: any readable overlay OK — don't force 90deg stamp
    if re.search(
        r"(автосервис|моторхаус|сто|шиномонтаж|booking|/api/booking)",
        fe_blob,
        re.I,
    ):
        has_hero = bool(re.search(r"\.hero\b|#hero\b", css_blob, re.I))
        has_veil = bool(re.search(r"linear-gradient\s*\(", css_blob, re.I))
        if has_hero and not has_veil and not re.search(r"<img\b", fe_blob, re.I):
            findings.append(
                _finding(
                    "minor",
                    "flat_hero_veil",
                    "Hero слабо читается — добавь veil/градиент или img с контрастом",
                )
            )

        # --- taste: anti-bland ---
        # Browser-default blue nav / phone
        if re.search(r"""class=["'][^"']*\btop__nav\b|class=["'][^"']*\btop\b""", fe_blob, re.I):
            has_tel_color = bool(
                re.search(
                    r"\.tel\b[^{]*\{[^}]{0,200}color\s*:|\.top__nav\s+a\.tel\s*\{[^}]{0,200}color\s*:",
                    css_blob,
                    re.I | re.S,
                )
            )
            has_nav_color = bool(
                re.search(
                    r"\.top__nav\s+a\s*\{[^}]{0,180}color\s*:|\.top\s+a\s*\{[^}]{0,180}color\s*:",
                    css_blob,
                    re.I | re.S,
                )
            )
            if not has_tel_color or not has_nav_color:
                findings.append(
                    _finding(
                        "major",
                        "browser_blue_nav",
                        "Шапка: нет color у .top__nav a и/или .tel — будут синие ссылки браузера (taste.md)",
                    )
                )

        # Tiny vitrine thumbs
        if re.search(r"""id=["']vitrine["']|\.vitrine\b""", fe_blob + css_blob, re.I):
            m_h = re.search(
                r"\.vitrine(?:\s+img|)\s+img\s*\{[^}]*\bheight\s*:\s*(\d+)px",
                css_blob,
                re.I | re.S,
            )
            if not m_h:
                m_h = re.search(
                    r"\.vitrine\s+img\s*\{[^}]*\bheight\s*:\s*(\d+)px",
                    css_blob,
                    re.I | re.S,
                )
            h_px = int(m_h.group(1)) if m_h else 0
            if h_px and h_px < 260:
                findings.append(
                    _finding(
                        "major",
                        "tiny_vitrine",
                        f"Витрина слишком мелкая (height:{h_px}px < 280) — taste.md: ударные фото",
                    )
                )
            elif not h_px and re.search(r"\.vitrine\s+img\s*\{", css_blob, re.I):
                findings.append(
                    _finding(
                        "major",
                        "tiny_vitrine",
                        "Витрина img без явной высоты — сделай кадры крупнее (не postage-stamp)",
                    )
                )

        # Reviews exist but no layout CSS
        if re.search(r"<blockquote\b", fe_blob, re.I) and not re.search(
            r"\.reviews\s*\{|blockquote\s*\{[^}]*border-left",
            css_blob,
            re.I | re.S,
        ):
            findings.append(
                _finding(
                    "major",
                    "no_reviews_css",
                    "Есть blockquote, но нет .reviews grid / border-left — голый HTML (taste.md)",
                )
            )

        # Egg corporate H1
        h1_m = re.search(r"<h1\b[^>]*>([\s\S]*?)</h1>", fe_blob, re.I)
        if h1_m:
            h1 = re.sub(r"<[^>]+>", " ", h1_m.group(1))
            h1 = re.sub(r"\s+", " ", h1).strip()
            if re.search(
                r"(?i)профессиональн|качественн|комплексн\w*\s+сервис|лучший\s+сервис|вашего\s+авто",
                h1,
            ):
                findings.append(
                    _finding(
                        "major",
                        "egg_headline",
                        f"H1 яйцевой («{h1[:48]}…») — бан Профессиональный/Качественный (taste.md)",
                    )
                )

        # Per-user uniqueness: visible brand + no MotоrХаус stamp when brand differs
        has_uniq = bool(
            re.search(r"""<html\b[^>]*\bdata-uniq\s*=\s*['"][a-f0-9]{6,}""", fe_blob, re.I)
        )
        if not has_uniq:
            findings.append(
                _finding(
                    "minor",
                    "missing_uniq",
                    "Нет data-uniq — желательно, но важнее UNIQUE бренд/контент из брифа",
                )
            )
        brand_m = re.search(
            r"""class=["'][^"']*\bbrand\b[^"']*["'][^>]*>\s*([^<]{2,40})\s*<""",
            fe_blob,
            re.I,
        )
        brand_txt = (brand_m.group(1).strip() if brand_m else "") or ""
        has_motorhaus = bool(re.search(r"МоторХаус", fe_blob))
        has_kashir = bool(re.search(r"Каширск", fe_blob, re.I))
        has_stamp_phone = bool(re.search(r"120-45-67", fe_blob))
        if brand_txt and "МоторХаус" not in brand_txt and has_motorhaus:
            findings.append(
                _finding(
                    "major",
                    "clone_motorhaus",
                    f"Бренд «{brand_txt}», но на странице торчит чужой «МоторХаус» — stamp clone",
                )
            )
        if (
            brand_txt
            and "МоторХаус" not in brand_txt
            and has_kashir
            and has_stamp_phone
        ):
            findings.append(
                _finding(
                    "major",
                    "clone_motorhaus",
                    f"Бренд «{brand_txt}», но контакты штампа Каширское/120-45-67 — не UNIQUE",
                )
            )

        # Footer must have tel:
        if re.search(r"<footer\b", fe_blob, re.I) and not re.search(
            r"<footer\b[\s\S]{0,1200}href\s*=\s*[\"']tel:",
            fe_blob,
            re.I,
        ):
            findings.append(
                _finding(
                    "major",
                    "weak_footer",
                    "Footer без tel: ссылки — taste.md",
                )
            )

        # Why photo must differ from hero
        hero_ids = set(
            re.findall(
                r"""\.hero\b[\s\S]{0,500}photo-([0-9a-zA-Z_-]+)""",
                css_blob,
                re.I,
            )
        )
        why_ids = set(
            re.findall(
                r"""(?:why__media|#why)[\s\S]{0,400}photo-([0-9a-zA-Z_-]+)""",
                fe_blob + css_blob,
                re.I,
            )
        )
        if hero_ids and why_ids and hero_ids == why_ids:
            findings.append(
                _finding(
                    "major",
                    "dup_why_hero",
                    "Why использует тот же photo-ID что hero — нужен другой кадр (taste.md)",
                )
            )

        # Why section needs a CTA button (not just facts)
        if re.search(r"""id=["']why["']|class=["'][^"']*\bwhy\b""", fe_blob, re.I):
            why_chunk = re.search(
                r"""(?:id=["']why["']|class=["'][^"']*\bwhy\b)[\s\S]{0,1800}""",
                fe_blob,
                re.I,
            )
            chunk = why_chunk.group(0) if why_chunk else ""
            if chunk and not re.search(
                r"""class=["'][^"']*\bbtn\b|<a\b[^>]*\bhref|<button\b""", chunk, re.I
            ):
                findings.append(
                    _finding(
                        "minor",
                        "why_no_cta",
                        "Блок «почему мы» без CTA — добавь кнопку/ссылку если секция есть",
                    )
                )

        # If model used STO chrome classes, check nav/tel colors aren't browser-default
        if re.search(r"""class=["'][^"']*\btel\b""", fe_blob, re.I) and re.search(
            r"\.top__nav\s+a\s*\{", css_blob, re.I
        ):
            if not re.search(
                r"\.top__nav\s+a\.tel\b|\.tel\s*,\s*\.top__nav|\.tel\s*\{[^}]*color\s*:",
                css_blob,
                re.I,
            ):
                findings.append(
                    _finding(
                        "minor",
                        "tel_specificity",
                        "Nav/tel: задай явный color (не browser-blue)",
                    )
                )

    return findings


def _deck_content_findings(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """HTML decks under /src/deck or .slide sections."""
    findings: list[dict[str, Any]] = []
    deck_arts = [
        a
        for a in artifacts
        if (a.get("path") or "").startswith("/src/deck")
        or "slide" in ((a.get("content") or "")[:2000]).lower()
        and (a.get("path") or "").endswith(".html")
    ]
    if not deck_arts:
        # also detect many .slide in frontend
        for a in artifacts:
            body = a.get("content") or ""
            if (a.get("path") or "").endswith(".html") and body.count("slide") >= 3:
                deck_arts.append(a)
    if not deck_arts:
        return findings
    blob = "\n".join(a.get("content") or "" for a in deck_arts)
    slides = len(
        re.findall(r"""class=["'][^"']*\bslide\b|<section[^>]*slide""", blob, re.I)
    )
    if slides and slides < 6:
        findings.append(
            _finding(
                "major",
                "thin_deck",
                f"Презентация: slide={slides} < 6 — нужно ≥8 с текстом (content-fill)",
            )
        )
    ids = re.findall(r"images\.unsplash\.com/photo-([0-9a-zA-Z_-]+)", blob, re.I)
    if ids and len(set(ids)) < 2 and len(ids) >= 2:
        findings.append(
            _finding(
                "major",
                "duplicate_media",
                "В колоде один photo-ID на все слайды — нужны разные кадры из media pack",
            )
        )
    return findings


def flatten_css_for_preview(artifacts: list[dict[str, Any]], css_text: str) -> str:
    """Resolve @import of workspace CSS (esp. design tokens) into a single stylesheet."""
    by_path = {(a.get("path") or "").strip(): a for a in artifacts}
    seen: set[str] = set()

    def expand(text: str, from_path: str, depth: int = 0) -> str:
        if depth > 6:
            return text

        def repl(m: re.Match[str]) -> str:
            ref = (m.group(1) or m.group(2) or "").strip()
            if not ref or ref.startswith(("http://", "https://", "data:")):
                return m.group(0)
            resolved = _resolve_fe_rel(ref, from_path)
            if not resolved or resolved in seen:
                return "/* skipped import */\n"
            target = by_path.get(resolved)
            if not target:
                # try basename match under design/
                base = resolved.rsplit("/", 1)[-1]
                for p, a in by_path.items():
                    if p.endswith("/" + base) and p.startswith("/src/"):
                        target = a
                        resolved = p
                        break
            if not target:
                return m.group(0)
            seen.add(resolved)
            body = target.get("content") or ""
            return f"/* inlined {resolved} */\n" + expand(body, resolved, depth + 1) + "\n"

        return _CSS_IMPORT_RE.sub(repl, text)

    return expand(css_text or "", "/src/frontend/styles.css")


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
    if "/* inlined design tokens" in fe_blob:
        return []
    used = set(re.findall(r"var\(\s*--([a-zA-Z][\w-]*)", fe_blob))
    shared = design_vars & used
    fe_defines = set(re.findall(r"--([a-zA-Z][\w-]*)\s*:", fe_blob))
    # Landing industry pack inlined in styles.css is intentional (static demos break on @import)
    industry = {"asphalt", "shop", "band", "amber", "amber-hover", "metal"}
    if industry & fe_defines and len(fe_defines) >= 4:
        return []
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
    """Inline HTML+CSS+JS for Playwright set_content (no network).

    Resolves @import (design tokens) via flatten_css_for_preview so gate/preview
    match what a workspace http.server would serve after token inline.
    """
    by_path = {(a.get("path") or ""): a for a in arts}
    html = (by_path.get("/src/frontend/index.html") or {}).get("content") or ""
    if not html:
        for a in arts:
            if (a.get("path") or "").endswith(".html"):
                html = a.get("content") or ""
                break
    if not html.strip():
        return None
    # Prefer frontend styles; flatten @import against full artifact set (incl. design)
    css_parts: list[str] = []
    for a in arts:
        path = a.get("path") or ""
        if path.startswith("/src/frontend/") and (
            path.endswith(".css") or a.get("language") == "css"
        ):
            css_parts.append(a.get("content") or "")
        elif path.endswith(".css") and a.get("role") == "frontend":
            css_parts.append(a.get("content") or "")
    css = flatten_css_for_preview(arts, "\n".join(css_parts))
    # If FE styles empty but design tokens exist, still inject tokens
    if not css.strip():
        tok = (by_path.get("/src/design/tokens.css") or {}).get("content") or ""
        css = tok
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
        low = html.lower()
        idx = low.find("</head>")
        if idx >= 0:
            html = html[:idx] + f"<style>\n{css}\n</style>" + html[idx:]
        else:
            html = f"<style>{css}</style>" + html
    if js:
        low = html.lower()
        idx = low.find("</body>")
        if idx >= 0:
            html = (
                html[:idx]
                + f'<script type="module">\n{js}\n</script>'
                + html[idx:]
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
        msg = str(e)
        # VPS without Playwright browsers — don't tank app score
        if "Executable doesn't exist" in msg or "playwright" in msg.lower():
            findings.append(
                _finding(
                    "info",
                    "browser_smoke_skipped",
                    "Playwright browser не установлен — smoke пропущен",
                )
            )
        else:
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
    # Pass full artifact set so flatten can pull /src/design/tokens.css
    srcdoc = _frontend_srcdoc(artifacts)
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
