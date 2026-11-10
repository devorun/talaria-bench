# Changelog

## 1.0.0 (2026-11-10)

First public release.

- Robot spec (YAML: parts, sizes in cm, masses in g, hobby servo models) with a servo catalog, templates and
  a MuJoCo model builder (soft contacts by material, servo free play, actuators from servo data).
- Test arena: flat ground, ramps 5/10/15 deg, 1 and 2 cm bars, push test, slippery floor, payload (arms),
  each in randomized physics worlds, run as background jobs; report card with pass rates, median and worst
  cases and the reason for each failure.
- Design comparison of up to six variants on the same worlds.
- Motion preflight: tip chance over 60 fixed worlds with a 95% Wilson interval, servo load estimates,
  collisions and speed limits; a `pre_tool_call` gate lets `robot_play` / `robot_pose` through only for
  exactly the move, speed and robot spec that passed.
- Real robot: ESP32 + PCA9685 firmware generated per robot (`hermes talaria firmware`), shared random
  robot token, spec-hash check, a return to the home pose before every move that takes at least 3 seconds
  (also for `robot_stop home=true`; a quick drop tips a light robot over), a Wi-Fi link that stays awake;
  a virtual robot with the same
  HTTP API (`hermes talaria sim`).
- Dashboard tab and Desktop page from one UI source: gallery, 3D robot view with its photo, report card,
  compare view, move check with replay.
- 3D view: parts drawn by material with a servo horn at every joint; each scene shows its own numbers (ramp
  angle, bar height, floor friction, push force, payload mass) and a 10 cm scale mark; replays with slow
  motion and a mark on the part that touches the floor when a run tips. Appearance only, never physics.
- Arena page: a robot and at most one changed version (size, total mass, servo model) on one scene, 10 worlds,
  replayed side by side in the same world with the terrain drawn, plus a results table.
- Your own robots get a small 3D picture on their gallery card (their photo if 3D is unavailable); a new logo.
- A robot whose servos cannot hold it up (a big template with weak servos) is replayed as it collapses and says
  so when it is made; template servo defaults follow the size.
- Photo-assisted onboarding skill (`robot-onboarding`).
- Seven bundled robots, including Caduceus, calibrated against videos of the real foam-board robot.
