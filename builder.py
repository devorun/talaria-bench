"""Robot spec -> MuJoCo model.

``build_mjcf(spec)`` returns the MJCF text (SI units) plus build info; ``make_model(spec, world)``
returns a compiled model with one world's physics applied (friction, masses, servo strength, gravity
for a tilted floor). Compiled base models are cached per spec hash.

Modelling choices (numbers in ``materials.py`` and ``servos.py``):

* Every joint is a hobby servo: a position actuator on a hinge, force limited to the stall torque
  (an estimate, see servos.py), stiff enough that a few degrees of error saturate it, with damping.
* Each servo hinge is followed by a passive "play" hinge on the same axis, free within
  +-backlash/2 with light damping: the slop of the servo's gears.
* Contacts take their softness and friction from the part's material; the floor contributes only the
  world friction. Parts collide with the floor and with each other (except parent/child pairs and
  pairs that already overlap in the rest pose, which are excluded with a warning).
* The root is placed so the lowest ground-contact geometry rests on the floor in the home pose.
* ``<compiler angle="degree">``: joint ranges are degrees, but actuator ctrl acts on qpos in radians.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Optional


from .spec import Part, Spec
from .worlds import World

TIMESTEP = 0.002
SATURATE_DEG = 3.0            # this much position error alone saturates the servo
KV_PER_KP = 0.02              # actuator damping, seconds
JOINT_DAMPING = 0.002         # N*m*s/rad, bearing/gear friction of the servo joint
PLAY_DAMPING = 0.0005         # N*m*s/rad, the gear slop moves almost freely
PLAY_ARMATURE = 1e-6
FLOOR_SIZE = 5.0              # half-size of the floor plane, m
DROP_CLEARANCE = 0.0005       # m between the lowest foot and the floor before the settle phase
CM = 0.01
G = 0.001
PLAY_SUFFIX = "__play"


@dataclass
class BuildInfo:
    root_z: float
    joint_names: list[str]
    excluded_pairs: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    front_x: float = 0.0        # m, front-most point of the robot in the home pose (root at x = 0)
    back_x: float = 0.0


def _rgba(color: str) -> str:
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    r, g, b = (int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return f"{r:.3f} {g:.3f} {b:.3f} 1"


def _f(v: float) -> str:
    return f"{v:.9g}"


def _v(vec) -> str:
    return " ".join(_f(x) for x in vec)


def _center_in_body(part: Part) -> tuple[float, float, float]:
    """Where the part's geometry center sits in its own body frame (m)."""
    if part.joint is not None:
        return tuple(x * CM for x in part.joint.offset)  # type: ignore[return-value]
    return (0.0, 0.0, 0.0)


def _geom_size(part: Part) -> str:
    s = [x * CM for x in part.size]
    if part.shape == "box":
        return _v([x / 2 for x in s])
    if part.shape == "cylinder":
        return _v([s[0], s[1] / 2])
    return _v([s[0]])


def _box_like_inertia(part: Part) -> list[float]:
    """Principal inertia of the part's shape about its own center (kg*m^2)."""
    m = part.mass * G
    s = [x * CM for x in part.size]
    if part.shape == "box":
        x, y, z = s
        return [m * (y * y + z * z) / 12, m * (x * x + z * z) / 12, m * (x * x + y * y) / 12]
    if part.shape == "cylinder":
        r, h = s
        side = m * (3 * r * r + h * h) / 12
        return [side, side, m * r * r / 2]
    r = s[0]
    return [2 * m * r * r / 5] * 3


def _servo_gains(part: Part, voltage: float) -> tuple[float, float, float]:
    torque = part.joint.servo.torque_nm(voltage)
    kp = torque / math.radians(SATURATE_DEG)
    return kp, kp * KV_PER_KP, torque


