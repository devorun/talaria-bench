# Robot spec format (talaria: 1)

A robot spec is a YAML file that describes a robot made of rigid parts moved by hobby servos.
Talaria Bench turns it into a MuJoCo model and runs moves on it. Examples:
[`examples/robots/caduceus.yaml`](../examples/robots/caduceus.yaml) (a foam-board biped) and
[`examples/robots/spider8.yaml`](../examples/robots/spider8.yaml) (an 8-servo quadruped).

**Units:** centimetres, grams, degrees. **Frame:** x forward, y left, z up; the robot faces +x.

## Top level

| key | required | meaning |
|---|---|---|
| `talaria` | yes | format version, `1` |
| `name` | yes | id: lowercase letters, digits, `-`, `_` (max 32) |
| `title`, `description` | no | display text |
| `photo` | no | image file next to the spec; appearance reference only, never used for physics |
| `voltage` | no | servo supply voltage, default `5.0` (servo torque and speed are interpolated) |
| `parts` | yes | list of parts (below) |
| `moves` | no | named keyframe moves (below) |
| `tether` | no | `{part, max_force_n, at}`: a power cable pulling horizontally on a part; `at` is the plug point in the part's frame (cm, default its center). An off-center plug also turns the robot |
| `worlds` | no | override randomization ranges, e.g. `friction: [0.4, 0.6]` (see `worlds.py`) |
| `limitations` | no | known model limits, `[{scope: locomotion, note: "..."}]`; scope `locomotion` (scenes that need walking), `standing`, `manipulation` or `all`. The report card marks results in that scope as "not reliable" and shows the note. Not part of the spec hash |
| `materials` | no | per-robot material overrides, e.g. `foam: {solref: [0.023, 1.0], solimp: [0.7, 0.95, 0.0038], friction: 1.0}` (solimp width in metres) |

Unknown keys are errors (typos are caught, not ignored).

## Parts

```yaml
- name: left_arm
  parent: head                 # omit for the root; exactly one part has no parent
  shape: box                   # box | cylinder | sphere
  size: [5.5, 5.5, 23.5]       # box [x depth, y width, z height]; cylinder [radius, length] (along z); sphere [radius]
  mass: 30                     # grams, include servos and electronics carried by the part
  material: foam               # foam | pla | wood | metal | rubber (contact softness + friction)
  color: "#c9ced6"             # optional, display only
  ground_contact: true         # may touch the floor (feet). Default false: touching the floor = fall
  friction: 1.2                # optional: this part's friction factor, replacing the material's (a rubber pad)
  com: [0, 0, 3]               # optional: centre of mass offset from the shape's center, cm (electronics on top)
  joint: {...}                 # a moving part (servo), or:
  pos: [0, 0, -3.5]            # a part fixed to its parent: its center in the parent's frame (cm)
```

The root is a free-floating body. The builder drops it so the lowest `ground_contact` part rests
on the floor in the home pose. Every other part needs either a `joint` or a `pos`.

### Joint (one hobby servo)

```yaml
joint:
  axis: pitch                  # pitch | roll | yaw | [x, y, z]
  anchor: [0, 11.2, 1.0]       # joint position in the parent's frame, parent center = origin (cm)
  offset: [0, 0, -9.25]        # this part's center relative to the joint at angle 0 (cm)
  range: [-72, 72]             # degrees, -180..180
  home: 0                      # optional rest angle, default 0
  servo: MG90S                 # SG90 | MG90S | MG996R | DS3218, {model: MG90S, backlash_deg: 2} (measured play),
                               # or inline {torque_kgcm, speed_s_per_60, backlash_deg[, mass_g]}
  max_speed: 240               # optional planning speed limit (deg/s), default: the servo's no-load speed
  hardware: {channel: 0, center_us: 1700, us_per_deg: 11.1, direction: -1}   # optional, for the real robot
```

Sign conventions for named axes (in the part's own frame, which starts aligned with the parent's):

* `pitch` (hinge axis 0 -1 0): positive swings the part's lower end forward (+x).
* `roll` (axis 1 0 0): positive moves the lower end to the left (+y).
* `yaw` (axis 0 0 1): positive turns the front to the left (counter-clockwise from above).

The joint name is the part name. Moves use these names.

## Moves

Same keyframe format as caduceus-body:

```yaml
moves:
  wave:
    description: Raise the right arm.
    loops: 1                   # play the frames this many times (1..10)
    repeat: false              # true = a gait: the simulator repeats it until the run time ends
    easing: linear             # smoothstep (default) | linear
    frames:
      - {ms: 1980, hold: 3000, joints: {right_arm: 72}}
      - {ms: 2895, joints: {right_arm: 0}}
```

With `smoothstep` each transition eases in and out from the current pose, and all joints arrive
together. With `linear` every moving joint turns at one constant speed (the largest change divided
by the frame time) and stops when it arrives. That is how a firmware loop that steps every servo by
the same amount behaves, for example Caduceus's `smoothMove`. A frame that would turn a joint
faster than its `max_speed` is slowed down (with a warning). Angles outside a joint's range are
errors.

## Calibration

`calibration.py` fits a spec to behaviour seen on video: it samples unknown parameters within
plausible ranges, runs moves, and keeps the sets that meet behaviour targets. See
`examples/robots/caduceus.calibration.yaml` and `docs/calibration-caduceus.md`.

## What the simulation adds (not in the spec)

* Each servo is a position actuator limited to the datasheet stall torque at the spec voltage. Stall
  torque is not a safe continuous torque; reported loads are estimates.
* Each servo has gear backlash: a free "play" hinge of +-backlash/2 behind the servo.
* Commands are rate-limited at the servo's no-load speed and delayed by the world's latency.
* Randomized worlds vary floor friction, masses, servo torque and stiffness, latency, servo
  calibration offsets, a slight floor tilt and the tether pull.

## Spec hash

`Spec.hash()` is a SHA-256 over the physics-relevant content after validation (parts, joints, servo
values at the spec voltage, tether, world ranges). It ignores comments, key order, part order,
title, description, photo, colors and moves, so cosmetic edits or a new move keep it; any physical
change gives a new hash. Motion preflight approvals are tied to it.
