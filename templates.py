"""Spec templates: a valid robot spec from a few numbers, so onboarding fills parameters instead of
hand-writing anchors and offsets.

* ``block_robot`` (Caduceus-like) and ``arm`` are fully parametric.
* ``biped4``, ``quadruped`` (8 or 12 servos), ``hexapod`` (12 or 18) and ``humanoid`` follow the proven
  layouts of the bundled examples (which stand and move in simulation) and scale their geometry uniformly
  to the given size; their gaits are joint angles, so they carry over.

Masses: give ``mass_g`` (total) when it is known. ``"unknown"`` (or leaving it out) estimates each part
from its volume and material plus the servo it carries, records which values are estimates, and widens
the randomized mass range (``worlds.mass_scale`` 0.7-1.3) so the bench covers the uncertainty.

``build(template, params)`` returns ``(spec_dict, notes)``; the dict is checked by ``parse_spec``.
"""

from __future__ import annotations

import copy
import math
import re
from pathlib import Path
from typing import Any, Callable

import yaml

from . import servos
from .spec import SpecError, parse_spec

EXAMPLES = Path(__file__).resolve().parent / "examples" / "robots"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
# Effective densities (g/cm^3) for estimates: printed parts are mostly air; foam board is very light.
DENSITY = {"foam": 0.04, "pla": 0.35, "wood": 0.55, "metal": 1.2, "rubber": 1.1}
ESTIMATE_MASS_RANGE = [0.7, 1.3]


class TemplateError(SpecError):
    pass


# ─── helpers ─────────────────────────────────────────────────────────────────────────────────────


def _num(params: dict, key: str, default: float, lo: float, hi: float, problems: list[str]) -> float:
    value = params.get(key, default)
    try:
        value = float(value)
    except (TypeError, ValueError):
        problems.append(f"{key} must be a number")
        return default
    if not lo <= value <= hi:
        problems.append(f"{key} must be between {lo:g} and {hi:g}")
        return default
    return value


def _choice(params: dict, key: str, default: Any, options, problems: list[str]) -> Any:
    value = params.get(key, default)
    if value not in options:
        problems.append(f"{key} must be one of {', '.join(map(str, options))}")
        return default
    return value


def _volume(part: dict) -> float:
    s = part["size"]
    if part.get("shape", "box") == "box":
        return s[0] * s[1] * s[2]
    if part["shape"] == "cylinder":
        return math.pi * s[0] ** 2 * s[1]
    return 4 / 3 * math.pi * s[0] ** 3


def _servo_mass(joint: dict | None) -> float:
    if not joint:
        return 0.0
    model = joint["servo"]["model"] if isinstance(joint["servo"], dict) else joint["servo"]
    return servos.lookup(model).mass_g


def _assign_masses(spec: dict, total: Any, notes: list[str], electronics_g: float = 40.0) -> None:
    """Total mass known: share it by volume (servo masses go to the parts that carry them). Unknown:
    estimate from volume x material density + servo masses + electronics in the root, and say so."""
    parts = spec["parts"]
    est = []
    for p in parts:
        density = DENSITY.get(p.get("material", "pla"), 0.35)
        est.append(_volume(p) * density + _servo_mass(p.get("joint")))
    est[0] += electronics_g                         # controller board + wiring in the root part
    if total in (None, "unknown", ""):
        for p, m in zip(parts, est):
            p["mass"] = round(max(m, 1.0), 1)
        spec.setdefault("worlds", {})["mass_scale"] = list(ESTIMATE_MASS_RANGE)
        notes.append(f"masses are estimates (total about {round(sum(est))} g from part volumes, servo masses and "
                     f"{electronics_g:g} g of electronics); the bench randomizes mass +/-30% to cover that")
        return
    total = float(total)
    scale = total / sum(est)
    for p, m in zip(parts, est):
        p["mass"] = round(max(m * scale, 1.0), 1)
    notes.append(f"total mass {total:g} g, shared between parts by size (servo masses included)")


