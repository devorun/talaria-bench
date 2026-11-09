"""Hermes integration: registration, tools, the preflight gate, approvals, jobs, the robot bridge,
firmware headers, settings, secrets and storage. No real Hermes and no hardware needed."""

from __future__ import annotations

import json
import sys
import time
import types
from pathlib import Path

import pytest
import yaml

import talaria_bench
from talaria_bench import bench, bridge, firmware, preflight, schemas
from talaria_bench.commands import slash_handler
from talaria_bench.hooks import make_pre_tool_call
from talaria_bench.runtime import EXAMPLES, Runtime
from talaria_bench.spec import load_spec, parse_spec
from talaria_bench.tools import TalariaTools

PLUGIN_ROOT = Path(talaria_bench.__file__).resolve().parent


class FakeCtx:
    def __init__(self, config=None):
        self.config = dict(config or {})
        self.tools, self.hooks, self.commands, self.cli = {}, {}, {}, {}

    def register_tool(self, name, toolset, schema, handler, **kwargs):
        assert schema["name"] == name and toolset == "talaria"
        self.tools[name] = handler

    def register_hook(self, name, callback):
        self.hooks[name] = callback

    def register_command(self, name, handler, **kwargs):
        self.commands[name] = handler

    def register_cli_command(self, name, **kwargs):
        self.cli[name] = kwargs

    def get_config(self, key, default=None):
        return self.config.get(key, default)


@pytest.fixture(autouse=True)
def _reset_data_dir():
    yield
    bench.set_data_dir(None)


@pytest.fixture
def rt(tmp_path):
    return Runtime(overrides={"data_dir": tmp_path / "data"})


@pytest.fixture
def tools(rt):
    t = TalariaTools(rt)
    yield t
    t.shutdown()


def call(tools, name, args):
    return json.loads(tools.handlers()[name](args))


def approve(rt, robot, move, speed=1.0, verdict="pass", reasons=(), suggestions=()):
    """Write an approval record without simulating (the gate only reads it)."""
    spec = rt.robot(robot)
    key = preflight.approval_key(spec, move, speed)
    result = {"verdict": verdict, "tip": {"falls": 25, "rate": 0.42, "low": 0.3, "high": 0.54},
              "reasons": list(reasons), "suggestions": list(suggestions), "worlds": 60}
    preflight.ApprovalStore(rt.folder("approvals")).save(preflight.record(key, spec, "x", move, speed, result))
    return key


# Registration and manifest ---------------------------------------------------------------------------


