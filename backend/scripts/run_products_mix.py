#!/usr/bin/env python3
"""Products shop via skill: Haiku 4.5 + Gemini 3 Pro + GPT-5.2."""
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

OUT = Path("/tmp/zeus-products-mix-v2")
OUT.mkdir(exist_ok=True)
DEMO = Path("/opt/zeuscode/data/demos/products-mix")
TASK = (
    "Сделай мини веб-приложение — магазин продуктов «Свежая Полка» (Москва). "
    "Не лендинг и не клон чужого UI: свой визуал под этот бренд, но рабочие потоки. "
    "Каталог с фото, «В корзину» + cart-badge, вкладка Корзина, вкладка Покупки (orders). "
    "Фильтры Овощи/Фрукты/Молочка = seed.category. "
    "Карточки: name+desc+image+category (не composition/size/stems). "
    "API GET /api/products (≥6 с live image), GET+POST /api/orders (product_name из name). "
    "Только HTML+CSS+JS + FastAPI. const API='.' . Не React. Логика только в app.js."
)

# Haiku 4.5 + Gemini 3 Pro + GPT-5.2
TEAM = ["claude-haiku-4-5", "gemini-3-pro", "gpt-5-2"]

collected: list = []
role_models: dict[str, str] = {}
gates: list = []
review: dict = {}
repairs: list = []
usage: list = []


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
        "cart": "addToCart" in js and "cart-badge" in html,
        "pokupki": "Покупки" in html or "покупки" in html.lower(),
        "brand": "Свежая Полка" in html,
        "markers": {
            "panel__head": "panel__head" in html,
            "addToCart": "addToCart" in js,
            "loadOrders": "loadOrders" in js,
            "template_fill": any(
                a.get("hardened") for a in arts if "frontend" in (a.get("path") or "")
            ),
        },
    }


async def main() -> None:
    t0 = time.perf_counter()
    async for ev in iter_studio_events(
        user_text=TASK,
        intent="app",
        mode="ultra",
        agents_n=3,
        team_models=TEAM,
    ):
        et = ev.get("type")
        if et == "meta":
            print("META team", ev.get("team"), "models", ev.get("models") or ev.get("pack"))
            print("META full", {k: ev.get(k) for k in ("team", "judge", "models", "pack") if ev.get(k)})
        elif et == "agent_start":
            role_models[ev.get("role") or "?"] = ev.get("model") or "?"
            print("START", ev.get("role"), "→", ev.get("model"))
        elif et == "agent_done":
            arts = ev.get("artifacts") or []
            collected.extend(arts)
            role = ev.get("role") or "?"
            pt = ev.get("prompt_tokens")
            ct = ev.get("completion_tokens")
            usage.append({"role": role, "model": role_models.get(role), "pt": pt, "ct": ct})
            if role == "frontend":
                print("DONE frontend", _sizes(arts), "tok", pt, ct)
            else:
                print("DONE", role, len(arts), "tok", pt, ct)
        elif et == "repair_start":
            repairs.append(ev)
            print("REPAIR", ev.get("role"), ev.get("codes"), "model", ev.get("model"))
        elif et == "repair_done":
            print("REPAIR done", ev.get("role"), ev.get("app_shop_sources"))
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
            print("ERR", ev.get("message") or ev)
    print("WALL", round(time.perf_counter() - t0, 1))


asyncio.run(main())

by = {}
for a in collected:
    if a.get("path"):
        by[a["path"]] = a

ship = filter_studio_artifacts(list(by.values()), allow_etalon_replace=True)
print("SHIP", _sizes(ship))
fs = scan_all(ship)
print("SCAN", score_from_findings(fs))
for f in fs:
    if f.get("severity") in ("critical", "major"):
        print("!", f.get("code"), (f.get("message") or "")[:110])

ship_by = {a["path"]: a for a in ship if a.get("path")}
for p, a in ship_by.items():
    if p.startswith("/src/"):
        d = OUT / "src" / p[len("/src/") :]
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_text(a.get("content") or "", encoding="utf-8")

