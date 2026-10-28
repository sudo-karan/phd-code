"""Screenshots of the explorer, step by step, for checking a site build by eye (round 15).

    python scripts/build_ui_site.py
    python -m http.server -d _site 8765 &
    python3.11 scripts/screenshot_explorer.py [--base http://localhost:8765/] \\
        [--out outputs/round15/screenshots] [--run <run_id> ...]

Needs Playwright with Chromium (`pip install playwright`; the Mac has it under Python 3.11). For
each run named (by default the six of the round 15 brief: Sanjay Van, both arms; Angul at 3 ha
and Koraput at 10 ha, both arms, all R3), it opens every step of the walkthrough by its link
(`#<run>/<step>`) and saves `<run>__<nn>_<step>.png` and the step's text as
`<run>__<nn>_<step>.txt`; then the two panels the banner opens, "What changed" and "Earlier
versions", and one earlier version as its banner shows it. Console errors and failed requests are
listed in `console.txt`; the script exits 1 if there are any. It reads the site only; nothing is
written outside --out, which should be a git-ignored folder (outputs/ is).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SIX = ("sanjay_van_baseline_keptland_r14", "sanjay_van_alphaearth_keptland_r14",
       "odisha_v120_3ha_squares_angul_keptland_s1desc_r14",
       "odisha_alphaearth_3ha_squares_angul_keptland_r14",
       "odisha_v120_10ha_squares_koraput_keptland_s1desc_r14",
       "odisha_alphaearth_10ha_squares_koraput_keptland_r14")
STEPS = ("area", "land", "measure", "superpixels", "stands", "types", "profiles", "field")
EARLIER = "odisha_v120_3ha_squares_angul_keptland_s1desc"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", default="http://localhost:8765/")
    ap.add_argument("--out", type=Path, default=Path("outputs/round15/screenshots"))
    ap.add_argument("--run", nargs="+", default=list(SIX))
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=1000)
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    args.out.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        page.on("console", lambda m: problems.append(f"{page.url}: console {m.type}: {m.text}")
                if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(f"{page.url}: page error: {e}"))
        page.on("requestfailed", lambda r: problems.append(f"{page.url}: failed request {r.url}")
                if "tile.openstreetmap" not in r.url else None)

        def open_view(fragment: str) -> None:
            page.goto("about:blank")
            page.goto(args.base + "#" + fragment, wait_until="networkidle")
            page.wait_for_timeout(2500)

        for run in args.run:
            open_view(f"{run}/area")
            walk = page.eval_on_selector_all("#stepper button[data-go]",
                                             "bs => bs.map(b => b.textContent)")
            for i, step in enumerate(STEPS[:len(walk)], 1):
                open_view(f"{run}/{step}")
                if page.evaluate("location.hash.split('?')[0]") != f"#{run}/{step}":
                    problems.append(f"{run}/{step}: the page opened "
                                    f"{page.evaluate('location.hash')}")
                stem = args.out / f"{run}__{i:02d}_{step}"
                page.screenshot(path=f"{stem}.png")
                stem.with_suffix(".txt").write_text(
                    page.inner_text("#banner") + "\n\n" + page.inner_text("#story") + "\n")
        for which in ("changed", "earlier"):
            open_view(f"{args.run[0]}/area")
            page.click(f"#banner button[data-versions='{which}']")
            page.wait_for_timeout(800)
            name = "what_changed" if which == "changed" else "earlier_versions"
            page.screenshot(path=str(args.out / f"panel__{name}.png"))
            (args.out / f"panel__{name}.txt").write_text(page.inner_text("#versions") + "\n")
        open_view(f"{EARLIER}/stands")
        page.screenshot(path=str(args.out / f"earlier__{EARLIER}__stands.png"))
        (args.out / f"earlier__{EARLIER}__stands.txt").write_text(
            page.inner_text("#banner") + "\n\n" + page.inner_text("#story") + "\n")
        browser.close()
    (args.out / "console.txt").write_text("\n".join(problems) + ("\n" if problems else ""))
    print(f"{len(list(args.out.glob('*.png')))} screenshots in {args.out}; "
          f"{len(problems)} console error(s) or failed request(s)")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
