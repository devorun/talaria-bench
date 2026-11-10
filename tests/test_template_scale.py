"""Templates at 0.5x to 2x of their default size: the robot builds, stands, and its replay has frames. A robot whose
servos cannot hold it up (a 50 cm quadruped on SG90s) is replayable too and says so when it is made."""

from __future__ import annotations

import itertools
import json
import math

import numpy as np
import pytest

from talaria_bench import simrun, spec as specmod, templates
from talaria_bench.runtime import Runtime
from talaria_bench.tools import TalariaTools

SCALES = (0.5, 1.0, 2.0)


def _params(tname, combo, scale):
    fields = templates.FIELDS[tname]
    options = [f for f in fields if isinstance(f[3], list)]
    params = {"name": f"scaled_{tname}", "_template": tname}
    for f, value in zip(options, combo):
        params[f[0]] = value
    for key, _label, default, unit in fields:
        if unit == "cm":
            if tname == "quadruped" and params.get("servos") == 12:
                default = 25                       # the 12-servo dog is built on a 25 cm body
            params[key] = round(default * scale_value(scale), 3)
    return params


def scale_value(scale):
    return scale


def _cases():
    for tname, fields in templates.FIELDS.items():
        options = [f[3] for f in fields if isinstance(f[3], list)]
        for combo in itertools.product(*options) if options else [()]:
            for scale in SCALES:
                yield pytest.param(tname, combo, scale, id=f"{tname}-{'-'.join(map(str, combo)) or 'x'}-{scale}")


@pytest.mark.parametrize("tname,combo,scale", list(_cases()))
def test_template_stands_and_replays_at_every_scale(tname, combo, scale):
    raw, _notes = templates.build(tname, _params(tname, combo, scale))
    spec = specmod.parse_spec(raw)
    r = simrun.run_move(spec, None, seconds=0.5, record=True)       # hold the home pose
    frames = r.trace["frames"]
    assert not r.fell, f"{tname} {combo} x{scale} collapses: {r.fall_reason}"
    assert len(frames) >= 10
    z = np.array([[part[2] for part in frame] for frame in frames])
    assert np.isfinite(z).all()
    assert z.min() > -0.005, "a part sank into the floor"
    assert math.isfinite(sum(p.mass for p in spec.parts))


def test_the_12_servo_quadruped_defaults_to_servos_that_hold_it():
    """The form used to send the 8-servo default (SG90) along with 12 servos; the template picks by size."""
    raw, _ = templates.build("quadruped", {"name": "big_dog", "_template": "quadruped", "servos": 12,
                                           "body_length": 50})
    spec = specmod.parse_spec(raw)
    assert {p.joint.servo.name for p in spec.joint_parts} == {"MG996R"}
    r = simrun.run_move(spec, None, seconds=0.5)
    assert not r.fell


@pytest.fixture
def too_weak():
    raw, _ = templates.build("quadruped", {"name": "weak_dog", "_template": "quadruped", "servos": 12,
                                           "body_length": 50, "servo": "SG90"})
    return specmod.parse_spec(raw)


def test_a_robot_that_cannot_stand_is_recorded_and_says_so(too_weak):
    r = simrun.run_move(too_weak, "walk", record=True)
    assert r.fell and r.fell_at_s == 0.0 and "cannot stand" in r.fall_reason
    frames = r.trace["frames"]
    assert len(frames) >= 30, "the collapse has to be replayable (it used to have no frames at all)"
    body = [frame[0][2] for frame in frames]
    assert body[0] > body[-1] + 0.1                                 # it goes down
    assert all(math.isfinite(v) for frame in frames for part in frame for v in part)
    assert min(part[2] for frame in frames for part in frame) > -0.005


def test_recorded_frames_of_a_standing_robot_start_after_settling():
    """The settling frames are only kept for a robot that collapses there: a standing robot's trace is the same
    as before (frame 0 is the settled pose, the move follows)."""
    raw, _ = templates.build("quadruped", {"name": "ok_dog", "_template": "quadruped"})
    spec = specmod.parse_spec(raw)
    with_trace = simrun.run_move(spec, "walk", record=True)
    plain = simrun.run_move(spec, "walk")
    assert not with_trace.fell
    assert with_trace.forward_m == plain.forward_m and with_trace.max_tilt_deg == plain.max_tilt_deg
    first, later = with_trace.trace["frames"][0], with_trace.trace["frames"][1]
    assert abs(first[0][2] - later[0][2]) < 0.02                  # standing, not falling from the drop height


def test_robot_define_warns_when_the_servos_cannot_hold_the_robot(tmp_path):
    rt = Runtime(overrides={"data_dir": tmp_path / "data"})
    tools = TalariaTools(rt)
    try:
        weak = json.loads(tools.handlers()["robot_define"]({"template": "quadruped", "params": {
            "name": "weak_dog", "servos": 12, "body_length": 50, "servo": "SG90"}}))
        assert weak["ok"] and any("cannot hold the robot up" in w for w in weak["warnings"])
        fine = json.loads(tools.handlers()["robot_define"]({"template": "quadruped", "params": {
            "name": "fine_dog", "servos": 12, "body_length": 50}}))
        assert fine["ok"] and not any("cannot hold" in w for w in fine["warnings"])
    finally:
        tools.shutdown()
