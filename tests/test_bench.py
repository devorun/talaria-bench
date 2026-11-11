import copy

import mujoco
import pytest

from talaria_bench import bench, compare, report, scenes
from talaria_bench.builder import base_model
from talaria_bench.simrun import run_move
from talaria_bench.spec import parse_spec
from talaria_bench.worlds import World

TOP_KEYS = {"format", "version", "simulation", "label", "created", "robot", "settings", "world_ranges", "scenes",
            "servo_note", "limitations", "timing", "summary"}
CARD_KEYS = {"id", "title", "family", "applicable", "status", "in_scope", "note", "conditions",
             "runs", "passed", "pass_rate", "metric", "failure_reasons", "falls", "loads"}


def test_scene_ids_and_families(spider, caduceus):
    assert scenes.resolve_scenes(["ramp"]) == ["ramp_5", "ramp_10", "ramp_15"]
    assert scenes.resolve_scenes(["moves"], caduceus) == ["move:wave", "move:arms_up_both", "move:arms_up_alternating"]
    assert "move:walk" not in scenes.resolve_scenes(None, spider)          # the walk is not a standing move
    with pytest.raises(KeyError):
        scenes.resolve_scenes(["lava"])


@pytest.mark.parametrize("sid", ["flat", "ramp_10", "obstacle_1cm", "slippery", "move:stand"])
def test_each_walk_scene_runs(spider, sid):
    job = scenes.run_scene(spider, sid, 3)
    assert job["applicable"] and job["scene"] == sid and job["seed"] == 3
    assert isinstance(job["metric"], float) and "world" in job and job["loads"]
    if sid != "slippery":
        assert isinstance(job["passed"], bool)


def test_scene_worlds(spider):
    ramp = scenes.world_for(spider, "ramp_15", 5)
    assert ramp.floor_tilt_deg == 15 and ramp.floor_tilt_dir_deg == 180
    g = ramp.gravity()
    assert g[0] < 0                       # downhill is behind the robot: it faces uphill
    slip = scenes.world_for(spider, "slippery", 5)
    assert 0.08 <= slip.effective_friction <= 0.15
    flat = scenes.world_for(spider, "flat", 5)
    assert flat.offsets_deg == slip.offsets_deg      # the same world seed is the same world in every scene


def test_slippery_friction_ignores_the_foot_material(spider):
    from talaria_bench.builder import make_model

    world = World(effective_friction=0.1)
    model, _ = make_model(spider, world)
    rubber = model.geom_friction[model.geom("foot_fl").id, 0]
    pla = model.geom_friction[model.geom("knee_fl").id, 0]
    assert rubber == pytest.approx(0.1) and pla == pytest.approx(0.1)


def test_push_measures_sliding(spider):
    job = scenes.run_scene(spider, "push", 1)
    slides = job["metrics"]["slides_cm"]
    assert set(slides) == set(scenes.PUSH_DIRECTIONS)
    assert all(v >= 0 for d in slides.values() for v in d.values())
    assert slides["left"]["0.5"] > slides["left"]["0.1"]


def test_cache_dir_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("TALARIA_CACHE", raising=False)
    bench.set_data_dir(None)
    assert bench.default_cache_dir() == bench.Path.home() / ".cache" / "talaria-bench"
    bench.set_data_dir(tmp_path / "plugin-data")
    assert bench.default_cache_dir() == tmp_path / "plugin-data" / "cache"
    monkeypatch.setenv("TALARIA_CACHE", str(tmp_path / "env"))
    assert bench.default_cache_dir() == tmp_path / "env"
    bench.set_data_dir(None)


def test_obstacle_bar_is_in_the_model(spider):
    terrain = (("box", "bar", 0.15, 0.0, 0.01, 0.01, 1.0, 0.01),)
    model, info, xml = base_model(spider, terrain)
    assert model.geom("bar").id >= 0 and 'name="bar"' in xml
    assert info.front_x > 0.05 and info.back_x < -0.05


def test_push_moves_the_robot(spider):
    still = run_move(spider, None, World.nominal(), 2.0)
    pushed = run_move(spider, None, World.nominal(), 2.0, pushes=[(0.5, 0.1, 5.0, 0.0, 0.0)])
    assert pushed.end_xy_m[0] - still.end_xy_m[0] > 0.01


