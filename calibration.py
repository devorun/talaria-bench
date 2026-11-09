"""Calibration: find the model parameters under which a robot reproduces behaviours seen on video.

A calibration file (YAML, see ``examples/robots/caduceus.calibration.yaml``) names:

* ``spec``: the robot spec to start from (relative to the calibration file);
* ``parameters``: unknowns with plausible ranges, ``name: [low, high]``;
* ``apply``: spec fields set from the parameters, ``"parts.left_leg.joint.anchor.2": "gap - 6.5"``
  (dotted path: mapping keys, part names inside ``parts``, list indices; values are small arithmetic
  expressions of the parameters: numbers, names, + - * / **, parentheses, min, max, abs);
* ``world``: World fields set from the parameters, e.g. ``friction: friction`` or ``offsets_deg.left_leg: off_ll``;
* ``targets``: behaviours, each ``{move, speed?, seconds?, require: {metric: bound}}``. Bounds are
  ``{min, max, abs_min, abs_max}`` or ``false``/``true`` for ``fell``.

Metrics: ``fell``, ``forward_cm``, ``lateral_cm``, ``yaw_deg``, ``steady_cm``, ``max_tilt_deg``,
``max_tilt_change_deg``, ``max_load``, and per ground-contact part ``lift_cm.<part>`` (highest gap to the
floor), ``rise_cm.<part>`` (that minus the gap after settling) and ``contact_frac.<part>``.

``calibrate`` samples parameter sets (Latin hypercube), runs every target for each, and reports the
acceptance rate, per-parameter acceptance tables and the closest sets. Every number is simulation.
"""

from __future__ import annotations

import ast
import copy
import operator
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np

from .simrun import Result, run_move
from .spec import Spec, load_spec, parse_spec
from .worlds import World

METRICS = ("fell", "forward_cm", "lateral_cm", "yaw_deg", "steady_cm", "max_tilt_deg", "max_tilt_change_deg",
           "max_roll_change_deg", "max_pitch_change_deg", "max_load")
PART_METRICS = ("lift_cm", "rise_cm", "contact_frac")
BOUND_KEYS = {"min", "max", "abs_min", "abs_max"}
TOP_KEYS = {"spec", "description", "samples", "seed", "parameters", "apply", "world", "targets", "bins"}
TARGET_KEYS = {"move", "speed", "seconds", "require", "description"}
WORLD_FIELDS = {"friction", "mass_scale", "torque_scale", "kp_scale", "latency_s", "floor_tilt_deg",
                "floor_tilt_dir_deg", "tether_scale", "tether_dir_deg"}


class CalibrationError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("invalid calibration file:\n  - " + "\n  - ".join(self.problems))


# ─── Safe arithmetic ─────────────────────────────────────────────────────────────────────────────

_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.Pow: operator.pow}
_FUNCS = {"min": min, "max": max, "abs": abs}


def _check_expr(node: ast.AST, names: set[str]) -> None:
    if isinstance(node, ast.Expression):
        return _check_expr(node.body, names)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return None
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise ValueError(f"unknown name {node.id!r}")
        return None
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        _check_expr(node.left, names)
        return _check_expr(node.right, names)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return _check_expr(node.operand, names)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS
            and not node.keywords and node.args):
        for arg in node.args:
            _check_expr(arg, names)
        return None
    raise ValueError(f"not allowed in an expression: {ast.dump(node)[:40]}")


def compile_expr(text: Any, names: set[str]) -> ast.Expression:
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        text = repr(float(text))
    if not isinstance(text, str):
        raise ValueError("must be a number or an expression")
    tree = ast.parse(text, mode="eval")
    _check_expr(tree, names)
    return tree


