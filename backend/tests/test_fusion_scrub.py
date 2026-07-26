"""Story 1.4 — scrub once at Edge→Policy + Brief contract."""

from __future__ import annotations

from unittest.mock import patch

from app.fusion import (
    build_satellite_brief,
    prepare_messages_for_policy,
    scrub_messages,
    scrub_secrets,
)
from app.fusion._monolith import _satellite_messages


def test_scrub_api_key_bearer_private_key_email():
    raw = (
        "key sk-abcdefghijklmnopqrstuvwxyz0123456789 "
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def "
        "contact leak@secret.example "
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAK\n-----END RSA PRIVATE KEY-----"
    )
    out = scrub_secrets(raw)
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in out
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in out
    assert "leak@secret.example" not in out
    assert "BEGIN RSA PRIVATE KEY" not in out
    assert "[REDACTED]" in out


def test_scrub_idempotent():
    raw = "token sk-abcdefghijklmnopqrstuvwxyz0123456789 end"
    once = scrub_secrets(raw)
    twice = scrub_secrets(once)
    assert once == twice
    assert once.count("[REDACTED]") == 1


def test_prepare_messages_scrubs_once_at_boundary():
    msgs = [
        {
            "role": "user",
            "content": "use sk-abcdefghijklmnopqrstuvwxyz0123456789 please",
        }
    ]
    call_count = {"n": 0}
    real_scrub = scrub_secrets

    def counting(text: str) -> str:
        call_count["n"] += 1
        return real_scrub(text)

    with patch("app.fusion._monolith.scrub_secrets", side_effect=counting):
        out = prepare_messages_for_policy(msgs)
    assert "[REDACTED]" in out[0]["content"]
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in out[0]["content"]
    # sanitize flattens → one scrub_secrets call for the user content
    assert call_count["n"] == 1


def test_scrub_messages_masks_upstream_payload():
    out = scrub_messages(
        [{"role": "user", "content": "Bearer FAKESECRET_g2h3i4j5k6l7m8n9o0p1"}]
    )
    assert "abc123xyz789tokenvalue" not in out[0]["content"]
    assert "Bearer [REDACTED]" in out[0]["content"]


def test_brief_only_last_assistant_errors_goal():
    messages = [
        {"role": "system", "content": "huge system dump with skills and tools " * 40},
        {
            "role": "assistant",
            "content": "ValueError: boom\nTraceback (most recent call last):\n  File x",
        },
        {"role": "user", "content": "fix the crash in login"},
    ]
    brief = build_satellite_brief(messages, user_q="fix the crash in login")
    d = brief.as_dict()
    assert set(d.keys()) == {"last_assistant", "errors", "goal"}
    assert "fix the crash" in d["goal"]
    assert d["last_assistant"]
    assert "ValueError" in d["errors"] or "Traceback" in d["errors"]
    # Must not carry full system dump
    assert "huge system dump" not in brief.as_prompt_block()


def test_satellite_messages_use_brief_contract():
    messages = [
        {"role": "system", "content": "CURSOR_SKILLS_DUMP=" + ("x" * 5000)},
        {"role": "assistant", "content": "TypeError: none\n"},
        {"role": "user", "content": "почини ошибку"},
    ]
    sat = _satellite_messages(messages, "почини ошибку")
    blob = "\n".join(str(m.get("content")) for m in sat)
    assert "CURSOR_SKILLS_DUMP" not in blob
    assert "почини ошибку" in blob
    assert "Last assistant:" in blob or "TypeError" in blob
    assert "Goal:" in blob
