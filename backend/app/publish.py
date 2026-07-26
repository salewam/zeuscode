"""Public free hosting for sites/apps built by Zeus agents.

Stores under data/public/<slug>/ and serves at /go/<slug>/.
Always injects a subtle «Сделано на ZeusCode» badge unless already present.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path
from typing import Any

from app.config import get_settings

settings = get_settings()

_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ROOT = _ROOT / "data" / "public"

_BADGE_MARKERS = (
    "zeus-badge",
    "сделано на zeuscode",
    "made with zeuscode",
    "made on zeuscode",
)

_BADGE_HTML = """
<a class="zeus-badge" href="{home}" target="_blank" rel="noopener noreferrer">Сделано на ZeusCode</a>
<style id="zeus-badge-css">
.zeus-badge{{
  position:fixed;right:14px;bottom:12px;z-index:2147483646;
  font:500 11px/1.25 system-ui,-apple-system,Segoe UI,sans-serif;
  letter-spacing:.02em;text-decoration:none;
  color:rgba(120,120,120,.42);pointer-events:auto;
  transition:color .2s ease,opacity .2s ease;
}}
.zeus-badge:hover{{color:rgba(120,120,120,.78)}}
</style>
""".strip()


def public_base_url() -> str:
    return (settings.APP_PUBLIC_URL or "https://zeuscode.ru").rstrip("/")


def ensure_public_root() -> Path:
    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    return PUBLIC_ROOT


def _slugify(text: str, *, fallback: str = "site") -> str:
    raw = (text or "").strip().lower()
    raw = raw.replace("ё", "e")
    # translit-ish for common RU letters used in brand names
    table = str.maketrans(
        {
            "а": "a",
            "б": "b",
            "в": "v",
            "г": "g",
            "д": "d",
            "е": "e",
            "ж": "zh",
            "з": "z",
            "и": "i",
            "й": "y",
            "к": "k",
            "л": "l",
            "м": "m",
            "н": "n",
            "о": "o",
            "п": "p",
            "р": "r",
            "с": "s",
            "т": "t",
            "у": "u",
            "ф": "f",
            "х": "h",
            "ц": "c",
            "ч": "ch",
            "ш": "sh",
            "щ": "sch",
            "ъ": "",
            "ы": "y",
            "ь": "",
            "э": "e",
            "ю": "yu",
            "я": "ya",
        }
    )
    raw = raw.translate(table)
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = fallback
    return slug[:48].strip("-") or fallback


def has_zeus_badge(html: str) -> bool:
    low = (html or "").lower()
    return any(m in low for m in _BADGE_MARKERS)


def inject_zeus_badge(html: str) -> str:
    """Insert semi-transparent ZeusCode credit before </body> (or append)."""
    if has_zeus_badge(html):
        return html
    badge = _BADGE_HTML.format(home=public_base_url())
    if re.search(r"</body\s*>", html, flags=re.I):
        return re.sub(r"</body\s*>", badge + "\n</body>", html, count=1, flags=re.I)
    if re.search(r"</html\s*>", html, flags=re.I):
        return re.sub(r"</html\s*>", badge + "\n</html>", html, count=1, flags=re.I)
    return html.rstrip() + "\n" + badge + "\n"


def extract_html_document(text: str) -> str | None:
    """Pull a full HTML document from model output / fenced blocks."""
    if not text:
        return None
    # fenced ```html ... ```
    m = re.search(r"```(?:html|HTML)\s*\n([\s\S]*?)```", text)
    if m:
        cand = m.group(1).strip()
        if "<html" in cand.lower() or "<!doctype" in cand.lower() or "<body" in cand.lower():
            return cand
    # raw document
    low = text.lower()
    if "<!doctype html" in low or "<html" in low:
        start = re.search(r"(<!doctype html|<html\b)", text, flags=re.I)
        if start:
            chunk = text[start.start() :].strip()
            end = re.search(r"</html\s*>", chunk, flags=re.I)
            if end:
                return chunk[: end.end()]
            return chunk
    return None


def _unique_slug(base: str) -> str:
    ensure_public_root()
    slug = base
    if not (PUBLIC_ROOT / slug).exists():
        return slug
    for _ in range(8):
        cand = f"{base}-{secrets.token_hex(2)}"
        if not (PUBLIC_ROOT / cand).exists():
            return cand
    return f"{base}-{int(time.time())}"


def publish_html(
    html: str,
    *,
    title: str | None = None,
    slug: str | None = None,
    extra_files: dict[str, str | bytes] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write site to data/public/<slug>/ and return public URL."""
    ensure_public_root()
    html = inject_zeus_badge(html)
    base = _slugify(slug or title or "site")
    final_slug = _unique_slug(base)
    dest = PUBLIC_ROOT / final_slug
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "index.html").write_text(html, encoding="utf-8")
    for rel, content in (extra_files or {}).items():
        rel_clean = rel.lstrip("/").replace("..", "")
        if not rel_clean or rel_clean == "index.html":
            continue
        path = dest / rel_clean
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(str(content), encoding="utf-8")
    info = {
        "slug": final_slug,
        "title": title or final_slug,
        "created_at": int(time.time()),
        "url": f"{public_base_url()}/go/{final_slug}/",
        **(meta or {}),
    }
    (dest / ".zeus-meta.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return info


def publish_frontend_dir(
    frontend_dir: Path,
    *,
    title: str | None = None,
    slug: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Publish a Studio /src/frontend folder (index.html + assets)."""
    root = Path(frontend_dir)
    entry = root / "index.html"
    if not entry.is_file():
        return None
    html = entry.read_text(encoding="utf-8", errors="replace")
    extras: dict[str, str | bytes] = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel in {".zeus-meta.json", "index.html"} or rel.startswith("."):
            continue
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff2", ".woff"}:
            extras[rel] = p.read_bytes()
        else:
            extras[rel] = p.read_text(encoding="utf-8", errors="replace")
    return publish_html(html, title=title, slug=slug, extra_files=extras, meta=meta)


def site_dir(slug: str) -> Path | None:
    clean = _slugify(slug)
    path = PUBLIC_ROOT / clean
    if path.is_dir() and (path / "index.html").is_file():
        return path
    return None


def append_publish_note(answer: str, url: str) -> str:
    note = f"\n\n---\n🔗 Живая ссылка: {url}\n"
    if url in (answer or ""):
        return answer
    return (answer or "").rstrip() + note


def enrich_answer_with_publish(answer: str, *, title: str | None = None) -> str:
    """If answer contains a full HTML site/app — badge + free /go/<slug>/ link."""
    html = extract_html_document(answer)
    if not html or len(html) < 500:
        return answer
    # Heuristic: real page, not a tiny snippet
    low = html.lower()
    if "<body" not in low and "<!doctype" not in low and "<html" not in low:
        return answer
    try:
        info = publish_html(html, title=title)
    except Exception:
        return answer
    badged = inject_zeus_badge(html)
    out = answer
    if html in out:
        out = out.replace(html, badged, 1)
    return append_publish_note(out, info["url"])
