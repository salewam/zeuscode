"""Live two-turn smoke for the doer prompt cache.

Turn 1 bootstraps the crew; turn 2 replays the same transcript plus one tool
result, which is exactly the shape a tool loop grows into. A healthy run keeps
the transcript as a shared prefix, so the provider reports cache hits on the
second turn.

    PYTHONPATH=backend .venv/bin/python backend/scripts/smoke_prompt_cache.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("ZEUS_SMOKE_BASE", "http://127.0.0.1:8081/v1")
KEY_FILE = os.environ.get("ZEUS_SMOKE_KEY_FILE", "/tmp/zeus_bench.key")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command in the repository.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    }
]

# Padding makes the shared prefix long enough for a provider to bother caching.
BULK = "\n".join(f"line {i}: def helper_{i}(value): return value * {i}" for i in range(900))


def _post(path: str, payload: dict, key: str) -> dict:
    request = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "X-Zeus-Session-Id": "smoke-prompt-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def _plan_fingerprint(data: dict) -> str:
    crew = (data.get("onestack") or {}).get("crew_state") or {}
    plan = str(crew.get("plan_digest") or "")
    return f"len={len(plan)} head={plan[:60]!r}"


def _cache_prefix(data: dict) -> tuple[str, int]:
    row = (data.get("onestack") or {}).get("cache_prefix") or {}
    return str(row.get("sha256") or ""), int(row.get("bytes") or 0)


def _branch_cache(data: dict) -> tuple[int, int]:
    prompt = cached = 0
    onestack = data.get("onestack") or {}
    for branch in onestack.get("branches") or []:
        usage = branch.get("usage") if isinstance(branch.get("usage"), dict) else {}
        b_prompt = int(branch.get("prompt_tokens") or usage.get("prompt_tokens") or 0)
        b_cached = int(usage.get("cached_tokens") or branch.get("cached_tokens") or 0)
        prompt += b_prompt
        cached += b_cached
        print(
            f"    branch role={branch.get('role')} model={branch.get('model')} "
            f"prompt={b_prompt} cached={b_cached}"
        )
    return prompt, cached


def main() -> int:
    with open(KEY_FILE, encoding="utf-8") as handle:
        key = handle.read().strip()

    system = "You are a coding agent. Use the bash tool for every action."
    user = (
        "Here is the module under test:\n"
        f"{BULK}\n\n"
        "Find why helper_7 returns the wrong value and fix it."
    )
    base_messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    print("turn 1: bootstrap")
    first = _post(
        "/chat/completions",
        {"model": "zeuscode", "messages": base_messages, "tools": TOOLS},
        key,
    )
    message = (first.get("choices") or [{}])[0].get("message") or {}
    calls = message.get("tool_calls") or []
    p1, c1 = _branch_cache(first)
    print(f"  tool_calls={len(calls)} prompt={p1} cached={c1}")
    print(f"  plan={_plan_fingerprint(first)}")
    prefix1 = _cache_prefix(first)
    print(f"  cache_prefix_sha256={prefix1[0]} bytes={prefix1[1]}")
    if not calls:
        print("  FAIL: a tool-enabled client must receive a tool call")
        return 1

    print("turn 2: continuation with a tool result")
    second_messages = [
        *base_messages,
        {
            "role": "assistant",
            "content": message.get("content"),
            "tool_calls": calls,
        },
        {
            "role": "tool",
            "tool_call_id": str(calls[0].get("id") or "call-1"),
            "content": "<returncode>0</returncode>\n<output>helper_7 multiplies by 8</output>",
        },
    ]
    second = _post(
        "/chat/completions",
        {"model": "zeuscode", "messages": second_messages, "tools": TOOLS},
        key,
    )
    message2 = (second.get("choices") or [{}])[0].get("message") or {}
    calls2 = message2.get("tool_calls") or []
    p2, c2 = _branch_cache(second)
    print(f"  tool_calls={len(calls2)} prompt={p2} cached={c2}")
    print(f"  plan={_plan_fingerprint(second)}")
    prefix2 = _cache_prefix(second)
    print(f"  cache_prefix_sha256={prefix2[0]} bytes={prefix2[1]}")
    if not prefix1[0] or prefix1 != prefix2:
        print(f"  FAIL: doer cache prefix changed: first={prefix1} second={prefix2}")
        return 1
    if not calls2:
        onestack = second.get("onestack") or {}
        print("  FAIL: continuation returned no tool call")
        print(f"  pipeline={onestack.get('pipeline')} kind={onestack.get('turn_kind')}")
        print(f"  active_roles={onestack.get('active_roles')}")
        print(
            "  branches="
            + json.dumps(
                [
                    {
                        "role": b.get("role"),
                        "model": b.get("model"),
                        "state": b.get("billable_state"),
                        "prompt": b.get("prompt_tokens"),
                        "meta": b.get("meta"),
                    }
                    for b in (onestack.get("branches") or [])
                ],
                ensure_ascii=False,
            )[:1500]
        )
        print(f"  text={str(message2.get('content') or '')[:600]}")
        return 1

    hit = round(100.0 * c2 / p2, 1) if p2 else 0.0
    print(f"\ncache hit on turn 2: {hit}% ({c2}/{p2})")
    if c2 <= 0:
        print("FAIL: stable prefix matched but provider reported no cached tokens")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as error:
        print(f"HTTP {error.code}: {error.read().decode('utf-8', 'ignore')[:1200]}")
        sys.exit(1)
