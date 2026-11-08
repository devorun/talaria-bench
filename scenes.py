"""Test arena scenes: terrain, start, move, metrics, pass rule and failure reasons.

Every scene runs in randomized worlds (worlds.py) and every number is simulation. Scenes:

* ``flat``: flat floor; pass = steady forward progress >= ``flat_min_cm`` (default 5 cm) and no fall.
* ``ramp_5`` / ``ramp_10`` / ``ramp_15``: the floor tilts up ahead of the robot (gravity is tilted, so the
  whole floor is the ramp); pass = climbs >= 5 cm along the slope without falling or sliding back.
* ``obstacle_1cm`` / ``obstacle_2cm``: a bar 2 cm deep across the path, 5 cm ahead of the robot's front;
  pass = the root ends >= 5 cm past the bar.
* ``push``: horizontal force pulses on the root (0.1 s, a multiple of body weight) from the front,
  back, left and right, increasing until the robot tips; pass = it survives a NUDGE (0.1 x weight for
  0.1 s, i.e. a velocity change of ~10 cm/s) from every side while standing. How far the robot slides
  after each push it survives is measured too (a low, wide robot slides instead of tipping). Robots with
  a walk are also nudged mid-walk (reported, not part of the pass rule).
* ``slippery``: effective foot-floor friction 0.08-0.15 whatever the feet are made of; pass = steady progress >= 50% of the robot's flat median and no
  fall (decided by the benchmark once the flat results are in).
* ``move:<name>`` (family ``moves``): every move of the robot that is not its walk or a repeating gait,
  played standing; pass = no fall. This is where arm gestures and dances are screened.

Scenes that need walking are "not applicable" for robots without a walk move.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .builder import base_model
from .simrun import Result, run_move
from .spec import Spec
from .worlds import World

SCENE_VERSION = 2
NUDGE = 0.1                                   # x body weight, for PUSH_DURATION seconds
PUSH_LEVELS = (0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)
PUSH_DURATION = 0.1                           # s
PUSH_AT = 1.0                                 # s after the move starts (standing)
PUSH_RUN = 3.0                                # s per standing push run
#: where the push comes from -> direction of the force (unit x, y): from the front pushes backwards
PUSH_DIRECTIONS = {"front": (-1.0, 0.0), "back": (1.0, 0.0), "left": (0.0, -1.0), "right": (0.0, 1.0)}
RAMP_MIN_CM = 5.0
OBSTACLE_AHEAD_M = 0.05
OBSTACLE_DEPTH_M = 0.02
OBSTACLE_PASS_M = 0.05
STUCK_MARGIN_M = 0.03
SLIPPERY_FRICTION = (0.08, 0.15)        # effective foot-floor friction, any material
SLIPPERY_SHARE = 0.5
G = 9.81


@dataclass(frozen=True)
class Scene:
    id: str
    family: str
    title: str
    locomotion: bool          # needs the walk move
    metric: str               # main metric name
    unit: str
    params: dict = field(default_factory=dict)


SCENES: dict[str, Scene] = {
    "flat": Scene("flat", "flat", "Flat floor", True, "steady progress", "cm"),
    "ramp_5": Scene("ramp_5", "ramp", "Ramp 5 deg", True, "climb along the slope", "cm", {"angle": 5.0}),
    "ramp_10": Scene("ramp_10", "ramp", "Ramp 10 deg", True, "climb along the slope", "cm", {"angle": 10.0}),
    "ramp_15": Scene("ramp_15", "ramp", "Ramp 15 deg", True, "climb along the slope", "cm", {"angle": 15.0}),
    "obstacle_1cm": Scene("obstacle_1cm", "obstacle", "Bar 1 cm", True, "distance past the bar", "cm",
                          {"height": 0.01}),
    "obstacle_2cm": Scene("obstacle_2cm", "obstacle", "Bar 2 cm", True, "distance past the bar", "cm",
                          {"height": 0.02}),
    "push": Scene("push", "push", "Push test", False, "weakest tipping push", "x weight"),
    "slippery": Scene("slippery", "slippery", "Slippery floor", True, "steady progress", "cm"),
}
FAMILIES: dict[str, list[str]] = {}
for _s in SCENES.values():
    FAMILIES.setdefault(_s.family, []).append(_s.id)
FAMILIES["moves"] = []          # filled per robot: move:<name> for each standing move


def get_scene(scene_id: str) -> Scene:
    if scene_id in SCENES:
        return SCENES[scene_id]
    if scene_id.startswith("move:") and len(scene_id) > 5:
        name = scene_id[5:]
        return Scene(scene_id, "moves", f"Move '{name}'", False, "max body tilt", "deg", {"move": name})
    raise KeyError(f"unknown scene {scene_id!r}")


def move_scenes(spec: Spec) -> list[str]:
    """``move:<name>`` for every move that is not the walk and not a repeating gait."""
    walk = walk_move(spec)
    return [f"move:{n}" for n, m in spec.moves.items() if n != walk and not m.get("repeat")]


def resolve_scenes(names: Optional[list[str]] = None, spec: Optional[Spec] = None) -> list[str]:
    """Scene ids from ids or family names (``ramp`` = all three ramps, ``moves`` = the robot's
    standing moves); default: every scene, plus the robot's moves when ``spec`` is given."""
    moves = move_scenes(spec) if spec is not None else []
    if not names:
        return list(SCENES) + moves
    out: list[str] = []
    for name in names:
        ids = moves if name == "moves" else FAMILIES.get(name) or ([name] if name in SCENES else None)
        if ids is None and name.startswith("move:"):
            ids = [name]
        if ids is None:
            raise KeyError(f"unknown scene {name!r} (scenes: {', '.join(SCENES)}; families: "
                           f"{', '.join(FAMILIES)}; or move:<name>)")
        out.extend(i for i in ids if i not in out)
    return out