def _set_servo(spec: dict, model: str) -> None:
    for p in spec["parts"]:
        j = p.get("joint")
        if not j:
            continue
        if isinstance(j["servo"], dict):
            j["servo"]["model"] = model
        else:
            j["servo"] = model


def _scale(spec: dict, s: float) -> None:
    """Uniform geometric scale of every length in the spec (cm)."""
    for p in spec["parts"]:
        p["size"] = [round(v * s, 3) for v in p["size"]]
        for key in ("pos", "com"):
            if p.get(key):
                p[key] = [round(v * s, 3) for v in p[key]]
        j = p.get("joint")
        if j:
            for key in ("anchor", "offset"):
                if j.get(key):
                    j[key] = [round(v * s, 3) for v in j[key]]
    if spec.get("tether") and spec["tether"].get("at"):
        spec["tether"]["at"] = [round(v * s, 3) for v in spec["tether"]["at"]]
    bench = spec.get("bench") or {}
    if "flat_min_cm" in bench:
        bench["flat_min_cm"] = round(bench["flat_min_cm"] * s, 2)


def _from_example(example: str) -> dict:
    raw = yaml.safe_load((EXAMPLES / f"{example}.yaml").read_text(encoding="utf-8"))
    for key in ("photo", "look", "limitations", "tether", "controller", "role", "title", "description"):
        raw.pop(key, None)
    for p in raw["parts"]:
        j = p.get("joint")
        if j:
            j.pop("hardware", None)                 # channels default to joint order
    return copy.deepcopy(raw)


def _finish(spec: dict, params: dict, family: str, title: str, notes: list[str]) -> dict:
    spec["talaria"] = 1
    spec["name"] = params["name"]
    # The user's own name reads better than the template's ("my_caduceus" -> "My Caduceus").
    spec["title"] = params.get("title") or params["name"].replace("_", " ").replace("-", " ").title()
    spec["family"] = family
    spec["description"] = params.get("description") or (
        f"Made from the {params['_template']} template. " + " ".join(n[0].upper() + n[1:] + "." for n in notes))
    if params.get("voltage"):
        spec["voltage"] = float(params["voltage"])
    return spec


# ─── templates ───────────────────────────────────────────────────────────────────────────────────


