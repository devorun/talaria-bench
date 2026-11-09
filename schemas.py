"""Tool schemas (OpenAI function format) for the model."""

from __future__ import annotations

ROBOT = {"type": "string", "description": "Robot name, as listed by robot_list (e.g. caduceus, spider8)."}
TARGET = {"type": "string", "enum": ["virtual", "real"],
          "description": "virtual = a simulated robot on this computer (default); real = the robot at the robot_url "
                         "setting. Use real only when the user asks for the real robot."}
FRAMES = {"type": "array", "description": "Keyframes in order. Each frame: {\"ms\": travel time, \"hold\": optional "
                                          "pause in ms, \"joints\": {joint name: angle in degrees}}. Joints left out "
                                          "keep their angle.",
          "items": {"type": "object"}}
MOVE_FIELDS = {
    "move": {"type": "string", "description": "Name of a move of this robot (built-in or saved with move_save)."},
    "frames": FRAMES,
    "loops": {"type": "integer", "minimum": 1, "maximum": 20, "description": "Times to play the frames (default 1)."},
    "easing": {"type": "string", "enum": ["smoothstep", "linear"],
               "description": "smoothstep (default) eases in and out; linear moves at one constant speed."},
    "speed": {"type": "number", "minimum": 0.1, "maximum": 2.0,
              "description": "Playback speed factor: 0.5 makes every transition twice as long (default 1)."},
}

ROBOT_LIST = {
    "name": "robot_list",
    "description": "List the robots the bench knows: the bundled examples and robots the user defined, with "
                   "family, servo count, mass and moves.",
    "parameters": {"type": "object", "properties": {}},
}

ROBOT_DEFINE = {
    "name": "robot_define",
    "description": "Add (or update) a user robot. Preferred: template + params, which builds a valid, standing "
                   "model from a few numbers (cm, g); leave unknown values out and the template uses documented "
                   "estimates (returned in estimates_and_notes - tell the user which values are estimates). "
                   "Templates: block_robot (box body + side arms + middle legs on pitch hinges, like Caduceus; "
                   "body_width, body_height, body_depth, arm_length, leg_length, limb_width, limb_depth, arms, "
                   "legs), biped4 (body_width), quadruped (servos 8|12, body_length), hexapod (servos 12|18, "
                   "body_length), arm (joints 4-7, upper_arm, forearm, base_radius), humanoid (height). All take "
                   "name (lowercase), mass_g (total, optional), servo (SG90, MG90S, MG996R, DS3218), material "
                   "(foam, pla, wood, metal, rubber). Alternative: spec_yaml with a full Talaria spec. photo_path: "
                   "the local path of the robot's photo (from '[Image attached at: <path>]' or 'available on disk at <path>'); it is copied and "
                   "shown next to the 3D model. Bundled robot names cannot be replaced.",
    "parameters": {"type": "object", "properties": {
        "template": {"type": "string", "enum": ["block_robot", "biped4", "quadruped", "hexapod", "arm", "humanoid"]},
        "params": {"type": "object", "description": "Template parameters, e.g. {\"name\": \"my_bot\", "
                                                    "\"arm_length\": 23.5, \"mass_g\": 400, \"servo\": \"MG90S\"}"},
        "spec_yaml": {"type": "string", "description": "Full spec as YAML (instead of template)."},
        "photo_path": {"type": "string", "description": "Local path of a JPEG/PNG/WebP photo of the robot."}}},
}

ROBOT_SHOW = {
    "name": "robot_show",
    "description": "Show one robot: parts, joints with ranges and servos, moves, model limitations, hardware "
                   "mapping and the latest benchmark headline.",
    "parameters": {"type": "object", "properties": {"robot": ROBOT}, "required": ["robot"]},
}

BENCH_RUN = {
    "name": "bench_run",
    "description": "Start the test arena for a robot in the background (flat, ramps, obstacles, pushes, slippery "
                   "floor, payload; many randomized simulated worlds each). Returns a job id at once; follow it "
                   "with bench_status and read the result with bench_report. Simulation only.",
    "parameters": {"type": "object", "properties": {
        "robot": ROBOT,
        "scenes": {"type": "array", "items": {"type": "string"},
                   "description": "Scene ids or families (flat, ramp, obstacle, push, slippery, payload, move). "
                                  "Default: all that apply."},
        "worlds": {"type": "integer", "minimum": 10, "maximum": 200, "description": "Worlds per scene (default 30)."},
        "quick": {"type": "boolean", "description": "10 worlds per scene, for a fast first look."}},
        "required": ["robot"]},
}

BENCH_STATUS = {
    "name": "bench_status",
    "description": "Status of a benchmark or comparison job, or the recent jobs when no id is given. With a job_id it "
                   "waits until the job finishes (up to wait_s, 90 s by default) and then says what to call next, so "
                   "one call is usually enough.",
    "parameters": {"type": "object", "properties": {
        "job_id": {"type": "string"},
        "wait_s": {"type": "number", "minimum": 0, "maximum": 300,
                   "description": "Seconds to wait for the job to finish (default 90; 0 returns at once)."}}},
}

