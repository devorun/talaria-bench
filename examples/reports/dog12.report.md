# Report card: Robot dog (12 servos) (simulation)

*Simulation results (MuJoCo, randomized worlds). Simulation-based risk screening, not a guarantee.*

Robot `dog12` (1600 g, 12 servos, spec `433d3b55949e`), 30 worlds per scene (seeds 0..29), 36 s.

| Scene | Status | Pass | Main metric: median (p10) | Worst | Top failure reasons |
|---|---|---|---|---|---|
| Flat floor | GREEN | 97% | steady progress: 45.1 (18.4) cm | -0.91 (world 10) | no progress (1) |
| Ramp 5 deg | GREEN | 90% | climb along the slope: 25.95 (7.94) cm | -28.62 (world 3) | slid back (3) |
| Ramp 10 deg | RED | 10% | climb along the slope: -32.66 (-72.07) cm | -104 (world 3) | slid back (21), no progress (3), tipped backward (3) |
| Ramp 15 deg | RED | 0% | climb along the slope: -68.58 (-189) cm | -261 (world 25) | tipped backward (22), slid back (8) |
| Bar 1 cm | GREEN | 97% | distance past the bar: 30.08 (18.38) cm | -34.47 (world 10) | no progress before the bar (1) |
| Bar 2 cm | AMBER | 50% | distance past the bar: 5.08 (-5.04) cm | -10.07 (world 26) | stuck at the bar (15) |
| Push test | GREEN | 100% | weakest tipping push: 1 (1) x weight | 1 (world 0) | - |
| Slippery floor | GREEN | 93% | steady progress: 107 (40.8) cm | -29.85 (world 24) | sliding (1), spinning in place (1) |
| Payload | n/a | - | - | - | the robot has no payload_part |
| Move 'stand' | GREEN | 100% | max body tilt: 0.03 (0.01) deg | 0 (world 3) | - |
| Move 'sit' | GREEN | 100% | max body tilt: 26.23 (25.08) deg | 24.87 (world 18) | - |

**Summary.** Walks well on flat ground (97% of worlds, median 45.1 cm). Climbs the 5 deg ramp in 90% of worlds but slid back on the 10 deg ramp in 70% of worlds. Clears the bar 1 cm in 97% of worlds. Clears the bar 2 cm in 50% of worlds. Survives a nudge from every side in 100% of worlds; does not tip even at the largest push. Standing moves that never or almost never tip it: stand, sit. Keeps at least half its flat speed on a slippery floor in 93% of worlds. The thigh hr servo is near its limit (peak 100% of stall, estimate) during the ramp 5 deg test.

**Push test** (tipping push in x body weight, median / p10; how far it slides when it does not tip, median):

| From | Tipping push | Survives nudge | Slide after nudge | after 0.5 x weight | after 1 x weight |
|---|---|---|---|---|---|
| front | >1 / >1 | 100% | 0.5 cm | 1.4 cm | 2.8 cm |
| back | >1 / 1 | 100% | 0.6 cm | 1.6 cm | 17.4 cm |
| left | >1 / 1 | 100% | 0.5 cm | 1.3 cm | 2.9 cm |
| right | >1 / 1 | 100% | 0.6 cm | 1.6 cm | 3.0 cm |

Mid-walk nudge survived: front 100%, back 100%, left 100%, right 100%

**Servo load (estimate)**: highest peak per joint across scenes.

| Joint | Peak (% of stall) | Time near limit (median %) | In scene |
|---|---|---|---|
| hip_fl | 100% | 0% | Flat floor |
| hip_fr | 100% | 0% | Flat floor |
| hip_hl | 100% | 0% | Ramp 5 deg |
| hip_hr | 100% | 0% | Ramp 5 deg |
| shin_fl | 100% | 28% | Flat floor |
| shin_fr | 100% | 29% | Flat floor |
| shin_hl | 100% | 0% | Flat floor |
| shin_hr | 100% | 1% | Flat floor |
| thigh_fl | 100% | 9% | Flat floor |
| thigh_fr | 100% | 6% | Flat floor |
| thigh_hl | 100% | 0% | Flat floor |
| thigh_hr | 100% | 0% | Flat floor |

_Servo load is an estimate: peak torque as a share of the datasheet stall torque. Stall torque is not a safe continuous torque; a servo held near it overheats._

**Conditions**

- Flat floor: move 'trot', pass: >= 5 cm steady progress, no fall
- Ramp 5 deg: slope 5 deg uphill, pass: climbs >= 5 cm, no fall or slide back
- Ramp 10 deg: slope 10 deg uphill, pass: climbs >= 5 cm, no fall or slide back
- Ramp 15 deg: slope 15 deg uphill, pass: climbs >= 5 cm, no fall or slide back
- Bar 1 cm: bar 1 cm high, 2 cm deep, 5 cm ahead; pass: root 5 cm past it
- Bar 2 cm: bar 2 cm high, 2 cm deep, 5 cm ahead; pass: root 5 cm past it
- Push test: pushes of 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1 x body weight for 0.1 s from 4 sides while standing; pass: survives the nudge (0.1 x weight) from every side
- Slippery floor: effective foot-floor friction 0.08-0.15 (any foot material); pass: >= 50% of the flat median, no fall
- Payload: payload steps lumped at the payload part; a step passes below 80% of stall at every joint, no tipping and < 2 cm drift from the no-load path; pass: >= the first non-zero step
- Move 'stand': plays 'stand' standing; pass: no fall
- Move 'sit': plays 'sit' standing; pass: no fall

World ranges: friction 0.3..0.7, mass_scale 0.85..1.15, torque_scale 0.7..1.1, kp_scale 0.6..1.2, latency_s 0..0.04, offset_deg -3..3, floor_tilt_deg 0..1.5, tether_scale 0..1, tether_dir_deg 120..240
