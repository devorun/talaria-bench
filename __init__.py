"""Talaria Bench: a physics test bench for DIY servo robots, inside Hermes.

Describe a robot (parts, sizes, masses, hobby servos) in a YAML spec, test it in MuJoCo across many
randomized worlds, and preflight every move before it plays on the robot. CPU only.

Registers:

* tools: robot_list, robot_define, robot_show, bench_run, bench_status, bench_report, bench_compare,
  move_check, move_save, move_list, robot_play, robot_pose, robot_stop, robot_status
* hook: pre_tool_call, which lets robot_play / robot_pose through only with a passing preflight for
  exactly that move, speed and robot spec
* ``/talaria`` in every chat and ``hermes talaria`` in the terminal (plus ``firmware`` and ``sim``)

Modules are imported lazily inside ``register`` so that tests and ``devcli.py`` can load the package
without Hermes, and pytest can collect the plugin directory without a parent package.
"""

from __future__ import annotations

TOOLSET = "talaria"
_RUNTIME = None
_TOOLS = None
EMOJI = {
    "robot_list": "🤖", "robot_define": "📐", "robot_show": "🔎", "bench_run": "🧪", "bench_status": "⏳",
    "bench_report": "📋", "bench_compare": "⚖️", "move_check": "🛡️", "move_save": "💾", "move_list": "📚",
    "robot_play": "💃", "robot_pose": "🦾", "robot_stop": "✋", "robot_status": "📡",
}


def register(ctx) -> None:
    from . import schemas
    from .commands import SLASH_HELP, cli_handler, setup_cli, slash_handler
    from .hooks import make_pre_tool_call
    from .runtime import Runtime
    from .tools import TalariaTools

    global _RUNTIME, _TOOLS
    runtime = Runtime(ctx)
    tools = TalariaTools(runtime)
    _RUNTIME, _TOOLS = runtime, tools          # dashboard/plugin_api.py reuses them in the same process
    handlers = tools.handlers()
    for schema in schemas.ALL:
        name = schema["name"]
        ctx.register_tool(name=name, toolset=TOOLSET, schema=schema, handler=handlers[name],
                          description=schema["description"], emoji=EMOJI.get(name, ""))
    ctx.register_hook("pre_tool_call", make_pre_tool_call(runtime))
    ctx.register_command("talaria", slash_handler(runtime, tools), description="Talaria Bench: " + SLASH_HELP,
                         args_hint="[status|gallery|bench|report|check|play|demo]")
    ctx.register_cli_command("talaria", help="Talaria Bench: test DIY servo robots in simulation",
                             setup_fn=setup_cli, handler_fn=cli_handler(runtime, tools),
                             description="Benchmark robots, preflight moves, write firmware, run a virtual robot.")
