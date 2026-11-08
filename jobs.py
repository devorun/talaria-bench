"""Background benchmark and comparison jobs.

A job runs ``devcli.py bench|compare`` in its own process (the benchmark forks worker processes, which
must not happen inside a multi-threaded Hermes process). Each job has a folder under ``jobs/<id>/``
with ``job.json``, ``progress.json`` and ``log.txt``; results land in ``reports/``. Nothing waits for a
human: a job either finishes or fails, and its status says which.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import yaml

from .runtime import PLUGIN_ROOT, Runtime

DEVCLI = PLUGIN_ROOT / "devcli.py"


class JobManager:
    def __init__(self, runtime: Runtime):
        self.rt = runtime
        self._procs: dict[str, subprocess.Popen] = {}

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        # Hermes adds its package folders to sys.path at start-up; hand them to the child explicitly.
        env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p and Path(p).exists())
        env["TALARIA_CACHE"] = str(self.rt.folder("cache"))
        env.pop("PYTHONHOME", None)
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
        vfile = self.rt.folder("jobs") / f"variants-{uuid.uuid4().hex[:8]}.yaml"
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
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True
