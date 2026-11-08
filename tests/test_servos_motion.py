import pytest

from talaria_bench import motion, servos


def test_catalog_has_the_common_servos():
    for name in ("SG90", "MG90S", "MG996R", "DS3218"):
        model = servos.lookup(name.lower())
        assert model.torque_kgcm(4.8) > 0 and model.speed_dps() > 0 and model.mass_g > 0


def test_voltage_interpolation_and_clamping():
    mg = servos.lookup("MG90S")
    assert mg.torque_kgcm(4.8) == 1.8
    assert mg.torque_kgcm(6.0) == 2.2
    assert mg.torque_kgcm(5.4) == pytest.approx(2.0)
    assert mg.torque_kgcm(3.0) == 1.8 and mg.torque_kgcm(9.0) == 2.2
    assert mg.torque_nm(6.0) == pytest.approx(2.2 * 0.0980665)
    assert mg.speed_dps(4.8) == pytest.approx(600.0)


def test_unknown_servo_message_lists_catalog():
    with pytest.raises(servos.ServoError) as info:
        servos.resolve("XY1", where="joint")
    assert "SG90" in str(info.value) and "joint" in str(info.value)


JOINTS = {"a": {"min": -90, "max": 90, "home": 0, "max_speed": 100.0},
          "b": {"min": -10, "max": 10, "home": 0, "max_speed": 600.0}}


def test_plan_stretches_frames_to_the_speed_limit():
    plan = motion.plan_move([{"ms": 100, "joints": {"a": 50}}], JOINTS)
    assert plan["frames"][0]["ms"] == 500
    assert "slowed from 100 ms to 500 ms" in plan["warnings"][0]


def test_plan_rejects_out_of_range_and_unknown_joints():
    with pytest.raises(motion.MoveError) as info:
        motion.plan_move([{"ms": 100, "joints": {"b": 20, "c": 1}}], JOINTS)
    text = str(info.value)
    assert "b=20 is outside its range -10..10" in text and "no joint named 'c'" in text


def test_trajectory_respects_speed_limits():
    move = {"frames": [{"ms": 50, "joints": {"a": 80, "b": 10}}, {"ms": 50, "joints": {"a": -80, "b": -10}}]}
    dt = 0.01
    names, rows = motion.trajectory(move, JOINTS, 4.0, dt, repeat=True)
    for k, name in enumerate(names):
        limit = JOINTS[name]["max_speed"]
        steps = [abs(rows[i + 1][k] - rows[i][k]) / dt for i in range(len(rows) - 1)]
        # smoothstep peaks at 1.5 x the average speed the planner allows
        assert max(steps) <= 1.5 * limit + 1e-6


def test_trajectory_holds_end_pose_unless_repeating():
    move = {"frames": [{"ms": 200, "joints": {"a": 30}}, {"ms": 200, "joints": {"a": 0}}]}
    _, once = motion.trajectory(move, JOINTS, 2.0, 0.01)
    assert once[-1][0] == 0.0 and max(r[0] for r in once[100:]) == 0.0
    _, again = motion.trajectory(move, JOINTS, 2.0, 0.01, repeat=True)
    assert max(r[0] for r in again[100:]) > 25


def test_check_move_rejects_unknown_fields():
    with pytest.raises(motion.MoveError) as info:
        motion.check_move({"frames": [{"ms": 100, "joints": {"a": 1}}], "speedy": True}, JOINTS)
    assert "unknown field(s) speedy" in str(info.value)
