"""Keyframe moves: format, validation (``plan_move``) and playback (``MotionEngine``).

Evolved from caduceus-body ``bodycore.py``, so a move plays the same way in the simulator, on the
virtual robot and on the ESP32 firmware. Standard library only.

A move is ``{"frames": [...], "loops": 1, "repeat": false, "description": "..."}``. Each frame is
``{"ms": 400, "joints": {"name": degrees, ...}, "hold": 0}`` (plus an optional ``face`` for robots
with a screen). A transition eases in and out (smoothstep) from wherever the joints are, and lasts at
least as long as the slowest joint's speed limit needs. Joints a frame does not name keep their angle.
``repeat: true`` marks a gait: the simulator plays it over and over until the run time ends.

``joints`` everywhere below is ``{name: {"min", "max", "home", "max_speed"}}`` (degrees, deg/s), built
from the robot spec (range from the spec, speed from the servo catalog).
"""

from __future__ import annotations

import math
from typing import Any, Optional

FACES = ("idle", "happy", "thinking", "talking", "surprised", "sad", "sleepy", "asking", "working")

MAX_FRAMES = 64
MIN_FRAME_MS = 20
MAX_FRAME_MS = 10_000
MAX_HOLD_MS = 10_000
MAX_LOOPS = 10
MAX_TOTAL_MS = 120_000
DEFAULT_FRAME_MS = 400
MIN_SPEED_FACTOR = 0.25
MAX_SPEED_FACTOR = 2.0
MOVE_KEYS = {"frames", "loops", "repeat", "description"}


