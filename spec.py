"""Robot spec: a human-writable YAML description of a rigid-part, hobby-servo robot.

Units in the file are centimetres, grams and degrees (the builder converts to SI). The frame is
x forward, y left, z up; the robot faces +x. See ``docs/robot-spec.md`` for the full format.

``load_spec(path)`` / ``parse_spec(data)`` return a validated :class:`Spec` or raise :class:`SpecError`
listing every problem found, one human-readable line each.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from . import materials, servos, worlds
from .motion import MoveError, check_move

SPEC_VERSION = 1
SHAPES = {"box": 3, "cylinder": 2, "sphere": 1}
SHAPE_HELP = {"box": "[x depth, y width, z height]", "cylinder": "[radius, length]", "sphere": "[radius]"}
NAMED_AXES = {"pitch": (0.0, -1.0, 0.0), "roll": (1.0, 0.0, 0.0), "yaw": (0.0, 0.0, 1.0)}
TOP_KEYS = {"talaria", "name", "title", "description", "photo", "voltage", "parts", "moves", "tether", "worlds",
            "materials", "limitations", "bench", "family", "role", "base", "payload_part", "controller", "look"}
#: appearance only (3D viewer and gallery renders); never part of the physics hash
LOOK_KEYS = {"material", "accent", "badge", "decals", "showcase"}
LOOK_MATERIALS = ("plastic", "aluminum")
#: firmware settings for the real robot's controller board (ESP32 + PCA9685)
CONTROLLER_DEFAULTS = {"sda": 21, "scl": 22, "pca9685_addr": 0x40, "servo_freq_hz": 50, "servo_min_us": 500,
                       "servo_max_us": 2500, "hostname": "", "oled": 0, "oled_addr": 0x3C}
BENCH_KEYS = {"walk_move", "flat_min_cm", "seconds", "payload_move", "payload_steps_g"}
BASES = ("free", "fixed")
#: what a limitation can cover: scenes that need walking, standing/arm-gesture moves, payload/arm work, or everything
LIMITATION_SCOPES = ("locomotion", "standing", "manipulation", "all")
MATERIAL_KEYS = {"friction", "solref", "solimp"}
PART_KEYS = {"name", "parent", "shape", "size", "mass", "material", "color", "ground_contact", "joint", "pos",
             "friction", "com"}
JOINT_KEYS = {"axis", "anchor", "offset", "range", "home", "servo", "max_speed", "hardware"}
HARDWARE_KEYS = {"channel", "center_us", "us_per_deg", "direction"}
TETHER_KEYS = {"part", "max_force_n", "at"}
MAX_SIZE_CM = 300.0
MAX_MASS_G = 50_000.0
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class SpecError(ValueError):
    """A spec that cannot be used. ``problems`` lists every reason, one per line."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("invalid robot spec:\n  - " + "\n  - ".join(self.problems))


@dataclass
class Joint:
    axis: tuple[float, float, float]        # unit vector in the parent's frame
    axis_name: Optional[str]                # pitch | roll | yaw, or None for a custom vector
    anchor: tuple[float, float, float]      # cm, in the parent's frame (parent center = origin)
    offset: tuple[float, float, float]      # cm, this part's center relative to the joint at angle 0
    range: tuple[float, float]              # degrees
    home: float                             # degrees
    servo: servos.ServoModel
    max_speed: float                        # deg/s used for move planning
    hardware: dict[str, Any] = field(default_factory=dict)


@dataclass
class Part:
    name: str
    parent: Optional[str]
    shape: str
    size: tuple[float, ...]                 # cm
    mass: float                             # g
    material: str
    color: str
    ground_contact: bool
    joint: Optional[Joint] = None
    pos: Optional[tuple[float, float, float]] = None   # cm, fixed parts only
    friction: Optional[float] = None        # this part's friction factor, replacing the material's
    com: Optional[tuple[float, float, float]] = None   # cm, centre of mass relative to the shape's center

    @property
    def is_root(self) -> bool:
        return self.parent is None


