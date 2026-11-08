# Report card: Caduceus v2 (design variant) (simulation)

*Simulation results (MuJoCo, randomized worlds). Simulation-based risk screening, not a guarantee.*

Robot `caduceus_v2` (437 g, 4 servos, spec `b87fbcae7048`), 30 worlds per scene (seeds 0..29), 22 s.

| Scene | Status | Pass | Main metric: median (p10) | Worst | Top failure reasons |
|---|---|---|---|---|---|
| Flat floor | NOT RELIABLE (would be red) | 20% | steady progress: 0 (0) cm | 0 (world 0) | fell (tipped over) (23), too slow (< 5 cm) (1) |
| Ramp 5 deg | NOT RELIABLE (would be red) | 0% | climb along the slope: -14.01 (-15.13) cm | -15.36 (world 24) | tipped backward (30) |
| Ramp 10 deg | NOT RELIABLE (would be red) | 0% | climb along the slope: 0 (-5.36) cm | -6.14 (world 29) | cannot stand on the slope (20), tipped backward (10) |
| Ramp 15 deg | NOT RELIABLE (would be red) | 0% | climb along the slope: 0 (0) cm | 0 (world 0) | cannot stand on the slope (30) |
| Bar 1 cm | NOT RELIABLE (would be red) | 0% | distance past the bar: -22.39 (-24.47) cm | -25.04 (world 28) | fell (tipped over) (25), stuck at the bar (5) |
| Bar 2 cm | NOT RELIABLE (would be red) | 0% | distance past the bar: -22.31 (-24.66) cm | -25.26 (world 28) | fell (tipped over) (23), stuck at the bar (7) |
| Push test | GREEN | 100% | weakest tipping push: 0.3 (0.3) x weight | 0.3 (world 0) | - |
| Slippery floor | NOT RELIABLE (would be red) | 0% | steady progress: 0 (0) cm | 0 (world 0) | fell (tipped over) (22), no flat progress to compare with (8) |
| Payload | n/a | - | - | - | the robot has no payload_part |
| Move 'wave' | GREEN | 100% | max body tilt: 0.72 (0.46) deg | 0.36 (world 22) | - |
| Move 'arms_up_both' | GREEN | 100% | max body tilt: 2.1 (1.36) deg | 1.28 (world 0) | - |
| Move 'arms_up_alternating' | GREEN | 100% | max body tilt: 1 (0.58) deg | 0.54 (world 22) | - |

**Summary.** Survives a nudge from every side in 100% of worlds; a push of 0.3 x body weight from the front tips it (median). Standing moves that never or almost never tip it: wave, arms_up_both, arms_up_alternating. 7 walking scene(s) are marked not reliable for this robot: Foam feet crushing and rolling at their edges are not in this rigid model; Caduceus walking results are not reliable (the model tips backwards on the firmware walk, the real robot moves ~6 cm forward in 2 cycles).

**Push test** (tipping push in x body weight, median / p10; how far it slides when it does not tip, median):

| From | Tipping push | Survives nudge | Slide after nudge | after 0.5 x weight | after 1 x weight |
|---|---|---|---|---|---|
| front | 0.3 / 0.3 | 100% | 0.2 cm | - | - |
| back | 0.3 / 0.3 | 100% | 0.1 cm | - | - |
| left | >1 / >1 | 100% | 0.2 cm | 0.9 cm | 6.6 cm |
| right | >1 / >1 | 100% | 0.2 cm | 1.1 cm | 7.1 cm |

Mid-walk nudge survived (NOT RELIABLE for this robot): front 7%, back 43%, left 23%, right 23%

**Servo load (estimate)**: highest peak per joint across scenes.

| Joint | Peak (% of stall) | Time near limit (median %) | In scene |
|---|---|---|---|
| left_arm | 70% | 0% | Move 'arms_up_both' |
| left_leg | 66% | 0% | Move 'arms_up_both' |
| right_arm | 74% | 0% | Move 'arms_up_both' |
| right_leg | 75% | 0% | Move 'arms_up_both' |

_Servo load is an estimate: peak torque as a share of the datasheet stall torque. Stall torque is not a safe continuous torque; a servo held near it overheats._

**Known model limitations** (results in these scenes are marked NOT RELIABLE):

- locomotion: Foam feet crushing and rolling at their edges are not in this rigid model; Caduceus walking results are not reliable (the model tips backwards on the firmware walk, the real robot moves ~6 cm forward in 2 cycles).

**Conditions**

- Flat floor: move 'walk', pass: >= 5 cm steady progress, no fall
- Ramp 5 deg: slope 5 deg uphill, pass: climbs >= 5 cm, no fall or slide back
- Ramp 10 deg: slope 10 deg uphill, pass: climbs >= 5 cm, no fall or slide back
- Ramp 15 deg: slope 15 deg uphill, pass: climbs >= 5 cm, no fall or slide back
- Bar 1 cm: bar 1 cm high, 2 cm deep, 5 cm ahead; pass: root 5 cm past it
- Bar 2 cm: bar 2 cm high, 2 cm deep, 5 cm ahead; pass: root 5 cm past it
- Push test: pushes of 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1 x body weight for 0.1 s from 4 sides while standing; pass: survives the nudge (0.1 x weight) from every side
- Slippery floor: effective foot-floor friction 0.08-0.15 (any foot material); pass: >= 50% of the flat median, no fall
- Payload: payload steps lumped at the payload part; a step passes below 80% of stall at every joint, no tipping and < 2 cm drift from the no-load path; pass: >= the first non-zero step
- Move 'wave': plays 'wave' standing; pass: no fall
- Move 'arms_up_both': plays 'arms_up_both' standing; pass: no fall
- Move 'arms_up_alternating': plays 'arms_up_alternating' standing; pass: no fall

World ranges: friction 0.33..0.63, mass_scale 0.85..1.15, torque_scale 0.82..1.06, kp_scale 0.67..1.1, latency_s 0.005..0.034, offset_deg -2.5..2.5, floor_tilt_deg 0.1..1.2, tether_scale 0..1, tether_dir_deg 113..255
