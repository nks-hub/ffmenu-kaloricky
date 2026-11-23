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
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from ffkt.app import Service
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
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        extension = str(ROOT / "extension")
        self.context = self.playwright.chromium.launch_persistent_context(
            tempfile.mkdtemp(), channel="chromium",
            args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"])
        self.addCleanup(self.context.close)

        def serve(route):
            url = route.request.url
            if url.startswith("https://www.ffmenu.cz/jidelnicek"):
                return route.fulfill(body=self.menu, content_type="text/html; charset=utf-8")
            if url.startswith(("https://www.dine4fit.com/", "chrome-extension://")):
                return route.continue_()
            return route.abort()
        self.context.route("**/*", serve)
        worker = self.context.service_workers[0] if self.context.service_workers \
            else self.context.wait_for_event("serviceworker")
        self.options_url = f"chrome-extension://{worker.url.split('/')[2]}/options.html"

    def test_qr_opens_a_new_kt_food_with_the_menu_values(self):
        import io
        import zxingcpp
        from PIL import Image
        meal = parse_menu(self.menu, PROGRAM)[0]
        options = self.context.new_page()
        options.goto(self.options_url)
        options.fill("#email", EMAIL)
        options.fill("#password", PASSWORD)
        options.click("#save")
        options.wait_for_selector("#status:not(:empty)", timeout=120_000)
        self.assertIn("Přihlášení funguje", options.inner_text("#status"))

        page = self.context.new_page()
        page.goto(f"https://www.ffmenu.cz/jidelnicek?product_variant_id={PROGRAM}&weeks=0")
        page.wait_for_selector(".ffkt-qr:is([data-state='done'], [data-state='error'])", timeout=120_000)
        box = page.locator(".ffkt-qr").first
        self.assertEqual(box.get_attribute("data-state"), "done", box.inner_text())
        url = zxingcpp.read_barcodes(Image.open(io.BytesIO(box.locator("svg").screenshot())))[0].text

        self.assertRegex(url, r"^https://dine4fit\.com/food/[0-9a-f]{32}$")
        food = Diary(self.client)._api(f"v1/foodstuff/{url.rsplit('/', 1)[1]}")
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
