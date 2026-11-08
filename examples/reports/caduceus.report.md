# Report card: Caduceus (simulation)

*Simulation results (MuJoCo, randomized worlds). Simulation-based risk screening, not a guarantee.*

Robot `caduceus` (437 g, 4 servos, spec `88cab10ab914`), 30 worlds per scene (seeds 0..29), 19 s.

| Scene | Status | Pass | Main metric: median (p10) | Worst | Top failure reasons |
|---|---|---|---|---|---|
| Flat floor | NOT RELIABLE (would be red) | 0% | steady progress: 0 (0) cm | 0 (world 0) | fell (tipped over) (30) |
| Ramp 5 deg | NOT RELIABLE (would be red) | 0% | climb along the slope: -13.54 (-14.62) cm | -15.9 (world 24) | tipped backward (30) |
| Ramp 10 deg | NOT RELIABLE (would be red) | 0% | climb along the slope: 0 (-0.88) cm | -1.85 (world 15) | cannot stand on the slope (26), tipped backward (4) |
| Ramp 15 deg | NOT RELIABLE (would be red) | 0% | climb along the slope: 0 (0) cm | 0 (world 0) | cannot stand on the slope (30) |
| Bar 1 cm | NOT RELIABLE (would be red) | 0% | distance past the bar: -24.09 (-24.76) cm | -25.23 (world 10) | fell (tipped over) (30) |
| Bar 2 cm | NOT RELIABLE (would be red) | 0% | distance past the bar: -24.54 (-25.21) cm | -25.28 (world 10) | fell (tipped over) (30) |
| Push test | GREEN | 100% | weakest tipping push: 0.2 (0.2) x weight | 0.2 (world 0) | - |
| Slippery floor | NOT RELIABLE (would be red) | 0% | steady progress: 0 (0) cm | 0 (world 0) | fell (tipped over) (30) |
| Payload | n/a | - | - | - | the robot has no payload_part |
| Move 'wave' | GREEN | 100% | max body tilt: 6.27 (0.97) deg | 0.49 (world 8) | - |
| Move 'arms_up_both' | AMBER | 70% | max body tilt: 8.52 (1.98) deg | 1.1 (world 8) | tipped over (9) |
| Move 'arms_up_alternating' | GREEN | 100% | max body tilt: 6.67 (1) deg | 0.61 (world 8) | - |

**Summary.** Survives a nudge from every side in 100% of worlds; a push of 0.2 x body weight from the front tips it (median). Standing moves that never or almost never tip it: wave, arms_up_alternating. Move 'arms_up_both' tips the robot in 30% of worlds. The right leg servo is near its limit (peak 100% of stall, estimate) during the move 'arms_up_both' test. 7 walking scene(s) are marked not reliable for this robot: Foam feet crushing and rolling at their edges are not in this rigid model; Caduceus walking results are not reliable (the model tips backwards on the firmware walk, the real robot moves ~6 cm forward in 2 cycles).

**Push test** (tipping push in x body weight, median / p10; how far it slides when it does not tip, median):

| From | Tipping push | Survives nudge | Slide after nudge | after 0.5 x weight | after 1 x weight |
|---|---|---|---|---|---|
| front | 0.2 / 0.2 | 100% | 0.3 cm | - | - |
| back | 0.3 / 0.2 | 100% | 0.3 cm | - | - |
| left | >1 / >1 | 100% | 0.2 cm | 1.0 cm | 6.9 cm |
| right | >1 / >1 | 100% | 0.2 cm | 1.3 cm | 7.5 cm |

Mid-walk nudge survived (NOT RELIABLE for this robot): front 0%, back 0%, left 0%, right 0%

**Servo load (estimate)**: highest peak per joint across scenes.

| Joint | Peak (% of stall) | Time near limit (median %) | In scene |
|---|---|---|---|
| left_arm | 100% | 0% | Move 'arms_up_both' |
| left_leg | 100% | 0% | Move 'arms_up_both' |
| right_arm | 100% | 0% | Move 'arms_up_both' |
| right_leg | 100% | 0% | Move 'arms_up_both' |

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
