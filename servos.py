"""Hobby servo catalog: stall torque and no-load speed at a few supply voltages, gear backlash, mass.

Numbers are typical datasheet values, rounded. They are estimates, not measurements of any one servo:

* Stall torque is the torque at which the servo stops moving. It is NOT a safe continuous torque.
  A hobby servo held near stall overheats within seconds to minutes. The simulator uses stall torque
  as the actuator's force limit, so any load it reports is an *estimate* of how close a move gets to
  what the servo can do at all, not a guarantee that the servo survives it.
* Speed is the no-load time for 60 degrees. Under load the servo is slower.
* Backlash is the free play at the output horn, a typical value for the gear type.

Values between catalog voltages are linearly interpolated; outside the range they are clamped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

KGCM_TO_NM = 0.0980665  # 1 kg*cm = 0.0980665 N*m
DEFAULT_VOLTAGE = 5.0


class ServoError(ValueError):
    pass


@dataclass(frozen=True)
class ServoModel:
    name: str
    #: (volts, stall torque kg*cm, no-load seconds per 60 degrees), sorted by volts
    points: tuple[tuple[float, float, float], ...]
    backlash_deg: float
    mass_g: float
    armature: float = 1.5e-4   # reflected rotor inertia at the output (kg*m^2), rough
    note: str = ""

    def torque_kgcm(self, volts: float = DEFAULT_VOLTAGE) -> float:
        return _interp(self.points, volts, 1)

    def torque_nm(self, volts: float = DEFAULT_VOLTAGE) -> float:
        return self.torque_kgcm(volts) * KGCM_TO_NM

    def s_per_60(self, volts: float = DEFAULT_VOLTAGE) -> float:
        return _interp(self.points, volts, 2)

    def speed_dps(self, volts: float = DEFAULT_VOLTAGE) -> float:
        """No-load speed in degrees per second."""
        return 60.0 / self.s_per_60(volts)

    def summary(self, volts: float = DEFAULT_VOLTAGE) -> dict[str, Any]:
        return {"name": self.name, "volts": volts, "stall_torque_kgcm": round(self.torque_kgcm(volts), 3),
                "speed_s_per_60": round(self.s_per_60(volts), 4), "backlash_deg": self.backlash_deg,
                "mass_g": self.mass_g}


def _interp(points: tuple[tuple[float, float, float], ...], volts: float, column: int) -> float:
    if volts <= points[0][0]:
        return points[0][column]
    if volts >= points[-1][0]:
        return points[-1][column]
    for lo, hi in zip(points, points[1:]):
        if lo[0] <= volts <= hi[0]:
            t = (volts - lo[0]) / (hi[0] - lo[0])
            return lo[column] + t * (hi[column] - lo[column])
    return points[-1][column]  # unreachable


CATALOG: dict[str, ServoModel] = {
    "SG90": ServoModel("SG90", ((4.8, 1.8, 0.10), (6.0, 2.2, 0.08)), backlash_deg=2.0, mass_g=9.0,
                       armature=1.2e-4, note="9 g micro servo, plastic gears"),
    "MG90S": ServoModel("MG90S", ((4.8, 1.8, 0.10), (6.0, 2.2, 0.08)), backlash_deg=1.0, mass_g=13.4,
                        armature=1.5e-4, note="13 g micro servo, metal gears"),
    "MG996R": ServoModel("MG996R", ((4.8, 9.4, 0.17), (6.0, 11.0, 0.14)), backlash_deg=1.0, mass_g=55.0,
                         armature=1.0e-3, note="standard size, metal gears"),
    "DS3218": ServoModel("DS3218", ((5.0, 19.0, 0.16), (6.8, 21.5, 0.14)), backlash_deg=0.5, mass_g=60.0,
                         armature=1.5e-3, note="standard size, 20 kg class, metal gears"),
}

_INLINE_KEYS = {"torque_kgcm", "speed_s_per_60", "backlash_deg", "mass_g"}


def names() -> list[str]:
    return sorted(CATALOG)


def lookup(name: str) -> ServoModel:
    key = str(name).strip().upper()
    for model in CATALOG.values():
        if model.name.upper() == key:
            return model
    raise ServoError(f"unknown servo {name!r} (catalog: {', '.join(names())}; or give "
                     "{torque_kgcm, speed_s_per_60, backlash_deg})")


def resolve(value: Any, where: str = "servo") -> ServoModel:
    """A catalog name or an inline ``{torque_kgcm, speed_s_per_60, backlash_deg[, mass_g]}`` mapping."""
    if isinstance(value, str):
        try:
            return lookup(value)
        except ServoError as exc:
            raise ServoError(f"{where}: {exc}") from None
    if isinstance(value, Mapping):
        unknown = set(value) - _INLINE_KEYS
        if unknown:
            raise ServoError(f"{where}: unknown field(s) {', '.join(sorted(map(str, unknown)))} "
                             f"(use {', '.join(sorted(_INLINE_KEYS))})")
        try:
            torque = float(value["torque_kgcm"])
            speed = float(value["speed_s_per_60"])
            backlash = float(value.get("backlash_deg", 1.0))
            mass = float(value.get("mass_g", 0.0))
        except KeyError as exc:
            raise ServoError(f"{where}: inline servo needs {exc.args[0]}") from None
        except (TypeError, ValueError):
            raise ServoError(f"{where}: inline servo values must be numbers") from None
        if torque <= 0 or speed <= 0 or backlash < 0 or mass < 0:
            raise ServoError(f"{where}: torque and speed must be > 0, backlash and mass >= 0")
        return ServoModel("custom", ((DEFAULT_VOLTAGE, torque, speed),), backlash_deg=backlash, mass_g=mass)
    raise ServoError(f"{where}: give a catalog name ({', '.join(names())}) or an inline mapping")