BENCH_REPORT = {
    "name": "bench_report",
    "description": "The report card of a finished job, or the latest benchmark report of a robot (this machine's, "
                   "else the bundled one). Markdown plus the one-paragraph summary.",
    "parameters": {"type": "object", "properties": {"job_id": {"type": "string"}, "robot": ROBOT}},
}

BENCH_COMPARE = {
    "name": "bench_compare",
    "description": "Compare design variants of a robot on the same simulated worlds, in the background (returns a "
                   "job id). A variant is {name, set: {path: value}} with paths like parts.body.mass, "
                   "parts.*.joint.servo, bench.walk_move (values absolute, or relative as \"+1.5\", \"-2\", "
                   "\"*1.2\"), or {name, robot} to compare against another robot.",
    "parameters": {"type": "object", "properties": {
        "robot": ROBOT,
        "variants": {"type": "array", "minItems": 1, "maxItems": 6, "items": {"type": "object"}},
        "scenes": {"type": "array", "items": {"type": "string"}},
        "worlds": {"type": "integer", "minimum": 10, "maximum": 200},
        "quick": {"type": "boolean"}},
        "required": ["robot", "variants"]},
}

MOVE_CHECK = {
    "name": "move_check",
    "description": "Preflight a move before it plays: simulate it in randomized worlds on flat ground and report "
                   "the tip chance with a 95% interval, estimated peak servo loads, collisions and speed-limit "
                   "stretches. PASS (upper tip bound <= 10% and no joint above 90% of stall) records an approval for "
                   "exactly this move, speed and robot spec; robot_play and robot_pose need it. Check a named move "
                   "(move) or your own frames (frames, loops, easing). When the verdict is fail (BLOCKED): tell the "
                   "user the tip chance in plain words, then revise the move following the suggestions (one limb at a "
                   "time, longer ms per frame, or a lower speed) and check the revised frames again; once it passes, "
                   "play exactly those frames (or save them with move_save and play that name). Never retry the "
                   "blocked move as it was. Simulation-based risk screening, not a safety guarantee. Takes a few "
                   "seconds.",
    "parameters": {"type": "object", "properties": {
        "robot": ROBOT, **MOVE_FIELDS,
        "quick": {"type": "boolean", "description": "Start with 30 worlds instead of 60; a clean run is extended "
                                                    "to 60 automatically so it can still pass."}},
        "required": ["robot"]},
}

MOVE_SAVE = {
    "name": "move_save",
    "description": "Save a move for a robot under a new name (checked against joint ranges and speed limits). "
                   "Saving does not approve it: run move_check before playing it.",
    "parameters": {"type": "object", "properties": {
        "robot": ROBOT,
        "name": {"type": "string", "description": "lowercase letters, digits, - and _"},
        "frames": FRAMES, "loops": MOVE_FIELDS["loops"], "easing": MOVE_FIELDS["easing"],
        "description": {"type": "string"}},
        "required": ["robot", "name", "frames"]},
}

MOVE_LIST = {
    "name": "move_list",
    "description": "List a robot's moves (built-in and saved) with duration and the latest preflight verdict.",
    "parameters": {"type": "object", "properties": {"robot": ROBOT}, "required": ["robot"]},
}

ROBOT_PLAY = {
    "name": "robot_play",
    "description": "Play a move on the virtual robot (default) or the real one. It plays only what passed move_check: "
                   "the same named move or the same frames, at the same speed, on the same robot spec; anything else "
                   "is refused before it reaches the robot, with the reason and what to change.",
    "parameters": {"type": "object", "properties": {"robot": ROBOT, **MOVE_FIELDS, "target": TARGET},
                   "required": ["robot"]},
}

ROBOT_POSE = {
    "name": "robot_pose",
    "description": "Move some joints to angles (one frame). Needs a passing move_check of the same single frame "
                   "(frames: [{ms, joints}]) first.",
    "parameters": {"type": "object", "properties": {
        "robot": ROBOT,
        "joints": {"type": "object", "description": "joint name -> angle in degrees"},
        "ms": {"type": "integer", "minimum": 50, "maximum": 10000, "description": "Travel time (default 600)."},
        "target": TARGET},
        "required": ["robot", "joints"]},
}

ROBOT_STOP = {
    "name": "robot_stop",
    "description": "Stop the robot now (never refused). home=true then eases back to the home pose.",
    "parameters": {"type": "object", "properties": {"robot": ROBOT, "target": TARGET, "home": {"type": "boolean"}}},
}

ROBOT_STATUS = {
    "name": "robot_status",
    "description": "Joint angles and whether a move is playing, on the virtual or the real robot.",
    "parameters": {"type": "object", "properties": {"robot": ROBOT, "target": TARGET}},
}

ALL = [ROBOT_LIST, ROBOT_DEFINE, ROBOT_SHOW, BENCH_RUN, BENCH_STATUS, BENCH_REPORT, BENCH_COMPARE, MOVE_CHECK,
       MOVE_SAVE, MOVE_LIST, ROBOT_PLAY, ROBOT_POSE, ROBOT_STOP, ROBOT_STATUS]
NAMES = [s["name"] for s in ALL]
GATED = ("robot_play", "robot_pose")
