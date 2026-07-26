"""UI Crew: Author + Critics + Gate (mocked upstream / web)."""

from __future__ import annotations

import asyncio

from app.fusion.model_power import pick_author, pick_critics, power_score
from app.fusion.ui_crew import (
    _gate_keeps_revise,
    _mobile_gaps,
    execute_ui_crew,
    is_ui_crew_task,
)


def test_pick_author_strongest():
    panel = ["gemini-3.1-pro", "claude-opus-4-8", "deepseek-v4-pro"]
    assert pick_author(panel) == "claude-opus-4-8"
    assert power_score("claude-opus-4-8") > power_score("gemini-3.1-pro")


def test_pick_critics_prefer_other_families():
    author = "claude-opus-4-8"
    panel = ["claude-opus-4-8", "claude-sonnet-4-5", "gemini-3.1-pro", "gpt-5.2"]
    critics = pick_critics(panel, author, n=2)
    assert author not in critics
    assert len(critics) == 2
    # Prefer non-claude first
    assert "claude" not in critics[0]


def test_is_ui_crew_task_heuristics():
    assert is_ui_crew_task(task_kind="ui", user_q="hello")
    assert is_ui_crew_task(task_kind="general", user_q="Сделай одностраничный сайт СТО")
    assert not is_ui_crew_task(task_kind="light", user_q="сколько будет 2+2")


def test_mobile_gaps_flags_missing_phone_css():
    bare = "<!doctype html><html><body><h1 style='font-size:90px'>X</h1><nav>a b c</nav></body></html>"
    gaps = _mobile_gaps(bare)
    assert any("viewport" in g.lower() or "@media" in g.lower() for g in gaps)

    okish = (
        '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
        "<style>@media (max-width:480px){nav{display:none}.hamburger{display:block}"
        "input{font-size:16px}}</style></head>"
        "<body><button class='hamburger' aria-expanded='false'>☰</button>"
        "<form><input style='font-size:16px'></form></body></html>"
    )
    assert len(_mobile_gaps(okish)) <= 2


def test_gate_rollback_on_short_or_incomplete():
    v1 = "<!doctype html><html><body>" + ("x" * 3000) + "@media (max-width:600px){}</body></html>"
    assert _gate_keeps_revise(v1, "<html>tiny</html>") is False
    assert _gate_keeps_revise(v1, v1.replace("@media", "/*gone*/")) is False
    v2 = v1 + "<!-- polish -->"
    assert _gate_keeps_revise(v1, v2) is True


def test_gate_requires_media_when_v1_lacks_it():
    v1 = "<!doctype html><html><head></head><body>" + ("y" * 2500) + "</body></html>"
    bad = v1 + "<!-- still no media -->"
    assert _gate_keeps_revise(v1, bad) is False
    good = (
        '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
        "<style>@media (max-width:480px){body{padding:0}}</style></head><body>"
        + ("y" * 2500)
        + "</body></html>"
    )
    assert _gate_keeps_revise(v1, good) is True


def _upstream_factory(answers: dict[str, str], *, tokens: int = 20):
    async def _call(model, messages, **kwargs):
        # Critic calls get JSON; author/revise keyed by call count per model
        text = answers.get(model, "")
        sys = ""
        for m in messages or []:
            if m.get("role") == "system":
                sys = str(m.get("content") or "")
                break
        if "critic" in sys.lower() and model in answers:
            # allow per-role override
            key = f"{model}::critic"
            if key in answers:
                text = answers[key]
        if "revising" in sys.lower() or "YOUR OWN HTML" in sys:
            key = f"{model}::revise"
            if key in answers:
                text = answers[key]
        return {
            "ok": bool(str(text).strip()),
            "text": text,
            "prompt_tokens": tokens if text else 0,
            "completion_tokens": tokens if text else 0,
        }

    return _call


def test_execute_ui_crew_happy_path(monkeypatch):
    v1 = (
        "<!doctype html><html><head><title>Motohaus</title>"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<style>@media (max-width:480px){body{padding:0}.grid{display:block}}"
        "input{font-size:16px}</style></head>"
        "<body><button class='hamburger' aria-expanded='false'>menu</button>"
        "<h1>Motohaus</h1><form><input style='font-size:16px'></form>"
        + ("section" * 400)
        + "</body></html>"
    )
    v2 = v1.replace("</body>", "<nav>Услуги</nav></body>")
    critique = (
        '{"upgrades":["Add sticky nav","Richer services grid"],'
        '"must_fix":[],"praise":["Brand hero"],"refs_used":["https://example.com"]}'
    )

    async def fake_research(user_q: str):
        return {
            "ok": True,
            "degraded": False,
            "backend": "test",
            "queries": ["sto landing"],
            "refs": [
                {
                    "url": "https://example.com/sto",
                    "title": "STO ref",
                    "snippet": "hero + services",
                    "excerpt": "Dark garage atmosphere, clear CTA",
                }
            ],
        }

    monkeypatch.setattr(
        "app.fusion.ui_crew.research_pack_for_critics", fake_research
    )

    async def _run():
        return await execute_ui_crew(
            panel=["claude-opus-4-8", "gemini-3.1-pro", "deepseek-v4-pro"],
            leader="claude-opus-4-8",
            messages=[{"role": "user", "content": "Сделай сайт СТО Motohaus"}],
            user_q="Сделай сайт СТО Motohaus",
            upstream_call=_upstream_factory(
                {
                    "claude-opus-4-8": v1,
                    "claude-opus-4-8::revise": v2,
                    "gemini-3.1-pro::critic": critique,
                    "gemini-3.1-pro": critique,
                    "deepseek-v4-pro::critic": critique,
                    "deepseek-v4-pro": critique,
                }
            ),
        )

    out = asyncio.run(_run())
    assert out.disaster is False
    assert out.leader == "claude-opus-4-8"
    assert out.meta.get("author") == "claude-opus-4-8"
    assert set(out.meta.get("critics") or []) == {"gemini-3.1-pro", "deepseek-v4-pro"}
    assert out.routed_by == "ui_author_critics_web"
    assert "Услуги" in out.answer
    assert out.meta.get("web", {}).get("ok") is True
    assert "https://example.com" in (out.meta.get("refs_used") or [])
    assert out.meta.get("author") == pick_author(
        ["claude-opus-4-8", "gemini-3.1-pro", "deepseek-v4-pro"]
    )


def test_execute_ui_crew_rollback(monkeypatch):
    v1 = (
        "<!doctype html><html><body>"
        + ("x" * 3000)
        + "@media (max-width:600px){}<form></form></body></html>"
    )
    bad = "<html>oops</html>"
    critique = '{"upgrades":["break it"],"must_fix":[],"praise":[]}'

    async def fake_research(user_q: str):
        return {"ok": False, "degraded": True, "backend": "off", "queries": [], "refs": []}

    monkeypatch.setattr(
        "app.fusion.ui_crew.research_pack_for_critics", fake_research
    )

    async def _run():
        return await execute_ui_crew(
            panel=["claude-opus-4-8", "gemini-3.1-pro"],
            leader="claude-opus-4-8",
            messages=[{"role": "user", "content": "landing page"}],
            user_q="landing page html",
            upstream_call=_upstream_factory(
                {
                    "claude-opus-4-8": v1,
                    "claude-opus-4-8::revise": bad,
                    "gemini-3.1-pro": critique,
                }
            ),
        )

    out = asyncio.run(_run())
    assert out.routed_by == "ui_author_rollback"
    assert out.answer == v1
    assert out.early_exit == "revise_regressed"
