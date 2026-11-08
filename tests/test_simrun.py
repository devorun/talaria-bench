import math

import pytest

from talaria_bench.simrun import run_move, run_worlds, steady_progress, summarize
from talaria_bench.spec import parse_spec
from talaria_bench.worlds import World


@pytest.mark.parametrize("name", ["caduceus", "spider"])
def test_robots_stand_still_for_3_seconds(request, name):
    spec = request.getfixturevalue(name)
    r = run_move(spec, None, World.nominal(), 3.0)
    assert not r.fell, r.fall_reason
    assert abs(r.forward_m) < 0.005 and abs(r.yaw_deg) < 2 and r.max_tilt_deg < 5


def test_steady_progress_ignores_a_lurch():
    assert steady_progress([0.0, 0.1, 0.1, 0.1, 0.1]) == 0.0
    assert steady_progress([0.0, 0.025, 0.05, 0.075, 0.1]) == pytest.approx(0.1)
    assert steady_progress([]) == 0.0


def test_trace_shape(spider):
    r = run_move(spider, "walk", World.nominal(), 1.0, record=True)
    t = r.trace
    assert t["fps"] == 30 and t["units"] == "m"
    assert [p["name"] for p in t["parts"]] == [p.name for p in spider.parts]
    assert 30 <= len(t["frames"]) <= 32
    for frame in (t["frames"][0], t["frames"][-1]):
        assert len(frame) == len(spider.parts)
        for x, y, z, qw, qx, qy, qz in frame:
            assert math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz) == pytest.approx(1.0, abs=1e-3)
    assert "trace" not in r.to_dict()


def test_same_seed_same_result(caduceus):
    a = run_move(caduceus, "walk", World.random(7, caduceus.joint_names), 3.0)
    b = run_move(caduceus, "walk", World.random(7, caduceus.joint_names), 3.0)
    assert a.to_dict() == b.to_dict()
    c = run_move(caduceus, "walk", World.random(8, caduceus.joint_names), 3.0)
    assert c.to_dict() != a.to_dict()


def test_world_random_is_reproducible_and_respects_ranges():
    w1 = World.random(3, ["a", "b"], {"friction": [0.2, 0.2], "offset_deg": [-1, 1]})
    w2 = World.random(3, ["a", "b"], {"friction": [0.2, 0.2], "offset_deg": [-1, 1]})
    assert w1 == w2 and w1.friction == 0.2 and w1.seed == 3
    assert all(-1 <= v <= 1 for v in w1.offsets_deg.values())
    g = World(floor_tilt_deg=0).gravity()
    assert g == pytest.approx((0, 0, -9.81))


def test_forbidden_floor_contact_is_a_fall_with_a_reason(mini_data):
    mini_data["parts"][1]["ground_contact"] = False
    r = run_move(parse_spec(mini_data), None, World.nominal(), 1.0)
    assert r.fell and r.fall_reason.startswith("part 'leg' touched the floor") and "settling" in r.fall_reason
    assert r.steady_m == 0.0


def test_loads_and_speeds_are_reported(spider):
    r = run_move(spider, {"frames": [{"ms": 20, "joints": {"knee_fl": 60, "hip_fr": 75}}]}, World.nominal(), 1.0)
    servo_speed = spider.part("knee_fl").joint.servo.speed_dps(spider.voltage)
    assert not r.fell
    for name in ("knee_fl", "hip_fr"):
        load = r.joints[name]
        assert 0 < load.peak_ratio <= 1.0 + 1e-6
        assert 100 < load.peak_speed_dps <= servo_speed * 1.05   # the servo never turns faster than it can


def test_calibrated_caduceus_waves_level_in_the_nominal_world(caduceus):
    """Calibrated against video (docs/calibration-caduceus.md): the arm lifts, the body stays level."""
    r = run_move(caduceus, "wave", World.nominal())
    assert r.seconds == pytest.approx((1980 + 3000 + 2895) / 1000 + 1.0)
    assert not r.fell
    assert r.ground["right_arm"].lift_cm - r.ground["right_arm"].start_cm > 2.0
    assert r.max_roll_change_deg < 5 and r.max_pitch_change_deg < 10 and abs(r.yaw_deg) < 5
    assert 0.1 < r.joints["right_arm"].peak_ratio <= 1.0


def test_caduceus_walking_is_a_declared_limitation(caduceus):
    """The rigid model cannot walk Caduceus (it tips backwards); the spec says so."""
    notes = caduceus.limitations_for("locomotion")
    assert notes and "not reliable" in notes[0]
    assert caduceus.limitations_for("standing") == []


def test_caduceus_arm_moves_safe_vs_risky(caduceus):
    """Preflight showcase: both arms thrown up together tips the robot in many worlds, one at a time does not."""
    seeds = list(range(1000, 1020))
    both = sum(r.fell for r in run_worlds(caduceus, "arms_up_both", None, seeds))
    alternating = sum(r.fell for r in run_worlds(caduceus, "arms_up_alternating", None, seeds))
    assert both >= 3 and alternating == 0


def test_roll_and_pitch_are_split(spider):
    r = run_move(spider, None, World(floor_tilt_deg=0), 1.0)
    assert r.max_roll_change_deg < 1 and r.max_pitch_change_deg < 1
    assert r.max_tilt_change_deg >= max(r.max_roll_change_deg, r.max_pitch_change_deg) - 1e-6


def test_tether_plug_point_makes_a_turning_moment(mini_data):
    mini_data["parts"][1]["joint"]["anchor"] = [3, 0, -2]
    mini_data["parts"].append({"name": "leg2", "parent": "body", "shape": "box", "size": [2, 2, 8], "mass": 20,
                               "ground_contact": True, "joint": {"axis": "pitch", "anchor": [-3, 0, -2],
                                                                 "offset": [0, 0, -4], "range": [-60, 60],
                                                                 "servo": "SG90"}})
    mini_data["parts"].append({"name": "leg3", "parent": "body", "shape": "box", "size": [2, 2, 8], "mass": 20,
                               "ground_contact": True, "pos": [0, 4, -6]})
    mini_data["parts"].append({"name": "leg4", "parent": "body", "shape": "box", "size": [2, 2, 8], "mass": 20,
                               "ground_contact": True, "pos": [0, -4, -6]})
    centered = dict(mini_data, tether={"part": "body", "max_force_n": 3.0})
    off_axis = dict(mini_data, tether={"part": "body", "max_force_n": 3.0, "at": [-5, 5, 0]})
    world = World(friction=0.05, tether_scale=1.0, tether_dir_deg=-90)
    a = run_move(parse_spec(centered), None, world, 1.0)
    b = run_move(parse_spec(off_axis), None, world, 1.0)
    assert abs(a.yaw_deg) < 1.0
    assert abs(b.yaw_deg) > 3 * max(abs(a.yaw_deg), 1.0)


@pytest.mark.slow
def test_spider_walk_acceptance(spider):
    """Plan acceptance: >= 10 cm steady progress in 8 s and no fall in >= 90% of 20 random worlds."""
    results = run_worlds(spider, "walk", 8.0, list(range(20)))
    s = summarize(results)
    assert s["no_fall_rate"] >= 0.9, s
    assert s["steady_cm_median"] >= 10.0, s
    assert s["steady_cm_p10"] >= 5.0, s
