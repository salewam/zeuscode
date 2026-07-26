#!/usr/bin/env python3
"""Prod retest: 3×Flash flower app after skill harden. Publish /demo/bouquet-flash/."""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import time
import textwrap
from pathlib import Path

sys.path.insert(0, "/opt/zeuscode/backend")
from dotenv import load_dotenv

load_dotenv("/opt/zeuscode/.env")
from app.orchestrate import filter_studio_artifacts, iter_studio_events
from app.evidence import scan_all, score_from_findings
from app.skills import load_skill_pack

load_skill_pack.cache_clear()

OUT = Path("/tmp/zeus-flower-v6")
OUT.mkdir(exist_ok=True)
TASK = (
    "Сделай мини веб-приложение для цветочного салона «Букет Лайн» Москва. "
    "Не лендинг. App-shell: каталог + новый заказ (имя, телефон, букет, адрес, дата) + мои заказы. "
    "API GET /api/bouquets, GET/POST /api/orders. States loading/empty/error/ready. "
    "Только HTML+CSS+JS. Без React/alert/onclick. "
    "Карточки с фото, ценой, составом и кнопкой В заказ. select из API."
)

collected: list = []
gates: list = []
review: dict = {}
repairs: list = []


async def main() -> None:
    t0 = time.perf_counter()
    async for ev in iter_studio_events(
        user_text=TASK,
        intent="app",
        mode="ultra",
        agents_n=3,
        team_models=["gemini-2.5-flash", "gemini-2.5-flash", "gemini-2.5-flash"],
    ):
        et = ev.get("type")
        if et == "meta":
            print("META", ev.get("team"))
        elif et == "agent_start":
            print("START", ev.get("role"))
        elif et == "agent_done":
            arts = ev.get("artifacts") or []
            collected.extend(arts)
            print("DONE", ev.get("role"), "files", len(arts), "repaired", ev.get("repaired"))
        elif et == "repair_start":
            repairs.append(ev)
            print("REPAIR", ev.get("role"), ev.get("codes"))
        elif et == "repair_done":
            print("REPAIR done", ev.get("role"), ev.get("artifacts_n"))
        elif et == "gate_done":
            gates.append(ev)
            print(
                "GATE",
                ev.get("gate"),
                ev.get("score"),
                "after_repair",
                ev.get("after_repair"),
                "n",
                ev.get("findings_n"),
            )
            for f in ev.get("findings") or []:
                if f.get("severity") in ("critical", "major"):
                    print(" !", f.get("code"), (f.get("message") or "")[:110])
        elif et == "review_done":
            review.update({k: ev.get(k) for k in ("verdict", "score", "gate")})
            print("REVIEW", review)
        elif et in ("error", "agent_error"):
            print("ERR", ev.get("message"))
    print("WALL", round(time.perf_counter() - t0, 1), "repairs", len(repairs))


asyncio.run(main())

by: dict = {}
for a in collected:
    if a.get("path"):
        by[a["path"]] = a
for a in filter_studio_artifacts(list(by.values())):
    by[a["path"]] = a

js = (by.get("/src/frontend/app.js") or {}).get("content") or ""
html = (by.get("/src/frontend/index.html") or {}).get("content") or ""
css = (by.get("/src/frontend/styles.css") or {}).get("content") or ""
be = "\n".join(
    (a.get("content") or "") for p, a in by.items() if p.startswith("/src/backend")
)
print("PATHS", sorted(by))
print("css_len", len(css), "density", "Auto-density" in css)
print("img", bool(re.search(r"<img|\.image|image_url", js)))
print(
    "pick_wire",
    "data-id" in js
    and ("dataset.id" in js or "hardened: wire" in js or "data-pick" in js),
)
print("select", "option" in js.lower() and "innerHTML" in js)
print("json", "application/json" in js)
print("address", "address" in html)
print("orders_nav", "orders" in html)
print("header_required", bool(re.search(r"Header\(\s*\.\.\.\s*\)", be)))
fs = scan_all(list(by.values()))
print("SCAN", score_from_findings(fs))
for f in fs:
    if f.get("severity") in ("critical", "major"):
        print("!", f.get("code"), (f.get("message") or "")[:120])

