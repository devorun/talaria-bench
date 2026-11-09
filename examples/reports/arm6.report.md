# Report card: Desk arm (6 servos) (simulation)

*Simulation results (MuJoCo, randomized worlds). Simulation-based risk screening, not a guarantee.*

Robot `arm6` (758 g, 6 servos, spec `297eee32befb`), 30 worlds per scene (seeds 0..29), 6 s.

| Scene | Status | Pass | Main metric: median (p10) | Worst | Top failure reasons |
|---|---|---|---|---|---|
| Flat floor | n/a | - | - | - | the robot has no walk move |
| Ramp 5 deg | n/a | - | - | - | the robot has no walk move |
| Ramp 10 deg | n/a | - | - | - | the robot has no walk move |
| Ramp 15 deg | n/a | - | - | - | the robot has no walk move |
| Bar 1 cm | n/a | - | - | - | the robot has no walk move |
| Bar 2 cm | n/a | - | - | - | the robot has no walk move |
| Push test | n/a | - | - | - | the base is fixed to the table |
| Slippery floor | n/a | - | - | - | the robot has no walk move |
| Payload | GREEN | 100% | max safe payload: 100 (95) g | 50 (world 1) | - |
| Move 'home' | GREEN | 100% | max body tilt: 0 (0) deg | 0 (world 5000) | - |
| Move 'wave' | GREEN | 100% | max body tilt: 0 (0) deg | 0 (world 5000) | - |
| Move 'pick_and_place' | GREEN | 100% | max body tilt: 0 (0) deg | 0 (world 5000) | - |

**Summary.** Walking scenes do not apply (the robot has no walk move). Standing moves that never or almost never tip it: home, wave, pick_and_place. Max safe payload (simulation estimate): median 100 g (p10 95 g); at 200 g the upper arm reaches 100% of stall.

**Payload** (move 'pick_and_place', weight at 'hand'; a step passes below 80% of stall, no tipping, < 2 cm drift):

| Payload | Pass | Peak load (median, % of stall) | Drift (median) | Tipped | Limiting joint |
|---|---|---|---|---|---|
| 0 g | 100% | 34% | 0.0 cm | 0 | upper_arm |
| 50 g | 100% | 49% | 0.7 cm | 0 | upper_arm |
| 100 g | 90% | 66% | 1.3 cm | 0 | upper_arm |
| 200 g | 0% | 100% | 3.0 cm | 0 | upper_arm |
| 300 g | 0% | 100% | 42.3 cm | 0 | upper_arm |

**Servo load (estimate)**: highest peak per joint across scenes.

| Joint | Peak (% of stall) | Time near limit (median %) | In scene |
|---|---|---|---|
| finger | 22% | 0% | Payload |
| forearm | 33% | 0% | Payload |
| hand | 32% | 0% | Move 'wave' |
| turret | 30% | 0% | Payload |
| upper_arm | 47% | 0% | Payload |
| wrist | 44% | 0% | Move 'wave' |

_Servo load is an estimate: peak torque as a share of the datasheet stall torque. Stall torque is not a safe continuous torque; a servo held near it overheats._

**Conditions**

- Flat floor: move 'None', pass: >= 5 cm steady progress, no fall
- Ramp 5 deg: slope 5 deg uphill, pass: climbs >= 5 cm, no fall or slide back
- Ramp 10 deg: slope 10 deg uphill, pass: climbs >= 5 cm, no fall or slide back
- Ramp 15 deg: slope 15 deg uphill, pass: climbs >= 5 cm, no fall or slide back
- Bar 1 cm: bar 1 cm high, 2 cm deep, 5 cm ahead; pass: root 5 cm past it
- Bar 2 cm: bar 2 cm high, 2 cm deep, 5 cm ahead; pass: root 5 cm past it
- Push test: pushes of 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1 x body weight for 0.1 s from 4 sides while standing; pass: survives the nudge (0.1 x weight) from every side
- Slippery floor: effective foot-floor friction 0.08-0.15 (any foot material); pass: 50-150% of the flat median and no fall; more than 150% = uncontrolled sliding
- Payload: payload steps lumped at the payload part; a step passes below 80% of stall at every joint, no tipping and < 2 cm drift from the no-load path; pass: >= the first non-zero step
- Move 'home': plays 'home' standing; pass: no fall
- Move 'wave': plays 'wave' standing; pass: no fall
- Move 'pick_and_place': plays 'pick_and_place' standing; pass: no fall

World ranges: friction 0.3..0.7, mass_scale 0.85..1.15, torque_scale 0.7..1.1, kp_scale 0.6..1.2, latency_s 0..0.04, offset_deg -3..3, floor_tilt_deg 0..1.5, tether_scale 0..1, tether_dir_deg 120..240
