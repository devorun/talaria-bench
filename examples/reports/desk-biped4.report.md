# Report card: Desk biped (4 servos) (simulation)

*Simulation results (MuJoCo, randomized worlds). Simulation-based risk screening, not a guarantee.*

Robot `desk-biped4` (166 g, 4 servos, spec `59d3d9d765e3`), 30 worlds per scene (seeds 0..29), 22 s.

| Scene | Status | Pass | Main metric: median (p10) | Worst | Top failure reasons |
|---|---|---|---|---|---|
| Flat floor | GREEN | 100% | steady progress: 18.88 (17.94) cm | 17.26 (world 9) | - |
| Ramp 5 deg | GREEN | 100% | climb along the slope: 12.43 (9.87) cm | 9.66 (world 11) | - |
| Ramp 10 deg | AMBER | 57% | climb along the slope: 5.89 (1.84) cm | -1.39 (world 29) | no progress (12), slid back (1) |
| Ramp 15 deg | RED | 17% | climb along the slope: 1.14 (-14.18) cm | -47.72 (world 29) | slid back (14), no progress (11) |
| Bar 1 cm | RED | 0% | distance past the bar: -5.46 (-5.49) cm | -5.52 (world 17) | stuck at the bar (30) |
| Bar 2 cm | RED | 0% | distance past the bar: -5.46 (-5.5) cm | -5.52 (world 17) | stuck at the bar (30) |
| Push test | GREEN | 100% | weakest tipping push: 0.75 (0.75) x weight | 0.5 (world 7) | - |
| Slippery floor | GREEN | 97% | steady progress: 16.48 (13.14) cm | 8.67 (world 11) | sliding (1) |
| Payload | n/a | - | - | - | the robot has no payload_part |
| Move 'stand' | GREEN | 100% | max body tilt: 0 (0) deg | 0 (world 5038) | - |
| Move 'dance' | GREEN | 100% | max body tilt: 3.45 (2.67) deg | 4.83 (world 5024) | - |

**Summary.** On flat ground it covers the target distance in 100% of worlds (median 18.88 cm). Climbs the 10 deg ramp in 57% of worlds but slid back on the 15 deg ramp in 47% of worlds. The bar 1 cm: stuck at the bar in most worlds (passes 0%). The bar 2 cm: stuck at the bar in most worlds (passes 0%). Survives a nudge from every side in 100% of worlds; a push of 0.75 x body weight from the front tips it (median). Standing moves that never or almost never tip it: stand, dance. Keeps at least half its flat speed on a slippery floor in 97% of worlds. The leg r servo is near its limit (peak 100% of stall, estimate) during the move 'dance' test.

**Push test** (tipping push in x body weight, median / p10; how far it slides when it does not tip, median):

| From | Tipping push | Survives nudge | Slide after nudge | after 0.5 x weight | after 1 x weight |
|---|---|---|---|---|---|
| front | 0.75 / 0.75 | 100% | 0.0 cm | 0.3 cm | - |
| back | 1 / 0.75 | 100% | 0.0 cm | 0.4 cm | 9.6 cm |
| left | >1 / 1 | 100% | 0.0 cm | 0.4 cm | 6.2 cm |
| right | >1 / 1 | 100% | 0.0 cm | 0.6 cm | 7.0 cm |

Mid-walk nudge survived: front 100%, back 100%, left 100%, right 100%

**Servo load (estimate)**: highest peak per joint across scenes.

| Joint | Peak (% of stall) | Time near limit (median %) | In scene |
|---|---|---|---|
| foot_l | 36% | 0% | Ramp 15 deg |
| foot_r | 36% | 0% | Ramp 15 deg |
| leg_l | 100% | 1% | Move 'dance' |
| leg_r | 100% | 1% | Move 'dance' |

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
- Move 'dance': plays 'dance' standing; pass: no fall

World ranges: friction 0.3..0.7, mass_scale 0.85..1.15, torque_scale 0.7..1.1, kp_scale 0.6..1.2, latency_s 0..0.04, offset_deg -3..3, floor_tilt_deg 0..1.5, tether_scale 0..1, tether_dir_deg 120..240