def _body_xml(spec: Spec, part: Part, indent: str, root_z: float) -> str:
    mat = spec.materials[part.material]
    lines = []
    if part.parent is None:
        lines.append(f'{indent}<body name="{part.name}" pos="0 0 {_f(root_z)}">')
        lines.append(f'{indent}  <freejoint name="root"/>')
    else:
        parent = spec.part(part.parent)
        base = _center_in_body(parent)
        rel = part.joint.anchor if part.joint is not None else part.pos
        pos = [b + r * CM for b, r in zip(base, rel)]
        lines.append(f'{indent}<body name="{part.name}" pos="{_v(pos)}">')
        if part.joint is not None:
            j = part.joint
            back = j.servo.backlash_deg / 2.0
            lines.append(f'{indent}  <joint name="{part.name}" type="hinge" axis="{_v(j.axis)}" '
                         f'range="{_f(j.range[0])} {_f(j.range[1])}" limited="true" damping="{_f(JOINT_DAMPING)}" '
                         f'armature="{_f(j.servo.armature)}"/>')
            if back > 0:
                lines.append(f'{indent}  <joint name="{part.name}{PLAY_SUFFIX}" type="hinge" axis="{_v(j.axis)}" '
                             f'range="{_f(-back)} {_f(back)}" limited="true" damping="{_f(PLAY_DAMPING)}" '
                             f'armature="{_f(PLAY_ARMATURE)}"/>')
    lines.append(
        f'{indent}  <geom name="{part.name}" type="{part.shape}" size="{_geom_size(part)}" '
        f'pos="{_v(_center_in_body(part))}" mass="{_f(part.mass * G)}" rgba="{_rgba(part.color)}" '
        f'friction="{_f(0.5 * mat.friction)} {_f(mat.torsional)} {_f(mat.rolling)}" '
        f'solref="{_v(mat.solref)}" solimp="{_v(mat.solimp)}" solmix="1" contype="2" conaffinity="3"/>')
    if part.com is not None:
        # Explicit inertial: the part's mass sits at center + com (e.g. electronics stacked on top).
        # The shape's own inertia is kept as an approximation.
        center = _center_in_body(part)
        pos = [c + o * CM for c, o in zip(center, part.com)]
        lines.append(f'{indent}  <inertial pos="{_v(pos)}" mass="{_f(part.mass * G)}" '
                     f'diaginertia="{_v(_box_like_inertia(part))}"/>')
    for child in spec.children(part.name):
        lines.append(_body_xml(spec, child, indent + "  ", root_z))
    lines.append(f"{indent}</body>")
    return "\n".join(lines)


def terrain_xml(terrain: tuple = ()) -> str:
    """Extra static geometry for scenes: ``("box", name, x, y, z, half_x, half_y, half_z)`` in metres.
    Like the floor, terrain contributes no friction of its own (the part's material decides)."""
    out = []
    for item in terrain:
        kind, name, x, y, z, hx, hy, hz = item
        if kind != "box":
            raise ValueError(f"unknown terrain kind {kind!r}")
        out.append(f'    <geom name="{name}" type="box" pos="{_v((x, y, z))}" size="{_v((hx, hy, hz))}" '
                   f'rgba="0.55 0.42 0.28 1" friction="0 0 0" solmix="0" contype="1" conaffinity="2"/>')
    return "\n".join(out)


def _mjcf(spec: Spec, root_z: float, excluded: list[tuple[str, str]], terrain: tuple = ()) -> str:
    actuators = []
    for part in spec.joint_parts:
        kp, kv, torque = _servo_gains(part, spec.voltage)
        lo, hi = (math.radians(a) for a in part.joint.range)
        actuators.append(f'    <position name="{part.name}" joint="{part.name}" kp="{_f(kp)}" kv="{_f(kv)}" '
                         f'ctrlrange="{_f(lo)} {_f(hi)}" forcerange="{_f(-torque)} {_f(torque)}"/>')
    excludes = "".join(f'\n    <exclude body1="{a}" body2="{b}"/>' for a, b in excluded)
    return f"""<mujoco model="{spec.name}">
  <compiler angle="degree"/>
  <option timestep="{TIMESTEP}" integrator="implicitfast"/>
  <worldbody>
    <light pos="0.5 -0.8 1.5" dir="-0.3 0.5 -1"/>
    <geom name="floor" type="plane" size="{FLOOR_SIZE} {FLOOR_SIZE} 0.05" rgba="0.18 0.24 0.33 1"
          friction="0 0 0" solmix="0" contype="1" conaffinity="2"/>
{terrain_xml(terrain)}
{_body_xml(spec, spec.root, "    ", root_z)}
  </worldbody>
  <contact>{excludes}
  </contact>
  <actuator>
{chr(10).join(actuators)}
  </actuator>
</mujoco>
"""


def lowest_z(model, data, geom_id: int) -> float:
    import numpy as np

    c = data.geom_xpos[geom_id]
    r = data.geom_xmat[geom_id].reshape(3, 3)
    size = model.geom_size[geom_id]
    gtype = int(model.geom_type[geom_id])
    import mujoco

    if gtype == mujoco.mjtGeom.mjGEOM_BOX:
        return float(c[2] - np.sum(np.abs(r[2, :]) * size[:3]))
    if gtype == mujoco.mjtGeom.mjGEOM_CYLINDER:
        cz = abs(r[2, 2])
        return float(c[2] - (cz * size[1] + size[0] * math.sqrt(max(0.0, 1.0 - cz * cz))))
    return float(c[2] - size[0])