def walk_move(spec: Spec) -> Optional[str]:
    name = spec.bench.get("walk_move", "walk") if spec.bench else "walk"
    return name if name in spec.moves else None


def applicable(spec: Spec, scene_id: str) -> tuple[bool, str]:
    scene = get_scene(scene_id)
    if scene.family == "moves" and scene.params["move"] not in spec.moves:
        return False, f"the robot has no move {scene.params['move']!r}"
    if scene.locomotion and walk_move(spec) is None:
        return False, "the robot has no walk move"
    return True, ""


def world_for(spec: Spec, scene_id: str, seed: int) -> World:
    """World ``seed`` drawn from the spec's ranges (the same world in every scene), plus the scene's
    own conditions (ramp angle, slippery floor)."""
    world = World.random(seed, spec.joint_names, spec.world_ranges)
    scene = get_scene(scene_id)
    if scene.family == "ramp":
        world.floor_tilt_deg = scene.params["angle"]
        world.floor_tilt_dir_deg = 180.0        # the floor goes down toward -x: the robot faces uphill
    if scene.family == "slippery":
        rng = np.random.default_rng([seed, 7919])
        world.effective_friction = round(float(rng.uniform(*SLIPPERY_FRICTION)), 4)
    return world


def _short_fall(reason: Optional[str]) -> str:
    if not reason:
        return "fell"
    if "while settling" in reason:
        return "cannot stand here"
    if "touched the floor" in reason:
        return reason.split(" while")[0].replace("part ", "")
    return "tipped over"


def _loads(r: Result) -> dict[str, dict[str, float]]:
    return {n: {"peak_ratio": j.peak_ratio, "saturated_frac": j.saturated_frac} for n, j in r.joints.items()}


def _job(scene_id: str, seed: int, world: World, **kw) -> dict[str, Any]:
    return {"scene": scene_id, "seed": seed, "world": world.to_dict(), "applicable": True, "passed": None,
            "reason": None, "metric": None, "fell": False, "metrics": {}, "loads": {}, **kw}


