# Report card: Small humanoid (16 servos) (simulation)

*Simulation results (MuJoCo, randomized worlds). Simulation-based risk screening, not a guarantee.*

Robot `humanoid16` (802 g, 16 servos, spec `a009b4e9f5fa`), 30 worlds per scene (seeds 0..29), 10 s.

| Scene | Status | Pass | Main metric: median (p10) | Worst | Top failure reasons |
|---|---|---|---|---|---|
| Flat floor | n/a | - | - | - | the robot has no walk move |
| Ramp 5 deg | n/a | - | - | - | the robot has no walk move |
| Ramp 10 deg | n/a | - | - | - | the robot has no walk move |
| Ramp 15 deg | n/a | - | - | - | the robot has no walk move |
| Bar 1 cm | n/a | - | - | - | the robot has no walk move |
| Bar 2 cm | n/a | - | - | - | the robot has no walk move |
| Push test | GREEN | 93% | weakest tipping push: 0.2 (0.2) x weight | 0.05 (world 7) | tips at a nudge from the front (2) |
| Slippery floor | n/a | - | - | - | the robot has no walk move |
| Payload | n/a | - | - | - | the robot has no payload_part |
| Move 'stand' | GREEN | 100% | max body tilt: 2.3 (0.47) deg | 7.88 (world 5028) | - |
| Move 'wave' | GREEN | 100% | max body tilt: 2.73 (1.38) deg | 7.41 (world 5005) | - |
| Move 'bow' | GREEN | 100% | max body tilt: 11.89 (7.92) deg | 19.35 (world 5005) | - |
| Move 'dance_safe' | GREEN | 98% | max body tilt: 3.71 (2.38) deg | 44.64 (world 5033) | tipped over (1) |
| Move 'dance_risky' | RED | 5% | max body tilt: 60.03 (53.23) deg | 70.41 (world 5000) | tipped over (56), 'forearm_l' touched the floor (1) |

**Summary.** Walking scenes do not apply (the robot has no walk move). Survives a nudge from every side in 93% of worlds; a push of 0.3 x body weight from the front tips it (median). Standing moves that never or almost never tip it: stand, wave, bow, dance_safe. Move 'dance_risky' tips the robot in 95% of 60 preflight worlds. The upperarm r servo is near its limit (peak 100% of stall, estimate) during the move 'dance_risky' test.

**Push test** (tipping push in x body weight, median / p10; how far it slides when it does not tip, median):

| From | Tipping push | Survives nudge | Slide after nudge | after 0.5 x weight | after 1 x weight |
|---|---|---|---|---|---|
| front | 0.3 / 0.2 | 93% | 0.6 cm | - | - |
| back | 0.3 / 0.2 | 93% | 0.6 cm | - | - |
| left | 0.5 / 0.48 | 93% | 0.6 cm | 1.4 cm | - |
| right | 0.5 / 0.5 | 93% | 0.5 cm | - | - |

**Servo load (estimate)**: highest peak per joint across scenes.

| Joint | Peak (% of stall) | Time near limit (median %) | In scene |
|---|---|---|---|
| foot_l | 100% | 0% | Push test |
| foot_r | 100% | 0% | Push test |
| forearm_l | 34% | 0% | Move 'dance_risky' |
| forearm_r | 42% | 0% | Move 'wave' |
| hiproll_l | 100% | 0% | Move 'dance_risky' |
| hiproll_r | 100% | 0% | Move 'dance_risky' |
| hipyaw_l | 100% | 0% | Move 'dance_risky' |
| hipyaw_r | 100% | 0% | Move 'dance_risky' |
| shin_l | 100% | 0% | Move 'dance_safe' |
| shin_r | 100% | 0% | Move 'dance_safe' |
| shoulder_l | 100% | 0% | Move 'dance_risky' |
| shoulder_r | 100% | 0% | Move 'dance_risky' |
| thigh_l | 100% | 0% | Move 'dance_risky' |
| thigh_r | 100% | 0% | Move 'dance_risky' |
| upperarm_l | 100% | 0% | Move 'dance_risky' |
| upperarm_r | 100% | 0% | Move 'dance_risky' |

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
- Move 'stand': plays 'stand' standing; pass: no fall
- Move 'wave': plays 'wave' standing; pass: no fall
- Move 'bow': plays 'bow' standing; pass: no fall
- Move 'dance_safe': plays 'dance_safe' standing; pass: no fall
- Move 'dance_risky': plays 'dance_risky' standing; pass: no fall

World ranges: friction 0.3..0.7, mass_scale 0.85..1.15, torque_scale 0.7..1.1, kp_scale 0.6..1.2, latency_s 0..0.04, offset_deg -3..3, floor_tilt_deg 0..1.5, tether_scale 0..1, tether_dir_deg 120..240
