"""Worker pools that work with every multiprocessing start method (fork, forkserver, spawn).

The plugin folder has a dash in its name, so ``talaria_bench`` is not importable from ``sys.path``: a
``spawn`` or ``forkserver`` worker (the default on Windows and macOS, and on Linux from Python 3.14) cannot
unpickle ``talaria_bench.bench._worker`` by itself. Each worker therefore starts with ``exec`` of a small
bootstrap (``exec`` is a builtin, so it pickles by reference) that loads the plugin package under the same
name as in the parent and then calls the module's own initializer.

``fork`` is used only on Linux and only from a single-threaded process (a benchmark job's own subprocess);
anywhere else, for example inside the multi-threaded Hermes gateway, workers are spawned.
``TALARIA_MP_START`` forces a start method (tests use it to prove ``spawn`` works).
"""

from __future__ import annotations

import multiprocessing as mp
import os
import pickle
import sys
import threading
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent
PACKAGE = __name__.rpartition(".")[0]

_BOOT = """
import importlib, importlib.util, pickle, sys, types
name, root = _TB["package"], _TB["root"]
if name not in sys.modules:
    parts = name.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[:i])
        if parent not in sys.modules:
            stub = types.ModuleType(parent)
            stub.__path__ = []
            sys.modules[parent] = stub
    spec = importlib.util.spec_from_file_location(name, root + "/__init__.py", submodule_search_locations=[root])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
target = importlib.import_module(name + "." + _TB["module"])
getattr(target, _TB["init"])(*pickle.loads(_TB["args"]))
"""


def start_method() -> str:
    forced = os.environ.get("TALARIA_MP_START", "").strip()
    if forced:
        return forced
    if sys.platform.startswith("linux") and threading.active_count() == 1 and "fork" in mp.get_all_start_methods():
        return "fork"
    return "spawn"


def pool(workers: int, module: str, init: str, *args: Any) -> ProcessPoolExecutor:
    """A process pool whose workers run ``<package>.<module>.<init>(*args)`` once at start."""
    boot = {"package": PACKAGE, "root": str(PLUGIN_ROOT), "module": module, "init": init,
            "args": pickle.dumps(args)}
    return ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context(start_method()),
                               initializer=exec, initargs=(_BOOT, {"_TB": boot}))
