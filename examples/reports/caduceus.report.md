# Report card: Caduceus (simulation)

*Simulation results (MuJoCo, randomized worlds). Simulation-based risk screening, not a guarantee.*

Robot `caduceus` (437 g, 4 servos, spec `88cab10ab914`), 30 worlds per scene (seeds 0..29), 11 s.

| Scene | Status | Pass | Main metric: median (p10) | Worst | Top failure reasons |
|---|---|---|---|---|---|
| Flat floor | OUT OF MODEL SCOPE | - | - | - | not scored (see limitations) |
| Ramp 5 deg | OUT OF MODEL SCOPE | - | - | - | not scored (see limitations) |
| Ramp 10 deg | OUT OF MODEL SCOPE | - | - | - | not scored (see limitations) |
| Ramp 15 deg | OUT OF MODEL SCOPE | - | - | - | not scored (see limitations) |
| Bar 1 cm | OUT OF MODEL SCOPE | - | - | - | not scored (see limitations) |
| Bar 2 cm | OUT OF MODEL SCOPE | - | - | - | not scored (see limitations) |
| Push test | GREEN | 100% | weakest tipping push: 0.2 (0.2) x weight | 0.2 (world 0) | - |
| Slippery floor | OUT OF MODEL SCOPE | - | - | - | not scored (see limitations) |
| Payload | n/a | - | - | - | the robot has no payload_part |
| Move 'wave' | GREEN | 100% | max body tilt: 6.84 (0.92) deg | 9.1 (world 5038) | - |
| Move 'arms_up_both' | AMBER | 58% | max body tilt: 9.09 (3) deg | 65 (world 5001) | tipped over (25) |
| Move 'arms_up_alternating' | GREEN | 100% | max body tilt: 7.08 (1.01) deg | 8.95 (world 5038) | - |

**Summary.** Survives a nudge from every side in 100% of worlds; a push of 0.2 x body weight from the front tips it (median). Standing moves that never or almost never tip it: wave, arms_up_alternating. Move 'arms_up_both' tips the robot in 42% of 60 preflight worlds. The right leg servo is near its limit (peak 100% of stall, estimate) during the move 'arms_up_both' test. 7 walking scene(s) are outside this model's scope for this robot and are not scored: This rigid-body model does not simulate soft foam feet; the bench does not guess here.

**Push test** (tipping push in x body weight, median / p10; how far it slides when it does not tip, median):

| From | Tipping push | Survives nudge | Slide after nudge | after 0.5 x weight | after 1 x weight |
|---|---|---|---|---|---|
| front | 0.2 / 0.2 | 100% | 0.3 cm | - | - |
| back | 0.3 / 0.2 | 100% | 0.3 cm | - | - |
| left | >1 / >1 | 100% | 0.2 cm | 1.0 cm | 6.9 cm |
| right | >1 / >1 | 100% | 0.2 cm | 1.3 cm | 7.5 cm |

Mid-walk nudge: OUT OF MODEL SCOPE for this robot (not scored).

**Servo load (estimate)**: highest peak per joint across scenes.

| Joint | Peak (% of stall) | Time near limit (median %) | In scene |
|---|---|---|---|
| left_arm | 100% | 0% | Move 'arms_up_both' |
| left_leg | 100% | 0% | Move 'arms_up_both' |
| right_arm | 100% | 0% | Move 'arms_up_both' |
| right_leg | 100% | 0% | Move 'arms_up_both' |

_Servo load is an estimate: peak torque as a share of the datasheet stall torque. Stall torque is not a safe continuous torque; a servo held near it overheats._

**Outside model scope** (these scenes are shown as OUT OF MODEL SCOPE and not scored):

- locomotion: This rigid-body model does not simulate soft foam feet; the bench does not guess here.

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
- Move 'wave': plays 'wave' standing; pass: no fall
- Move 'arms_up_both': plays 'arms_up_both' standing; pass: no fall
- Move 'arms_up_alternating': plays 'arms_up_alternating' standing; pass: no fall

World ranges: friction 0.33..0.63, mass_scale 0.85..1.15, torque_scale 0.82..1.06, kp_scale 0.67..1.1, latency_s 0.005..0.034, offset_deg -2.5..2.5, floor_tilt_deg 0.1..1.2, tether_scale 0..1, tether_dir_deg 113..255
