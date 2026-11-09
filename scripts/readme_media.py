"""Build the README media from existing renders and screenshots: docs/img/banner.png (1200x600, the 2:1 catalog
image) and docs/img/tour.gif (gallery -> report card -> compare -> BLOCKED -> PASS). Dev tool (needs Pillow,
which is not a plugin dependency).

    python talaria-bench/scripts/readme_media.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "img"
FONT_DIRS = [Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts"), Path("C:/Windows/Fonts")]

BG = (14, 38, 40)
INK = (236, 244, 242)
MUTED = (150, 186, 180)
ACCENT = (255, 214, 120)


def font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    names = ["DejaVuSans-Bold.ttf", "arialbd.ttf"] if bold else ["DejaVuSans.ttf", "arial.ttf"]
    for d in FONT_DIRS:
        for n in names:
            if (d / n).is_file():
                return ImageFont.truetype(str(d / n), size)
    return ImageFont.load_default(size)


def card(img: Image.Image, size: tuple[int, int], label: str, label_bg: tuple[int, int, int]) -> Image.Image:
    out = ImageOps.fit(img.convert("RGB"), size, Image.LANCZOS, centering=(0.5, 0.45))
    d = ImageDraw.Draw(out)
    f = font(True, 15)
    w = d.textlength(label, font=f)
    d.rounded_rectangle((12, size[1] - 40, 12 + w + 20, size[1] - 12), radius=8, fill=label_bg)
    d.text((22, size[1] - 35), label, font=f, fill=(255, 255, 255))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=18, fill=255)
    out.putalpha(mask)
    return out


def banner() -> Path:
    W, H = 1200, 600
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((56, 70), "TALARIA BENCH", font=font(True, 54), fill=INK)
    d.text((58, 150), "Test your DIY robot in physics", font=font(False, 28), fill=INK)
    d.text((58, 186), "before it moves.", font=font(False, 28), fill=INK)
    d.text((58, 232), "No GPU, no CAD.", font=font(True, 28), fill=ACCENT)
    lines = ["Robot from a photo + measurements", "Arena benchmark with a report card",
             "Compare designs before you build", "Every real move screened in simulation"]
    for i, line in enumerate(lines):
        y = 300 + i * 36
        d.ellipse((60, y + 8, 70, y + 18), fill=ACCENT)
        d.text((84, y), line, font=font(False, 21), fill=MUTED)
    d.text((58, 530), "A Hermes Agent plugin  ·  MuJoCo  ·  CPU only", font=font(False, 17), fill=MUTED)

    photo = Image.open(ROOT / "examples" / "robots" / "caduceus_front.jpg")
    render = Image.open(IMG / "gallery" / "caduceus.png")
    cw, ch = 290, 340
    real = card(photo, (cw, ch), "REAL", (30, 120, 90))
    sim = card(render, (cw, ch), "SIMULATION", (60, 70, 90))
    im.paste(real, (560, 50), real)
    im.paste(sim, (870, 50), sim)
    tw, th = 140, 105
    for i, name in enumerate(("spider8", "dog12", "humanoid16", "arm6")):
        t = ImageOps.fit(Image.open(IMG / "gallery" / "thumbs" / f"{name}.png").convert("RGB"), (tw, th),
                         Image.LANCZOS)
        mask = Image.new("L", (tw, th), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, tw - 1, th - 1), radius=12, fill=255)
        im.paste(t, (560 + i * (tw + 10), 420), mask)
    d.text((560, 538), "Bundled robots: spider, dog, humanoid, arm, biped, Caduceus", font=font(False, 16),
           fill=MUTED)
    out = IMG / "banner.png"
    im.save(out, optimize=True)
    return out


def tour() -> Path:
    shots = [("dashboard-gallery", "1  Gallery: robots in 3D (simulation)"),
             ("dashboard-report-spider8", "2  One-click benchmark: the report card"),
             ("dashboard-compare-spider8-high-step", "3  Compare design variants"),
             ("dashboard-check-arms_up_both-blocked", "4  Preflight blocks a risky move"),
             ("dashboard-check-arms_up_alternating-pass", "5  A revised move passes the gate")]
    W, H = 900, 600
    frames = []
    for name, caption in shots:
        im = Image.open(IMG / "screens" / f"{name}.png").convert("RGB").crop((240, 0, 1440, 960))
        im = im.resize((W, int(im.height * W / im.width)), Image.LANCZOS).crop((0, 0, W, H - 44))
        frame = Image.new("RGB", (W, H), BG)
        frame.paste(im, (0, 44))
        ImageDraw.Draw(frame).text((16, 10), caption, font=font(True, 20), fill=INK)
        frames.append(frame.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    out = IMG / "tour.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=2600, loop=0, optimize=True)
    return out


DESKTOP_SIDEBAR_PX = 261     # the Desktop session list (chat titles, user name) is never published


def crop_desktop_shots() -> None:
    for path in sorted((IMG / "screens").glob("desktop-*.png")):
        im = Image.open(path)
        if im.width == 1440:
            im.crop((DESKTOP_SIDEBAR_PX, 0, im.width, im.height)).save(path, optimize=True)
            print("cropped", path.relative_to(ROOT))


if __name__ == "__main__":
    crop_desktop_shots()
    for p in (banner(), tour()):
        print(p.relative_to(ROOT), f"{p.stat().st_size // 1024} KB")
