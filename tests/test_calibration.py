import ast

import pytest
import yaml

from talaria_bench import calibration as cal
from talaria_bench import motion
from talaria_bench.spec import SpecError, parse_spec


def test_expressions_are_arithmetic_only():
    tree = cal.compile_expr("min(a, 2) * (b - 1) / 4 + -a ** 2", {"a", "b"})
    assert cal.eval_expr(tree, {"a": 3.0, "b": 5.0}) == pytest.approx(min(3, 2) * 4 / 4 - 9)
    assert cal.eval_expr(cal.compile_expr(0.5, set()), {}) == 0.5
    for bad in ("__import__('os')", "a.real", "open('x')", "a if b else 1", "[a]", "unknown + 1"):
        with pytest.raises((ValueError, SyntaxError)):
            cal.compile_expr(bad, {"a", "b"})


def test_set_path_follows_part_names_and_creates_overrides(mini_data):
    cal.set_path(mini_data, "parts.leg.joint.anchor.2", -3.0)
    cal.set_path(mini_data, "parts.leg.joint.servo.backlash_deg", 2.5)
    cal.set_path(mini_data, "materials.pla.solref.0", 0.01)
    cal.set_path(mini_data, "tether.at.1", 4.0)
    mini_data["tether"]["part"], mini_data["tether"]["max_force_n"] = "body", 0.1
    assert mini_data["parts"][1]["joint"]["servo"] == {"model": "SG90", "backlash_deg": 2.5}
    assert mini_data["tether"]["at"] == [0.0, 4.0]
    mini_data["tether"]["at"].append(0.0)
    spec = parse_spec(mini_data)
    assert spec.part("leg").joint.anchor[2] == -3.0
    assert spec.part("leg").joint.servo.backlash_deg == 2.5
    assert spec.materials["pla"].solref == (0.01, 1.0)
    with pytest.raises(KeyError):
        cal.set_path(mini_data, "parts.tail.mass", 1)


def test_latin_hypercube_is_stratified_and_reproducible():
    params = {"a": (0.0, 1.0), "b": (10.0, 20.0)}
    sets = cal.latin_hypercube(8, params, seed=3)
    assert sets == cal.latin_hypercube(8, params, seed=3)
    assert sorted(int(s["a"] * 8) for s in sets) == list(range(8))
    assert all(10 <= s["b"] <= 20 for s in sets)


def test_violations_measure_how_far_off():
    m = {"fell": False, "yaw_deg": -20.0, "forward_cm": 1.0, "rise_cm.arm": 0.5}
    req = {"fell": False, "yaw_deg": {"abs_max": 5}, "forward_cm": {"abs_max": 3}, "rise_cm.arm": {"min": 2}}
    v = {x["metric"]: x["miss"] for x in cal.violations(m, req)}
    assert set(v) == {"yaw_deg", "rise_cm.arm"}
    assert v["yaw_deg"] == pytest.approx(3.0)
    assert cal.violations({"fell": True}, {"fell": False})[0]["miss"] == 1.0


def _write_config(tmp_path, mini_data, **extra):
    (tmp_path / "mini.yaml").write_text(yaml.safe_dump(mini_data), encoding="utf-8")
    config = {"spec": "mini.yaml", "samples": 6, "seed": 1, "bins": 2,
              "parameters": {"body_g": [150, 250], "friction": [0.3, 0.7]},
              "apply": {"parts.body.mass": "body_g"},
              "world": {"friction": "friction"},
              "targets": {"kick": {"move": "kick", "speed": "1", "require": {
                  "fell": False, "max_roll_change_deg": {"max": 5}, "lift_cm.leg": {"min": -1}}}}}
    config.update(extra)
    path = tmp_path / "mini.calibration.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_calibrate_end_to_end_small(tmp_path, mini_data):
    config = cal.load_config(_write_config(tmp_path, mini_data))
    report = cal.calibrate(config)
    assert report["samples"] == 6 and len(report["rows"]) == 6
    assert 0 <= report["acceptance_rate"] <= 1
    assert set(report["parameter_tables"]) == {"body_g", "friction"}
    assert len(report["parameter_tables"]["body_g"]["bins"]) == 2
    row = report["rows"][0]
    assert "max_pitch_change_deg" in row["targets"]["kick"]["metrics"]
    assert "rise_cm.leg" in row["targets"]["kick"]["metrics"]
    spec, world = cal.build_sample(config, row["values"])
    assert spec.part("body").mass == pytest.approx(row["values"]["body_g"], abs=1e-6)
    assert world.friction == pytest.approx(row["values"]["friction"])
    if report["accepted"]:
        assert report["central_accepted"]["ok"]
    out = cal.validate(config, parse_spec(mini_data), worlds=3)
    assert out["kick"]["worlds"] == 3 and "max_roll_change_deg" in out["kick"]["distributions"]


def test_config_errors_are_listed(tmp_path, mini_data):
    path = _write_config(tmp_path, mini_data, targets={"kick": {"move": "kick", "require": {"wobble": {"max": 1},
                                                                                        "lift_cm": {"min": 1}}}},
                         world={"gravity": "friction"}, apply={"parts.body.mass": "nope * 2"})
    with pytest.raises(cal.CalibrationError) as info:
        cal.load_config(path)
    text = str(info.value)
    assert "unknown metric 'wobble'" in text and "lift_cm needs a part" in text
    assert "not a World field" in text and "unknown name 'nope'" in text


def test_shipped_caduceus_calibration_files_load():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "examples" / "robots"
    for name in ("caduceus.calibration.yaml", "caduceus.calibration-stage2.yaml"):
        config = cal.load_config(root / name)
        assert set(config.targets) == {"wave", "walk"}
        assert isinstance(config.targets["wave"].speed, ast.Expression)


def test_linear_easing_moves_at_one_constant_speed():
    joints = {"a": {"min": -90, "max": 90, "home": 0, "max_speed": 500.0},
              "b": {"min": -90, "max": 90, "home": 0, "max_speed": 500.0}}
    move = {"easing": "linear", "frames": [{"ms": 1000, "joints": {"a": 40, "b": 20}}]}
    names, rows = motion.trajectory(move, joints, 1.2, 0.01)
    a = [r[0] for r in rows]
    b = [r[1] for r in rows]
    assert a[50] == pytest.approx(20, abs=0.5)          # 40 deg/s, linear
    assert b[50] == pytest.approx(20, abs=0.5)          # same speed, already arrived
    assert b[25] == pytest.approx(10, abs=0.5)
    smooth = motion.trajectory({**move, "easing": "smoothstep"}, joints, 1.2, 0.01)[1]
    assert smooth[25][1] < 10 * 0.8                     # eases in
    with pytest.raises(motion.MoveError):
        motion.check_move({**move, "easing": "bouncy"}, joints)


def test_spec_overrides_validate(mini_data):
    mini_data["materials"] = {"pla": {"solref": [0.001, 1]}}
    mini_data["parts"][1]["friction"] = 9
    mini_data["parts"][1]["joint"]["servo"] = {"model": "SG90", "torque_kgcm": 5}
    with pytest.raises(SpecError) as info:
        parse_spec(mini_data)
    text = str(info.value)
    assert "solref must be" in text and "friction factor must be" in text and "with model, only" in text


def test_overrides_change_the_hash(mini_data):
    base = parse_spec(mini_data).hash()
    mini_data["materials"] = {"pla": {"friction": 0.5}}
    assert parse_spec(mini_data).hash() != base
