"""The committed UI bundles (built by ui/build.mjs) follow the surface rules Hermes enforces."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop" / "plugin.js"
DASHBOARD = ROOT / "dashboard" / "dist" / "index.js"
ALLOWED = {"@hermes/plugin-sdk", "react", "react/jsx-runtime"}


def test_desktop_bundle_imports_only_the_sdk_and_react():
    src = DESKTOP.read_text(encoding="utf-8")
    specs = set(re.findall(r"^import\s[^;]*?from\s+\"([^\"]+)\"", src, re.M))
    assert specs and specs <= ALLOWED, specs
    assert re.search(r"export\s*(default\b|\{[^}]*\bas default\b)", src) and 'id: "talaria-bench"' in src
    # three.js sets defaults on its own classes' prototypes inside the bundle; patching built-in or DOM
    # prototypes (what catalog rule 8 is about) must never happen.
    builtin = (r"\b(?:Object|Array|Function|String|Number|Boolean|Promise|Map|Set|Element|HTMLElement|Node|"
               r"EventTarget|Document|Window|Response|Request|XMLHttpRequest)\.prototype\.[\w$]+\s*=[^=]")
    for bad in (r"(?<![\w$.])eval\(", r"\bnew\s+Function\(", r"<script\b", builtin, r"__proto__\s*=",
                r"\bObject\.setPrototypeOf\(",
                r"\bimport\(", r"document\.querySelector\([^)]*\[data-(?:slot|tour|sidebar|testid)"):
        assert not re.search(bad, src), bad


def test_dashboard_bundle_uses_the_dashboard_sdk():
    src = DASHBOARD.read_text(encoding="utf-8")
    assert "window.__HERMES_PLUGIN_SDK__" in src and '__HERMES_PLUGINS__.register("talaria-bench"' in src
    assert not re.search(r"^import\s", src, re.M)           # an IIFE, nothing to resolve at load time
    manifest = json.loads((ROOT / "dashboard" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "talaria-bench" and manifest["entry"] == "dist/index.js"
    assert manifest["api"] == "plugin_api.py" and manifest["tab"]["path"] == "/talaria"


def test_bundles_are_built_from_the_committed_sources():
    newest_src = max(p.stat().st_mtime for p in (ROOT / "ui" / "src").rglob("*") if p.is_file())
    assert DESKTOP.stat().st_mtime >= newest_src - 1 and DASHBOARD.stat().st_mtime >= newest_src - 1, \
        "run `cd ui && npm run build`"