class MoveError(ValueError):
    """A move that cannot be played as written. ``problems`` lists every reason, one per line."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def home_pose(joints: dict[str, dict[str, Any]]) -> dict[str, float]:
    return {name: float(j["home"]) for name, j in joints.items()}


def frame_duration_ms(start: dict[str, float], target: dict[str, float],
                      joints: dict[str, dict[str, Any]], ms: float) -> int:
    """How long a transition really takes: the requested ``ms`` or longer, so no joint exceeds its
    ``max_speed`` on average over the transition."""
    needed = 0.0
    for name, angle in target.items():
        joint = joints.get(name)
        if joint is None:
            continue
        delta = abs(angle - start.get(name, joint["home"]))
        needed = max(needed, delta / joint["max_speed"] * 1000.0)
    return int(math.ceil(max(float(ms), needed, float(MIN_FRAME_MS))))


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def _fmt(value: float) -> str:
    return f"{value:g}"


def plan_move(frames: Any, joints: dict[str, dict[str, Any]], *, start_pose: Optional[dict[str, float]] = None,
              loops: int = 1, speed: float = 1.0) -> dict[str, Any]:
    """Check and normalize frames. Returns ``{"frames", "loops", "duration_ms", "end_pose",
    "warnings"}``; raises :class:`MoveError` listing every problem when the move cannot be played.

    Unknown joints, angles outside a joint's range and malformed frames are errors. A frame that would
    move a joint faster than its ``max_speed`` is stretched instead, with a warning."""
    problems: list[str] = []
    warnings: list[str] = []
    if not joints:
        raise MoveError(["the robot has no joints"])
    if not isinstance(frames, list) or not frames:
        raise MoveError(["frames must be a non-empty list"])
    if len(frames) > MAX_FRAMES:
        problems.append(f"{len(frames)} frames is more than the limit of {MAX_FRAMES}")
    loops_n = _number(loops)
    if loops_n is None or int(loops_n) != loops_n or not 1 <= loops_n <= MAX_LOOPS:
        problems.append(f"loops must be a whole number from 1 to {MAX_LOOPS}")
        loops_n = 1
    speed_n = _number(speed)
    if speed_n is None or not MIN_SPEED_FACTOR <= speed_n <= MAX_SPEED_FACTOR:
        problems.append(f"speed must be between {MIN_SPEED_FACTOR} and {MAX_SPEED_FACTOR}")
        speed_n = 1.0

    normalized: list[dict[str, Any]] = []
    for index, frame in enumerate(frames[:MAX_FRAMES], start=1):
        where = f"frame {index}"
        if not isinstance(frame, dict):
            problems.append(f"{where}: must be an object like {{\"ms\": 400, \"joints\": {{...}}}}")
            continue
        unknown_keys = set(frame) - {"ms", "joints", "hold", "face"}
        if unknown_keys:
            problems.append(f"{where}: unknown field(s) {', '.join(sorted(map(str, unknown_keys)))} "
                            "(use ms, joints, hold, face)")
        ms = _number(frame.get("ms", DEFAULT_FRAME_MS))
        if ms is None or not MIN_FRAME_MS <= ms <= MAX_FRAME_MS:
            problems.append(f"{where}: ms must be a number from {MIN_FRAME_MS} to {MAX_FRAME_MS}")
            ms = DEFAULT_FRAME_MS
        hold = _number(frame.get("hold", 0))
        if hold is None or not 0 <= hold <= MAX_HOLD_MS:
            problems.append(f"{where}: hold must be a number from 0 to {MAX_HOLD_MS}")
            hold = 0
        face = frame.get("face")
        if face is not None and face not in FACES:
            problems.append(f"{where}: face {face!r} is not one of {', '.join(FACES)}")
            face = None
        raw_joints = frame.get("joints", {})
        if not isinstance(raw_joints, dict):
            problems.append(f"{where}: joints must be an object of joint name -> angle")
            raw_joints = {}
        targets: dict[str, float] = {}
        for raw_name, raw_angle in raw_joints.items():
            name = str(raw_name)
            joint = joints.get(name)
            if joint is None:
                problems.append(f"{where}: no joint named {name!r} (joints: {', '.join(joints)})")
                continue
            angle = _number(raw_angle)
            if angle is None:
                problems.append(f"{where}: {name} angle must be a number")
                continue
            if not joint["min"] <= angle <= joint["max"]:
                problems.append(f"{where}: {name}={_fmt(angle)} is outside its range "
                                f"{_fmt(joint['min'])}..{_fmt(joint['max'])}")
                continue
            targets[name] = angle
        if not raw_joints and face is None and not hold:
            problems.append(f"{where}: moves nothing (give joints, a hold or a face)")
        normalized.append({"ms": int(round(ms / speed_n)), "hold": int(round(hold)),
                           "joints": targets, **({"face": face} if face else {})})
    if problems:
        raise MoveError(problems)

    pose = dict(start_pose or home_pose(joints))
    for name, joint in joints.items():
        pose.setdefault(name, float(joint["home"]))
    total = 0
    stretched: dict[int, dict[str, Any]] = {}
    for _ in range(int(loops_n)):
        for index, frame in enumerate(normalized):
            target = {**pose, **frame["joints"]}
            needed = frame_duration_ms(pose, frame["joints"], joints, MIN_FRAME_MS)
            if needed > frame["ms"]:
                def travel(n: str, start: dict[str, float] = pose, moves: dict[str, float] = frame["joints"]) -> float:
                    return abs(moves[n] - start[n]) / joints[n]["max_speed"]
                limiter = max(frame["joints"], key=travel)
                entry = stretched.setdefault(index, {"before": frame["ms"]})
                entry.update(after=needed, joint=limiter, delta=abs(frame["joints"][limiter] - pose[limiter]))
                frame["ms"] = needed
            total += frame["ms"] + frame["hold"]
            pose = target
    for index, s in sorted(stretched.items()):
        warnings.append(f"frame {index + 1} slowed from {s['before']} ms to {s['after']} ms: {s['joint']} moves "
                        f"{s['delta']:.0f} deg and its limit is {_fmt(joints[s['joint']]['max_speed'])} deg/s")
    if total > MAX_TOTAL_MS:
        raise MoveError([f"the move lasts {total / 1000:.1f} s, more than the limit of {MAX_TOTAL_MS // 1000} s"])
    return {"frames": normalized, "loops": int(loops_n), "duration_ms": total, "end_pose": pose,
            "warnings": warnings}


def check_move(move: Any, joints: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Validate a whole move object (frames + loops + repeat + description) and plan it."""
    if not isinstance(move, dict):
        raise MoveError(["a move must be an object with frames (and optional loops, repeat, description)"])
    problems = []
    unknown = set(move) - MOVE_KEYS
    if unknown:
        problems.append(f"unknown field(s) {', '.join(sorted(map(str, unknown)))} (use {', '.join(sorted(MOVE_KEYS))})")
    if "repeat" in move and not isinstance(move["repeat"], bool):
        problems.append("repeat must be true or false")
    if "description" in move and not isinstance(move["description"], str):
        problems.append("description must be text")
    try:
        plan = plan_move(move.get("frames"), joints, loops=move.get("loops", 1))
    except MoveError as exc:
        raise MoveError(problems + exc.problems) from None
    if problems:
        raise MoveError(problems)
    plan["repeat"] = bool(move.get("repeat", False))
    return plan