def test_register_matches_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = FakeCtx()
    talaria_bench.register(ctx)
    manifest = yaml.safe_load((PLUGIN_ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    assert sorted(ctx.tools) == sorted(manifest["provides_tools"]) == sorted(schemas.NAMES)
    assert len(ctx.tools) == 14
    assert sorted(ctx.hooks) == sorted(manifest["provides_hooks"]) == ["pre_tool_call"]
    assert list(ctx.commands) == ["talaria"] and list(ctx.cli) == ["talaria"]
    assert manifest["requires_hermes"] == ">=0.22.0"
    token = manifest["config_schema"]["robot_token"]
    assert token["type"] == "secret" and token["env"] == "TALARIA_ROBOT_TOKEN"


def test_every_schema_is_well_formed():
    for s in schemas.ALL:
        assert s["description"] and s["parameters"]["type"] == "object"
        for req in s["parameters"].get("required", []):
            assert req in s["parameters"]["properties"]


# Settings, secrets, storage --------------------------------------------------------------------------


def test_settings_secret_and_data_dir_come_from_hermes(tmp_path, monkeypatch):
    data = tmp_path / "plugin-data" / "talaria-bench"
    storage = types.ModuleType("plugins.plugin_storage")
    storage.plugin_data_dir = lambda name: data
    secret = types.ModuleType("agent.secret_scope")
    secret.get_secret = lambda env: "s3cret" if env == "TALARIA_ROBOT_TOKEN" else None
    monkeypatch.setitem(sys.modules, "plugins", types.ModuleType("plugins"))
    monkeypatch.setitem(sys.modules, "plugins.plugin_storage", storage)
    monkeypatch.setitem(sys.modules, "agent", types.ModuleType("agent"))
    monkeypatch.setitem(sys.modules, "agent.secret_scope", secret)
    rt = Runtime(FakeCtx({"robot_url": "http://192.168.1.8", "timeout_s": 5}))
    assert rt.data_dir() == data and bench.DATA_DIR == data and bench.default_cache_dir() == data / "cache"
    assert rt.token() == "s3cret"
    assert rt.setting("robot_url") == "http://192.168.1.8" and rt.number("timeout_s") == 5.0
    assert rt.setting("real_robot") == "caduceus"                 # default when unset
    for sub in ("robots", "moves", "approvals", "reports", "cache"):
        assert rt.folder(sub).parent == data
    assert PLUGIN_ROOT not in rt.data_dir().parents


def test_data_dir_falls_back_outside_hermes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "plugins.plugin_storage", None)     # import fails
    monkeypatch.setitem(sys.modules, "agent.secret_scope", None)
    rt = Runtime()
    assert rt.data_dir() == tmp_path / ".cache" / "talaria-bench"
    assert rt.token() is None


# Wilson interval and approval keys -------------------------------------------------------------------


def test_wilson_interval():
    lo, hi = preflight.wilson(0, 60)
    assert lo == 0.0 and 0.059 < hi < 0.061
    lo, hi = preflight.wilson(25, 60)
    assert 0.29 < lo < 0.31 and 0.53 < hi < 0.55
    assert preflight.wilson(0, 30)[1] > 0.10          # 30 clean worlds cannot reach the 10% bound
    assert preflight.wilson(0, 0) == (0.0, 1.0)


def test_approval_key_tracks_move_speed_physics_and_hardware(caduceus, mini_data):
    move = {"frames": [{"ms": 400, "joints": {"right_arm": 30}}]}
    key = preflight.approval_key(caduceus, move)
    assert key == preflight.approval_key(caduceus, {"frames": [{"ms": 400.0, "hold": 0, "joints": {"right_arm": 30.0}}],
                                                    "loops": 1, "easing": "smoothstep", "description": "same"})
    assert key != preflight.approval_key(caduceus, {"frames": [{"ms": 300, "joints": {"right_arm": 30}}]})
    assert key != preflight.approval_key(caduceus, {"frames": [{"ms": 400, "joints": {"right_arm": 31}}]})
    assert key != preflight.approval_key(caduceus, move, speed=0.5)
    assert key != preflight.approval_key(caduceus, {**move, "easing": "linear"})
    base = parse_spec(mini_data)
    mv = {"frames": [{"ms": 300, "joints": {"leg": 20}}]}
    body, leg = mini_data["parts"]
    heavier = dict(mini_data, parts=[dict(body, mass=250), leg])
    rewired = dict(mini_data, parts=[body, {**leg, "joint": {**leg["joint"], "hardware": {"channel": 5}}}])
    assert preflight.approval_key(parse_spec(heavier), mv) != preflight.approval_key(base, mv)
    assert preflight.approval_key(parse_spec(rewired), mv) != preflight.approval_key(base, mv)


# The gate --------------------------------------------------------------------------------------------


def test_hook_blocks_without_approval_and_ignores_other_tools(rt):
    hook = make_pre_tool_call(rt)
    out = hook(tool_name="robot_play", args={"robot": "caduceus", "move": "wave"})
    assert out["action"] == "block" and "move_check" in out["message"]
    assert hook(tool_name="terminal", args={"command": "ls"}) is None
    assert hook(tool_name="robot_stop", args={"robot": "caduceus"}) is None
    assert hook(tool_name="robot_status", args={}) is None


def test_hook_allows_exact_approved_move_only(rt):
    spec = rt.robot("caduceus")
    approve(rt, "caduceus", spec.moves["wave"])
    hook = make_pre_tool_call(rt)
    assert hook(tool_name="robot_play", args={"robot": "caduceus", "move": "wave"}) is None
    assert hook(tool_name="robot_play", args={"robot": "caduceus", "move": "wave", "speed": 1.5})["action"] == "block"
    assert hook(tool_name="robot_play", args={"robot": "caduceus", "move": "arms_up_both"})["action"] == "block"


def test_hook_is_fast(rt):
    spec = rt.robot("caduceus")
    approve(rt, "caduceus", spec.moves["wave"])
    hook = make_pre_tool_call(rt)
    t0 = time.perf_counter()
    for _ in range(20):
        hook(tool_name="robot_play", args={"robot": "caduceus", "move": "wave"})
    assert (time.perf_counter() - t0) / 20 < 0.05


def test_hook_blocks_failed_move_with_reason_and_suggestions(rt):
    spec = rt.robot("caduceus")
    approve(rt, "caduceus", spec.moves["arms_up_both"], verdict="fail",
            reasons=["tips in 42% (30%-54%) of simulated worlds, mostly during frame 2"],
            suggestions=["Slow it down: play the move at speed 0.5."])
    out = make_pre_tool_call(rt)(tool_name="robot_play", args={"robot": "caduceus", "move": "arms_up_both"})
    assert out["action"] == "block"
    assert "did not pass preflight" in out["message"] and "42% (30%-54%)" in out["message"]
    assert "Try: Slow it down" in out["message"]


def test_move_changed_after_approval_is_blocked(rt, tools):
    frames = [{"ms": 900, "joints": {"right_arm": 40}}, {"ms": 900, "joints": {"right_arm": 0}}]
    assert call(tools, "move_save", {"robot": "caduceus", "name": "salute", "frames": frames})["ok"]
    approve(rt, "caduceus", rt.saved_moves("caduceus")["salute"])
    hook = make_pre_tool_call(rt)
    assert hook(tool_name="robot_play", args={"robot": "caduceus", "move": "salute"}) is None
    frames[0]["ms"] = 500                                             # faster now, same name
    assert call(tools, "move_save", {"robot": "caduceus", "name": "salute", "frames": frames})["ok"]
    out = hook(tool_name="robot_play", args={"robot": "caduceus", "move": "salute"})
    assert out["action"] == "block" and "no preflight for this exact move" in out["message"]


def test_spec_change_after_approval_is_blocked(rt, tools, mini_data):
    assert call(tools, "robot_define", {"spec_yaml": yaml.safe_dump(mini_data)})["ok"]
    approve(rt, "mini", mini_data["moves"]["kick"])
    hook = make_pre_tool_call(rt)
    assert hook(tool_name="robot_play", args={"robot": "mini", "move": "kick"}) is None
    mini_data["parts"][0]["mass"] = 260
    assert call(tools, "robot_define", {"spec_yaml": yaml.safe_dump(mini_data)})["ok"]
    rt._specs.clear()                                                # same mtime second on fast disks
    assert hook(tool_name="robot_play", args={"robot": "mini", "move": "kick"})["action"] == "block"


def test_handler_gates_too_for_slash_and_cli(rt, tools):
    data = call(tools, "robot_play", {"robot": "caduceus", "move": "wave"})
    assert data["ok"] is False and data["blocked"] is True
    assert "move_check" in slash_handler(rt, tools)("play caduceus wave")


def test_robot_pose_needs_its_own_check(rt, tools):
    blocked = call(tools, "robot_pose", {"robot": "caduceus", "joints": {"right_arm": 30}})
    assert blocked["blocked"]
    approve(rt, "caduceus", {"frames": [{"ms": 600, "joints": {"right_arm": 30}}]})
    ok = call(tools, "robot_pose", {"robot": "caduceus", "joints": {"right_arm": 30}})
    assert ok["ok"] and ok["joints"] == {"right_arm": 30.0}


# Tools -----------------------------------------------------------------------------------------------


def test_robot_list_show_define(rt, tools, mini_data):
    names = {r["name"] for r in call(tools, "robot_list", {})["robots"]}
    assert {"caduceus", "spider8", "dog12", "arm6"} <= names
    show = call(tools, "robot_show", {"robot": "caduceus"})
    assert show["ok"] and show["hardware"]["controller"]["sda"] == 4 and show["limitations"]
    bad = call(tools, "robot_define", {"spec_yaml": yaml.safe_dump(dict(mini_data, name="caduceus"))})
    assert not bad["ok"] and "bundled" in " ".join(bad["problems"])
    broken = call(tools, "robot_define", {"spec_yaml": "talaria: 1\nname: x\nparts: []\n"})
    assert not broken["ok"] and broken["problems"]
    assert call(tools, "robot_show", {"robot": "nope"})["ok"] is False
    assert (rt.data_dir() / "robots").is_dir() and not (rt.data_dir() / "robots" / "caduceus.yaml").exists()


def test_move_save_and_list(rt, tools):
    clash = call(tools, "move_save", {"robot": "caduceus", "name": "wave",
                                      "frames": [{"ms": 500, "joints": {"right_arm": 10}}]})
    assert not clash["ok"]
    out_of_range = call(tools, "move_save", {"robot": "caduceus", "name": "big",
                                             "frames": [{"ms": 500, "joints": {"right_arm": 500}}]})
    assert not out_of_range["ok"] and out_of_range["problems"]
    assert call(tools, "move_save", {"robot": "caduceus", "name": "nod",
                                     "frames": [{"ms": 800, "joints": {"left_arm": 20}}]})["ok"]
    moves = {m["name"]: m for m in call(tools, "move_list", {"robot": "caduceus"})["moves"]}
    assert moves["nod"]["source"] == "saved" and moves["nod"]["preflight"] == "not checked"
    assert (rt.data_dir() / "moves" / "caduceus.json").is_file()


def test_tools_never_raise(tools):
    for name in schemas.NAMES:
        if name in ("bench_run", "bench_compare"):
            continue
        data = json.loads(tools.handlers()[name]({"robot": 42, "job_id": "missing", "variants": "x"}))
        assert isinstance(data, dict) and "ok" in data


# Virtual end to end ----------------------------------------------------------------------------------


def test_virtual_end_to_end_check_play_status(rt, tools):
    check = call(tools, "move_check", {"robot": "caduceus", "move": "arms_up_alternating"})
    assert check["ok"] and check["verdict"] == "pass" and check["approved"], check.get("reasons")
    assert check["tip"]["falls"] == 0 and check["tip"]["high"] <= 0.10 and check["simulation"] is True
    assert set(check["joints"]) == {"left_arm", "left_leg", "right_leg", "right_arm"}
    hook = make_pre_tool_call(rt)
    assert hook(tool_name="robot_play", args={"robot": "caduceus", "move": "arms_up_alternating"}) is None
    play = call(tools, "robot_play", {"robot": "caduceus", "move": "arms_up_alternating", "target": "virtual"})
    assert play["ok"] and play["duration_s"] == pytest.approx(2.2)
    time.sleep(0.3)
    status = call(tools, "robot_status", {"robot": "caduceus"})
    assert status["ok"] and status["simulated"] and status["busy"] and status["playing"] == "arms_up_alternating"
    assert call(tools, "robot_stop", {"robot": "caduceus"})["stopped"]
    assert call(tools, "robot_status", {"robot": "caduceus"})["busy"] is False


def test_failing_check_explains_and_suggests(rt, tools):
    check = call(tools, "move_check", {"robot": "caduceus", "move": "arms_up_both", "quick": True})
    assert check["verdict"] == "fail" and not check["approved"]
    assert check["worlds"] == 30 and not check["official"] and check["quick"]   # never BLOCKED on fewer than 30
    assert check["tip_seeds"] and all(s >= 5000 for s in check["tip_seeds"])
    assert check["tip"]["falls"] > 0 and check["reasons"] and check["suggestions"]
    assert any("Slow it down" in s for s in check["suggestions"])
    out = make_pre_tool_call(rt)(tool_name="robot_play", args={"robot": "caduceus", "move": "arms_up_both"})
    assert out["action"] == "block" and "Try:" in out["message"]


def test_quick_check_extends_a_clean_move_so_it_can_pass(rt, tools):
    check = call(tools, "move_check", {"robot": "caduceus", "move": "arms_up_alternating", "quick": True})
    assert check["verdict"] == "pass" and check["extended"] and check["worlds"] == 60
    assert check["worlds_requested"] == 30 and check["tip"]["high"] <= 0.10


def test_real_target_checks_address_token_and_identity(rt, tools):
    spec = rt.robot("caduceus")
    approve(rt, "caduceus", spec.moves["wave"])
    no_url = call(tools, "robot_play", {"robot": "caduceus", "move": "wave", "target": "real"})
    assert not no_url["ok"] and "robot_url" in no_url["error"]
    server = bridge.start_virtual(spec, token="tok")
    other = bridge.start_virtual(rt.robot("spider8"), token="tok")
    try:
        rt.overrides.update(robot_url=server.url, token="wrong")
        assert "token" in call(tools, "robot_play", {"robot": "caduceus", "move": "wave", "target": "real"})["error"]
        rt.overrides["token"] = "tok"
        ok = call(tools, "robot_play", {"robot": "caduceus", "move": "wave", "target": "real"})
        assert ok["ok"] and ok["address"] == server.url
        rt.overrides["robot_url"] = other.url
        wrong = call(tools, "robot_play", {"robot": "caduceus", "move": "wave", "target": "real"})
        assert not wrong["ok"] and "spider8" in wrong["error"]
        rt.overrides["robot_url"] = "http://127.0.0.1:9"
        assert "hint" in call(tools, "robot_status", {"robot": "caduceus", "target": "real"})
    finally:
        for s in (server, other):
            s.shutdown()
            s.server_close()


# Background jobs -------------------------------------------------------------------------------------


def _wait(tools, job_id, limit=180):
    for _ in range(limit * 4):
        job = call(tools, "bench_status", {"job_id": job_id, "wait_s": 0})["job"]
        if job["status"] != "running":
            return job
        time.sleep(0.25)
    raise AssertionError("job did not finish")


def test_background_job_lifecycle(rt, tools):
    started = call(tools, "bench_run", {"robot": "arm6", "scenes": ["move:home"], "quick": True})
    assert started["ok"] and started["status"] == "running"
    assert call(tools, "bench_status", {})["jobs"][0]["id"] == started["job_id"]
    job = _wait(tools, started["job_id"])
    assert job["status"] == "done", job.get("log_tail")
    report = call(tools, "bench_report", {"job_id": started["job_id"]})
    assert report["ok"] and "(simulation)" in report["markdown"] and report["summary"]
    assert Path(report["report"]).parent == rt.data_dir() / "reports"
    assert call(tools, "bench_report", {"robot": "arm6"})["report"] == report["report"]
    assert any((rt.data_dir() / "cache").iterdir())                  # the job cached into the data dir
    assert not (PLUGIN_ROOT / "cache").exists()


def test_failed_job_reports_failure(tools):
    started = call(tools, "bench_run", {"robot": "arm6", "scenes": ["no_such_scene"]})
    job = _wait(tools, started["job_id"])
    assert job["status"] == "failed" and job["log_tail"]
    assert call(tools, "bench_report", {"job_id": started["job_id"]})["ok"] is False


def test_compare_variants_are_names_or_overrides_only(tools):
    bad = call(tools, "bench_compare", {"robot": "spider8", "variants": [{"name": "x", "spec": "/etc/passwd"}]})
    assert not bad["ok"]
    ok = call(tools, "bench_compare", {"robot": "spider8", "quick": True, "scenes": ["move:stand"],
                                       "variants": [{"name": "heavier", "set": {"parts.body.mass": "+50"}}]})
    assert ok["ok"] and ok["variants"] == ["heavier"]
    job = _wait(tools, ok["job_id"])
    assert job["status"] == "done", job.get("log_tail")


# Firmware --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", sorted(p for p in EXAMPLES.glob("*.yaml") if ".calibration" not in p.name),
                         ids=lambda p: p.stem)
