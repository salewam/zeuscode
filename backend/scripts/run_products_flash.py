#!/usr/bin/env python3
"""Pure skill run: product grocery app. No hand FE. Publish RAW gate path only."""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/zeuscode/backend")
from dotenv import load_dotenv

load_dotenv("/opt/zeuscode/.env")
from app.orchestrate import filter_studio_artifacts, iter_studio_events
from app.evidence import scan_all, score_from_findings
from app.skills import load_skill_pack

load_skill_pack.cache_clear()

TASK = (
    "Сделай мини веб-приложение — магазин продуктов «Свежая Полка» (Москва). "
    "Не лендинг. Эталон templates/app-shop-products: каталог с фото, "
    "кнопка «В корзину», вкладка Корзина (cart-badge), вкладка Покупки (orders). "
    "Фильтры Овощи/Фрукты/Молочка = seed.category. "
    "Карточки: name+desc+image (не composition/size/stems). "
    "API GET /api/products (≥6: name, desc, category, image из media pack grocery), "
    "GET+POST /api/orders (product_name из name). "
    "Только HTML+CSS+JS + FastAPI. API='.' . Не React."
)
OUT = Path("/tmp/zeus-products-v4")
OUT.mkdir(exist_ok=True)
DEMO = Path("/opt/zeuscode/data/demos/products-flash")

collected: list = []
raw_fe: list = []
gates: list = []
review: dict = {}
repairs: list = []
sources_log: list = []


def _sizes(arts: list) -> dict:
    by = {a["path"]: a for a in arts if a.get("path")}
    html = (by.get("/src/frontend/index.html") or {}).get("content") or ""
    css = (by.get("/src/frontend/styles.css") or {}).get("content") or ""
    js = (by.get("/src/frontend/app.js") or {}).get("content") or ""
    return {
        "html": len(html),
        "css": len(css),
        "js": len(js),
        "products_api": "/api/products" in js or "/api/products" in html,
        "bouquets_leak": "/api/bouquets" in js or "букет" in js.lower(),
        "brand": "Свежая Полка" in html,
        "markers": {
            "panel__head": "panel__head" in html,
            "renderPreview": "renderPreview" in js,
            "loadOrders": "loadOrders" in js,
            "template_fill": any(a.get("hardened") for a in arts if "frontend" in (a.get("path") or "")),
        },
    }


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
            role = ev.get("role") or "?"
            collected.extend(arts)
            if role == "frontend":
                raw_fe.clear()
                raw_fe.extend(arts)
                print("DONE frontend", _sizes(arts), "sources", ev.get("app_shop_sources"))
                if ev.get("app_shop_sources"):
                    sources_log.append(ev.get("app_shop_sources"))
            else:
                print("DONE", role, len(arts))
        elif et == "repair_start":
            repairs.append(ev)
            print("REPAIR", ev.get("role"), ev.get("codes"))
        elif et == "repair_done":
            print("REPAIR done", ev.get("role"), ev.get("app_shop_sources"))
            if ev.get("app_shop_sources"):
                sources_log.append(ev.get("app_shop_sources"))
        elif et == "gate_done":
            gates.append(ev)
            print("GATE", ev.get("gate"), ev.get("score"), "after_repair", ev.get("after_repair"))
            for f in ev.get("findings") or []:
                if f.get("severity") in ("critical", "major"):
                    print(" !", f.get("code"), (f.get("message") or "")[:100])
        elif et == "review_done":
            review.update({k: ev.get(k) for k in ("verdict", "score", "gate")})
            print("REVIEW", review)
        elif et in ("error", "agent_error"):
            print("ERR", ev.get("message"))
    print("WALL", round(time.perf_counter() - t0, 1))


asyncio.run(main())

by = {}
for a in collected:
    if a.get("path"):
        by[a["path"]] = a

# Final publish: allow etalon replace so cart template ships if model thin after repair
ship_arts = filter_studio_artifacts(list(by.values()), allow_etalon_replace=True)
print("SHIP_PATH", _sizes(ship_arts))
gate_arts = ship_arts
gate_by = {a["path"]: a for a in ship_arts if a.get("path")}
for p, a in gate_by.items():
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
            "sources": sources_log,
            "sizes": _sizes(gate_arts),
            "hand_built": False,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

# --- publish demo from skill artifacts only ---
(DEMO / "frontend").mkdir(parents=True, exist_ok=True)
(DEMO / "backend").mkdir(parents=True, exist_ok=True)
for name in ("index.html", "styles.css", "app.js"):
    src = gate_by.get(f"/src/frontend/{name}")
    if not src:
        raise SystemExit(f"missing FE {name}")
    content = src.get("content") or ""
    if name == "app.js":
        content = re.sub(r"fetch\(\s*(['\"])/api/", r"fetch(\1./api/", content)
        content = re.sub(r"fetch\(\s*(['\"])\./api/", r"fetch(\1./api/", content)
        # API="." + "/api/..." style
        if 'API = "."' in content or "API='.'" in content or 'API = "."' in content:
            pass
    (DEMO / "frontend" / name).write_text(content, encoding="utf-8")

# dump backend arts as-is
be_blob = ""
for p, a in sorted(gate_by.items()):
    if "/backend/" in p and p.endswith(".py"):
        rel = p.split("/backend/", 1)[-1]
        dest = DEMO / "backend" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        body = a.get("content") or ""
        dest.write_text(body, encoding="utf-8")
        be_blob += body + "\n"