(OUT / "summary.json").write_text(
    json.dumps(
        {
            "team": TEAM,
            "role_models": role_models,
            "usage": usage,
            "review": review,
            "gates": [
                {k: g.get(k) for k in ("gate", "score", "after_repair", "findings_n")}
                for g in gates
            ],
            "repairs": [{"role": r.get("role"), "codes": r.get("codes")} for r in repairs],
            "sizes": _sizes(ship),
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

# --- publish demo ---
(DEMO / "frontend").mkdir(parents=True, exist_ok=True)
(DEMO / "backend").mkdir(parents=True, exist_ok=True)
for name in ("index.html", "styles.css", "app.js"):
    src = ship_by.get(f"/src/frontend/{name}")
    if not src:
        print("missing", name)
        continue
    content = src.get("content") or ""
    if name == "app.js":
        content = re.sub(r"fetch\(\s*(['\"])/api/", r"fetch(\1./api/", content)
    (DEMO / "frontend" / name).write_text(content, encoding="utf-8")

be_blob = ""
for p, a in sorted(ship_by.items()):
    if "/backend/" in p and p.endswith(".py"):
        rel = p.split("/backend/", 1)[-1]
        dest = DEMO / "backend" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        body = a.get("content") or ""
        dest.write_text(body, encoding="utf-8")
        be_blob += body + "\n"

list_m = re.search(
    r"((?:PRODUCTS_SEED|PRODUCTS|BOUQUETS)\s*=\s*\[.*?\n\])",
    be_blob,
    re.S,
)
seed_name = "PRODUCTS"
if not list_m:
    seed_lit = "PRODUCTS = []"
    print("WARN empty seed")
else:
    seed_lit = list_m.group(1)
    name = seed_lit.split("=", 1)[0].strip()
    if name in ("BOUQUETS", "PRODUCTS_SEED"):
        seed_lit = "PRODUCTS = " + seed_lit.split("=", 1)[1]
    print("SEED", len(seed_lit))

server = f'''\
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
        "id": oid, "name": body.name, "phone": body.phone, "product_id": pid,
        "delivery_date": body.delivery_date, "address": body.address,
        "comment": body.comment, "status": "confirmed",
        "product_name": pname, "bouquet_name": pname, "total": item.get("price"),
    }}
    ORDERS.append(row)
    return row

@app.get("/")
def index():
    return FileResponse(FE / "index.html", headers={{"Cache-Control": "no-store"}})

app.mount("/", StaticFiles(directory=str(FE), html=True), name="fe")
'''
(DEMO / "server.py").write_text(server, encoding="utf-8")

unit = """\
[Unit]
Description=ZeusCode mix models products demo
After=network.target
[Service]
WorkingDirectory=/opt/zeuscode/data/demos/products-mix
ExecStart=/opt/zeuscode/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8769
Restart=always
[Install]
WantedBy=multi-user.target
"""
Path("/etc/systemd/system/zeus-products-mix.service").write_text(unit, encoding="utf-8")
subprocess.check_call(["systemctl", "daemon-reload"])
subprocess.check_call(["systemctl", "enable", "--now", "zeus-products-mix"])
subprocess.check_call(["systemctl", "restart", "zeus-products-mix"])

nginx = Path("/etc/nginx/sites-enabled/zeuscode.ru")
txt = nginx.read_text(encoding="utf-8")
if "/demo/products-mix/" not in txt:
    block = """
    location /demo/products-mix/ {
        proxy_pass http://127.0.0.1:8769/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
    location = /demo/products-mix { return 301 /demo/products-mix/; }
"""
    if "location /demo/products-flash/" in txt:
        txt = txt.replace(
            "location /demo/products-flash/",
            block + "\n    location /demo/products-flash/",
        )
    else:
        txt = txt.replace("server {", "server {" + block, 1)
    nginx.write_text(txt, encoding="utf-8")
    subprocess.check_call(["nginx", "-t"])
    subprocess.check_call(["systemctl", "reload", "nginx"])

time.sleep(1)
code = subprocess.check_output(
    ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "https://zeuscode.ru/demo/products-mix/"],
    text=True,
)
api = subprocess.check_output(
    ["curl", "-sS", "https://zeuscode.ru/demo/products-mix/api/products"], text=True
)[:180]
print("DEMO", code, api)
print("URL https://zeuscode.ru/demo/products-mix/")
print("ROLES", role_models)
print("USAGE", usage)
