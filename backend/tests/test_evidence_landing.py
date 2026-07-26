"""Landing quality gates — traps that previously scored PASS@100."""

from app.evidence import (
    flatten_css_for_preview,
    scan_artifacts,
    score_from_findings,
)
from app.orchestrate import filter_studio_artifacts
from app.brief_expand import _fallback_autoservice


def _codes(findings: list[dict]) -> set[str]:
    return {f.get("code") for f in findings}


def test_placeholder_contact_is_major():
    arts = [
        {
            "path": "/src/frontend/index.html",
            "role": "frontend",
            "content": (
                "<html><body><a href='tel:+74950000000'>+7 (495) 000-00-00</a>"
                "<form><label>Имя</label><input></form></body></html>"
            ),
        }
    ]
    findings = scan_artifacts(arts)
    assert "placeholder_contact" in _codes(findings)
    score, _, gate = score_from_findings(findings)
    assert gate != "PASS"
    assert score < 100


def test_missing_asset_hero_jpg():
    arts = [
        {
            "path": "/src/frontend/index.html",
            "role": "frontend",
            "content": "<html><body><header class='hero'>МоторХаус</header></body></html>",
        },
        {
            "path": "/src/frontend/styles.css",
            "role": "frontend",
            "content": (
                ".hero { min-height: 80vh; "
                "background: url('assets/hero-workshop.jpg') center/cover; }"
            ),
        },
    ]
    findings = scan_artifacts(arts)
    assert "missing_asset" in _codes(findings)
    _, _, gate = score_from_findings(findings)
    assert gate != "PASS"


def test_broken_css_import_tokens():
    arts = [
        {
            "path": "/src/frontend/index.html",
            "role": "frontend",
            "content": "<html><body><h1>x</h1></body></html>",
        },
        {
            "path": "/src/frontend/styles.css",
            "role": "frontend",
            "content": "@import url('../design/tokens.css');\nbody{color:red}",
        },
    ]
    findings = scan_artifacts(arts)
    assert "broken_css_import" in _codes(findings)


def test_api_orphan_booking_without_backend():
    arts = [
        {
            "path": "/src/frontend/index.html",
            "role": "frontend",
            "content": (
                "<html><body><form id='booking-form'>"
                "<label>Имя</label><input name='name'>"
                "<button type='submit'>Go</button></form>"
                "<script src='./app.js'></script></body></html>"
            ),
        },
        {
            "path": "/src/frontend/app.js",
            "role": "frontend",
            "content": (
                "form.addEventListener('submit', async (e) => {"
                " e.preventDefault();"
                " await fetch('/api/booking', {method:'POST', body:'{}'});"
                "});"
            ),
        },
    ]
    findings = scan_artifacts(arts)
    assert "api_orphan" in _codes(findings)
    _, _, gate = score_from_findings(findings)
    assert gate != "PASS"


def test_fake_form_success_in_catch():
    arts = [
        {
            "path": "/src/frontend/index.html",
            "role": "frontend",
            "content": "<html><body><form id='f'><label>x</label><input></form></body></html>",
        },
        {
            "path": "/src/frontend/app.js",
            "role": "frontend",
            "content": (
                "form.addEventListener('submit', async (e) => {"
                " e.preventDefault();"
                " try {"
                "  const r = await fetch('/api/booking', {method:'POST'});"
                "  if (!r.ok) throw new Error('x');"
                " } catch (err) {"
                "  status.textContent = 'Заявка отправлена. Мы свяжемся с вами';"
                " }"
                "});"
            ),
        },
    ]
    findings = scan_artifacts(arts)
    codes = _codes(findings)
    assert "fake_form_success" in codes
    # also orphan API (no backend) — both major
    assert "api_orphan" in codes


def test_filter_inlines_design_tokens_not_import_only():
    arts = [
        {
            "path": "/src/design/tokens.css",
            "role": "design",
            "content": ":root { --color-accent: #c47a2c; }",
        },
        {
            "path": "/src/frontend/styles.css",
            "role": "frontend",
            "content": "body { color: var(--color-accent); }",
        },
        {
            "path": "/src/frontend/index.html",
            "role": "frontend",
            "content": "<html><body>ok</body></html>",
        },
    ]
    out = filter_studio_artifacts(arts)
    by = {a["path"]: a for a in out}
    styles = by["/src/frontend/styles.css"]["content"]
    assert "/* inlined design tokens" in styles
    assert "--color-accent" in styles
    assert "@import" not in styles or "tokens.css" not in styles
    # After inline, broken_css_import should not fire
    findings = scan_artifacts(out)
    assert "broken_css_import" not in _codes(findings)


