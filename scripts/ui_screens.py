"""Drive the real Talaria Bench UI with Playwright: smoke-test the main views, collect console errors and save
the README screenshots under docs/img/screens/. Dev tool (Playwright is not a plugin dependency).

    python talaria-bench/scripts/ui_screens.py dashboard [url]      # hermes dashboard, default 127.0.0.1:9119
    python talaria-bench/scripts/ui_screens.py webapp <link> [dark] # Desktop workspace: `hermes webapp --no-open`
    python talaria-bench/scripts/ui_screens.py desktop [cdp_url]    # Hermes Desktop started with
                                                                    # --remote-debugging-port=9222

Use a temporary HERMES_HOME for published screenshots, so no chat titles, user name or paths can appear.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "screens"
ERRORS: list[str] = []


def tab(page: Page, label: str) -> None:
    page.locator(".tb-tabs .tb-tab", has_text=label).first.click()
    page.wait_for_timeout(600)


def pick_robot(page: Page, name: str) -> None:
    page.locator(".tb-picker select").select_option(name)
    page.wait_for_timeout(800)


def settle(page: Page, ms: int = 2500) -> None:
    """Wait until no 3D view is still recording (polls the DOM; the webapp's CSP forbids string evaluation)."""
    for _ in range(360):
        if page.locator(".tb-root .tb-viewer-wait").count() == 0:
            break
        page.wait_for_timeout(500)
    page.wait_for_timeout(ms)


def shot(page: Page, prefix: str, name: str, full: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{prefix}-{name}.png"
    clip = None
    if prefix.startswith("desktop") and not full:
        # Leave out the Desktop session list: it shows the user's own chat titles and user name.
        size = page.viewport_size or {"width": 1440, "height": 960}
        clip = {"x": 261, "y": 0, "width": size["width"] - 261, "height": size["height"]}
    page.screenshot(path=str(path), full_page=full, clip=clip)
    print("saved", path.relative_to(ROOT))


def scrub(page: Page, seconds: float) -> None:
    """Pause the last timeline and move it to ``seconds`` (a range input driven by React's input events)."""
    button = page.locator(".tb-timeline .tb-icon-btn").last
    if button.get_attribute("aria-label") == "Pause":
        button.click()
    page.locator(".tb-timeline input[type=range]").last.evaluate(
        """(el, v) => { const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set;
                        set.call(el, String(v)); el.dispatchEvent(new Event('input', { bubbles: true })) }""",
        seconds)
    page.wait_for_timeout(700)


def tip_seconds(page: Page) -> float | None:
    import re
    for text in page.locator(".tb-viewer-label small").all_inner_texts():
        m = re.search(r"tip(?:s|ped) at ([0-9.]+) s", text)
        if m:
            return float(m.group(1))
    return None


def run(page: Page, prefix: str) -> None:
    root = page.locator(".tb-root")
    root.wait_for(timeout=60_000)
    page.wait_for_selector(".tb-robot-card img", timeout=60_000)
    page.wait_for_timeout(1500)
    shot(page, prefix, "gallery")

    page.locator(".tb-robot-card", has_text="Caduceus").first.click()
    page.wait_for_selector(".tb-photo img", timeout=60_000)
    settle(page)
    shot(page, prefix, "robot-caduceus")

    tab(page, "Report card")
    pick_robot(page, "spider8")
    page.wait_for_selector(".tb-tile", timeout=60_000)
    page.wait_for_timeout(800)
    shot(page, prefix, "report-spider8")
    page.locator(".tb-tile", has_text="Ramp 10 deg").click()
    page.wait_for_selector(".tb-timeline", timeout=180_000)
    settle(page, 3500)
    scrub(page, 3.0)
    page.locator(".tb-timeline").last.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    shot(page, prefix, "report-spider8-replay")

    tab(page, "Compare")
    page.wait_for_selector(".tb-check", timeout=60_000)
    for box in page.locator(".tb-check").all():
        want = "high step" in box.inner_text()
        cb = box.locator("input")
        if cb.is_checked() != want:
            cb.click()
    page.get_by_role("button", name="Compare 1 variant").click()
    page.wait_for_selector(".tb-table-compare", timeout=600_000)
    page.wait_for_timeout(500)
    page.locator(".tb-table-compare tr", has_text="Bar 2 cm").click()
    page.wait_for_selector(".tb-grid-views canvas", timeout=180_000)
    settle(page, 4000)
    scrub(page, 4.0)
    page.locator(".tb-table-compare tr", has_text="Ramp 15 deg").scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    shot(page, prefix, "compare-spider8-high-step")

    tab(page, "Move check")
    pick_robot(page, "caduceus")
    for move, name in (("arms_up_both", "check-arms_up_both-blocked"), ("arms_up_alternating", "check-arms_up_alternating-pass")):
        page.locator(".tb-field select").first.select_option(move)
        page.get_by_role("button", name="Run preflight").click()
        page.wait_for_selector(".tb-verdict", timeout=300_000)
        settle(page, 3000)
        t = tip_seconds(page)
        if t is not None:
            scrub(page, t + 0.25)                 # the red tip flash and the TIPPED tag
        page.locator(".tb-verdict").scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        shot(page, prefix, name)


def skip_onboarding(page: Page) -> None:
    """A fresh Hermes home opens the Desktop workspace with "connect a model provider": choose "later"."""
    try:
        page.get_by_text("choose a provider later").first.click(timeout=6000)
        page.wait_for_timeout(1500)
    except Exception:
        pass


def close_notice(page: Page) -> None:
    """A fresh dashboard shows a one-time "Help improve Hermes?" bar above every page: decline it."""
    try:
        page.get_by_role("button", name="No thanks").click(timeout=3000)
        page.wait_for_timeout(600)
    except Exception:
        pass


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "dashboard"
    with sync_playwright() as pw:
        if target == "webapp":
            # Hermes Desktop's workspace served by the gateway (`hermes webapp`): the same renderer and the same
            # desktop/plugin.js as the Electron app. argv[2] is a one-use link from `hermes webapp --no-open`.
            browser = pw.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
            dark = len(sys.argv) > 3 and sys.argv[3] == "dark"
            page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1,
                                    color_scheme="dark" if dark else "light")
            page.on("console", lambda m: ERRORS.append(m.text) if m.type == "error" and "talaria" in m.text.lower() else None)
            page.on("pageerror", lambda e: ERRORS.append(str(e)))
            # The workspace keeps its colour mode in this browser's storage (default "system"); pin it.
            mode = "dark" if dark else "light"
            page.add_init_script(f"""try {{ localStorage.setItem('hermes-desktop-mode-v1', '{mode}');
                localStorage.setItem('hermes-desktop-profile-modes-v1', JSON.stringify({{ default: '{mode}' }})) }} catch (e) {{}}""")
            page.goto(sys.argv[2])
            page.wait_for_url("**/#/**", timeout=60_000)
            base = page.url.split("#")[0]
            skip_onboarding(page)
            page.goto(base + "#/capabilities?tab=plugins")
            skip_onboarding(page)
            page.get_by_placeholder("Search plugins").fill("Talaria Bench")
            page.wait_for_timeout(1500)
            switch = page.get_by_role("switch", name="Talaria Bench")
            if switch.get_attribute("aria-checked") != "true":
                switch.click()
            page.wait_for_timeout(2500)
            page.goto(base + "#/talaria")
            run(page, "desktop-dark" if dark else "desktop")
            browser.close()
        elif target == "desktop":
            browser = pw.chromium.connect_over_cdp(sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:9222")
            page = next(p for c in browser.contexts for p in c.pages if not p.url.startswith("devtools"))
            page.on("console", lambda m: ERRORS.append(m.text) if m.type == "error" else None)
            page.wait_for_selector(".tb-root", timeout=60_000)
            run(page, "desktop")
        else:
            browser = pw.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
            page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
            page.on("console", lambda m: ERRORS.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: ERRORS.append(str(e)))
            url = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:9119"
            page.goto(url.rstrip("/") + "/talaria", wait_until="networkidle")
            close_notice(page)
            run(page, "dashboard")
            browser.close()
    print("console errors:", len(ERRORS))
    for e in ERRORS[:20]:
        print("  ", e[:300])
    return 1 if ERRORS else 0


if __name__ == "__main__":
    t0 = time.time()
    code = main()
    print(f"done in {time.time() - t0:.0f} s")
    raise SystemExit(code)
