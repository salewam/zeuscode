#!/usr/bin/env python3
import json, re, sys
from pathlib import Path

sys.path.insert(0, "/opt/zeuscode/backend")
from app.evidence import scan_artifacts, score_from_findings

rep = json.load(open("/tmp/sto-cheap4-bake/REPORT.json"))
print("balance", rep.get("balance_start"), "->", rep.get("balance_end"))
for d in sorted(Path("/tmp/sto-cheap4-bake").iterdir()):
    if not d.is_dir():
        continue
    root = d / "src"
    fe = root / "frontend" / "index.html"
    if not fe.exists():
        print(d.name, "NO FE")
        continue
    arts = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in {".html", ".css", ".js", ".py", ".json"}:
            rel = "/src/" + str(p.relative_to(root))
            role = (
                "frontend"
                if "frontend" in rel
                else ("design" if "design" in rel else "backend")
            )
            arts.append(
                {"path": rel, "role": role, "content": p.read_text(errors="ignore")}
            )
    f = scan_artifacts(arts)
    score, grade, gate = score_from_findings(f)
    majors = sorted({x["code"] for x in f if x["severity"] == "major"})
    h = fe.read_text()
    css_p = root / "frontend" / "styles.css"
    c = css_p.read_text() if css_p.exists() else ""
    h1 = re.sub(
        r"<[^>]+>",
        " ",
        (re.search(r"<h1[^>]*>([\s\S]*?)</h1>", h) or ["", ""])[1],
    ).strip()[:70]
    imgs = len(re.findall(r"<img[^>]+src=[\"']https", h, re.I))
    vit = re.search(
        r"\.vitrine\s+img\s*\{[^}]*height\s*:\s*(\d+)px", c, re.I | re.S
    )
    print(f"{d.name:22} {gate:16} {score:3} majors={majors}")
    print(
        f"  html={len(h)} img={imgs} vit_h={vit.group(1) if vit else 0} h1={h1!r}"
    )

print("REPORT runs:")
for r in rep.get("runs", []):
    print(
        r.get("model"),
        r.get("local_gate"),
        r.get("local_score"),
        r.get("local_majors"),
        "wall",
        r.get("wall_s"),
        "html",
        (r.get("fe") or {}).get("html_bytes"),
    )
