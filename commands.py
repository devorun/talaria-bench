"""``/talaria`` in any chat and ``hermes talaria`` in a terminal.

Both use the same tool handlers as the model, so the preflight gate applies to ``play`` here too.
Nothing here waits for a human: benchmarks run in the background and report a job id.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

from . import bridge, preflight
from .runtime import TOKEN_ENV, Runtime
from .tools import TalariaTools

SLASH_HELP = ("/talaria status | gallery | bench <robot> [--quick] | report <robot> | check <robot> <move> | "
              "play <robot> <move> [--real] | demo")
DEMO_ROBOT, DEMO_BENCH = "caduceus", "spider8"
DEMO_MOVES = ("arms_up_both", "arms_up_alternating")


def _call(tools: TalariaTools, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return json.loads(tools.handlers()[name](args))


def _err(data: dict[str, Any]) -> str:
    text = str(data.get("error"))
    if data.get("problems"):
        text += "\n" + "\n".join("  - " + p for p in data["problems"])
    if data.get("hint"):
        text += "\n" + data["hint"]
    return text


def _check_text(data: dict[str, Any]) -> str:
    if not data.get("ok"):
        return _err(data)
    lines = [data["summary"]]
    lines += ["  " + r for r in data.get("reasons") or []]
    lines += ["  Try: " + s for s in data.get("suggestions") or []]
    lines += ["  " + w for w in data.get("speed_limit_stretches") or []]
    lines.append("  " + data["label"])
    return "\n".join(lines)


def status_text(rt: Runtime, tools: TalariaTools) -> str:
    robots = _call(tools, "robot_list", {})
    jobs = tools.jobs.jobs()[:5]
    running = [j for j in jobs if j["status"] == "running"]
    url = rt.setting("robot_url") or "not set"
    lines = [f"Talaria Bench: {len(robots.get('robots', []))} robots, data in {rt.data_dir()}",
             f"Real robot: {rt.setting('real_robot')} at {url}" + (" (token set)" if rt.token() else ""),
             f"Virtual robots running: {', '.join(rt.virtual) or 'none'}",
             f"Jobs: {len(running)} running" + "".join(
                 f"\n  {j['id']} {j['kind']} {j['robot']}: {j['status']}" + _progress(j) for j in jobs)]
    return "\n".join(lines)


def _progress(job: dict[str, Any]) -> str:
    p = job.get("progress") or {}
    if job["status"] == "running" and p.get("total"):
        return f" ({p.get('done')}/{p.get('total')})"
    return ""


def gallery_text(tools: TalariaTools) -> str:
    data = _call(tools, "robot_list", {})
    return "\n".join(f"{r['name']:13s} {r['family'] or '-':10s} {r['servos']:2d} servos {r['mass_g']:5d} g  "
                     f"{r['source']}  moves: {', '.join(r['moves']) or '-'}" for r in data.get("robots", []))


def demo_text(rt: Runtime, tools: TalariaTools) -> str:
    lines = ["Talaria demo (simulation only, no hardware).", ""]
    bench = _call(tools, "bench_run", {"robot": DEMO_BENCH, "quick": True})
    if bench.get("ok"):
        lines.append(f"1. Quick benchmark of {DEMO_BENCH} started in the background: job {bench['job_id']} "
                     f"(follow with /talaria status, read with /talaria report {DEMO_BENCH}).")
    else:
        lines.append(f"1. Could not start the {DEMO_BENCH} benchmark: {_err(bench)}")
    lines += ["", f"2. Preflight of two {DEMO_ROBOT} moves, {preflight.DEFAULT_WORLDS} randomized worlds each:"]
    for move in DEMO_MOVES:
        lines.append(_check_text(_call(tools, "move_check", {"robot": DEMO_ROBOT, "move": move})))
    lines += ["", "3. The gate:"]
    for move in DEMO_MOVES:
        play = _call(tools, "robot_play", {"robot": DEMO_ROBOT, "move": move, "target": "virtual"})
        if play.get("ok"):
            lines.append(f"  {move}: played on the virtual {DEMO_ROBOT} ({play['duration_s']:.1f} s).")
        else:
            lines.append(f"  {move}: {play.get('error')}")
    return "\n".join(lines)


def slash_handler(rt: Runtime, tools: TalariaTools) -> Callable[..., str]:
    def handle(raw_args: str = "", **kwargs: Any) -> str:
        words = (raw_args or "").split()
        verb = words[0].lower() if words else "status"
        rest = [w for w in words[1:] if not w.startswith("--")]
        flags = {w for w in words[1:] if w.startswith("--")}
        try:
            if verb in ("help", "?"):
                return SLASH_HELP
            if verb == "status":
                return status_text(rt, tools)
            if verb == "gallery":
                return gallery_text(tools)
            if verb == "demo":
                return demo_text(rt, tools)
            if verb == "bench" and rest:
                data = _call(tools, "bench_run", {"robot": rest[0], "quick": "--quick" in flags})
                return (f"Benchmark of {rest[0]} started: job {data['job_id']} (/talaria status, then "
                        f"/talaria report {rest[0]})") if data.get("ok") else _err(data)
            if verb == "report" and rest:
                data = _call(tools, "bench_report", {"robot": rest[0]})
                return data["markdown"] if data.get("ok") else _err(data)
            if verb == "check" and len(rest) >= 2:
                return _check_text(_call(tools, "move_check", {"robot": rest[0], "move": rest[1],
                                                               "quick": "--quick" in flags}))
            if verb == "play" and len(rest) >= 2:
                target = "real" if "--real" in flags else "virtual"
                data = _call(tools, "robot_play", {"robot": rest[0], "move": rest[1], "target": target})
                if data.get("ok"):
                    return f"Playing {rest[1]} on the {target} {rest[0]} ({data['duration_s']:.1f} s)."
                return _err(data)
        except Exception as exc:   # a slash command must answer, not raise
            return f"talaria: {exc}"
        return "Usage: " + SLASH_HELP

    return handle


# ─── hermes talaria ... ─────────────────────────────────────────────────────────────────────────


def setup_cli(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="talaria_cmd")
    sub.add_parser("status", help="robots, jobs and the robot connection")
    sub.add_parser("gallery", help="list the robots")
    p = sub.add_parser("bench", help="run the test arena for a robot (waits and prints the report)")
    p.add_argument("robot")
    p.add_argument("--quick", action="store_true")
    p.add_argument("--worlds", type=int, default=None)
    p = sub.add_parser("report", help="print a robot's latest report")
    p.add_argument("robot")
    p = sub.add_parser("check", help="preflight a move")
    p.add_argument("robot")
    p.add_argument("move")
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--quick", action="store_true")
    p = sub.add_parser("play", help="play a checked move (virtual unless --real)")
    p.add_argument("robot")
    p.add_argument("move")
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--real", action="store_true")
    sub.add_parser("demo", help="quick spider benchmark + Caduceus preflight, no hardware")
    p = sub.add_parser("firmware", help="write the ESP32 firmware for a robot (with its robot_config.h)")
    p.add_argument("robot")
    p.add_argument("out_dir")
    p.add_argument("--new-token", action="store_true",
                   help="write a fresh random robot token even if Hermes already has one")
    p = sub.add_parser("sim", help="run a virtual robot with the firmware's HTTP API")
    p.add_argument("robot", nargs="?", default=None)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)


def cli_handler(rt: Runtime, tools: TalariaTools) -> Callable[[argparse.Namespace], int]:
    def handle(args: argparse.Namespace) -> int:
        cmd = getattr(args, "talaria_cmd", None) or "status"
        out = print
        if cmd == "status":
            out(status_text(rt, tools))
        elif cmd == "gallery":
            out(gallery_text(tools))
        elif cmd == "demo":
            out(demo_text(rt, tools))
            tools.shutdown()
        elif cmd == "report":
            data = _call(tools, "bench_report", {"robot": args.robot})
            out(data["markdown"] if data.get("ok") else _err(data))
            return 0 if data.get("ok") else 1
        elif cmd == "check":
            data = _call(tools, "move_check", {"robot": args.robot, "move": args.move, "speed": args.speed,
                                               "quick": args.quick})
            out(_check_text(data))
            return 0 if data.get("ok") and data.get("verdict") == "pass" else 1
        elif cmd == "play":
            target = "real" if args.real else "virtual"
            data = _call(tools, "robot_play", {"robot": args.robot, "move": args.move, "speed": args.speed,
                                               "target": target})
            if not data.get("ok"):
                out(_err(data))
                return 1
            out(f"Playing {args.move} on the {target} {args.robot} ({data['duration_s']:.1f} s).")
            if target == "virtual":
                time.sleep(data["duration_s"] + 0.2)
                state = _call(tools, "robot_status", {"robot": args.robot})
                out(f"Done; pose: {state.get('pose')}")
                tools.shutdown()
        elif cmd == "bench":
            return _bench_foreground(tools, args)
        elif cmd == "firmware":
            from .firmware import export_firmware, new_token
            existing = None if getattr(args, "new_token", False) else rt.token()
            token = existing or new_token()
            folder = export_firmware(rt.robot(args.robot), Path(args.out_dir), token)
            out(f"Firmware for {args.robot} written to {folder}")
            if existing:
                out(f"robot_config.h uses the robot token already stored in Hermes ({TOKEN_ENV}); pass --new-token "
                    "for a fresh one.")
            else:
                out(f"robot_config.h has a new random robot token: {token}")
                out("Store the same value in Hermes (Talaria Bench refuses to move the real robot without it):")
                out(f"  hermes config set {TOKEN_ENV} {token}")
                out("  (or Hermes Desktop: Settings > Plugins > Talaria Bench > Robot token)")
            out("Copy secrets.example.h to secrets.h and fill in the Wi-Fi, then build with the ESP32 core and the "
                "Adafruit PWM Servo Driver library.")
        elif cmd == "sim":
            spec = rt.robot(args.robot or str(rt.setting("real_robot")))
            return bridge.serve(spec, host=args.host, port=args.port, token=rt.token(), out=out)
        else:
            out(SLASH_HELP)
            return 2
        return 0

    return handle


def _bench_foreground(tools: TalariaTools, args: argparse.Namespace) -> int:
    data = _call(tools, "bench_run", {"robot": args.robot, "quick": args.quick, "worlds": args.worlds})
    if not data.get("ok"):
        print(_err(data))
        return 1
    job_id, last = data["job_id"], None
    print(f"Benchmark of {args.robot}: job {job_id}")
    while True:
        job = tools.jobs.job(job_id)
        p = job.get("progress") or {}
        now = (p.get("done"), p.get("total"))
        if p.get("total") and now != last:
            print(f"  {p['done']}/{p['total']}", file=sys.stderr, flush=True)
            last = now
        if job["status"] != "running":
            break
        time.sleep(1.0)
    if job["status"] != "done":
        print(f"The job {job['status']}:\n{job.get('log_tail', '')}")
        return 1
    print(Path(job["report"]).read_text(encoding="utf-8"))
    return 0