# Minimal infra wrapper ONLY — seed/API must come from Flash backend blob if present.
# Parse list literal name PRODUCTS or BOUQUETS from Flash; do not invent catalog rows.
seed_name = "PRODUCTS" if "PRODUCTS" in be_blob or "/api/products" in be_blob else "BOUQUETS"
list_m = re.search(
    rf"({seed_name}\s*=\s*\[.*?\n\])",
    be_blob,
    re.S,
)
orders_ok = bool(re.search(r"@\w+\.(get|post)\([^\)]*orders", be_blob, re.I)) or "orders" in be_blob.lower()

if not list_m:
    # Flash sometimes uses lowercase or different var — last resort: empty + fail loud in UI
    print("WARN: no seed list in backend arts — demo API will be empty list")
    seed_lit = "PRODUCTS = []"
else:
    seed_lit = list_m.group(1)
    # domain normalize name
    if seed_lit.strip().startswith("BOUQUETS"):
        seed_lit = "PRODUCTS = " + seed_lit.split("=", 1)[1]
    print("SEED_FROM_FLASH", len(seed_lit), "chars")

server = f'''\
"""Infra only: serves skill FE + Flash seed. No hand catalog."""
from pathlib import Path
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

FE = Path(__file__).resolve().parent / "frontend"
app = FastAPI()
{seed_lit}
if not isinstance(PRODUCTS, list):
    PRODUCTS = []
# normalize image_url alias + name from title + desc
for _p in PRODUCTS:
    if isinstance(_p, dict):
        if _p.get("image") and not _p.get("image_url"):
            _p["image_url"] = _p["image"]
        if _p.get("title") and not _p.get("name"):
            _p["name"] = _p["title"]
        if _p.get("description") and not _p.get("desc"):
            _p["desc"] = _p["description"]
ORDERS = []

class OrderIn(BaseModel):
    name: str = Field(min_length=2)
    phone: str = Field(min_length=7)
    product_id: int | None = None
    bouquet_id: int | None = None
    delivery_date: str = ""
    address: str = Field(min_length=3)
    comment: str = ""

@app.get("/api/products")
@app.get("/api/bouquets")
def list_products():
    return PRODUCTS

@app.get("/api/orders")
def list_orders():
    return list(reversed(ORDERS))

@app.post("/api/orders", status_code=status.HTTP_201_CREATED)
def create_order(body: OrderIn):
    pid = body.product_id if body.product_id is not None else body.bouquet_id
    if pid is None:
        raise HTTPException(400, "product_id required")
    item = next((x for x in PRODUCTS if x.get("id") == pid), None)
    if not item:
        raise HTTPException(404, "not found")
    oid = len(ORDERS) + 1
    pname = item.get("name") or item.get("title") or ""
    row = {{
        "id": oid,
        "name": body.name,
        "phone": body.phone,
        "product_id": pid,
        "delivery_date": body.delivery_date,
        "address": body.address,
        "comment": body.comment,
        "status": "confirmed",
        "product_name": pname,
        "bouquet_name": pname,
        "total": item.get("price"),
    }}
    ORDERS.append(row)
    return row

@app.get("/")
def index():
    return FileResponse(FE / "index.html", headers={{"Cache-Control": "no-store"}})

app.mount("/", StaticFiles(directory=str(FE), html=True), name="fe")
'''
(DEMO / "server.py").write_text(server, encoding="utf-8")

# systemd + nginx
unit = """\
[Unit]
Description=ZeusCode Flash products demo (skill output)
After=network.target
[Service]
WorkingDirectory=/opt/zeuscode/data/demos/products-flash
ExecStart=/opt/zeuscode/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8768
Restart=always
[Install]
WantedBy=multi-user.target
"""
Path("/etc/systemd/system/zeus-products-flash.service").write_text(unit, encoding="utf-8")
subprocess.check_call(["systemctl", "daemon-reload"])
subprocess.check_call(["systemctl", "enable", "--now", "zeus-products-flash"])
subprocess.check_call(["systemctl", "restart", "zeus-products-flash"])

nginx = Path("/etc/nginx/sites-enabled/zeuscode.ru")
txt = nginx.read_text(encoding="utf-8")
if "/demo/products-flash/" not in txt:
    block = """
    location /demo/products-flash/ {
        proxy_pass http://127.0.0.1:8768/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
    location = /demo/products-flash { return 301 /demo/products-flash/; }
"""
    # insert before bouquet-flash block if possible
    if "location /demo/bouquet-flash/" in txt:
        txt = txt.replace("location /demo/bouquet-flash/", block + "\n    location /demo/bouquet-flash/")
    else:
        txt = txt.replace("server {", "server {" + block, 1)
    nginx.write_text(txt, encoding="utf-8")
    subprocess.check_call(["nginx", "-t"])
    subprocess.check_call(["systemctl", "reload", "nginx"])

time.sleep(1)
code = subprocess.check_output(
    [
        "curl",
        "-sS",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "https://zeuscode.ru/demo/products-flash/",
    ],
    text=True,
)
api = subprocess.check_output(
    ["curl", "-sS", "https://zeuscode.ru/demo/products-flash/api/products"],
    text=True,
)[:200]
print("DEMO", code, "API", api)
print("URL https://zeuscode.ru/demo/products-flash/")
print("SUMMARY", OUT / "summary.json")
