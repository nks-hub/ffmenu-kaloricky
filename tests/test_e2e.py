"""Browser runs of the extension and the phone page; need Playwright, Chromium and internet (OCR loads from CDN).

Run with: FFKT_E2E=1 python -m unittest discover -s tests -p test_e2e.py
"""
import hashlib
import importlib.util
import os
import ssl
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path

from fake_kt import TLS, FakeKT
from ffkt.app import Service, make_server
from ffkt.kt import KTClient
from test_app import FIXTURES, AppTest, fixture_fetch

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
    """The extension asks https://ffkt.nks-hub.cz; Chromium resolves that host to a local ffkt server on FakeKT."""

    def setUp(self):
        self.kt = FakeKT()
        self.addCleanup(self.kt.close)
        client = KTClient(self.kt.email, hashlib.md5(b"tajne heslo").hexdigest(), base_url=self.kt.url)
        client.retry_delays = (0, 0)
        service = Service(client, program=1, store_path=Path(tempfile.mkdtemp()) / "added.json",
                          fetch=fixture_fetch, today=lambda: date(2026, 11, 23))
        self.server = make_server(service, "127.0.0.1", 0, token="e2e")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(TLS / "cert.pem", TLS / "key.pem")
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True, do_handshake_on_connect=False)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        extension = str(ROOT / "extension")
        self.context = playwright.chromium.launch_persistent_context(
            tempfile.mkdtemp(), channel="chromium", ignore_https_errors=True,
            args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}",
                  f"--host-resolver-rules=MAP ffkt.nks-hub.cz 127.0.0.1:{self.server.server_port}",
                  "--ignore-certificate-errors"])
        self.addCleanup(self.context.close)
        if not self.context.service_workers:
            self.context.wait_for_event("serviceworker")
        menu = (FIXTURES / "racio-6000.html").read_text(encoding="utf-8")

        # third-party scripts (the cookie bar among them) would cover the QR codes in screenshots
        def serve(route):
            url = route.request.url
            if url.startswith("https://www.ffmenu.cz/jidelnicek"):
                return route.fulfill(body=menu, content_type="text/html; charset=utf-8")
            if url.startswith(("https://ffkt.nks-hub.cz/", "chrome-extension://")):
                return route.continue_()
            return route.abort()
        self.context.route("**/*", serve)

    def open_menu(self):
        page = self.context.new_page()
        page.goto("https://www.ffmenu.cz/jidelnicek?product_variant_id=1&weeks=0")
        page.wait_for_selector(".ffkt-qr")
        return page

    def click_qr(self, page, key):
        box = page.locator(f'.ffkt-qr[data-key="{key}"]')
        box.locator("button").click()
        page.wait_for_selector(f'.ffkt-qr[data-key="{key}"]:is([data-state="done"], [data-state="error"])')
        return box

    def scan(self, box):
        """Decodes the QR code shown for a meal the way a phone camera would."""
        import io
        import zxingcpp
        from PIL import Image
        return zxingcpp.read_barcodes(Image.open(io.BytesIO(box.locator("svg").screenshot())))[0].text

    def test_qr_appears_after_click_and_opens_the_kt_food_of_the_meal(self):
        page = self.open_menu()
        self.assertEqual(page.locator(".ffkt-qr svg").count(), 0)
        self.assertEqual(self.kt.foods, {})

        box = self.click_qr(page, "1:2026-11-23:1")

        self.assertEqual(box.get_attribute("data-state"), "done", box.inner_text())
        url = self.scan(box)
        guid = url.rsplit("/", 1)[1]
        self.assertEqual(url, f"https://dine4fit.com/food/{guid}")
        self.assertEqual(self.kt.foods[guid]["title"], "FF Menu: Ovesná kaše s proteinem a borůvkami (1345 kJ)")
        self.assertIn("100 g = 1 porce", box.inner_text())
        self.assertEqual(page.locator(".ffkt-qr svg").count(), 1)

    def test_kcal_is_shown_next_to_kj(self):
        page = self.open_menu()

        energy = [" ".join(e.split()) for e in page.locator(".text-large").all_inner_texts()]

        self.assertIn("1 263 kJ (302 kcal)", energy)
        self.assertIn("1 345 kJ (321 kcal)", energy)

    def test_kt_failure_is_shown_and_retry_gets_the_qr(self):
        self.kt.unavailable = 3
        page = self.open_menu()

        box = self.click_qr(page, "1:2026-11-23:1")

        self.assertEqual(box.get_attribute("data-state"), "error")
        self.assertIn("Nepodařilo se", box.inner_text())
        box.locator("button", has_text="Zkusit znovu").click()
        page.wait_for_selector('.ffkt-qr[data-key="1:2026-11-23:1"][data-state="done"]')
        self.assertEqual(len(self.kt.foods), 1)

    def test_unreachable_server_is_reported(self):
        self.server.shutdown()
        self.server.server_close()
        page = self.open_menu()

        box = self.click_qr(page, "1:2026-11-23:1")

        self.assertEqual(box.get_attribute("data-state"), "error")
        self.assertIn("server doplňku není dostupný", box.inner_text())


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
