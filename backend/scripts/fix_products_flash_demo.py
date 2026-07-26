#!/usr/bin/env python3
"""Fix products-flash demo: relative API + missing product_id select."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

fe = Path("/opt/zeuscode/data/demos/products-flash/frontend")
html_path = fe / "index.html"
js_path = fe / "app.js"
html = html_path.read_text(encoding="utf-8")
js = js_path.read_text(encoding="utf-8")

if 'id="product_id"' not in html:
    select = """            <label>Товар
              <select id="product_id" name="product_id" required></select>
            </label>
            <label>Дата доставки
              <input id="delivery_date" name="delivery_date" type="date" required />
            </label>
"""
    anchor = """            <label>Адрес
              <input id="address\""""
    if anchor in html:
        html = html.replace(anchor, select + anchor, 1)
        print("inserted select+date before address")
    else:
        html = html.replace(
            '<form id="order-form"',
            '<form id="order-form"',
            1,
        )
        # inject after form open
        html = html.replace(
            '<form id="order-form" class="form" novalidate>',
            '<form id="order-form" class="form" novalidate>\n' + select,
            1,
        )
        print("inserted select after form open")

js2 = js
js2 = js2.replace('const API = "";', 'const API = ".";')
js2 = js2.replace("const API = '';", "const API = '.';")
js2 = js2.replace('const API="";', 'const API=".";')
if not re.search(r'const\s+API\s*=\s*["\']\.', js2):
    js2 = 'const API = ".";\n' + js2
    print("forced API=.")

js2 = js2.replace(
    'productSelect.addEventListener("change"',
    'productSelect && productSelect.addEventListener("change"',
    1,
)
js2 = re.sub(r"fetch\(\s*(['\"])/api/", r"fetch(\1./api/", js2)

html_path.write_text(html, encoding="utf-8")
js_path.write_text(js2, encoding="utf-8")
print("ok product_id", 'id="product_id"' in html)
print("api line", next(l for l in js2.splitlines() if "const API" in l))

subprocess.check_call(["systemctl", "restart", "zeus-products-flash"])
print("restarted")
