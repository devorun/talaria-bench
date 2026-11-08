"""Backend routes for the Talaria Bench Desktop page and dashboard tab, mounted by Hermes at
``/api/plugins/talaria-bench/``. The logic lives in ``webapi.py``; this file only finds the plugin
package (already loaded by Hermes in this process, or loaded here) and exposes ``router``."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_INIT = _ROOT / "__init__.py"


def _package():
    """The plugin package: the copy Hermes loaded (same __init__.py), else load it here."""
    for module in list(sys.modules.values()):
        try:
            if getattr(module, "__file__", None) and Path(module.__file__).resolve() == _INIT:
                return module
        except (OSError, TypeError, ValueError):
            continue
    name = "talaria_bench"
    if name in sys.modules:
        name = "talaria_bench_dashboard"
    spec = importlib.util.spec_from_file_location(name, _INIT, submodule_search_locations=[str(_ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _SettingsCtx:
    """Reads this plugin's settings the way ``ctx.get_config`` does, for a process where register() did
    not run (the plugin host normally runs both)."""

    def get_config(self, key, default=None):
        try:
            from hermes_cli.config import load_config_readonly
        except ImportError:
            return default
        cfg = load_config_readonly() or {}
        entry = ((cfg.get("plugins") or {}).get("entries") or {}).get("talaria-bench") or {}
        settings = entry.get("settings") or {}
        return settings.get(key, default)


def _build_router():
    pkg = _package()
    webapi = importlib.import_module(pkg.__name__ + ".webapi")
    runtime = getattr(pkg, "_RUNTIME", None)
    tools = getattr(pkg, "_TOOLS", None)
    if runtime is None:
        runtime_mod = importlib.import_module(pkg.__name__ + ".runtime")
        runtime = runtime_mod.Runtime(_SettingsCtx())
        tools = None
    return webapi.make_router(webapi.WebAPI(runtime, tools))


router = _build_router()
