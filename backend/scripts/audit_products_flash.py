#!/usr/bin/env python3
"""Audit products-flash demo for real user-facing bugs."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

fe = Path("/opt/zeuscode/data/demos/products-flash/frontend")
html = (fe / "index.html").read_text(encoding="utf-8")
css = (fe / "styles.css").read_text(encoding="utf-8")
js = (fe / "app.js").read_text(encoding="utf-8")
api = json.load(urllib.request.urlopen("http://127.0.0.1:8768/api/products"))

issues: list[str] = []
keys = set(api[0]) if api else set()
print("API n=", len(api), "keys=", sorted(keys))
print("sample=", api[0] if api else None)

filters = re.findall(r'data-filter=["\']([^"\']+)["\']', html)
cats = sorted({p.get("category") for p in api if p.get("category")})
print("filters=", filters)
print("api categories=", cats)
for f in filters:
    if f != "all" and f not in cats:
        issues.append(f"chip data-filter={f!r} нет в API categories={cats}")

for eid in (
    "product_id",
    "catalog-list",
    "order-preview",
    "order-form",
    "orders-list",
    "status-catalog",
    "toast",
    "refresh-orders",
    "delivery_date",
    "address",
    "name",
    "phone",
):
    if f'id="{eid}"' not in html:
        issues.append(f"нет #{eid} в HTML")

if re.search(r'\$\("client_name"\)\.value', js):
    issues.append("JS пишет в #client_name — такого id нет → runtime error")
if "cart.length" in js and not re.search(r"\bcart\s*=", js):
    issues.append("JS: cart.length, но cart не объявлен")
if re.search(r"""const\s+API\s*=\s*['"]/?['"]\s*;""", js):
    issues.append('API="" → fetch бьёт в zeuscode.ru/api (404)')

# card fields
if re.search(r"p\.description|p\.desc|p\.composition", js) and not any(
    k in keys for k in ("description", "desc", "composition")
):
    issues.append("JS ждёт description/desc, в seed пусто → пустые meta")

# POST
payload = json.dumps(
    {
        "name": "Тест",
        "phone": "+79990001122",
        "product_id": api[0]["id"],
        "address": "ул. Тест 1",
        "delivery_date": "2026-07-20",
        "comment": "x",
    }
).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8768/api/orders",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
        print("POST", r.status, body)
except Exception as e:  # noqa: BLE001
    issues.append(f"POST /api/orders падает: {e}")

abs_fetches = re.findall(r"""fetch\(\s*['"](/api/[^'"]+)""", js)
if abs_fetches:
    issues.append(f"абсолютный fetch {abs_fetches} под /demo/")

# padding junk after loadCatalog that can throw on init path
if "$(\"client_name\")" in js or "$('client_name')" in js:
    pass  # already flagged

# filter chips vs logic
if "data-filter" in html and "data-filter" not in js:
    issues.append("фильтры в HTML, логики в JS нет")

# thin / quality
if "undefined" in js and "||" not in js[js.find("undefined") - 40 : js.find("undefined") + 40]:
    pass

# orders list field names after POST
orders = json.load(urllib.request.urlopen("http://127.0.0.1:8768/api/orders"))
print("orders sample", orders[0] if orders else None)
if orders and js.count("o.product_name") and not orders[0].get("product_name"):
    if not orders[0].get("bouquet_name"):
        issues.append("orders list ждёт product_name, API не отдаёт")

# visual: check if render uses missing fields leading to blank cards
m = re.search(r"catalogList\.innerHTML = filtered\s*\.map\((.*?)\)\.join", js, re.S)
if m:
    card = m.group(1)
    print("CARD_SNIP", " ".join(card.split())[:240])

print("\n=== ТРАБЛЫ ===")
if not issues:
    print("(статических не нашёл — смотри UX ниже)")
for i, msg in enumerate(issues, 1):
    print(f"{i}. {msg}")

# Always-report UX smells even if not hard bugs
smells = []
if "title" in keys and "name" not in keys:
    smells.append("seed.title вместо name — работает только через name||title")
if not any(k in keys for k in ("desc", "description", "composition")):
    smells.append("у товаров нет состава/описания — карточки беднее эталона")
if re.search(r"style=\"max-width:120px", js):
    smells.append("preview с inline style max-width:120px — выглядит куцо")
if "Дополнительные блоки логики" in js or "Analytics" in js:
    smells.append("в JS водяная простыня ради объёма (analytics/theme padding)")
if "$(\"client_name\")" in js:
    smells.append("мертвый localStorage sync на несуществующие поля")
print("\n=== UX / запах ===")
for s in smells:
    print("-", s)
