"""Ask / chitchat must never inflate into design+frontend."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.orchestrate import resolve_team
from app.skills import infer_intent_from_task


def test_infer_chitchat_as_ask():
    for t in (
        "как дела",
        "как дела?",
        "привет",
        "Привет!",
        "hello",
        "что нового",
        "спасибо",
        "что ты умеешь?",
    ):
        assert infer_intent_from_task(t) == "ask", t


def test_infer_build_tasks_not_ask():
    assert infer_intent_from_task("лендинг для кофейни сделать") == "ui"
    assert infer_intent_from_task("добавь POST /api/items") == "api"


def test_resolve_ask_never_inflates_with_agents_n():
    for n in (1, 2, 3, 4):
        team = resolve_team("feature", "standard", agents_n=n, user_text="как дела")
        assert team == ["general"], (n, team)
        team2 = resolve_team("feature", "ultra", agents_n=n, user_text="привет")
        assert team2 == ["general"], (n, team2)


def test_resolve_explicit_ask_chip():
    assert resolve_team("ask", "standard", agents_n=4, user_text="как дела") == [
        "general"
    ]


def test_resolve_landing_still_builds():
    team = resolve_team(
        "feature", "standard", agents_n=2, user_text="лендинг для кофейни сделать"
    )
    assert "frontend" in team
    assert "general" not in team
    assert team[0] in ("frontend", "design")