def run_scene(spec: Spec, scene_id: str, seed: int, record: bool = False) -> dict[str, Any]:
    """One scene in world ``seed``. Returns a JSON-able job result (plus ``trace`` when recording)."""
    ok, why = applicable(spec, scene_id)
    if not ok:
        return {"scene": scene_id, "seed": seed, "applicable": False, "reason": why}
    scene = get_scene(scene_id)
    world = world_for(spec, scene_id, seed)
    seconds = spec.bench.get("seconds") if spec.bench else None
    if scene.family == "push":
        return _run_push(spec, seed, world, record)
    if scene.family == "moves":
        r = run_move(spec, scene.params["move"], world, None, record=record)
        job = _job(scene_id, seed, world, fell=r.fell, loads=_loads(r), passed=not r.fell,
                   metric=r.max_tilt_change_deg,
                   reason=_short_fall(r.fall_reason) if r.fell else None,
                   metrics={"max_roll_change_deg": r.max_roll_change_deg,
                            "max_pitch_change_deg": r.max_pitch_change_deg, "yaw_deg": r.yaw_deg,
                            "fell_at_s": r.fell_at_s, "fall_reason": r.fall_reason})
        if record:
            job["trace"] = r.trace
        return job
    move = walk_move(spec)
    terrain: tuple = ()
    if scene.family == "obstacle":
        _, info, _ = base_model(spec)
        near = info.front_x + OBSTACLE_AHEAD_M
        h = scene.params["height"]
        terrain = (("box", "bar", near + OBSTACLE_DEPTH_M / 2, 0.0, h / 2, OBSTACLE_DEPTH_M / 2, 1.0, h / 2),)
    r = run_move(spec, move, world, seconds, record=record, terrain=terrain)
    job = _job(scene_id, seed, world, fell=r.fell, loads=_loads(r),
               metrics={"forward_cm": round(r.forward_m * 100, 3), "steady_cm": round(r.steady_m * 100, 3),
                        "yaw_deg": r.yaw_deg, "lateral_cm": round(r.lateral_m * 100, 3),
                        "max_tilt_deg": r.max_tilt_deg, "fall_reason": r.fall_reason})
    if record:
        job["trace"] = r.trace
    if scene.family in ("flat", "slippery"):
        job["metric"] = job["metrics"]["steady_cm"]
        if scene.family == "flat":
            need = float(spec.bench.get("flat_min_cm", 5.0)) if spec.bench else 5.0
            job["passed"] = not r.fell and job["metric"] >= need
            if not job["passed"]:
                job["reason"] = (f"fell ({_short_fall(r.fall_reason)})" if r.fell else
                                 "no progress" if job["metric"] < 1.0 else f"too slow (< {need:g} cm)")
        return job                                  # slippery: decided against the flat median later
    if scene.family == "ramp":
        job["metric"] = job["metrics"]["forward_cm"]
        job["passed"] = not r.fell and job["metric"] >= RAMP_MIN_CM
        if not job["passed"]:
            if r.fell and "while settling" in (r.fall_reason or ""):
                job["reason"] = "cannot stand on the slope"
            elif r.fell:
                job["reason"] = "tipped backward" if job["metric"] < 0 else f"fell ({_short_fall(r.fall_reason)})"
            elif job["metric"] <= -1.0:
                job["reason"] = "slid back"
            else:
                job["reason"] = "no progress"
        return job
    # obstacle
    _, info, _ = base_model(spec)
    near = info.front_x + OBSTACLE_AHEAD_M
    far = near + OBSTACLE_DEPTH_M
    end_x = r.end_xy_m[0]
    job["metric"] = round((end_x - far) * 100, 3)
    job["metrics"]["bar_near_cm"] = round(near * 100, 2)
    job["passed"] = not r.fell and end_x >= far + OBSTACLE_PASS_M
    if not job["passed"]:
        if r.fell:
            job["reason"] = "tipped over the bar" if end_x + info.front_x >= near else \
                f"fell ({_short_fall(r.fall_reason)})"
        elif end_x + info.front_x >= near - STUCK_MARGIN_M:   # feet reach ahead of the home pose mid-step
            job["reason"] = "stuck at the bar"
        else:
            job["reason"] = "no progress before the bar"
    return job


