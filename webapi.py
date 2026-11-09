"""Backend for the visual lab: the Hermes Desktop page and the web-dashboard tab call the same routes,
mounted by ``dashboard/plugin_api.py`` at ``/api/plugins/talaria-bench/``.

Everything here goes through the same runtime, tools and preflight gate as the agent: playing a move from
the UI needs the same passing preflight as the ``robot_play`` tool. Traces are recorded on demand (or
taken from a finished run), compacted to 30 fps with 3 decimals and served gzip-compressed; recorded
traces are cached in the plugin data folder.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from . import preflight
from .motion import MoveError, check_move
from .runtime import EXAMPLE_REPORTS, PLUGIN_ROOT, Runtime
from .spec import Spec, SpecError
from .tools import TalariaTools, _headline

PHOTO_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
GALLERY_IMG = PLUGIN_ROOT / "docs" / "img" / "gallery"
VARIANTS_DIR = PLUGIN_ROOT / "examples" / "variants"
TRACE_DECIMALS = 3
TRACE_VERSION = 3          # 3: traces carry look.detail (drawing hints per part)
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
EDITABLE = ("size", "mass", "servo")


class ApiError(Exception):
    def __init__(self, status: int, error: str, problems: Optional[list[str]] = None):
        super().__init__(error)
        self.status, self.error, self.problems = status, error, problems or []

    def payload(self) -> dict[str, Any]:
        return {"ok": False, "error": self.error, **({"problems": self.problems} if self.problems else {})}


def _whole(body: dict[str, Any], key: str, lo: int, hi: int) -> Optional[int]:
    """``body[key]`` as a whole number in [lo, hi], None when absent; anything else is a 400, not a 500."""
    value = body.get(key)
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = math.nan
    if isinstance(value, bool) or not math.isfinite(number) or number != int(number) or not lo <= number <= hi:
        raise ApiError(400, f"{key} must be a whole number from {lo} to {hi} (got {value!r})")
    return int(number)


def _real(body: dict[str, Any], key: str, default: float) -> float:
    value = body.get(key)
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = math.nan
    if isinstance(value, bool) or not math.isfinite(number):
        raise ApiError(400, f"{key} must be a number (got {value!r})")
    return number


def _call(tools: TalariaTools, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return json.loads(tools.handlers()[name](args))


def compact_trace(trace: dict[str, Any]) -> dict[str, Any]:
    d = TRACE_DECIMALS
    return {"fps": trace["fps"], "units": "m", "parts": trace["parts"],
            "frames": [[[round(v, d) for v in part] for part in frame] for frame in trace["frames"]]}


def gzip_json(payload: dict[str, Any]) -> bytes:
    return gzip.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"), mtime=0)


class WebAPI:
    def __init__(self, runtime: Runtime, tools: Optional[TalariaTools] = None):
        self.rt = runtime
        self.tools = tools or TalariaTools(runtime)
        self._look_detail: dict[str, dict[str, Any]] = {}      # drawing hints per spec hash

    # Robots ---------------------------------------------------------------------------------------

    def _spec(self, name: str) -> Spec:
        try:
            return self.rt.robot(str(name))
        except KeyError as exc:
            raise ApiError(404, str(exc.args[0] if exc.args else exc)) from None
        except SpecError as exc:
            raise ApiError(400, "the robot spec is not valid", getattr(exc, "problems", [str(exc)])) from None

    def robots(self) -> dict[str, Any]:
        data = _call(self.tools, "robot_list", {})
        out = []
        for r in data.get("robots", []):
            spec = self._spec(r["name"])
            out.append({**r, "role": spec.role or spec.description, "headline": self._headline(spec.name),
                        "look": {k: v for k, v in spec.look.items() if k in ("badge", "accent", "material")},
                        "has_photo": self.photo_path(spec.name) is not None,
                        "has_thumb": (GALLERY_IMG / f"{spec.name}.png").is_file() and r["source"] == "bundled"})
        return {"ok": True, "robots": out}

    def _headline(self, name: str) -> Optional[str]:
        rep = self.report(name, quiet=True, official=True)
        if not rep:
            return None
        sentences = [s.strip().rstrip(".") for s in rep.get("summary", "").split(". ") if s.strip()]
        for key in ("Max safe payload", "tips the robot in", "On flat ground"):
            hit = next((s for s in sentences if key in s), None)
            if hit:
                return hit + "."
        return (sentences[0] + ".") if sentences else None

    def robot(self, name: str) -> dict[str, Any]:
        spec = self._spec(name)
        show = _call(self.tools, "robot_show", {"robot": spec.name})
        raw = self._raw(spec)
        parts = []
        for p in spec.parts:
            entry = {"name": p.name, "parent": p.parent, "shape": p.shape, "size": list(p.size), "mass": p.mass,
                     "material": p.material, "color": p.color, "ground_contact": p.ground_contact,
                     "servo": p.joint.servo.name if p.joint else None}
            parts.append(entry)
        return {"ok": True, "robot": spec.name, "title": spec.title, "description": spec.description,
                "family": spec.family, "role": spec.role, "base": spec.base, "summary": spec.summary(),
                "parts": parts, "joints": show.get("joints", []), "moves": self.moves(spec.name)["moves"],
                "limitations": spec.limitations, "spec_hash": spec.hash()[:16],
                "has_photo": self.photo_path(spec.name) is not None, "render": self.render(spec),
                "look": self.look(spec),
                "showcase": self.render(spec, (spec.look.get("showcase") or {}).get("joints")),
                "variants": self.variants(spec.name)["variants"], "servos": self._servo_names(),
                "editable": bool(raw), "headline": _headline(spec.name),
                "source": self.rt.robot_paths()[spec.name][1]}

    @staticmethod
    def _servo_names() -> list[str]:
        from . import servos

        catalog = getattr(servos, "SERVOS", None) or getattr(servos, "CATALOG", None) or {}
        return sorted(catalog)

    @staticmethod
    def _raw(spec: Spec) -> Optional[dict[str, Any]]:
        try:
            data = yaml.safe_load(Path(spec.source).read_text(encoding="utf-8"))
        except (OSError, TypeError, yaml.YAMLError):
            return None
        return data if isinstance(data, dict) else None

    def look(self, spec: Spec) -> dict[str, Any]:
        """The spec's look plus drawing hints per part, for the 3D viewer only (appearance, never physics):
        the part's material and whether it may touch the floor, and for a jointed part its servo model and
        the joint's anchor and axis in the part's own frame, so the viewer can draw a servo horn that moves
        with the part. Read from the finished model at the home pose; nothing is changed."""
        key = spec.hash()
        hit = self._look_detail.get(key)
        if hit is None:
            import mujoco

            from .builder import _set_home, base_model

            model, _, _ = base_model(spec)
            data = mujoco.MjData(model)
            _set_home(model, data, spec)
            mujoco.mj_forward(model, data)
            jointed = {p.name for p in spec.joint_parts}
            hit = {}
            for p in spec.parts:
                entry: dict[str, Any] = {"material": p.material, "ground": bool(p.ground_contact)}
                if p.name in jointed:
                    gid, jid = model.geom(p.name).id, model.joint(p.name).id
                    rot = data.geom_xmat[gid].reshape(3, 3)
                    entry["servo"] = p.joint.servo.name
                    entry["anchor"] = [round(float(v), 4) for v in rot.T @ (data.xanchor[jid] - data.geom_xpos[gid])]
                    entry["axis"] = [round(float(v), 4) for v in rot.T @ data.xaxis[jid]]
                hit[p.name] = entry
            if len(self._look_detail) > 64:
                self._look_detail.clear()
            self._look_detail[key] = hit
        return {**spec.look, "detail": hit}

    def render(self, spec: Spec, joints: Optional[dict[str, float]] = None) -> dict[str, Any]:
        """A static pose for the 3D viewer: every part's shape, size, colour and world pose, and every joint's
        world anchor and axis (metres, MuJoCo frame: z up, x forward). ``joints`` (degrees, clamped to each
        joint's range) poses the robot, e.g. the spec's look.showcase; a free-standing robot is then lowered or
        raised so its lowest ground-contact part touches the floor."""
        import math as _m

        import mujoco
        import numpy as np

        from .builder import _set_home, base_model, lowest_z

        model, _, _ = base_model(spec)
        data = mujoco.MjData(model)
        _set_home(model, data, spec)
        if joints:
            limits = spec.joint_limits()
            for name, deg in joints.items():
                if name in limits:
                    deg = min(max(float(deg), limits[name]["min"]), limits[name]["max"])
                    data.qpos[model.jnt_qposadr[model.joint(name).id]] = _m.radians(deg)
        mujoco.mj_forward(model, data)
        if joints and spec.base == "free":
            feet = [model.geom(p.name).id for p in spec.parts if p.ground_contact]
            if feet:
                low = min(lowest_z(model, data, g) for g in feet)
                data.qpos[model.jnt_qposadr[model.joint("root").id] + 2] -= low
                mujoco.mj_forward(model, data)
        q = np.zeros(4)
        parts = []
        for p in spec.parts:
            gid = model.geom(p.name).id
            mujoco.mju_mat2Quat(q, data.geom_xmat[gid])
            parts.append({"name": p.name, "shape": p.shape, "size_m": [s * 0.01 for s in p.size], "color": p.color,
                          "pose": [round(float(v), 4) for v in (*data.geom_xpos[gid], *q)]})
        joint_axes = []
        for p in spec.joint_parts:
            jid = model.joint(p.name).id
            joint_axes.append({"name": p.name, "anchor": [round(float(v), 4) for v in data.xanchor[jid]],
                           "axis": [round(float(v), 4) for v in data.xaxis[jid]]})
        return {"parts": parts, "joints": joint_axes, "units": "m", "up": "z", "look": self.look(spec)}

    def photo_path(self, name: str) -> Optional[Path]:
        try:
            spec = self.rt.robot(str(name))
        except (KeyError, SpecError):
            return None
        if not spec.photo or not spec.source:
            return None
        folder = Path(spec.source).resolve().parent
        path = Path(spec.photo)
        path = (path if path.is_absolute() else folder / path).resolve()
        if folder not in path.parents or path.suffix.lower() not in PHOTO_TYPES or not path.is_file():
            return None
        return path

    def thumb_path(self, name: str) -> Optional[Path]:
        if not _NAME_RE.match(str(name)):
            return None
        paths = self.rt.robot_paths()
        if name not in paths or paths[name][1] != "bundled":
            return None
        for path in (GALLERY_IMG / "thumbs" / f"{name}.png", GALLERY_IMG / f"{name}.png"):
            if path.is_file():
                return path
        return None

    def edit(self, name: str, body: dict[str, Any]) -> dict[str, Any]:
        """Save an edited copy (sizes, masses, servos) as a user robot through robot_define."""
        spec = self._spec(name)
        raw = self._raw(spec)
        if raw is None:
            raise ApiError(400, f"{name} has no editable spec file")
        new_name = str(body.get("new_name") or f"{spec.name}_custom")
        if not _NAME_RE.match(new_name):
            raise ApiError(400, "names use lowercase letters, digits, - and _ (up to 32)")
        changes = body.get("parts") or {}
        if not isinstance(changes, dict):
            raise ApiError(400, "parts must map part name -> {size, mass, servo}")
        by_name = {p.get("name"): p for p in raw.get("parts", []) if isinstance(p, dict)}
        problems = []
        for part, change in changes.items():
            target = by_name.get(part)
            if target is None or not isinstance(change, dict):
                problems.append(f"no part named {part!r}")
                continue
            for key, value in change.items():
                if key not in EDITABLE:
                    problems.append(f"{part}: {key} cannot be edited here (only {', '.join(EDITABLE)})")
                elif key == "servo":
                    if not target.get("joint"):
                        problems.append(f"{part} has no joint, so no servo")
                    elif isinstance(target["joint"], dict):
                        target["joint"]["servo"] = value
                else:
                    target[key] = value
        if problems:
            raise ApiError(400, "the edit cannot be applied", problems)
        raw["name"] = new_name
        raw["title"] = f"{raw.get('title') or spec.name} (edited)"
        raw.pop("photo", None)                       # the photo shows the original robot, not the edit
        defined = _call(self.tools, "robot_define", {"spec_yaml": yaml.safe_dump(raw, sort_keys=False)})
        if not defined.get("ok"):
            raise ApiError(400, defined.get("error", "the edited robot is not valid"), defined.get("problems"))
        return defined

    def templates(self) -> dict[str, Any]:
        from . import servos, templates

        return {"ok": True, "templates": [{"name": n, "help": h,
                                           "fields": [{"key": k, "label": lab, "default": d,
                                                       **({"options": u} if isinstance(u, list) else {"unit": u})}
                                                      for k, lab, d, u in templates.FIELDS[n]],
                                           "servo": templates.SERVO_DEFAULT[n]}
                                          for n, h in templates.describe().items()],
                "servos": servos.names(), "materials": list(templates.DENSITY)}

    def new_robot(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._ok_or_raise(_call(self.tools, "robot_define", {"template": body.get("template"),
                                                                   "params": body.get("params") or {}}))

    def upload_photo(self, name: str, body: dict[str, Any]) -> dict[str, Any]:
        """A photo for one of the user's robots (base64 JPEG/PNG/WebP, at most 10 MB); bundled robots keep theirs."""
        spec = self._spec(name)
        paths = self.rt.robot_paths()
        if paths[spec.name][1] != "user":
            raise ApiError(400, "bundled robots keep their photo; save your own copy first (edit the parts)")
        try:
            data = base64.b64decode(str(body.get("data") or "").split(",")[-1], validate=True)
        except (ValueError, TypeError):
            raise ApiError(400, "photo: send the image as base64") from None
        try:
            rel = self.rt.store_photo(spec.name, data)
        except SpecError as exc:
            raise ApiError(400, "the photo was refused", getattr(exc, "problems", [str(exc)])) from None
        raw = self._raw(spec) or {}
        raw["photo"] = rel
        try:
            self.rt.define_robot(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
        except SpecError as exc:
            raise ApiError(400, "the robot could not be saved with the photo", getattr(exc, "problems", [])) from None
        return {"ok": True, "robot": spec.name, "photo": rel}

    # Reports and jobs -----------------------------------------------------------------------------

    def report(self, name: str, quiet: bool = False, official: bool = False) -> Optional[dict[str, Any]]:
        """The newest report from this machine, else the bundled one. ``official``: only a full run that
        scored moves on the 60 preflight worlds (quick runs and older-format reports are skipped), which is
        what headlines and move tip numbers use; the report card shows the newest run, labelled quick."""
        mine = sorted(self.rt.folder("reports").glob(f"{name}-bench-*.report.json"), key=lambda p: p.stat().st_mtime)
        if official:
            def full(p: Path) -> bool:
                try:
                    st = json.loads(p.read_text(encoding="utf-8")).get("settings") or {}
                except (OSError, ValueError):
                    return False
                return not st.get("quick") and st.get("move_worlds") == preflight.DEFAULT_WORLDS
            mine = [p for p in mine if full(p)]
        path = mine[-1] if mine else EXAMPLE_REPORTS / f"{name}.report.json"
        try:
            rep = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            if quiet:
                return None
            raise ApiError(404, f"no benchmark report for {name} yet; run one") from None
        rep["origin"] = "this machine" if mine else "bundled example"
        return rep

    def start_bench(self, body: dict[str, Any]) -> dict[str, Any]:
        args = {"robot": body.get("robot"), "quick": bool(body.get("quick"))}
        worlds = _whole(body, "worlds", 1, 10**6)
        if worlds:
            args["worlds"] = worlds
        return self._ok_or_raise(_call(self.tools, "bench_run", args))

    def start_compare(self, body: dict[str, Any]) -> dict[str, Any]:
        args = {"robot": body.get("robot"), "variants": body.get("variants"), "quick": bool(body.get("quick", True))}
        if body.get("scenes"):
            args["scenes"] = body["scenes"]
        return self._ok_or_raise(_call(self.tools, "bench_compare", args))

    def job(self, job_id: str) -> dict[str, Any]:
        try:
            job = self.tools.jobs.job(str(job_id))
        except KeyError as exc:
            raise ApiError(404, str(exc.args[0])) from None
        out = {"ok": True, "id": job["id"], "kind": job["kind"], "robot": job["robot"], "status": job["status"],
               "progress": job.get("progress") or {}}
        if job["status"] == "failed":
            out["log_tail"] = job.get("log_tail", "")[-800:]
        if job["status"] == "done":
            out_path = Path(job["out"])
            src = out_path.with_suffix(".report.json") if job["kind"] == "bench" else out_path
            try:
                result = json.loads(src.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                result = None
            out["result"] = result
        return out

    def variants(self, name: str) -> dict[str, Any]:
        path = VARIANTS_DIR / f"{name}.yaml"
        out = []
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            data = {}
        for v in (data.get("variants") if isinstance(data, dict) else data) or []:
            if not isinstance(v, dict) or not v.get("name"):
                continue
            if v.get("set"):
                out.append({"name": v["name"], "set": v["set"]})
            elif v.get("spec"):
                other = Path(str(v["spec"])).stem
                if other in self.rt.robot_paths():
                    out.append({"name": v["name"], "robot": other})
        return {"ok": True, "robot": name, "variants": out}

    # Moves ----------------------------------------------------------------------------------------

    def official_tips(self, name: str) -> dict[str, dict[str, Any]]:
        """Tip numbers per move from the robot's latest report: its move scenes run on the preflight's own
        worlds (60, fixed seeds; quick runs 30 and say so), so these equal a full move_check."""
        rep = self.report(name, quiet=True, official=True) or {}
        quick = bool((rep.get("settings") or {}).get("quick"))
        out = {}
        for c in rep.get("scenes", []):
            if c.get("id", "").startswith("move:") and c.get("applicable") and c.get("runs"):
                falls = c["runs"] - c["passed"]
                lo, hi = preflight.wilson(falls, c["runs"])
                out[c["id"][5:]] = {"falls": falls, "worlds": c["runs"], "rate": round(falls / c["runs"], 4),
                                    "low": round(lo, 4), "high": round(hi, 4), "quick": quick,
                                    "origin": rep.get("origin")}
        return out

    def moves(self, name: str) -> dict[str, Any]:
        data = self._ok_or_raise(_call(self.tools, "move_list", {"robot": name}))
        tips = self.official_tips(name)
        for m in data["moves"]:
            if m["name"] in tips:
                m["official"] = tips[m["name"]]
        return data

    def check(self, body: dict[str, Any]) -> dict[str, Any]:
        args = {k: body[k] for k in ("robot", "move", "frames", "loops", "easing", "speed", "quick") if k in body}
        return self._ok_or_raise(_call(self.tools, "move_check", args))

    def play(self, body: dict[str, Any]) -> dict[str, Any]:
        args = {k: body[k] for k in ("robot", "move", "frames", "loops", "easing", "speed", "target") if k in body}
        data = _call(self.tools, "robot_play", args)
        if data.get("blocked"):
            return data                                   # a block is an answer, not an error
        return self._ok_or_raise(data)

    def stop(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._ok_or_raise(_call(self.tools, "robot_stop", {k: body[k] for k in ("robot", "target", "home")
                                                                  if k in body}))

    def status(self, body: dict[str, Any]) -> dict[str, Any]:
        return _call(self.tools, "robot_status", {k: body[k] for k in ("robot", "target") if k in body})

    @staticmethod
    def _ok_or_raise(data: dict[str, Any]) -> dict[str, Any]:
        if data.get("ok"):
            return data
        raise ApiError(400, str(data.get("error")), data.get("problems"))

    # Traces ---------------------------------------------------------------------------------------

    def _trace_spec(self, body: dict[str, Any]) -> Spec:
        spec = self._spec(body.get("robot"))
        variant = None
        if body.get("job_id") and body.get("variant") not in (None, "base"):
            job = self.job(str(body["job_id"]))
            result = job.get("result") or {}
            variant = next((v for v in result.get("variants", []) if v.get("name") == body["variant"]), None)
            if variant is None:
                raise ApiError(404, f"no variant {body['variant']!r} in job {body['job_id']}")
            if variant.get("spec"):
                path = Path(variant["spec"]).resolve()
                known = {p.resolve(): n for n, (p, _) in self.rt.robot_paths().items()}
                if path not in known:
                    raise ApiError(400, "variant spec is not a registered robot")
                return self._spec(known[path])
        elif isinstance(body.get("set"), dict) and body["set"]:
            variant = {"name": "custom", "set": body["set"]}
        if variant and variant.get("set"):
            from .compare import build_variant

            try:
                return build_variant(spec, {"name": variant["name"], "set": variant["set"]})
            except (SpecError, ValueError, KeyError) as exc:
                raise ApiError(400, f"variant cannot be built: {exc}") from None
        return spec

    def trace(self, body: dict[str, Any]) -> bytes:
        """A recorded run as gzip JSON: a scene in world ``seed`` (median/worst replays) or a move in a
        world (``seed`` given) or the nominal world (no seed)."""
        from .builder import MODEL_VERSION
        from .scenes import SCENE_VERSION

        spec = self._trace_spec(body)
        scene = body.get("scene")
        seed = _whole(body, "seed", 0, 2**31 - 1)
        speed = _real(body, "speed", 1.0)
        if scene is None:
            try:
                name, move = self.rt.resolve_move(spec, body.get("move"), body.get("frames"), body.get("loops"),
                                                  body.get("easing"))
                check_move(move, spec.joint_limits(), speed=speed)
            except MoveError as exc:
                raise ApiError(400, "the move cannot be played as written", exc.problems) from None
            what: Any = {"move": preflight.canonical_move(move), "speed": speed}
        else:
            what = {"scene": str(scene)}
        # The physics hash leaves out moves and bench settings, but a scene replays the spec's walk move:
        # a variant such as "high step" (bench.walk_move) must not reuse the base design's trace.
        key = hashlib.sha256(json.dumps({"v": TRACE_VERSION, "spec": spec.hash(), "bench": spec.bench,
                                         "moves": spec.moves, "what": what, "seed": seed,
                                         "scene_version": SCENE_VERSION, "model": MODEL_VERSION},
                                        sort_keys=True).encode()).hexdigest()[:32]
        cache = self.rt.folder("cache") / "traces" / f"{key}.json.gz"
        if cache.is_file():
            return cache.read_bytes()
        payload = self._record(spec, scene, seed, speed, body)
        blob = gzip_json(payload)
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".tmp")
        tmp.write_bytes(blob)
        tmp.replace(cache)
        return blob

    def _record(self, spec: Spec, scene: Optional[str], seed: Any, speed: float, body: dict[str, Any]) -> dict:
        from .simrun import run_move
        from .worlds import World

        if scene is None:
            name, move = self.rt.resolve_move(spec, body.get("move"), body.get("frames"), body.get("loops"),
                                              body.get("easing"))
            world = (World.random(int(seed), spec.joint_names, spec.world_ranges) if seed is not None
                     else World.nominal())
            r = run_move(spec, move, world, None, record=True, speed=speed)
            return {"ok": True, "simulation": True, "robot": spec.name, "move": name, "seed": seed, "speed": speed,
                    "trace": compact_trace(r.trace), "meta": {"floor": "flat"}, "look": self.look(spec),
                    "result": {"fell": r.fell, "fell_at_s": r.fell_at_s, "fall_reason": r.fall_reason,
                               "max_tilt_deg": round(r.max_tilt_deg, 2)}}
        from .scenes import SCENES, get_scene, run_scene

        if scene not in SCENES and not str(scene).startswith("move:"):
            raise ApiError(404, f"no scene {scene!r}")
        rec = run_scene(spec, scene, int(seed or 0), record=True)
        if not rec.get("applicable", True):
            raise ApiError(400, f"{scene} does not apply to {spec.name}: {rec.get('reason')}")
        if not rec.get("trace"):
            raise ApiError(500, "the run produced no trace")
        return {"ok": True, "simulation": True, "robot": spec.name, "scene": scene, "seed": seed,
                "trace": compact_trace(rec["trace"]), "note": rec.get("trace_note"), "look": self.look(spec),
                "meta": self.scene_meta(spec, get_scene(scene), rec),
                "result": {"passed": rec.get("passed"), "fell": rec.get("fell"), "metric": rec.get("metric"),
                           "reason": rec.get("reason"), "fell_at_s": (rec.get("metrics") or {}).get("fell_at_s")}}

    @staticmethod
    def scene_meta(spec: Spec, scene: Any, rec: dict[str, Any]) -> dict[str, Any]:
        meta: dict[str, Any] = {"floor": "flat", **(rec.get("trace_meta") or {})}
        if scene.family == "ramp":
            meta.update(tilt_deg=scene.params["angle"], rises_toward="+x")
        elif scene.family == "obstacle":
            from .builder import base_model
            from .scenes import OBSTACLE_AHEAD_M, OBSTACLE_DEPTH_M

            _, info, _ = base_model(spec)
            h = scene.params["height"]
            x = info.front_x + OBSTACLE_AHEAD_M + OBSTACLE_DEPTH_M / 2
            meta["boxes"] = [{"center": [round(x, 4), 0.0, h / 2], "half": [OBSTACLE_DEPTH_M / 2, 1.0, h / 2]}]
        elif scene.family == "slippery":
            meta["floor"] = "slippery"
            friction = (rec.get("world") or {}).get("effective_friction")
            if isinstance(friction, (int, float)) and math.isfinite(friction):
                meta["friction"] = friction
        return meta


def body_size(obj: Any) -> int:
    return len(json.dumps(obj))


# FastAPI router ------------------------------------------------------------------------------------


def make_router(api: WebAPI):
    from fastapi import APIRouter, Body
    from fastapi.responses import FileResponse, JSONResponse, Response

    router = APIRouter()

    def guard(fn, *args):
        """A missing resource is a 404; a request the bench refuses (bad move, invalid edit, blocked play)
        is an answer: 200 with ``{"ok": false, "error", "problems"}``, so both UIs can show the problems."""
        try:
            return fn(*args)
        except ApiError as exc:
            return JSONResponse(exc.payload(), status_code=200 if exc.status == 400 else exc.status)

    def data_url(path):
        if path is None:
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        mime = PHOTO_TYPES.get(path.suffix.lower(), "image/png")
        return {"ok": True, "data_url": f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")}

    @router.get("/robots/{name}/photo.json")
    def photo_json(name: str):
        return data_url(api.photo_path(name))

    @router.get("/robots/{name}/thumb.json")
    def thumb_json(name: str):
        return data_url(api.thumb_path(name))

    @router.get("/robots")
    def robots():
        return guard(api.robots)

    @router.get("/robots/{name}")
    def robot(name: str):
        return guard(api.robot, name)

    @router.get("/robots/{name}/photo")
    def photo(name: str):
        path = api.photo_path(name)
        if path is None:
            return JSONResponse({"ok": False, "error": "no photo"}, status_code=404)
        return FileResponse(path, media_type=PHOTO_TYPES[path.suffix.lower()])

    @router.get("/robots/{name}/thumb")
    def thumb(name: str):
        path = api.thumb_path(name)
        if path is None:
            return JSONResponse({"ok": False, "error": "no thumbnail"}, status_code=404)
        return FileResponse(path, media_type="image/png")

    @router.get("/robots/{name}/report")
    def report(name: str):
        return guard(lambda: {"ok": True, "report": api.report(name)})

    @router.get("/robots/{name}/moves")
    def moves(name: str):
        return guard(api.moves, name)

    @router.get("/robots/{name}/variants")
    def variants(name: str):
        return guard(api.variants, name)

    @router.post("/robots/{name}/edit")
    def edit(name: str, body: dict = Body(default_factory=dict)):
        return guard(api.edit, name, body)

    @router.get("/templates")
    def templates_route():
        return guard(api.templates)

    @router.post("/robots/new")
    def new_robot(body: dict = Body(default_factory=dict)):
        return guard(api.new_robot, body)

    @router.post("/robots/{name}/photo")
    def upload_photo(name: str, body: dict = Body(default_factory=dict)):
        return guard(api.upload_photo, name, body)

    @router.post("/bench")
    def bench(body: dict = Body(default_factory=dict)):
        return guard(api.start_bench, body)

    @router.post("/compare")
    def compare(body: dict = Body(default_factory=dict)):
        return guard(api.start_compare, body)

    @router.get("/jobs/{job_id}")
    def job(job_id: str):
        return guard(api.job, job_id)

    @router.post("/check")
    def check(body: dict = Body(default_factory=dict)):
        return guard(api.check, body)

    @router.post("/play")
    def play(body: dict = Body(default_factory=dict)):
        return guard(api.play, body)

    @router.post("/stop")
    def stop(body: dict = Body(default_factory=dict)):
        return guard(api.stop, body)

    @router.post("/status")
    def status(body: dict = Body(default_factory=dict)):
        return guard(api.status, body)

    @router.post("/trace")
    def trace(body: dict = Body(default_factory=dict)):
        try:
            blob = api.trace(body)
        except ApiError as exc:
            return JSONResponse(exc.payload(), status_code=200 if exc.status == 400 else exc.status)
        return Response(content=blob, media_type="application/json",
                        headers={"Content-Encoding": "gzip", "Cache-Control": "no-store"})

    return router