def eval_expr(tree: ast.AST, env: Mapping[str, float]) -> float:
    if isinstance(tree, ast.Expression):
        return eval_expr(tree.body, env)
    if isinstance(tree, ast.Constant):
        return float(tree.value)
    if isinstance(tree, ast.Name):
        return float(env[tree.id])
    if isinstance(tree, ast.BinOp):
        return float(_BINOPS[type(tree.op)](eval_expr(tree.left, env), eval_expr(tree.right, env)))
    if isinstance(tree, ast.UnaryOp):
        v = eval_expr(tree.operand, env)
        return -v if isinstance(tree.op, ast.USub) else v
    if isinstance(tree, ast.Call):
        return float(_FUNCS[tree.func.id](*(eval_expr(a, env) for a in tree.args)))
    raise ValueError("bad expression")


# ─── Spec paths ──────────────────────────────────────────────────────────────────────────────────


def set_path(data: dict, path: str, value: float) -> None:
    """Set ``value`` at a dotted ``path`` in raw spec data. Inside ``parts`` a key selects a part by name;
    a catalog servo name becomes ``{model: <name>}`` when a field below it is set; a missing material
    override starts from the built-in material."""
    keys = path.split(".")
    node: Any = data
    for i, key in enumerate(keys[:-1]):
        nxt = keys[i + 1]
        if isinstance(node, list):
            if key.isdigit():
                node = node[int(key)]
                continue
            match = [p for p in node if isinstance(p, dict) and p.get("name") == key]
            if not match:
                raise KeyError(f"{path}: no part named {key!r}")
            node = match[0]
            continue
        if key not in node or node[key] is None:
            if keys[0] == "materials" and i == 1:
                from .materials import MATERIALS

                base = MATERIALS[key]
                node[key] = {"friction": base.friction, "solref": list(base.solref), "solimp": list(base.solimp)}
            else:
                node[key] = [] if nxt.isdigit() else {}
        elif isinstance(node[key], str) and not nxt.isdigit():
            node[key] = {"model": node[key]}
        elif isinstance(node[key], tuple):
            node[key] = list(node[key])
        node = node[key]
    last = keys[-1]
    if isinstance(node, list):
        index = int(last)
        node.extend([0.0] * (index + 1 - len(node)))
        node[index] = value
    else:
        node[last] = value


# ─── Config ──────────────────────────────────────────────────────────────────────────────────────


@dataclass
class Target:
    name: str
    move: str
    require: dict[str, Any]
    speed: Optional[ast.Expression] = None
    seconds: Optional[float] = None


@dataclass
class Config:
    path: Path
    spec_path: Path
    base: dict[str, Any]
    params: dict[str, tuple[float, float]]
    apply: dict[str, ast.Expression]
    world: dict[str, ast.Expression]
    targets: dict[str, Target]
    samples: int = 300
    seed: int = 0
    bins: int = 4
    description: str = ""
    raw_apply: dict[str, str] = field(default_factory=dict)