def test_flatten_css_resolves_token_import():
    arts = [
        {
            "path": "/src/design/tokens.css",
            "content": ":root { --ink: #111; }",
        },
        {
            "path": "/src/frontend/styles.css",
            "content": "@import url('../design/tokens.css');\nbody{color:var(--ink)}",
        },
    ]
    flat = flatten_css_for_preview(
        arts, arts[1]["content"]
    )
    assert "--ink" in flat
    assert "inlined" in flat.lower() or ":root" in flat


def test_generic_fallback_phone_not_zeros():
    data = _fallback_autoservice("сделай лендинг для кофейни")
    phone = data["contacts"]["phone"]
    assert "000-00-00" not in phone


def test_no_hero_media_and_thin_landing_fail_skeleton():
    """Cheap-model navy void + 2KB shell must not PASS@100."""
    arts = [
        {
            "path": "/src/frontend/index.html",
            "role": "frontend",
            "content": (
                "<!DOCTYPE html><html lang='ru'><body>"
                "<header><strong>МоторХаус</strong></header>"
                "<section class='hero'><h1>Ремонт авто</h1>"
                "<a href='#booking'>Записаться</a></section>"
                "<section id='services'><h2>Услуги</h2>"
                "<article><h3>ТО</h3><p>от 3000 ₽</p></article>"
                "<article><h3>Шины</h3><p>от 1800 ₽</p></article>"
                "</section>"
                "<section id='booking'><form id='booking-form'>"
                "<label>Имя</label><input name='name'>"
                "<button>Отправить</button></form></section>"
                "</body></html>"
            ),
        },
        {
            "path": "/src/frontend/styles.css",
            "role": "frontend",
            "content": ".hero{min-height:70vh;background:#1e293b;color:#fff}",
        },
        {
            "path": "/src/frontend/app.js",
            "role": "frontend",
            "content": "fetch('/api/booking',{method:'POST'})",
        },
        {
            "path": "/src/backend/routers/booking.py",
            "role": "backend",
            "content": "@router.post('/api/booking')\ndef booking(): return {'ok': True}\n",
        },
    ]
    findings = scan_artifacts(arts)
    codes = _codes(findings)
    assert "no_hero_media" in codes
    assert "thin_landing" in codes
    score, _, gate = score_from_findings(findings)
    assert gate != "PASS"
    assert score < 100


def test_remote_hero_rich_landing_avoids_skeleton_majors():
    html = (
        "<!DOCTYPE html><html lang='ru'><body>"
        "<section class='hero'><h1>МоторХаус</h1><p>Все виды работ</p></section>"
        "<section id='services'><h2>Услуги</h2>"
        + "".join(
            f"<article><h3>Услуга{i}</h3><p>Описание работ</p>"
            f"<p class='price'>от {1000 + i * 100} ₽</p></article>"
            for i in range(6)
        )
        + "</section>"
        "<section id='steps'><h2>Как записаться</h2><ol>"
        "<li>Заявка</li><li>Звонок</li><li>Слот</li></ol></section>"
        "<section id='why'><h2>Гарантия</h2><ul><li>90 дней</li></ul></section>"
        "<section id='reviews'><h2>Отзывы</h2><blockquote>Ок</blockquote></section>"
        "<section id='booking'><h2>Запись</h2>"
        "<form id='booking-form'><label>Имя</label><input name='name'>"
        "<label>Тел</label><input name='phone'>"
        "<button>Отправить</button></form></section>"
        "<footer>Каширское ш. · +7 (495) 120-45-67</footer>"
        "</body></html>"
    )
    arts = [
        {"path": "/src/frontend/index.html", "role": "frontend", "content": html},
        {
            "path": "/src/frontend/styles.css",
            "role": "frontend",
            "content": (
                ".hero{min-height:72vh;background:"
                "url('https://images.unsplash.com/photo-1486262715619-67b85e0b08d3"
                "?auto=format&fit=crop&w=2000&q=80') center/cover}"
            ),
        },
    ]
    codes = _codes(scan_artifacts(arts))
    assert "no_hero_media" not in codes
    assert "thin_landing" not in codes
    assert "empty_hero" not in codes


def test_autoservice_fallback_has_remote_hero_url():
    data = _fallback_autoservice("сайт автосервиса полного цикла")
    md = data["brief_md"]
    assert "images.unsplash.com" in md
    assert data["hero_media"]["primary"].startswith("https://")


def test_resolve_team_forces_backend_for_booking_api():
    from app.orchestrate import resolve_team

    team = resolve_team(
        "ui",
        "standard",
        agents_n=2,
        user_text="сайт автосервиса с формой POST /api/booking",
    )
    assert "backend" in team
    assert "frontend" in team or "design" in team
