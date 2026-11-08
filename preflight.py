"""Motion preflight: simulation-based risk screening of a move before it plays on a robot.

``check(spec, name, move)`` plays the move in N randomized worlds on flat ground and reports the tip
probability with a 95% Wilson interval, peak servo load estimates per joint, collisions, speed-limit
stretches and a verdict. A passing check writes an approval record keyed by
``approval_key(spec, move, speed)``: a hash of the robot's physics, its firmware/hardware mapping, the
exact move content and the playback speed. Change any of them and the approval no longer applies.

This is risk screening in simulation, not a safety guarantee. Servo loads are estimates against
datasheet stall torque.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .motion import MoveError, check_move
from .simrun import run_move
from .spec import Spec
from .worlds import World

DEFAULT_WORLDS = 60
QUICK_WORLDS = 30
BATCH = 10
SEED_BASE = 5000
MOVE_KEYS = ("frames", "loops", "easing", "repeat")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for k successes in n trials."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _norm(value: Any) -> Any:
    """Numbers as rounded floats (so 30 and 30.0 hash the same), recursively."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 4)
    if isinstance(value, dict):
        return {str(k): _norm(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    return value


def canonical_move(move: dict[str, Any]) -> dict[str, Any]:
    """The parts of a move that change what the robot does (no description), with defaults filled in."""
    out = {k: move[k] for k in MOVE_KEYS if k in move}
    out.setdefault("loops", 1)
    out.setdefault("easing", "smoothstep")
    out.setdefault("repeat", False)
    frames = []
    for f in out.get("frames") or []:
        if isinstance(f, dict):
            f = dict(f)
            f.setdefault("hold", 0)
        frames.append(f)
    out["frames"] = frames
    return _norm(out)


def approval_key(spec: Spec, move: dict[str, Any], speed: float = 1.0) -> str:
    blob = json.dumps({"physics": spec.hash(), "hardware": spec.hardware_mapping(),
                       "move": canonical_move(move), "speed": round(float(speed), 4)},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ApprovalStore:
    """One JSON record per approval key (the latest check of that exact move), pass or fail."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def path(self, key: str) -> Path:
        return self.folder / f"{key}.json"

    def save(self, record: dict[str, Any]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.path(record["key"]).with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=1), encoding="utf-8")
        tmp.replace(self.path(record["key"]))

    def get(self, key: str) -> Optional[dict[str, Any]]:
        try:
            return json.loads(self.path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None


def _frame_times(plan: dict[str, Any]) -> list[tuple[float, float, int]]:
    """(start s, end s, frame index) for every frame of every loop, after speed-limit stretching."""
    out, t = [], 0.0
    for _ in range(plan["loops"]):
        for i, f in enumerate(plan["frames"]):
            end = t + (f["ms"] + f["hold"]) / 1000.0
            out.append((t, end, i))
            t = end
    return out


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def check(spec: Spec, name: str, move: dict[str, Any], speed: float = 1.0, worlds: int = DEFAULT_WORLDS,
          seed: int = SEED_BASE, max_tip_upper: float = 0.10, max_load: float = 0.90,
          adaptive: bool = True) -> dict[str, Any]:
    """Screen ``move`` in randomized worlds (flat ground). Returns a JSON-able result.

    Adaptive (default): worlds run in batches of ``BATCH``; the check stops early once the tip chance is
    clearly above ``max_tip_upper`` (the Wilson lower bound is past it), and a clean run that is too
    short to bound the chance (e.g. quick mode, 0/30 leaves 11%) is extended to ``DEFAULT_WORLDS``."""
    limits = spec.joint_limits()
    plan = check_move(move, limits, speed=speed)        # raises MoveError for unplayable moves
    seconds = 8.0 if plan["repeat"] else plan["duration_ms"] / 1000.0 + 1.0
    target = max(1, int(worlds))
    runs: list = []
    stopped_early = extended = False
    while True:
        while len(runs) < target:
            i = len(runs)
            runs.append(run_move(spec, move, World.random(seed + i, spec.joint_names, spec.world_ranges),
                                 seconds, speed=speed))
            if (adaptive and len(runs) % BATCH == 0 and len(runs) < target
                    and wilson(sum(r.fell for r in runs), len(runs))[0] > max_tip_upper):
                stopped_early = True               # the failure is already clear
                break
        if stopped_early:
            break
        k0 = sum(r.fell for r in runs)
        # No tips yet but too few worlds to bound the chance under the limit: extend before deciding.
        if adaptive and k0 == 0 and wilson(0, len(runs))[1] > max_tip_upper and target < DEFAULT_WORLDS:
            target, extended = DEFAULT_WORLDS, True
            continue
        break
    falls = [r for r in runs if r.fell]
    k, n = len(falls), len(runs)
    lo, hi = wilson(k, n)
    tip_seeds = [seed + i for i, r in enumerate(runs) if r.fell][:5]
    joints = {}
    for j in spec.joint_names:
        peaks = np.array([r.joints[j].peak_ratio for r in runs])
        joints[j] = {"peak_pct_p90": round(float(np.percentile(peaks, 90)) * 100, 1),
                     "peak_pct_max": round(float(peaks.max()) * 100, 1),
                     "near_limit_time_pct_median": round(float(np.median([r.joints[j].saturated_frac for r in runs])) * 100, 1)}
    over = {j: v for j, v in joints.items() if v["peak_pct_p90"] > max_load * 100}
    ground = sum(1 for r in falls if "touched the floor" in (r.fall_reason or ""))
    self_coll = sum(1 for r in runs if r.self_collisions)
    timeline = _frame_times(plan)
    fall_frame = None
    if falls:
        t_med = float(np.median([r.fell_at_s for r in falls if r.fell_at_s is not None] or [0.0]))
        fall_frame = next((i for s, e, i in timeline if s <= t_med < e), timeline[-1][2] if timeline else None)
    tip_ok = hi <= max_tip_upper
    load_ok = not over
    if tip_ok and load_ok:
        verdict = "pass"
    elif k == 0 and load_ok:
        verdict = "inconclusive"
    else:
        verdict = "fail"
    reasons = []
    if not tip_ok:
        reasons.append(f"tips in {_pct(k / n)} ({_pct(lo)}-{_pct(hi)}) of simulated worlds"
                       + (f", mostly during frame {fall_frame + 1}" if fall_frame is not None else ""))
    if over:
        worst = sorted(over.items(), key=lambda kv: -kv[1]["peak_pct_p90"])
        reasons.append("servo load above " + f"{max_load * 100:.0f}% of stall (estimate, 90th percentile): "
                       + ", ".join(f"{j} {v['peak_pct_p90']:.0f}%" for j, v in worst))
    if verdict == "inconclusive":
        reasons = [f"0 tips in {n} worlds is not enough to show the tip chance is below {_pct(max_tip_upper)} "
                   f"(upper bound {_pct(hi)}); run the check with {DEFAULT_WORLDS} or more worlds"]
    result = {
        "robot": spec.name, "move": name, "speed": speed, "worlds": n, "verdict": verdict,
        "worlds_requested": int(worlds), "stopped_early": stopped_early, "extended": extended,
        "seed": seed, "tip_seeds": tip_seeds,
        "tip": {"falls": k, "rate": round(k / n, 4), "low": round(lo, 4), "high": round(hi, 4),
                "fall_reasons": _count(r.fall_reason for r in falls), "fall_frame": None if fall_frame is None else fall_frame + 1},
        "joints": joints, "ground_contacts": ground, "self_collision_worlds": self_coll,
        "speed_limit_stretches": list(plan["warnings"]),
        "duration_s": round(plan["duration_ms"] / 1000.0, 3),
        "thresholds": {"max_tip_upper": max_tip_upper, "max_load": max_load},
        "reasons": reasons,
        "suggestions": suggestions(plan, limits, fall_frame, over, speed) if verdict == "fail" else [],
        "simulation": True,
        "label": "Simulation-based risk screening, not a safety guarantee.",
    }
    return result


def _count(items) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in items:
        if x:
            out[x] = out.get(x, 0) + 1
    return out


def suggestions(plan: dict[str, Any], limits: dict[str, Any], fall_frame: Optional[int], over: dict[str, Any],
                speed: float) -> list[str]:
    """Concrete fixes derived from the move and the numbers."""
    tips: list[str] = []
    frames = plan["frames"]
    pose = {n: j["home"] for n, j in limits.items()}
    changes = []
    for f in frames:
        delta = {n: abs(a - pose[n]) for n, a in f["joints"].items()}
        changes.append(delta)
        pose.update(f["joints"])
    focus = fall_frame if fall_frame is not None else max(range(len(frames)),
                                                        key=lambda i: max(changes[i].values(), default=0) / max(frames[i]["ms"], 1))
    f, delta = frames[focus], changes[focus]
    moving = [n for n, d in delta.items() if d >= 15]
    fastest = max((d / max(f["ms"], 1) * 1000 for d in delta.values()), default=0.0)
    slower = max(0.25, round(speed * 0.5, 2))
    if fastest >= 60:
        tips.append(f"Slow it down: frame {focus + 1} turns a joint at about {fastest:.0f} deg/s; play the move at "
                    f"speed {slower:g} (every transition twice as long) or give frame {focus + 1} at least "
                    f"{int(f['ms'] * 2)} ms.")
    if len(moving) >= 2:
        tips.append(f"One limb at a time: frame {focus + 1} moves {', '.join(moving)} together; split it into "
                    f"{len(moving)} frames that each move one of them.")
    big = [n for n, d in delta.items() if d >= 40] or list(over)
    if big:
        tips.append(f"Smaller amplitude: swing {', '.join(big)} about 30% less in frame {focus + 1}.")
    if not tips:
        tips.append("Slow it down: play the move at speed 0.5 and check again.")
    return tips


def record(key: str, spec: Spec, name: str, move: dict[str, Any], speed: float, result: dict[str, Any]) -> dict[str, Any]:
    return {"key": key, "robot": spec.name, "move_name": name, "move": canonical_move(move), "speed": speed,
            "spec_hash": spec.hash(), "verdict": result["verdict"], "tip": result["tip"],
            "reasons": result["reasons"], "suggestions": result["suggestions"],
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "worlds": result["worlds"]}


def summary_line(result: dict[str, Any]) -> str:
    t = result["tip"]
    head = (f"{result['robot']} / {result['move']} at speed {result['speed']:g}: {result['verdict'].upper()} - tips in "
            f"{t['falls']}/{result['worlds']} simulated worlds ({_pct(t['rate'])}, 95% interval "
            f"{_pct(t['low'])}-{_pct(t['high'])})")
    worst = max(result["joints"].items(), key=lambda kv: kv[1]["peak_pct_p90"])
    return head + f"; highest servo load {worst[0]} {worst[1]['peak_pct_p90']:.0f}% of stall (estimate, p90)."


__all__ = ["wilson", "approval_key", "canonical_move", "check", "ApprovalStore", "record", "summary_line",
           "MoveError", "DEFAULT_WORLDS", "QUICK_WORLDS"]