def block_robot(params: dict) -> tuple[dict, list[str]]:
    """A box body with long side limbs (arms) and short middle limbs (legs) on pitch hinges, all standing on
    the floor, like Caduceus. Sizes in cm: body_width (side to side), body_height, body_depth, arm_length,
    leg_length, limb_width, limb_depth; arms 0-2, legs 0-2."""
    p: list[str] = []
    W = _num(params, "body_width", 16.5, 4, 80, p)
    H = _num(params, "body_height", 9, 2, 60, p)
    D = _num(params, "body_depth", 6, 2, 60, p)
    La = _num(params, "arm_length", 23.5, 3, 80, p)
    Ll = _num(params, "leg_length", 16, 3, 80, p)
    lw = _num(params, "limb_width", 5.5, 1, 20, p)
    ld = _num(params, "limb_depth", min(D, 5.2), 1, 20, p)
    arms = int(_num(params, "arms", 2, 0, 2, p))
    legs = int(_num(params, "legs", 2, 0, 2, p))
    servo = _choice(params, "servo", "MG90S", servos.names(), p)
    material = _choice(params, "material", "foam", list(DENSITY), p)
    if arms + legs == 0:
        p.append("give at least one limb (arms or legs)")
    if legs and Ll > La:
        p.append("leg_length must not exceed arm_length (the arms are the long outer limbs)")
    if p:
        raise TemplateError(p)
    notes: list[str] = []
    pivot = round(H * 0.11, 2)                      # arm pivot a little above the body centre
    above = min(2.75, La * 0.12)                    # arm length above its pivot
    arm_bottom = pivot - (La - above)
    parts: list[dict] = [{"name": "body", "shape": "box", "size": [D, W, H], "material": material,
                          "com": [0, 0, round(H * 0.25, 2)]}]
    sides = [("left", 1), ("right", -1)]
    for side, sgn in sides[:arms]:
        parts.append({"name": f"{side}_arm", "parent": "body", "shape": "box", "size": [ld, lw, La],
                      "material": material, "ground_contact": True,
                      "joint": {"axis": "pitch", "anchor": [0, sgn * round(W / 2 + lw / 2 + 0.2, 2), pivot],
                                "offset": [0, 0, round(-(La / 2 - above), 2)], "range": [-72, 72],
                                "servo": {"model": servo, "backlash_deg": 2.0}}})
    for side, sgn in sides[:legs]:
        anchor_z = round((arm_bottom - 0.2 + Ll) if arms else (-H / 2 + 0.5), 2)
        if anchor_z > H / 2 - 0.5:
            raise TemplateError(["leg_length is too long for the arms: the leg tops would be above the body"])
        parts.append({"name": f"{side}_leg", "parent": "body", "shape": "box", "size": [ld, lw, Ll],
                      "material": material, "ground_contact": True,
                      "joint": {"axis": "pitch", "anchor": [0, sgn * round(min(W / 2 - lw / 2, lw * 0.68), 2), anchor_z],
                                "offset": [0, 0, round(-Ll / 2, 2)], "range": [-45, 45],
                                "servo": {"model": servo, "backlash_deg": 4.0}}})
    # Order like Caduceus (left arm, left leg, right leg, right arm) so channels 0-3 match its wiring.
    order = {"body": 0, "left_arm": 1, "left_leg": 2, "right_leg": 3, "right_arm": 4}
    parts.sort(key=lambda x: order[x["name"]])
    spec = {"parts": parts, "moves": {}}
    _assign_masses(spec, params.get("mass_g"), notes)
    arm_names = [x["name"] for x in parts if x["name"].endswith("_arm")]
    if arm_names:
        a = arm_names[-1]
        spec["moves"]["wave"] = {"description": f"Raise {a} forward, hold, lower it slowly.", "easing": "linear",
                                 "frames": [{"ms": 1980, "hold": 3000, "joints": {a: 72}}, {"ms": 2895, "joints": {a: 0}}]}
        spec["moves"]["arms_up_alternating"] = {
            "description": "One arm up and down, then the other (the other arm always supports).",
            "frames": [f for arm in reversed(arm_names) for f in ({"ms": 250, "hold": 500, "joints": {arm: 72}},
                                                                  {"ms": 250, "hold": 200, "joints": {arm: 0}})]}
    if material == "foam":
        notes.append("foam limbs are modelled as rigid boxes; soft foam feet are outside the model's scope")
        spec["limitations"] = [{"scope": "locomotion", "note": "This rigid-body model does not simulate soft foam "
                                                               "feet; the bench does not guess here."}]
    return _finish(spec, params, "biped" if legs else "other", params.get("title") or "Block robot", notes), notes


