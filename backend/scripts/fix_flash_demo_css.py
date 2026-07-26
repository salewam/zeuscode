from pathlib import Path

pack = Path("/opt/zeuscode/backend/app/agent_skills/frontend/templates/app-density.css").read_text(
    encoding="utf-8"
)
# deploy latest density template first
Path("/opt/zeuscode/backend/app/agent_skills/frontend/templates/app-density.css").write_text(
    pack, encoding="utf-8"
)

fe = Path("/opt/zeuscode/data/demos/bouquet-flash/frontend/styles.css")
body = fe.read_text(encoding="utf-8")
if "Auto-density pack" in body:
    body = body.split("/* Auto-density pack")[0].rstrip()
extra = "\n.screen{display:none}\n.screen.active{display:block}\n"
fe.write_text(body + "\n\n" + pack + extra, encoding="utf-8")
print("css bytes", fe.stat().st_size)
