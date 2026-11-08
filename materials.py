"""Part materials: contact softness and friction. All tunable numbers live in this one table.

* ``friction``: multiplier on the floor friction of the world (``World.friction`` is the sliding
  friction of a factor-1.0 material on that floor). Rubber grips more, metal less.
* ``solref`` (time constant s, damping ratio) and ``solimp`` (dmin, dmax, width m): MuJoCo's soft
  contact model. A larger time constant and a wider, lower impedance make a softer contact that
  sinks in a little, like foam board. Keep the time constant >= 2 x the physics timestep (0.002 s).
* ``color``: default display color when a part gives none.

These are starting values, not measurements. Step 3 (calibration) tunes them against real videos.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    friction: float
    solref: tuple[float, float]
    solimp: tuple[float, float, float]
    color: str
    torsional: float = 0.005
    rolling: float = 0.0001


MATERIALS: dict[str, Material] = {
    # 5 mm foam board (Caduceus): compliant, sinks a few millimetres under load.
    "foam": Material(friction=1.0, solref=(0.025, 1.0), solimp=(0.70, 0.95, 0.004), color="#d9dde3"),
    # 3D-printed PLA: hard and a little slippery on wood.
    "pla": Material(friction=0.9, solref=(0.006, 1.0), solimp=(0.90, 0.97, 0.001), color="#4a90d9"),
    "wood": Material(friction=1.0, solref=(0.006, 1.0), solimp=(0.90, 0.97, 0.001), color="#b08a5a"),
    "metal": Material(friction=0.8, solref=(0.005, 1.0), solimp=(0.95, 0.99, 0.001), color="#9aa3ad"),
    # Rubber feet or tyres: grippy and slightly soft.
    "rubber": Material(friction=1.6, solref=(0.012, 0.8), solimp=(0.80, 0.95, 0.002), color="#333333"),
}


def names() -> list[str]:
    return sorted(MATERIALS)
