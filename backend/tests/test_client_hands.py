from app.client_hands import (
    apply_client_hands_policy,
    detect_external_coding_client,
    looks_like_hands_refusal,
)


def test_detect_aider_from_system():
    msgs = [
        {
            "role": "system",
            "content": "Aider is an AI programming tool. Act as an expert software developer.",
        },
        {"role": "user", "content": "run pwd"},
    ]
    assert detect_external_coding_client(messages=msgs) == "aider"


def test_detect_header():
    assert detect_external_coding_client(client_header="aider") == "aider"


def test_apply_appends_system():
    out = apply_client_hands_policy([{"role": "user", "content": "hi"}], client="aider")
    assert out[0]["role"] == "system"
    assert "client hands" in out[0]["content"]
    assert out[1]["content"] == "hi"


def test_refusal_heuristic():
    assert looks_like_hands_refusal("I cannot run terminal commands on your system.")
    assert not looks_like_hands_refusal("Applied edit to notes/x.txt")
