"""The ``pre_tool_call`` gate: robot_play and robot_pose run only with a passing preflight for exactly that
move, speed and robot spec. No simulation here (it only hashes and reads one small file), so it is fast.
Every other tool passes through untouched.

The same check runs inside the robot_play / robot_pose handlers too, so ``/talaria play`` and
``hermes talaria play`` (which do not go through the model's tool loop) are gated the same way.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from . import preflight
from .motion import MoveError
from .runtime import Runtime
from .schemas import GATED

logger = logging.getLogger(__name__)

DEFAULT_POSE_MS = 600


def requested_move(rt: Runtime, tool_name: str, args: dict[str, Any]):
    """(spec, move name, move, speed) that ``tool_name`` with ``args`` would play."""
    args = args or {}
    robot = args.get("robot") or rt.setting("real_robot")
    spec = rt.robot(str(robot))
    if tool_name == "robot_pose":
        joints = args.get("joints")
        if not isinstance(joints, dict) or not joints:
            raise MoveError(["joints must be an object of joint name -> angle"])
        move = {"frames": [{"ms": args.get("ms") or DEFAULT_POSE_MS, "joints": joints}]}
        return spec, "pose", move, 1.0
    name, move = rt.resolve_move(spec, args.get("move"), args.get("frames"), args.get("loops"), args.get("easing"))
    speed = args.get("speed")
    return spec, name, move, float(speed) if speed is not None else 1.0


def block_reason(rt: Runtime, tool_name: str, args: dict[str, Any]) -> Optional[str]:
    """None when the call may run, else a plain-words reason."""
    return gate(rt, tool_name, args)[0]


def gate(rt: Runtime, tool_name: str, args: dict[str, Any]):
    """(reason, None) when blocked, else (None, (spec, name, move, speed)): the handler plays exactly the move
    this check approved, without resolving the robot spec or a saved move a second time."""
    try:
        resolved = requested_move(rt, tool_name, args)
    except KeyError as exc:
        return f"Blocked: {exc.args[0] if exc.args else exc}.", None
    except MoveError as exc:
        return "Blocked: the move cannot be played as written: " + "; ".join(exc.problems), None
    except (TypeError, ValueError) as exc:
        return f"Blocked: {exc}", None
    spec, name, move, speed = resolved
    key = preflight.approval_key(spec, move, speed)
    record = preflight.ApprovalStore(rt.folder("approvals")).get(key)
    if record is not None and record.get("verdict") == "pass":
        return None, resolved
    return _blocked_text(spec, name, move, speed, tool_name, record), None


def _blocked_text(spec, name: str, move: dict[str, Any], speed: float, tool_name: str,
                  record: Optional[dict[str, Any]]) -> str:
    what = f"{spec.name} / {name}" + (f" at speed {speed:g}" if speed != 1.0 else "")
    if tool_name == "robot_pose":
        how = ("run move_check with robot " + spec.name + " and frames [{\"ms\": " + str(move["frames"][0]["ms"])
               + ", \"joints\": <the same joints>}] first")
    else:
        how = "run move_check on it first" + (" (with the same speed)" if speed != 1.0 else "")
    if record is None:
        return (f"Blocked: {what} has no preflight for this exact move, speed and robot spec; {how}. "
                "Any change to the frames, timing, speed or the robot spec needs a new check.")
    t = record.get("tip") or {}
    pct = preflight._pct
    head = f"Blocked: {what} did not pass preflight ({record.get('verdict')})"
    if t.get("falls"):
        head += (f": tips in {pct(t.get('rate', 0))} ({pct(t.get('low', 0))}-{pct(t.get('high', 0))}) of "
                 f"{record.get('worlds')} simulated worlds")
    reasons = [r for r in record.get("reasons") or [] if not r.startswith("tips in")]
    tips = record.get("suggestions") or []
    msg = head + "."
    if reasons:
        msg += " " + "; ".join(reasons) + "."
    if tips:
        msg += " Try: " + " ".join(tips)
    return msg


def make_pre_tool_call(rt: Runtime):
    def on_pre_tool_call(tool_name: str = "", args: Optional[dict[str, Any]] = None, **kwargs: Any):
        if tool_name not in GATED:
            return None
        try:
            reason = block_reason(rt, tool_name, args or {})
        except Exception as exc:   # never let a hook bug turn into an allowed move
            logger.exception("talaria-bench: preflight gate failed")
            reason = f"Blocked: the preflight gate could not check this call ({exc})."
        if reason is None:
            return None
        return {"action": "block", "message": reason}

    return on_pre_tool_call
