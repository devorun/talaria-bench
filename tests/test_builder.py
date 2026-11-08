import math

import mujoco
import numpy as np
import pytest

from talaria_bench.builder import PLAY_SUFFIX, SATURATE_DEG, base_model, build_mjcf, make_model
from talaria_bench.materials import MATERIALS
from talaria_bench.spec import parse_spec
from talaria_bench.worlds import World


@pytest.mark.parametrize("name", ["caduceus", "spider"])
def test_examples_compile_and_mass_matches(request, name):
    spec = request.getfixturevalue(name)
    model, info, xml = base_model(spec)
    assert "<compiler angle=\"degree\"/>" in xml
    assert info.joint_names == spec.joint_names
    assert model.nu == len(spec.joint_names)
    assert float(np.sum(model.body_mass)) * 1000 == pytest.approx(spec.total_mass_g, rel=1e-6)


def test_play_hinge_and_servo_actuator(caduceus):
    model, _, _ = base_model(caduceus)
    arm = caduceus.part("left_arm")
    play = model.joint("left_arm" + PLAY_SUFFIX)
    half = arm.joint.servo.backlash_deg / 2
    assert np.degrees(model.jnt_range[play.id]) == pytest.approx([-half, half])
    assert np.allclose(model.jnt_axis[play.id], model.jnt_axis[model.joint("left_arm").id])
    act = model.actuator("left_arm")
    torque = arm.joint.servo.torque_nm(caduceus.voltage)
    assert model.actuator_forcerange[act.id] == pytest.approx([-torque, torque])
    # ctrl acts on qpos in radians even though the compiler reads degrees
    assert model.actuator_ctrlrange[act.id] == pytest.approx(np.radians(arm.joint.range))
    assert model.actuator_gainprm[act.id, 0] * math.radians(SATURATE_DEG) == pytest.approx(torque)


def test_root_is_dropped_onto_the_floor(spider):
    model, info, _ = base_model(spider)
    data = mujoco.MjData(model)
    for p in spider.joint_parts:
        data.qpos[model.jnt_qposadr[model.joint(p.name).id]] = math.radians(p.joint.home)
    mujoco.mj_forward(model, data)
    feet = [model.geom(f"foot_{leg}").id for leg in ("fl", "fr", "hl", "hr")]
    bottoms = [data.geom_xpos[g][2] - model.geom_size[g][0] for g in feet]
    assert min(bottoms) == pytest.approx(0.0005, abs=1e-4)
    assert info.root_z > 0.05


def test_foam_is_softer_than_pla():
    assert MATERIALS["foam"].solref[0] > 2 * MATERIALS["pla"].solref[0]
    assert MATERIALS["foam"].solimp[2] > MATERIALS["pla"].solimp[2]
    for m in MATERIALS.values():
        assert m.solref[0] >= 2 * 0.002


def test_world_is_applied_without_touching_the_cached_model(spider):
    base, _, _ = base_model(spider)
    before = base.actuator_forcerange.copy()
    world = World(friction=0.3, mass_scale=1.2, torque_scale=0.5, floor_tilt_deg=10, floor_tilt_dir_deg=0)
    model, _ = make_model(spider, world)
    assert model.actuator_forcerange == pytest.approx(before * 0.5)
    assert np.sum(model.body_mass) == pytest.approx(np.sum(base.body_mass) * 1.2)
    assert model.geom_friction[model.geom("foot_fl").id, 0] == pytest.approx(0.3 * MATERIALS["rubber"].friction)
    assert model.opt.gravity[0] > 1.0
    assert base.actuator_forcerange == pytest.approx(before)


def _limb_center_after(axis: str, offset, angle: float):
    data = {"talaria": 1, "name": "probe", "parts": [
        {"name": "body", "shape": "box", "size": [10, 10, 10], "mass": 500},
        {"name": "limb", "parent": "body", "shape": "box", "size": [2, 2, 2], "mass": 10,
         "joint": {"axis": axis, "anchor": [0, 0, 0], "offset": offset, "range": [-90, 90], "servo": "MG90S"}}]}
    spec = parse_spec(data)
    model, _, _ = base_model(spec)
    d = mujoco.MjData(model)
    d.qpos[model.jnt_qposadr[model.joint("limb").id]] = math.radians(angle)
    mujoco.mj_forward(model, d)
    return d.geom_xpos[model.geom("limb").id] - d.xpos[model.body("body").id]


def test_joint_sign_conventions():
    # +pitch swings a limb's lower end forward (+x)
    assert _limb_center_after("pitch", [0, 0, -5], 30)[0] > 0.02
    # +roll moves the lower end to +y
    assert _limb_center_after("roll", [0, 0, -5], 30)[1] > 0.02
    # +yaw turns the front (+x) to the left (+y)
    assert _limb_center_after("yaw", [5, 0, 0], 30)[1] > 0.02


def test_overlapping_parts_are_excluded_with_a_warning(mini_data):
    mini_data["parts"].append({"name": "twin", "parent": "body", "shape": "box", "size": [2, 2, 8], "mass": 20,
                               "joint": {"axis": "pitch", "anchor": [0, 0.5, -2], "offset": [0, 0, -4],
                                         "range": [-60, 60], "servo": "SG90"}})
    xml, info = build_mjcf(parse_spec(mini_data))
    assert ("leg", "twin") in info.excluded_pairs
    assert '<exclude body1="leg" body2="twin"/>' in xml
    assert any("overlap" in w for w in info.warnings)
