#!/usr/bin/env python3
import json
from pathlib import Path

p = Path("/tmp/sto-mixed-cheap-bake/mixed/_events.json")
print("exists", p.exists(), "size", p.stat().st_size if p.exists() else 0)
if not p.exists():
    raise SystemExit(0)
ev = json.loads(p.read_text())
print("n events", len(ev), "types", sorted({e.get("type") for e in ev}))
for e in ev:
    t = e.get("type")
    if t in (
        "error",
        "fail",
        "agent_error",
        "status",
        "wave_start",
        "wave_done",
        "agent_start",
        "agent_done",
        "final",
        "gate_done",
        "brief_expand",
        "meta",
    ):
        msg = e.get("message") or e.get("error") or e.get("text") or e.get("summary") or ""
        print(f"{t}: role={e.get('role')} model={e.get('model')} {str(msg)[:240]}")
print("--- last 10 ---")
for e in ev[-10:]:
    print(e.get("type"), list(e.keys())[:10], str(e)[:180])