def arm(params: dict) -> tuple[dict, list[str]]:
    """A desk arm on a fixed base: turret (yaw), ``joints`` - 2 pitch links (shoulder, elbow, wrist...),
    a wrist rotation and a gripper finger. Lengths in cm: base_radius, upper_arm, forearm, link_width."""
    p: list[str] = []
    n = int(_num(params, "joints", 6, 4, 7, p))
    R = _num(params, "base_radius", 6, 2, 30, p)
    Lu = _num(params, "upper_arm", 12, 3, 60, p)
    Lf = _num(params, "forearm", 10, 3, 60, p)
    w = _num(params, "link_width", 3.5, 1, 12, p)
    servo = _choice(params, "servo", "MG996R", servos.names(), p)
    small = _choice(params, "wrist_servo", "SG90", servos.names(), p)
    material = _choice(params, "material", "pla", list(DENSITY), p)
    if p:
        raise TemplateError(p)
    notes: list[str] = []
    parts = [{"name": "base", "shape": "cylinder", "size": [R, 4], "material": material, "color": "#2f3b4c"},
             {"name": "turret", "parent": "base", "shape": "cylinder", "size": [round(R * 0.66, 2), 3],
              "material": material,
              "joint": {"axis": "yaw", "anchor": [0, 0, 2], "offset": [0, 0, 1.5], "range": [-90, 90], "servo": servo}},
             {"name": "upper_arm", "parent": "turret", "shape": "box", "size": [w * 0.85, w, Lu], "material": material,
              "joint": {"axis": "pitch", "anchor": [0, 0, 2.5], "offset": [0, 0, Lu / 2], "range": [-100, 100],
                        "servo": servo}},
             {"name": "forearm", "parent": "upper_arm", "shape": "box", "size": [w * 0.7, w * 0.85, Lf],
              "material": material,
              "joint": {"axis": "pitch", "anchor": [0, 0, Lu / 2], "offset": [0, 0, Lf / 2], "range": [-130, 130],
                        "servo": servo}}]
    parent, top = "forearm", Lf / 2
    # joints: turret, upper_arm, forearm (+ wrist pitch for 6, + a second wrist for 7) (+ hand yaw from 5) + finger
    for name in ["wrist", "wrist2"][: max(0, n - 5)]:
            parts.append({"name": name, "parent": parent, "shape": "box", "size": [2, 3, 4], "material": material,
                          "color": "#3d7bd9",
                          "joint": {"axis": "pitch", "anchor": [0, 0, top], "offset": [0, 0, 2], "range": [-100, 100],
                                    "servo": small}})
            parent, top = name, 2
    parts.append({"name": "hand", "parent": parent, "shape": "box", "size": [2, 4, 2], "material": material,
                  "color": "#3d7bd9",
                  "joint": {"axis": "yaw", "anchor": [0, 0, top], "offset": [0, 0, 1], "range": [-90, 90], "servo": small}})
    parts.append({"name": "finger", "parent": "hand", "shape": "box", "size": [1, 0.6, 4], "material": material,
                  "color": "#2f3b4c",
                  "joint": {"axis": "roll", "anchor": [0, 1.2, 1], "offset": [0, 0, 2], "range": [0, 60], "servo": small}})
    if n == 4:                                     # 4 joints: no hand rotation
        parts = [x for x in parts if x["name"] != "hand"]
        parts[-1]["parent"] = parent
        parts[-1]["joint"]["anchor"] = [0, 1.2, top]
    spec = {"parts": parts, "base": "fixed", "payload_part": parts[-2]["name"] if n > 4 else parts[-1]["name"]}
    _assign_masses(spec, params.get("mass_g"), notes, electronics_g=60)
    if params.get("mass_g") in (None, "unknown", ""):
        spec["parts"][0]["mass"] = round(spec["parts"][0]["mass"] + 300, 1)   # a base needs ballast to sit still
        notes.append("the base gets 300 g of assumed ballast so it does not tip; set mass_g if you know it")
    spec["moves"] = {
        "home": {"description": "Upright, gripper closed.", "frames": [{"ms": 800, "joints": {"upper_arm": 0, "forearm": 0}}]},
        "wave": {"description": "Lean forward and swing the forearm.",
                 "frames": [{"ms": 900, "joints": {"upper_arm": 30, "forearm": 60}},
                            {"ms": 600, "joints": {"forearm": 30}}, {"ms": 600, "joints": {"forearm": 60}},
                            {"ms": 900, "joints": {"upper_arm": 0, "forearm": 0}}]}}
    spec["look"] = {"showcase": {"joints": {"turret": 25, "upper_arm": 30, "forearm": 70, "finger": 45}}}
    return _finish(spec, params, "arm", f"Desk arm ({n} servos)", notes), notes


def _scaled_example(example: str, params: dict, ref_key: str, ref_value: float, family: str, title: str,
                    servo_default: str, notes: list[str], lo: float, hi: float) -> dict:
    p: list[str] = []
    size = _num(params, ref_key, ref_value, lo, hi, p)
    servo = _choice(params, "servo", servo_default, servos.names(), p)
    if p:
        raise TemplateError(p)
    spec = _from_example(example)
    s = size / ref_value
    if abs(s - 1) > 1e-6:
        _scale(spec, s)
        notes.append(f"the {example} layout scaled by {s:.2f} to {ref_key.replace('_', ' ')} {size:g} cm")
    if servo != servo_default:
        _set_servo(spec, servo)
    _assign_masses(spec, params.get("mass_g"), notes)
    return _finish(spec, params, family, title, notes)


