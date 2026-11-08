import copy

import pytest
import yaml

from talaria_bench.spec import SpecError, load_spec, parse_spec


def problems_for(data) -> str:
    with pytest.raises(SpecError) as info:
        parse_spec(data)
    return "\n".join(info.value.problems)


def test_mini_spec_parses(mini_data):
    spec = parse_spec(mini_data)
    assert spec.root.name == "body"
    assert spec.joint_names == ["leg"]
    assert spec.total_mass_g == 220
    assert spec.part("leg").joint.axis == (0.0, -1.0, 0.0)
    assert spec.part("leg").joint.max_speed == pytest.approx(60 / 0.09667, rel=1e-3)


def test_examples_load(caduceus, spider):
    assert caduceus.joint_names == ["left_arm", "left_leg", "right_leg", "right_arm"]
    assert caduceus.photo is not None and caduceus.photo.is_file()
    assert caduceus.tether == {"part": "head", "max_force_n": 0.09, "at": [-1.4, 0.0, 2.9]}
    assert {"wave", "walk"} <= set(caduceus.moves)
    assert caduceus.moves["wave"]["easing"] == "linear"
    assert caduceus.part("left_arm").joint.servo.backlash_deg == 2.0
    assert caduceus.materials["foam"].solref == (0.023, 1.0)
    assert caduceus.world_ranges["friction"] == (0.33, 0.63)
    assert len(spider.joint_names) == 8
    assert spider.total_mass_g == pytest.approx(250)
    assert spider.moves["walk"]["repeat"] is True


@pytest.mark.parametrize("mutate, expected", [
    (lambda d: d["parts"][1].update(parent="bdy"), "parent 'bdy' does not exist"),
    (lambda d: d["parts"][1].update(size=[2, 0, 8]), "every size must be > 0"),
    (lambda d: d["parts"][1].update(size=[2, 8]), "box size must be [x depth, y width, z height]"),
    (lambda d: d["parts"][1].update(size=[20, 20, 800]), "not millimetres"),
    (lambda d: d["parts"][1].update(mass=0), "mass must be a number > 0"),
    (lambda d: d["parts"][1]["joint"].update(range=[-200, 60]), "-180 <= min < max <= 180"),
    (lambda d: d["parts"][1]["joint"].update(range=[30, -30]), "-180 <= min < max <= 180"),
    (lambda d: d["parts"][1]["joint"].update(servo="XY123"), "unknown servo 'XY123'"),
    (lambda d: d["parts"][1]["joint"].update(servo={"torque_kgcm": 2}), "inline servo needs speed_s_per_60"),
    (lambda d: d["parts"][1]["joint"].update(axis="sideways"), "axis must be pitch, roll, yaw"),
    (lambda d: d["parts"][1]["joint"].update(home=90), "home 90 is outside the range"),
    (lambda d: d["parts"][1]["joint"].update(max_speed=5000), "faster than the servo can turn"),
    (lambda d: d["parts"].append(copy.deepcopy(d["parts"][1])), "duplicate name"),
    (lambda d: d["parts"][0].update(joint=d["parts"][1]["joint"]), "root part (no parent) cannot have a joint"),
    (lambda d: d["parts"][1].update(colour="#fff"), "unknown field(s) colour"),
    (lambda d: d["parts"][1].update(material="steel"), "material must be one of"),
    (lambda d: d["parts"][1].pop("joint"), "needs a joint (moving part) or pos"),
    (lambda d: d["parts"].append({"name": "x", "shape": "sphere", "size": [1], "mass": 5}), "found body, x"),
    (lambda d: d.update(talaria=2), "talaria: must be 1"),
    (lambda d: d.update(name="My Robot"), "name: lowercase"),
    (lambda d: d["moves"]["kick"]["frames"][0]["joints"].update(arm=10), "no joint named 'arm'"),
    (lambda d: d["moves"]["kick"]["frames"][0]["joints"].update(leg=99), "leg=99 is outside its range"),
    (lambda d: d.update(tether={"part": "tail", "max_force_n": 1}), "tether: part 'tail' does not exist"),
    (lambda d: d.update(worlds={"gravity": [1, 2]}), "unknown range 'gravity'"),
    (lambda d: d.update(worlds={"friction": [0.9, 0.2]}), "friction must be [low, high]"),
])
def test_validation_errors(mini_data, mutate, expected):
    mutate(mini_data)
    assert expected in problems_for(mini_data)


