"""Run one move on one robot in one world, headless, and measure what happened.

``run_move(spec, move, world, seconds, record=False) -> Result``. Every number this produces comes
from simulation; servo loads are estimates against datasheet stall torque (see servos.py).

Timeline: the servos boot at home + the world's calibration offsets (offsets are there from t=0,
never applied mid-run), the robot settles for ``SETTLE_S``, then the move plays. Commands are delayed
by the world's latency and rate-limited at each servo's no-load speed, like a real hobby servo.

Fall rules (CLAUDE.md): a part with ``ground_contact: false`` touches the floor, or the root tilts more
than ``FALL_TILT_DEG`` from upright. Distance counts only steady progress: progress in the second half
of the run x 2, capped by the total, so a one-time lurch earns nothing.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import numpy as np

from .builder import TIMESTEP, lowest_z, make_model
from .motion import trajectory
from .spec import Spec
from .worlds import World

CTRL_DT = 0.01            # servo command period, s
SETTLE_S = 0.5
FALL_TILT_DEG = 60.0
COLLAPSE_REPLAY_S = 1.5   # a robot that cannot stand is replayed for this long after it starts to go down
SATURATED = 0.98          # |torque| / limit at or above this counts as saturated
TRACE_FPS = 30


@dataclass
class JointLoad:
    peak_torque_nm: float
    available_nm: float
    peak_ratio: float           # peak |torque| / available (1.0 = stalled at the limit)
    saturated_frac: float       # fraction of control steps at the limit
    peak_speed_dps: float       # fastest the servo joint actually turned, deg/s


@dataclass
class GroundPart:
    start_cm: float             # gap between the part's lowest point and the floor after settling
    lift_cm: float              # highest that gap got during the move
    contact_frac: float         # fraction of control steps the part touched the floor


@dataclass
class Result:
    move: str
    seconds: float
    forward_m: float            # along the heading the robot had after settling
    lateral_m: float            # + = to the robot's left
    yaw_deg: float              # + = turned left (continuous, can exceed 180)
    steady_m: float             # steady forward progress (0 when the robot fell)
    max_tilt_deg: float         # root tilt from upright (gravity), worst moment
    max_tilt_change_deg: float  # root tilt relative to its settled pose, worst moment
    max_roll_change_deg: float  # side-to-side part of that (about the robot's own x axis)
    max_pitch_change_deg: float  # front-back part (about the robot's own y axis)
    fell: bool
    fell_at_s: Optional[float]
    fall_reason: Optional[str]
    joints: dict[str, JointLoad]
    self_collisions: int        # contact onsets between two parts
    self_collision_pairs: list[list[str]]
    world: dict[str, Any]
    ground: dict[str, GroundPart] = field(default_factory=dict)   # parts with ground_contact: true
    foot_slip_cm_s: float = 0.0     # mean horizontal speed of ground-contact parts while they touch the floor
    body_speed_cm_s: float = 0.0    # mean horizontal speed of the root
    start_xy_m: list[float] = field(default_factory=list)        # root position after settling
    end_xy_m: list[float] = field(default_factory=list)          # root position at the end
    warnings: list[str] = field(default_factory=list)
    trace: Optional[dict[str, Any]] = None

    @property
    def max_load_ratio(self) -> float:
        return max((j.peak_ratio for j in self.joints.values()), default=0.0)

    def to_dict(self, trace: bool = False) -> dict[str, Any]:
        out = asdict(self)
        if not trace:
            out.pop("trace", None)
        return out


def _yaw(quat: np.ndarray) -> float:
    w, x, y, z = quat
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def steady_progress(progress: list[float]) -> float:
    """Progress in the second half x 2, capped by the total: a one-time lurch earns nothing."""
    if not progress:
        return 0.0
    total = progress[-1]
    late = progress[-1] - progress[len(progress) // 2]
    return min(total, 2.0 * late)


def resolve_move(spec: Spec, move: Any) -> tuple[str, dict[str, Any]]:
    if move is None:
        return "hold", {"frames": [{"ms": 20, "joints": {p.name: p.joint.home for p in spec.joint_parts}}]}
    if isinstance(move, str):
        if move not in spec.moves:
            raise KeyError(f"{spec.name} has no move {move!r} (moves: {', '.join(sorted(spec.moves)) or 'none'})")
        return move, spec.moves[move]
    return "custom", move


def run_move(spec: Spec, move: Any = None, world: Optional[World] = None, seconds: Optional[float] = None,
             record: bool = False, repeat: Optional[bool] = None, speed: float = 1.0,
             terrain: tuple = (), pushes: Optional[list[tuple[float, float, float, float, float]]] = None,
             stop_on_fall: bool = True) -> Result:
    """Simulate ``move`` (a spec move name, a move dict, or None to hold the home pose). ``speed``
    scales frame times like ``plan_move`` (0.5 = everything takes twice as long; holds unchanged).
    ``terrain`` adds scene geometry (builder.terrain_xml). ``pushes`` are ``(t_start, duration, fx, fy,
    fz)`` force pulses in newtons on the root's centre of mass, timed from the start of the move."""
    import mujoco

    world = world or World.nominal()
    move_name, move_dict = resolve_move(spec, move)
    limits = spec.joint_limits()
    if seconds is None:
        from .motion import check_move

        plan = check_move(move_dict, limits, speed=speed)
        rep = plan["repeat"] if repeat is None else repeat
        seconds = 8.0 if rep else plan["duration_ms"] / 1000.0 + 1.0
    names, rows = trajectory(move_dict, limits, seconds, CTRL_DT, repeat=repeat, speed=speed)
    traj = np.asarray(rows, dtype=float).reshape(len(rows), len(names))

    m, info = make_model(spec, world, terrain)
    d = mujoco.MjData(m)
    parts = spec.parts
    floor = m.geom("floor").id
    geom_part = {m.geom(p.name).id: p for p in parts}
    root_id = m.body(spec.root.name).id
    qadr = np.array([m.jnt_qposadr[m.joint(n).id] for n in names], dtype=int)
    lo = np.array([limits[n]["min"] for n in names])
    hi = np.array([limits[n]["max"] for n in names])
    offsets = np.array([world.offsets_deg.get(n, 0.0) for n in names])
    servo_dps = np.array([spec.part(n).joint.servo.speed_dps(spec.voltage) for n in names])
    act = np.array([m.actuator(n).id for n in names], dtype=int)
    limit_nm = np.abs(m.actuator_forcerange[act, 1])
    vadr = np.array([m.jnt_dofadr[m.joint(n).id] for n in names], dtype=int)

    home = np.array([limits[n]["home"] for n in names])
    sent = np.clip(home + offsets, lo, hi)
    d.qpos[qadr] = np.radians(sent)
    d.ctrl[act] = np.radians(sent)
    tether_force = None
    if spec.tether and world.tether_scale > 0:
        f = world.tether_scale * spec.tether["max_force_n"]
        a = math.radians(world.tether_dir_deg)
        tether_force = np.array([f * math.cos(a), f * math.sin(a), 0.0])
        tether_body = m.body(spec.tether["part"]).id
        # where the cable plugs in, relative to the body frame (the part center for root/fixed parts)
        center = np.zeros(3) if spec.part(spec.tether["part"]).joint is None else \
            np.array(spec.part(spec.tether["part"]).joint.offset) * 0.01
        tether_at = center + np.array(spec.tether["at"]) * 0.01

    def apply_tether(now: Optional[float] = None) -> None:
        """External forces: the cable (a constant horizontal pull at the plug point, plus the torque it
        makes about the COM) and any push pulse active at move time ``now``."""
        d.xfrc_applied[:] = 0.0
        if tether_force is not None:
            point = d.xpos[tether_body] + d.xmat[tether_body].reshape(3, 3) @ tether_at
            d.xfrc_applied[tether_body, :3] = tether_force
            d.xfrc_applied[tether_body, 3:] = np.cross(point - d.xipos[tether_body], tether_force)
        if pushes and now is not None:
            for t0, dur, fx, fy, fz in pushes:
                if t0 - 1e-9 <= now < t0 + dur - 1e-9:
                    d.xfrc_applied[root_id, :3] += (fx, fy, fz)

    mujoco.mj_forward(m, d)
    apply_tether()

    g = np.array(world.gravity())
    up = -g / np.linalg.norm(g)
    sub = max(1, int(round(CTRL_DT / TIMESTEP)))
    fell, fell_at, reason = False, None, None
    max_tilt = 0.0

    floor_parts: set[str] = set()

    def check(now: Optional[float]) -> tuple[Optional[str], set]:
        touching: set[tuple[str, str]] = set()
        floor_parts.clear()
        why = None
        for i in range(d.ncon):
            g1, g2 = int(d.contact.geom[i, 0]), int(d.contact.geom[i, 1])
            if g1 == floor or g2 == floor:
                part = geom_part.get(g2 if g1 == floor else g1)
                if part is not None:
                    floor_parts.add(part.name)
                    if not part.ground_contact and why is None:
                        why = f"part '{part.name}' touched the floor"
            elif g1 in geom_part and g2 in geom_part:
                touching.add(tuple(sorted((geom_part[g1].name, geom_part[g2].name))))
        return why, touching

    def tilt_deg() -> float:
        z_axis = d.xmat[root_id].reshape(3, 3)[:, 2]
        return math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(z_axis, up))))))

    # The recorded trace starts with the settling, so a robot that collapses there can still be replayed
    # (the frames are dropped again when it settles and stands).
    trace = None
    if record:
        geom_ids = [m.geom(p.name).id for p in parts]
        trace = {"fps": TRACE_FPS, "units": "m", "dt": round(1.0 / TRACE_FPS, 6),
                 "parts": [{"name": p.name, "shape": p.shape, "size_m": [s * 0.01 for s in p.size],
                            "color": p.color} for p in parts], "frames": []}
        next_frame = 0.0

        def snap() -> None:
            q = np.zeros(4)
            frame = []
            for gid in geom_ids:
                mujoco.mju_mat2Quat(q, d.geom_xmat[gid])
                frame.append([round(float(v), 5) for v in (*d.geom_xpos[gid], *q)])
            trace["frames"].append(frame)
    settle_t, settle_next = 0.0, 0.0
    for _ in range(int(round(SETTLE_S / CTRL_DT))):
        if record and settle_t + 1e-9 >= settle_next:
            snap()
            settle_next += 1.0 / TRACE_FPS
        settle_t += CTRL_DT
        apply_tether()
        mujoco.mj_step(m, d, nstep=sub)
        why, _ = check(None)
        tilt = tilt_deg()
        if why or tilt > FALL_TILT_DEG:
            fell, fell_at = True, 0.0
            reason = (why or f"root tilted {tilt:.0f} deg") + " while settling (it cannot stand)"
            break

    if record:
        if fell:                        # let the collapse play out for the replay (no result depends on it)
            extra_next = 0.0
            for k in range(int(round(COLLAPSE_REPLAY_S / CTRL_DT))):
                if k * CTRL_DT + 1e-9 >= extra_next:
                    snap()
                    extra_next += 1.0 / TRACE_FPS
                apply_tether()
                mujoco.mj_step(m, d, nstep=sub)
            snap()
        else:
            trace["frames"].clear()
        next_frame = 0.0

    x0, y0 = float(d.xpos[root_id, 0]), float(d.xpos[root_id, 1])
    yaw0 = _yaw(d.xquat[root_id])
    hx, hy = math.cos(yaw0), math.sin(yaw0)
    yaw_acc, yaw_prev = 0.0, yaw0
    progress = []
    peak = np.zeros(len(names))
    peak_speed = np.zeros(len(names))
    saturated = np.zeros(len(names))
    steps_done = 0
    lat_steps = int(round(world.latency_s / CTRL_DT))
    max_step = servo_dps * CTRL_DT
    touching_prev: set = set()
    collisions = 0
    pairs: set = set()
    r_settled = d.xmat[root_id].reshape(3, 3).copy()
    z_settled = r_settled[:, 2].copy()
    max_tilt_change = max_roll = max_pitch = 0.0
    ground_parts = [(p.name, m.geom(p.name).id) for p in parts if p.ground_contact]
    ground_start = {name: lowest_z(m, d, gid) for name, gid in ground_parts}
    ground_max = dict(ground_start)
    ground_touch = {name: 0 for name, _ in ground_parts}
    ground_gid = {name: gid for name, gid in ground_parts}
    slip_sum = slip_n = 0.0
    body_speed_sum = 0.0
    vel6 = np.zeros(6)

    if not fell:
        for i in range(len(traj)):
            now = i * CTRL_DT
            if record and now + 1e-9 >= next_frame:
                snap()
                next_frame += 1.0 / TRACE_FPS
            cmd = np.clip(traj[max(0, i - lat_steps)] + offsets, lo, hi)
            sent = sent + np.clip(cmd - sent, -max_step, max_step)
            d.ctrl[act] = np.radians(sent)
            apply_tether(now)
            mujoco.mj_step(m, d, nstep=sub)
            steps_done += 1

            force = np.abs(d.actuator_force[act])
            peak = np.maximum(peak, force)
            saturated += force >= SATURATED * limit_nm
            peak_speed = np.maximum(peak_speed, np.abs(d.qvel[vadr]))
            p = d.xpos[root_id]
            progress.append((p[0] - x0) * hx + (p[1] - y0) * hy)
            yaw_now = _yaw(d.xquat[root_id])
            yaw_acc += _wrap(yaw_now - yaw_prev)
            yaw_prev = yaw_now

            why, touching = check(now)
            new = touching - touching_prev
            collisions += len(new)
            pairs |= touching
            touching_prev = touching
            for name, gid in ground_parts:
                ground_max[name] = max(ground_max[name], lowest_z(m, d, gid))
                ground_touch[name] += name in floor_parts
            for name in floor_parts:
                gid = ground_gid.get(name)
                if gid is not None:
                    mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_GEOM, gid, vel6, 0)
                    slip_sum += math.hypot(vel6[3], vel6[4])
                    slip_n += 1
            mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, root_id, vel6, 0)
            body_speed_sum += math.hypot(vel6[3], vel6[4])
            tilt = tilt_deg()
            max_tilt = max(max_tilt, tilt)
            r_now = d.xmat[root_id].reshape(3, 3)
            max_tilt_change = max(max_tilt_change,
                                  math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(r_now[:, 2], z_settled)))))))
            rel = r_settled.T @ r_now          # rotation since settling, in the robot's settled frame
            max_roll = max(max_roll, abs(math.degrees(math.atan2(rel[2, 1], rel[2, 2]))))
            max_pitch = max(max_pitch, abs(math.degrees(math.asin(max(-1.0, min(1.0, -rel[2, 0]))))))
            if not fell and (why or tilt > FALL_TILT_DEG):
                fell, fell_at = True, round(now + CTRL_DT, 3)
                reason = why or f"root tilted more than {FALL_TILT_DEG:.0f} deg"
                if stop_on_fall and not record:
                    break
        if record:
            snap()

    p = d.xpos[root_id]
    forward = (p[0] - x0) * hx + (p[1] - y0) * hy
    lateral = -(p[0] - x0) * hy + (p[1] - y0) * hx
    steady = 0.0 if fell else steady_progress(progress)
    n = max(steps_done, 1)
    loads = {name: JointLoad(peak_torque_nm=round(float(peak[k]), 5), available_nm=round(float(limit_nm[k]), 5),
                             peak_ratio=round(float(peak[k] / limit_nm[k]), 4),
                             saturated_frac=round(float(saturated[k] / n), 4),
                             peak_speed_dps=round(math.degrees(float(peak_speed[k])), 2)) for k, name in enumerate(names)}
    return Result(move=move_name, seconds=float(seconds), forward_m=round(float(forward), 5),
                  lateral_m=round(float(lateral), 5), yaw_deg=round(math.degrees(yaw_acc), 3),
                  steady_m=round(float(steady), 5), max_tilt_deg=round(max_tilt, 3),
                  max_tilt_change_deg=round(max_tilt_change, 3), max_roll_change_deg=round(max_roll, 3),
                  max_pitch_change_deg=round(max_pitch, 3), fell=fell, fell_at_s=fell_at,
                  fall_reason=reason, joints=loads, self_collisions=collisions,
                  self_collision_pairs=[list(pr) for pr in sorted(pairs)], world=world.to_dict(),
                  foot_slip_cm_s=round(slip_sum / slip_n * 100, 3) if slip_n else 0.0,
                  body_speed_cm_s=round(body_speed_sum / n * 100, 3),
                  start_xy_m=[round(x0, 5), round(y0, 5)], end_xy_m=[round(float(p[0]), 5), round(float(p[1]), 5)],
                  ground={name: GroundPart(start_cm=round(ground_start[name] * 100, 3),
                                           lift_cm=round(ground_max[name] * 100, 3),
                                           contact_frac=round(ground_touch[name] / n, 4)) for name, _ in ground_parts},
                  warnings=list(info.warnings), trace=trace)