def _set_home(model, data, spec: Spec, offsets: Optional[dict[str, float]] = None) -> None:
    for part in spec.joint_parts:
        j = part.joint
        angle = j.home + (offsets or {}).get(part.name, 0.0)
        angle = min(max(angle, j.range[0]), j.range[1])
        data.qpos[model.jnt_qposadr[model.joint(part.name).id]] = math.radians(angle)


def extent_x(model, data, geom_id: int) -> tuple[float, float]:
    """Smallest and largest world x of a geom (box, cylinder or sphere)."""
    import numpy as np

    import mujoco

    c = data.geom_xpos[geom_id]
    r = data.geom_xmat[geom_id].reshape(3, 3)
    size = model.geom_size[geom_id]
    gtype = int(model.geom_type[geom_id])
    if gtype == mujoco.mjtGeom.mjGEOM_BOX:
        half = float(np.sum(np.abs(r[0, :]) * size[:3]))
    elif gtype == mujoco.mjtGeom.mjGEOM_CYLINDER:
        cx = abs(r[0, 2])
        half = cx * size[1] + size[0] * math.sqrt(max(0.0, 1.0 - cx * cx))
    else:
        half = float(size[0])
    return float(c[0] - half), float(c[0] + half)


def build_mjcf(spec: Spec, terrain: tuple = ()) -> tuple[str, BuildInfo]:
    """MJCF text for the spec with the root dropped onto the floor, and what the builder decided.
    ``terrain`` adds scene geometry (see :func:`terrain_xml`); it does not change the robot's placement."""
    import mujoco

    warnings: list[str] = []
    probe = mujoco.MjModel.from_xml_string(_mjcf(spec, 0.0, []))
    data = mujoco.MjData(probe)
    _set_home(probe, data, spec)
    mujoco.mj_forward(probe, data)

    feet = [p.name for p in spec.parts if p.ground_contact] or [p.name for p in spec.parts]
    if not any(p.ground_contact for p in spec.parts):
        warnings.append("no part has ground_contact: true, so any floor contact counts as a fall")
    lowest = min(lowest_z(probe, data, probe.geom(n).id) for n in feet)
    root_z = -lowest + DROP_CLEARANCE

    floor = probe.geom("floor").id
    excluded: list[tuple[str, str]] = []
    for i in range(data.ncon):
        g1, g2 = (int(g) for g in data.contact.geom[i])
        if floor in (g1, g2) or data.contact.dist[i] >= 0:
            continue
        b1, b2 = probe.body(int(probe.geom_bodyid[g1])).name, probe.body(int(probe.geom_bodyid[g2])).name
        pair = tuple(sorted((b1, b2)))
        if pair not in excluded:
            excluded.append(pair)  # type: ignore[arg-type]
            warnings.append(f"parts {pair[0]} and {pair[1]} overlap in the home pose; their collisions are ignored")
    xs = [extent_x(probe, data, probe.geom(p.name).id) for p in spec.parts]
    return _mjcf(spec, root_z, excluded, terrain), BuildInfo(
        root_z=root_z, joint_names=spec.joint_names, excluded_pairs=excluded, warnings=warnings,
        front_x=max(x[1] for x in xs), back_x=min(x[0] for x in xs))


_CACHE: dict[tuple, tuple[Any, BuildInfo, str]] = {}
CACHE_SIZE = 32


def base_model(spec: Spec, terrain: tuple = ()):
    """Compiled model at nominal physics (cached per spec hash and terrain, last ``CACHE_SIZE``).
    Returns ``(model, info, xml)``."""
    import mujoco

    key = (spec.hash(), tuple(terrain))
    if key in _CACHE:
        _CACHE[key] = _CACHE.pop(key)   # most recently used last
    else:
        xml, info = build_mjcf(spec, terrain)
        _CACHE[key] = (mujoco.MjModel.from_xml_string(xml), info, xml)
        while len(_CACHE) > CACHE_SIZE:
            _CACHE.pop(next(iter(_CACHE)))
    return _CACHE[key]


def make_model(spec: Spec, world: Optional[World] = None, terrain: tuple = ()):
    """A fresh compiled model with ``world`` applied. Returns ``(model, info)``."""
    world = world or World.nominal()
    base, info, _ = base_model(spec, terrain)
    m = copy.copy(base)
    for part in spec.parts:
        gid = m.geom(part.name).id
        factor = part.friction if part.friction is not None else spec.materials[part.material].friction
        m.geom_friction[gid, 0] = world.friction * factor
    m.body_mass[1:] *= world.mass_scale
    m.body_inertia[1:] *= world.mass_scale
    m.actuator_gainprm[:, 0] *= world.kp_scale
    m.actuator_biasprm[:, 1] *= world.kp_scale
    m.actuator_forcerange[:] *= world.torque_scale
    m.opt.gravity[:] = world.gravity()
    return m, info
