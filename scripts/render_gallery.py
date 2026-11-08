"""Render every gallery robot with the app's own three.js stage (rounded parts, materials, soft shadows, the
same lights) in its showcase pose (spec look.showcase), at 2x device pixels, through headless Chromium.
Writes docs/img/gallery/<robot>.png (labelled), docs/img/gallery/thumbs/<robot>.png (for the app's gallery
cards) and the combined sheet docs/img/gallery.png. Dev tool: needs Playwright + Pillow and a UI build.

    (cd talaria-bench/ui && npm run build)
    python talaria-bench/scripts/render_gallery.py
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devcli import load_package  # noqa: E402

load_package()
from talaria_bench.runtime import EXAMPLES, Runtime  # noqa: E402
from talaria_bench.spec import load_spec  # noqa: E402
from talaria_bench.webapi import WebAPI  # noqa: E402

OUT = ROOT / "docs" / "img" / "gallery"
THUMBS = OUT / "thumbs"
BUNDLE = ROOT / "ui" / "render" / "render.js"
SCALE = 2

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body { margin: 0; background: transparent; font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; }
#frame { position: relative; overflow: hidden; color: #1f2937;
  background: radial-gradient(120% 90% at 50% 18%, #fbfbfc 0%, #eceef2 55%, #dfe3e9 100%); }
#stage { position: absolute; inset: 0; }
#stage canvas { width: 100% !important; height: 100% !important; display: block; }
#info { position: absolute; left: 22px; bottom: 18px; }
#name { font-size: 22px; font-weight: 700; letter-spacing: -0.01em; display: flex; gap: 8px; align-items: center; }
#sub { font-size: 12.5px; color: #6b7280; margin-top: 3px; }
#badge { display: none; align-items: center; padding: 1px 8px; border-radius: 6px; font-size: 12px; font-weight: 800; color: #fff; }
#sim { position: absolute; right: 16px; top: 14px; font-size: 10.5px; font-weight: 750; letter-spacing: .12em;
  padding: 3px 8px; border-radius: 6px; color: #4b5563; background: rgba(255,255,255,.85); border: 1px solid #d5d9e0; }
</style></head><body>
<div id="frame"><div id="stage"></div>
<div id="sim">SIMULATION</div>
<div id="info"><div id="name"></div><div id="sub"></div></div>
</div>
<script>BUNDLE</script>
<script>
  // the badge sits next to the name
  const n = document.getElementById('name'); const b = document.createElement('span'); b.id = 'badge'; n.after(b);
  document.getElementById('info').insertBefore(b, document.getElementById('sub'));
</script>
</body></html>"""


def robots() -> list[dict]:
    api = WebAPI(Runtime(overrides={"data_dir": tempfile.mkdtemp()}))
    out = []
    for path in sorted(EXAMPLES.glob("*.yaml")):
        if ".calibration" in path.name:
            continue
        spec = load_spec(path)
        pose = api.render(spec, (spec.look.get("showcase") or {}).get("joints"))
        out.append({"name": spec.name, "title": spec.title or spec.name, "look": spec.look, "parts": pose["parts"],
                    "sub": f"{spec.name} · {len(spec.joint_parts)} servos · {round(spec.total_mass_g)} g"})
    return out


def main() -> int:
    if not BUNDLE.is_file():
        raise SystemExit("build the UI first: cd ui && npm run build")
    OUT.mkdir(parents=True, exist_ok=True)
    THUMBS.mkdir(parents=True, exist_ok=True)
    html = Path(tempfile.mkdtemp()) / "render.html"
    html.write_text(PAGE.replace("BUNDLE", BUNDLE.read_text(encoding="utf-8")), encoding="utf-8")
    data = robots()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        for kind, (w, h), folder, label in (("image", (800, 600), OUT, True), ("thumb", (480, 360), THUMBS, False)):
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=SCALE)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(html.as_uri())
            page.evaluate(f"document.getElementById('frame').style.cssText += ';width:{w}px;height:{h}px'")
            for robot in data:
                page.evaluate("([d, l]) => window.renderRobot(d, { label: l })", [robot, label])
                page.wait_for_timeout(400)
                page.locator("#frame").screenshot(path=str(folder / f"{robot['name']}.png"))
                print(kind, robot["name"], f"{w * SCALE}x{h * SCALE}")
            if errors:
                raise SystemExit(f"render errors: {errors[:3]}")
            page.close()
        browser.close()
    tiles = [Image.open(OUT / f"{r['name']}.png") for r in data]
    cols, gap = 4, 24
    tw, th = tiles[0].width // 2, tiles[0].height // 2
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * gap, rows * th + (rows + 1) * gap), (255, 255, 255))
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet.paste(t.convert("RGB").resize((tw, th), Image.LANCZOS), (gap + c * (tw + gap), gap + r * (th + gap)))
    sheet.save(OUT.parent / "gallery.png", optimize=True)
    print("sheet", (OUT.parent / "gallery.png").relative_to(ROOT), sheet.size)
    json.dumps(len(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
