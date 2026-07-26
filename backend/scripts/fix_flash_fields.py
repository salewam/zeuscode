from pathlib import Path
import re
import subprocess

p = Path("/opt/zeuscode/data/demos/bouquet-flash/frontend/app.js")
out = p.read_text(encoding="utf-8")
out = out.replace("${i.title}", "${i.name || i.title}")
out = out.replace("${i.image}", "${i.image || i.image_url}")
out = re.sub(r"state\.cart\.title", "(state.cart.name || state.cart.title)", out)
out = re.sub(
    r"data-pick='\${JSON\.stringify\(i\)}'",
    'data-pick="${i.id}"',
    out,
)
if "window.__items" not in out:
    out = out.replace(
        "const items = await res.json();\n  const list = document.getElementById('catalog-list');",
        "const items = await res.json();\n  window.__items = items;\n  const list = document.getElementById('catalog-list');",
    )
out = out.replace(
    "state.cart = JSON.parse(e.target.dataset.pick);",
    "const id = Number(e.target.dataset.pick); state.cart = (window.__items||[]).find(x=>x.id===id) || {id, name:'Букет'};",
)
out = out.replace(
    "/* hardened: removed success alert — use role=status/alert */ undefined;",
    "const msg=document.querySelector('#form-msg,[role=status]'); if(msg) msg.textContent='Заказ принят';",
)
# wrap bare img in card__media if missing
if "card__media" not in out and "<img src=" in out:
    out = out.replace(
        '<img src="${i.image || i.image_url}" alt="${i.name || i.title}">',
        '<div class="card__media"><img src="${i.image || i.image_url}" alt="${i.name || i.title}"></div>',
    )
p.write_text(out, encoding="utf-8")
print("patched ok")
subprocess.check_call(["systemctl", "restart", "zeus-bouquet-flash"])
