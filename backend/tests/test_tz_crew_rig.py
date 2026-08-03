"""TZ ZeusCode crew & rig — acceptance smoke for new modules."""

from __future__ import annotations

from app.fusion.context_compress import compress_history
from app.fusion.error_bank import note_log_digest, reset_error_bank_for_tests
from app.fusion.metrics import (
    empty_rate,
    note_response_emptiness,
    note_token_profile,
    reset_metrics_for_tests,
    snapshot_metrics,
)
from app.fusion.project_memory import (
    format_memory_block,
    memory_key,
    remember_decision,
    reset_memory_for_tests,
)
from app.fusion.prompt_assembly import assemble_messages, extract_client_system
from app.fusion.taste import extract_urls, format_taste_block, refs_for
from app.fusion.verify import GateSignals, compute_unified_gate, machine_signals_from_client
from app.client_hands import HANDS_SYSTEM_APPEND


def test_prompt_assembly_stable_prefix_order():
    msgs = assemble_messages(
        role_system="ROLE",
        client_system="CLIENT SKILLS",
        project_memory="decided X",
        taste_refs="linear.app",
        artifacts="brief: y",
        compressed_history=[{"role": "user", "content": "old"}],
        fresh_user="new ask",
        hands_append=True,
    )
    sys0 = msgs[0]["content"]
    assert sys0.index("ROLE") < sys0.index("CLIENT SKILLS")
    assert sys0.index("CLIENT SKILLS") < sys0.index("project memory")
    assert HANDS_SYSTEM_APPEND.strip()[:20] in sys0
    assert msgs[-1] == {"role": "user", "content": "new ask"}
    # Client system preserved (append, not replace)
    assert "CLIENT SKILLS" in extract_client_system([{"role": "system", "content": "CLIENT SKILLS"}])


def test_machine_signals_force_red():
    gate, reasons = compute_unified_gate(
        GateSignals(
            mini_passed=True,
            tests_failed=True,
            allow_green_without_mini=False,
        )
    )
    assert gate == "RED"
    assert "tests_failed" in reasons

    gate2, reasons2 = compute_unified_gate(
        GateSignals(
            mini_passed=True,
            patch_applied=False,
        )
    )
    assert gate2 == "RED"
    assert "patch_not_applied" in reasons2

    mapped = machine_signals_from_client(
        {"exec": {"tests_ok": False, "compile_ok": True, "patch_applied": True}}
    )
    assert mapped["tests_failed"] is True
    assert mapped["compile_failed"] is False
    assert mapped["patch_applied"] is True


def test_empty_rate_and_token_profile():
    reset_metrics_for_tests()
    note_response_emptiness(empty=True, disaster=True)
    note_response_emptiness(empty=False)
    note_response_emptiness(empty=False)
    note_token_profile(prompt_tokens=1000, completion_tokens=10, cached_tokens=800)
    snap = snapshot_metrics()
    assert snap["empty_responses"] == 1
    assert snap["non_empty_responses"] == 2
    assert abs(empty_rate() - 33.333) < 0.01 or snap["empty_rate"] == 33.333
    assert snap["cached_tokens_total"] == 800
    assert snap["cache_hit_pct"] == 80.0
    assert snap["disaster_total"] == 1


def test_project_memory_and_taste():
    reset_memory_for_tests()
    key = memory_key(project_id="demo")
    remember_decision(key, "use JWT")
    block = format_memory_block(key)
    assert "JWT" in block
    urls = extract_urls("look at https://linear.app please")
    assert urls == ["https://linear.app"]
    refs = refs_for("landing page", user_urls=urls)
    assert refs[0]["url"] == "https://linear.app"
    assert "linear" in format_taste_block("landing", user_urls=urls).lower()


def test_error_bank_promotes_rule():
    reset_error_bank_for_tests()
    dig = {"summary": "ModuleNotFoundError: foo_bar_unique_xyz", "critical": True}
    assert note_log_digest(dig) is None
    assert note_log_digest(dig) is None
    promoted = note_log_digest(dig)
    assert promoted and "foo_bar_unique_xyz" in promoted


def test_compress_history_keeps_tail():
    hist = [{"role": "user", "content": f"m{i}" * 100} for i in range(12)]
    out = compress_history(hist, keep_last=4, max_total_chars=3000)
    assert len(out) <= 8
    assert out[-1]["content"].startswith("m11")


def test_disaster_no_charge():
    from app.routers.chat import _charge_amounts, _ensure_non_empty_completion

    data = {
        "_fusion_result": {
            "path": "FAST",
            "disaster": True,
            "disaster_code": "fusion_disaster",
            "branches": [
                {
                    "model_id": "gpt-5.4",
                    "billable_state": "completed",
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                }
            ],
        },
        "choices": [{"message": {"role": "assistant", "content": ""}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    up, charged, pt, ct = _charge_amounts(data, "gpt-5.4")
    assert charged == 0.0 and up == 0.0
    assert _ensure_non_empty_completion(data) is True
    assert data["choices"][0]["message"]["content"].strip()