def load_config(path: str | Path) -> Config:
    import yaml

    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    if not isinstance(data, Mapping):
        raise CalibrationError(["the file must be a YAML mapping"])
    extra = set(data) - TOP_KEYS
    if extra:
        problems.append(f"unknown field(s) {', '.join(sorted(map(str, extra)))}")
    spec_path = path.parent / str(data.get("spec", ""))
    try:
        base = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        load_spec(spec_path)
    except Exception as exc:  # noqa: BLE001 - report any spec problem
        raise CalibrationError([f"spec {data.get('spec')!r}: {exc}"]) from None

    params: dict[str, tuple[float, float]] = {}
    for name, rng in (data.get("parameters") or {}).items():
        ok = isinstance(rng, (list, tuple)) and len(rng) == 2 and all(isinstance(v, (int, float)) for v in rng)
        if not ok or rng[0] > rng[1] or not str(name).isidentifier():
            problems.append(f"parameter {name!r}: must be an identifier with [low, high], low <= high")
            continue
        params[str(name)] = (float(rng[0]), float(rng[1]))
    if not params:
        problems.append("parameters: give at least one name: [low, high]")
    names = set(params)

    def exprs(section: str) -> dict[str, ast.Expression]:
        out = {}
        for key, text in (data.get(section) or {}).items():
            try:
                out[str(key)] = compile_expr(text, names)
            except (ValueError, SyntaxError) as exc:
                problems.append(f"{section} {key!r}: {exc}")
        return out

    apply = exprs("apply")
    world = exprs("world")
    for key in world:
        if key not in WORLD_FIELDS and not key.startswith("offsets_deg."):
            problems.append(f"world {key!r}: not a World field ({', '.join(sorted(WORLD_FIELDS))}, offsets_deg.<joint>)")

    targets: dict[str, Target] = {}
    for tname, t in (data.get("targets") or {}).items():
        where = f"target {tname!r}"
        if not isinstance(t, Mapping) or "move" not in t:
            problems.append(f"{where}: needs move and require")
            continue
        extra = set(t) - TARGET_KEYS
        if extra:
            problems.append(f"{where}: unknown field(s) {', '.join(sorted(extra))}")
        req = t.get("require") or {}
        for metric, bound in req.items():
            base_metric = metric.split(".")[0]
            if base_metric not in METRICS and base_metric not in PART_METRICS:
                problems.append(f"{where}: unknown metric {metric!r}")
            elif base_metric in PART_METRICS and "." not in metric:
                problems.append(f"{where}: {metric} needs a part, e.g. {metric}.left_leg")
            elif metric == "fell":
                if not isinstance(bound, bool):
                    problems.append(f"{where}: fell must be true or false")
            elif not isinstance(bound, Mapping) or not bound or set(bound) - BOUND_KEYS:
                problems.append(f"{where}: {metric} bound must use {', '.join(sorted(BOUND_KEYS))}")
        speed = None
        if "speed" in t:
            try:
                speed = compile_expr(t["speed"], names)
            except (ValueError, SyntaxError) as exc:
                problems.append(f"{where} speed: {exc}")
        targets[str(tname)] = Target(name=str(tname), move=str(t["move"]), require=dict(req), speed=speed,
                                     seconds=t.get("seconds"))
    if not targets:
        problems.append("targets: give at least one behaviour")
    if problems:
        raise CalibrationError(problems)
    return Config(path=path, spec_path=spec_path, base=base, params=params, apply=apply, world=world,
                  targets=targets, samples=int(data.get("samples", 300)), seed=int(data.get("seed", 0)),
                  bins=int(data.get("bins", 4)), description=str(data.get("description", "")),
                  raw_apply={k: str(v) for k, v in (data.get("apply") or {}).items()})


# ─── Running one parameter set ───────────────────────────────────────────────────────────────────


def build_sample(config: Config, values: Mapping[str, float]) -> tuple[Spec, World]:
    data = copy.deepcopy(config.base)
    for path, expr in config.apply.items():
        set_path(data, path, round(eval_expr(expr, values), 6))
    spec = parse_spec(data, base_dir=config.spec_path.parent)
    world = World.nominal()
    for key, expr in config.world.items():
        v = eval_expr(expr, values)
        if key.startswith("offsets_deg."):
            world.offsets_deg[key.split(".", 1)[1]] = v
        else:
            setattr(world, key, v)
    return spec, world


def metrics_of(r: Result) -> dict[str, float]:
    out: dict[str, float] = {
        "fell": r.fell, "forward_cm": r.forward_m * 100, "lateral_cm": r.lateral_m * 100, "yaw_deg": r.yaw_deg,
        "steady_cm": r.steady_m * 100, "max_tilt_deg": r.max_tilt_deg, "max_tilt_change_deg": r.max_tilt_change_deg,
        "max_roll_change_deg": r.max_roll_change_deg, "max_pitch_change_deg": r.max_pitch_change_deg,
        "max_load": r.max_load_ratio,
    }
    for name, g in r.ground.items():
        out[f"lift_cm.{name}"] = g.lift_cm
        out[f"rise_cm.{name}"] = g.lift_cm - g.start_cm
        out[f"contact_frac.{name}"] = g.contact_frac
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}


