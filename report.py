"""Report card: benchmark results -> JSON (dashboard) and Markdown (chat, README).

Always labelled simulation. Status per scene: green >= 80% pass, amber 40-80%, red < 40%, "n/a" when the
scene does not apply, and a neutral grey "out of model scope" when the robot spec declares a limitation
for that kind of scene (the bench does not score it; raw numbers stay in the JSON for debugging only).
Wording describes what happened in simulation, never a judgement of the robot. Servo loads are estimates against datasheet
stall torque, which is not a safe continuous torque. The summary paragraph is generated from the
numbers (no language model). Schema: docs/report-format.md.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Optional

import numpy as np

from .scenes import NUDGE, PUSH_DIRECTIONS, PUSH_DURATION, PUSH_LEVELS, SLIPPERY_FRICTION, get_scene

REPORT_FORMAT = "talaria-bench/report"
REPORT_VERSION = 1
GREEN, AMBER = 0.8, 0.4
LABEL = "Simulation results (MuJoCo, randomized worlds). Simulation-based risk screening, not a guarantee."
SERVO_NOTE = ("Servo load is an estimate: peak torque as a share of the datasheet stall torque. Stall torque is "
              "not a safe continuous torque; a servo held near it overheats.")
NEAR_LIMIT = 0.9
ABOVE_MAX = PUSH_LEVELS[-1] * 1.25          # stands for "did not tip at the largest push"


def status_for(pass_rate: Optional[float]) -> str:
    if pass_rate is None:
        return "n/a"
    return "green" if pass_rate >= GREEN else "amber" if pass_rate >= AMBER else "red"


def _conditions(sid: str, results: dict) -> str:
    scene = get_scene(sid)
    if scene.family == "moves":
        return f"plays '{scene.params['move']}' standing; pass: no fall"
    if scene.family == "payload":
        return ("payload steps lumped at the payload part; a step passes below 80% of stall at every joint, "
                "no tipping and < 2 cm drift from the no-load path; pass: >= the first non-zero step")
    walk = results["settings"].get("walk_move")
    if scene.family == "flat":
        need = results["settings"].get("bench", {}).get("flat_min_cm", 5.0)
        return f"move '{walk}', pass: >= {need:g} cm steady progress, no fall"
    if scene.family == "ramp":
        return f"slope {scene.params['angle']:g} deg uphill, pass: climbs >= 5 cm, no fall or slide back"
    if scene.family == "obstacle":
        return f"bar {scene.params['height'] * 100:g} cm high, 2 cm deep, 5 cm ahead; pass: root 5 cm past it"
    if scene.family == "push":
        return (f"pushes of {', '.join(f'{p:g}' for p in PUSH_LEVELS)} x body weight for {PUSH_DURATION:g} s "
                f"from 4 sides while standing; pass: survives the nudge ({NUDGE:g} x weight) from every side")
    return (f"effective foot-floor friction {SLIPPERY_FRICTION[0]:g}-{SLIPPERY_FRICTION[1]:g} (any foot "
            "material); pass: 50-150% of the flat median and no fall; more than 150% = uncontrolled sliding")


def _fmt(v: Optional[float], unit: str = "") -> str:
    if v is None:
        return "-"
    if unit == "x weight" and v >= ABOVE_MAX - 1e-9:
        return f">{PUSH_LEVELS[-1]:g}"
    return f"{v:.2f}".rstrip("0").rstrip(".") if abs(v) < 100 else f"{v:.0f}"


def _scene_card(sid: str, jobs: list[dict], results: dict) -> dict[str, Any]:
    scene = get_scene(sid)
    limits = [lim["note"] for lim in results["robot"].get("limitations", [])
              if lim["scope"] in ("all", "locomotion" if scene.locomotion else "standing")]
    passed = [j for j in jobs if j.get("passed")]
    pass_rate = len(passed) / len(jobs) if jobs else None
    vals = [ABOVE_MAX if (sid == "push" and j.get("metric") is None) else float(j.get("metric") or 0.0)
            for j in jobs]
    worst_job = min(jobs, key=lambda j: (ABOVE_MAX if sid == "push" and j.get("metric") is None
                                         else float(j.get("metric") or 0.0)))
    reasons = Counter(j["reason"] for j in jobs if not j.get("passed") and j.get("reason"))
    loads: dict[str, dict[str, float]] = {}
    joints = sorted({n for j in jobs for n in j.get("loads", {})})
    for n in joints:
        peaks = [j["loads"][n]["peak_ratio"] for j in jobs if n in j.get("loads", {})]
        sats = [j["loads"][n]["saturated_frac"] for j in jobs if n in j.get("loads", {})]
        loads[n] = {"peak_pct_median": round(float(np.median(peaks)) * 100, 1),
                    "peak_pct_max": round(float(np.max(peaks)) * 100, 1),
                    "near_limit_time_pct_median": round(float(np.median(sats)) * 100, 1)}
    computed = status_for(pass_rate)
    card: dict[str, Any] = {
        "id": sid, "title": scene.title, "family": scene.family, "applicable": True,
        "status": "out_of_scope" if limits else computed, "in_scope": not limits,
        "note": " ".join(limits) if limits else None, "conditions": _conditions(sid, results),
        "runs": len(jobs), "passed": len(passed), "pass_rate": None if pass_rate is None else round(pass_rate, 3),
        "metric": {"name": scene.metric, "unit": scene.unit,
                   "median": round(float(np.median(vals)), 3), "p10": round(float(np.percentile(vals, 10)), 3),
                   "worst": {"value": None if (sid == "push" and worst_job.get("metric") is None)
                             else worst_job.get("metric"),
                             "seed": worst_job["seed"], "reason": worst_job.get("reason")}},
        "failure_reasons": dict(reasons.most_common()),
        "falls": sum(bool(j.get("fell")) for j in jobs),
        "loads": loads,
    }
    if sid == "push":
        per_dir = {}
        for d in PUSH_DIRECTIONS:
            th = [j["metrics"]["thresholds"][d] for j in jobs]
            nums = [ABOVE_MAX if t is None else t for t in th]
            per_dir[d] = {"median": round(float(np.median(nums)), 3),
                          "p10": round(float(np.percentile(nums, 10)), 3),
                          "survives_nudge_pct": round(100 * sum(t is None or t > NUDGE for t in th) / len(th), 1)}
            for key, level in (("slide_nudge_cm_median", NUDGE), ("slide_half_weight_cm_median", 0.5),
                               ("slide_full_weight_cm_median", 1.0)):
                vals = [j["metrics"].get("slides_cm", {}).get(d, {}).get(f"{level:g}") for j in jobs]
                vals = [v for v in vals if v is not None]
                per_dir[d][key] = round(float(np.median(vals)), 2) if vals else None
        card["push"] = {"levels": list(PUSH_LEVELS), "nudge": NUDGE, "duration_s": PUSH_DURATION,
                        "thresholds": per_dir}
        walks = [j["metrics"].get("walk_nudge_survived") for j in jobs if j["metrics"].get("walk_nudge_survived")]
        if walks:
            walk_limits = [lim["note"] for lim in results["robot"].get("limitations", [])
                           if lim["scope"] in ("all", "locomotion")]
            card["push"]["mid_walk"] = {
                "survives_nudge_pct": {d: round(100 * sum(w[d] for w in walks) / len(walks), 1)
                                       for d in PUSH_DIRECTIONS},
                "in_scope": not walk_limits, "note": " ".join(walk_limits) if walk_limits else None}
    if sid == "slippery":
        card["needed_cm"] = (jobs[0]["metrics"].get("needed_cm") if jobs else None)
        card["slide_cap_cm"] = (jobs[0]["metrics"].get("slide_cap_cm") if jobs else None)
    if scene.locomotion and jobs and "foot_slip_cm_s" in jobs[0]["metrics"]:
        slip = [j["metrics"]["foot_slip_cm_s"] for j in jobs]
        speed = [j["metrics"]["body_speed_cm_s"] for j in jobs]
        card["foot_slip"] = {"foot_slip_cm_s_median": round(float(np.median(slip)), 2),
                             "body_speed_cm_s_median": round(float(np.median(speed)), 2)}
    if sid == "payload" and jobs:
        steps = [st["grams"] for st in jobs[0]["metrics"]["steps"]]
        rows = []
        for k, g in enumerate(steps):
            sts = [j["metrics"]["steps"][k] for j in jobs]
            rows.append({"grams": g, "pass_pct": round(100 * sum(s["ok"] for s in sts) / len(sts), 1),
                         "max_peak_pct_median": round(float(np.median([s["max_peak_pct"] for s in sts])), 1),
                         "tracking_error_cm_median": round(float(np.median([s["tracking_error_cm"] for s in sts])), 2),
                         "tipped": sum(s["tipped"] for s in sts),
                         "worst_joint": Counter(s["worst_joint"] for s in sts).most_common(1)[0][0],
                         "top_reason": next(iter(Counter(
                             ("tips" if s["tipped"] else "load" if s["max_peak_pct"] >= 80 else "drift")
                             for s in sts if not s["ok"]).most_common(1)), (None,))[0]})
        card["payload"] = {"move": jobs[0]["metrics"]["move"], "part": jobs[0]["metrics"]["payload_part"],
                           "load_limit_pct": 80, "track_limit_cm": 2.0, "steps": rows}
    return card


def build_report(results: dict) -> dict[str, Any]:
    cards = []
    for sid in results["settings"]["scenes"]:
        if sid in results.get("not_applicable", {}):
            scene = get_scene(sid)
            cards.append({"id": sid, "title": scene.title, "family": scene.family, "applicable": False,
                          "status": "n/a", "in_scope": True, "note": results["not_applicable"][sid],
                          "conditions": _conditions(sid, results), "runs": 0, "pass_rate": None})
        else:
            cards.append(_scene_card(sid, results["scenes"][sid], results))
    report = {
        "format": REPORT_FORMAT, "version": REPORT_VERSION, "simulation": True, "label": LABEL,
        "created": results.get("created"), "robot": results["robot"], "settings": results["settings"],
        "world_ranges": results["robot"].get("world_ranges", {}), "scenes": cards,
        "servo_note": SERVO_NOTE, "limitations": results["robot"].get("limitations", []),
        "timing": results.get("timing", {}),
    }
    report["summary"] = summary(report)
    return report


def _pct(x: Optional[float]) -> str:
    return "-" if x is None else f"{x * 100:.0f}%"


def summary(report: dict) -> str:
    """One plain-English paragraph built from the numbers."""
    cards = {c["id"]: c for c in report["scenes"]}
    out: list[str] = []
    out_of_scope = [c for c in cards.values() if c.get("applicable") and not c.get("in_scope", True)]
    walk_cards = [c for c in cards.values() if get_scene(c["id"]).locomotion]
    if walk_cards and all(not c.get("applicable") for c in walk_cards):
        out.append("Walking scenes do not apply (the robot has no walk move).")
    flat = cards.get("flat")
    if flat and flat.get("applicable") and flat.get("in_scope", True):
        m = flat["metric"]
        txt = (f"On flat ground it covers the target distance in {_pct(flat['pass_rate'])} of worlds "
               f"(median {_fmt(m['median'])} cm)")
        if flat["status"] == "red":
            txt += f"; most common outcome otherwise: {next(iter(flat['failure_reasons']), 'no progress')}"
        out.append(txt + ".")
    ramps = [cards[s] for s in ("ramp_5", "ramp_10", "ramp_15") if s in cards and cards[s].get("applicable")
             and cards[s].get("in_scope", True)]
    if ramps:
        ok = [c for c in ramps if c["status"] != "red"]
        bad = [c for c in ramps if c["status"] == "red"]
        parts = []
        if ok:
            parts.append(f"climbs the {ok[-1]['title'].lower().replace('ramp ', '')} ramp in {_pct(ok[-1]['pass_rate'])} of worlds")
        if bad:
            c = bad[0]
            top, n = next(iter(c["failure_reasons"].items()), ("fails", c["runs"]))
            parts.append(f"{top} on the {c['title'].lower().replace('ramp ', '')} ramp in "
                         f"{100 * n / max(c['runs'], 1):.0f}% of worlds")
        out.append(("It " + " but ".join(parts) + ".").replace("It climbs", "Climbs"))
    for sid in ("obstacle_1cm", "obstacle_2cm"):
        c = cards.get(sid)
        if c and c.get("applicable") and c.get("in_scope", True):
            if c["status"] == "red":
                top = next(iter(c["failure_reasons"]), "fails")
                out.append(f"The {c['title'].lower()}: {top} in most worlds (passes {_pct(c['pass_rate'])}).")
            else:
                out.append(f"Clears the {c['title'].lower()} in {_pct(c['pass_rate'])} of worlds.")
    push = cards.get("push")
    if push and push.get("applicable"):
        th = push["push"]["thresholds"]
        weakest = min(th, key=lambda d: th[d]["median"])
        w = th[weakest]["median"]
        tips = "does not tip even at the largest push" if w >= ABOVE_MAX - 1e-9 else \
            f"a push of {_fmt(w)} x body weight from the {weakest} tips it (median)"
        slide = max(((v.get("slide_half_weight_cm_median") or 0.0, d) for d, v in th.items()), default=(0.0, ""))
        if slide[0] >= 2.0:
            tips += f", and it slides instead (median {slide[0]:.0f} cm after a 0.5 x weight push from the {slide[1]})"
        out.append(f"Survives a nudge from every side in {_pct(push['pass_rate'])} of worlds; {tips}.")
    moves = [c for c in cards.values() if c["family"] == "moves" and c.get("applicable") and c.get("in_scope", True)]
    if moves:
        safe = [c["id"][5:] for c in moves if c["pass_rate"] >= 0.95]
        risky = [c for c in moves if c["pass_rate"] < 0.95]
        if safe:
            out.append("Standing moves that never or almost never tip it: " + ", ".join(safe) + ".")
        for c in sorted(risky, key=lambda c: c["pass_rate"]):
            out.append(f"Move '{c['id'][5:]}' tips the robot in {100 - c['pass_rate'] * 100:.0f}% of worlds.")
    pay = cards.get("payload")
    if pay and pay.get("applicable"):
        m = pay["metric"]
        limit = next((r for r in pay["payload"]["steps"] if r["pass_pct"] < 50), None)
        txt = f"Max safe payload (simulation estimate): median {_fmt(max(m['median'], 0))} g (p10 {_fmt(max(m['p10'], 0))} g)"
        if limit:
            why = {"tips": "the base tips over",
                   "drift": f"the gripper sags off its path (median {limit['tracking_error_cm_median']:.1f} cm; "
                            f"{limit['worst_joint'].replace('_', ' ')} at {limit['max_peak_pct_median']:.0f}% of stall)",
                   "load": f"the {limit['worst_joint'].replace('_', ' ')} reaches {limit['max_peak_pct_median']:.0f}% "
                           "of stall"}.get(limit.get("top_reason"), "it fails")
            txt += f"; at {limit['grams']:g} g {why}"
        out.append(txt + ".")
    slip = cards.get("slippery")
    if slip and slip.get("applicable") and slip.get("in_scope", True):
        skating = slip["failure_reasons"].get("uncontrolled sliding", 0)
        if skating > slip["runs"] / 2:
            out.append(f"On a slippery floor its feet skate and it glides out of control in "
                       f"{100 * skating / slip['runs']:.0f}% of worlds.")
        elif slip["status"] == "red":
            top = next(iter(slip["failure_reasons"]), "slides")
            out.append(f"On a slippery floor it passes in {_pct(slip['pass_rate'])} of worlds (most common "
                       f"outcome otherwise: {top}).")
        else:
            out.append(f"Keeps at least half its flat speed on a slippery floor in {_pct(slip['pass_rate'])} of worlds.")
    hot = []
    for c in cards.values():
        for joint, load in (c.get("loads") or {}).items():
            if c.get("in_scope", True) and load["peak_pct_max"] >= NEAR_LIMIT * 100:
                hot.append((load["peak_pct_max"], joint, c["title"].lower()))
    if hot:
        p, joint, where = max(hot)
        out.append(f"The {joint.replace('_', ' ')} servo is near its limit (peak {p:.0f}% of stall, estimate) "
                   f"during the {where} test.")
    if out_of_scope:
        out.append(f"{len(out_of_scope)} walking scene(s) are outside this model's scope for this robot and are "
                   f"not scored: {out_of_scope[0]['note']}")
    return " ".join(out) or "No scenes were run."


def to_markdown(report: dict) -> str:
    r = report["robot"]
    s = report["settings"]
    t = report.get("timing", {})
    lines = [f"# Report card: {r.get('title') or r['name']} (simulation)", "",
             f"*{report['label']}*", "",
             f"Robot `{r['name']}` ({r.get('total_mass_g', 0):.0f} g, {len(r.get('joints', []))} servos, spec "
             f"`{r['hash'][:12]}`), {s['worlds']} worlds per scene (seeds {s['seed']}..{s['seed'] + s['worlds'] - 1})"
             + (f", {t.get('seconds_total', 0):.0f} s" if t else "") + ".", "",
             "| Scene | Status | Pass | Main metric: median (p10) | Worst | Top failure reasons |",
             "|---|---|---|---|---|---|"]
    names = {"green": "GREEN", "amber": "AMBER", "red": "RED", "n/a": "n/a", "out_of_scope": "OUT OF MODEL SCOPE"}
    for c in report["scenes"]:
        if not c.get("applicable"):
            lines.append(f"| {c['title']} | n/a | - | - | - | {c.get('note') or ''} |")
            continue
        m = c["metric"]
        unit = m["unit"]
        worst = m["worst"]
        if c["status"] == "out_of_scope":
            lines.append(f"| {c['title']} | OUT OF MODEL SCOPE | - | - | - | not scored (see limitations) |")
            continue
        reasons = ", ".join(f"{k} ({v})" for k, v in list(c["failure_reasons"].items())[:3]) or "-"
        status = names[c["status"]]
        lines.append(f"| {c['title']} | {status} | {_pct(c['pass_rate'])} | {m['name']}: {_fmt(m['median'], unit)} "
                     f"({_fmt(m['p10'], unit)}) {unit} | {_fmt(worst['value'], unit)} (world {worst['seed']}) | {reasons} |")
    lines += ["", "**Summary.** " + report["summary"], ""]
    push = next((c for c in report["scenes"] if c["id"] == "push" and c.get("applicable")), None)
    if push:
        lines += ["**Push test** (tipping push in x body weight, median / p10; how far it slides when it does "
                  "not tip, median):", "",
                  "| From | Tipping push | Survives nudge | Slide after nudge | after 0.5 x weight | after 1 x weight |",
                  "|---|---|---|---|---|---|"]
        for d, v in push["push"]["thresholds"].items():
            def cm(x):
                return "-" if x is None else f"{x:.1f} cm"
            lines.append(f"| {d} | {_fmt(v['median'], 'x weight')} / {_fmt(v['p10'], 'x weight')} | "
                         f"{v['survives_nudge_pct']:.0f}% | {cm(v.get('slide_nudge_cm_median'))} | "
                         f"{cm(v.get('slide_half_weight_cm_median'))} | {cm(v.get('slide_full_weight_cm_median'))} |")
        mw = push["push"].get("mid_walk")
        if mw:
            if mw["in_scope"]:
                lines += ["", "Mid-walk nudge survived: " +
                          ", ".join(f"{d} {v:.0f}%" for d, v in mw["survives_nudge_pct"].items())]
            else:
                lines += ["", "Mid-walk nudge: OUT OF MODEL SCOPE for this robot (not scored)."]
        lines.append("")
    pay = next((c for c in report["scenes"] if c["id"] == "payload" and c.get("applicable")), None)
    if pay:
        lines += [f"**Payload** (move '{pay['payload']['move']}', weight at '{pay['payload']['part']}'; a step passes "
                  "below 80% of stall, no tipping, < 2 cm drift):", "",
                  "| Payload | Pass | Peak load (median, % of stall) | Drift (median) | Tipped | Limiting joint |",
                  "|---|---|---|---|---|---|"]
        for r in pay["payload"]["steps"]:
            lines.append(f"| {r['grams']:g} g | {r['pass_pct']:.0f}% | {r['max_peak_pct_median']:.0f}% | "
                         f"{r['tracking_error_cm_median']:.1f} cm | {r['tipped']} | {r['worst_joint']} |")
        lines.append("")
    joints: dict[str, tuple[float, float, str]] = {}
    for c in report["scenes"]:
        if not c.get("in_scope", True):
            continue                     # no loads from scenes outside the model's scope
        for j, load in (c.get("loads") or {}).items():
            if j not in joints or load["peak_pct_max"] > joints[j][0]:
                joints[j] = (load["peak_pct_max"], load["near_limit_time_pct_median"], c["title"])
    if joints:
        lines += ["**Servo load (estimate)**: highest peak per joint across scenes.", "",
                  "| Joint | Peak (% of stall) | Time near limit (median %) | In scene |", "|---|---|---|---|"]
        for j, (p, sat, where) in sorted(joints.items()):
            lines.append(f"| {j} | {p:.0f}% | {sat:.0f}% | {where} |")
        lines += ["", f"_{report['servo_note']}_", ""]
    if report.get("limitations"):
        lines += ["**Outside model scope** (these scenes are shown as OUT OF MODEL SCOPE and not scored):", ""]
        lines += [f"- {lim['scope']}: {lim['note']}" for lim in report["limitations"]] + [""]
    lines += ["**Conditions**", ""] + [f"- {c['title']}: {c['conditions']}" for c in report["scenes"]]
    lines += ["", "World ranges: " + ", ".join(f"{k} {v[0]:g}..{v[1]:g}" for k, v in report["world_ranges"].items())]
    return "\n".join(lines) + "\n"