def test_firmware_header_for_every_example(path, tmp_path):
    spec = load_spec(path)
    header = firmware.robot_config_h(spec)
    assert f'"{spec.name}"' in header and spec.hash()[:16] in header
    for name in spec.joint_names:
        assert f'"{name}"' in header
    folder = firmware.export_firmware(spec, tmp_path)
    assert {p.name for p in folder.iterdir()} >= {"talaria_robot.ino", "robot_config.h", "secrets.example.h"}
    ino = (folder / "talaria_robot.ino").read_text(encoding="utf-8")
    assert ino.count("readPrescale") == 1                             # once in setup, never per servo write


# Slash command ---------------------------------------------------------------------------------------


def test_slash_status_gallery_and_help(rt, tools):
    handle = slash_handler(rt, tools)
    assert "Talaria Bench" in handle("status")
    assert "spider8" in handle("gallery")
    assert "/talaria" in handle("help") and "Usage" in handle("bogus")


def test_full_check_is_the_official_number_the_report_shows(rt, tools):
    """A full move_check runs the 60 fixed preflight worlds; the bench scores standing moves on the same
    worlds, so the report card (and the gallery headline built from it) shows the same number."""
    from talaria_bench.bench import run_benchmark

    check = call(tools, "move_check", {"robot": "caduceus", "move": "arms_up_both"})
    assert check["official"] and check["worlds"] == 60 and not check["stopped_early"]
    res = run_benchmark(rt.robot("caduceus"), scenes=["move:arms_up_both"], cache_dir=None, traces=False, workers=1)
    jobs = res["scenes"]["move:arms_up_both"]
    assert len(jobs) == 60 and [j["seed"] for j in jobs] == list(range(5000, 5060))
    assert sum(1 for j in jobs if j["fell"]) == check["tip"]["falls"]