def run_worlds(spec: Spec, move: Any, seconds: Optional[float], seeds: list[int],
               repeat: Optional[bool] = None) -> list[Result]:
    """The same move in one random world per seed (worlds drawn from the spec's ranges)."""
    return [run_move(spec, move, World.random(s, spec.joint_names, spec.world_ranges), seconds, repeat=repeat)
            for s in seeds]


def summarize(results: list[Result]) -> dict[str, Any]:
    steady = np.array([r.steady_m for r in results])
    falls = [r for r in results if r.fell]
    reasons: dict[str, int] = {}
    for r in falls:
        reasons[r.fall_reason] = reasons.get(r.fall_reason, 0) + 1
    return {
        "runs": len(results),
        "falls": len(falls),
        "no_fall_rate": round(1 - len(falls) / max(len(results), 1), 3),
        "steady_cm_median": round(float(np.median(steady)) * 100, 2),
        "steady_cm_p10": round(float(np.percentile(steady, 10)) * 100, 2),
        "forward_cm_median": round(float(np.median([r.forward_m for r in results])) * 100, 2),
        "yaw_deg_median": round(float(np.median([r.yaw_deg for r in results])), 2),
        "max_tilt_deg_median": round(float(np.median([r.max_tilt_deg for r in results])), 2),
        "max_load_ratio": round(max(r.max_load_ratio for r in results), 3),
        "fall_reasons": reasons,
    }