@dataclass
class Spec:
    name: str
    title: str
    description: str
    voltage: float
    parts: list[Part]                       # tree order: root first, parents before children
    moves: dict[str, dict[str, Any]]
    tether: Optional[dict[str, Any]]
    world_ranges: dict[str, tuple[float, float]]
    photo: Optional[Path] = None
    source: Optional[Path] = None
    warnings: list[str] = field(default_factory=list)
    materials: dict[str, materials.Material] = field(default_factory=lambda: dict(materials.MATERIALS))
    #: known model limitations, ``[{"scope": ..., "note": ...}]``; results in that scope are "out of model scope"
    limitations: list[dict[str, str]] = field(default_factory=list)
    #: benchmark settings: which move is the walk, the flat-floor pass threshold, run time
    bench: dict[str, Any] = field(default_factory=dict)
    family: str = ""                        # e.g. "quadruped", "humanoid", "arm" (gallery metadata)
    role: str = ""                          # one line: why this robot is in the gallery
    base: str = "free"                      # free: the root floats (walkers); fixed: bolted to the table (arms)
    payload_part: Optional[str] = None      # where the payload scene hangs its weight (e.g. the gripper)
    controller: dict[str, Any] = field(default_factory=dict)   # ESP32/PCA9685 settings for the firmware
    look: dict[str, Any] = field(default_factory=dict)         # appearance only (viewer, gallery renders)

    def hardware_mapping(self) -> dict[str, Any]:
        """Everything the firmware is configured with: controller settings and each joint's channel,
        pulse center, pulse per degree, direction, range and speed limit (part of approval keys)."""
        joints = []
        for k, p in enumerate(self.joint_parts):
            hw = p.joint.hardware
            joints.append({"name": p.name, "channel": int(hw.get("channel", k)),
                           "center_us": float(hw.get("center_us", 1500)), "us_per_deg": float(hw.get("us_per_deg", 11.1)),
                           "direction": int(hw.get("direction", 1)), "min": p.joint.range[0], "max": p.joint.range[1],
                           "home": p.joint.home, "max_speed": round(p.joint.max_speed, 3)})
        return {"controller": {**CONTROLLER_DEFAULTS, **self.controller}, "joints": joints}

    def limitations_for(self, scope: str) -> list[str]:
        """Notes of the limitations that cover ``scope`` (including ``all``)."""
        return [lim["note"] for lim in self.limitations if lim["scope"] in (scope, "all")]

    @property
    def root(self) -> Part:
        return self.parts[0]

    def part(self, name: str) -> Part:
        for p in self.parts:
            if p.name == name:
                return p
        raise KeyError(name)

    def children(self, name: str) -> list[Part]:
        return [p for p in self.parts if p.parent == name]

    @property
    def joint_parts(self) -> list[Part]:
        return [p for p in self.parts if p.joint is not None]

    @property
    def joint_names(self) -> list[str]:
        return [p.name for p in self.joint_parts]

    def joint_limits(self) -> dict[str, dict[str, Any]]:
        """``{name: {min, max, home, max_speed}}`` for motion planning."""
        return {p.name: {"min": p.joint.range[0], "max": p.joint.range[1], "home": p.joint.home,
                         "max_speed": p.joint.max_speed} for p in self.joint_parts}

    @property
    def total_mass_g(self) -> float:
        return sum(p.mass for p in self.parts)

    def canonical(self) -> dict[str, Any]:
        """The physics-relevant content, normalized: what :meth:`hash` covers. Cosmetic fields
        (title, description, photo, colors) and moves are left out, so renaming the robot or adding a
        move does not change it; any change to geometry, masses, joints, servos, tether or world
        ranges does. Part order in the file does not matter."""
        def r(v: float) -> float:
            return round(float(v), 6)

        def vec(v) -> list[float]:
            return [r(x) for x in v]

        parts = []
        for p in sorted(self.parts, key=lambda q: q.name):
            entry: dict[str, Any] = {"name": p.name, "parent": p.parent, "shape": p.shape, "size": vec(p.size),
                                     "mass": r(p.mass), "material": p.material, "ground_contact": p.ground_contact}
            if p.pos is not None:
                entry["pos"] = vec(p.pos)
            if p.com is not None:
                entry["com"] = vec(p.com)
            if p.friction is not None:
                entry["friction"] = r(p.friction)
            if p.joint is not None:
                j = p.joint
                entry["joint"] = {
                    "axis": vec(j.axis), "anchor": vec(j.anchor), "offset": vec(j.offset), "range": vec(j.range),
                    "home": r(j.home), "max_speed": r(j.max_speed),
                    "servo": {"torque_kgcm": r(j.servo.torque_kgcm(self.voltage)),
                              "speed_s_per_60": r(j.servo.s_per_60(self.voltage)),
                              "backlash_deg": r(j.servo.backlash_deg)},
                }
            parts.append(entry)
        used = sorted({p.material for p in self.parts})
        mats = {name: {"friction": r(self.materials[name].friction), "solref": vec(self.materials[name].solref),
                       "solimp": vec(self.materials[name].solimp)} for name in used}
        return {"talaria": SPEC_VERSION, "voltage": r(self.voltage), "parts": parts, "materials": mats,
                **({"base": self.base} if self.base != "free" else {}),
                "tether": {"part": self.tether["part"], "max_force_n": r(self.tether["max_force_n"]),
                           "at": vec(self.tether["at"])} if self.tether else None,
                "worlds": {k: vec(v) for k, v in sorted(self.world_ranges.items())}}

    def hash(self) -> str:
        blob = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, "title": self.title, "family": self.family, "role": self.role,
                "base": self.base, "parts": len(self.parts), "joints": self.joint_names,
                "total_mass_g": round(self.total_mass_g, 1), "moves": sorted(self.moves),
                "hash": self.hash()[:16], "warnings": list(self.warnings)}