def biped4(params: dict) -> tuple[dict, list[str]]:
    """A 4-servo desk biped (hip yaw + ankle roll per leg) like desk-biped4; body_width in cm (8 by default)."""
    notes: list[str] = []
    return _scaled_example("desk-biped4", params, "body_width", 8, "biped", "Desk biped (4 servos)", "SG90",
                           notes, 4, 30), notes


def quadruped(params: dict) -> tuple[dict, list[str]]:
    """``servos`` 8 (spider-style crawler, body_length 10 cm by default) or 12 (dog-style, 25 cm)."""
    p: list[str] = []
    n = int(_num(params, "servos", 8, 8, 12, p))
    if n not in (8, 12):
        p.append("servos must be 8 or 12")
    if p:
        raise TemplateError(p)
    notes: list[str] = []
    if n == 8:
        return _scaled_example("spider8", params, "body_length", 10, "quadruped", "Quadruped (8 servos)", "SG90",
                               notes, 5, 40), notes
    return _scaled_example("dog12", params, "body_length", 25, "quadruped", "Quadruped (12 servos)", "MG996R",
                           notes, 12, 60), notes


def hexapod(params: dict) -> tuple[dict, list[str]]:
    """Six spider-style legs on a longer body: ``servos`` 12 (hip yaw + knee) or 18 (hip yaw + femur + tibia);
    body_length in cm (16 by default). Includes a tripod gait."""
    p: list[str] = []
    n = int(_num(params, "servos", 12, 12, 18, p))
    if n not in (12, 18):
        p.append("servos must be 12 or 18")
    L = _num(params, "body_length", 16, 8, 60, p)
    servo = _choice(params, "servo", "SG90", servos.names(), p)
    material = _choice(params, "material", "pla", list(DENSITY), p)
    if p:
        raise TemplateError(p)
    notes: list[str] = []
    s = L / 16.0
    W = 10 * s
    parts: list[dict] = [{"name": "body", "shape": "box", "size": [L, W, 3 * s], "material": material,
                          "color": "#3d7bd9"}]
    legs = [("fl", L / 2 - 1, 1, -35), ("ml", 0, 1, 0), ("hl", -L / 2 + 1, 1, 35),
            ("fr", L / 2 - 1, -1, 35), ("mr", 0, -1, 0), ("hr", -L / 2 + 1, -1, -35)]
    for tag, x, sgn, home in legs:
        parts.append({"name": f"hip_{tag}", "parent": "body", "shape": "box", "size": [2.5 * s, 5 * s, 2 * s],
                      "material": material,
                      "joint": {"axis": "yaw", "anchor": [round(x, 2), round(sgn * W / 2, 2), 0],
                                "offset": [0, round(sgn * 2.5 * s, 2), 0], "range": [-80, 80], "home": home,
                                "servo": servo}})
        if n == 18:
            parts.append({"name": f"femur_{tag}", "parent": f"hip_{tag}", "shape": "box",
                          "size": [1.5 * s, 4 * s, 1.5 * s], "material": material,
                          "joint": {"axis": "roll", "anchor": [0, round(sgn * 2.5 * s, 2), 0],
                                    "offset": [0, round(sgn * 2 * s, 2), 0], "range": [-60, 60], "servo": servo}})
            parent, anchor = f"femur_{tag}", [0, round(sgn * 2 * s, 2), 0]
        else:
            parent, anchor = f"hip_{tag}", [0, round(sgn * 2.5 * s, 2), 0]
        parts.append({"name": f"knee_{tag}", "parent": parent, "shape": "box", "size": [1.5 * s, 1.5 * s, 7 * s],
                      "material": material, "ground_contact": True,
                      "joint": {"axis": "roll", "anchor": anchor, "offset": [0, 0, round(-3.5 * s, 2)],
                                "range": [-70, 70], "servo": servo}})
    spec = {"parts": parts}
    _assign_masses(spec, params.get("mass_g"), notes)
    # Tripod gait: legs fl, mr, hl lift and swing together, then fr, ml, hr.
    a, b = ["fl", "mr", "hl"], ["fr", "ml", "hr"]
    homes = {f"hip_{t}": h for t, _, _, h in legs}
    sign = {t: sg for t, _, sg, _ in legs}

    def frame(lift, swing_fwd, ms=180):
        j = {}
        for t in lift:
            j[f"knee_{t}"] = 25 * sign[t]
        for t in a + b:
            fwd = (20 if t in swing_fwd else -20) * sign[t]
            j[f"hip_{t}"] = homes[f"hip_{t}"] + fwd
        return {"ms": ms, "joints": j}

    def down(ms=120):
        return {"ms": ms, "joints": {f"knee_{t}": 0 for t in a + b}}

    spec["moves"] = {
        "stand": {"description": "All six feet down.", "frames": [{"ms": 500, "joints": {**homes, **{f"knee_{t}": 0 for t in a + b}}}]},
        "walk": {"description": "Tripod gait forward (repeats until stopped).", "repeat": True,
                 "frames": [frame(a, a), down(), frame(b, b), down()]},
    }
    spec["bench"] = {"walk_move": "walk", "flat_min_cm": round(5 * s, 2)}
    notes.append("the tripod gait is generated, not tuned; run the benchmark before trusting it")
    return _finish(spec, params, "hexapod", f"Hexapod ({n} servos)", notes), notes


