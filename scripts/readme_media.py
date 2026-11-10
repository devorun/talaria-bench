"""Build the README media from the gallery renders and the screenshots:

* docs/img/banner.png (2:1, the catalog image): the Caduceus photo next to its 3D model, four gallery robots,
  the name and the headline. Laid out as HTML and rendered with headless Chromium.
* docs/img/banner-x.png (1500x500): the cover for an X / social profile: the logo, the name and the tagline.
* docs/img/tour.gif: gallery -> robot page -> report card -> replay -> compare -> BLOCKED -> PASS.
* docs/img/screens/*.png are re-saved with a 256-colour palette (README use only; keeps the repository small).

Dev tool (needs Playwright and Pillow, which are not plugin dependencies). Run after render_gallery.py and
ui_screens.py:

    python talaria-bench/scripts/readme_media.py
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "img"
SCREENS = IMG / "screens"
FONT_DIRS = [Path("/mnt/c/Windows/Fonts"), Path("C:/Windows/Fonts"), Path("/Library/Fonts"),
             Path("/usr/share/fonts/truetype/dejavu")]
FONTS = {400: ["segoeui.ttf", "Arial.ttf", "DejaVuSans.ttf"], 600: ["seguisb.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"],
         700: ["segoeuib.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"]}
BG = (11, 31, 34)
INK = (236, 244, 242)
HERMES_NAV_PX = 240          # the dashboard's own navigation column, left out of the tour frames


def font_file(weight: int) -> Path | None:
    for d in FONT_DIRS:
        for n in FONTS[weight]:
            if (d / n).is_file():
                return d / n
    return None


def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


BANNER = """<!doctype html><html><head><meta charset="utf-8"><style>
@@FACES@@
* { box-sizing: border-box; }
html, body { margin: 0; }
body { width: 1200px; height: 600px; overflow: hidden; color: #ecf4f2; font-family: 'Banner', 'Segoe UI', system-ui, sans-serif;
  background: radial-gradient(90% 120% at 12% 0%, #14403f 0%, #0b1f22 55%, #081619 100%); position: relative; }
body::before { content: ""; position: absolute; inset: 0; opacity: .5;
  background-image: linear-gradient(rgba(255,255,255,.045) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px);
  background-size: 40px 40px; mask-image: radial-gradient(70% 90% at 30% 40%, #000 0%, transparent 100%); }
.left { position: absolute; left: 56px; top: 54px; width: 500px; }
.pill { display: inline-block; font-size: 12.5px; font-weight: 700; letter-spacing: .14em; color: #ffd678; padding: 5px 11px;
  border: 1px solid rgba(255,214,120,.45); border-radius: 99px; }
h1 { margin: 18px 0 0; font-size: 62px; line-height: 1; font-weight: 700; letter-spacing: -.02em; display: flex; align-items: center; gap: 16px; }
h1 img { width: 66px; height: 66px; border-radius: 17px; box-shadow: 0 0 0 1px rgba(255,255,255,.14), 0 14px 30px -16px #000; }
.head { margin: 18px 0 0; font-size: 27px; line-height: 1.25; font-weight: 400; }
.head b { display: block; margin-top: 6px; font-weight: 700; color: #ffd678; }
ul { list-style: none; margin: 30px 0 0; padding: 0; display: grid; gap: 11px; font-size: 18.5px; color: #b4d0ca; }
li { display: flex; gap: 12px; align-items: center; }
li::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: #ffd678; flex: none; }
.foot { position: absolute; left: 56px; bottom: 40px; font-size: 15px; color: #8fb3ac; letter-spacing: .02em; }
.right { position: absolute; left: 596px; top: 46px; width: 560px; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.card { position: relative; height: 344px; border-radius: 18px; overflow: hidden; border: 1px solid rgba(255,255,255,.16);
  box-shadow: 0 24px 50px -28px #000; background: #e6e9ee; }
.card img { width: 100%; height: 100%; object-fit: cover; display: block; }
.card.sim img { object-position: 47% 50%; }
.tag { position: absolute; left: 12px; bottom: 12px; font-size: 12.5px; font-weight: 700; letter-spacing: .12em; color: #fff;
  padding: 5px 10px; border-radius: 8px; background: rgba(18,21,27,.78); border: 1px solid rgba(255,255,255,.25); }
.tag.real { background: rgba(22,120,84,.92); }
.row { margin-top: 14px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.row div { height: 104px; border-radius: 13px; overflow: hidden; border: 1px solid rgba(255,255,255,.16); background: #e6e9ee; }
.row img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cap { margin-top: 12px; font-size: 14.5px; color: #8fb3ac; }
</style></head><body>
<div class="left">
  <span class="pill">HERMES AGENT PLUGIN</span>
  <h1><img src="@@LOGO@@">Talaria Bench</h1>
  <p class="head">Test your DIY robot in physics<br>before it moves.<b>No GPU, no CAD.</b></p>
  <ul>
    <li>Robot from a photo and a few measurements</li>
    <li>Arena benchmark with a report card</li>
    <li>Compare designs before you build</li>
    <li>Every real move screened in simulation</li>
  </ul>
</div>
<div class="foot">MuJoCo &nbsp;·&nbsp; CPU only &nbsp;·&nbsp; hobby servo robots</div>
<div class="right">
  <div class="pair">
    <div class="card"><img src="@@PHOTO@@"><span class="tag real">REAL</span></div>
    <div class="card sim"><img src="@@RENDER@@"><span class="tag">SIMULATION</span></div>
  </div>
  <div class="row">@@THUMBS@@</div>
  <div class="cap">Bundled robots: spider, dog, humanoid, arm, biped and Caduceus</div>
</div>
</body></html>"""


def banner() -> Path:
    faces = ""
    for weight in (400, 600, 700):
        f = font_file(weight)
        if f:
            faces += (f"@font-face {{ font-family: 'Banner'; font-weight: {weight}; "
                      f"src: url('{data_uri(f, 'font/ttf')}'); }}\n")
    thumbs = "".join(f'<div><img src="{data_uri(IMG / "gallery" / "thumbs" / f"{n}.png", "image/png")}"></div>'
                     for n in ("spider8", "dog12", "humanoid16", "arm6"))
    html = (BANNER.replace("@@FACES@@", faces)
            .replace("@@PHOTO@@", data_uri(ROOT / "examples" / "robots" / "caduceus_front.jpg", "image/jpeg"))
            .replace("@@RENDER@@", data_uri(IMG / "gallery" / "thumbs" / "caduceus.png", "image/png"))
            .replace("@@THUMBS@@", thumbs)
            .replace("@@LOGO@@", data_uri(IMG / "logo-tile.png", "image/png")))
    page_file = Path(tempfile.mkdtemp()) / "banner.html"
    page_file.write_text(html, encoding="utf-8")
    out = IMG / "banner.png"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 600}, device_scale_factor=2)
        page.goto(page_file.as_uri())
        page.wait_for_timeout(400)
        page.screenshot(path=str(out))
        browser.close()
    # Rendered at 2x for clean edges, kept at 1600x800: sharp at GitHub's README width, well under 1 MB.
    Image.open(out).convert("RGB").resize((1600, 800), Image.LANCZOS).save(out, optimize=True)
    return out


BANNER_X = """<!doctype html><html><head><meta charset="utf-8"><style>
@@FACES@@
* { box-sizing: border-box; }
html, body { margin: 0; }
body { width: 1500px; height: 500px; overflow: hidden; color: #ecf4f2; font-family: 'Banner', 'Segoe UI', system-ui, sans-serif;
  background: radial-gradient(80% 140% at 18% 20%, #16403f 0%, #0c1f22 55%, #081518 100%); position: relative; }
body::before { content: ""; position: absolute; inset: 0; opacity: .5;
  background-image: linear-gradient(rgba(255,255,255,.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.04) 1px, transparent 1px);
  background-size: 44px 44px; mask-image: radial-gradient(60% 100% at 30% 50%, #000 0%, transparent 100%); }
.glow { position: absolute; left: 40px; top: 20px; width: 470px; height: 470px; border-radius: 50%;
  background: radial-gradient(closest-side, rgba(255,214,120,.20), transparent); }
.logo { position: absolute; left: 70px; top: 60px; width: 380px; height: 380px; object-fit: contain;
  filter: drop-shadow(0 18px 30px rgba(0,0,0,.45)); }
.text { position: absolute; left: 500px; top: 0; height: 500px; width: 520px; display: flex; flex-direction: column; justify-content: center; }
.pill { align-self: flex-start; font-size: 14px; font-weight: 700; letter-spacing: .15em; color: #ffd678; padding: 6px 13px;
  border: 1px solid rgba(255,214,120,.45); border-radius: 99px; }
h1 { margin: 20px 0 0; font-size: 88px; line-height: 1; font-weight: 700; letter-spacing: -.025em; }
.tag { margin: 18px 0 0; font-size: 38px; line-height: 1.15; font-weight: 700; color: #ffd678; }
.sub { margin: 16px 0 0; font-size: 22px; color: #a9cbc4; letter-spacing: .01em; }
.grid { position: absolute; left: 1086px; top: 62px; display: grid; grid-template-columns: 1fr 1fr; gap: 14px; width: 360px; }
.grid div { height: 172px; border-radius: 16px; overflow: hidden; border: 1px solid rgba(255,255,255,.16);
  box-shadow: 0 22px 44px -26px #000; background: #e6e9ee; }
.grid img { width: 100%; height: 100%; object-fit: cover; display: block; }
.lab { position: absolute; right: 54px; bottom: 36px; font-size: 13px; font-weight: 700; letter-spacing: .12em; color: #8fb3ac; }
</style></head><body>
<div class="glow"></div><img class="logo" src="@@LOGO@@">
<div class="text"><span class="pill">HERMES AGENT PLUGIN</span><h1>Talaria Bench</h1>
  <div class="tag">Test before it moves.</div><div class="sub">DIY robots in physics &nbsp;·&nbsp; no GPU, no CAD</div></div>
<div class="grid">@@THUMBS@@</div><div class="lab">SIMULATION</div>
</body></html>"""


def banner_x() -> Path:
    faces = ""
    for weight in (400, 600, 700):
        f = font_file(weight)
        if f:
            faces += (f"@font-face {{ font-family: 'Banner'; font-weight: {weight}; "
                      f"src: url('{data_uri(f, 'font/ttf')}'); }}\n")
    thumbs = "".join(f'<div><img src="{data_uri(IMG / "gallery" / "thumbs" / f"{n}.png", "image/png")}"></div>'
                     for n in ("spider8", "dog12", "humanoid16", "arm6"))
    html = (BANNER_X.replace("@@FACES@@", faces)
            .replace("@@LOGO@@", data_uri(IMG / "logo.png", "image/png"))
            .replace("@@THUMBS@@", thumbs))
    page_file = Path(tempfile.mkdtemp()) / "banner-x.html"
    page_file.write_text(html, encoding="utf-8")
    out = IMG / "banner-x.png"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 500}, device_scale_factor=2)
        page.goto(page_file.as_uri())
        page.wait_for_timeout(400)
        page.screenshot(path=str(out))
        browser.close()
    Image.open(out).convert("RGB").resize((1500, 500), Image.LANCZOS).save(out, optimize=True)
    return out


def pil_font(weight: int, size: int) -> ImageFont.FreeTypeFont:
    f = font_file(weight)
    return ImageFont.truetype(str(f), size) if f else ImageFont.load_default(size)


def tour() -> Path:
    shots = [("dashboard-gallery", "1  Gallery: seven robots in 3D (simulation)"),
             ("dashboard-robot-caduceus", "2  A robot next to its photo"),
             ("dashboard-report-spider8", "3  One click: the report card"),
             ("dashboard-report-spider8-replay", "4  Replay the median and the worst world"),
             ("dashboard-compare-spider8-high-step", "5  Compare design variants on the same worlds"),
             ("dashboard-check-arms_up_both-blocked", "6  Preflight blocks a move that tips"),
             ("dashboard-check-arms_up_alternating-pass", "7  A revised move passes the gate")]
    W, H, BAR = 960, 640, 44
    frames = []
    for name, caption in shots:
        im = Image.open(SCREENS / f"{name}.png").convert("RGB")
        im = im.crop((HERMES_NAV_PX, 0, im.width, im.height))
        im = im.resize((W, int(im.height * W / im.width)), Image.LANCZOS).crop((0, 0, W, H - BAR))
        frame = Image.new("RGB", (W, H), BG)
        frame.paste(im, (0, BAR))
        ImageDraw.Draw(frame).text((16, 9), caption, font=pil_font(600, 21), fill=INK)
        frames.append(frame.quantize(colors=160, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    out = IMG / "tour.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=2600, loop=0, optimize=True)
    return out


def shrink_screens() -> None:
    """Screenshots are README material only: a 256-colour palette cuts them to about a third."""
    for path in sorted(SCREENS.glob("*.png")):
        im = Image.open(path)
        if im.mode == "P":
            continue
        before = path.stat().st_size
        im.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                                   dither=Image.Dither.FLOYDSTEINBERG).save(path, optimize=True)
        print(path.relative_to(ROOT), f"{before // 1024} -> {path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    for p in (banner(), banner_x(), tour()):                      # the tour is built from the full-colour screenshots
        print(p.relative_to(ROOT), f"{p.stat().st_size // 1024} KB")
    shrink_screens()
