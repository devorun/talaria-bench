"""Developer CLI for Talaria Bench (no Hermes needed).

    python talaria-bench/devcli.py info examples/robots/spider8.yaml
    python talaria-bench/devcli.py run examples/robots/spider8.yaml --move walk --seconds 8 [--seed N] [--worlds 20]
    python talaria-bench/devcli.py mjcf examples/robots/caduceus.yaml > caduceus.xml

Spec paths are tried as given, then relative to the plugin folder. Without ``--worlds`` the move runs
once in the nominal world; with ``--worlds N`` it runs in N random worlds (seeds seed .. seed+N-1).
All results are simulation results.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent
PACKAGE = "talaria_bench"


def load_package():
    """Import the plugin folder (its name has a dash) as the package ``talaria_bench``."""
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(PACKAGE, PLUGIN_ROOT / "__init__.py",
                                                      submodule_search_locations=[str(PLUGIN_ROOT)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = module
        spec.loader.exec_module(module)
    return sys.modules[PACKAGE]


def find_spec_file(path: str) -> Path:
    p = Path(path)
    if p.is_file():
        return p
    alt = PLUGIN_ROOT / path
    if alt.is_file():
        return alt
    raise SystemExit(f"spec not found: {path} (also looked in {PLUGIN_ROOT})")


def _fmt_result(r) -> str:
    status = f"FELL at {r.fell_at_s:.2f} s: {r.fall_reason}" if r.fell else "no fall"
    worst = max(r.joints.items(), key=lambda kv: kv[1].peak_ratio) if r.joints else None
    load = f"{worst[0]} {worst[1].peak_ratio * 100:.0f}% of stall (sat {worst[1].saturated_frac * 100:.0f}%)" if worst else "-"
    return (f"forward {r.forward_m * 100:6.2f} cm | steady {r.steady_m * 100:6.2f} cm | lateral {r.lateral_m * 100:6.2f} cm"
            f" | yaw {r.yaw_deg:6.1f} deg | max tilt {r.max_tilt_deg:5.1f} deg | peak load {load}"
            f" | self-collisions {r.self_collisions} | {status}")


def cmd_info(args) -> int:
    load_package()
    from talaria_bench.builder import build_mjcf
    from talaria_bench.spec import load_spec

    spec = load_spec(find_spec_file(args.spec))
    _, info = build_mjcf(spec)
    print(json.dumps({**spec.summary(), "root_height_cm": round(info.root_z * 100, 2),
                      "excluded_pairs": info.excluded_pairs, "build_warnings": info.warnings}, indent=2))
    return 0


def cmd_mjcf(args) -> int:
    load_package()
    from talaria_bench.builder import build_mjcf
    from talaria_bench.spec import load_spec

    xml, info = build_mjcf(load_spec(find_spec_file(args.spec)))
    print(xml)
    for w in info.warnings:
        print(f"<!-- warning: {w} -->")
    return 0


def cmd_run(args) -> int:
    load_package()
    from talaria_bench.simrun import run_move, run_worlds, summarize
    from talaria_bench.spec import load_spec
    from talaria_bench.worlds import World

    spec = load_spec(find_spec_file(args.spec))
    move = args.move
    repeat = True if args.repeat else None
    print(f"[simulation] robot {spec.name} ({spec.total_mass_g:.0f} g, spec {spec.hash()[:12]}), "
          f"move {move or 'hold'}, {args.seconds if args.seconds else 'auto'} s")
    t0 = time.perf_counter()
    if not args.worlds:
        world = World.random(args.seed, spec.joint_names, spec.world_ranges) if args.seed is not None else None
        r = run_move(spec, move, world, args.seconds, record=bool(args.trace), repeat=repeat)
        print(("nominal world: " if world is None else f"world seed {args.seed}: ") + _fmt_result(r))
        for w in r.warnings:
            print(f"  warning: {w}")
        if args.json:
            print(json.dumps(r.to_dict(), indent=2))
        if args.trace:
            Path(args.trace).write_text(json.dumps(r.trace), encoding="utf-8")
            print(f"trace: {len(r.trace['frames'])} frames -> {args.trace}")
    else:
        seed = args.seed or 0
        results = run_worlds(spec, move, args.seconds, list(range(seed, seed + args.worlds)), repeat=repeat)
        if args.verbose:
            for s, r in zip(range(seed, seed + args.worlds), results):
                print(f"  seed {s:3d}: " + _fmt_result(r))
        print(json.dumps(summarize(results), indent=2))
    print(f"({time.perf_counter() - t0:.1f} s wall)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="devcli.py", description="Talaria Bench developer CLI (simulation only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info", help="validate a spec and print a summary")
    p.add_argument("spec")
    p.set_defaults(fn=cmd_info)
    p = sub.add_parser("mjcf", help="print the generated MuJoCo XML")
    p.add_argument("spec")
    p.set_defaults(fn=cmd_mjcf)
    p = sub.add_parser("run", help="simulate a move and print metrics")
    p.add_argument("spec")
    p.add_argument("--move", default=None, help="move name from the spec (default: hold the home pose)")
    p.add_argument("--seconds", type=float, default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--worlds", type=int, default=0, help="run in N random worlds and summarize")
    p.add_argument("--repeat", action="store_true", help="loop the move until the time ends")
    p.add_argument("--trace", default=None, help="write a 3D trace JSON here (single run only)")
    p.add_argument("--json", action="store_true", help="print the full result as JSON (single run only)")
    p.add_argument("-v", "--verbose", action="store_true", help="print every world")
    p.set_defaults(fn=cmd_run)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except Exception as exc:  # human-readable errors for spec problems
        from talaria_bench.spec import SpecError

        if isinstance(exc, (SpecError, KeyError)):
            print(f"error: {exc}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
