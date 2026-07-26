#!/usr/bin/env python3
import json
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, "/opt/zeuscode/backend")
from app.catalog import get_model, upstream_prices

usage = json.loads(Path("/tmp/zeus-products-mix-v1/summary.json").read_text())["usage"]
MARKUP = 1.5
USD_RUB = 92.016


def cost(model, pt, ct):
    prices = upstream_prices().get(model)
    m = get_model(model) or {}
    if prices:
        pin, pout = prices
    else:
        pin = float(m.get("input_usd") or 0)
        pout = float(m.get("output_usd") or 0)
    up = (pt / 1e6) * pin + (ct / 1e6) * pout
    user = up * MARKUP
    ir, orr = m.get("input_rub"), m.get("output_rub")
    rub = None
    if ir is not None and orr is not None:
        rub = (pt / 1e6) * float(ir) + (ct / 1e6) * float(orr)
    return up, user, rub


print("=== prices USD/M tok ===")
for mid in ["claude-haiku-4-5", "gemini-3-pro", "gpt-5-2", "gemini-2.5-flash"]:
    m = get_model(mid) or {}
    print(mid, m.get("input_usd"), m.get("output_usd"), "rub", m.get("input_rub"), m.get("output_rub"))

total_up = total_user = total_rub = 0.0
print("\n=== agents ===")
for u in usage:
    up, user, rub = cost(u["model"], u["pt"] or 0, u["ct"] or 0)
    total_up += up
    total_user += user
    if rub:
        total_rub += rub
    line = f"{u['role']:10} {u['model']:22} pt={u['pt']} ct={u['ct']} up=${up:.4f} user=${user:.4f}"
    if rub is not None:
        line += f" rub≈{rub:.2f}"
    print(line)

for label, pt, ct in [("reviewer~", 12000, 1500), ("synth~", 8000, 500)]:
    up, user, rub = cost("gemini-3-pro", pt, ct)
    total_up += up
    total_user += user
    if rub:
        total_rub += rub
    print(f"{label:10} gemini-3-pro          pt={pt} ct={ct} up=${up:.4f} user=${user:.4f} rub≈{rub:.2f}")

print(f"\nTOTAL upstream ${total_up:.4f}")
print(f"TOTAL user*markup ${total_user:.4f} ≈ {total_user * USD_RUB:.0f} RUB")

api = json.load(urllib.request.urlopen("http://127.0.0.1:8769/api/products"))
js = Path("/opt/zeuscode/data/demos/products-mix/frontend/app.js").read_text()
html = Path("/opt/zeuscode/data/demos/products-mix/frontend/index.html").read_text()
css = Path("/opt/zeuscode/data/demos/products-mix/frontend/styles.css").read_text()
print("\nLIVE addToCart", "addToCart" in js, "products", len(api))
print("sizes", len(html), len(css), len(js))
ok = 0
for p in api:
    url = p.get("image") or ""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            if r.status == 200:
                ok += 1
    except Exception:
        print("dead", p.get("name"))
print("images_ok", ok, "/", len(api))
