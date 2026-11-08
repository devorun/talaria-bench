# Report and results formats

Every file is JSON. Every number in it is simulation (`"simulation": true`).

## Results (`format: talaria-bench/results`, version 1)

Written by `bench.run_benchmark` / `devcli.py bench --out <file>`. It holds every run, plus the
traces for the 3D viewer.

| key | meaning |
|---|---|
| `robot` | spec summary: `name`, `title`, `parts`, `joints`, `total_mass_g`, `moves`, `hash`, `source`, `limitations`, `world_ranges` |
| `settings` | `scenes` (ids run), `worlds`, `seed`, `quick`, `walk_move`, `bench` (spec settings), `scene_version` |
| `not_applicable` | `{scene id: why}`, e.g. no walk move |
| `scenes` | `{scene id: [job, ...]}`, one job per world, in seed order |
| `flat_median_cm` | used by the slippery rule |
| `traces` | `{scene id: {"median": {...}, "worst": {...}}}`; each has `seed`, `metric`, `passed`, `reason`, `note`, `trace` |
| `timing` | `jobs`, `computed`, `cached`, `workers`, `seconds_jobs`, `seconds_total` |

A **job** (one scene in one world): `scene`, `seed`, `world` (all World parameters), `applicable`,
`passed`, `reason` (failure classification or null), `metric` (the scene's main metric), `fell`,
`metrics` (scene-specific extras) and `loads` (`{joint: {peak_ratio, saturated_frac}}`).

A **trace**: `{"fps": 30, "units": "m", "dt", "parts": [{name, shape, size_m, color}],
"frames": [[[x, y, z, qw, qx, qy, qz] per part] per frame]}`. Poses are the parts' geometry centers.

## Report card (`format: talaria-bench/report`, version 1)

Written by `report.build_report(results)` (`devcli.py bench` also saves `<out>.report.json` and
`<out>.report.md`).

| key | meaning |
|---|---|
| `label` | the "simulation-based risk screening, not a guarantee" line, always shown |
| `robot`, `settings`, `world_ranges`, `limitations`, `timing` | copied from the results |
| `scenes` | list of scene cards (below), in run order |
| `servo_note` | stall torque is an estimate, not a safe continuous torque |
| `summary` | one plain-English paragraph generated from the numbers (no language model) |

**Scene card** keys:

| key | meaning |
|---|---|
| `id`, `title`, `family`, `conditions` | e.g. `ramp_10`, "Ramp 10 deg", `ramp`, terrain and pass rule in words |
| `applicable` | false -> only `status: "n/a"` and `note` (why) are meaningful |
| `status` | `green` (pass >= 80%), `amber` (40-80%), `red` (< 40%), `n/a`, or `unreliable` |
| `computed_status` | the colour the numbers alone would give (useful when `status` is `unreliable`) |
| `reliable`, `note` | false + the spec's limitation note when the robot declares a limitation for this kind of scene |
| `runs`, `passed`, `pass_rate` | worlds run, worlds passed, share |
| `metric` | `name`, `unit`, `median`, `p10`, `worst: {value, seed, reason}` |
| `failure_reasons` | `{reason: count}`, most common first |
| `falls` | runs that fell |
| `loads` | `{joint: {peak_pct_median, peak_pct_max, near_limit_time_pct_median}}` (% of stall torque) |
| `push` (push scene only) | `levels`, `nudge`, `duration_s`, `thresholds: {front/back/left/right: {median, p10, survives_nudge_pct}}`, optional `mid_walk: {survives_nudge_pct, reliable, note}` |
| `needed_cm` (slippery only) | 50% of the flat median |
| `payload` (payload scene only) | `move`, `part`, `load_limit_pct` (80), `track_limit_cm` (2), `steps: [{grams, pass_pct, max_peak_pct_median, tracking_error_cm_median, tipped, worst_joint, top_reason}]` |

The push `thresholds` entries also hold `slide_nudge_cm_median`, `slide_half_weight_cm_median` and
`slide_full_weight_cm_median`: how far the root moved after a push it survived. The slippery scene
sets the effective foot-floor friction directly (0.08-0.15, whatever the material); the job's
`world.effective_friction` holds the value. Payload jobs keep every step in `metrics.steps`, and
their `metric` is the max safe payload in grams (-1 when even the no-load run fails).

Push thresholds are in multiples of body weight. "Did not tip at the largest push (1.0 x weight)" is
stored as 1.25 and shown as `>1`.

Failure reasons used: `fell (tipped over)`, `fell (<part> touched the floor)`, `cannot stand here`,
`no progress`, `too slow (< N cm)`, `slid back`, `tipped backward`, `cannot stand on the slope`,
`stuck at the bar`, `tipped over the bar`, `no progress before the bar`, `tips at a nudge from the <side>`,
`sliding`, `spinning in place`, `no flat progress to compare with`, `tipped over`.

## Comparison (`format: talaria-bench/compare`, version 1)

`robot`, `settings`, `variants` (`name` plus `set` or `spec`), `rows` (per scene: `cells` per variant
with `status`, `pass_rate`, `median`, `unit`, and for variants `delta_pass` and `delta_median` vs
`base`), and `reports` (a full report card per variant). Every variant runs the same world seeds.