def test_robot_define_from_template_with_photo(rt, tools):
    photo = EXAMPLES / "caduceus_front.jpg"
    data = call(tools, "robot_define", {"template": "block_robot", "photo_path": str(photo),
                                        "params": {"name": "my_bot", "arm_length": 23.5, "leg_length": 16,
                                                   "body_width": 16.5, "mass_g": 400, "servo": "MG90S"}})
    assert data["ok"] and data["robot"] == "my_bot" and data["photo"] == "photos/my_bot.jpg"
    assert (rt.data_dir() / "robots" / "photos" / "my_bot.jpg").read_bytes() == photo.read_bytes()
    spec = rt.robot("my_bot")
    assert spec.photo and len(spec.joint_parts) == 4 and abs(spec.total_mass_g - 400) < 1
    est = call(tools, "robot_define", {"template": "quadruped", "params": {"name": "crawler"}})
    assert est["ok"] and any("estimate" in n for n in est["estimates_and_notes"])


def test_robot_define_refuses_bad_photos(rt, tools, tmp_path):
    params = {"name": "p_bot"}
    outside = call(tools, "robot_define", {"template": "biped4", "params": params, "photo_path": "/etc/hostname"})
    assert not outside["ok"] and "home folder" in " ".join(outside["problems"])
    fake = rt.data_dir() / "fake.jpg"
    fake.write_text("not an image")
    bad = call(tools, "robot_define", {"template": "biped4", "params": params, "photo_path": str(fake)})
    assert not bad["ok"] and "JPEG, PNG or WebP" in " ".join(bad["problems"])
    missing = call(tools, "robot_define", {"template": "biped4", "params": params, "photo_path": "/nope/x.jpg"})
    assert not missing["ok"]
    assert call(tools, "robot_define", {"template": "biped4", "params": {"name": "caduceus"}})["ok"] is False


