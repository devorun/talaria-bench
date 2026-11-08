"""Talaria Bench: a physics test bench for DIY servo robots, inside Hermes.

Describe a robot (parts, sizes, masses, hobby servos) in a YAML spec, and run its moves in MuJoCo
across many randomized worlds before anything moves on the real robot. CPU only.

Modules are imported lazily inside ``register`` so that tests and ``devcli.py`` can load the package
without Hermes, and pytest can collect the plugin directory without a parent package.
"""

from __future__ import annotations


def register(ctx) -> None:
    """Hermes entry point. Tools, hooks, commands and the dashboard are added in later steps."""
    return None
