"""Browser runs of the extension and the phone page; need Playwright, Chromium and internet (OCR loads from CDN).

Run with: FFKT_E2E=1 python -m unittest discover -s tests -p test_e2e.py
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from fake_kt import FakeKT
from test_app import FIXTURES, AppTest

ROOT = Path(__file__).resolve().parent.parent
ENABLED = os.environ.get("FFKT_E2E") == "1" and importlib.util.find_spec("playwright") is not None
SKIP = "set FFKT_E2E=1 and install playwright"
OCR_TIMEOUT = 180_000
playwright = None


def setUpModule():
    global playwright
    if ENABLED:
        from playwright.sync_api import sync_playwright
        playwright = sync_playwright().start()


def tearDownModule():
    if playwright:
        playwright.stop()


@unittest.skipUnless(ENABLED, SKIP)
class ExtensionTest(unittest.TestCase):
    """The extension talks to https://www.dine4fit.com itself; Chromium resolves that host to FakeKT."""

    def setUp(self):
        self.kt = FakeKT(tls=True)
        self.addCleanup(self.kt.close)
        extension = str(ROOT / "extension")
        self.context = playwright.chromium.launch_persistent_context(
            tempfile.mkdtemp(), channel="chromium", ignore_https_errors=True,
            args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}",
                  f"--host-resolver-rules=MAP www.dine4fit.com 127.0.0.1:{self.kt.server.server_port}",
                  "--ignore-certificate-errors"])
        self.addCleanup(self.context.close)
        worker = self.context.service_workers[0] if self.context.service_workers \
            else self.context.wait_for_event("serviceworker")
        self.options_url = f"chrome-extension://{worker.url.split('/')[2]}/options.html"
        menu = (FIXTURES / "racio-6000.html").read_text(encoding="utf-8")
        self.context.route("https://www.ffmenu.cz/**", lambda route: route.fulfill(
            body=menu, content_type="text/html; charset=utf-8") if "/jidelnicek" in route.request.url
            else route.abort())

    def log_in(self, password="tajne heslo"):
        page = self.context.new_page()
        page.goto(self.options_url)
        page.fill("#email", self.kt.email)
        page.fill("#password", password)
        page.click("#save")
        # extension pages forbid eval, so wait_for_function with a string cannot run there
        page.wait_for_selector("#status:not(:empty)")
        return page.inner_text("#status")

    def open_menu(self):
        page = self.context.new_page()
        page.goto("https://www.ffmenu.cz/jidelnicek?product_variant_id=1&weeks=0")
        page.wait_for_selector(".ffkt-btn")
        return page

    def click_meal(self, page, key):
        button = page.locator(f'.ffkt-btn[data-key="{key}"]')
        button.click()
        page.wait_for_selector(f'.ffkt-btn[data-key="{key}"]:is([data-state="done"], [data-state="error"])')
        self.assertEqual(button.get_attribute("data-state"), "done", button.get_attribute("title"))

    def test_meal_button_writes_values_read_from_the_page(self):
        self.assertIn("Přihlášení funguje", self.log_in())
        page = self.open_menu()

        self.click_meal(page, "1:2026-11-23:1")

        self.assertEqual(self.kt.intakes, [{
            "Datum": "2026-11-23", "Cas": "10:00", "ID_Cas": 2,
            "Polozky": [{
                "Typ": "vlozenaHodnota", "Nazev": "FF Menu: Ovesná kaše s proteinem a borůvkami",
                "Energie": 1345, "Bilkoviny": 20, "Sacharidy": 33, "Tuky": 12,
                "Vlaknina": 4.8, "Cholesterol": 0,
            }],
        }])

    def test_energy_goes_in_kcal_for_kcal_accounts(self):
        self.kt.unit = "kcal"
        self.log_in()

        self.click_meal(self.open_menu(), "1:2026-11-23:1")

        self.assertEqual(self.kt.intakes[0]["Polozky"][0]["Energie"], 321.2)

    def test_day_button_writes_remaining_meals_and_marks_them(self):
        self.log_in()
        page = self.open_menu()
        self.click_meal(page, "1:2026-11-23:0")

        page.locator('.ffkt-day[data-day="2026-11-23"]').click()
        page.wait_for_selector('.ffkt-day[data-day="2026-11-23"][data-state="done"]')

        self.assertEqual([e["ID_Cas"] for e in self.kt.intakes], [1, 2, 3, 4, 5])
        self.assertEqual(page.locator('.ffkt-btn[data-key^="1:2026-11-23:"][data-state="done"]').count(), 5)

    def test_written_meals_stay_marked_after_reload_and_are_not_sent_twice(self):
        self.log_in()
        page = self.open_menu()
        self.click_meal(page, "1:2026-11-24:2")

        page.reload()
        page.wait_for_selector('.ffkt-btn[data-key="1:2026-11-24:2"][data-state="done"]')
        page.locator('.ffkt-day[data-day="2026-11-24"]').click()
        page.wait_for_selector('.ffkt-day[data-day="2026-11-24"][data-state="done"]')

        self.assertEqual(page.locator('.ffkt-btn[data-state="done"][data-key]').count(), 5)
        self.assertEqual(len(self.kt.intakes), 5)

    def test_expired_kt_session_logs_in_again(self):
        self.log_in()
        page = self.open_menu()
        self.click_meal(page, "1:2026-11-23:0")
        self.kt.hashes.clear()

        self.click_meal(page, "1:2026-11-23:1")

        self.assertEqual((self.kt.logins, len(self.kt.intakes)), (2, 2))

    def test_overloaded_kt_api_is_retried(self):
        self.log_in()
        page = self.open_menu()
        self.kt.unavailable = 2

        self.click_meal(page, "1:2026-11-23:1")

        self.assertEqual(len(self.kt.intakes), 1)

    def test_wrong_password_is_reported_in_options(self):
        status = self.log_in(password="spatne")

        self.assertIn("Špatné heslo", status)
        self.assertEqual(self.kt.logins, 0)

    def test_menu_page_asks_for_login_first(self):
        page = self.open_menu()

        page.wait_for_selector(".ffkt-banner")
        self.assertIn("přihlášení", page.inner_text(".ffkt-banner"))
        page.locator('.ffkt-btn[data-key="1:2026-11-23:1"]').click()
        page.wait_for_selector('.ffkt-btn[data-key="1:2026-11-23:1"][data-state="error"]')
        self.assertEqual(self.kt.intakes, [])


@unittest.skipUnless(ENABLED, SKIP)
class PhonePageTest(AppTest):
    token = "e2e-token"

    @property
    def base(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def open_page(self):
        browser = playwright.chromium.launch()
        self.addCleanup(browser.close)
        page = browser.new_page()
        page.goto(f"{self.base}/#t={self.token}")
        return page

    def scan(self, photo):
        page = self.open_page()
        page.fill("#day", "2026-11-23")
        page.wait_for_selector("#menu .meal")
        page.set_input_files("#scan-input", str(FIXTURES / "photos" / photo))
        page.wait_for_function(
            "['Našel', 'nepodařilo'].some(t => document.querySelector('#scan-status').textContent.includes(t))",
            timeout=OCR_TIMEOUT)
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
        page = self.open_page()
        page.click("#pair summary")
        page.wait_for_selector("#qr svg", timeout=30_000)

        self.assertRegex(page.inner_text("#qr-url"), rf"^http://[\d.]+:{self.server.server_port}/#t={self.token}$")


if __name__ == "__main__":
    unittest.main()
