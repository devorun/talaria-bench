"""Write the README diagrams as SVG with real text, each in a light and a dark variant (the README picks one
with <picture> and prefers-color-scheme): docs/img/diagram-{pipeline,gate,hardware}-{light,dark}.svg.
Dev tool, standard library only.

    python talaria-bench/scripts/diagrams.py
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parents[1] / "docs" / "img"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace"

THEMES = {
    "light": {"box": "#f6f8fa", "line": "#d0d7de", "ink": "#1f2328", "muted": "#57606a", "accent": "#0969da",
              "green": "#1a7f37", "red": "#cf222e", "amber": "#9a6700", "green_bg": "#dafbe1", "red_bg": "#ffebe9",
              "accent_bg": "#ddf4ff"},
    "dark": {"box": "#161b22", "line": "#30363d", "ink": "#e6edf3", "muted": "#8b949e", "accent": "#58a6ff",
             "green": "#3fb950", "red": "#f85149", "amber": "#d29922", "green_bg": "#12261e", "red_bg": "#25171c",
             "accent_bg": "#121d2f"},
}


class Svg:
    def __init__(self, width: int, height: int, theme: dict[str, str], title: str):
        self.t = theme
        self.w, self.h = width, height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="img" aria-label="{escape(title)}" font-family="{FONT}">',
            f"<title>{escape(title)}</title>",
            "<defs>" + "".join(
                f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
                f'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{theme[name]}"/></marker>'
                for name in ("muted", "green", "red")) + "</defs>",
        ]

    def box(self, x, y, w, h, title, lines=(), tone=None, step=None, mono_title=False):
        t = self.t
        fill = t[tone + "_bg"] if tone else t["box"]
        stroke = t[tone] if tone else t["line"]
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" '
                          f'stroke-width="1.5"/>')
        cx = x + w / 2
        ty = y + 32
        if step is not None:
            self.parts.append(f'<circle cx="{x + 22}" cy="{y + 24}" r="11" fill="{t["accent"]}"/>'
                              f'<text x="{x + 22}" y="{y + 28.5}" text-anchor="middle" font-size="12.5" font-weight="700" '
                              f'fill="{t["box"]}">{step}</text>')
            ty = y + 56
        family = f' font-family="{MONO}"' if mono_title else ""
        for i, part in enumerate(title.split("\n")):
            self.parts.append(f'<text x="{cx}" y="{ty + i * 19}" text-anchor="middle" font-size="15.5" font-weight="700" '
                              f'fill="{t[tone] if tone else t["ink"]}"{family}>{escape(part)}</text>')
        ly = ty + (len(title.split("\n")) - 1) * 19 + 24
        for i, line in enumerate(lines):
            self.parts.append(f'<text x="{cx}" y="{ly + i * 17}" text-anchor="middle" font-size="12.5" '
                              f'fill="{t["muted"]}">{escape(line)}</text>')

    def arrow(self, points, tone="muted", label=None, label_at=None, dashed=False):
        d = "M" + " L".join(f"{x} {y}" for x, y in points)
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        self.parts.append(f'<path d="{d}" fill="none" stroke="{self.t[tone]}" stroke-width="2" stroke-linejoin="round" '
                          f'marker-end="url(#arrow-{tone})"{dash}/>')
        if label:
            lx, ly = label_at
            self.parts.append(f'<text x="{lx}" y="{ly}" text-anchor="middle" font-size="11.5" font-weight="700" '
                              f'letter-spacing="0.6" fill="{self.t[tone]}">{escape(label)}</text>')

    def note(self, x, y, text, tone="muted", size=13, weight=400, anchor="middle"):
        self.parts.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" font-weight="{weight}" '
                          f'fill="{self.t[tone]}">{escape(text)}</text>')

    def save(self, path: Path) -> None:
        path.write_text("\n".join(self.parts + ["</svg>"]) + "\n", encoding="utf-8")


def pipeline(theme) -> Svg:
    s = Svg(1040, 232, theme, "How Talaria Bench works: robot spec, MuJoCo model, randomized worlds, "
                              "arena scenes, report card")
    w, h, gap, y = 176, 158, 40, 14
    boxes = [
        ("Robot spec", ["template + your numbers:", "parts in cm and g,", "hobby servo models"]),
        ("MuJoCo model", ["soft contacts by material,", "servo torque and speed,", "servo free play"]),
        ("Randomized worlds", ["friction, mass, torque,", "latency, offsets, floor tilt;", "30 per scene, 60 per move"]),
        ("Arena scenes", ["flat floor, ramps, bars,", "push, slippery floor,", "payload, standing moves"]),
        ("Report card", ["pass rate, median,", "worst world and the reason", "for each failure"]),
    ]
    for i, (title, lines) in enumerate(boxes):
        x = i * (w + gap)
        s.box(x, y, w, h, title, lines, step=i + 1, tone="accent" if i == 4 else None)
        if i:
            s.arrow([(x - gap + 5, y + h / 2), (x - 5, y + h / 2)])
    s.note(520, 214, "All of it is simulation, on a laptop CPU: no GPU, no CAD.")
    return s


def gate(theme) -> Svg:
    s = Svg(1040, 372, theme, "The motion gate: a move is checked in 60 fixed simulated worlds; only an approved move "
                              "passes the pre_tool_call hook to the virtual or real robot")
    w, h, gap, y = 176, 132, 40, 14
    cy = y + h / 2
    xs = [i * (w + gap) for i in range(5)]
    s.box(xs[0], y, w, h, "Hermes writes a move", ["keyframes, loops,", "easing, speed"])
    s.box(xs[1], y, w, h, "move_check", ["60 fixed simulated worlds,", "tip chance with a 95%", "Wilson interval, servo load"],
          mono_title=True)
    s.box(xs[2], y, w, h, "Approval key", ["for exactly this move,", "speed and robot spec"], tone="green")
    s.box(xs[3], y, w, h, "pre_tool_call hook", ["robot_play and robot_pose", "pass only with a", "matching approval"],
          mono_title=True)
    s.box(xs[4], y, w, h, "Virtual or real robot", ["the firmware clamps", "angles and speeds", "again on its own"])
    s.arrow([(xs[0] + w + 5, cy), (xs[1] - 5, cy)])
    s.arrow([(xs[1] + w + 5, cy), (xs[2] - 5, cy)], tone="green", label="PASS", label_at=(xs[1] + w + gap / 2, cy - 9))
    s.arrow([(xs[2] + w + 5, cy), (xs[3] - 5, cy)])
    s.arrow([(xs[3] + w + 5, cy), (xs[4] - 5, cy)])
    # The blocked branch, back to Hermes.
    by, bh = 222, 92
    bx, bw = xs[1] - 40, w + 80
    s.box(bx, by, bw, bh, "BLOCKED", ["the reasons and suggestions", "go back to Hermes, which revises"], tone="red")
    s.arrow([(xs[1] + w / 2, y + h + 5), (xs[1] + w / 2, by - 5)], tone="red")
    s.arrow([(bx - 5, by + bh / 2), (xs[0] + w / 2, by + bh / 2), (xs[0] + w / 2, y + h + 5)], tone="red", dashed=True)
    # No approval, no play.
    s.box(xs[3], by, 2 * w + gap, bh, "A changed move, speed or spec",
          ["has no approval: the hook refuses it", "until a new check passes"])
    s.arrow([(xs[3] + w / 2, by - 5), (xs[3] + w / 2, y + h + 5)], dashed=True)
    s.note(520, 356, "Simulation-based risk screening, not a safety guarantee.")
    return s


def hardware(theme) -> Svg:
    s = Svg(1040, 150, theme, "The hardware path: Hermes sends a checked move over LAN HTTP with a token to an ESP32, "
                              "which drives hobby servos through a PCA9685")
    w, h, gap, y = 176, 104, 40, 10
    boxes = [
        ("Hermes", ["robot_play with a", "checked move (keyframes)"]),
        ("LAN HTTP + token", ["plain HTTP on your", "own network"]),
        ("ESP32 firmware", ["clamps every angle and", "speed, no reflashing"]),
        ("PCA9685", ["16-channel PWM", "servo driver (I2C)"]),
        ("Hobby servos", ["SG90, MG90S,", "MG996R and friends"]),
    ]
    for i, (title, lines) in enumerate(boxes):
        x = i * (w + gap)
        s.box(x, y, w, h, title, lines)
        if i:
            s.arrow([(x - gap + 5, y + h / 2), (x - 5, y + h / 2)])
    s.note(520, 140, "No hardware? The virtual robot speaks the same HTTP API.")
    return s


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in (("pipeline", pipeline), ("gate", gate), ("hardware", hardware)):
        for theme_name, theme in THEMES.items():
            path = OUT / f"diagram-{name}-{theme_name}.svg"
            build(theme).save(path)
            print(path.relative_to(OUT.parents[1]), f"{path.stat().st_size} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
