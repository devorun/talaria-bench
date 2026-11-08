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
TOP_KEYS = {"talaria", "name", "title", "description", "photo", "voltage", "parts", "moves", "tether", "worlds"}
PART_KEYS = {"name", "parent", "shape", "size", "mass", "material", "color", "ground_contact", "joint", "pos"}
JOINT_KEYS = {"axis", "anchor", "offset", "range", "home", "servo", "max_speed", "hardware"}
HARDWARE_KEYS = {"channel", "center_us", "us_per_deg", "direction"}
TETHER_KEYS = {"part", "max_force_n"}
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
        return {"talaria": SPEC_VERSION, "voltage": r(self.voltage), "parts": parts,
                "tether": {k: (r(v) if isinstance(v, float) else v) for k, v in self.tether.items()} if self.tether else None,
                "worlds": {k: vec(v) for k, v in sorted(self.world_ranges.items())}}

    def hash(self) -> str:
        blob = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, "title": self.title, "parts": len(self.parts), "joints": self.joint_names,
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
    for key, value in (("title", title), ("description", description)):
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
            if raw_tether.get("part") not in seen:
                problems.append(f"tether: part {raw_tether.get('part')!r} does not exist")
            elif force is None or not 0 <= force <= 50:
                problems.append("tether: max_force_n must be a number from 0 to 50 (newtons)")
            else:
                tether = {"part": raw_tether["part"], "max_force_n": force}

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

    if problems:
        raise SpecError(problems)
    return Spec(name=name, title=title, description=description, voltage=voltage, parts=ordered, moves=moves,
                tether=tether, world_ranges=world_ranges, photo=photo, warnings=warnings)


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
                ground_contact=ground_contact, joint=joint, pos=pos)


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
