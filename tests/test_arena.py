"""The Arena's two whole-robot knobs (size, total mass) on top of the existing variants, and its job path
(bench with a scene, compare with one variant, replay of either robot in the same world)."""

from __future__ import annotations

import pytest

from talaria_bench import compare
from talaria_bench.runtime import Runtime
from talaria_bench.spec import SpecError

from test_webapi import PREFIX, client, get, post, wait_job  # noqa: F401  (the fixture and helpers)


@pytest.fixture
def spider(tmp_path):
    rt = Runtime(overrides={"data_dir": tmp_path / "data"})
    return rt.robot("spider8")


def _total(spec):
    return sum(p.mass for p in spec.parts)


def test_scale_multiplies_lengths_and_the_volume_of_the_mass(spider):
    big = compare.build_variant(spider, {"name": "big", "set": {"@scale": 1.3}})
    assert big.part("body").size == pytest.approx(tuple(v * 1.3 for v in spider.part("body").size))
    assert _total(big) == pytest.approx(_total(spider) * 1.3 ** 3, rel=0.02)
    small = compare.build_variant(spider, {"name": "small", "set": {"@scale": 0.6}})
    assert small.part("body").size == pytest.approx(tuple(v * 0.6 for v in spider.part("body").size))


def test_total_mass_sets_the_weight_and_wins_over_the_volume_rule(spider):
    heavy = compare.build_variant(spider, {"name": "heavy", "set": {"@mass_total": 400}})
    assert _total(heavy) == pytest.approx(400, abs=0.5)
    assert heavy.part("body").size == spider.part("body").size
    both = compare.build_variant(spider, {"name": "both", "set": {"@scale": 1.3, "@mass_total": 400}})
    assert _total(both) == pytest.approx(400, abs=0.5) and both.part("body").size[0] == pytest.approx(13.0)


def test_servo_knob_is_the_existing_override(spider):
    v = compare.build_variant(spider, {"name": "mg", "set": {"parts.*.joint.servo": "MG90S"}})
    assert {p.joint.servo.name for p in v.joint_parts} == {"MG90S"}


@pytest.mark.parametrize("bad", [{"@scale": 9}, {"@scale": 0.1}, {"@scale": "wide"}, {"@mass_total": 1},
                                 {"@mass_total": "heavy"}, {"@mass_total": 10**7}])
def test_out_of_range_knobs_are_refused(spider, bad):
    with pytest.raises((ValueError, SpecError)):
        compare.build_variant(spider, {"name": "bad", "set": bad})


def test_a_scale_of_one_changes_nothing(spider):
    same = compare.build_variant(spider, {"name": "same", "set": {"@scale": 1.0}})
    assert same.hash() == spider.hash()


def test_arena_runs_one_robot_alone_without_replacing_its_report_card(client):
    before = get(client, "/robots/spider8/report")[1]["report"]["origin"]
    code, job = post(client, "/compare", {"robot": "spider8", "scenes": ["ramp_10"], "quick": True,
                                          "variants": [{"name": "same", "set": {"@scale": 1}}]})
    assert code == 200
    done = wait_job(client, job["job_id"])
    assert done["status"] == "done", done.get("log_tail")
    card = done["result"]["reports"]["base"]["scenes"][0]
    assert card["id"] == "ramp_10" and card["runs"] == 10
    seed = card["metric"]["median_seed"]
    trace = client.post(PREFIX + "/trace", json={"robot": "spider8", "scene": "ramp_10", "seed": seed}).json()
    assert trace["trace"]["frames"] and trace["meta"]["tilt_deg"] == 10
    assert get(client, "/robots/spider8/report")[1]["report"]["origin"] == before      # a compare saves no report


def test_arena_compares_a_scaled_variant_in_the_same_world(client):
    variant = {"name": "x1.3 size", "set": {"@scale": 1.3}}
    code, job = post(client, "/compare", {"robot": "spider8", "scenes": ["ramp_10"], "quick": True, "variants": [variant]})
    assert code == 200
    done = wait_job(client, job["job_id"])
    assert done["status"] == "done", done.get("log_tail")
    res = done["result"]
    assert [v["name"] for v in res["variants"]] == ["base", "x1.3 size"]
    assert res["variants"][1]["set"] == {"@scale": 1.3}
    row = res["rows"][0]
    assert [s for s, _ in row["outcomes"]["base"]] == [s for s, _ in row["outcomes"]["x1.3 size"]]   # same seeds
    seed = res["reports"]["base"]["scenes"][0]["metric"]["median_seed"]
    base = client.post(PREFIX + "/trace", json={"robot": "spider8", "scene": "ramp_10", "seed": seed}).json()
    big = client.post(PREFIX + "/trace", json={"robot": "spider8", "scene": "ramp_10", "seed": seed,
                                               "job_id": job["job_id"], "variant": "x1.3 size"}).json()
    assert base["trace"]["frames"] and big["trace"]["frames"]
    assert big["trace"]["parts"][0]["size_m"] == pytest.approx([v * 1.3 for v in base["trace"]["parts"][0]["size_m"]])


def test_arena_refuses_a_bad_knob_with_a_message(client):
    code, job = post(client, "/compare", {"robot": "spider8", "scenes": ["flat"], "quick": True,
                                          "variants": [{"name": "huge", "set": {"@scale": 99}}]})
    if code == 200 and job.get("ok"):                      # accepted at start, refused by the job
        done = wait_job(client, job["job_id"])
        assert done["status"] == "failed"
    else:
        assert not job.get("ok", False)
