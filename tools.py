"""Tool handlers. Each returns a JSON string and never raises: problems come back as
``{"ok": false, "error": ..., "problems": [...]}`` that the model can act on."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from . import bridge, preflight
from .hooks import block_reason, requested_move
from .jobs import JobManager
from .motion import MoveError, check_move
from .runtime import EXAMPLE_REPORTS, Runtime
from .spec import SpecError

logger = logging.getLogger(__name__)

REPORT_CHARS = 12000
SIM_NOTE = "Simulation results: risk screening, not a guarantee of how the real robot behaves."


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _guarded(fn: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[..., str]:
    def handler(args: Optional[dict[str, Any]] = None, **kwargs: Any) -> str:
        try:
            return _dump(fn(args or {}))
        except MoveError as exc:
            return _dump({"ok": False, "error": "the move cannot be played as written", "problems": exc.problems})
        except SpecError as exc:
            return _dump({"ok": False, "error": "the robot spec is not valid",
                          "problems": getattr(exc, "problems", [str(exc)])})
        except bridge.RobotUnreachable as exc:
            return _dump({"ok": False, "error": str(exc),
                          "hint": "The robot did not answer: it may be off, on another network or at another "
                                  "address (robot_url setting). target 'virtual' works without hardware."})
        except (bridge.RobotError, KeyError, ValueError) as exc:
            return _dump({"ok": False, "error": str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc)})
        except Exception as exc:  # a tool must never raise into the agent loop
            logger.exception("talaria-bench: %s failed", getattr(fn, "__name__", "tool"))
            return _dump({"ok": False, "error": f"unexpected error: {exc}"})

    handler.__name__ = getattr(fn, "__name__", "handler")
    return handler


def _headline(robot: str) -> Optional[str]:
    path = EXAMPLE_REPORTS / f"{robot}.report.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("summary")
    except (OSError, ValueError):
        return None


class TalariaTools:
    def __init__(self, runtime: Runtime, jobs: Optional[JobManager] = None):
        self.rt = runtime
        self.jobs = jobs or JobManager(runtime)

    def handlers(self) -> dict[str, Callable[..., str]]:
        return {name: _guarded(getattr(self, name)) for name in (
            "robot_list", "robot_define", "robot_show", "bench_run", "bench_status", "bench_report",
            "bench_compare", "move_check", "move_save", "move_list", "robot_play", "robot_pose", "robot_stop",
            "robot_status")}

    # Robots ---------------------------------------------------------------------------------------

    def robot_list(self, args: dict[str, Any]) -> dict[str, Any]:
        robots, broken = [], []
        for name, (path, kind) in self.rt.robot_paths().items():
            try:
                spec = self.rt.robot(name)
            except SpecError as exc:
                broken.append({"name": name, "problems": getattr(exc, "problems", [str(exc)])})
                continue
            robots.append({"name": name, "title": spec.title, "source": kind, "family": spec.family or None,
                           "servos": len(spec.joint_parts), "mass_g": round(spec.total_mass_g), "base": spec.base,
                           "moves": list(self.rt.all_moves(spec))})
        return {"ok": True, "robots": robots, **({"invalid": broken} if broken else {})}

    def robot_define(self, args: dict[str, Any]) -> dict[str, Any]:
        """A robot from a template + params (the reliable path) or full spec YAML, optionally with a photo."""
        import yaml

        from . import templates

        template, text, photo = args.get("template"), args.get("spec_yaml"), args.get("photo_path")
        notes: list[str] = []
        if template:
            params = args.get("params") or {}
            if not isinstance(params, dict):
                raise ValueError("params must be an object of template parameters")
            raw, notes = templates.build(str(template), params)
        elif isinstance(text, str) and text.strip():
            if len(text) > 200_000:
                raise ValueError("spec_yaml is too long (200 kB at most)")
            try:
                raw = yaml.safe_load(text)
            except yaml.YAMLError as exc:
                raise SpecError([f"not valid YAML: {getattr(exc, 'problem', None) or exc}"]) from None
            if not isinstance(raw, dict):
                raise SpecError(["the spec must be a YAML mapping (talaria: 1, name: ..., parts: [...])"])
        else:
            raise ValueError("give template + params (preferred) or spec_yaml")
        name = str(raw.get("name") or "")
        bundled = {n for n, (_, kind) in self.rt.robot_paths().items() if kind == "bundled"}
        if name in bundled:
            raise SpecError([f"name {name!r} belongs to a bundled robot; choose another name"])
        photo_rel = self.rt.photo_from_path(name, photo) if photo else None
        spec, path = self.rt.define_robot_data(raw, photo_rel)
        return {"ok": True, "robot": spec.name, "template": template, "summary": spec.summary(),
                "estimates_and_notes": notes, "photo": photo_rel, "warnings": spec.warnings,
                "next": (f"Tell the user to open Talaria Bench → Robot → {spec.name} to see the 3D model"
                         + (" next to the photo" if photo_rel else "") + ", and ask what to correct; then offer "
                         f"bench_run robot={spec.name} quick=true and a move_check.")}

    def robot_show(self, args: dict[str, Any]) -> dict[str, Any]:
        spec = self.rt.robot(str(args.get("robot")))
        joints = [{"name": n, **{k: j[k] for k in ("min", "max", "home", "max_speed")},
                   "servo": spec.part(n).joint.servo.name}
                  for n, j in spec.joint_limits().items()]
        report = self.jobs.latest_report(spec.name)
        return {"ok": True, "robot": spec.name, "summary": spec.summary(), "joints": joints,
                "moves": {n: kind for n, (_, kind) in self.rt.all_moves(spec).items()},
                "limitations": spec.limitations, "hardware": spec.hardware_mapping(),
                "spec_hash": spec.hash()[:16], "latest_report": str(report) if report else None,
                "headline": _headline(spec.name)}

    # Benchmarks -----------------------------------------------------------------------------------

    def bench_run(self, args: dict[str, Any]) -> dict[str, Any]:
        robot = str(args.get("robot"))
        self.rt.robot(robot)
        scenes = args.get("scenes") or None
        job = self.jobs.start_bench(robot, scenes=scenes, worlds=args.get("worlds"), quick=bool(args.get("quick")))
        return {"ok": True, "job_id": job["id"], "robot": robot, "status": "running",
                "next": f"bench_status job_id={job['id']}, then bench_report job_id={job['id']}", "note": SIM_NOTE}

    def bench_status(self, args: dict[str, Any]) -> dict[str, Any]:
        if args.get("job_id"):
            job = self.jobs.job(str(args["job_id"]))
            return {"ok": True, "job": _public_job(job)}
        return {"ok": True, "jobs": [_public_job(j) for j in self.jobs.jobs()[:10]]}

    def bench_report(self, args: dict[str, Any]) -> dict[str, Any]:
        if args.get("job_id"):
            job = self.jobs.job(str(args["job_id"]))
            if job["status"] != "done":
                return {"ok": False, "error": f"job {job['id']} is {job['status']}", "job": _public_job(job)}
            path = Path(job["report"])
        elif args.get("robot"):
            self.rt.robot(str(args["robot"]))
            path = self.jobs.latest_report(str(args["robot"]))
            if path is None:
                return {"ok": False, "error": f"no benchmark report for {args['robot']} yet; start one with bench_run"}
        else:
            raise ValueError("give job_id or robot")
        md = path.read_text(encoding="utf-8")
        summary = None
        if path.name.endswith(".report.md"):
            try:
                summary = json.loads(path.with_name(path.name[:-3] + ".json").read_text(encoding="utf-8")).get("summary")
            except (OSError, ValueError, AttributeError):
                summary = None
        return {"ok": True, "report": str(path), "summary": summary,
                "markdown": md[:REPORT_CHARS] + ("\n... (truncated)" if len(md) > REPORT_CHARS else "")}

    def bench_compare(self, args: dict[str, Any]) -> dict[str, Any]:
        robot = str(args.get("robot"))
        self.rt.robot(robot)
        raw = args.get("variants")
        if not isinstance(raw, list) or not raw:
            raise ValueError("variants must be a non-empty list")
        variants = []
        for i, v in enumerate(raw[:6], start=1):
            if not isinstance(v, dict) or not v.get("name"):
                raise ValueError(f"variant {i} needs a name")
            if v.get("robot"):
                other = self.rt.robot(str(v["robot"]))      # a registered robot only, never an arbitrary path
                variants.append({"name": str(v["name"]), "spec": str(other.source)})
            elif isinstance(v.get("set"), dict) and v["set"]:
                variants.append({"name": str(v["name"]), "set": v["set"]})
            else:
                raise ValueError(f"variant {i} needs set: {{path: value}} or robot: <name>")
        job = self.jobs.start_compare(robot, variants, scenes=args.get("scenes") or None, worlds=args.get("worlds"),
                                      quick=bool(args.get("quick")))
        return {"ok": True, "job_id": job["id"], "robot": robot, "variants": [v["name"] for v in variants],
                "status": "running", "next": f"bench_status job_id={job['id']}", "note": SIM_NOTE}

    # Moves ----------------------------------------------------------------------------------------

    def move_check(self, args: dict[str, Any]) -> dict[str, Any]:
        spec, name, move, speed = requested_move(self.rt, "robot_play", args)
        quick = bool(args.get("quick"))
        worlds = preflight.QUICK_WORLDS if quick else int(min(500, max(60, self.rt.number("check_worlds"))))
        result = preflight.check(spec, name, move, speed=speed, worlds=worlds, adaptive=quick)
        key = preflight.approval_key(spec, move, speed)
        rec = preflight.record(key, spec, name, move, speed, result)
        preflight.ApprovalStore(self.rt.folder("approvals")).save(rec)
        out = {"ok": True, "summary": preflight.summary_line(result), **result,
               "approved": result["verdict"] == "pass", "approval_key": key[:16], "checked_at": rec["checked_at"]}
        if result["verdict"] == "pass":
            out["next"] = f"robot_play robot={spec.name} move={name}" + (f" speed={speed:g}" if speed != 1.0 else "")
        return out

    def move_save(self, args: dict[str, Any]) -> dict[str, Any]:
        spec = self.rt.robot(str(args.get("robot")))
        move = {k: args[k] for k in ("frames", "loops", "easing", "description") if args.get(k) is not None}
        plan = self.rt.save_move(spec, str(args.get("name") or ""), move)
        return {"ok": True, "robot": spec.name, "move": args.get("name"), "duration_s": plan["duration_ms"] / 1000,
                "warnings": plan["warnings"], "approved": False,
                "next": f"move_check robot={spec.name} move={args.get('name')} before playing it"}

    def move_list(self, args: dict[str, Any]) -> dict[str, Any]:
        spec = self.rt.robot(str(args.get("robot")))
        store = preflight.ApprovalStore(self.rt.folder("approvals"))
        limits = spec.joint_limits()
        moves = []
        for name, (move, kind) in self.rt.all_moves(spec).items():
            entry: dict[str, Any] = {"name": name, "source": kind, "description": move.get("description", "")}
            try:
                entry["duration_s"] = check_move(move, limits)["duration_ms"] / 1000
            except MoveError as exc:
                entry["problems"] = exc.problems
            rec = store.get(preflight.approval_key(spec, move, 1.0))
            entry["preflight"] = (f"{rec['verdict']} ({rec['checked_at']})" if rec else "not checked")
            moves.append(entry)
        return {"ok": True, "robot": spec.name, "moves": moves}

    # Robot ----------------------------------------------------------------------------------------

    def _client(self, spec, target: str) -> bridge.RobotClient:
        target = target or "virtual"
        timeout = self.rt.number("timeout_s")
        if target == "virtual":
            entry = self.rt.virtual.get(spec.name)
            if entry is None or entry[0] != spec.hash():
                if entry is not None:
                    entry[1].shutdown()
                    entry[1].server_close()
                server = bridge.start_virtual(spec)
                self.rt.virtual[spec.name] = (spec.hash(), server)
                entry = self.rt.virtual[spec.name]
            return bridge.RobotClient(entry[1].url, timeout=timeout)
        if target != "real":
            raise ValueError("target must be virtual or real")
        url = str(self.rt.setting("robot_url") or "")
        if not url:
            raise bridge.RobotError("no robot address set: put the robot's address in the talaria-bench "
                                    "robot_url setting (e.g. http://192.168.1.8)")
        return bridge.RobotClient(url, token=self.rt.token(), timeout=timeout)

    def _check_real(self, client: bridge.RobotClient, spec) -> list[str]:
        """The real robot must be the robot we checked; returns warnings."""
        info = client.info()
        reported = str(info.get("name") or "").lower()
        if reported not in (spec.name.lower(), (spec.title or "").lower()):
            raise bridge.RobotError(f"the robot at {client.url} reports itself as {info.get('name')!r}, not "
                                    f"{spec.name!r}; refusing to play a move checked for another robot")
        names = {j.get("name") for j in info.get("joints") or [] if isinstance(j, dict)}
        missing = [n for n in spec.joint_names if n not in names]
        if missing:
            raise bridge.RobotError(f"the robot at {client.url} has no joint(s) {', '.join(missing)}")
        warnings = []
        fw_hash = info.get("spec_hash")
        if fw_hash and fw_hash != spec.hash()[:len(fw_hash)]:
            warnings.append("the robot's firmware was generated from a different version of this spec; regenerate it "
                            "with `hermes talaria firmware` so its built-in limits match")
        return warnings

    def _gate(self, tool: str, args: dict[str, Any]) -> None:
        reason = block_reason(self.rt, tool, args)
        if reason:
            raise _Blocked(reason)

    def robot_play(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            self._gate("robot_play", args)
        except _Blocked as exc:
            return {"ok": False, "blocked": True, "error": str(exc)}
        spec, name, move, speed = requested_move(self.rt, "robot_play", args)
        plan = check_move(move, spec.joint_limits(), speed=speed)
        target = args.get("target") or "virtual"
        client = self._client(spec, target)
        warnings = self._check_real(client, spec) if target == "real" else []
        frames = [{"ms": f["ms"], "hold": f["hold"], "joints": f["joints"]} for f in plan["frames"]]
        client.play(frames, loops=plan["loops"], easing=plan["easing"], name=name)
        return {"ok": True, "robot": spec.name, "move": name, "target": target, "speed": speed,
                "duration_s": plan["duration_ms"] / 1000, "warnings": plan["warnings"] + warnings,
                "address": client.url}

    def robot_pose(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            self._gate("robot_pose", args)
        except _Blocked as exc:
            return {"ok": False, "blocked": True, "error": str(exc)}
        spec, _, move, _ = requested_move(self.rt, "robot_pose", args)
        plan = check_move(move, spec.joint_limits())
        target = args.get("target") or "virtual"
        client = self._client(spec, target)
        warnings = self._check_real(client, spec) if target == "real" else []
        frame = plan["frames"][0]
        client.pose(frame["joints"], ms=frame["ms"])
        return {"ok": True, "robot": spec.name, "target": target, "joints": frame["joints"], "ms": frame["ms"],
                "warnings": plan["warnings"] + warnings,
                "note": "the check assumed the robot starts from its home pose"}

    def robot_stop(self, args: dict[str, Any]) -> dict[str, Any]:
        spec = self.rt.robot(str(args.get("robot") or self.rt.setting("real_robot")))
        target = args.get("target") or "virtual"
        if target == "virtual" and spec.name not in self.rt.virtual:
            return {"ok": True, "robot": spec.name, "target": target, "stopped": False, "note": "nothing was playing"}
        client = self._client(spec, target)
        client.stop(home=bool(args.get("home")))
        return {"ok": True, "robot": spec.name, "target": target, "stopped": True, "home": bool(args.get("home"))}

    def robot_status(self, args: dict[str, Any]) -> dict[str, Any]:
        spec = self.rt.robot(str(args.get("robot") or self.rt.setting("real_robot")))
        target = args.get("target") or "virtual"
        client = self._client(spec, target)
        info = client.info()
        state = client.state()
        return {"ok": True, "robot": spec.name, "target": target, "address": client.url,
                "firmware": info.get("firmware"), "simulated": bool(info.get("simulated")),
                "busy": state.get("busy"), "playing": state.get("move"), "pose": state.get("pose"),
                "stop_reason": state.get("stop_reason")}

    def shutdown(self) -> None:
        for _, server in list(self.rt.virtual.values()):
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass
        self.rt.virtual.clear()


class _Blocked(Exception):
    pass


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    keep = ("id", "kind", "robot", "status", "progress", "report", "variants", "quick", "worlds", "scenes", "log_tail")
    return {k: job[k] for k in keep if k in job and job[k] is not None}
