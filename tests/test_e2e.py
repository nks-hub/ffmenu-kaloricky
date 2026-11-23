"""Browser runs of the phone page and the extension; need Playwright, Chromium and internet (OCR loads from CDN).

Run with: FFKT_E2E=1 python -m unittest discover -s tests -p test_e2e.py
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from test_app import FIXTURES, AppTest

ROOT = Path(__file__).resolve().parent.parent
ENABLED = os.environ.get("FFKT_E2E") == "1" and importlib.util.find_spec("playwright") is not None
TIMEOUT = 180_000


@unittest.skipUnless(ENABLED, "set FFKT_E2E=1 and install playwright")
class BrowserTest(AppTest):
    token = "e2e-token"

    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()

    @classmethod
    def tearDownClass(cls):
        cls.playwright.stop()

    @property
    def base(self):
        return f"http://127.0.0.1:{self.server.server_port}"


class PhonePageTest(BrowserTest):
    def scan(self, photo):
        browser = self.playwright.chromium.launch()
        self.addCleanup(browser.close)
        page = browser.new_page()
        page.goto(f"{self.base}/#t={self.token}")
        page.fill("#day", "2026-11-23")
        page.wait_for_selector("#menu .meal")
        page.set_input_files("#scan-input", str(FIXTURES / "photos" / photo))
        page.wait_for_function(
            "['Našel', 'nepodařilo'].some(t => document.querySelector('#scan-status').textContent.includes(t))",
            timeout=TIMEOUT)
        return page

    def test_porridge_photo_is_recognised_and_written(self):
        page = self.scan("kase.jpg")

        self.assertIn("Našel", page.inner_text("#scan-status"))
        first = page.locator("#candidates .meal").first
        self.assertEqual(first.locator(".name").inner_text(), "Ovesná kaše s proteinem a borůvkami")
        first.locator("button").click()
        page.wait_for_selector("#candidates .meal button:has-text('Zapsáno')")
        self.assertEqual(self.kt.intakes[0]["Polozky"][0]["Nazev"], "FF Menu: Ovesná kaše s proteinem a borůvkami")
        self.assertEqual(self.kt.intakes[0]["ID_Cas"], 2)

    def test_spread_photo_is_recognised(self):
        page = self.scan("pomazanka.jpg")

        self.assertEqual(page.locator("#candidates .meal .name").first.inner_text(),
                         "Vajíčková pomazánka s žitným chlebem")

    def test_pairing_qr_carries_lan_address_and_token(self):
        browser = self.playwright.chromium.launch()
        self.addCleanup(browser.close)
        page = browser.new_page()
        page.goto(f"{self.base}/#t={self.token}")
        page.click("#pair summary")
        page.wait_for_selector("#qr svg", timeout=30_000)

        self.assertRegex(page.inner_text("#qr-url"), rf"^http://[\d.]+:{self.server.server_port}/#t={self.token}$")


class ExtensionTest(BrowserTest):
    def setUp(self):
        super().setUp()
        extension = str(ROOT / "extension")
        self.context = self.playwright.chromium.launch_persistent_context(
            tempfile.mkdtemp(), channel="chromium",
            args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"])
        self.addCleanup(self.context.close)
        worker = self.context.service_workers[0] if self.context.service_workers \
            else self.context.wait_for_event("serviceworker")
        extension_id = worker.url.split("/")[2]

        page = self.context.new_page()
        page.goto(f"chrome-extension://{extension_id}/options.html")
        page.fill("#url", f"{self.base}/#t={self.token}")
        page.click("#save")
        # extension pages forbid eval, so wait_for_function with a string cannot run there
        page.wait_for_selector("#status:has-text('Spojení funguje')")

        menu = (FIXTURES / "racio-6000.html").read_text(encoding="utf-8")
        self.context.route("https://www.ffmenu.cz/**", lambda route: route.fulfill(
            body=menu, content_type="text/html; charset=utf-8") if "/jidelnicek" in route.request.url
            else route.abort())
        self.page = page
        page.goto("https://www.ffmenu.cz/jidelnicek?product_variant_id=1&weeks=0")
        page.wait_for_selector(".ffkt-btn")

    def test_meal_button_writes_that_meal(self):
        button = self.page.locator('.ffkt-btn[data-key="1:2026-11-23:1"]')
        button.click()
        self.page.wait_for_selector('.ffkt-btn[data-key="1:2026-11-23:1"][data-state="done"]')

        self.assertEqual(len(self.kt.intakes), 1)
        self.assertEqual((self.kt.intakes[0]["Datum"], self.kt.intakes[0]["ID_Cas"]), ("2026-11-23", 2))

    def test_day_button_writes_remaining_meals_and_marks_them(self):
        self.page.locator('.ffkt-btn[data-key="1:2026-11-23:0"]').click()
        self.page.wait_for_selector('.ffkt-btn[data-key="1:2026-11-23:0"][data-state="done"]')

        self.page.locator('.ffkt-day[data-day="2026-11-23"]').click()
        self.page.wait_for_selector('.ffkt-btn[data-key="1:2026-11-23:4"][data-state="done"]')

        self.assertEqual([e["ID_Cas"] for e in self.kt.intakes], [1, 2, 3, 4, 5])
        self.assertEqual(self.page.locator('.ffkt-btn[data-key^="1:2026-11-23:"][data-state="done"]').count(), 5)

    def test_buttons_show_meals_added_earlier(self):
        self.service.add(self.service.find("1:2026-11-24:2"), self.service.find("1:2026-11-24:2").day)

        self.page.reload()

        self.page.wait_for_selector('.ffkt-btn[data-key="1:2026-11-24:2"][data-state="done"]')
        self.assertEqual(self.page.locator('.ffkt-btn[data-state="done"]').count(), 1)


if __name__ == "__main__":
    unittest.main()
