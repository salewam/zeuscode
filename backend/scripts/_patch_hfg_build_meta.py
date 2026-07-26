#!/usr/bin/env python3
from pathlib import Path
import re

html_path = Path("/var/www/sto-demos/hfg/index.html")
css_path = Path("/var/www/sto-demos/hfg/styles.css")
html = html_path.read_text(encoding="utf-8")

block = """
  <aside class="zc-build" aria-label="Сборка ZeusCode">
    <p class="zc-build__price"><strong>41 ₽</strong></p>
    <p class="zc-build__time">Время: ~2 мин 48 сек (167.5 с)</p>
    <table class="zc-build__table">
      <thead>
        <tr><th>Роль</th><th>Нейронка</th><th>Время</th></tr>
      </thead>
      <tbody>
        <tr><td>судья / synth / review</td><td><code>gemini-3-pro</code></td><td>—</td></tr>
        <tr><td>дизайн</td><td><code>claude-haiku-4-5</code></td><td>39 с</td></tr>
        <tr><td>фронт</td><td><code>gemini-3-flash</code></td><td>54 с</td></tr>
        <tr><td>бэк</td><td><code>gpt-5-2</code></td><td>13 с</td></tr>
        <tr><td>тесты</td><td><code>claude-haiku-4-5</code></td><td>21 с</td></tr>
      </tbody>
    </table>
  </aside>
"""

html2, n = re.subn(
    r'<aside class="zc-build"[\s\S]*?</aside>',
    block.strip(),
    html,
    count=1,
)
if n == 0:
    html2 = html.replace("</footer>", block + "\n  </footer>")
html_path.write_text(html2, encoding="utf-8")

css = css_path.read_text(encoding="utf-8")
css = re.sub(r"\n?\.zc-build[\s\S]*?\.zc-build code\{[^}]*\}", "", css)
css += """
.zc-build{margin:1.5rem auto 0;width:min(100% - 2rem,1100px);padding:1.1rem 1.25rem;background:#1a1c1e;color:#f3f1ec;border-radius:10px;font-size:.92rem;line-height:1.45}
.zc-build__price{margin:0 0 .35rem}
.zc-build__price strong{color:#c47a2c;font-size:1.35rem}
.zc-build__time{margin:0 0 .85rem;opacity:.85}
.zc-build__table{width:100%;border-collapse:collapse}
.zc-build__table th,.zc-build__table td{text-align:left;padding:.45rem .35rem;border-bottom:1px solid #333}
.zc-build__table th{opacity:.7;font-weight:600}
.zc-build__table code{color:#e8c49a}
"""
css_path.write_text(css, encoding="utf-8")

Path("/var/www/sto-demos/hfg/BUILD.json").write_text(
    """{
  "price_rub": 41,
  "wall_s": 167.5,
  "wall_human": "2 мин 48 сек",
  "gate": "PASS 100",
  "roles": [
    {"role": "судья / synth / review", "model": "gemini-3-pro", "time_s": null},
    {"role": "дизайн", "model": "claude-haiku-4-5", "time_s": 39},
    {"role": "фронт", "model": "gemini-3-flash", "time_s": 54},
    {"role": "бэк", "model": "gpt-5-2", "time_s": 13},
    {"role": "тесты", "model": "claude-haiku-4-5", "time_s": 21}
  ]
}
""",
    encoding="utf-8",
)
print("ok n=", n)
