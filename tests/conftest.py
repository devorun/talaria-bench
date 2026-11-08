"""Load the plugin folder as the package ``talaria_bench`` (its name has a dash) and give every test its
own HERMES_HOME, so nothing reads or writes the real ~/.hermes."""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = PLUGIN_ROOT / "examples" / "robots"


def _load_plugin_package() -> None:
    if "talaria_bench" in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        "talaria_bench", PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["talaria_bench"] = module
    spec.loader.exec_module(module)


_load_plugin_package()


@pytest.fixture(autouse=True)
def hermes_home(tmp_path, monkeypatch):
    home = tmp_path / "hermes-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


@pytest.fixture(scope="session")
def caduceus():
    from talaria_bench.spec import load_spec

    return load_spec(EXAMPLES / "caduceus.yaml")


@pytest.fixture(scope="session")
def spider():
    from talaria_bench.spec import load_spec

    return load_spec(EXAMPLES / "spider8.yaml")


MINI = {
    "talaria": 1,
    "name": "mini",
    "parts": [
        {"name": "body", "shape": "box", "size": [10, 10, 4], "mass": 200, "material": "pla"},
        {"name": "leg", "parent": "body", "shape": "box", "size": [2, 2, 8], "mass": 20, "material": "pla",
         "ground_contact": True,
         "joint": {"axis": "pitch", "anchor": [0, 0, -2], "offset": [0, 0, -4], "range": [-60, 60], "servo": "SG90"}},
    ],
    "moves": {"kick": {"frames": [{"ms": 300, "joints": {"leg": 30}}]}},
}


@pytest.fixture
def mini_data():
    """A small valid spec as a plain dict (a fresh deep copy per test)."""
    return copy.deepcopy(MINI)
