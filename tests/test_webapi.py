"""The shared Desktop/dashboard backend, through the real ``dashboard/plugin_api.py`` loader and FastAPI's
TestClient (httpx decodes the gzip trace responses like a browser does)."""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import talaria_bench  # noqa: E402
from talaria_bench import bench  # noqa: E402

PLUGIN_ROOT = Path(talaria_bench.__file__).resolve().parent
PREFIX = "/api/plugins/talaria-bench"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "plugins.plugin_storage", None)        # outside Hermes: ~/.cache
    monkeypatch.setattr(talaria_bench, "_RUNTIME", None, raising=False)
    spec = importlib.util.spec_from_file_location("talaria_plugin_api_test", PLUGIN_ROOT / "dashboard" / "plugin_api.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    app = FastAPI()
    app.include_router(mod.router, prefix=PREFIX)
    with TestClient(app) as c:
        yield c
    bench.set_data_dir(None)


def get(c, path):
    r = c.get(PREFIX + path)
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r


def post(c, path, body):
    r = c.post(PREFIX + path, json=body)
    return r.status_code, r.json()


def wait_job(c, job_id, limit=240):
    for _ in range(limit * 4):
        code, job = get(c, f"/jobs/{job_id}")
        assert code == 200
        if job["status"] != "running":
            return job
        time.sleep(0.25)
    raise AssertionError("job did not finish")


def test_plugin_api_finds_the_loaded_package(client, tmp_path):
    code, data = get(client, "/robots")
    assert code == 200 and data["ok"]
    names = {r["name"] for r in data["robots"]}
    assert {"caduceus", "spider8", "dog12", "humanoid16", "arm6", "desk-biped4", "caduceus_v2"} <= names
    cad = next(r for r in data["robots"] if r["name"] == "caduceus")
    assert cad["has_photo"] and cad["family"] == "biped" and cad["headline"]
    assert (tmp_path / ".cache" / "talaria-bench").is_dir()           # data dir, not the code folder


def test_robot_detail_has_render_geometry(client):
    code, data = get(client, "/robots/caduceus")
    assert code == 200
    render = data["render"]
    assert len(render["parts"]) == len(data["parts"]) and len(render["joints"]) == 4
    for p in render["parts"]:
        assert len(p["pose"]) == 7 and p["shape"] in ("box", "cylinder", "sphere", "capsule") and p["color"]
    feet_z = min(p["pose"][2] for p in render["parts"])
    assert 0.0 < feet_z < 0.2                                          # resting on the floor
    assert {m["name"] for m in data["moves"]} >= {"wave", "arms_up_both", "arms_up_alternating"}
    assert data["variants"] and data["servos"] and data["editable"]
    assert get(client, "/robots/nope")[0] == 404


def test_photo_is_served_safely(client):
    r = client.get(PREFIX + "/robots/caduceus/photo")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and len(r.content) > 1000
    assert client.get(PREFIX + "/robots/spider8/photo").status_code == 404
    for bad in ("..%2F..%2Fetc%2Fpasswd", "..", "caduceus%2F..%2F..%2Fplugin.yaml"):
        assert client.get(PREFIX + f"/robots/{bad}/photo").status_code == 404
        assert client.get(PREFIX + f"/robots/{bad}/thumb").status_code == 404


def test_report_card_bundled(client):
    code, data = get(client, "/robots/caduceus/report")
    rep = data["report"]
    assert code == 200 and rep["origin"] == "bundled example" and rep["simulation"]
    statuses = {c["status"] for c in rep["scenes"]}
    assert "out_of_scope" in statuses
    tile = next(c for c in rep["scenes"] if c["id"] == "move:arms_up_both")
    assert "median_seed" in tile["metric"] and tile["metric"]["worst"]["reason"]


def test_move_trace_is_compact_gzip_and_cached(client, tmp_path):
    r = client.post(PREFIX + "/trace", json={"robot": "caduceus", "move": "wave"})
    assert r.status_code == 200 and r.headers.get("content-encoding") == "gzip"
    data = r.json()
    tr = data["trace"]
    assert data["simulation"] and tr["fps"] == 30 and len(tr["frames"]) > 200
    assert all(len(p) == 7 for p in tr["frames"][0])
    assert all(len(str(v).split(".")[-1]) <= 3 for v in tr["frames"][10][0])
    cached = list((tmp_path / ".cache" / "talaria-bench" / "cache" / "traces").glob("*.json.gz"))
    assert len(cached) == 1
    t0 = time.perf_counter()
    assert client.post(PREFIX + "/trace", json={"robot": "caduceus", "move": "wave"}).json() == data
    assert time.perf_counter() - t0 < 1.0


def test_scene_traces_carry_terrain(client):
    obstacle = client.post(PREFIX + "/trace", json={"robot": "spider8", "scene": "obstacle_1cm", "seed": 0}).json()
    box = obstacle["meta"]["boxes"][0]
    assert box["half"][2] == pytest.approx(0.005) and box["center"][0] > 0
    ramp = client.post(PREFIX + "/trace", json={"robot": "spider8", "scene": "ramp_10", "seed": 1}).json()
    assert ramp["meta"]["tilt_deg"] == 10.0
    push = client.post(PREFIX + "/trace", json={"robot": "caduceus", "scene": "push", "seed": 0}).json()
    assert push["meta"]["push"]["direction"] in ("front", "back", "left", "right")
    slip = client.post(PREFIX + "/trace", json={"robot": "spider8", "scene": "slippery", "seed": 2}).json()
    assert slip["meta"]["floor"] == "slippery" and 0.05 < slip["meta"]["friction"] < 0.2
    na = client.post(PREFIX + "/trace", json={"robot": "arm6", "scene": "flat", "seed": 0})
    assert na.status_code == 400


def test_preflight_and_play_go_through_the_gate(client):
    code, bad = post(client, "/check", {"robot": "caduceus", "move": "arms_up_both", "quick": True})
    assert code == 200 and bad["verdict"] == "fail" and bad["tip_seeds"] and bad["suggestions"]
    code, blocked = post(client, "/play", {"robot": "caduceus", "move": "arms_up_both"})
    assert code == 200 and blocked["blocked"] and "did not pass preflight" in blocked["error"]
    code, good = post(client, "/check", {"robot": "caduceus", "move": "arms_up_alternating", "quick": True})
    assert good["verdict"] == "pass" and good["extended"]
    code, played = post(client, "/play", {"robot": "caduceus", "move": "arms_up_alternating", "target": "virtual"})
    assert code == 200 and played["ok"]
    code, st = post(client, "/status", {"robot": "caduceus"})
    assert st["ok"] and st["simulated"]
    assert post(client, "/stop", {"robot": "caduceus"})[1]["stopped"]
    code, real = post(client, "/play", {"robot": "caduceus", "move": "arms_up_alternating", "target": "real"})
    assert code == 400 and "robot_url" in real["error"]


def test_edit_saves_a_user_copy(client):
    code, data = post(client, "/robots/caduceus/edit", {"new_name": "caduceus_heavy",
                                                         "parts": {"head": {"mass": 220}}})
    assert code == 200 and data["robot"] == "caduceus_heavy"
    code, detail = get(client, "/robots/caduceus_heavy")
    assert detail["title"].endswith("(edited)") and not detail["has_photo"]
    assert next(p for p in detail["parts"] if p["name"] == "head")["mass"] == 220
    code, bad = post(client, "/robots/caduceus/edit", {"new_name": "x1", "parts": {"head": {"color": "red"}}})
    assert code == 400 and bad["problems"]
    code, bad = post(client, "/robots/caduceus/edit", {"new_name": "x2", "parts": {"left_arm": {"servo": "NOPE9"}}})
    assert code == 400 and bad["problems"]
    code, bad = post(client, "/robots/caduceus/edit", {"new_name": "caduceus"})
    assert code == 400


def test_bench_job_and_compare_job(client):
    code, job = post(client, "/bench", {"robot": "arm6", "quick": True})
    assert code == 200
    done = wait_job(client, job["job_id"])
    assert done["status"] == "done", done.get("log_tail")
    assert done["result"]["scenes"] and done["result"]["summary"]
    assert get(client, "/robots/arm6/report")[1]["report"]["origin"] == "this machine"
    code, cmp_job = post(client, "/compare", {"robot": "spider8", "quick": True, "scenes": ["move:stand"],
                                             "variants": [{"name": "heavy", "set": {"parts.body.mass": "+80"}}]})
    assert code == 200
    done = wait_job(client, cmp_job["job_id"])
    assert done["status"] == "done", done.get("log_tail")
    assert [v["name"] for v in done["result"]["variants"]] == ["base", "heavy"]
    seed = done["result"]["reports"]["heavy"]["scenes"][0]["metric"]["median_seed"]
    base = client.post(PREFIX + "/trace", json={"robot": "spider8", "scene": "move:stand", "seed": seed}).json()
    heavy = client.post(PREFIX + "/trace", json={"robot": "spider8", "scene": "move:stand", "seed": seed,
                                                 "job_id": cmp_job["job_id"], "variant": "heavy"}).json()
    assert base["trace"]["frames"] and heavy["trace"]["frames"] and base["trace"] != heavy["trace"]


def test_variant_presets(client):
    code, data = get(client, "/robots/spider8/variants")
    names = [v["name"] for v in data["variants"]]
    assert "high step" in names and all(v.get("set") or v.get("robot") for v in data["variants"])
    code, data = get(client, "/robots/caduceus/variants")
    assert data["variants"]