for p, a in by.items():
    if p.startswith("/src/"):
        d = OUT / "src" / p[len("/src/") :]
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_text(a.get("content") or "", encoding="utf-8")
(OUT / "summary.json").write_text(
    json.dumps(
        {
            "review": review,
            "gates": [
                {k: g.get(k) for k in ("gate", "score", "after_repair", "findings_n")}
                for g in gates
            ],
            "repairs": [{"role": r.get("role"), "codes": r.get("codes")} for r in repairs],
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

# Publish Flash FE (post-harden) under /demo/bouquet-flash/
DEMO = Path("/opt/zeuscode/data/demos/bouquet-flash")
(DEMO / "frontend").mkdir(parents=True, exist_ok=True)
for name in ("index.html", "styles.css", "app.js"):
    src = by.get(f"/src/frontend/{name}")
    if src:
        (DEMO / "frontend" / name).write_text(src.get("content") or "", encoding="utf-8")

(DEMO / "server.py").write_text(
    textwrap.dedent(
        '''\
        from pathlib import Path
        from fastapi import FastAPI, HTTPException, status, Header
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
        from pydantic import BaseModel, Field

        FE = Path(__file__).resolve().parent / "frontend"
        app = FastAPI()
        BOUQUETS = [
            {"id": 1, "name": "Изумрудный сад", "price": 4500, "composition": "пионы, эвкалипт",
             "image": "https://images.unsplash.com/photo-1490750967868-88aa4486c946?w=800&q=80",
             "image_url": "https://images.unsplash.com/photo-1490750967868-88aa4486c946?w=800&q=80"},
            {"id": 2, "name": "Пудровое утро", "price": 3200, "composition": "розы, ранункулюс",
             "image": "https://images.unsplash.com/photo-1487530811176-3780de880c2d?w=800&q=80",
             "image_url": "https://images.unsplash.com/photo-1487530811176-3780de880c2d?w=800&q=80"},
            {"id": 3, "name": "Алый рассвет", "price": 5600, "composition": "красные розы",
             "image": "https://images.unsplash.com/photo-1519378058457-4c29a0a2efac?w=800&q=80",
             "image_url": "https://images.unsplash.com/photo-1519378058457-4c29a0a2efac?w=800&q=80"},
            {"id": 4, "name": "Летний рынок", "price": 2900, "composition": "полевые, ромашки",
             "image": "https://images.unsplash.com/photo-1525310072745-f49212b5ac6d?w=800&q=80",
             "image_url": "https://images.unsplash.com/photo-1525310072745-f49212b5ac6d?w=800&q=80"},
        ]
        ORDERS = []

        class OrderIn(BaseModel):
            name: str = Field(min_length=2)
            phone: str = Field(min_length=7)
            bouquet_id: int
            address: str = Field(min_length=5)
            delivery_date: str

        @app.get("/api/bouquets")
        def list_bouquets():
            return BOUQUETS

        @app.get("/api/orders")
        def list_orders(x_user_id: str = Header(default="demo")):
            return [o for o in ORDERS if o.get("user_id", "demo") == x_user_id]

        @app.post("/api/orders", status_code=status.HTTP_201_CREATED)
        def create_order(body: OrderIn, x_user_id: str = Header(default="demo")):
            if not any(b["id"] == body.bouquet_id for b in BOUQUETS):
                raise HTTPException(404, "not found")
            oid = len(ORDERS) + 1
            ORDERS.append({"id": oid, **body.model_dump(), "user_id": x_user_id, "status": "confirmed"})
            return {"id": oid, "status": "confirmed"}

        @app.get("/")
        def index():
            return FileResponse(FE / "index.html", headers={"Cache-Control": "no-store"})

        app.mount("/", StaticFiles(directory=str(FE), html=True), name="fe")
        '''
    ),
    encoding="utf-8",
)

# Prefer Flash seed if present
shop = (by.get("/src/backend/routers/shop.py") or {}).get("content") or ""
if "BOUQUETS" in shop:
    (DEMO / "flash_shop.py").write_text(shop, encoding="utf-8")

Path("/etc/systemd/system/zeus-bouquet-flash.service").write_text(
    """[Unit]
Description=ZeusCode Flash bouquet demo (skill output)
After=network.target
[Service]
WorkingDirectory=/opt/zeuscode/data/demos/bouquet-flash
ExecStart=/opt/zeuscode/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8767
Restart=always
[Install]
WantedBy=multi-user.target
""",
    encoding="utf-8",
)
subprocess.check_call(["systemctl", "daemon-reload"])
subprocess.check_call(["systemctl", "enable", "--now", "zeus-bouquet-flash"])
subprocess.check_call(["systemctl", "restart", "zeus-bouquet-flash"])

conf = Path("/etc/nginx/sites-enabled/zeuscode.ru")
txt = conf.read_text(encoding="utf-8")
if "demo/bouquet-flash" not in txt:
    snip = """
    location /demo/bouquet-flash/ {
        proxy_pass http://127.0.0.1:8767/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location = /demo/bouquet-flash { return 301 /demo/bouquet-flash/; }

"""
    needle = "    location /demo/bouquet/ {"
    if needle in txt:
        txt = txt.replace(needle, snip + needle, 1)
    else:
        txt = txt.replace(
            "    location / {\n        proxy_pass http://127.0.0.1:8080;",
            snip + "    location / {\n        proxy_pass http://127.0.0.1:8080;",
            1,
        )
    conf.write_text(txt, encoding="utf-8")
    subprocess.check_call(["nginx", "-t"])
    subprocess.check_call(["systemctl", "reload", "nginx"])

time.sleep(1)
print(
    "DEMO",
    subprocess.check_output(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "https://zeuscode.ru/demo/bouquet-flash/"],
        text=True,
    ),
)
print(
    "API",
    subprocess.check_output(
        ["curl", "-sS", "https://zeuscode.ru/demo/bouquet-flash/api/bouquets"], text=True
    )[:160],
)