# ─── Parsing ─────────────────────────────────────────────────────────────────────────────────────


def load_spec(path: str | Path) -> Spec:
    import yaml

    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError([f"cannot read {path}: {exc.strerror or exc}"]) from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        raise SpecError([f"{path.name} is not valid YAML{where}: {getattr(exc, 'problem', None) or exc}"]) from None
    spec = parse_spec(data, base_dir=path.parent)
    spec.source = path
    return spec


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _vec(value: Any, n: int) -> Optional[tuple[float, ...]]:
    if not isinstance(value, (list, tuple)) or len(value) != n:
        return None
    out = tuple(_num(v) for v in value)
    return None if any(v is None for v in out) else out  # type: ignore[return-value]


def _unknown(where: str, data: Mapping, allowed: set[str], problems: list[str]) -> None:
    extra = set(map(str, data)) - allowed
    if extra:
        problems.append(f"{where}: unknown field(s) {', '.join(sorted(extra))} (allowed: {', '.join(sorted(allowed))})")


def parse_spec(data: Any, base_dir: Optional[Path] = None) -> Spec:
    problems: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, Mapping):
        raise SpecError(["the spec must be a YAML mapping (talaria: 1, name: ..., parts: [...])"])
    _unknown("spec", data, TOP_KEYS, problems)

    version = data.get("talaria")
    if version != SPEC_VERSION:
        problems.append(f"talaria: must be {SPEC_VERSION} (the spec format version), got {version!r}")
    name = data.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        problems.append("name: lowercase letters, digits, - and _, up to 32 characters (e.g. my-robot)")
        name = "robot"
    title = data.get("title", name)
    description = data.get("description", "")
    family = data.get("family", "")
    role = data.get("role", "")
    for key, value in (("title", title), ("description", description), ("family", family), ("role", role)):
        if not isinstance(value, str):
            problems.append(f"{key}: must be text")
    voltage = _num(data.get("voltage", servos.DEFAULT_VOLTAGE))
    if voltage is None or not 3.0 <= voltage <= 9.0:
        problems.append("voltage: servo supply voltage must be a number from 3 to 9")
        voltage = servos.DEFAULT_VOLTAGE

    photo = None
    if data.get("photo") is not None:
        if not isinstance(data["photo"], str):
            problems.append("photo: must be a file name relative to the spec file")
        else:
            photo = (base_dir / data["photo"]) if base_dir else Path(data["photo"])
            if base_dir and not photo.is_file():
                warnings.append(f"photo {data['photo']!r} not found next to the spec")

    raw_parts = data.get("parts")
    parts: list[Part] = []
    if not isinstance(raw_parts, list) or not raw_parts:
        problems.append("parts: must be a non-empty list of parts")
        raw_parts = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_parts, start=1):
        part = _parse_part(raw, index, voltage, problems)
        if part is None:
            continue
        if part.name in seen:
            problems.append(f"part {part.name!r}: duplicate name (every part needs its own name)")
            continue
        seen.add(part.name)
        parts.append(part)

    ordered = _tree_order(parts, problems)

    joint_limits = {p.name: {"min": p.joint.range[0], "max": p.joint.range[1], "home": p.joint.home,
                             "max_speed": p.joint.max_speed} for p in ordered if p.joint is not None}
    moves: dict[str, dict[str, Any]] = {}
    raw_moves = data.get("moves") or {}
    if not isinstance(raw_moves, Mapping):
        problems.append("moves: must be a mapping of move name -> {frames, loops, ...}")
        raw_moves = {}
    for move_name, move in raw_moves.items():
        if not isinstance(move_name, str) or not _NAME_RE.match(move_name):
            problems.append(f"move {move_name!r}: names use lowercase letters, digits, - and _")
            continue
        if not joint_limits:
            problems.append(f"move {move_name!r}: the robot has no joints to move")
            continue
        try:
            check_move(move, joint_limits)
        except MoveError as exc:
            problems.extend(f"move {move_name!r}: {p}" for p in exc.problems)
            continue
        moves[move_name] = dict(move)

    tether = None
    raw_tether = data.get("tether")
    if raw_tether is not None:
        if not isinstance(raw_tether, Mapping):
            problems.append("tether: must be {part: <name>, max_force_n: <newtons>}")
        else:
            _unknown("tether", raw_tether, TETHER_KEYS, problems)
            force = _num(raw_tether.get("max_force_n"))
            at = _vec(raw_tether.get("at", [0, 0, 0]), 3)
            if raw_tether.get("part") not in seen:
                problems.append(f"tether: part {raw_tether.get('part')!r} does not exist")
            elif force is None or not 0 <= force <= 50:
                problems.append("tether: max_force_n must be a number from 0 to 50 (newtons)")
            elif at is None:
                problems.append("tether: at must be [x, y, z] in cm (where the cable plugs in, part frame)")
            else:
                tether = {"part": raw_tether["part"], "max_force_n": force, "at": list(at)}

    world_ranges: dict[str, tuple[float, float]] = {}
    raw_worlds = data.get("worlds") or {}
    if not isinstance(raw_worlds, Mapping):
        problems.append("worlds: must be a mapping of range name -> [low, high]")
        raw_worlds = {}
    for key, value in raw_worlds.items():
        if key not in worlds.DEFAULT_RANGES:
            problems.append(f"worlds: unknown range {key!r} (known: {', '.join(worlds.DEFAULT_RANGES)})")
            continue
        pair = _vec(value, 2)
        if pair is None or pair[0] > pair[1]:
            problems.append(f"worlds: {key} must be [low, high] with low <= high")
            continue
        world_ranges[str(key)] = (pair[0], pair[1])

    table = _parse_materials(data.get("materials"), problems)
    limitations = _parse_limitations(data.get("limitations"), problems)
    bench = _parse_bench(data.get("bench"), moves, problems)

    base = data.get("base", "free")
    if base not in BASES:
        problems.append(f"base: must be one of {', '.join(BASES)} (got {base!r})")
        base = "free"
    controller: dict[str, Any] = {}
    raw_ctl = data.get("controller")
    if raw_ctl is not None:
        if not isinstance(raw_ctl, Mapping):
            problems.append("controller: must be a mapping (sda, scl, pca9685_addr, servo_freq_hz, ...)")
        else:
            _unknown("controller", raw_ctl, set(CONTROLLER_DEFAULTS), problems)
            for key, value in raw_ctl.items():
                if key == "hostname":
                    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9-]{0,32}", value):
                        problems.append("controller: hostname must be lowercase letters, digits and -")
                        continue
                elif key in CONTROLLER_DEFAULTS and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                    problems.append(f"controller: {key} must be a whole number")
                    continue
                controller[str(key)] = value
    look = _parse_look(data.get("look"), seen, problems)
    payload_part = data.get("payload_part")
    if payload_part is not None and payload_part not in seen:
        problems.append(f"payload_part: part {payload_part!r} does not exist")
        payload_part = None
    if bench.get("payload_move") and payload_part is None:
        problems.append("bench: payload_move needs a payload_part")

    if problems:
        raise SpecError(problems)
    return Spec(name=name, title=title, description=description, voltage=voltage, parts=ordered, moves=moves,
                tether=tether, world_ranges=world_ranges, photo=photo, warnings=warnings, materials=table,
                limitations=limitations, bench=bench, family=family, role=role, base=base,
                payload_part=payload_part, controller=controller, look=look)


