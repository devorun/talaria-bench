"""Settings, secrets, storage, the robot registry and the move library: one place for tools, the hook,
the slash command and the CLI.

* Settings live under ``plugins.entries.talaria-bench.settings`` (``ctx.get_config``).
* The optional robot token is a Hermes secret (``TALARIA_ROBOT_TOKEN``) read with
  ``agent.secret_scope.get_secret``, never from a file.
* Data goes to the plugin data folder Hermes provides (``plugins.plugin_storage.plugin_data_dir``),
  else ``~/.cache/talaria-bench``; never into the plugin's code folder.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Optional

from . import bench
from .motion import MoveError, check_move
from .spec import Spec, SpecError, load_spec, parse_spec

logger = logging.getLogger(__name__)

PLUGIN_NAME = "talaria-bench"
TOKEN_ENV = "TALARIA_ROBOT_TOKEN"
PLUGIN_ROOT = Path(__file__).resolve().parent
EXAMPLES = PLUGIN_ROOT / "examples" / "robots"
EXAMPLE_REPORTS = PLUGIN_ROOT / "examples" / "reports"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

DEFAULTS: dict[str, Any] = {
    "robot_url": "",
    "real_robot": "caduceus",
    "timeout_s": 3.0,
    "check_worlds": 60,
    "max_tip_upper": 0.10,
    "max_load": 0.90,
}


class Runtime:
    """One per loaded plugin. ``ctx`` is Hermes's plugin context; tests pass ``overrides`` instead."""

    def __init__(self, ctx: Any = None, overrides: Optional[dict[str, Any]] = None):
        self.ctx = ctx
        self.overrides = dict(overrides or {})
        self._specs: dict[str, tuple[float, Spec]] = {}
        self._lock = threading.Lock()
        self.virtual: dict[str, Any] = {}      # robot name -> running virtual server
        bench.set_data_dir(self.data_dir())

    # Settings and secrets -------------------------------------------------------------------------

    def setting(self, key: str) -> Any:
        if key in self.overrides:
            return self.overrides[key]
        if self.ctx is not None:
            try:
                value = self.ctx.get_config(key, default=None)
            except Exception:
                logger.debug("talaria-bench: could not read setting %s", key, exc_info=True)
                value = None
            if value is not None:
                return value
        return DEFAULTS.get(key)

    def number(self, key: str) -> float:
        try:
            return float(self.setting(key))
        except (TypeError, ValueError):
            return float(DEFAULTS[key])

    def token(self) -> Optional[str]:
        if "token" in self.overrides:
            return self.overrides["token"]
        try:
            from agent.secret_scope import get_secret
        except ImportError:   # outside Hermes
            return None
        try:
            return get_secret(TOKEN_ENV) or None
        except Exception:
            logger.debug("talaria-bench: token lookup failed", exc_info=True)
            return None

    # Storage --------------------------------------------------------------------------------------

    def data_dir(self) -> Path:
        if "data_dir" in self.overrides:
            path = Path(self.overrides["data_dir"])
        else:
            try:
                from plugins.plugin_storage import plugin_data_dir
                path = Path(plugin_data_dir(PLUGIN_NAME))
            except Exception:
                path = Path.home() / ".cache" / PLUGIN_NAME
        path.mkdir(parents=True, exist_ok=True)
        return path

    def folder(self, name: str) -> Path:
        path = self.data_dir() / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    # Robots ---------------------------------------------------------------------------------------

    def robot_paths(self) -> dict[str, tuple[Path, str]]:
        """name -> (spec file, "bundled" | "user")."""
        out: dict[str, tuple[Path, str]] = {}
        for p in sorted(EXAMPLES.glob("*.yaml")):
            if ".calibration" not in p.name:
                out[p.stem] = (p, "bundled")
        for p in sorted(self.folder("robots").glob("*.yaml")):
            out.setdefault(p.stem, (p, "user"))
        return out

    def robot(self, name: str) -> Spec:
        paths = self.robot_paths()
        if name not in paths:
            raise KeyError(f"no robot named {name!r} (robots: {', '.join(paths)})")
        path = paths[name][0]
        mtime = path.stat().st_mtime
        with self._lock:
            cached = self._specs.get(str(path))
            if cached and cached[0] == mtime:
                return cached[1]
        spec = load_spec(path)
        with self._lock:
            self._specs[str(path)] = (mtime, spec)
        return spec

    def define_robot(self, text: str) -> tuple[Spec, Path]:
        import yaml

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise SpecError([f"not valid YAML: {getattr(exc, 'problem', None) or exc}"]) from None
        spec = parse_spec(data, base_dir=self.folder("robots"))
        bundled = {n for n, (_, kind) in self.robot_paths().items() if kind == "bundled"}
        if spec.name in bundled:
            raise SpecError([f"name {spec.name!r} belongs to a bundled robot; choose another name"])
        path = self.folder("robots") / f"{spec.name}.yaml"
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        spec.source = path
        return spec, path

    # Moves ----------------------------------------------------------------------------------------

    def _moves_file(self, robot: str) -> Path:
        return self.folder("moves") / f"{robot}.json"

    def saved_moves(self, robot: str) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self._moves_file(robot).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def save_move(self, spec: Spec, name: str, move: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(name, str) or not _NAME_RE.match(name):
            raise MoveError(["move names use lowercase letters, digits, - and _ (up to 32)"])
        if name in spec.moves:
            raise MoveError([f"{spec.name} already has a built-in move {name!r}; choose another name"])
        clean = {k: move[k] for k in ("frames", "loops", "easing", "repeat", "description") if k in move}
        plan = check_move(clean, spec.joint_limits())
        moves = self.saved_moves(spec.name)
        moves[name] = clean
        self._moves_file(spec.name).write_text(json.dumps(moves, indent=1), encoding="utf-8")
        return plan

    def all_moves(self, spec: Spec) -> dict[str, tuple[dict[str, Any], str]]:
        out = {n: (m, "spec") for n, m in spec.moves.items()}
        for n, m in self.saved_moves(spec.name).items():
            out.setdefault(n, (m, "saved"))
        return out

    def resolve_move(self, spec: Spec, name: Optional[str] = None, frames: Any = None, loops: Any = None,
                     easing: Any = None) -> tuple[str, dict[str, Any]]:
        """A named move of the robot, or an inline move from frames. Returns (name, move)."""
        if frames is not None:
            move: dict[str, Any] = {"frames": frames}
            if loops is not None:
                move["loops"] = loops
            if easing is not None:
                move["easing"] = easing
            return name or "custom", move
        if not name:
            raise MoveError(["give a move name or frames"])
        moves = self.all_moves(spec)
        if name not in moves:
            raise MoveError([f"{spec.name} has no move {name!r} (moves: {', '.join(moves) or 'none'})"])
        return name, dict(moves[name][0])
