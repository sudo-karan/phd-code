"""Screenshot the HTML report (scripts/report.py output) for use in slides.

Generates report_screenshot_top.png / _full.png at the repo root (both gitignored)
from reports/multi_sanjay_van_baseline/report.html, using the pre-installed
Chromium via Playwright. Run before scripts/build_honest.js.

  pip install playwright   # browser is pre-provisioned at PLAYWRIGHT_BROWSERS_PATH
  python scripts/report_screenshot.py
"""
import glob, os
from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
URL = "file://" + os.path.join(REPO, "reports/multi_sanjay_van_baseline/report.html")

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1300, "height": 1000}, device_scale_factor=2)
    pg.goto(URL, wait_until="networkidle")
    pg.screenshot(path=os.path.join(REPO, "report_screenshot_full.png"), full_page=True)
    pg.screenshot(path=os.path.join(REPO, "report_screenshot_top.png"),
                  clip={"x": 0, "y": 0, "width": 1300, "height": 1500})
    b.close()
print("wrote report_screenshot_top.png / _full.png")
