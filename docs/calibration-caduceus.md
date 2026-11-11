# Calibrating Caduceus against video (8 Nov 2026)

Every number on this page comes from simulation, except the lines marked "real robot". During
calibration the real robot was only observed on video and measured by hand. The published model and
its results come first, then the final decision that chose it. The earlier calibration experiments
(3b with real measurements, then 3a from video only) follow under their own heading. Their numbers
describe earlier versions of the model, not the published one.

## The published model

* **File:** `examples/robots/caduceus.yaml` (437 g, four MG90S servos, five parts).
* **Physics hash** (the spec hash that approvals and the firmware check):
  `88cab10ab91487a1aa7c49c4705618ee271a460a796f713c2a3031b363793eed` (shown as `88cab10ab914` in
  the report card).
* **Date:** the model was chosen on 8 Nov 2026 (see the next section). The file was last edited on
  9 Nov 2026, for the OLED wiring and appearance fields. These results were re-checked on 11 Nov 2026.
* **Basis:** the "legs carry weight" geometry, head centre of mass +3 cm, leg free play 6.5 deg,
  plus the 3a values for masses, depths, foam contact, cable and firmware timing.

Results of the published model (simulation):

| check | worlds | result |
|---|---|---|
| preflight `wave` (original firmware wave) | 60 fixed preflight worlds | **PASS**, tips in 0 of 60 (95% interval 0-6%) |
| preflight `arms_up_alternating` | 60 fixed preflight worlds | **PASS**, tips in 0 of 60 |
| preflight `arms_up_both` | 60 fixed preflight worlds | **BLOCKED**, tips in 25 of 60 (42%, 95% interval 30-54%) |
| `wave`, all video targets (no fall, level body, arm rises) | 100 fresh worlds, seeds 1000-1099 | 100% pass, 0 falls |
| `arms_up_both` | 100 worlds | 40 falls |
| `arms_up_alternating` | 100 worlds | 0 falls |
| push test (report card) | 30 worlds | survives a nudge from every side in 100%; 0.2 x body weight from the front tips it (median) |
| walking scenes (flat, ramps, bars, slippery floor) | - | OUT OF MODEL SCOPE, not scored |

Full report card: [examples/reports/caduceus.report.md](../examples/reports/caduceus.report.md).

On the real robot (10 Nov 2026): the gate held back `arms_up_both`, and a left-arm lift and the wave
played as checked. `arms_up_alternating` passes in simulation but tipped the real robot, because an
arm dragging on the table can tip it and arm-to-surface friction on soft foam is not modelled yet.

## How the published model was chosen (Decision, 8 Nov 2026: what `caduceus.yaml` is now)

* **Basis: the "legs carry weight" geometry from 3a.** The legs are 2 mm longer than the arms and
  the foam crushes, so all four feet touch, as measured. This is the geometry that reproduced the
  wave on video in 100% of worlds.