def humanoid(params: dict) -> tuple[dict, list[str]]:
    """The 16-servo small humanoid layout (humanoid16) scaled to ``height`` cm (about 25 cm by default)."""
    notes: list[str] = []
    return _scaled_example("humanoid16", params, "height", 25, "humanoid", "Small humanoid (16 servos)", "MG90S",
                           notes, 12, 80), notes


TEMPLATES: dict[str, Callable[[dict], tuple[dict, list[str]]]] = {
    "block_robot": block_robot, "biped4": biped4, "quadruped": quadruped, "hexapod": hexapod, "arm": arm,
    "humanoid": humanoid,
}


# The few numbers the "New robot from template" form asks for: (key, label, default, unit or options).
FIELDS: dict[str, list[tuple[str, str, Any, Any]]] = {
    "block_robot": [("body_width", "Body width", 16.5, "cm"), ("body_height", "Body height", 9, "cm"),
                    ("arm_length", "Arm length", 23.5, "cm"), ("leg_length", "Leg length", 16, "cm")],
    "biped4": [("body_width", "Body width", 8, "cm")],
    "quadruped": [("servos", "Servos", 8, [8, 12]), ("body_length", "Body length", 10, "cm")],
    "hexapod": [("servos", "Servos", 12, [12, 18]), ("body_length", "Body length", 16, "cm")],
    "arm": [("joints", "Joints", 6, [4, 5, 6, 7]), ("upper_arm", "Upper arm", 12, "cm"), ("forearm", "Forearm", 10, "cm")],
    "humanoid": [("height", "Height", 25, "cm")],
}
SERVO_DEFAULT = {"block_robot": "MG90S", "biped4": "SG90", "quadruped": "SG90", "hexapod": "SG90", "arm": "MG996R",
                 "humanoid": "MG90S"}


def describe() -> dict[str, str]:
    """Template name -> its one-paragraph help (the docstring), for the tool schema and the UI."""
    return {name: " ".join((fn.__doc__ or "").split()) for name, fn in TEMPLATES.items()}


def build(template: str, params: dict) -> tuple[dict, list[str]]:
    """A checked spec dict from a template and parameters. Raises TemplateError/SpecError with the problems."""
    if template not in TEMPLATES:
        raise TemplateError([f"no template {template!r} (templates: {', '.join(TEMPLATES)})"])
    params = dict(params or {})
    name = str(params.get("name") or "")
    if not _NAME_RE.match(name):
        raise TemplateError(["name: lowercase letters, digits, - and _ (up to 32), e.g. my_robot"])
    params["_template"] = template
    spec, notes = TEMPLATES[template](params)
    parse_spec(copy.deepcopy(spec))                 # raises SpecError listing every problem
    return spec, notes
