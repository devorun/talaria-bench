---
name: robot-onboarding
description: Add a user's own servo robot to Talaria Bench from a photo and/or a description, then show it in 3D, benchmark it and check its moves. Use when the user shares a robot photo, describes a robot they built, or asks to "add my robot".
---

# Robot onboarding: from a photo to a tested model

Goal: a sensible simulation model of the user's robot in a few minutes, with honest labels for what is
measured and what is estimated. Keep replies short and friendly.

## 1. Look first

If there is a photo, look at it and keep its local path: the message says `[Image attached at: <path>]`
or "available on disk at `<path>`" (Desktop and webapp attachments land in `~/.hermes/attachments/`).
Say in one or two lines what you see: the family (arm, biped, quadruped, hexapod, humanoid, or a
Caduceus-like block robot with side arms and middle legs), the main parts, the servos and joints you can
see. If you are unsure about something, say so instead of guessing silently.

## 2. Pick a template and draft numbers

`robot_define` builds a valid, standing model from a template, so never hand-write anchors or offsets:

| template | use for | key numbers (cm, g) |
|---|---|---|
| `block_robot` | box body with long side arms and short middle legs on pitch hinges (Caduceus-like) | body_width, body_height, body_depth, arm_length, leg_length, limb_width, limb_depth, arms, legs |
| `biped4` | 4-servo desk biped (hip + ankle per leg) | body_width |
| `quadruped` | 8-servo crawler or 12-servo dog | servos (8 or 12), body_length |
| `hexapod` | six legs | servos (12 or 18), body_length |
| `arm` | desk arm on a fixed base | joints (4-7), upper_arm, forearm, base_radius |
| `humanoid` | small humanoid | height |

Every template also takes `name` (lowercase, e.g. `my_bot`), `mass_g` (total), `servo` (SG90, MG90S,
MG996R, DS3218) and `material` (foam, pla, wood, metal, rubber).

## 3. Ask only what matters

Ask for at most three or four measurements, the ones that change the physics most: the main limb
length, the body size, the total mass if known, the servo model. Everything else takes the template's
defaults. If the user already gave numbers, do not ask again.

## 4. Define it

Call `robot_define` with `template`, `params` and `photo_path` (the attached image path). Read
`estimates_and_notes` and tell the user plainly which values are estimates (for example "masses are
estimated from the part sizes; the bench varies them by +/-30%").

## 5. Show it

Tell the user to open **Talaria Bench → Robot** (Hermes Desktop page or the dashboard tab) to see the 3D
model next to their photo. If they correct a number, call `robot_define` again with the same name and
the corrected params; it replaces their robot.

## 6. Offer the next steps

Offer, in one line each:
- a quick benchmark: `bench_run` with `quick: true`, then `bench_status` and `bench_report`;
- a move check: `move_check` on one of its moves before anything plays on the real robot.

Everything Talaria shows is simulation: say "in simulation", never promise how the real robot behaves.
