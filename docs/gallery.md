# Robot gallery

Ready-made robots in `examples/robots/`, covering the main hobby robot families. Every number below
comes from simulation: the arena benchmark, 30 randomized worlds per scene. The full report cards
are in `examples/reports/<robot>.report.md` (and `.report.json` for the dashboard).

Regenerate the reports, then the table:

```
python talaria-bench/devcli.py bench examples/robots/<robot>.yaml --out bench/<robot>.json
python talaria-bench/devcli.py gallery --markdown
```

| Robot | Family | Servos | Mass | Role | Benchmark headline (simulation) |
|---|---|---|---|---|---|
| `arm6` Desk arm (6 servos) (fixed base) | arm | 6 | 758 g | The most common hobby robot of all; shows how much it can lift before a servo is near its limit. | Max safe payload (simulation estimate): median 100 g (p10 95 g); at 200 g the upper arm reaches 100% of stall. [4 green] |
| `caduceus` Caduceus | biped | 4 | 437 g | Devran's real robot - the model is fitted to video; arm gestures are in the model's scope, walking is not. | Move 'arms_up_both' tips the robot in 30% of worlds. [1 amber, 3 green, 7 out of model scope] |
| `caduceus_v2` Caduceus v2 (design variant) | biped | 4 | 437 g | "What would the fixed design do?" - compare it with caduceus. | Survives a nudge from every side in 100% of worlds; a push of 0.3 x body weight from the front tips it (median). [4 green, 7 out of model scope] |
| `desk-biped4` Desk biped (4 servos) | biped | 4 | 166 g | The most common robot in schools and maker clubs. | On flat ground it covers the target distance in 100% of worlds (median 18.88 cm). [1 amber, 6 green, 3 red] |
| `dog12` Robot dog (12 servos) | quadruped | 12 | 1600 g | The eye-catcher - a 12-servo dog that trots; shows where slopes, bars and slippery floors stop a trot. | On flat ground it covers the target distance in 97% of worlds (median 45.1 cm). [1 amber, 6 green, 3 red] |
| `humanoid16` Small humanoid (16 servos) | humanoid | 16 | 802 g | Dance and motion-preflight showcase - one dance is safe, one looks fine and tips it over. | Move 'dance_risky' tips the robot in 93% of worlds. [5 green, 1 red] |
| `spider8` Spider (8 servos) | quadruped | 8 | 250 g | A cheap 8-servo crawler that really walks in simulation - the arena success story. | On flat ground it covers the target distance in 100% of worlds (median 23.34 cm). [1 amber, 5 green, 3 red] |

## What works and what does not (simulation)

**desk-biped4** (4 x SG90, 166 g)
* Walk: an ankle rock plus a hip swing, a quarter cycle apart, 1 s per cycle. Median 18.9 cm in 8 s;
  100% of worlds pass the 5 cm bar.
* `turn_left`: only the left hip swings; about 150 deg in 8 s, almost on the spot. `dance` never falls.
* Climbs 5 deg (100%) and 10 deg (57%); fails 15 deg.
* Its feet barely lift, so it is stuck at both bars. Survives pushes up to 0.75 x its weight.

**dog12** (12 x MG996R at 6 V, 1.6 kg)
* `trot` (the arena gait, diagonal pairs, 0.6 s per cycle): median 45 cm in 8 s, 97% pass.
* `walk` (creep): median 44 cm in 20 worlds.
* Clears a 1 cm bar in 97% of worlds and a 2 cm bar in 50%.
* Climbs 5 deg in 90%; slides back or tips on 10-15 deg.
* `sit` and `stand` are safe. The dog does not tip under any push up to 1 x its weight; it slides
  1-3 cm instead.
* Slippery floor: the trot's feet skate (median foot slip while in contact 6.9 cm/s vs 5.0 cm/s on
  the normal floor) and the body glides on: median 107 cm vs 45 cm on the normal floor. Progress
  above 1.5 x the flat median is classified as "uncontrolled sliding", not success, so the scene is
  RED (20% pass; uncontrolled sliding in 22/30 worlds).
* Hip-pitch servos reach stall on ramps (an estimate).

**humanoid16** (10 x MG90S legs, 6 x SG90 arms, 6 V, 0.8 kg)
* No walk, so the locomotion scenes are n/a.
* `stand` 93%, `wave` 90%, `bow` 90% and `dance_safe` 93% stay upright.
* `dance_risky` (arms up and a fast hip twist) tips it in 93% of worlds: the motion-preflight demo.
* With three soft hobby servos in series per leg it is near the limit of standing at all. A first,
  heavier version (850 g, battery high, 5 V) could not stand.

**arm6** (MG996R base/shoulder/elbow, SG90 wrist/gripper, fixed base, 758 g)
* All moves are fine.
* Max safe payload (simulation estimate): median 100 g (p10 95 g).
  * At 100 g it passes in 90% of worlds: the gripper sags 1.3 cm off its no-load path (median) and the
    shoulder peaks at 66% of stall.
  * At 200 g the shoulder reaches stall.
* Set `base: free` to test a free-standing base for tipping.

**spider8**, **caduceus**, **caduceus_v2**: see the main README and `docs/calibration-caduceus.md`.

Time spent per new robot (including gait search): arm6 ~15 min, humanoid16 ~40 min (it found a
numerical bug in the gear-play model; see below), desk-biped4 ~15 min, dog12 ~15 min.

**Fixed-base note:** a fixed base is welded to the world, and MuJoCo does not filter contacts
between the world and its children. The arm's turret rubbed on the base until the builder excluded
those parent/child pairs explicitly. With the fix, the arm's payload p10 went from 50 to 95 g.

**Numerical note:** the free "play" hinge that models servo backlash first had an inertia of
1e-6 kg m^2. In long serial chains (the humanoid's legs) that made the simulation unstable: the
robot fell over standing still. It is now 1e-4 kg m^2. Spider and Caduceus results barely moved
(the Caduceus wave went 99% -> 100%, arms_up_both 41 -> 40/100), but the spider's ramp results
changed noticeably (10 deg ramp 0% -> 73%). The earlier spider ramp numbers came from that
artifact.
