"""zeuscode + tools must stay on the crew path — no solo remount."""

from __future__ import annotations

import inspect

from app.fusion import run_fusion
from app.openai_tools import request_wants_tools
from app.routers import chat as chat_mod


def test_request_wants_tools_still_detects_tools():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "run",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    assert request_wants_tools(tools) is True


def test_chat_router_has_no_agent_tools_remount():
    src = inspect.getsource(chat_mod)
    assert "agent_tools_reroute" not in src
    assert "pick_agent_solo_model" not in src


def test_run_fusion_accepts_tools_kwargs():
    sig = inspect.signature(run_fusion)
    assert "tools" in sig.parameters
    assert "tool_choice" in sig.parameters
