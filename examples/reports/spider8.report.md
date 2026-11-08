# Report card: Spider (8 servos) (simulation)

*Simulation results (MuJoCo, randomized worlds). Simulation-based risk screening, not a guarantee.*

Robot `spider8` (250 g, 8 servos, spec `6ffd18ca18bc`), 30 worlds per scene (seeds 0..29), 8 s.

| Scene | Status | Pass | Main metric: median (p10) | Worst | Top failure reasons |
|---|---|---|---|---|---|
| Flat floor | GREEN | 100% | steady progress: 23.34 (22.2) cm | 20.82 (world 7) | - |
| Ramp 5 deg | GREEN | 100% | climb along the slope: 15.4 (14.68) cm | 14.09 (world 18) | - |
| Ramp 10 deg | AMBER | 73% | climb along the slope: 6.05 (4.72) cm | 3.39 (world 29) | no progress (8) |
| Ramp 15 deg | RED | 0% | climb along the slope: -3.86 (-8.2) cm | -13.87 (world 29) | slid back (29), no progress (1) |
| Bar 1 cm | RED | 23% | distance past the bar: 1.32 (-11.88) cm | -12.23 (world 24) | stuck at the bar (23) |
| Bar 2 cm | RED | 0% | distance past the bar: -12.65 (-12.97) cm | -13.19 (world 25) | stuck at the bar (30) |
| Push test | GREEN | 100% | weakest tipping push: >1 (>1) x weight | - (world 0) | - |
| Slippery floor | GREEN | 100% | steady progress: 21.88 (18.47) cm | 15.31 (world 22) | - |
| Payload | n/a | - | - | - | the robot has no payload_part |
| Move 'stand' | GREEN | 100% | max body tilt: 0 (0) deg | 0.02 (world 5010) | - |

**Summary.** On flat ground it covers the target distance in 100% of worlds (median 23.34 cm). Climbs the 10 deg ramp in 73% of worlds but slid back on the 15 deg ramp in 97% of worlds. The bar 1 cm: stuck at the bar in most worlds (passes 23%). The bar 2 cm: stuck at the bar in most worlds (passes 0%). Survives a nudge from every side in 100% of worlds; does not tip even at the largest push. Standing moves that never or almost never tip it: stand. Keeps at least half its flat speed on a slippery floor in 100% of worlds. The knee fr servo is near its limit (peak 100% of stall, estimate) during the bar 1 cm test.

**Push test** (tipping push in x body weight, median / p10; how far it slides when it does not tip, median):

| From | Tipping push | Survives nudge | Slide after nudge | after 0.5 x weight | after 1 x weight |
|---|---|---|---|---|---|
| front | >1 / >1 | 100% | 0.2 cm | 0.6 cm | 2.8 cm |
| back | >1 / >1 | 100% | 0.3 cm | 0.5 cm | 2.8 cm |
| left | >1 / >1 | 100% | 0.2 cm | 0.5 cm | 2.6 cm |
| right | >1 / >1 | 100% | 0.3 cm | 0.7 cm | 2.9 cm |

Mid-walk nudge survived: front 100%, back 100%, left 100%, right 100%

**Servo load (estimate)**: highest peak per joint across scenes.

| Joint | Peak (% of stall) | Time near limit (median %) | In scene |
|---|---|---|---|
| hip_fl | 100% | 0% | Bar 2 cm |
| hip_fr | 100% | 0% | Bar 1 cm |
| hip_hl | 100% | 0% | Bar 1 cm |
| hip_hr | 60% | 0% | Bar 1 cm |
| knee_fl | 97% | 0% | Bar 1 cm |
| knee_fr | 100% | 0% | Bar 1 cm |
| knee_hl | 88% | 0% | Bar 1 cm |
| knee_hr | 59% | 0% | Ramp 5 deg |

_Servo load is an estimate: peak torque as a share of the datasheet stall torque. Stall torque is not a safe continuous torque; a servo held near it overheats._

**Conditions**

- Flat floor: move 'walk', pass: >= 5 cm steady progress, no fall
- Ramp 5 deg: slope 5 deg uphill, pass: climbs >= 5 cm, no fall or slide back
- Ramp 10 deg: slope 10 deg uphill, pass: climbs >= 5 cm, no fall or slide back
- Ramp 15 deg: slope 15 deg uphill, pass: climbs >= 5 cm, no fall or slide back
- Bar 1 cm: bar 1 cm high, 2 cm deep, 5 cm ahead; pass: root 5 cm past it
- Bar 2 cm: bar 2 cm high, 2 cm deep, 5 cm ahead; pass: root 5 cm past it
- Push test: pushes of 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1 x body weight for 0.1 s from 4 sides while standing; pass: survives the nudge (0.1 x weight) from every side
- Slippery floor: effective foot-floor friction 0.08-0.15 (any foot material); pass: 50-150% of the flat median and no fall; more than 150% = uncontrolled sliding
- Payload: payload steps lumped at the payload part; a step passes below 80% of stall at every joint, no tipping and < 2 cm drift from the no-load path; pass: >= the first non-zero step
- Move 'stand': plays 'stand' standing; pass: no fall

World ranges: friction 0.3..0.7, mass_scale 0.85..1.15, torque_scale 0.7..1.1, kp_scale 0.6..1.2, latency_s 0..0.04, offset_deg -3..3, floor_tilt_deg 0..1.5, tether_scale 0..1, tether_dir_deg 120..240