def _weight_n(spec: Spec, world: World) -> float:
    return spec.total_mass_g / 1000.0 * world.mass_scale * G


def _push(spec: Spec, world: World, move: Optional[str], level: float, direction: str, at: float,
          seconds: float, record: bool = False) -> Result:
    f = level * _weight_n(spec, world)
    dx, dy = PUSH_DIRECTIONS[direction]
    return run_move(spec, move, world, seconds, record=record,
                    pushes=[(at, PUSH_DURATION, f * dx, f * dy, 0.0)])


def _run_push(spec: Spec, seed: int, world: World, record: bool) -> dict[str, Any]:
    thresholds: dict[str, Optional[float]] = {}
    slides: dict[str, dict[str, float]] = {}
    loads: dict[str, dict[str, float]] = {}
    for direction in PUSH_DIRECTIONS:
        thresholds[direction] = None
        slides[direction] = {}
        for level in PUSH_LEVELS:
            r = _push(spec, world, None, level, direction, PUSH_AT, PUSH_RUN)
            if not r.fell:
                dx = r.end_xy_m[0] - r.start_xy_m[0]
                dy = r.end_xy_m[1] - r.start_xy_m[1]
                slides[direction][f"{level:g}"] = round(math.hypot(dx, dy) * 100, 3)
            if level == NUDGE:
                for n, v in _loads(r).items():
                    old = loads.get(n)
                    if old is None or v["peak_ratio"] > old["peak_ratio"]:
                        loads[n] = v
            if r.fell:
                thresholds[direction] = level
                break
    worst_dir = min(thresholds, key=lambda d: thresholds[d] if thresholds[d] is not None else math.inf)
    worst = thresholds[worst_dir]
    passed = all(t is None or t > NUDGE for t in thresholds.values())
    metrics: dict[str, Any] = {"thresholds": thresholds, "weakest_side": worst_dir, "slides_cm": slides}
    move = walk_move(spec)
    if move:
        plan_s = 2.5
        survived = {}
        for direction in PUSH_DIRECTIONS:
            r = _push(spec, world, move, NUDGE, direction, plan_s, 6.0)
            survived[direction] = not r.fell
        metrics["walk_nudge_survived"] = survived
    job = _job("push", seed, world, passed=passed, fell=worst is not None and worst <= NUDGE, loads=loads,
               metric=worst if worst is not None else None, metrics=metrics)
    if not passed:
        job["reason"] = f"tips at a nudge from the {worst_dir}"
    if record:
        level = worst if worst is not None else NUDGE
        job["trace"] = _push(spec, world, None, level, worst_dir, PUSH_AT, PUSH_RUN, record=True).trace
        job["trace_note"] = f"push {level:g} x weight from the {worst_dir}"
    return job


def decide_slippery(jobs: list[dict[str, Any]], flat_median_cm: Optional[float]) -> None:
    """Slippery passes need the flat result: progress >= 50% of the flat median and no fall."""
    for job in jobs:
        if not job.get("applicable", True) or job["scene"] != "slippery":
            continue
        need = None if flat_median_cm is None or flat_median_cm <= 0 else SLIPPERY_SHARE * flat_median_cm
        m = job["metrics"]
        job["metrics"]["needed_cm"] = None if need is None else round(need, 3)
        job["passed"] = bool(need is not None and not job["fell"] and job["metric"] >= need)
        if job["passed"]:
            job["reason"] = None
        elif job["fell"]:
            job["reason"] = f"fell ({_short_fall(m.get('fall_reason'))})"
        elif need is None:
            job["reason"] = "no flat progress to compare with"
        elif abs(m["yaw_deg"]) > 45:
            job["reason"] = "spinning in place"
        else:
            job["reason"] = "sliding"
