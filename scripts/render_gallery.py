"""Render every gallery robot standing (home pose, 3/4 view, light background) with MuJoCo offscreen
(EGL), plus a combined sheet. Dev tool for the README and the gallery thumbnails; needs Pillow.

    MUJOCO_GL=egl python talaria-bench/scripts/render_gallery.py
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devcli import load_package  # noqa: E402

load_package()
from talaria_bench.builder import _set_home, base_model  # noqa: E402
from talaria_bench.spec import load_spec  # noqa: E402

OUT = ROOT / "docs" / "img" / "gallery"
THUMBS = OUT / "thumbs"
W, H, SS = 800, 600, 2                        # output size, supersampling
BG_TOP, BG_BOTTOM = (247, 248, 250), (226, 230, 236)
FLOOR = (0.90, 0.91, 0.93, 1.0)


def font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def background() -> Image.Image:
    grad = np.linspace(0, 1, H * SS)[:, None]
    top, bottom = np.array(BG_TOP, float), np.array(BG_BOTTOM, float)
    rows = (top * (1 - grad) + bottom * grad).astype(np.uint8)
    return Image.fromarray(np.repeat(rows[:, None, :], W * SS, axis=1))


def render(spec) -> Image.Image:
    model, _, _ = base_model(spec)
    model = mujoco.MjModel.from_xml_string(base_model(spec)[2])      # a private copy we may restyle
    model.vis.global_.offwidth, model.vis.global_.offheight = W * SS, H * SS
    model.vis.headlight.ambient[:] = 0.42
    model.vis.headlight.diffuse[:] = 0.5
    model.vis.headlight.specular[:] = 0.12
    model.vis.quality.shadowsize = 8192
    model.vis.map.znear = 0.002
    floor = model.geom("floor").id
    model.geom_rgba[floor] = FLOOR
    data = mujoco.MjData(model)
    _set_home(model, data, spec)
    mujoco.mj_forward(model, data)

    ids = [model.geom(p.name).id for p in spec.parts]
    pts = np.array([data.geom_xpos[i] for i in ids])
    radius = max(float(np.max(model.geom_rbound[ids])), 0.01)
    lo, hi = pts.min(0) - radius * 0.6, pts.max(0) + radius * 0.6
    center = (lo + hi) / 2
    extent = float(np.linalg.norm(hi - lo))

    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = center
    cam.distance = max(extent * 1.55, 0.25)
    cam.azimuth = 140.0                         # from the front right (the robot faces +x)
    cam.elevation = -20.0
    opt = mujoco.MjvOption()
    renderer = mujoco.Renderer(model, H * SS, W * SS)
    renderer.update_scene(data, camera=cam, scene_option=opt)
    scene = renderer.scene
    scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = True
    scene.flags[mujoco.mjtRndFlag.mjRND_SKYBOX] = False
    rgb = renderer.render().copy()
    renderer.enable_depth_rendering()
    renderer.update_scene(data, camera=cam, scene_option=opt)
    depth = renderer.render().copy()
    renderer.close()

    # Fade the floor out with distance from the robot and put the robot on a soft gradient.
    img = Image.fromarray(rgb)
    sky = depth >= depth.max() * 0.999
    far = np.clip((depth - cam.distance * 0.9) / (cam.distance * 0.7), 0, 1)
    alpha = np.where(sky, 0.0, 1.0 - far ** 1.2)
    mask = Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(SS * 2))
    out = background()
    out.paste(img, (0, 0), mask)
    return out.resize((W, H), Image.LANCZOS)


def label(img: Image.Image, title: str, sub: str) -> Image.Image:
    d = ImageDraw.Draw(img)
    d.text((22, H - 58), title, font=font(24), fill=(36, 41, 51))
    d.text((22, H - 28), sub, font=font(13), fill=(110, 117, 128))
    tag = "SIMULATION"
    f = font(11)
    tw = d.textlength(tag, font=f)
    d.rounded_rectangle((W - tw - 34, 16, W - 16, 38), radius=6, fill=(255, 255, 255), outline=(210, 214, 220))
    d.text((W - tw - 25, 20), tag, font=f, fill=(85, 92, 104))
    return img


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    THUMBS.mkdir(parents=True, exist_ok=True)
    tiles = []
    for path in sorted((ROOT / "examples" / "robots").glob("*.yaml")):
        if ".calibration" in path.name:
            continue
        spec = load_spec(path)
        plain = render(spec)
        # The UI's gallery cards print the name and the SIM tag themselves: unlabelled, smaller thumbnails.
        plain.resize((W // 2, H // 2), Image.LANCZOS).save(THUMBS / f"{spec.name}.png", optimize=True)
        img = label(plain.copy(), spec.title or spec.name,
                    f"{spec.name} · {len(spec.joint_parts)} servos · {round(spec.total_mass_g)} g")
        img.save(OUT / f"{spec.name}.png", optimize=True)
        tiles.append(img)
        print("rendered", spec.name)
    cols = 4
    rows = math.ceil(len(tiles) / cols)
    gap = 16
    sheet = Image.new("RGB", (cols * W // 2 + (cols + 1) * gap, rows * H // 2 + (rows + 1) * gap), (255, 255, 255))
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet.paste(t.resize((W // 2, H // 2), Image.LANCZOS), (gap + c * (W // 2 + gap), gap + r * (H // 2 + gap)))
    sheet.save(OUT.parent / "gallery.png", optimize=True)
    print("sheet", OUT.parent / "gallery.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
