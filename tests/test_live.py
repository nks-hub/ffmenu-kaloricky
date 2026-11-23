"""End-to-end runs against the real Kalorické tabulky and ffmenu.cz with a throwaway test account.

Each test writes meals into the account's diary, reads them back through the API the KT app uses for
its diary screen, and deletes them again. Never point this at an account whose diary you care about.

Run with:
  FFKT_LIVE=1 FFKT_KT_EMAIL=... FFKT_KT_PASSWORD=... python -m unittest discover -s tests -p test_live.py
"""
import hashlib
import importlib.util
import json
import os
import re
import ssl
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from ffkt.app import Service, make_server
from ffkt.ffmenu import fetch_page, parse_menu
from ffkt.kt import APP_PARAMS, KJ_PER_KCAL, RETRY_DELAYS, KTClient

ROOT = Path(__file__).resolve().parent.parent
EMAIL = os.environ.get("FFKT_KT_EMAIL")
PASSWORD = os.environ.get("FFKT_KT_PASSWORD")
ENABLED = os.environ.get("FFKT_LIVE") == "1" and EMAIL and PASSWORD
SKIP = "set FFKT_LIVE=1, FFKT_KT_EMAIL and FFKT_KT_PASSWORD of a test account"
PROGRAM = 1


class Diary:
    """Reads and deletes diary entries through the JSON API (www.dine4fit.com/api) of the KT app."""

    def __init__(self, client):
        self.client = client

    def _api(self, path, body=None):
        if self.client.hash is None:
            self.client.login()
        request = urllib.request.Request(
            f"https://www.dine4fit.com/api/{path}",
            data=None if body is None else json.dumps(body).encode(),
            headers={"hash": self.client.hash, "version": APP_PARAMS["v"], "pid": APP_PARAMS["pid"],
                     "lang": "cs", "Content-Type": "application/json", "User-Agent": "okhttp/4.12.0"})
        for delay in (*RETRY_DELAYS, None):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.loads(response.read() or b"null")
            except urllib.error.HTTPError as error:
                if error.code != 503 or delay is None:
                    raise
                time.sleep(delay)

    def ff_entries(self, day):
        """FF Menu entries of a day as (diary time id, item) pairs."""
        summary = self._api(f"v1/summary?date={day.isoformat()}")["summary"]
        return [(slot["id"], item) for slot in summary["intake"]["diary_times"]
                for item in slot["items"] if item["title"].startswith("FF Menu: ")]

    def ff_foods(self, meal):
        """FF Menu foods KT already has with the meal's values, by the KT app's duplicate check."""
        values = {"energy": f"{meal.kj:g}", "energy_unit": "kj", "protein": f"{meal.protein:g}",
                  "carbohydrate": f"{meal.carbs:g}", "fat": f"{meal.fat:g}", "fiber": f"{meal.fiber:g}"}
        items = self._api("v1/food-suggestion/search/duplicates", values)["items"]
        return [item["id"] for item in items if item["title"].startswith(f"FF Menu: {meal.name}")]

    def delete(self, entries):
        if entries:
            self._api("v1/diary/delete", {"diary_foodstuff_ids": [item["id"] for _, item in entries]})


def first_menu_day():
    meals = parse_menu(fetch_page(PROGRAM, 0), PROGRAM)
    day = min(m.day for m in meals)
    return day, [m for m in meals if m.day == day]


@unittest.skipUnless(ENABLED, SKIP)
class LiveTest(unittest.TestCase):
    def setUp(self):
        self.client = KTClient(EMAIL, hashlib.md5(PASSWORD.encode()).hexdigest())
        self.diary = Diary(self.client)
        self.day, self.meals = first_menu_day()
        self.diary.delete(self.diary.ff_entries(self.day))
        self.addCleanup(lambda: self.diary.delete(self.diary.ff_entries(self.day)))

    def assert_written(self, meal, entries):
        found = [(slot, item) for slot, item in entries if item["title"] == f"FF Menu: {meal.name}"]
        self.assertEqual(len(found), 1, [item["title"] for _, item in entries])
        slot, item = found[0]
        self.assertEqual(str(slot), str(meal.day_time))
        energy = item["energy"]
        expected = meal.kj if energy["unit_localized"].lower() == "kj" else meal.kj / KJ_PER_KCAL
        self.assertAlmostEqual(energy["value"], expected, delta=1)


class LiveServiceTest(LiveTest):
    def test_service_writes_a_meal_that_appears_in_the_diary(self):
        service = Service(self.client, program=PROGRAM, store_path=Path(tempfile.mkdtemp()) / "added.json",
                          today=date.today)
        meal = self.meals[1]

        service.add(meal, self.day)

        self.assert_written(meal, self.diary.ff_entries(self.day))