def test_push_scene_on_a_robot_that_cannot_stand(mini_data):
    mini_data["parts"][1]["ground_contact"] = False
    job = scenes.run_scene(parse_spec(mini_data), "push", 0)
    assert job["passed"] is False and job["metric"] == scenes.PUSH_LEVELS[0]
    assert job["reason"].startswith("tips at a nudge")


def test_not_applicable_without_a_walk(mini_data):
    spec = parse_spec(mini_data)
    assert scenes.applicable(spec, "flat") == (False, "the robot has no walk move")
    assert scenes.run_scene(spec, "ramp_5", 0)["applicable"] is False
    assert scenes.applicable(spec, "push")[0] and scenes.applicable(spec, "move:kick")[0]


def test_slippery_rule_needs_the_flat_median():
    base = {"scene": "slippery", "applicable": True, "fell": False,
            "metrics": {"yaw_deg": 0.0, "fall_reason": None}}
    jobs = [dict(base, metric=6.0, metrics=dict(base["metrics"])),
            dict(base, metric=2.0, metrics=dict(base["metrics"])),
            dict(base, metric=1.0, metrics={"yaw_deg": 90.0, "fall_reason": None}),
            dict(base, metric=9.0, fell=True, metrics={"yaw_deg": 0.0, "fall_reason": "root tilted more than 60 deg"}),
            dict(base, metric=24.0, metrics=dict(base["metrics"]))]
    scenes.decide_slippery(jobs, flat_median_cm=10.0)
    assert [j["passed"] for j in jobs] == [True, False, False, False, False]
    assert [j["reason"] for j in jobs] == [None, "sliding", "spinning in place", "fell (tipped over)",
                                           "uncontrolled sliding"]
    assert jobs[0]["metrics"]["slide_cap_cm"] == 15.0
    scenes.decide_slippery(jobs[:1], flat_median_cm=None)
    assert jobs[0]["passed"] is False and jobs[0]["reason"] == "no flat progress to compare with"


def test_status_thresholds():
    assert [report.status_for(x) for x in (0.8, 0.79, 0.4, 0.39, None)] == ["green", "amber", "amber", "red", "n/a"]


def test_same_seed_same_scene_result(spider):
    assert scenes.run_scene(spider, "flat", 4) == scenes.run_scene(spider, "flat", 4)


def test_benchmark_cache_quick_and_progress(spider, tmp_path):
    seen = []
    first = bench.run_benchmark(spider, scenes=["move:stand"], quick=True, workers=1, cache_dir=tmp_path,
                                progress=lambda d, t, s: seen.append((d, t)), progress_file=tmp_path / "p.json",
                                traces=False)
    # standing moves run on the quick preflight worlds (30, seeds 5000+), not the 10 quick arena worlds
    assert first["settings"]["worlds"] == 10 and first["settings"]["move_worlds"] == 30
    assert first["timing"]["computed"] == 30 and seen[-1] == (30, 30)
    assert [j["seed"] for j in first["scenes"]["move:stand"]] == list(range(5000, 5030))
    assert (tmp_path / "p.json").read_text().count('"finished": true') == 1
    again = bench.run_benchmark(spider, scenes=["move:stand"], quick=True, workers=1, cache_dir=tmp_path, traces=False)
    assert again["timing"]["computed"] == 0 and again["timing"]["cached"] == 30
    assert again["scenes"] == first["scenes"]
    assert bench.job_key(spider, "move:stand", 1) != bench.job_key(spider, "move:stand", 2)


def test_parallel_matches_serial(spider):
    a = bench.run_benchmark(spider, scenes=["flat"], worlds=3, workers=1, cache_dir=None, traces=False)
    b = bench.run_benchmark(spider, scenes=["flat"], worlds=3, workers=3, cache_dir=None, traces=False)
    assert a["scenes"] == b["scenes"]