* **Added from 3b, because they keep the wave intact:**
  * head centre of mass +3 cm (electronics on top; measured range 2-4);
  * leg joint free play 6.5 deg (measured range 3-10; the play hinge's limit is the stop at the head).
* **Wave check in 100 fresh worlds** (seeds 1000-1099; measured before the numerical fix below): 99%
  pass all wave targets, with 0 falls, roll p90 0.2 deg and pitch p90 8.8 deg. Target was >= 95%
  no-tip with the body level: **met.** The published model, after that fix: **100% pass, 0 falls.**
* **Sensitivity** (before the numerical fix): the wave holds at the low and middle measured values
  (com 2-3 cm, play 3-6.5 deg: 99-100%). It breaks at the top of both ranges (com +4 cm and play
  10 deg: 34% pass, 10 falls).
* **Walking is a declared limitation:** `limitations: [{scope: locomotion, note: ...}]`. The note
  reads "This rigid-body model does not simulate soft foam feet; the bench does not guess here."
  On the firmware walk the model tips backwards in 100% of worlds, while the real robot moves
  ~6 cm forward. The report card shows every scene that needs walking as a grey "OUT OF MODEL
  SCOPE" (not scored) with that note.
* **Demo moves** (arm gestures; 100 worlds, Caduceus's own world ranges; measured before the
  numerical fix below, after which `arms_up_both` falls in 40/100 and the other two still in 0):

| move | what it does | falls / 100 |
|---|---|---|
| `wave` (original firmware) | right arm up to 72 deg in ~2 s, hold 3 s, down | 0 |
| `arms_up_alternating` | one arm up and down, then the other (250 ms per swing) | 0 |
| `arms_up_both` | both arms thrown up together (250 ms per swing, 288 deg/s), hold, down | **41** |

  `arms_up_both` is risky because of its speed. With the robot on its two in-line legs, the swing
  of both arms throws it. The same move at 600 ms per swing tips it in 4/100 worlds, at 300 ms in
  11/100, at 250 ms in 41/100. So "slow it down" or "one arm at a time" are honest fixes for
  preflight to suggest.
* **Later numerical fix (step 4b):** the backlash hinge's inertia was raised from 1e-6 to
  1e-4 kg m^2, because the old value made long serial chains unstable. Re-checked on Caduceus:
  * wave: 100% pass, 0 falls (was 99%);
  * arms_up_both: 40/100 (was 41);
  * arms_up_alternating: 0/100.
* **`caduceus_v2`** (design variant, not a robot): tight joints (1.5 deg everywhere) and the
  electronics low inside the head (centre of mass -2 cm); everything else is the same. Wave 100%
  pass; `arms_up_both` 0/100 falls (vs 40/100 for the real design after the numerical fix; 41/100
  before it). The walk is still outside the model's scope (same foam feet).

## Earlier calibration experiments (superseded, not the published model)

Everything below is kept as a record of how the model was reached. These runs came before the
decision above, so their numbers belong to earlier versions of the model, not to the published
`caduceus.yaml`. For example, the 39% wave pass rate is the 3a fit; the published model passes the
wave in 100% of worlds (0 of 60 preflight worlds tip). Where the text below says "current" or
"shipped", it means the model at that time.

### 3b: with real measurements (result: targets NOT met, caduceus.yaml values kept from 3a)

New facts (Devran, 8 Nov):
* All four feet touch the floor at rest: a card fits under none of them. The leg gap is 0 to -2 mm
  and the foam crushes.
* The leg joints have a deliberate large free play (3-10 deg) that ends against the head. The arm
  play is small.
* The electronics sit on top of the head, so the head's centre of mass is 2-4 cm high.
* The firmware walk `/ileri?n=2` (confirmed: `handleWalk`, the move modelled here) moves the robot
  about 6 cm forward in 2 cycles. The arms lift, swing forward, land in front and drag the body.
* Some videos are sped up, so the firmware speed still comes from the I2C code analysis
  (3.0-4.5 ms per step).

The source videos are now in `reference/videos/` (the 1 fps frame sheets are in
`reference/video-frames/*_1fps.jpg`). They confirm four feet on the floor at rest, and a level
head top edge through the whole wave in both clips (no visible roll).

New model features: per-part `com` (centre of mass offset) and per-joint backlash up to 20 deg.
The play hinge's limit is the mechanical stop (the head).

Targets: wave as before (no fall, roll < 5, pitch < 10, abs(yaw) < 5 deg, arm rises >= 2 cm);
walk no fall and **3-9 cm forward in 2 cycles**; walk yaw is reported only.
(`examples/robots/caduceus.calibration.yaml`, 400 sets, every other range as in 3a.)

| run (400 sets) | accepted | wave alone | walk alone | walk without a fall | closest set |
|---|---|---|---|---|---|
| 3b as measured (leg play 3-10 deg total) | 0 | 39% | 0% | 3/400 | wave ok; walk falls |
| legs mounted opposite to the firmware names (both) | 0 | 39% | 0% | 41/400 (max +2.6 cm) | wave ok; walk +2.6 cm, no fall |
| right leg only opposite | 0 | 39% | 1/400 | - | wave ok; walk +0.8 cm |
| leg play read as 3-10 deg each way (6-20 total) | 0 | 15% | 0% | 5/400 (max +5.6 cm) | wave ok; walk falls |

In 397 of 400 sets the walk tips over backwards, and always in the same way. In phase 1 the arms
swing forward but stay loaded, so the body leans about 8 deg forward instead of the arms lifting.
In phase 2 the loaded legs swing back with their feet stuck by friction, so the body rotates
backwards. The arms then leave the floor, and the robot balances on the 4-6 cm deep leg soles with
its centre of mass about 23 cm high. Past about 6 deg it falls.

The then-current `caduceus.yaml` (3a) against the 3b targets, in 100 worlds: wave 39% (60 falls); walk
0%, with forward median +0.25 cm where 3-9 cm is needed. (Earlier model; the published model passes
the wave in 100% of worlds.)

**What is probably missing.** The real robot does what the rigid model cannot: with all four feet
down, its arms lift and swing forward, and the loaded legs swing back without tipping it.
Candidates:
1. **Foam feet are not rigid boxes.** They crush, and their edges roll. That lets a loaded leg
   pivot under the body instead of levering it backwards, and lets the load move to the legs when
   an arm swings.
2. **Load sharing.** If the crushed leg foam carries most of the weight, the arms are almost
   unloaded and lift as described. The soft-contact model spreads the load more evenly.
3. **Leg play.** A side view of the walk would show whether the legs swing through their play
   without driving the body. Devran's "3-10 deg" may be per side, or larger.
4. **Leg direction.** If the leg servos turn opposite to the firmware names, the model falls far
   less (41/400 without a fall) but still comes short of 3 cm. A one-servo nudge test settles this.

A side-view clip of `/ileri?n=2` would decide between these. Until then the 3a fit stays the
shipped model, and its walk forward distance (~0 cm vs ~6 cm real) is a known error. (Written before
the decision of 8 Nov above, which replaced the 3a fit and declared walking out of the model's scope.)

**caduceus_v2** (`examples/robots/caduceus_v2.yaml`) is a design variant for step 4's design
comparison, not a real robot. Changes: legs level with the arms, 1.5 deg play on every joint,
electronics low inside the head (centre of mass 2 cm down). Results in 100 worlds with the 3b
targets:
* wave passes 92% (4 falls, pitch median 4.7 deg);
* the original firmware walk falls in 100% (backwards, phase 2): this gait needs the arms to carry
  the robot, and level legs make it tip.

### 3a: video only (superseded; selected parameters retained)

(Superseded by 3b's measurements. The published model keeps the 3a masses, depths, foam contact,
cable and firmware timing, but not the 3a leg gap: it uses the "legs carry weight" geometry.)

#### Summary

* **Walk: reproduced.** The calibrated model plays the original firmware walk without falling in
  100 of 100 fresh random worlds. Forward progress stays near zero (median +0.2 cm) and both legs
  swing off the floor (median 0.8 cm). That matches the "come here" clip.
* **Walk turning: not reproduced.** The clip shows roughly 20-30 deg of turning. The model turns
  less than 1 deg (p10..p90 -1.0..+0.9 deg). None of the plausible asymmetries I tried explains it
  together with the other targets (see "Hypotheses tested").
* **Wave: partly reproduced.** The original firmware wave passes all targets in 39 of 100 fresh
  worlds: the arm lifts about 10 cm, roll stays under 5 deg and the robot keeps facing forward. In
  60 of 100 worlds the model still tips the body forward or backward. The target was 95% no-tip, so
  **the wave target is not met.** Before calibration, 0 of 100 worlds passed.
* **The core conflict is the leg gap.** If the legs are 2 mm longer than the arms (they carry
  weight), the wave is perfect in 100% of worlds but the walk falls in 100%. If they are 1-3 mm
  shorter, the walk is perfect but the wave tips in about half the worlds. One fixed rigid geometry
  does not explain both clips.
* **The original firmware is probably about 2.5x slower than its code suggests.** Each
  `smoothMove` step writes 4 PCA9685 channels over 100 kHz I2C. The Adafruit library also reads the
  prescale register on every `writeMicroseconds`, which is roughly 1 ms per channel. With that,
  the walk runs at about 26 deg/s (not 60) and the wave arm takes about 2 s (not 0.4 s) to rise.
  This was the single most helpful finding, and it should be checked on video.

#### Inputs and how they were measured

The original videos were not in the work folder, so no frame-level measurement was possible. I
used the frame sheets in `reference/video-frames/` and the photo:

* `whatsapp_sheet.jpg` (wave, front view, wooden desk): the right arm swings forward and up, its
  foot clearly leaves the table, the head stays level and the robot keeps facing the camera.
* `come_here_sheet.jpg`, `walk_detail.jpg`, `before_after.jpg` (walk, front view, white wall): the
  legs swing and leave the floor, the head tilts sideways by a few degrees at times, and the
  start/end frames show a clear turn. FINDINGS.md estimates 20-30 deg. That estimate could not be
  checked without the video.

Both clips are front views. Side-to-side tilt (roll) and turning (yaw) show clearly from the
front. Front-back tilt (pitch) barely shows: 10 deg of pitch shortens the head by 1.5%. So the
wave target was split into roll < 5 deg, pitch < 10 deg and |yaw| < 5 deg, instead of a single
"tilt < 5 deg". The two clips have different backgrounds, so they were recorded on different
occasions.

#### Targets (`examples/robots/caduceus.calibration-3a.yaml`)

| move | requirement |
|---|---|
| wave | no fall; roll change < 5 deg; pitch change < 10 deg; abs(yaw) < 5 deg; right arm rises >= 2 cm |
| walk (2 cycles) | no fall; abs(forward) < 3 cm; each leg lifts >= 0.5 cm; *(yaw 15-40 deg: reported, not required, see below)* |

#### Model changes made for this step

* Moves get `easing: linear`, which plays like the firmware's `smoothMove`: every joint moves at
  one constant speed and stops when it arrives. Caduceus's wave and walk use it.
* New metrics: lift above the floor and contact fraction per ground-contact part; tilt change
  since settling, split into roll and pitch.
* Spec additions: `materials:` overrides (calibrated foam softness), `{model: MG90S,
  backlash_deg: 2}`, a per-part `friction` factor, and the tether plug point `at` (a pull at the
  plug point turns the robot; a pull at the center of mass cannot).
* `calibration.py` (generic: spec + parameter ranges + behaviour targets) and
  `devcli.py calibrate | validate`.

#### Method

Latin hypercube sampling with 400 parameter sets per run. Each set runs both moves. A set is
accepted if both moves meet all their requirements. Runs use 8 worker processes and take about
20 s each.

Parameters and plausible ranges (stage 1):

| parameter | range | note |
|---|---|---|
| leg gap (leg bottoms minus arm bottoms) | -3..+5 mm | |
| arm above its pivot | 1.5..4 cm | pivot height |
| head / arm / leg mass | 250-400 g / 15-40 g / 15-40 g | |
| arm / leg depth | 4-6 cm | |
| servo backlash | 1-3 deg | |
| foam contact softness | solref 0.01-0.05 s, width 1-8 mm | |
| floor friction / per-foot factor | 0.3-0.7 / 0.6-1.4 | factor: hand-wrapped tape |
| I2C overhead per smoothMove step | 0.5-4.5 ms | see Summary |
| cable pull, direction, plug point | 0-0.15 N, 90-270 deg, back/top half of the head | |
| servo offsets | +-3 deg each | |
| torque scale, stiffness scale, latency, floor tilt | 0.8-1.1, 0.6-1.2, 0-40 ms, 0-1.5 deg | |

Stage 2 (`caduceus.calibration-3a-stage2.yaml`) samples again inside the region stage 1 found:
leg gap +1..+3 mm and overhead 3.5-4.5 ms. Every other parameter keeps its full range.

Reproduce (from `talaria-work/`):

```
python talaria-bench/devcli.py calibrate examples/robots/caduceus.calibration-3a.yaml --out stage1.json
python talaria-bench/devcli.py calibrate examples/robots/caduceus.calibration-3a-stage2.yaml --out stage2.json
python talaria-bench/devcli.py validate examples/robots/caduceus.calibration-3a.yaml --worlds 100 --param step_overhead_ms=3.95
```

#### Results

**Stage 1:** 16 of 400 accepted (4.0%). The wave alone passed 32%, the walk alone 48%. The two
parameters that decide acceptance:

| I2C overhead | gap -3..0 mm | 0..+1 | +1..+2 | +2..+3 | +3..+5 |
|---|---|---|---|---|---|
| 0.5-2.5 ms | 0% (wave 58 / walk 0) | 0% | 8% | 0% (wave 0 / walk 96) | 0% |
| 2.5-3.5 ms | 7% | 5% | 0% | 7% | 0% |
| 3.5-4.5 ms | 0% (wave 52 / walk 0) | 9% | 25% | 30% | 9% |

(both targets passed; in brackets, the wave and walk pass rates separately)

**Stage 2:** 65 of 400 accepted (16.2%; wave 22%, walk 77%). Within this region the deciding
parameters are:
* a small cable pull: 33% accepted at 0-0.04 N, 5% above 0.08 N;
* stiffer foam contact;
* the direction of the floor tilt;
* the left arm's servo offset.

**Chosen nominal values** (`caduceus.yaml` at the time of 3a): the medians of the stage-2 accepted
sets, with the p10-p90 range in brackets. (The published model keeps these except the leg gap and the
backlash of the legs, see the top of this page.)

| | value |
|---|---|
| leg gap | +2.0 mm (1.1-2.7) |
| arm above pivot | 2.75 cm (1.7-3.8) |
| head / arm / leg mass | 325 g / 30 g / 26 g |
| arm / leg depth | 5.2 / 5.2 cm |
| backlash | 2.0 deg |
| foam contact | solref 0.023 s, width 3.8 mm |
| cable | 0.09 N max, plugged in at (-1.4, 0, 2.9) cm |
| move timing | I2C overhead 3.95 ms: wave up 1.98 s, hold 3 s, down 2.9 s; walk 26 deg/s |

The per-foot friction medians were all about 1.0, so they were left at 1.0. The world ranges were
set to the accepted p10-p90 of each parameter, for example friction 0.33-0.63 and servo offsets
+-2.5 deg.

**Validation in 100 fresh worlds** (seeds 1000-1099, drawn from each spec's own ranges):

| | before (step 2 model) | after (calibrated) |
|---|---|---|
| wave: all targets met | 0% | 39% |
| wave: falls | 58 | 60 |
| wave: right arm rise, median | 1.9 cm | 10.4 cm |
| wave: yaw, median | -77 deg | -2.4 deg |
| wave: roll change, median | 38.5 deg | 1.2 deg |
| walk: all targets met | 99% | 100% |
| walk: falls | 1 | 0 |
| walk: forward, median | -0.4 cm | +0.2 cm |
| walk: yaw, p10..p90 | -0.1..+0.1 deg | -1.0..+0.9 deg |
| walk: legs lift, median | 1.5 cm (never touched the floor) | 0.8 cm (from 2 mm) |

**The three candidate geometries** (100 worlds each, calibrated ranges):

| nominal | leg gap | wave passes | walk passes |
|---|---|---|---|
| median of accepted (shipped at the time of 3a) | +2.0 mm | 39% | 100% |
| most central accepted set | +1.25 mm | 49% | 99% |
| legs carry weight (the basis of the published model) | -2.0 mm | **100%** (pitch 1.4 deg, yaw < 1 deg) | **0%** (falls backwards) |

Images (simulation, nominal world, side view): `img/caduceus-wave-side.png`, `img/caduceus-walk-side.png`.

#### Hypotheses tested and rejected (400 sets each, stage-1 style)

These runs came before the I2C finding, so they used the fast nominal firmware timing. Some also
used the earlier single "tilt < 5 deg" wave target.

| idea | why plausible | result |
|---|---|---|
| lower friction (0.15-0.7) | aluminium tape on lacquer | no change (0/400) |
| larger servo offsets (+-8 deg) and +-2 mm leg length error | one CENTER for all servos, 20-tooth spline; hand-cut foam | more falls (0/400) |
| legs in antiphase (one leg servo not mirrored) | front view could hide it; makes turning | walk 2% -> 5% (narrow band 4% -> 11%); both 0.5% |
| per-foot friction 0.6-1.4 | uneven tape | no change |
| servo torque down to 0.35x | supply sag over the long thin cable | no change |
| elastic horn mount (series spring) | glued foam on the horn | worse, and numerically unstable when stiff; removed |
| cable plug point | a pull at the plug point turns the robot | small effect; kept (it is real) |
| slower firmware (I2C overhead) | computed from the library | **decisive: 0.5% -> 4% -> 16%** |

#### What is probably missing, and what would settle it

1. **The legs.** The two clips want different leg gaps. Were both clips recorded with the same
   legs (no spacer, pad or re-glue in between)? The spike already had a "spacer" variant. A quick
   paper-slip test under each leg, with the robot standing, measures the real gap.
2. **The turn in the walk.** It may come from something not modelled: the cable snagging, an
   uneven table, or a foam leg twisting on its horn. Copying `come_here.mp4` to `reference/videos/`
   would let us measure yaw per frame.
3. **Timing.** Timing the wave arm's rise on video checks the I2C slowness: about 2 s predicted,
   0.4 s if the overhead were zero.
4. **Rigid limbs.** Foam limbs bend and the foam feet crush at their edges. The model has rigid
   boxes with soft contact only. Real compliance may let the load move from legs to arms as needed,
   which would be the "both behaviours" mechanism the rigid model lacks.

Consequence for the product (3a model, at the time): the calibrated Caduceus is conservative about arm
gestures. Preflight will flag the original wave as a tip risk in about 60% of worlds, while the real
robot does it. Present this as simulation-based risk screening, never as a guarantee. (The published
model no longer has this problem: the wave tips in 0 of 60 preflight worlds.)