def one_meal_menu():
    """Live menu page cut down to its first day's second meal, so a run creates a single public KT food."""
    head, first_day, *_ = fetch_page(PROGRAM, 0).split("<div class='section-h3'>")
    prefix, _, second, *_ = first_day.split("<div class='col-sm-6 col-lg-4 mb-5'>")
    return f"{head}<div class='section-h3'>{prefix}<div class='col-sm-6 col-lg-4 mb-5'>{second}</div></div></body></html>"


@unittest.skipUnless(ENABLED and importlib.util.find_spec("playwright") and importlib.util.find_spec("zxingcpp"),
                     SKIP + " and install playwright, zxing-cpp and pillow")
class LiveExtensionTest(unittest.TestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright
        self.client = KTClient(EMAIL, hashlib.md5(PASSWORD.encode()).hexdigest())
        self.menu = one_meal_menu()
        # the ffkt server of the extension, run here on the test account with an empty food cache
        service = Service(self.client, program=PROGRAM, store_path=Path(tempfile.mkdtemp()) / "added.json",
                          fetch=lambda variant, weeks: self.menu, today=date.today)
        server = make_server(service, "127.0.0.1", 0, token="live")
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(ROOT / "tests" / "fixtures" / "tls" / "cert.pem",
                            ROOT / "tests" / "fixtures" / "tls" / "key.pem")
        server.socket = tls.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        extension = str(ROOT / "extension")
        self.context = self.playwright.chromium.launch_persistent_context(
            tempfile.mkdtemp(), channel="chromium", ignore_https_errors=True,
            args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}",
                  f"--host-resolver-rules=MAP ffkt.nks-hub.cz 127.0.0.1:{server.server_port}",
                  "--ignore-certificate-errors"])
        self.addCleanup(self.context.close)

        def serve(route):
            url = route.request.url
            if url.startswith("https://www.ffmenu.cz/jidelnicek"):
                return route.fulfill(body=self.menu, content_type="text/html; charset=utf-8")
            if url.startswith(("https://ffkt.nks-hub.cz/", "chrome-extension://")):
                return route.continue_()
            return route.abort()
        self.context.route("**/*", serve)
        if not self.context.service_workers:
            self.context.wait_for_event("serviceworker")

    def test_qr_opens_a_new_kt_food_with_the_menu_values(self):
        import io
        import zxingcpp
        from PIL import Image
        meal = parse_menu(self.menu, PROGRAM)[0]
        known = Diary(self.client).ff_foods(meal)

        page = self.context.new_page()
        page.goto(f"https://www.ffmenu.cz/jidelnicek?product_variant_id={PROGRAM}&weeks=0")
        box = page.locator(".ffkt-qr").first
        box.locator("button").click()
        page.wait_for_selector(".ffkt-qr:is([data-state='done'], [data-state='error'])", timeout=120_000)
        self.assertEqual(box.get_attribute("data-state"), "done", box.inner_text())
        url = zxingcpp.read_barcodes(Image.open(io.BytesIO(box.locator("svg").screenshot())))[0].text

        self.assertRegex(url, r"^https://dine4fit\.com/food/[0-9a-f]{32}$")
        guid = url.rsplit("/", 1)[1]
        # a dish KT already has is reused, so KT ends up with no new food for it
        if known:
            self.assertIn(guid, known)
        self.assertEqual(len(Diary(self.client).ff_foods(meal)), max(len(known), 1))
        food = Diary(self.client)._api(f"v1/foodstuff/{guid}")
        # a title KT already has (an earlier run) gets a short suffix
        self.assertRegex(food["title"], rf"^FF Menu: {re.escape(meal.name)} \({meal.kj:.0f} kJ\)( · [0-9a-f]{{4}})?$")
        self.assertIn({"title": "100 g", "multiplier": 100.0},
                      [{k: u[k] for k in ("title", "multiplier")} for u in food["units"]])
        # KT stores values per gram; the 100 g unit stands for one FF Menu portion
        values = food["values"]
        kj = next(v["value"] for v in values["energy"]["values"] if v["unit"] == "kJ")
        for got, expected in ((kj, meal.kj), (values["protein"]["value"], meal.protein),
                              (values["carbohydrates"]["value"], meal.carbs), (values["fat"]["value"], meal.fat),
                              (values["fiber"]["value"], meal.fiber)):
            self.assertAlmostEqual(got * 100, expected, places=1)


if __name__ == "__main__":
    unittest.main()
