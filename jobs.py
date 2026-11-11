"""Background benchmark and comparison jobs.

A job runs ``devcli.py bench|compare`` in its own process, which starts the worker pool (see
``procpool.py``), so no pool is ever created inside the multi-threaded Hermes process. Requests are bounded
(10-200 worlds per scene, known scene ids only, at most ``MAX_RUNNING`` jobs at once). Each job has a folder
under ``jobs/<id>/`` with ``job.json``, ``progress.json`` and ``log.txt``; results land in ``reports/``.
Nothing waits for a human: a job either finishes or fails, and its status says which.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import yaml

from .runtime import PLUGIN_ROOT, Runtime

DEVCLI = PLUGIN_ROOT / "devcli.py"
MIN_WORLDS, MAX_WORLDS = 10, 200      # per scene, as in the tool schemas
MAX_RUNNING = 2                       # each job already uses every core but one
_JOB_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")

# A job's environment is built from this allowlist, never copied from Hermes: the Hermes process holds the
# provider API keys and other secrets, and a benchmark needs none of them.
ENV_ALLOW = (
    "PATH", "HOME", "USERPROFILE", "LANG", "TMPDIR", "TEMP", "TMP", "TALARIA_MP_START",
    "PYTHONUTF8", "PYTHONIOENCODING",  # Hermes runs Python in UTF-8 mode; the job's log is read back as UTF-8
    "MUJOCO_GL",                       # MuJoCo reads its display backend when it is imported (headless setups)
)
ENV_ALLOW_PREFIXES = ("LC_",)
ENV_ALLOW_WINDOWS = ("SYSTEMROOT",)    # Python on Windows needs it (sockets, the system's crypto and DLLs)


def job_env(environ: Optional[dict[str, str]] = None) -> dict[str, str]:
    """The allowlisted part of ``environ`` (default: this process's environment)."""
    source = os.environ if environ is None else environ
    names = set(ENV_ALLOW) | (set(ENV_ALLOW_WINDOWS) if os.name == "nt" else set())
    return {k: v for k, v in source.items()
            if k.upper() in names or k.upper().startswith(ENV_ALLOW_PREFIXES)}


class JobManager:
    def __init__(self, runtime: Runtime):
        self.rt = runtime
        self._procs: dict[str, subprocess.Popen] = {}

    def _check_request(self, spec, scenes: Optional[list[str]], worlds: Optional[int]) -> Optional[list[str]]:
        """Refuse what would run for hours or reach the job command line unvalidated; returns scene ids."""
        running = [i for i, p in self._procs.items() if p.poll() is None]
        if len(running) >= MAX_RUNNING:
            raise ValueError(f"{len(running)} benchmark jobs are already running ({', '.join(running)}); wait for "
                             "one to finish (bench_status) before starting another")
        if worlds is not None:
            try:
                n = int(worlds)
            except (TypeError, ValueError):
                raise ValueError(f"worlds must be a whole number from {MIN_WORLDS} to {MAX_WORLDS}") from None
            if not MIN_WORLDS <= n <= MAX_WORLDS:
                raise ValueError(f"worlds must be from {MIN_WORLDS} to {MAX_WORLDS} per scene (got {worlds})")
        if not scenes:
            return None
        if not isinstance(scenes, list) or not all(isinstance(s, str) for s in scenes):
            raise ValueError("scenes must be a list of scene ids or families")
        from .scenes import resolve_scenes

        return resolve_scenes(scenes, spec)      # KeyError for anything else, including option-like strings

    def _env(self) -> dict[str, str]:
        env = job_env()
        # Hermes adds its package folders to sys.path at start-up; hand them to the child explicitly.
        env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p and Path(p).exists())
        env["TALARIA_CACHE"] = str(self.rt.folder("cache"))
        return env

    def _start(self, kind: str, robot: str, args: list[str], meta: dict[str, Any]) -> dict[str, Any]:
        job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        folder = self.rt.folder("jobs") / job_id
        folder.mkdir(parents=True)
        out = self.rt.folder("reports") / f"{robot}-{kind}-{job_id}.json"
        progress = folder / "progress.json"
        cmd = [sys.executable, str(DEVCLI), kind, *args, "--out", str(out), "--progress-file", str(progress)]
        log = open(folder / "log.txt", "w", encoding="utf-8")
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                cwd=str(self.rt.data_dir()), env=self._env(), start_new_session=True)
        log.close()
        self._procs[job_id] = proc
        job = {"id": job_id, "kind": kind, "robot": robot, "out": str(out), "pid": proc.pid,
               "started": time.time(), "command": cmd[1:], **meta}
        (folder / "job.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
        return job

    def start_bench(self, robot: str, scenes: Optional[list[str]] = None, worlds: Optional[int] = None,
                    quick: bool = False) -> dict[str, Any]:
        spec = self.rt.robot(robot)
        scenes = self._check_request(spec, scenes, worlds)
        args = [str(spec.source)]
        if scenes:
            args += ["--scenes", *scenes]
        if quick:
            args.append("--quick")
        elif worlds:
            args += ["--worlds", str(int(worlds))]
        return self._start("bench", robot, args, {"scenes": scenes, "worlds": worlds, "quick": quick})

    def start_compare(self, robot: str, variants: list[dict[str, Any]], scenes: Optional[list[str]] = None,
                      worlds: Optional[int] = None, quick: bool = False) -> dict[str, Any]:
        spec = self.rt.robot(robot)
        scenes = self._check_request(spec, scenes, worlds)
        vfile =self.rt.folder("jobs") / f"variants-{uuid.uuid4().hex[:8]}.yaml"
        vfile.write_text(yaml.safe_dump({"variants": variants}), encoding="utf-8")
        args = [str(spec.source), "--variants", str(vfile)]
        if scenes:
            args += ["--scenes", *scenes]
        if quick:
            args.append("--quick")
        elif worlds:
            args += ["--worlds", str(int(worlds))]
        return self._start("compare", robot, args, {"variants": [v.get("name") for v in variants]})

    def job(self, job_id: str) -> dict[str, Any]:
        if not _JOB_ID_RE.match(str(job_id)):
            raise KeyError(f"no job {job_id!r}")
        folder = self.rt.folder("jobs") / job_id
        try:
            job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise KeyError(f"no job {job_id!r}") from None
        progress = {}
        try:
            progress = json.loads((folder / "progress.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        proc = self._procs.get(job_id)
        code = proc.poll() if proc is not None else None
        out = Path(job["out"])
        done_file = out.with_suffix(".report.md") if job["kind"] == "bench" else out.with_suffix(".md")
        if done_file.is_file():
            status = "done"
        elif proc is not None and code is None:
            status = "running"
        elif proc is None and _alive(job.get("pid")):
            status = "running"
        else:
            status = "failed"
        job.update(status=status, progress=progress, report=str(done_file) if done_file.is_file() else None)
        if status == "failed":
            try:
                job["log_tail"] = (folder / "log.txt").read_text(encoding="utf-8")[-1500:]
            except OSError:
                job["log_tail"] = ""
        return job

    def jobs(self) -> list[dict[str, Any]]:
        out = []
        for folder in sorted(self.rt.folder("jobs").glob("*"), reverse=True):
            if folder.is_dir():
                try:
                    out.append(self.job(folder.name))
                except KeyError:
                    continue
        return out

    def latest_report(self, robot: str) -> Optional[Path]:
        """Newest finished benchmark report for ``robot`` (this machine), else the bundled one."""
        mine = sorted(self.rt.folder("reports").glob(f"{robot}-bench-*.report.md"), key=lambda p: p.stat().st_mtime)
        if mine:
            return mine[-1]
        bundled = PLUGIN_ROOT / "examples" / "reports" / f"{robot}.report.md"
        return bundled if bundled.is_file() else None


def _alive(pid: Any) -> bool:
    """Whether process ``pid`` still runs. Never ``os.kill(pid, 0)`` on Windows: there it terminates the process."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        return _alive_windows(pid)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True                     # exists, owned by someone else
    except OSError:
        return False
    return True


def _alive_windows(pid: int) -> bool:
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)      # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)
