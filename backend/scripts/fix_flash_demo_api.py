from pathlib import Path
import re
import subprocess
import time

p = Path("/opt/zeuscode/data/demos/bouquet-flash/frontend/app.js")
raw = p.read_text(encoding="utf-8")
raw2 = re.sub(r"fetch\(\s*(['\"])/api/", r"fetch(\1./api/", raw)
p.write_text(raw2, encoding="utf-8")
print("patched", raw != raw2)
subprocess.check_call(["systemctl", "restart", "zeus-bouquet-flash"])
time.sleep(1)
print(subprocess.check_output(["curl", "-sS", "https://zeuscode.ru/demo/bouquet-flash/api/bouquets"], text=True)[:120])
