"""One-click benchmark: every scene in many randomized worlds, in parallel, cached, deterministic.

``run_benchmark(spec)`` returns a JSON-able results dict (``format: talaria-bench/results``) that
``report.build_report`` turns into the report card. Every number is simulation.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from .builder import MODEL_VERSION
from .scenes import SCENE_VERSION, SCENES, applicable, decide_slippery, resolve_scenes, run_scene, walk_move
from .spec import Spec

RESULTS_FORMAT = "talaria-bench/results"
RESULTS_VERSION = 1
DEFAULT_WORLDS = 30
QUICK_WORLDS = 10

_WORKER_SPEC: Optional[Spec] = None


DATA_DIR: Optional[Path] = None      # set by register() to the data folder Hermes gives the plugin


def set_data_dir(path: Optional[Path | str]) -> None:
    """Where the plugin may keep data (Hermes: $HERMES_HOME/plugin-data/<plugin>). Never the code folder."""
    global DATA_DIR
    DATA_DIR = Path(path) if path else None


def default_cache_dir() -> Path:
    """$TALARIA_CACHE, else <plugin data dir>/cache when Hermes gave one, else ~/.cache/talaria-bench."""
    env = os.environ.get("TALARIA_CACHE")
    if env:
        return Path(env)
    if DATA_DIR is not None:
        return DATA_DIR / "cache"
    return Path.home() / ".cache" / "talaria-bench"


def default_workers() -> int:
    return max(1, min(8, (os.cpu_count() or 2) - 1))


def move_hash(spec: Spec) -> str:
    """Hash of everything besides the spec physics that changes a scene result."""
    walk = walk_move(spec)
    blob = json.dumps({"moves": spec.moves, "walk": walk, "bench": spec.bench}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def job_key(spec: Spec, scene_id: str, seed: int) -> str:
    blob = json.dumps([SCENE_VERSION, MODEL_VERSION, spec.hash(), move_hash(spec), scene_id, int(seed)])
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def _cache_get(cache_dir: Optional[Path], key: str) -> Optional[dict]:
    if cache_dir is None:
        return None
    path = cache_dir / "jobs" / key[:2] / f"{key}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def replace_quietly(tmp: Path, path: Path, tries: int = 5) -> bool:
    """``os.replace`` for files other processes may be reading: on Windows a reader that has ``path`` open
    makes the replace fail with PermissionError. Retry briefly; on failure leave ``path`` as it was and
    return False (callers only write advisory files: progress and the result cache)."""
    for attempt in range(tries):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))
    return False


def _cache_put(cache_dir: Optional[Path], key: str, job: dict) -> None:
    if cache_dir is None:
        return
    path = cache_dir / "jobs" / key[:2] / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(job), encoding="utf-8")
    if not replace_quietly(tmp, path):
        tmp.unlink(missing_ok=True)          # another process has the same result cached already


def _init_worker(spec: Spec) -> None:
    global _WORKER_SPEC
    _WORKER_SPEC = spec


def _worker(task: tuple[str, int]) -> dict:
    return run_scene(_WORKER_SPEC, task[0], task[1])


def write_progress(path: Optional[Path | str], state: dict) -> None:
    """Progress JSON for the dashboard. Best effort: an update the reader blocks is skipped, never fatal."""
    if path is None:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    replace_quietly(tmp, path)


# Official move worlds: the preflight's seeds (preflight.SEED_BASE) and world count (preflight.DEFAULT_WORLDS).
MOVE_SEED_BASE = 5000
MOVE_WORLDS = 60
MOVE_QUICK_WORLDS = 30


def run_benchmark(spec: Spec, scenes: Optional[list[str]] = None, worlds: int = DEFAULT_WORLDS, seed: int = 0,
                  quick: bool = False, progress: Optional[Callable[[int, int, str], None]] = None,
                  workers: Optional[int] = None, cache_dir: Optional[Path | str] = "default",
                  progress_file: Optional[Path | str] = None, traces: bool = True) -> dict[str, Any]:
    """Run ``scenes`` (ids or families; default all) in worlds ``seed .. seed+worlds-1``.

    ``quick`` uses 10 worlds. ``cache_dir=None`` disables the result cache. ``progress(done, total,
    scene)`` is called as jobs finish; ``progress_file`` gets the same as JSON (for the dashboard)."""
    t_start = time.perf_counter()
    if quick:
        worlds = QUICK_WORLDS
    scene_ids = resolve_scenes(scenes, spec)
    if "slippery" in scene_ids and "flat" not in scene_ids:
        scene_ids = ["flat"] + scene_ids          # slippery is judged against the flat median
    cache = default_cache_dir() if cache_dir == "default" else (Path(cache_dir) if cache_dir else None)
    pfile = Path(progress_file) if progress_file else None
    seeds = list(range(seed, seed + worlds))
    # Standing moves are scored on the official preflight worlds (the same seeds and count as move_check),
    # so the report card, the gallery and the preflight screen show one number per move. Quick runs use
    # the first QUICK move worlds and are labelled quick.
    move_seeds = list(range(MOVE_SEED_BASE + seed, MOVE_SEED_BASE + seed + (MOVE_QUICK_WORLDS if quick else MOVE_WORLDS)))

    def seeds_for(sid: str) -> list[int]:
        return move_seeds if sid.startswith("move:") else seeds

    jobs: dict[tuple[str, int], dict] = {}
    todo: list[tuple[str, int]] = []
    na: dict[str, str] = {}
    for sid in scene_ids:
        ok, why = applicable(spec, sid)
        if not ok:
            na[sid] = why
            continue
        for s in seeds_for(sid):
            hit = _cache_get(cache, job_key(spec, sid, s))
            if hit is not None:
                jobs[(sid, s)] = hit
            else:
                todo.append((sid, s))
    total = len(jobs) + len(todo)
    done = len(jobs)
    state = {"done": done, "total": total, "scene": None, "started": datetime.now(timezone.utc).isoformat(),
             "robot": spec.name, "finished": False}
    write_progress(pfile, state)

    def finished(task: tuple[str, int], job: dict) -> None:
        nonlocal done
        jobs[task] = job
        _cache_put(cache, job_key(spec, *task), job)
        done += 1
        state.update(done=done, scene=task[0])
        if progress:
            progress(done, total, task[0])
        if done == total or done % 5 == 0:
            write_progress(pfile, state)

    n_workers = workers or default_workers()
    if todo and n_workers > 1 and len(todo) > 2:
        from .procpool import pool as make_pool

        # push jobs are the slowest: start them first so the pool stays busy to the end
        order = sorted(todo, key=lambda t: 0 if t[0] == "push" else 1)
        with make_pool(n_workers, "bench", "_init_worker", spec) as pool:
            futures = {pool.submit(_worker, t): t for t in order}
            for fut in as_completed(futures):
                finished(futures[fut], fut.result())
    else:
        for task in todo:
            finished(task, run_scene(spec, *task))
    t_jobs = time.perf_counter() - t_start

    by_scene: dict[str, list[dict]] = {sid: [jobs[(sid, s)] for s in seeds_for(sid)] for sid in scene_ids
                                       if sid not in na}
    flat_median = None
    if "flat" in by_scene:
        flat_median = float(np.median([j["metric"] for j in by_scene["flat"]]))
    if "slippery" in by_scene:
        decide_slippery(by_scene["slippery"], flat_median)

    trace_out: dict[str, dict] = {}
    if traces:
        for sid, js in by_scene.items():
            trace_out[sid] = _pick_traces(spec, sid, js)
    state.update(finished=True, done=total)
    write_progress(pfile, state)
    return {
        "format": RESULTS_FORMAT, "version": RESULTS_VERSION, "simulation": True,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "robot": {**spec.summary(), "hash": spec.hash(), "source": str(spec.source) if spec.source else None,
                  "limitations": list(spec.limitations), "world_ranges": _world_ranges(spec)},
        "settings": {"scenes": scene_ids, "worlds": worlds, "seed": seed, "quick": quick,
                     "move_worlds": len(move_seeds), "move_seed": move_seeds[0],
                     "walk_move": walk_move(spec), "bench": dict(spec.bench), "scene_version": SCENE_VERSION},
        "not_applicable": na,
        "scenes": by_scene,
        "flat_median_cm": flat_median,
        "traces": trace_out,
        "timing": {"jobs": total, "computed": len(todo), "cached": total - len(todo), "workers": n_workers,
                   "seconds_jobs": round(t_jobs, 2), "seconds_total": round(time.perf_counter() - t_start, 2)},
    }


def _world_ranges(spec: Spec) -> dict[str, list[float]]:
    from .worlds import merged_ranges

    return {k: [round(v[0], 4), round(v[1], 4)] for k, v in merged_ranges(spec.world_ranges).items()}


def _sort_value(job: dict) -> float:
    m = job.get("metric")
    if job["scene"] == "push":
        return 9.0 if m is None else float(m)         # no tip up to the largest push = best
    return -1e9 if m is None else float(m)


def _pick_traces(spec: Spec, scene_id: str, jobs: list[dict]) -> dict[str, Any]:
    """Re-run the median-world and the worst run with recording, for the 3D viewer."""
    ranked = sorted(jobs, key=_sort_value)
    worst = next((j for j in jobs if j.get("fell")), ranked[0])
    median = ranked[len(ranked) // 2]
    out = {}
    for label, job in (("median", median), ("worst", worst)):
        rec = run_scene(spec, scene_id, job["seed"], record=True)
        out[label] = {"seed": job["seed"], "metric": job.get("metric"), "passed": job.get("passed"),
                      "reason": job.get("reason"), "note": rec.get("trace_note"), "trace": rec.get("trace")}
    return out


def save_results(results: dict, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results), encoding="utf-8")
    return path


def load_results(path: Path | str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != RESULTS_FORMAT:
        raise ValueError(f"{path} is not a Talaria Bench results file")
    return data


__all__ = ["run_benchmark", "save_results", "load_results", "job_key", "default_cache_dir", "SCENES"]
