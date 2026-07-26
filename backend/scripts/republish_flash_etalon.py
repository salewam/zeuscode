#!/usr/bin/env python3
"""Apply app-shop etalon harden to thin Flash FE and republish demo."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/opt/zeuscode/backend")
from app.orchestrate import filter_studio_artifacts

FLASH = Path("/opt/zeuscode/data/demos/bouquet-flash/frontend")
# Simulate thin flash arts (current files) then harden
arts = []
for name in ("index.html", "styles.css", "app.js"):
    p = FLASH / name
    arts.append(
        {
            "path": f"/src/frontend/{name}",
            "title": name,
            "role": "frontend",
            "content": p.read_text(encoding="utf-8") if p.is_file() else "",
        }
    )
# force catalog signal
arts.append(
    {
        "path": "/src/backend/routers/shop.py",
        "role": "backend",
        "content": 'BOUQUETS=[{"image":"https://images.unsplash.com/x"}]\n@router.get("/bouquets")\n',
    }
)
out = {a["path"]: a for a in filter_studio_artifacts(arts)}
for name in ("index.html", "styles.css", "app.js"):
    a = out[f"/src/frontend/{name}"]
    body = a.get("content") or ""
    (FLASH / name).write_text(body, encoding="utf-8")
    print(name, len(body), "hardened" if a.get("hardened") else "keep")
print("done")
