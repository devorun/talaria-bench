"""Every template builds a valid spec that stands in simulation, with estimates when masses are unknown."""

from __future__ import annotations

import pytest

from talaria_bench import templates
from talaria_bench.simrun import run_move
from talaria_bench.spec import SpecError, parse_spec

CASES = [
    ("block_robot", {}),
    ("block_robot", {"arm_length": 23.5, "leg_length": 16, "body_width": 16.5, "mass_g": 400, "servo": "MG90S"}),
    ("biped4", {}),
    ("quadruped", {"servos": 8}),
    ("quadruped", {"servos": 12}),
    ("hexapod", {"servos": 12}),
    ("hexapod", {"servos": 18}),
    ("arm", {"joints": 6}),
    ("arm", {"joints": 4}),
    ("humanoid", {}),
]


@pytest.mark.parametrize("template,params", CASES, ids=[f"{t}-{i}" for i, (t, _) in enumerate(CASES)])
def test_template_builds_validates_and_stands(template, params):
    raw, notes = templates.build(template, {"name": "t_" + template, **params})
    spec = parse_spec(raw)
    assert spec.name == "t_" + template and spec.joint_parts and notes
    r = run_move(spec, None, None, 3.0)
    assert not r.fell, f"{template} {params}: {r.fall_reason}"
    if template == "arm":
        assert spec.base == "fixed" and len(spec.joint_parts) == params["joints"]


def test_unknown_masses_are_estimates_with_a_wide_range():
    raw, notes = templates.build("block_robot", {"name": "est"})
    assert any("estimate" in n for n in notes) and raw["worlds"]["mass_scale"] == [0.7, 1.3]
    raw2, notes2 = templates.build("block_robot", {"name": "known", "mass_g": 400})
    assert abs(sum(p["mass"] for p in raw2["parts"]) - 400) < 1 and "worlds" not in raw2


def test_template_input_errors_are_listed():
    with pytest.raises(SpecError) as e:
        templates.build("block_robot", {"name": "x", "arm_length": -3, "servo": "NOPE"})
    assert len(e.value.problems) >= 2
    with pytest.raises(SpecError):
        templates.build("dragon", {"name": "x"})
    with pytest.raises(SpecError):
        templates.build("arm", {"name": "Bad Name"})
    assert set(templates.describe()) == set(templates.TEMPLATES)
