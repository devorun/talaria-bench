"""Design comparison: the same benchmark (same world seeds) for a robot and its variants.

A variant is a name plus overrides of the robot's spec, or a whole spec file:

* ``{"name": "legs +1.5 cm", "set": {"parts.left_leg.size.2": "+1.5", ...}}``. Values are absolute
  numbers/strings, or relative strings: ``"+1.5"``, ``"-2"``, ``"*1.2"``. ``parts.*`` matches every part
  (``parts.*.joint.servo`` sets the servo of every jointed part).
* ``{"name": "v2", "spec": "examples/robots/caduceus_v2.yaml"}``.
* Two whole-robot knobs for the Arena: ``"@scale": 1.3`` (every length times 1.3; explicit part masses follow
  the volume, x1.3^3) and ``"@mass_total": 400`` (every part mass scaled so the robot weighs 400 g; applied
  after ``@scale``, so it wins over the volume rule).

Every number is simulation.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Optional

import yaml

from .bench import run_benchmark
from .calibration import set_path
from .report import _fmt, build_report, status_for
from .spec import Spec, load_spec, parse_spec


def _relative(old: Any, value: Any) -> Any:
    if isinstance(value, str) and value[:1] in "+-*" and len(value) > 1:
        try:
            amount = float(value[1:])
        except ValueError:
            return value
        if not isinstance(old, (int, float)) or isinstance(old, bool):
            raise ValueError(f"cannot apply {value!r} to {old!r}")
        return round(old * amount if value[0] == "*" else old + (amount if value[0] == "+" else -amount), 6)
    return value


def _get(data: Any, keys: list[str]) -> Any:
    node = data
    for key in keys:
        if isinstance(node, list):
            if key.isdigit():
                node = node[int(key)]
            else:
                node = next(p for p in node if isinstance(p, dict) and p.get("name") == key)
        else:
            node = node[key]
    return node


SCALE_KEY = "@scale"
MASS_KEY = "@mass_total"
SCALE_RANGE = (0.4, 2.5)
MASS_RANGE_G = (5.0, 50_000.0)


def _number(key: str, value: Any, lo: float, hi: float) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a number") from None
    if not lo <= x <= hi:
        raise ValueError(f"{key} must be between {lo:g} and {hi:g}")
    return x


def apply_overrides(data: dict, overrides: dict[str, Any]) -> dict:
    """Raw spec data with ``overrides`` applied (paths as in calibration.set_path, plus ``parts.*`` and ``@scale``;
    ``@mass_total`` needs the parsed masses and is applied by build_variant)."""
    out = copy.deepcopy(data)
    overrides = dict(overrides)
    if MASS_KEY in overrides:
        _number(MASS_KEY, overrides.pop(MASS_KEY), *MASS_RANGE_G)
    if SCALE_KEY in overrides:
        from .templates import _scale

        k = _number(SCALE_KEY, overrides.pop(SCALE_KEY), *SCALE_RANGE)
        if abs(k - 1) > 1e-9:
            _scale(out, k)
            for part in out.get("parts", []):
                if isinstance(part.get("mass"), (int, float)) and not isinstance(part["mass"], bool):
                    part["mass"] = round(part["mass"] * k ** 3, 4)
    for path, value in overrides.items():
        keys = path.split(".")
        if keys[:2] == ["parts", "*"]:
            targets = [p["name"] for p in out["parts"] if len(keys) < 3 or keys[2] != "joint" or p.get("joint")]
            paths = [".".join(["parts", n] + keys[2:]) for n in targets]
        else:
            paths = [path]
        for p in paths:
            try:
                old = _get(out, p.split("."))
            except (KeyError, IndexError, StopIteration, TypeError):
                old = None
            new = _relative(old, value)
            if isinstance(old, dict) and isinstance(new, str):
                if not (p.endswith(".servo") and "model" in old):
                    raise ValueError(f"{p}: cannot replace a mapping with {new!r}")
                new = {**old, "model": new}     # another catalog servo, same measured backlash
            set_path_any(out, p, new)
    return out


def set_path_any(data: dict, path: str, value: Any) -> None:
    """Like calibration.set_path but for any value (strings and mappings too)."""
    keys = path.split(".")
    parent: Any = data
    for i, key in enumerate(keys[:-1]):            # walk down, creating missing mappings (e.g. bench)
        if isinstance(parent, dict) and key not in parent:
            parent[key] = [] if keys[i + 1].isdigit() else {}
        parent = _get(parent, [key])
    if isinstance(parent, list):
        parent[int(keys[-1])] = value
    elif isinstance(parent, dict):
        parent[keys[-1]] = value
    else:
        set_path(data, path, value)


def build_variant(spec: Spec, variant: dict[str, Any], base_dir: Optional[Path] = None) -> Spec:
    if variant.get("spec"):
        path = Path(variant["spec"])
        if not path.is_file() and base_dir is not None:
            path = base_dir / variant["spec"]
        return load_spec(path)
    if spec.source is None:
        raise ValueError("override variants need a spec loaded from a file")
    raw = yaml.safe_load(Path(spec.source).read_text(encoding="utf-8"))
    sets = variant.get("set") or {}
    data = apply_overrides(raw, sets)
    out = parse_spec(data, base_dir=Path(spec.source).parent)
    if MASS_KEY in sets:
        target = _number(MASS_KEY, sets[MASS_KEY], *MASS_RANGE_G)
        total = sum(p.mass for p in out.parts)
        if total > 0:
            masses = {p.name: p.mass * target / total for p in out.parts}
            for part in data["parts"]:
                if part.get("name") in masses:
                    part["mass"] = round(masses[part["name"]], 4)
            out = parse_spec(data, base_dir=Path(spec.source).parent)
    out.source = spec.source
    return out


def parse_variant_arg(text: str) -> dict[str, Any]:
    """CLI form ``name:path=value,path=value`` or ``name:file.yaml``."""
    name, _, rest = text.partition(":")
    if not rest:
        raise ValueError(f"variant {text!r}: use name:path=value,... or name:spec.yaml")
    if "=" not in rest:
        return {"name": name, "spec": rest}
    sets: dict[str, Any] = {}
    for item in rest.split(","):
        key, _, value = item.partition("=")
        v = value.strip()
        if v[:1] in "+-*":
            sets[key.strip()] = v            # relative: +1.5, -2, *1.2
        else:
            try:
                sets[key.strip()] = float(v)
            except ValueError:
                sets[key.strip()] = v        # a name, e.g. a servo model
    return {"name": name, "set": sets}


def load_variants_file(path: Path | str) -> list[dict[str, Any]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    items = data.get("variants") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError(f"{path}: expected a list of variants (or variants: [...])")
    return items


def compare(spec: Spec, variants: list[dict[str, Any]], scenes: Optional[list[str]] = None, worlds: int = 30,
            seed: int = 0, quick: bool = False, workers: Optional[int] = None, cache_dir: Any = "default",
            base_dir: Optional[Path] = None, progress=None) -> dict[str, Any]:
    """Benchmark the robot and every variant on the same worlds; side-by-side cards with deltas."""
    runs = [("base", spec, None)]
    for v in variants:
        runs.append((v["name"], build_variant(spec, v, base_dir), v))
    reports = {}
    outcomes: dict[str, dict[str, list[list]]] = {}
    for name, s, _ in runs:
        res = run_benchmark(s, scenes=scenes, worlds=worlds, seed=seed, quick=quick, workers=workers,
                            cache_dir=cache_dir, traces=False,
                            progress=(lambda d, t, sc, name=name: progress(name, d, t, sc)) if progress else None)
        reports[name] = build_report(res)
        outcomes[name] = {sid: [[j["seed"], bool(j.get("passed"))] for j in jobs] for sid, jobs in res["scenes"].items()}
    base = reports["base"]
    rows = []
    for card in base["scenes"]:
        sid = card["id"]
        # Per-world pass/fail of every design (same seeds), so a viewer can open a world where they differ.
        row = {"scene": sid, "title": card["title"], "cells": {},
               "outcomes": {name: outcomes.get(name, {}).get(sid, []) for name in reports}}
        for name, rep in reports.items():
            c = next(c for c in rep["scenes"] if c["id"] == sid)
            cell = {"status": c["status"], "pass_rate": c.get("pass_rate"),
                    "median": c.get("metric", {}).get("median") if c.get("applicable") else None,
                    "unit": c.get("metric", {}).get("unit") if c.get("applicable") else None}
            if name != "base" and cell["pass_rate"] is not None and card.get("pass_rate") is not None:
                cell["delta_pass"] = round(cell["pass_rate"] - card["pass_rate"], 3)
                cell["delta_median"] = round(cell["median"] - card["metric"]["median"], 3)
            row["cells"][name] = cell
        rows.append(row)
    return {"format": "talaria-bench/compare", "version": 1, "simulation": True,
            "robot": base["robot"]["name"], "settings": base["settings"],
            "variants": [{"name": n, **({"set": v.get("set")} if v and v.get("set") else {}),
                          **({"spec": v.get("spec")} if v and v.get("spec") else {})} for n, _, v in runs],
            "rows": rows, "reports": reports}


def to_markdown(result: dict) -> str:
    names = [v["name"] for v in result["variants"]]
    lines = [f"# Design comparison: {result['robot']} (simulation)", "",
             f"Same {result['settings']['worlds']} worlds per scene for every variant "
             f"(seeds {result['settings']['seed']}..). Pass rate and main metric median; delta vs base.", "",
             "| Scene | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for row in result["rows"]:
        cells = []
        for n in names:
            c = row["cells"][n]
            if c["pass_rate"] is None:
                cells.append("n/a")
                continue
            txt = f"{c['pass_rate'] * 100:.0f}% ({_fmt(c['median'], c['unit'])} {c['unit']})"
            if c["status"] == "out_of_scope":
                cells.append("OUT OF MODEL SCOPE")
                continue
            if "delta_pass" in c:
                txt += f" [{c['delta_pass'] * 100:+.0f} pts]"
            cells.append(txt)
        lines.append(f"| {row['title']} | " + " | ".join(cells) + " |")
    lines += ["", "Variants:"] + [f"- {v['name']}: " + (", ".join(f"{k} = {val}" for k, val in v.get("set", {}).items())
                                                      if v.get("set") else v.get("spec", "the robot as specified"))
                                  for v in result["variants"]]
    for name, rep in result["reports"].items():
        lines += ["", f"**{name}**: {rep['summary']}"]
    return "\n".join(lines) + "\n"


__all__ = ["apply_overrides", "build_variant", "compare", "parse_variant_arg", "load_variants_file", "status_for"]
