import re
import subprocess
import sys
from pathlib import Path

import yaml

import talaria_bench

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_stub():
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    assert manifest["name"] == "talaria-bench"
    assert manifest["manifest_version"] == 2
    deps = manifest["python_dependencies"]
    assert {re.split(r"[<>=!~]", d)[0] for d in deps} == {"mujoco", "numpy", "pyyaml"}
    for dep in deps:   # Hermes warns about any entry without an upper bound
        assert "<" in dep, dep


def test_register_needs_no_heavy_imports():
    calls = []

    class Ctx:
        def __getattr__(self, name):
            return lambda *a, **k: calls.append(name)

    talaria_bench.register(Ctx())


def test_devcli_runs(tmp_path):
    out = subprocess.run([sys.executable, str(ROOT / "devcli.py"), "run", "examples/robots/spider8.yaml",
                          "--move", "walk", "--seconds", "2"], capture_output=True, text=True, cwd=tmp_path,
                         timeout=120)
    assert out.returncode == 0, out.stderr
    assert "[simulation]" in out.stdout and "no fall" in out.stdout
    bad = subprocess.run([sys.executable, str(ROOT / "devcli.py"), "run", "examples/robots/spider8.yaml",
                          "--move", "moonwalk"], capture_output=True, text=True, cwd=tmp_path, timeout=120)
    assert bad.returncode == 2 and "no move 'moonwalk'" in bad.stderr