def violations(metrics: Mapping[str, Any], require: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every unmet requirement, with a normalized miss (0 = met) for ranking near misses."""
    out = []
    for metric, bound in require.items():
        value = metrics.get(metric)
        if metric == "fell":
            if bool(value) != bool(bound):
                out.append({"metric": metric, "value": value, "want": bound, "miss": 1.0})
            continue
        if value is None:
            out.append({"metric": metric, "value": None, "want": bound, "miss": 1.0})
            continue
        miss = 0.0
        scale = max(abs(float(x)) for x in bound.values()) or 1.0
        if "min" in bound and value < bound["min"]:
            miss += (bound["min"] - value) / scale
        if "max" in bound and value > bound["max"]:
            miss += (value - bound["max"]) / scale
        if "abs_min" in bound and abs(value) < bound["abs_min"]:
            miss += (bound["abs_min"] - abs(value)) / scale
        if "abs_max" in bound and abs(value) > bound["abs_max"]:
            miss += (abs(value) - bound["abs_max"]) / scale
        if miss > 0:
            out.append({"metric": metric, "value": value, "want": dict(bound), "miss": round(miss, 4)})
    return out


def run_targets(config: Config, spec: Spec, world: World, values: Mapping[str, float]) -> dict[str, Any]:
    results = {}
    for t in config.targets.values():
        speed = eval_expr(t.speed, values) if t.speed is not None else 1.0
        r = run_move(spec, t.move, world, t.seconds, speed=min(max(speed, 0.1), 4.0))
        m = metrics_of(r)
        v = violations(m, t.require)
        results[t.name] = {"ok": not v, "metrics": m, "violations": v, "fall_reason": r.fall_reason}
    return results


def evaluate(config: Config, values: Mapping[str, float]) -> dict[str, Any]:
    spec, world = build_sample(config, values)
    targets = run_targets(config, spec, world, values)
    miss = sum(x["miss"] for t in targets.values() for x in t["violations"])
    return {"values": dict(values), "targets": targets, "ok": all(t["ok"] for t in targets.values()),
            "miss": round(miss, 4)}


def latin_hypercube(n: int, params: Mapping[str, tuple[float, float]], seed: int) -> list[dict[str, float]]:
    rng = np.random.default_rng(seed)
    cols = {}
    for name, (lo, hi) in params.items():
        u = (rng.permutation(n) + rng.uniform(0, 1, n)) / n
        cols[name] = lo + u * (hi - lo)
    return [{name: round(float(cols[name][i]), 6) for name in params} for i in range(n)]


_WORKER_CONFIG: Optional[Config] = None


def _init_worker(path: str) -> None:
    global _WORKER_CONFIG
    _WORKER_CONFIG = load_config(path)


def _worker(values: dict[str, float]) -> dict[str, Any]:
    return evaluate(_WORKER_CONFIG, values)


def calibrate(config: Config, samples: Optional[int] = None, workers: int = 1, seed: Optional[int] = None,
              progress=None) -> dict[str, Any]:
    sets = latin_hypercube(samples or config.samples, config.params, config.seed if seed is None else seed)
    rows: list[dict[str, Any]] = []
    if workers > 1:
        from .procpool import pool as make_pool

        with make_pool(workers, "calibration", "_init_worker", str(config.path)) as pool:
            for i, row in enumerate(pool.map(_worker, sets, chunksize=4)):
                rows.append(row)
                if progress and (i + 1) % 50 == 0:
                    progress(i + 1, len(sets))
    else:
        for i, values in enumerate(sets):
            rows.append(evaluate(config, values))
            if progress and (i + 1) % 50 == 0:
                progress(i + 1, len(sets))
    return analyze(config, rows)


def analyze(config: Config, rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    accepted = [r for r in rows if r["ok"]]
    per_target = {t: round(sum(r["targets"][t]["ok"] for r in rows) / max(n, 1), 4) for t in config.targets}
    tables = {}
    for name, (lo, hi) in config.params.items():
        edges = np.linspace(lo, hi, config.bins + 1)
        bins = []
        for b in range(config.bins):
            inside = [r for r in rows if edges[b] <= r["values"][name] <= edges[b + 1]
                      and (b == config.bins - 1 or r["values"][name] < edges[b + 1])]
            k = len(inside)
            bins.append({"range": [round(float(edges[b]), 4), round(float(edges[b + 1]), 4)], "n": k,
                         "accept": round(sum(r["ok"] for r in inside) / k, 3) if k else None,
                         **{t: (round(sum(r["targets"][t]["ok"] for r in inside) / k, 3) if k else None)
                            for t in config.targets}})
        rates = [b["accept"] for b in bins if b["accept"] is not None]
        tables[name] = {"bins": bins, "spread": round(max(rates) - min(rates), 3) if rates else 0.0}
    ranking = sorted(tables, key=lambda k: -tables[k]["spread"])
    stats = {}
    if accepted:
        for name in config.params:
            vals = np.array([r["values"][name] for r in accepted])
            stats[name] = {"median": round(float(np.median(vals)), 4), "p10": round(float(np.percentile(vals, 10)), 4),
                           "p90": round(float(np.percentile(vals, 90)), 4), "min": round(float(vals.min()), 4),
                           "max": round(float(vals.max()), 4)}
    central = None
    if accepted:
        spans = {k: (hi - lo) or 1.0 for k, (lo, hi) in config.params.items()}

        def dist(r):
            return sum(((r["values"][k] - stats[k]["median"]) / spans[k]) ** 2 for k in config.params)

        central = min(accepted, key=dist)
    closest = sorted(rows, key=lambda r: r["miss"])[:5]
    return {"samples": n, "accepted": len(accepted), "acceptance_rate": round(len(accepted) / max(n, 1), 4),
            "per_target_pass": per_target, "parameter_tables": tables, "deciding_parameters": ranking,
            "accepted_stats": stats, "central_accepted": central, "closest": closest, "rows": rows}


# ─── Checking a finished spec in its own random worlds ───────────────────────────────────────────


def validate(config: Config, spec: Spec, worlds: int = 100, seed: int = 1000,
             speed_values: Optional[Mapping[str, float]] = None) -> dict[str, Any]:
    """Run every target in ``worlds`` fresh random worlds drawn from the spec's own ranges."""
    out = {}
    for t in config.targets.values():
        speed = eval_expr(t.speed, speed_values or {}) if t.speed is not None else 1.0
        rows = []
        for s in range(seed, seed + worlds):
            world = World.random(s, spec.joint_names, spec.world_ranges)
            r = run_move(spec, t.move, world, t.seconds, speed=min(max(speed, 0.1), 4.0))
            m = metrics_of(r)
            rows.append({"metrics": m, "violations": violations(m, t.require)})
        keys = [k for k in rows[0]["metrics"] if k != "fell"]
        dist = {k: {q: round(float(np.percentile([r["metrics"][k] for r in rows], p)), 3)
                    for q, p in (("p10", 10), ("median", 50), ("p90", 90))} for k in keys}
        failed: dict[str, int] = {}
        for r in rows:
            for v in r["violations"]:
                failed[v["metric"]] = failed.get(v["metric"], 0) + 1
        out[t.name] = {"worlds": worlds, "pass_rate": round(sum(not r["violations"] for r in rows) / worlds, 3),
                       "falls": sum(bool(r["metrics"]["fell"]) for r in rows), "failed_requirements": failed,
                       "distributions": dist}
    return out


def default_workers() -> int:
    return max(1, min(8, (os.cpu_count() or 2) - 1))