def test_report_schema_and_markdown(caduceus, tmp_path):
    results = bench.run_benchmark(caduceus, scenes=["flat", "move:wave"], worlds=2, workers=1, cache_dir=None)
    assert set(results["traces"]["flat"]) == {"median", "worst"}
    assert results["traces"]["move:wave"]["median"]["trace"]["fps"] == 30
    rep = report.build_report(results)
    assert set(rep) == TOP_KEYS and rep["simulation"] is True and "Simulation" in rep["label"]
    for card in rep["scenes"]:
        assert set(card) >= CARD_KEYS
    flat = next(c for c in rep["scenes"] if c["id"] == "flat")
    assert flat["status"] == "out_of_scope" and flat["in_scope"] is False and "does not guess" in flat["note"]
    wave = next(c for c in rep["scenes"] if c["id"] == "move:wave")
    assert wave["in_scope"] is True and wave["status"] in ("green", "amber", "red")
    md = report.to_markdown(rep)
    assert "OUT OF MODEL SCOPE" in md and "NOT RELIABLE" not in md and "(simulation)" in md and "stall torque is not a safe continuous torque" in md.lower()
    path = bench.save_results(results, tmp_path / "r.json")
    assert bench.load_results(path)["robot"]["name"] == "caduceus"


def test_variant_overrides(spider, caduceus):
    import yaml

    raw = yaml.safe_load(open(spider.source))
    data = compare.apply_overrides(raw, {"parts.*.joint.servo": "MG90S", "parts.body.mass": "+100"})
    v = parse_spec(data)
    assert {p.joint.servo.name for p in v.joint_parts} == {"MG90S"}
    assert v.part("body").mass == spider.part("body").mass + 100
    legs = compare.build_variant(caduceus, {"name": "legs", "set": {"parts.left_leg.size.2": "+1.5",
                                                                   "parts.left_leg.joint.offset.2": "-0.75"}})
    assert legs.part("left_leg").size[2] == 17.5 and legs.part("left_leg").joint.offset[2] == -8.75
    assert legs.part("left_leg").joint.servo.backlash_deg == 6.5        # untouched fields stay
    assert compare.parse_variant_arg("x:parts.body.mass=*1.2,parts.body.material=wood") == \
        {"name": "x", "set": {"parts.body.mass": "*1.2", "parts.body.material": "wood"}}
    assert compare.parse_variant_arg("v2:examples/robots/caduceus_v2.yaml") == \
        {"name": "v2", "spec": "examples/robots/caduceus_v2.yaml"}
    with pytest.raises(ValueError):
        compare.apply_overrides(copy.deepcopy(raw), {"parts.body.mass": "+heavy"} | {"parts.body": "x"})


def test_compare_uses_the_same_worlds(spider):
    out = compare.compare(spider, [{"name": "heavy", "set": {"parts.body.mass": "+100"}}],
                          scenes=["move:stand"], worlds=2, workers=1, cache_dir=None)
    row = out["rows"][0]
    assert set(row["cells"]) == {"base", "heavy"} and "delta_pass" in row["cells"]["heavy"]
    assert out["reports"]["base"]["settings"]["seed"] == out["reports"]["heavy"]["settings"]["seed"]
    assert "Design comparison" in compare.to_markdown(out)
    _ = mujoco  # imported so a missing mujoco fails here, not deep inside a worker


def test_progress_file_survives_a_reader_holding_it(tmp_path, monkeypatch):
    """On Windows os.replace fails while the dashboard has progress.json open: retry, then skip the update."""
    target = tmp_path / "job" / "progress.json"
    real_replace = bench.os.replace
    calls = {"n": 0}

    def busy_twice(src, dst):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError(13, "Access is denied")
        real_replace(src, dst)

    monkeypatch.setattr(bench.os, "replace", busy_twice)
    bench.write_progress(target, {"done": 1, "total": 4})
    assert calls["n"] == 3 and target.read_text(encoding="utf-8") == "{\"done\": 1, \"total\": 4}"

    def always_busy(src, dst):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(bench.os, "replace", always_busy)
    bench.write_progress(target, {"done": 2, "total": 4})          # no exception: the update is skipped
    assert target.read_text(encoding="utf-8") == "{\"done\": 1, \"total\": 4}"