def _parse_look(raw: Any, parts: set[str], problems: list[str]) -> dict[str, Any]:
    """Appearance hints: material (plastic | aluminum), accent colour, a short badge, decals on parts
    (``{part, kind: oled}``) and a showcase pose (``joints: {name: degrees}``) for gallery renders."""
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        problems.append("look: must be a mapping (material, accent, badge, decals, showcase)")
        return {}
    _unknown("look", raw, LOOK_KEYS, problems)
    out: dict[str, Any] = {}
    if "material" in raw:
        if raw["material"] not in LOOK_MATERIALS:
            problems.append(f"look: material must be one of {', '.join(LOOK_MATERIALS)}")
        else:
            out["material"] = raw["material"]
    if "accent" in raw:
        if not isinstance(raw["accent"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", raw["accent"]):
            problems.append("look: accent must be a colour like #ff7a1a")
        else:
            out["accent"] = raw["accent"]
    if "badge" in raw:
        if not isinstance(raw["badge"], str) or not 0 < len(raw["badge"]) <= 8:
            problems.append("look: badge must be text of at most 8 characters")
        else:
            out["badge"] = raw["badge"]
    decals = []
    for i, d in enumerate(raw.get("decals") or []):
        if not isinstance(d, Mapping) or d.get("part") not in parts or d.get("kind") not in ("oled",):
            problems.append(f"look: decal {i + 1} needs part (an existing part) and kind: oled")
            continue
        decals.append({"part": d["part"], "kind": d["kind"]})
    if decals:
        out["decals"] = decals
    show = raw.get("showcase")
    if show is not None:
        joints = show.get("joints") if isinstance(show, Mapping) else None
        if not isinstance(joints, Mapping) or not all(isinstance(v, (int, float)) for v in joints.values()):
            problems.append("look: showcase must be {joints: {joint name: degrees}}")
        else:
            out["showcase"] = {"joints": {str(k): float(v) for k, v in joints.items()}}
    return out


def _parse_bench(raw: Any, moves: Mapping[str, Any], problems: list[str]) -> dict[str, Any]:
    """Benchmark settings. Defaults: the walk is the move named ``walk``, flat floor passes at 5 cm of
    steady progress, gaits (repeat moves) run 8 s and other moves run their own length + 1 s."""
    out: dict[str, Any] = {"walk_move": "walk", "flat_min_cm": 5.0, "seconds": None,
                           "payload_move": None, "payload_steps_g": [0.0, 50.0, 100.0, 200.0, 300.0]}
    if raw is None:
        return out
    if not isinstance(raw, Mapping):
        problems.append("bench: must be a mapping (walk_move, flat_min_cm, seconds)")
        return out
    _unknown("bench", raw, BENCH_KEYS, problems)
    if "walk_move" in raw:
        if raw["walk_move"] is not None and raw["walk_move"] not in moves:
            problems.append(f"bench: walk_move {raw['walk_move']!r} is not one of the moves")
        else:
            out["walk_move"] = raw["walk_move"]
    if raw.get("payload_move") is not None:
        if raw["payload_move"] not in moves:
            problems.append(f"bench: payload_move {raw['payload_move']!r} is not one of the moves")
        else:
            out["payload_move"] = raw["payload_move"]
    if raw.get("payload_steps_g") is not None:
        steps = raw["payload_steps_g"]
        nums = [_num(v) for v in steps] if isinstance(steps, list) else [None]
        if not nums or any(v is None or v < 0 for v in nums) or nums != sorted(nums) or nums[0] != 0:
            problems.append("bench: payload_steps_g must be an increasing list of grams starting at 0")
        else:
            out["payload_steps_g"] = nums
    for key, lo, hi in (("flat_min_cm", 0.0, 500.0), ("seconds", 1.0, 120.0)):
        if raw.get(key) is not None:
            v = _num(raw[key])
            if v is None or not lo <= v <= hi:
                problems.append(f"bench: {key} must be a number from {lo:g} to {hi:g}")
            else:
                out[key] = v
    return out


def _parse_limitations(raw: Any, problems: list[str]) -> list[dict[str, str]]:
    """Honest notes about what the model cannot do, e.g. walking on crushable foam feet."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        problems.append("limitations: must be a list of {scope, note}")
        return []
    out = []
    for i, item in enumerate(raw, start=1):
        where = f"limitations #{i}"
        if not isinstance(item, Mapping):
            problems.append(f"{where}: must be {{scope, note}}")
            continue
        _unknown(where, item, {"scope", "note"}, problems)
        scope, note = item.get("scope"), item.get("note")
        if scope not in LIMITATION_SCOPES:
            problems.append(f"{where}: scope must be one of {', '.join(LIMITATION_SCOPES)} (got {scope!r})")
            continue
        if not isinstance(note, str) or not note.strip():
            problems.append(f"{where}: note must be a short text")
            continue
        out.append({"scope": scope, "note": " ".join(note.split())})
    return out


def _parse_materials(raw: Any, problems: list[str]) -> dict[str, materials.Material]:
    """Per-robot overrides of the material table, e.g. a softer foam found by calibration."""
    from dataclasses import replace

    table = dict(materials.MATERIALS)
    if raw is None:
        return table
    if not isinstance(raw, Mapping):
        problems.append("materials: must be a mapping of material -> {friction, solref, solimp}")
        return table
    for name, fields in raw.items():
        where = f"materials {name!r}"
        if name not in table:
            problems.append(f"{where}: unknown material (known: {', '.join(materials.names())})")
            continue
        if not isinstance(fields, Mapping):
            problems.append(f"{where}: must be a mapping with friction, solref and/or solimp")
            continue
        _unknown(where, fields, MATERIAL_KEYS, problems)
        changes: dict[str, Any] = {}
        if "friction" in fields:
            f = _num(fields["friction"])
            if f is None or not 0.05 <= f <= 3.0:
                problems.append(f"{where}: friction factor must be 0.05..3")
            else:
                changes["friction"] = f
        if "solref" in fields:
            v = _vec(fields["solref"], 2)
            if v is None or not 0.004 <= v[0] <= 0.2 or not 0.1 <= v[1] <= 5:
                problems.append(f"{where}: solref must be [time constant 0.004..0.2 s, damping ratio 0.1..5]")
            else:
                changes["solref"] = v
        if "solimp" in fields:
            v = _vec(fields["solimp"], 3)
            if v is None or not 0 < v[0] <= v[1] < 1 or not 0 < v[2] <= 0.05:
                problems.append(f"{where}: solimp must be [dmin, dmax, width m] with 0 < dmin <= dmax < 1, "
                                "0 < width <= 0.05")
            else:
                changes["solimp"] = v
        table[name] = replace(table[name], **changes)
    return table


def _parse_part(raw: Any, index: int, voltage: float, problems: list[str]) -> Optional[Part]:
    if not isinstance(raw, Mapping):
        problems.append(f"part #{index}: must be a mapping with name, shape, size, mass, ...")
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        problems.append(f"part #{index}: name must use lowercase letters, digits, - and _ (got {name!r})")
        return None
    where = f"part {name!r}"
    before = len(problems)
    _unknown(where, raw, PART_KEYS, problems)

    parent = raw.get("parent")
    if parent is not None and not isinstance(parent, str):
        problems.append(f"{where}: parent must be a part name")
        parent = None
    shape = raw.get("shape", "box")
    size: tuple[float, ...] = ()
    if shape not in SHAPES:
        problems.append(f"{where}: shape must be one of {', '.join(SHAPES)} (got {shape!r})")
    else:
        vec = _vec(raw.get("size"), SHAPES[shape])
        if vec is None:
            problems.append(f"{where}: {shape} size must be {SHAPE_HELP[shape]} in cm")
        elif any(v <= 0 for v in vec):
            problems.append(f"{where}: every size must be > 0 cm")
        elif any(v > MAX_SIZE_CM for v in vec):
            problems.append(f"{where}: size above {MAX_SIZE_CM:g} cm; sizes are in centimetres, not millimetres")
        else:
            size = vec
    mass = _num(raw.get("mass"))
    if mass is None or mass <= 0:
        problems.append(f"{where}: mass must be a number > 0 (grams)")
        mass = 1.0
    elif mass > MAX_MASS_G:
        problems.append(f"{where}: mass above {MAX_MASS_G:g} g; masses are in grams")
    material = raw.get("material", "pla")
    if material not in materials.MATERIALS:
        problems.append(f"{where}: material must be one of {', '.join(materials.names())} (got {material!r})")
        material = "pla"
    color = raw.get("color", materials.MATERIALS[material].color)
    if not isinstance(color, str) or not _COLOR_RE.match(color):
        problems.append(f"{where}: color must look like \"#a1b2c3\"")
        color = materials.MATERIALS[material].color
    ground_contact = raw.get("ground_contact", False)
    if not isinstance(ground_contact, bool):
        problems.append(f"{where}: ground_contact must be true or false")
        ground_contact = False
    friction = None
    if raw.get("friction") is not None:
        friction = _num(raw["friction"])
        if friction is None or not 0.05 <= friction <= 3.0:
            problems.append(f"{where}: friction factor must be 0.05..3 (replaces the material's factor)")
            friction = None
    com = None
    if raw.get("com") is not None:
        com = _vec(raw["com"], 3)
        if com is None or any(abs(v) > MAX_SIZE_CM for v in com):
            problems.append(f"{where}: com must be [x, y, z] in cm (centre of mass offset from the shape's center)")
            com = None
    joint = None
    pos = None
    if parent is None:
        if raw.get("joint") is not None:
            problems.append(f"{where}: the root part (no parent) cannot have a joint; it floats free")
        if raw.get("pos") is not None:
            problems.append(f"{where}: the root part (no parent) cannot have pos; it is placed on the floor")
    else:
        if raw.get("joint") is not None and raw.get("pos") is not None:
            problems.append(f"{where}: give either joint (a moving part) or pos (a fixed part), not both")
        elif raw.get("joint") is not None:
            joint = _parse_joint(raw["joint"], where, voltage, problems)
        elif raw.get("pos") is not None:
            pos = _vec(raw["pos"], 3)
            if pos is None:
                problems.append(f"{where}: pos must be [x, y, z] in cm (center in the parent's frame)")
        else:
            problems.append(f"{where}: needs a joint (moving part) or pos (part fixed to its parent)")
    if len(problems) > before:
        return None
    return Part(name=name, parent=parent, shape=shape, size=size, mass=mass, material=material, color=color,
                ground_contact=ground_contact, joint=joint, pos=pos, friction=friction, com=com)


def _parse_joint(raw: Any, where: str, voltage: float, problems: list[str]) -> Optional[Joint]:
    where = f"{where} joint"
    if not isinstance(raw, Mapping):
        problems.append(f"{where}: must be a mapping with axis, anchor, offset, range, servo")
        return None
    before = len(problems)
    _unknown(where, raw, JOINT_KEYS, problems)
    axis_raw = raw.get("axis", "pitch")
    axis_name = None
    axis = (0.0, -1.0, 0.0)
    if isinstance(axis_raw, str):
        if axis_raw not in NAMED_AXES:
            problems.append(f"{where}: axis must be pitch, roll, yaw or [x, y, z] (got {axis_raw!r})")
        else:
            axis_name, axis = axis_raw, NAMED_AXES[axis_raw]
    else:
        vec = _vec(axis_raw, 3)
        norm = math.sqrt(sum(v * v for v in vec)) if vec else 0.0
        if vec is None or norm < 1e-9:
            problems.append(f"{where}: axis vector must be three numbers, not all zero")
        else:
            axis = tuple(v / norm for v in vec)  # type: ignore[assignment]
    anchor = _vec(raw.get("anchor", [0, 0, 0]), 3)
    if anchor is None:
        problems.append(f"{where}: anchor must be [x, y, z] in cm (joint position in the parent's frame)")
    offset = _vec(raw.get("offset", [0, 0, 0]), 3)
    if offset is None:
        problems.append(f"{where}: offset must be [x, y, z] in cm (part center relative to the joint)")
    rng = _vec(raw.get("range"), 2)
    if rng is None:
        problems.append(f"{where}: range must be [min, max] in degrees")
    elif not -180 <= rng[0] < rng[1] <= 180:
        problems.append(f"{where}: range must satisfy -180 <= min < max <= 180 (got {list(rng)})")
        rng = None
    home = _num(raw.get("home", 0))
    if home is None:
        problems.append(f"{where}: home must be a number (degrees)")
    elif rng is not None and not rng[0] <= home <= rng[1]:
        problems.append(f"{where}: home {home:g} is outside the range {rng[0]:g}..{rng[1]:g}")
    servo = None
    if raw.get("servo") is None:
        problems.append(f"{where}: servo is required (catalog: {', '.join(servos.names())}, or inline values)")
    else:
        try:
            servo = servos.resolve(raw["servo"], where=f"{where} servo")
        except servos.ServoError as exc:
            problems.append(str(exc))
    max_speed = None
    if raw.get("max_speed") is not None:
        max_speed = _num(raw["max_speed"])
        if max_speed is None or max_speed <= 0:
            problems.append(f"{where}: max_speed must be a number > 0 (deg/s)")
    hardware = raw.get("hardware") or {}
    if not isinstance(hardware, Mapping):
        problems.append(f"{where}: hardware must be a mapping (channel, center_us, us_per_deg, direction)")
        hardware = {}
    else:
        _unknown(f"{where} hardware", hardware, HARDWARE_KEYS, problems)
        ch = hardware.get("channel")
        if ch is not None and (not isinstance(ch, int) or isinstance(ch, bool) or not 0 <= ch <= 15):
            problems.append(f"{where} hardware: channel must be a whole number 0..15 (PCA9685)")
        d = hardware.get("direction")
        if d is not None and d not in (1, -1):
            problems.append(f"{where} hardware: direction must be 1 or -1")
        for key in ("center_us", "us_per_deg"):
            if key in hardware and (_num(hardware[key]) is None or _num(hardware[key]) <= 0):
                problems.append(f"{where} hardware: {key} must be a number > 0")
    if len(problems) > before:
        return None
    speed = max_speed if max_speed is not None else servo.speed_dps(voltage)
    if max_speed is not None and max_speed > servo.speed_dps(voltage) + 1e-6:
        problems.append(f"{where}: max_speed {max_speed:g} deg/s is faster than the servo can turn "
                        f"({servo.speed_dps(voltage):.0f} deg/s at {voltage:g} V)")
        return None
    return Joint(axis=axis, axis_name=axis_name, anchor=anchor, offset=offset, range=rng, home=home, servo=servo,
                 max_speed=speed, hardware=dict(hardware))


def _tree_order(parts: list[Part], problems: list[str]) -> list[Part]:
    """Root first, then each parent before its children (file order among siblings)."""
    if not parts:
        return []
    names = {p.name for p in parts}
    roots = [p for p in parts if p.parent is None]
    ok = True
    for p in parts:
        if p.parent is not None and p.parent not in names:
            problems.append(f"part {p.name!r}: parent {p.parent!r} does not exist (parts: {', '.join(sorted(names))})")
            ok = False
        if p.parent == p.name:
            problems.append(f"part {p.name!r}: a part cannot be its own parent")
            ok = False
    if len(roots) != 1:
        if not roots:
            problems.append("parts: exactly one part must have no parent (the root/body); found none")
        else:
            problems.append("parts: exactly one part must have no parent (the root/body); found "
                            + ", ".join(p.name for p in roots))
        ok = False
    if not ok:
        return parts
    by_parent: dict[str, list[Part]] = {}
    for p in parts:
        if p.parent is not None:
            by_parent.setdefault(p.parent, []).append(p)
    ordered = [roots[0]]
    i = 0
    while i < len(ordered):
        ordered.extend(by_parent.get(ordered[i].name, []))
        i += 1
    if len(ordered) != len(parts):
        stuck = sorted(names - {p.name for p in ordered})
        problems.append("parts: parent links form a cycle or are cut off from the root: " + ", ".join(stuck))
        return parts
    return ordered
