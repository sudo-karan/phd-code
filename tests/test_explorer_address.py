"""The explorer's address after a switch of run, in a browser (round 16's question 6, answered (b);
round 17, Task 5; register site-address-written-again-after-a-switch-of-run).

After each kind of switch ("open it", "Open the re-run", a picker), the address holds the view on
screen: it is the link "Copy link to this view" copies, and opened in a new page it shows the same
run, step and layers. A link opened from outside still opens what it names.

Needs Playwright with Chromium, so it is skipped where Playwright is not installed (the repo's
.venv, GitHub's CI). It builds the site with scripts/build_ui_site.py and serves it itself, or uses
a site already served at EXPLORER_URL.
"""

from __future__ import annotations

import functools
import http.server
import os
import sys
import threading
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent

# A switch of run: the view opened first, what is clicked, and the run it opens.
SWITCHES = {
    "open it": ("odisha_v120_3ha_squares_koraput_keptland_s1desc/field",
                "#story button[data-open-run]", "odisha_v120_3ha_squares_koraput_keptland_s1desc_r14"),
    "Open the re-run": ("odisha_v120_3ha_squares_dhenkanal_keptland/field",
                        "#story button[data-open-run]",
                        "odisha_v120_3ha_squares_dhenkanal_keptland_s1desc"),
    "a picker": ("odisha_v120_3ha_squares_angul_keptland_s1desc_r14/stands",
                 "#pick-arm button[data-arm='alphaearth']",
                 "odisha_alphaearth_3ha_squares_angul_keptland_r14"),
}


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


@pytest.fixture(scope="module")
def site_url(tmp_path_factory):
    url = os.environ.get("EXPLORER_URL")
    if url:
        yield url.rstrip("/") + "/"
        return
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_ui_site

    out = tmp_path_factory.mktemp("site")
    assert build_ui_site.main(["--out", str(out)]) == 0
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(out)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _open(page, url: str) -> None:
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(1500)


def _layers_on(page) -> list[str]:
    """The layers switched on, by the toggles' keys (`<run>|<step>|<layer>`)."""
    return sorted(set(page.eval_on_selector_all(
        "input[type='checkbox'][data-key]", "els => els.filter(e => e.checked).map(e => e.dataset.key)")))


def _copied(page) -> str:
    """What "Copy link to this view" copies: from the clipboard, or from the prompt the page shows
    when the clipboard is refused."""
    prompted: list[str] = []
    page.once("dialog", lambda d: (prompted.append(d.default_value), d.dismiss()))
    page.click("#copylink")
    page.wait_for_timeout(300)
    return prompted[0] if prompted else page.evaluate("navigator.clipboard.readText()")


@pytest.mark.parametrize("kind", list(SWITCHES))
def test_after_a_switch_of_run_the_address_opens_what_is_on_screen(browser, site_url, kind):
    first, click, after = SWITCHES[kind]
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    errors: list[str] = []
    page = context.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open(page, site_url + "#" + first)
    step = first.split("/")[1]
    page.locator(click).first.click()
    page.wait_for_function(f"location.hash.startsWith('#{after}/{step}')")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    address, on = page.evaluate("location.hash"), _layers_on(page)
    assert on and all(key.startswith(f"{after}|") for key in on)
    # The address is the view: no layer of the step is said to be off, and it is the link copied.
    assert "off=" not in address
    copied = _copied(page)
    assert copied == site_url + address
    # Opened in a new page, the link shows the same run, step and layers.
    again = context.new_page()
    again.on("pageerror", lambda e: errors.append(str(e)))
    _open(again, copied)
    assert again.evaluate("location.hash") == address
    assert _layers_on(again) == on
    assert errors == []
    context.close()


def test_a_link_still_opens_what_it_names(browser, site_url):
    """At start-up the address is written once the link is restored: a link with a map view and a
    layer switched off opens as named, and its address is kept."""
    link = "#sanjay_van_baseline_keptland_r14/types?at=28.53000,77.17503,15&off=stand_types"
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    _open(page, site_url + link)
    assert page.evaluate("location.hash") == link
    assert not any(key.endswith("|stand_types") for key in _layers_on(page))
    context.close()
