"""Real-robot safety: every play starts from the home pose, a real robot needs its token and matching
firmware, the firmware command makes the token, schema limits equal the engine's, ignored arguments warn,
a real move needs a person's approval, approvals expire with the engine and the check's rules, the virtual
robot takes JSON only, and a benchmark job gets none of Hermes's secrets."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import time
from pathlib import Path

import pytest

from talaria_bench import bench, bridge, builder, firmware, jobs, motion, preflight, schemas, tools as tools_mod
from talaria_bench.commands import cli_handler
from talaria_bench.hooks import make_pre_tool_call
from talaria_bench.runtime import Runtime
from talaria_bench.tools import TalariaTools


@pytest.fixture
def rt(tmp_path):
    runtime = Runtime(overrides={"data_dir": tmp_path / "data"})
    yield runtime
    bench.set_data_dir(None)


@pytest.fixture
def tools(rt):
    t = TalariaTools(rt)
    yield t
    t.shutdown()


def call(tools, name, args):
    return json.loads(tools.handlers()[name](args))


def approve(rt, robot, move, speed=1.0):
    spec = rt.robot(robot)
    result = {"verdict": "pass", "tip": {"falls": 0, "rate": 0, "low": 0, "high": 0.06}, "reasons": [],
              "suggestions": [], "worlds": 60}
    key = preflight.approval_key(spec, move, speed)
    preflight.ApprovalStore(rt.folder("approvals")).save(preflight.record(key, spec, "x", move, speed, result))


POSE = {"frames": [{"ms": 600, "joints": {"left_arm": 40}}]}
MOVE = {"frames": [{"ms": 800, "joints": {"right_arm": 30}}, {"ms": 800, "joints": {"right_arm": 0}}]}


class FakeRobot:
    """Records what the tools send; reports ``pose`` and becomes idle after ``busy_polls`` busy answers."""

    url = "http://fake"

    def __init__(self, pose=None, busy_polls=0):
        self.pose_now, self.busy_polls, self.calls = pose, busy_polls, []

    def state(self):
        self.calls.append(("state",))
        busy = self.busy_polls > 0
        self.busy_polls -= 1
        return {"ok": True, "busy": busy, **({"pose": self.pose_now} if self.pose_now is not None else {})}

    def pose(self, joints, ms=400):
        self.calls.append(("pose", dict(joints), ms))

    def play(self, frames, loops=1, easing="smoothstep", name=None):
        self.calls.append(("play", frames, loops))

    def stop(self, home=False):
        self.calls.append(("stop", home))


def _use(tools, fake, monkeypatch):
    monkeypatch.setattr(tools, "_client", lambda spec, target: fake)


# B: back to home first ---------------------------------------------------------------------------------


def test_play_returns_home_at_half_speed_then_plays(rt, tools, monkeypatch):
    spec = rt.robot("caduceus")
    approve(rt, "caduceus", MOVE)
    limits = spec.joint_limits()
    home = {n: j["home"] for n, j in limits.items()}
    fake = FakeRobot(pose={**home, "left_arm": home["left_arm"] + 40}, busy_polls=1)
    _use(tools, fake, monkeypatch)
    out = call(tools, "robot_play", {"robot": "caduceus", "frames": MOVE["frames"]})
    assert out["ok"], out
    kinds = [c[0] for c in fake.calls]
    assert kinds[0] == "state" and kinds[1] == "pose" and kinds[-1] == "play"
    assert kinds.index("play") > kinds.index("pose") + 1                # waited until the robot stood still
    _, joints, ms = fake.calls[1]
    assert joints == home
    slowest = 40 / (limits["left_arm"]["max_speed"] * tools_mod.HOME_SPEED_FRACTION) * 1000
    assert ms >= max(slowest, tools_mod.HOME_MIN_MS) and out["homing_ms"] == ms
    assert "home pose" in out["note"]


def test_stop_with_home_eases_home_in_at_least_three_seconds(rt, tools, monkeypatch):
    spec = rt.robot("caduceus")
    limits = spec.joint_limits()
    home = {n: j["home"] for n, j in limits.items()}
    fake = FakeRobot(pose={**home, "right_arm": 50})
    _use(tools, fake, monkeypatch)
    out = call(tools, "robot_stop", {"robot": "caduceus", "target": "real", "home": True})
    assert out["ok"] and out["home"]
    assert ("stop", False) in fake.calls and ("stop", True) not in fake.calls   # plugin-side slow return
    poses = [c for c in fake.calls if c[0] == "pose"]
    assert len(poses) == 1 and poses[0][1] == home and poses[0][2] >= 3000
    fake2 = FakeRobot(pose=None)                                                  # unknown pose: still >= 3 s
    _use(tools, fake2, monkeypatch)
    call(tools, "robot_stop", {"robot": "caduceus", "target": "real", "home": True})
    assert [c for c in fake2.calls if c[0] == "pose"][0][2] >= 3000
    fake3 = FakeRobot(pose=home)
    _use(tools, fake3, monkeypatch)
    call(tools, "robot_stop", {"robot": "caduceus", "target": "real"})            # no home: just a stop
    assert [c[0] for c in fake3.calls] == ["stop"]


def test_play_from_home_skips_the_return(rt, tools, monkeypatch):
    spec = rt.robot("caduceus")
    approve(rt, "caduceus", MOVE)
    fake = FakeRobot(pose={n: j["home"] + 0.5 for n, j in spec.joint_limits().items()})
    _use(tools, fake, monkeypatch)
    out = call(tools, "robot_play", {"robot": "caduceus", "frames": MOVE["frames"]})
    assert out["ok"] and out["homing_ms"] == 0
    assert [c[0] for c in fake.calls] == ["state", "play"]


def test_unknown_pose_returns_home_over_the_full_range(rt, tools, monkeypatch):
    spec = rt.robot("caduceus")
    approve(rt, "caduceus", MOVE)
    fake = FakeRobot(pose=None)
    _use(tools, fake, monkeypatch)
    out = call(tools, "robot_play", {"robot": "caduceus", "frames": MOVE["frames"]})
    full = max((j["max"] - j["min"]) / (j["max_speed"] * tools_mod.HOME_SPEED_FRACTION) * 1000
               for j in spec.joint_limits().values())
    assert out["ok"] and out["homing_ms"] >= min(full, motion.MAX_FRAME_MS) - 1


def test_pose_returns_home_first_too(rt, tools, monkeypatch):
    spec = rt.robot("caduceus")
    approve(rt, "caduceus", POSE)
    home = {n: j["home"] for n, j in spec.joint_limits().items()}
    fake = FakeRobot(pose={**home, "right_arm": 30})
    _use(tools, fake, monkeypatch)
    out = call(tools, "robot_pose", {"robot": "caduceus", "joints": {"left_arm": 40}})
    assert out["ok"], out
    poses = [c for c in fake.calls if c[0] == "pose"]
    assert poses[0][1] == home and poses[1][1] == {"left_arm": 40.0}


def test_a_robot_that_never_gets_home_does_not_play(rt, tools, monkeypatch):
    spec = rt.robot("caduceus")
    approve(rt, "caduceus", MOVE)
    monkeypatch.setattr(tools_mod, "HOME_GRACE_S", 0.1)
    fake = FakeRobot(pose={n: j["home"] + 5 for n, j in spec.joint_limits().items()}, busy_polls=10**6)
    _use(tools, fake, monkeypatch)
    out = call(tools, "robot_play", {"robot": "caduceus", "frames": MOVE["frames"]})
    assert not out["ok"] and "did not reach its home pose" in out["error"]
    assert "play" not in [c[0] for c in fake.calls]


def test_virtual_robot_plays_from_home_after_a_pose(rt, tools):
    approve(rt, "caduceus", POSE)
    approve(rt, "caduceus", MOVE)
    assert call(tools, "robot_pose", {"robot": "caduceus", "joints": {"left_arm": 40}})["ok"]
    time.sleep(0.8)
    out = call(tools, "robot_play", {"robot": "caduceus", "frames": MOVE["frames"]})
    assert out["ok"] and out["homing_ms"] >= tools_mod.HOME_MIN_MS
    state = call(tools, "robot_status", {"robot": "caduceus"})
    assert state["busy"] and abs(state["pose"]["left_arm"]) < 1.0         # left arm already back home


# C: token ---------------------------------------------------------------------------------------------


def test_real_play_needs_a_token_unless_explicitly_allowed(rt, tools):
    approve(rt, "caduceus", MOVE)
    args = {"robot": "caduceus", "frames": MOVE["frames"], "target": "real"}
    out = call(tools, "robot_play", args)
    assert not out["ok"] and "without a token" in out["error"]
    assert "hermes config set TALARIA_ROBOT_TOKEN" in out["error"] and "allow_unauthenticated_robot" in out["error"]
    approve(rt, "caduceus", POSE)
    pose = call(tools, "robot_pose", {"robot": "caduceus", "joints": {"left_arm": 40}, "target": "real"})
    assert not pose["ok"] and "without a token" in pose["error"]
    rt.overrides["allow_unauthenticated_robot"] = "true"
    assert "robot_url" in call(tools, "robot_play", args)["error"]          # past the token check
    rt.overrides["allow_unauthenticated_robot"] = False
    stop = call(tools, "robot_stop", {"robot": "caduceus", "target": "real"})   # stopping is never refused
    assert "without a token" not in stop.get("error", "")


def test_flag_settings_need_an_explicit_true(rt):
    for value, expected in ((True, True), ("true", True), ("On", True), ("1", True), (False, False),
                            ("false", False), ("", False), (None, False), (1, False)):
        rt.overrides["allow_firmware_mismatch"] = value
        assert rt.flag("allow_firmware_mismatch") is expected, value


def _firmware_cli(rt, tools, out_dir, new_token=False):
    ns = argparse.Namespace(talaria_cmd="firmware", robot="caduceus", out_dir=str(out_dir), new_token=new_token)
    return cli_handler(rt, tools)(ns)


def test_firmware_command_writes_a_random_token_and_prints_the_setup(rt, tools, tmp_path, capsys):
    assert _firmware_cli(rt, tools, tmp_path / "a") == 0
    printed = capsys.readouterr().out
    token = re.search(r"new random robot token: ([0-9a-f]{32})", printed).group(1)
    assert f"hermes config set TALARIA_ROBOT_TOKEN {token}" in printed
    header = (tmp_path / "a" / "talaria_robot" / "robot_config.h").read_text(encoding="utf-8")
    assert f'#define ROBOT_TOKEN     "{token}"' in header and "#undef ROBOT_TOKEN" in header
    _firmware_cli(rt, tools, tmp_path / "b")
    assert token not in capsys.readouterr().out                            # a fresh one each time
    rt.overrides["token"] = "kept-token"
    _firmware_cli(rt, tools, tmp_path / "c")
    printed = capsys.readouterr().out
    assert "kept-token" not in printed and "already stored in Hermes" in printed
    assert '"kept-token"' in (tmp_path / "c" / "talaria_robot" / "robot_config.h").read_text(encoding="utf-8")
    _firmware_cli(rt, tools, tmp_path / "d", new_token=True)
    assert "new random robot token" in capsys.readouterr().out


def test_sketch_takes_the_token_from_robot_config(rt):
    ino = (firmware.SKETCH_DIR / "talaria_robot.ino").read_text(encoding="utf-8")
    assert ino.index('#include "secrets.h"') < ino.index('#include "robot_config.h"')
    assert "#define ROBOT_TOKEN" not in (firmware.SKETCH_DIR / "secrets.example.h").read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        firmware.robot_config_h(rt.robot("caduceus"), 'bad"token')
    with pytest.raises(ValueError):
        firmware.export_firmware(rt.robot("caduceus"), "unused", "")


# D: firmware must match the checked spec ---------------------------------------------------------------


@pytest.mark.parametrize("reported", ["0123456789abcdef", None])
def test_real_play_refuses_firmware_from_another_spec(rt, tools, reported):
    spec = rt.robot("caduceus")
    approve(rt, "caduceus", MOVE)
    server = bridge.start_virtual(spec, token="tok")
    real_info = server.robot.info

    def info():
        data = real_info()
        data.pop("spec_hash")
        return {**data, **({"spec_hash": reported} if reported else {})}

    server.robot.info = info
    try:
        rt.overrides.update(robot_url=server.url, token="tok")
        args = {"robot": "caduceus", "frames": MOVE["frames"], "target": "real"}
        out = call(tools, "robot_play", args)
        assert not out["ok"] and "refusing to play on the real robot" in out["error"]
        assert "hermes talaria firmware caduceus" in out["error"] and "allow_firmware_mismatch" in out["error"]
        rt.overrides["allow_firmware_mismatch"] = True
        allowed = call(tools, "robot_play", args)
        assert allowed["ok"] and any("allow_firmware_mismatch" in w for w in allowed["warnings"])
        server.robot.info = real_info
        rt.overrides["allow_firmware_mismatch"] = False
        assert call(tools, "robot_play", args)["ok"]                        # matching firmware plays
    finally:
        server.shutdown()
        server.server_close()


# F: schema limits --------------------------------------------------------------------------------------


def test_schema_limits_equal_the_motion_engine():
    fields = schemas.MOVE_FIELDS
    assert (fields["loops"]["minimum"], fields["loops"]["maximum"]) == (1, motion.MAX_LOOPS)
    assert (fields["speed"]["minimum"], fields["speed"]["maximum"]) == (motion.MIN_SPEED_FACTOR,
                                                                         motion.MAX_SPEED_FACTOR)
    ms = schemas.ROBOT_POSE["parameters"]["properties"]["ms"]
    assert (ms["minimum"], ms["maximum"]) == (motion.MIN_FRAME_MS, motion.MAX_FRAME_MS)
    for schema in (schemas.ROBOT_PLAY, schemas.ROBOT_POSE):
        assert "home pose" in schema["description"]


# G: ignored arguments and extra variants warn ----------------------------------------------------------


def test_loops_and_easing_on_a_named_move_warn(rt, tools, monkeypatch):
    spec = rt.robot("caduceus")
    approve(rt, "caduceus", spec.moves["wave"])
    _use(tools, FakeRobot(pose={n: j["home"] for n, j in spec.joint_limits().items()}), monkeypatch)
    out = call(tools, "robot_play", {"robot": "caduceus", "move": "wave", "loops": 3, "easing": "linear"})
    assert out["ok"] and any("loops and easing ignored" in w for w in out["warnings"])
    approve(rt, "caduceus", {**MOVE, "loops": 2})
    inline = call(tools, "robot_play", {"robot": "caduceus", "frames": MOVE["frames"], "loops": 2})
    assert inline["ok"] and not any("ignored" in w for w in inline["warnings"])
    monkeypatch.setattr(preflight, "check", lambda *a, **k: _fake_check(spec))
    checked = call(tools, "move_check", {"robot": "caduceus", "move": "wave", "easing": "linear"})
    assert any("easing ignored" in w for w in checked["warnings"])


def _fake_check(spec):
    return {"robot": spec.name, "move": "wave", "speed": 1.0, "worlds": 60, "verdict": "pass",
            "tip": {"falls": 0, "rate": 0, "low": 0, "high": 0.06}, "joints": {n: {"peak_pct_p90": 10}
                                                                                for n in spec.joint_names},
            "reasons": [], "suggestions": []}


def test_more_than_six_variants_warn(tools, monkeypatch):
    seen = {}

    def start_compare(robot, variants, **kwargs):
        seen["variants"] = variants
        return {"id": "20261109-000000-aaaaaa"}

    monkeypatch.setattr(tools.jobs, "start_compare", start_compare)
    variants = [{"name": f"v{i}", "set": {"parts.body.mass": f"+{i}"}} for i in range(8)]
    out = call(tools, "bench_compare", {"robot": "spider8", "variants": variants, "quick": True})
    assert out["ok"] and len(seen["variants"]) == 6
    assert "only the first 6 of 8" in out["warnings"][0] and "v6, v7" in out["warnings"][0]
    few = call(tools, "bench_compare", {"robot": "spider8", "variants": variants[:2], "quick": True})
    assert "warnings" not in few


# H: a person approves every real move --------------------------------------------------------------------


def test_real_move_goes_to_hermes_approval(rt):
    spec = rt.robot("caduceus")
    approve(rt, "caduceus", spec.moves["wave"])
    approve(rt, "caduceus", POSE)
    rt.overrides["robot_url"] = "http://192.168.1.8"
    hook = make_pre_tool_call(rt)
    for target in (None, "virtual"):
        assert hook(tool_name="robot_play", args={"robot": "caduceus", "move": "wave", "target": target}) is None
    out = hook(tool_name="robot_play", args={"robot": "caduceus", "move": "wave", "target": "real"})
    assert out["action"] == "approve" and "REAL robot: caduceus / wave" in out["message"]
    assert "http://192.168.1.8" in out["message"] and "0 of 60 worlds tipped" in out["message"]
    assert out["rule_key"] == "talaria-bench:real:caduceus:" + preflight.approval_key(spec, spec.moves["wave"])[:16]
    pose = hook(tool_name="robot_pose", args={"robot": "caduceus", "joints": {"left_arm": 40}, "target": "real"})
    assert pose["action"] == "approve" and "caduceus pose left_arm=40" in pose["message"]
    assert pose["rule_key"] != out["rule_key"]                     # an answer covers one exact move only
    odd = hook(tool_name="robot_play", args={"robot": "caduceus", "move": "wave", "target": "Real"})
    assert odd["action"] == "approve"                              # anything but virtual counts as real
    blocked = hook(tool_name="robot_play", args={"robot": "caduceus", "move": "arms_up_both", "target": "real"})
    assert blocked["action"] == "block"                            # no passing preflight: nothing to approve


def test_approval_key_expires_with_the_engine_and_the_rules(rt):
    spec = rt.robot("caduceus")
    move = spec.moves["wave"]
    key = preflight.approval_key(spec, move)
    changes = [(builder, "MODEL_VERSION", builder.MODEL_VERSION + 1), (preflight, "DEFAULT_WORLDS", 100),
               (preflight, "QUICK_WORLDS", 20), (preflight, "MIN_DECIDE_WORLDS", 40), (preflight, "SEED_BASE", 6000),
               (preflight, "MAX_TIP_UPPER", 0.2), (preflight, "MAX_LOAD", 0.95)]
    for module, name, value in changes:
        with pytest.MonkeyPatch.context() as m:
            m.setattr(module, name, value)
            assert preflight.approval_key(spec, move) != key, name
    assert preflight.approval_key(spec, move) == key
    approve(rt, "caduceus", move)
    hook = make_pre_tool_call(rt)
    assert hook(tool_name="robot_play", args={"robot": "caduceus", "move": "wave"}) is None
    with pytest.MonkeyPatch.context() as m:
        m.setattr(builder, "MODEL_VERSION", builder.MODEL_VERSION + 1)       # a new engine: check again
        out = hook(tool_name="robot_play", args={"robot": "caduceus", "move": "wave"})
        assert out["action"] == "block" and "no preflight for this exact move" in out["message"]


# I: the virtual robot takes JSON only --------------------------------------------------------------------


def _raw_post(server, path, body, content_type):
    host, port = server.server_address[:2]
    conn = http.client.HTTPConnection(host, port, timeout=3)
    headers = {"Content-Type": content_type} if content_type else {}
    try:
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read() or b"{}")
    finally:
        conn.close()


def test_virtual_robot_refuses_posts_that_are_not_json(rt):
    server = bridge.start_virtual(rt.robot("caduceus"))
    body = json.dumps({"joints": {"left_arm": 40}, "ms": 400}).encode()
    try:
        for content_type in (None, "text/plain", "application/x-www-form-urlencoded",
                             "multipart/form-data; boundary=x"):
            status, data = _raw_post(server, "/pose", body, content_type)
            assert status == 415 and data["ok"] is False, content_type
        assert server.robot.state()["busy"] is False                 # nothing moved
        assert _raw_post(server, "/pose", body, "application/json; charset=utf-8") == (200, {"ok": True})
        assert bridge.RobotClient(server.url).stop()["ok"]              # the plugin's own client sends JSON
    finally:
        server.shutdown()
        server.server_close()


# J: a benchmark job gets none of Hermes's secrets --------------------------------------------------------


def test_job_env_is_an_allowlist():
    env = {"PATH": "/bin", "HOME": "/h", "USERPROFILE": "/h", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
           "TMPDIR": "/t", "TEMP": "/t", "TMP": "/t", "TALARIA_MP_START": "spawn", "PYTHONUTF8": "1",
           "PYTHONIOENCODING": "utf-8", "MUJOCO_GL": "egl", "SYSTEMROOT": "C:\\Windows",
           "OPENAI_API_KEY": "sk-x", "ANTHROPIC_API_KEY": "x", "TELEGRAM_BOT_TOKEN": "x", "GITHUB_TOKEN": "x",
           "TALARIA_ROBOT_TOKEN": "x", "HERMES_HOME": "/hh", "PYTHONHOME": "/py", "LD_PRELOAD": "x.so"}
    kept = set(jobs.job_env(env))
    expected = {"PATH", "HOME", "USERPROFILE", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "TALARIA_MP_START",
                "PYTHONUTF8", "PYTHONIOENCODING", "MUJOCO_GL"}
    assert kept == expected | ({"SYSTEMROOT"} if os.name == "nt" else set())


def test_job_subprocess_gets_no_api_keys(rt, tools, tmp_path, monkeypatch):
    monkeypatch.setenv("TALARIA_FAKE_API_KEY", "sk-fake-talaria-0000")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-fake-0000")
    dump = tmp_path / "dump_env.py"                  # stands in for devcli.py: writes its environment to --out
    dump.write_text("import json, os, sys\n"
                    "out = sys.argv[sys.argv.index('--out') + 1]\n"
                    "with open(out, 'w', encoding='utf-8') as f:\n"
                    "    json.dump(dict(os.environ), f)\n", encoding="utf-8")
    monkeypatch.setattr(jobs, "DEVCLI", dump)
    started = call(tools, "bench_run", {"robot": "arm6", "quick": True})
    assert tools.jobs._procs[started["job_id"]].wait(timeout=60) == 0
    env = json.loads(Path(tools.jobs.job(started["job_id"])["out"]).read_text(encoding="utf-8"))
    names = {k.upper() for k in env}
    assert not [n for n in names if n.endswith("_API_KEY")]
    assert "sk-fake-talaria-0000" not in env.values() and "sk-or-fake-0000" not in env.values()
    assert "HERMES_HOME" not in names                                # set for every test by conftest
    assert {"PATH", "PYTHONPATH", "TALARIA_CACHE"} <= names
    assert env[next(k for k in env if k.upper() == "TALARIA_CACHE")] == str(rt.folder("cache"))
