"""Randomized physics worlds.

A ``World`` holds everything about one simulated run that is not the robot itself: floor friction,
how far the real robot's masses and servos differ from the spec, command latency, servo calibration
offsets, a slightly tilted floor and the pull of a power cable. ``World.random(rng)`` draws one from
the ranges below; a spec (``worlds:``) or a scene can narrow or widen any range.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional

import numpy as np

#: name -> (low, high). Units: friction coefficient, scale factors, seconds, degrees.
DEFAULT_RANGES: dict[str, tuple[float, float]] = {
    "friction": (0.3, 0.7),          # floor sliding friction for a factor-1.0 material (wood parquet)
    "mass_scale": (0.85, 1.15),      # every part's mass and inertia
    "torque_scale": (0.7, 1.1),      # servo stall torque (battery sag, worn servos, datasheet optimism)
    "kp_scale": (0.6, 1.2),          # servo stiffness (how hard it pushes per degree of error)
    "latency_s": (0.0, 0.04),        # command delay
    "offset_deg": (-3.0, 3.0),       # per-servo calibration error, present from boot
    "floor_tilt_deg": (0.0, 1.5),    # floor tilt magnitude; direction is uniform
    "tether_scale": (0.0, 1.0),      # fraction of the spec's tether max_force_n
}


def merged_ranges(overrides: Optional[Mapping[str, Any]] = None) -> dict[str, tuple[float, float]]:
    ranges = dict(DEFAULT_RANGES)
    for key, value in (overrides or {}).items():
        if key not in DEFAULT_RANGES:
            raise ValueError(f"unknown world range {key!r} (known: {', '.join(DEFAULT_RANGES)})")
        lo, hi = (float(v) for v in value)
        if lo > hi:
            raise ValueError(f"world range {key}: low {lo} is above high {hi}")
        ranges[key] = (lo, hi)
    return ranges


@dataclass
class World:
    friction: float = 0.5
    mass_scale: float = 1.0
    torque_scale: float = 1.0
    kp_scale: float = 1.0
    latency_s: float = 0.0
    offsets_deg: dict[str, float] = field(default_factory=dict)   # joint name -> offset (missing = 0)
    floor_tilt_deg: float = 0.0
    floor_tilt_dir_deg: float = 0.0     # direction the floor slopes down toward, 0 = +x
    tether_scale: float = 0.0
    tether_dir_deg: float = 180.0       # direction the cable pulls (horizontal), 180 = backwards (-x)
    seed: Optional[int] = None

    @staticmethod
    def nominal() -> "World":
        return World()

    @staticmethod
    def random(rng: np.random.Generator | int, joints: list[str] | tuple[str, ...] = (),
               ranges: Optional[Mapping[str, Any]] = None) -> "World":
        """Draw a world. ``rng`` may be a seed; the same seed and joint list always give the same world."""
        seed = None
        if not isinstance(rng, np.random.Generator):
            seed = int(rng)
            rng = np.random.default_rng(seed)
        r = merged_ranges(ranges)

        def u(key: str) -> float:
            lo, hi = r[key]
            return float(rng.uniform(lo, hi)) if hi > lo else float(lo)

        world = World(
            friction=u("friction"),
            mass_scale=u("mass_scale"),
            torque_scale=u("torque_scale"),
            kp_scale=u("kp_scale"),
            latency_s=u("latency_s"),
            floor_tilt_deg=u("floor_tilt_deg"),
            floor_tilt_dir_deg=float(rng.uniform(-180.0, 180.0)),
            tether_scale=u("tether_scale"),
            tether_dir_deg=float(180.0 + rng.uniform(-60.0, 60.0)),
            seed=seed,
        )
        world.offsets_deg = {name: u("offset_deg") for name in joints}
        return world

    def gravity(self) -> tuple[float, float, float]:
        """Gravity vector for a floor tilted by ``floor_tilt_deg`` toward ``floor_tilt_dir_deg``."""
        t = math.radians(self.floor_tilt_deg)
        d = math.radians(self.floor_tilt_dir_deg)
        g = 9.81
        return (g * math.sin(t) * math.cos(d), g * math.sin(t) * math.sin(d), -g * math.cos(t))

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        return {k: (round(v, 5) if isinstance(v, float) else v) for k, v in out.items()}
