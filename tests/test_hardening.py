"""Regression tests from the independent review: worker pools under every start method, job limits and ids,
the Windows-safe process check, one resolution per gated play, and a clear error without MuJoCo."""

from __future__ import annotations

import json
import sys

import pytest

from talaria_bench import bench, hooks, jobs, preflight, procpool
from talaria_bench.runtime import Runtime
from talaria_bench.tools import TalariaTools


@pytest.fixture
def rt(tmp_path):
    runtime = Runtime(overrides={"data_dir": tmp_path / "data"})
    yield runtime
    bench.set_data_dir(None)


@pytest.fixture
def tools(rt):
    t = TalariaTools(rt)
    yield t
    t.shutdown()


def call(tools, name, args):
    return json.loads(tools.handlers()[name](args))


# Worker pools ----------------------------------------------------------------------------------------


def _metrics(res):
    return {sid: [(j["seed"], j["metric"], j.get("passed")) for j in js] for sid, js in res["scenes"].items()}


@pytest.mark.parametrize("method", ["spawn", "forkserver"])
def test_benchmark_pool_works_without_fork(spider, monkeypatch, method):
    """Windows and macOS spawn workers; a spawned worker must still find the plugin package and the spec."""
    if method not in __import__("multiprocessing").get_all_start_methods():
        pytest.skip(f"{method} not available here")
    monkeypatch.setenv("TALARIA_MP_START", method)
    assert procpool.start_method() == method
    pooled = bench.run_benchmark(spider, scenes=["flat"], worlds=3, workers=2, cache_dir=None, traces=False)
    serial = bench.run_benchmark(spider, scenes=["flat"], worlds=3, workers=1, cache_dir=None, traces=False)
    assert pooled["timing"]["workers"] == 2
    assert _metrics(pooled) == _metrics(serial)


def test_fork_only_from_a_single_threaded_linux_process(monkeypatch):
    monkeypatch.delenv("TALARIA_MP_START", raising=False)
    monkeypatch.setattr(procpool.threading, "active_count", lambda: 3)       # e.g. inside the Hermes gateway
    assert procpool.start_method() == "spawn"
    monkeypatch.setattr(procpool.threading, "active_count", lambda: 1)
    monkeypatch.setattr(procpool.sys, "platform", "win32")
    assert procpool.start_method() == "spawn"
    monkeypatch.setattr(procpool.sys, "platform", "darwin")
    assert procpool.start_method() == "spawn"


# Jobs ------------------------------------------------------------------------------------------------


def test_alive_never_signals_a_process_on_windows(monkeypatch):
    """os.kill(pid, 0) terminates the process on Windows; the liveness check must not use it there."""
    def no_kill(*args):
        raise AssertionError("os.kill must not be called on Windows")

    seen = []
    monkeypatch.setattr(jobs.os, "kill", no_kill)
    monkeypatch.setattr(jobs, "_alive_windows", lambda pid: seen.append(pid) or True)
    monkeypatch.setattr(jobs.os, "name", "nt")
    try:
        assert jobs._alive(4242) is True
    finally:
        monkeypatch.undo()
    assert seen == [4242]
    assert jobs._alive("not a pid") is False and jobs._alive(0) is False


def test_bench_requests_are_bounded_and_validated(tools):
    huge = call(tools, "bench_run", {"robot": "spider8", "worlds": 100000})
    assert not huge["ok"] and "worlds must be from 10 to 200" in huge["error"]
    injected = call(tools, "bench_run", {"robot": "spider8", "scenes": ["--worlds", "100000"]})
    assert not injected["ok"] and "unknown scene" in injected["error"]
    bad = call(tools, "bench_compare", {"robot": "spider8", "worlds": 5000,
                                        "variants": [{"name": "h", "set": {"parts.body.mass": "+5"}}]})
    assert not bad["ok"] and "worlds" in bad["error"]
    assert not list(tools.rt.folder("jobs").iterdir())                # nothing was started


def test_running_jobs_are_capped(tools):
    class Running:
        def poll(self):
            return None

    tools.jobs._procs.update({"20261109-000000-aaaaaa": Running(), "20261109-000001-bbbbbb": Running()})
    out = call(tools, "bench_run", {"robot": "spider8", "quick": True})
    assert not out["ok"] and "already running" in out["error"]
    tools.jobs._procs.clear()


@pytest.mark.parametrize("job_id", ["../../etc", "..", "x/../../y", "20261109-000000-aaaaaa/../../z"])
def test_job_ids_cannot_leave_the_jobs_folder(tools, job_id):
    out = call(tools, "bench_status", {"job_id": job_id, "wait_s": 0})
    assert not out["ok"] and "no job" in out["error"]


# Gate ------------------------------------------------------------------------------------------------


def test_gated_play_resolves_the_move_once(rt, tools, monkeypatch):
    """The handler plays the exact move the gate approved; it does not look the move or spec up again."""
    move = {"frames": [{"ms": 800, "joints": {"left_arm": 40}}]}
    spec = rt.robot("caduceus")
    result = {"verdict": "pass", "tip": {"falls": 0, "rate": 0, "low": 0, "high": 0.06}, "reasons": [],
              "suggestions": [], "worlds": 60}
    key = preflight.approval_key(spec, move)
    preflight.ApprovalStore(rt.folder("approvals")).save(preflight.record(key, spec, "x", move, 1.0, result))
    calls = []
    real = hooks.requested_move

    def counting(*args, **kwargs):
        calls.append(args[1])
        return real(*args, **kwargs)

    monkeypatch.setattr(hooks, "requested_move", counting)
    out = call(tools, "robot_play", {"robot": "caduceus", "frames": move["frames"], "target": "virtual"})
    assert out["ok"], out
    assert calls == ["robot_play"]


# Failure behaviour -----------------------------------------------------------------------------------


def test_missing_mujoco_gives_an_install_hint(tools, monkeypatch):
    monkeypatch.setitem(sys.modules, "mujoco", None)
    out = call(tools, "move_check", {"robot": "caduceus", "move": "wave", "quick": True})
    assert not out["ok"] and "dependency is missing" in out["error"] and "--install-deps" in out["hint"]
