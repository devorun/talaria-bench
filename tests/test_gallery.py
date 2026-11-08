from pathlib import Path

import pytest

from talaria_bench import scenes
from talaria_bench.simrun import run_move, run_worlds
from talaria_bench.spec import load_spec, parse_spec
from talaria_bench.worlds import World

ROBOTS = Path(__file__).resolve().parents[1] / "examples" / "robots"
NEW = ("desk-biped4", "dog12", "humanoid16", "arm6")


@pytest.fixture(scope="module")
def gallery():
    return {name: load_spec(ROBOTS / f"{name}.yaml") for name in NEW}


@pytest.mark.parametrize("name", NEW)
def test_new_robots_load_and_stand(gallery, name):
    spec = gallery[name]
    assert spec.family and spec.role and spec.title
    r = run_move(spec, None, World.nominal(), 3.0)
    assert not r.fell, r.fall_reason


def test_gallery_metadata(gallery):
    assert gallery["arm6"].base == "fixed" and gallery["arm6"].payload_part == "hand"
    assert len(gallery["dog12"].joint_names) == 12 and len(gallery["humanoid16"].joint_names) == 16
    assert 1200 <= gallery["dog12"].total_mass_g <= 1800 and 800 <= gallery["humanoid16"].total_mass_g <= 1200
    assert 150 <= gallery["desk-biped4"].total_mass_g <= 200
    assert gallery["dog12"].bench["walk_move"] == "trot"
    assert scenes.applicable(gallery["arm6"], "push") == (False, "the base is fixed to the table")
    assert not scenes.applicable(gallery["humanoid16"], "flat")[0]


@pytest.mark.slow
def test_desk_biped_walk_acceptance(gallery):
    rs = run_worlds(gallery["desk-biped4"], "walk", 8.0, list(range(10)))
    assert sum(not r.fell and r.steady_m >= 0.05 for r in rs) >= 7


@pytest.mark.slow
def test_dog_trot_acceptance(gallery):
    rs = run_worlds(gallery["dog12"], "trot", 8.0, list(range(10)))
    assert sum(not r.fell and r.steady_m >= 0.10 for r in rs) >= 8


@pytest.mark.slow
def test_humanoid_safe_and_risky_dances(gallery):
    seeds = list(range(20))
    safe = sum(r.fell for r in run_worlds(gallery["humanoid16"], "dance_safe", None, seeds))
    risky = sum(r.fell for r in run_worlds(gallery["humanoid16"], "dance_risky", None, seeds))
    assert safe <= 2 and risky >= 10


def _tiny_arm(base="fixed"):
    return parse_spec({
        "talaria": 1, "name": "tiny-arm", "base": base, "payload_part": "hand",
        "bench": {"payload_steps_g": [0, 20, 3000]},
        "parts": [
            {"name": "base", "shape": "box", "size": [8, 8, 2], "mass": 300, "ground_contact": True},
            {"name": "link", "parent": "base", "shape": "box", "size": [2, 2, 10], "mass": 30,
             "joint": {"axis": "pitch", "anchor": [0, 0, 1], "offset": [0, 0, 5], "range": [-90, 90], "servo": "MG90S"}},
            {"name": "hand", "parent": "link", "shape": "box", "size": [2, 2, 2], "mass": 10, "ground_contact": True,
             "pos": [0, 0, 6]}],
        "moves": {"reach": {"frames": [{"ms": 600, "hold": 300, "joints": {"link": -60}},
                                       {"ms": 600, "joints": {"link": 0}}]}}})


def test_payload_scene_pass_and_fail_logic():
    spec = _tiny_arm()
    assert scenes.payload_move(spec) == "reach"
    job = scenes.run_scene(spec, "payload", 0)
    steps = job["metrics"]["steps"]
    assert [s["grams"] for s in steps] == [0, 20, 3000]
    assert steps[0]["ok"] and steps[1]["ok"] and not steps[2]["ok"]
    assert job["metric"] == 20 and job["passed"] is True
    assert job["reason"].startswith("at 3000 g:")
    assert steps[2]["max_peak_pct"] >= 80


def test_payload_scene_needs_a_payload_part(spider):
    assert scenes.applicable(spider, "payload") == (False, "the robot has no payload_part")


def test_free_base_arm_can_be_pushed():
    assert scenes.applicable(_tiny_arm("free"), "push")[0]
    assert "base" in _tiny_arm().canonical() and "base" not in _tiny_arm("free").canonical()


def test_gallery_command_lists_every_robot():
    import importlib.util

    spec = importlib.util.spec_from_file_location("devcli_test", Path(__file__).resolve().parents[1] / "devcli.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = {r["name"]: r for r in mod.gallery_rows()}
    assert set(NEW) | {"caduceus", "spider8"} <= set(rows)
    assert rows["arm6"]["base"] == "fixed" and rows["dog12"]["servos"] == 12
