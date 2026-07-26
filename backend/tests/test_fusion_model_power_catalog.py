"""Every catalog model must have an explicit power_score entry."""

from __future__ import annotations

from app.catalog import public_catalog
from app.fusion.model_power import _POWER, missing_explicit_scores, power_score


def test_all_catalog_models_have_explicit_power():
    miss = missing_explicit_scores()
    assert miss == [], f"missing power scores: {miss}"


def test_catalog_ids_nonzero_scores():
    for row in public_catalog():
        mid = str(row["id"])
        assert mid in _POWER
        assert power_score(mid) > 0


def test_chat_beats_image_for_author_pick():
    from app.fusion.model_power import pick_author

    assert pick_author(["google-nano-banana-pro", "claude-opus-4-8", "kling-3.0"]) == "claude-opus-4-8"
