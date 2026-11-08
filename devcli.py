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


def cmd_calibrate(args) -> int:
    load_package()
    from talaria_bench.calibration import calibrate, default_workers, load_config

    config = load_config(find_spec_file(args.config))
    workers = args.workers or default_workers()
    n = args.samples or config.samples
    print(f"[simulation] calibrating {config.spec_path.name}: {n} parameter sets x {len(config.targets)} targets, "
          f"{workers} workers")
    t0 = time.perf_counter()
    report = calibrate(config, samples=n, workers=workers, seed=args.seed,
                       progress=lambda i, k: print(f"  {i}/{k} ({time.perf_counter() - t0:.0f} s)", flush=True))
    print(f"accepted {report['accepted']}/{report['samples']} ({report['acceptance_rate'] * 100:.1f}%); "
          f"per target: " + ", ".join(f"{t} {v * 100:.0f}%" for t, v in report["per_target_pass"].items()))
    targets = list(config.targets)
    print("\nparameters by how much they decide acceptance (accept rate per quarter of the range):")
    for name in report["deciding_parameters"]:
        tab = report["parameter_tables"][name]
        cells = " | ".join(
            f"{b['range'][0]:g}..{b['range'][1]:g}: {'-' if b['accept'] is None else f'{b['accept'] * 100:.0f}%'}"
            f" ({'/'.join('-' if b[t] is None else f'{b[t] * 100:.0f}' for t in targets)})" for b in tab["bins"])
        print(f"  {name:20s} spread {tab['spread'] * 100:4.0f}%  {cells}")
    print(f"  (in brackets: pass % of {' / '.join(targets)})")
    if report["accepted_stats"]:
        print("\naccepted sets: median [p10, p90]")
        for name, s in report["accepted_stats"].items():
            print(f"  {name:20s} {s['median']:9.4g} [{s['p10']:.4g}, {s['p90']:.4g}]")
        c = report["central_accepted"]
        print("\nmost central accepted set:", json.dumps(c["values"]))
        for t, res in c["targets"].items():
            print(f"  {t}: " + json.dumps(res["metrics"]))
    print("\nclosest sets:")
    for row in report["closest"][:3]:
        print(f"  miss {row['miss']:.3f}: " + "; ".join(f"{t}: " + (", ".join(
            f"{v['metric']}={v['value']}" for v in res["violations"]) or "ok") for t, res in row["targets"].items()))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(f"\nfull report -> {args.out}")
    print(f"({time.perf_counter() - t0:.0f} s wall)")
    return 0


def cmd_validate(args) -> int:
    load_package()
    from talaria_bench.calibration import load_config, validate
    from talaria_bench.spec import load_spec

    config = load_config(find_spec_file(args.config))
    spec = load_spec(find_spec_file(args.spec) if args.spec else config.spec_path)
    values = {k: (lo + hi) / 2 for k, (lo, hi) in config.params.items()}
    for item in args.param or []:
        key, _, val = item.partition("=")
        values[key] = float(val)
    print(f"[simulation] validating {spec.name} (spec {spec.hash()[:12]}) in {args.worlds} fresh worlds "
          f"(seeds {args.seed}..{args.seed + args.worlds - 1}) from its own world ranges")
    out = validate(config, spec, worlds=args.worlds, seed=args.seed, speed_values=values)
    print(json.dumps(out, indent=1))
    return 0


def _bench_progress(prefix: str = ""):
    state = {"last": -1}

    def cb(done: int, total: int, scene: str) -> None:
        step = max(1, total // 10)
        if done == total or done // step != state["last"]:
            state["last"] = done // step
            print(f"  {prefix}{done}/{total} ({scene})", file=sys.stderr, flush=True)
    return cb


def cmd_bench(args) -> int:
    load_package()
    from talaria_bench.bench import run_benchmark, save_results
    from talaria_bench.report import build_report, to_markdown
    from talaria_bench.spec import load_spec

    spec = load_spec(find_spec_file(args.spec))
    results = run_benchmark(spec, scenes=args.scenes, worlds=args.worlds, seed=args.seed, quick=args.quick,
                            workers=args.workers or None, cache_dir=None if args.no_cache else "default",
                            progress=_bench_progress(), progress_file=args.progress_file)
    report = build_report(results)
    out = Path(args.out) if args.out else Path(f"{spec.name}-bench.json")
    save_results(results, out)
    out.with_suffix(".report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    md = to_markdown(report)
    out.with_suffix(".report.md").write_text(md, encoding="utf-8")
    print(md)
    t = results["timing"]
    print(f"results -> {out} (+ .report.json, .report.md); {t['jobs']} jobs, {t['computed']} computed, "
          f"{t['cached']} cached, {t['workers']} workers, {t['seconds_total']:.1f} s")
    return 0


def cmd_report(args) -> int:
    load_package()
    from talaria_bench.bench import load_results
    from talaria_bench.report import build_report, to_markdown

    report = build_report(load_results(args.results))
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        print(to_markdown(report))
    return 0


def cmd_compare(args) -> int:
    load_package()
    from talaria_bench.compare import compare, load_variants_file, parse_variant_arg, to_markdown
    from talaria_bench.spec import load_spec

    spec_path = find_spec_file(args.spec)
    spec = load_spec(spec_path)
    variants = []
    base_dir = None
    if args.variants:
        vfile = find_spec_file(args.variants)
        variants += load_variants_file(vfile)
        base_dir = vfile.parent
    variants += [parse_variant_arg(v) for v in args.variant or []]
    if not variants:
        raise SystemExit("give --variant name:path=value,... or --variants file.yaml")
    t0 = time.perf_counter()
    result = compare(spec, variants, scenes=args.scenes, worlds=args.worlds, seed=args.seed, quick=args.quick,
                     workers=args.workers or None, cache_dir=None if args.no_cache else "default", base_dir=base_dir,
                     progress=lambda name, d, t, sc: _bench_progress(f"{name}: ")(d, t, sc))
    md = to_markdown(result)
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1), encoding="utf-8")
        Path(args.out).with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)
    print(f"({time.perf_counter() - t0:.1f} s wall)")
    return 0


