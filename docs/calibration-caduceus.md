# Calibrating Caduceus against video (8 Nov 2026)

Every number on this page comes from simulation. The real robot was only observed on video.

## Summary

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

## Inputs and how they were measured

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

## Targets (`examples/robots/caduceus.calibration.yaml`)

| move | requirement |
|---|---|
| wave | no fall; roll change < 5 deg; pitch change < 10 deg; abs(yaw) < 5 deg; right arm rises >= 2 cm |
| walk (2 cycles) | no fall; abs(forward) < 3 cm; each leg lifts >= 0.5 cm; *(yaw 15-40 deg: reported, not required, see below)* |

## Model changes made for this step

* Moves get `easing: linear`, which plays like the firmware's `smoothMove`: every joint moves at
  one constant speed and stops when it arrives. Caduceus's wave and walk use it.
* New metrics: lift above the floor and contact fraction per ground-contact part; tilt change
  since settling, split into roll and pitch.
* Spec additions: `materials:` overrides (calibrated foam softness), `{model: MG90S,
  backlash_deg: 2}`, a per-part `friction` factor, and the tether plug point `at` (a pull at the
  plug point turns the robot; a pull at the center of mass cannot).
* `calibration.py` (generic: spec + parameter ranges + behaviour targets) and
  `devcli.py calibrate | validate`.

## Method

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

Stage 2 (`caduceus.calibration-stage2.yaml`) samples again inside the region stage 1 found:
leg gap +1..+3 mm and overhead 3.5-4.5 ms. Every other parameter keeps its full range.

Reproduce (from `talaria-work/`):

```
python talaria-bench/devcli.py calibrate examples/robots/caduceus.calibration.yaml --out stage1.json
python talaria-bench/devcli.py calibrate examples/robots/caduceus.calibration-stage2.yaml --out stage2.json
python talaria-bench/devcli.py validate examples/robots/caduceus.calibration.yaml --worlds 100 --param step_overhead_ms=3.95
```

## Results

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

**Chosen nominal values** (`caduceus.yaml`): the medians of the stage-2 accepted sets, with the
p10-p90 range in brackets.

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
| median of accepted (shipped) | +2.0 mm | 39% | 100% |
| most central accepted set | +1.25 mm | 49% | 99% |
| legs carry weight | -2.0 mm | **100%** (pitch 1.4 deg, yaw < 1 deg) | **0%** (falls backwards) |

Images (simulation, nominal world, side view): `img/caduceus-wave-side.png`, `img/caduceus-walk-side.png`.

## Hypotheses tested and rejected (400 sets each, stage-1 style)

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

## What is probably missing, and what would settle it

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

Consequence for the product: the calibrated Caduceus is conservative about arm gestures. Preflight
will flag the original wave as a tip risk in about 60% of worlds, while the real robot does it.
Present this as simulation-based risk screening, never as a guarantee.