def smoothstep(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


class MotionEngine:
    """Plays frames against a pose, the way the firmware does: each transition eases in and out
    (smoothstep) from wherever the joints are when it starts, lasts at least as long as the slowest
    joint's speed limit needs, then holds. Angles are clamped to each joint's range again here."""

    def __init__(self, joints: dict[str, dict[str, Any]]):
        self.joints = joints
        self.pose = home_pose(joints)
        self._program: list[dict[str, Any]] = []
        self._loops = 1
        self._index = 0
        self._loop = 0
        self._phase = "idle"
        self._phase_start = 0.0
        self._start: dict[str, float] = {}
        self._target: dict[str, float] = {}
        self._duration = 0.0

    @property
    def busy(self) -> bool:
        return self._phase != "idle"

    def clamp(self, name: str, angle: float) -> float:
        joint = self.joints[name]
        return min(max(angle, joint["min"]), joint["max"])

    def load(self, frames: list[dict[str, Any]], *, loops: int = 1, now: float = 0.0) -> None:
        self._program = [
            {"ms": max(int(f.get("ms", DEFAULT_FRAME_MS)), MIN_FRAME_MS), "hold": max(int(f.get("hold", 0)), 0),
             "joints": {n: self.clamp(n, float(a)) for n, a in (f.get("joints") or {}).items() if n in self.joints}}
            for f in frames[:MAX_FRAMES]
        ]
        self._loops = max(1, min(int(loops), MAX_LOOPS))
        self._index = 0
        self._loop = 0
        if self._program:
            self._begin_frame(now)
        else:
            self._phase = "idle"

    def _begin_frame(self, now: float) -> None:
        frame = self._program[self._index]
        self._start = dict(self.pose)
        self._target = {**self.pose, **frame["joints"]}
        self._duration = frame_duration_ms(self._start, frame["joints"], self.joints, frame["ms"]) / 1000.0
        self._phase = "move"
        self._phase_start = now

    def tick(self, now: float) -> None:
        # Catch up through every phase boundary that has passed, so a slow tick never skips a frame.
        for _ in range(4 * MAX_FRAMES * MAX_LOOPS):
            if self._phase == "idle":
                return
            frame = self._program[self._index]
            elapsed = now - self._phase_start
            if self._phase == "move":
                t = 1.0 if self._duration <= 0 else elapsed / self._duration
                eased = smoothstep(t)
                self.pose = {n: self._start[n] + (self._target[n] - self._start[n]) * eased for n in self.pose}
                if t < 1.0:
                    return
                self.pose = dict(self._target)
                self._phase, self._phase_start = "hold", self._phase_start + self._duration
                continue
            if elapsed < frame["hold"] / 1000.0:
                return
            boundary = self._phase_start + frame["hold"] / 1000.0
            self._index += 1
            if self._index >= len(self._program):
                self._index = 0
                self._loop += 1
                if self._loop >= self._loops:
                    self._phase, self._program = "idle", []
                    return
            self._begin_frame(boundary)


def trajectory(move: dict[str, Any], joints: dict[str, dict[str, Any]], seconds: float, dt: float,
               repeat: Optional[bool] = None) -> tuple[list[str], list[list[float]]]:
    """Commanded joint angles (degrees) every ``dt`` seconds for ``seconds``. The move plays once (with
    its loops) and then holds its end pose, or, for ``repeat`` moves, starts over until time runs out.
    Returns ``(joint names, rows)``."""
    plan = check_move(move, joints)
    if repeat is None:
        repeat = plan["repeat"]
    names = list(joints)
    engine = MotionEngine(joints)
    engine.load(plan["frames"], loops=plan["loops"], now=0.0)
    steps = int(round(seconds / dt))
    rows: list[list[float]] = []
    t = 0.0
    for _ in range(steps):
        engine.tick(t)
        if repeat and not engine.busy:
            engine.load(plan["frames"], loops=plan["loops"], now=t)
            engine.tick(t)
        rows.append([engine.pose[n] for n in names])
        t += dt
    return names, rows