def test_cycle_is_reported(mini_data):
    mini_data["parts"].append({"name": "a", "parent": "b", "shape": "sphere", "size": [1], "mass": 5, "pos": [0, 0, 0]})
    mini_data["parts"].append({"name": "b", "parent": "a", "shape": "sphere", "size": [1], "mass": 5, "pos": [0, 0, 0]})
    assert "cycle or are cut off from the root: a, b" in problems_for(mini_data)


def test_every_problem_is_listed(mini_data):
    mini_data["parts"][1]["mass"] = -1
    mini_data["parts"][1]["joint"]["servo"] = "nope"
    with pytest.raises(SpecError) as info:
        parse_spec(mini_data)
    assert len(info.value.problems) >= 2
    assert "invalid robot spec" in str(info.value)


def test_yaml_errors_are_readable(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("talaria: 1\nparts: [\n", encoding="utf-8")
    with pytest.raises(SpecError) as info:
        load_spec(bad)
    assert "not valid YAML (line" in info.value.problems[0]
    with pytest.raises(SpecError):
        load_spec(tmp_path / "missing.yaml")


def test_hash_is_stable_across_order_comments_and_cosmetics(tmp_path, mini_data):
    base = parse_spec(mini_data).hash()
    shuffled = copy.deepcopy(mini_data)
    shuffled["parts"].reverse()
    shuffled["parts"][0] = dict(reversed(list(shuffled["parts"][0].items())))
    assert parse_spec(shuffled).hash() == base

    cosmetic = copy.deepcopy(mini_data)
    cosmetic.update(title="Mini!", description="changed")
    cosmetic["parts"][0]["color"] = "#123456"
    cosmetic["moves"]["wiggle"] = {"frames": [{"ms": 200, "joints": {"leg": -10}}]}
    assert parse_spec(cosmetic).hash() == base

    path = tmp_path / "mini.yaml"
    path.write_text("# a comment\n" + yaml.safe_dump(mini_data, sort_keys=True), encoding="utf-8")
    assert load_spec(path).hash() == base

    heavier = copy.deepcopy(mini_data)
    heavier["parts"][1]["mass"] = 21
    assert parse_spec(heavier).hash() != base
    other_servo = copy.deepcopy(mini_data)
    other_servo["parts"][1]["joint"]["servo"] = "MG90S"
    assert parse_spec(other_servo).hash() != base


def test_inline_servo_and_named_vector_axis(mini_data):
    joint = mini_data["parts"][1]["joint"]
    joint["servo"] = {"torque_kgcm": 3.0, "speed_s_per_60": 0.12, "backlash_deg": 0.5}
    joint["axis"] = [0, 0, 2]
    spec = parse_spec(mini_data)
    j = spec.part("leg").joint
    assert j.axis == (0.0, 0.0, 1.0) and j.axis_name is None
    assert j.servo.torque_kgcm() == 3.0
    assert j.max_speed == pytest.approx(500.0)


def test_fixed_part(mini_data):
    mini_data["parts"].append({"name": "foot", "parent": "leg", "shape": "sphere", "size": [1], "mass": 3,
                               "material": "rubber", "ground_contact": True, "pos": [0, 0, -4]})
    spec = parse_spec(mini_data)
    assert spec.part("foot").joint is None and spec.part("foot").pos == (0.0, 0.0, -4.0)
    assert [p.name for p in spec.parts] == ["body", "leg", "foot"]


def test_look_is_appearance_only(mini_data):
    from talaria_bench.spec import SpecError, parse_spec

    plain = parse_spec(mini_data)
    styled = parse_spec(dict(mini_data, look={"material": "aluminum", "accent": "#ff7a1a", "badge": "v2",
                                              "decals": [{"part": "body", "kind": "oled"}],
                                              "showcase": {"joints": {"leg": 20}}}))
    assert styled.look["badge"] == "v2" and styled.look["showcase"]["joints"] == {"leg": 20.0}
    assert styled.hash() == plain.hash()                      # never part of the physics hash
    for bad in ({"material": "gold"}, {"accent": "orange"}, {"decals": [{"part": "nope", "kind": "oled"}]},
                {"badge": "far too long"}, {"sparkle": True}):
        with pytest.raises(SpecError):
            parse_spec(dict(mini_data, look=bad))
