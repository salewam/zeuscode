#!/usr/bin/env python3
"""Retest Flash against app-shop etalon; publish /demo/bouquet-flash/."""
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

OUT = Path("/tmp/zeus-flower-v7")
OUT.mkdir(exist_ok=True)
TASK = (
    "Сделай мини веб-приложение для цветочного салона «Букет Лайн» Москва. "
    "Не лендинг. Эталон templates/app-shop: бренд+телефон+tabs, фильтры, "
    "карточки с фото/тегом/составом/data-pick, заказ с preview, мои заказы+badge. "
    "API GET /api/bouquets, GET/POST /api/orders. Только HTML+CSS+JS."
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
        team_models=["gemini-2.5-flash"] * 3,
    ):
        et = ev.get("type")
        if et == "meta":
            print("META", ev.get("team"))
        elif et == "agent_start":
            print("START", ev.get("role"))
        elif et == "agent_done":
            arts = ev.get("artifacts") or []
            collected.extend(arts)
            print("DONE", ev.get("role"), len(arts), "repaired", ev.get("repaired"))
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
                    print(" !", f.get("code"), (f.get("message") or "")[:100])
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
print("sizes", len(html), len(css), len(js))
print(
    "chrome",
    {
        "brand": "brand__name" in html or "brand__mark" in html,
        "filters": "data-filter" in html,
        "preview": "order-preview" in html or "order-layout" in html,
        "pick": "data-pick" in js,
        "golden_css": "golden app-shop" in css or "brand__name" in css,
    },
)
fs = scan_all(list(by.values()))
print("SCAN", score_from_findings(fs))
for f in fs:
    if f.get("severity") in ("critical", "major"):
        print("!", f.get("code"), (f.get("message") or "")[:110])

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
            "sizes": {"html": len(html), "css": len(css), "js": len(js)},
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

DEMO = Path("/opt/zeuscode/data/demos/bouquet-flash")
(DEMO / "frontend").mkdir(parents=True, exist_ok=True)
for name in ("index.html", "styles.css", "app.js"):
    src = by.get(f"/src/frontend/{name}")
    if src:
        content = src.get("content") or ""
        if name == "app.js":
            content = re.sub(r"fetch\(\s*(['\"])/api/", r"fetch(\1./api/", content)
        (DEMO / "frontend" / name).write_text(content, encoding="utf-8")

# Prefer flash backend seed if rich; else etalon seed
shop = (by.get("/src/backend/routers/shop.py") or {}).get("content") or ""
(DEMO / "server.py").write_text(
    textwrap.dedent(
        '''\
        from pathlib import Path
        from fastapi import FastAPI, HTTPException, status
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
        from pydantic import BaseModel, Field

        FE = Path(__file__).resolve().parent / "frontend"
        app = FastAPI()
        BOUQUETS = [
            {"id": 1, "name": "Изумрудный сад", "price": 4500, "size": "высокий", "stems": 25,
             "composition": "пионы, эвкалипт, эустома", "desc": "Плотный букет для дома.",
             "image": "https://images.unsplash.com/photo-1490750967868-88aa4486c946?w=800&q=80",
             "image_url": "https://images.unsplash.com/photo-1490750967868-88aa4486c946?w=800&q=80", "tag": "хит"},
            {"id": 2, "name": "Пудровое утро", "price": 3200, "size": "средний", "stems": 15,
             "composition": "розы, ранункулюс", "desc": "Мягкие пудровые тона.",
             "image": "https://images.unsplash.com/photo-1487530811176-3780de880c2d?w=800&q=80",
             "image_url": "https://images.unsplash.com/photo-1487530811176-3780de880c2d?w=800&q=80", "tag": "новый"},
            {"id": 3, "name": "Алый рассвет", "price": 5600, "size": "крупный", "stems": 35,
             "composition": "красные розы", "desc": "Классика на торжество.",
             "image": "https://images.unsplash.com/photo-1519378058457-4c29a0a2efac?w=800&q=80",
             "image_url": "https://images.unsplash.com/photo-1519378058457-4c29a0a2efac?w=800&q=80", "tag": "премиум"},
            {"id": 4, "name": "Летний рынок", "price": 2900, "size": "средний", "stems": 19,
             "composition": "полевые, ромашки", "desc": "Лёгкий микс.",
             "image": "https://images.unsplash.com/photo-1525310072745-f49212b5ac6d?w=800&q=80",
             "image_url": "https://images.unsplash.com/photo-1525310072745-f49212b5ac6d?w=800&q=80", "tag": ""},
            {"id": 5, "name": "Белый шёлк", "price": 6100, "size": "высокий", "stems": 21,
             "composition": "белые розы, орхидея", "desc": "Сдержанный светлый букет.",
             "image": "https://images.unsplash.com/photo-1468327768560-75b448c4b124?w=800&q=80",
             "image_url": "https://images.unsplash.com/photo-1468327768560-75b448c4b124?w=800&q=80", "tag": "премиум"},
            {"id": 6, "name": "Ягодный джем", "price": 3800, "size": "средний", "stems": 17,
             "composition": "альстромерия, гвоздика", "desc": "Яркий акцент.",
             "image": "https://images.unsplash.com/photo-1455659817273-f9680774153e?w=800&q=80",
             "image_url": "https://images.unsplash.com/photo-1455659817273-f9680774153e?w=800&q=80", "tag": ""},
        ]
        ORDERS = []

        class OrderIn(BaseModel):
            name: str = Field(min_length=2)
            phone: str = Field(min_length=7)
            bouquet_id: int
            delivery_date: str
            address: str = Field(min_length=5)
            comment: str = ""

        @app.get("/api/bouquets")
        def list_bouquets():
            return BOUQUETS

        @app.get("/api/orders")
        def list_orders():
            return list(reversed(ORDERS))

        @app.post("/api/orders", status_code=status.HTTP_201_CREATED)
        def create_order(body: OrderIn):
            bq = next((b for b in BOUQUETS if b["id"] == body.bouquet_id), None)
            if not bq:
                raise HTTPException(404, "not found")
            oid = len(ORDERS) + 1
            ORDERS.append({"id": oid, **body.model_dump(), "status": "confirmed",
                           "bouquet_name": bq["name"], "total": bq["price"]})
            return {"id": oid, "status": "confirmed", "bouquet_name": bq["name"], "total": bq["price"]}

        @app.get("/")
        def index():
            return FileResponse(FE / "index.html", headers={"Cache-Control": "no-store"})

        app.mount("/", StaticFiles(directory=str(FE), html=True), name="fe")
        '''
    ),
    encoding="utf-8",
)
if "BOUQUETS" in shop:
    (DEMO / "flash_shop.py").write_text(shop, encoding="utf-8")

subprocess.check_call(["systemctl", "restart", "zeus-bouquet-flash"])
time.sleep(1)
print(
    "DEMO",
    subprocess.check_output(
        [
            "curl",
            "-sS",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "https://zeuscode.ru/demo/bouquet-flash/",
        ],
        text=True,
    ),
)