def gallery_rows() -> list[dict]:
    """Every bundled example robot with its metadata and, when saved, its report headline."""
    load_package()
    from talaria_bench.spec import load_spec

    rows = []
    for path in sorted((PLUGIN_ROOT / "examples" / "robots").glob("*.yaml")):
        if ".calibration" in path.name:
            continue
        spec = load_spec(path)
        rep_path = PLUGIN_ROOT / "examples" / "reports" / f"{spec.name}.report.json"
        headline = ""
        if rep_path.is_file():
            rep = json.loads(rep_path.read_text(encoding="utf-8"))
            cards = [c for c in rep["scenes"] if c.get("applicable")]
            colours = {}
            for c in cards:
                colours[c["status"]] = colours.get(c["status"], 0) + 1
            counts = ", ".join(f"{n} {k}" for k, n in sorted(colours.items()))
            sentences = [s.strip().rstrip(".") for s in rep["summary"].split(". ") if s.strip()]
            pick = None
            for key in ("Max safe payload", "tips the robot in", "Walks well", "Walks on", "Struggles"):
                pick = next((s for s in sentences if key in s), None)
                if pick:
                    break
            pick = pick or next((s for s in sentences if not s.startswith("Walking scenes")), "")
            headline = (pick + ". " if pick else "") + f"[{counts}]"
        rows.append({"name": spec.name, "title": spec.title, "family": spec.family or "-",
                     "servos": len(spec.joint_parts), "mass_g": round(spec.total_mass_g), "base": spec.base,
                     "role": spec.role or spec.description, "headline": headline})
    return rows


def cmd_gallery(args) -> int:
    rows = gallery_rows()
    if args.markdown:
        print("| Robot | Family | Servos | Mass | Role | Benchmark headline (simulation) |")
        print("|---|---|---|---|---|---|")
        for r in rows:
            base = " (fixed base)" if r["base"] == "fixed" else ""
            print(f"| `{r['name']}` {r['title']}{base} | {r['family']} | {r['servos']} | {r['mass_g']} g | "
                  f"{r['role']} | {r['headline'] or '-'} |")
    else:
        for r in rows:
            print(f"{r['name']:14s} {r['family']:10s} {r['servos']:2d} servos {r['mass_g']:5d} g  {r['base']:5s}  {r['role']}")
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
    p = sub.add_parser("calibrate", help="sample model parameters against behaviour targets")
    p.add_argument("config", help="calibration YAML, e.g. examples/robots/caduceus.calibration.yaml")
    p.add_argument("--samples", type=int, default=None)
    p.add_argument("--workers", type=int, default=0)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--out", default=None, help="write the full JSON report here")
    p.set_defaults(fn=cmd_calibrate)
    p = sub.add_parser("validate", help="check the targets in fresh random worlds from the spec's ranges")
    p.add_argument("config")
    p.add_argument("--spec", default=None, help="spec to check (default: the one in the calibration file)")
    p.add_argument("--worlds", type=int, default=100)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--param", action="append", help="name=value for parameters used in target speeds")
    p.set_defaults(fn=cmd_validate)

    def bench_args(p):
        p.add_argument("--scenes", nargs="*", default=None, help="scene ids or families (default: all)")
        p.add_argument("--worlds", type=int, default=30)
        p.add_argument("--seed", type=int, default=0)
        p.add_argument("--quick", action="store_true", help="10 worlds")
        p.add_argument("--workers", type=int, default=0)
        p.add_argument("--no-cache", action="store_true")

    p = sub.add_parser("bench", help="run the test arena and print the report card")
    p.add_argument("spec")
    bench_args(p)
    p.add_argument("--out", default=None, help="results JSON (default <robot>-bench.json)")
    p.add_argument("--progress-file", default=None)
    p.set_defaults(fn=cmd_bench)
    p = sub.add_parser("report", help="print the report card of a results JSON")
    p.add_argument("results")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("compare", help="benchmark design variants side by side")
    p.add_argument("spec")
    p.add_argument("--variant", action="append", help="name:path=value,... (relative +x -x *x) or name:spec.yaml")
    p.add_argument("--variants", default=None, help="YAML file with a list of variants")
    p.add_argument("--out", default=None)
    bench_args(p)
    p.set_defaults(fn=cmd_compare)
    p = sub.add_parser("gallery", help="list the bundled example robots")
    p.add_argument("--markdown", action="store_true", help="a Markdown table with benchmark headlines")
    p.set_defaults(fn=cmd_gallery)
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
