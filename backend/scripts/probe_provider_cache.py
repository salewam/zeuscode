"""Ask the upstream twice with a shared prefix and print the raw usage block.

Tells us whether the provider reports prompt-cache hits at all, which decides
whether the stable-prefix work can be measured end to end.

    PYTHONPATH=backend .venv/bin/python backend/scripts/probe_provider_cache.py [model]
"""

from __future__ import annotations

import asyncio
import json
import sys

from app import upstream

PREFIX = "\n".join(
    f"line {i}: def helper_{i}(value): return value * {i}" for i in range(1200)
)


async def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt-5.4"
    base = [
        {"role": "system", "content": "You are a terse code reviewer."},
        {"role": "user", "content": f"Module:\n{PREFIX}\n\nName one helper."},
    ]
    print(f"model={model} prefix_chars={len(PREFIX)}")
    for attempt in (1, 2):
        messages = list(base)
        if attempt == 2:
            messages.append({"role": "assistant", "content": "helper_1"})
            messages.append({"role": "user", "content": "Name another one."})
        data = await upstream.chat_completions(
            model=model, messages=messages, max_tokens=32, temperature=0.0
        )
        usage = data.get("usage") or {}
        print(f"  call {attempt} usage={json.dumps(usage, ensure_ascii=False)}")
        print(f"  call {attempt} extract_cached={upstream.extract_cached_tokens(data)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