def test_firmware_screen_is_optional_per_robot():
    cad = firmware.robot_config_h(load_spec(EXAMPLES / "caduceus.yaml"))
    spider = firmware.robot_config_h(load_spec(EXAMPLES / "spider8.yaml"))
    assert "#define HAS_OLED      1" in cad and "#define OLED_ADDR     0x3C" in cad
    assert "#define HAS_OLED      0" in spider
    ino = (PLUGIN_ROOT / "firmware" / "talaria_robot" / "talaria_robot.ino").read_text(encoding="utf-8")
    assert "#if HAS_OLED" in ino and "showMessage(ROBOT_NAME, ip.c_str())" in ino


def test_bench_status_waits_for_the_job(tools):
    started = call(tools, "bench_run", {"robot": "arm6", "scenes": ["move:home"], "quick": True})
    data = call(tools, "bench_status", {"job_id": started["job_id"]})       # one call, no polling loop
    assert data["job"]["status"] == "done" and data["next"].startswith("bench_report")


def test_robot_names_accept_a_unique_prefix(rt, tools):
    assert rt.robot("spider").name == "spider8" and rt.robot("dog").name == "dog12"
    assert call(tools, "robot_show", {"robot": "caduceus_"})["robot"] == "caduceus_v2"
    assert rt.robot("caduceus").name == "caduceus"                        # an exact name always wins
    ambiguous = call(tools, "robot_show", {"robot": "cad"})               # caduceus or caduceus_v2
    assert ambiguous["ok"] is False and "several robots" in ambiguous["error"]
    started = call(tools, "bench_run", {"robot": "arm", "scenes": ["move:home"], "quick": True})
    assert started["ok"] and started["robot"] == "arm6"
