import hashlib
import json
import tempfile
import threading
import unittest
import unittest.mock
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from fake_kt import FakeKT
from ffkt.app import Service, make_server
from ffkt.kt import KTClient

FIXTURES = Path(__file__).parent / "fixtures"
PAGES = {1: "racio-6000", 5: "racio-7500", 2: "muscle"}


def fixture_fetch(variant, weeks):
    if weeks != 0 or variant not in PAGES:
        raise urllib.error.HTTPError("https://www.ffmenu.cz/jidelnicek", 404, "Not Found", {}, None)
    return (FIXTURES / f"{PAGES[variant]}.html").read_text(encoding="utf-8")


class AppTest(unittest.TestCase):
    token = None

    def setUp(self):
        self.kt = FakeKT()
        self.addCleanup(self.kt.close)
        store = Path(tempfile.mkdtemp()) / "added.json"
        client = KTClient(self.kt.email, hashlib.md5(b"tajne heslo").hexdigest(), base_url=self.kt.url)
        self.service = Service(client, program=1, store_path=store,
                               fetch=fixture_fetch, today=lambda: date(2026, 11, 23))
        self.server = make_server(self.service, "127.0.0.1", 0, token=self.token)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def call(self, path, body=None, headers=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.server_port}{path}",
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()

    def json(self, path, body=None, headers=None):
        status, text = self.call(path, body, headers)
        return status, json.loads(text)


class ServiceApiTest(AppTest):
    def test_menu_lists_the_program_meals_of_a_day(self):
        status, data = self.json("/api/menu?date=2026-11-23")

        self.assertEqual(status, 200)
        self.assertEqual([m["name"] for m in data["meals"]][:2], [
            "Vajíčková pomazánka s žitným chlebem", "Ovesná kaše s proteinem a borůvkami"])
        self.assertEqual(data["meals"][1]["key"], "1:2026-11-23:1")
        self.assertFalse(any(m["added"] for m in data["meals"]))

    def test_unpublished_week_gives_empty_menu(self):
        status, data = self.json("/api/menu?date=2026-11-30")

        self.assertEqual((status, data["meals"]), (200, []))

    def test_adding_a_meal_writes_it_to_the_diary_slot(self):
        status, data = self.json("/api/add", {"key": "1:2026-11-23:1", "date": "2026-11-24"})

        self.assertEqual(status, 200, data)
        entry = self.kt.intakes[0]
        self.assertEqual((entry["Datum"], entry["ID_Cas"]), ("2026-11-24", 2))
        self.assertEqual(entry["Polozky"][0]["Nazev"], "FF Menu: Ovesná kaše s proteinem a borůvkami")
        self.assertEqual(entry["Polozky"][0]["Energie"], 1345)
        menu = self.json("/api/menu?date=2026-11-23&diary=2026-11-24")[1]["meals"]
        self.assertEqual([m["added"] for m in menu], [False, True, False, False, False])

    def test_same_meal_twice_on_one_day_is_refused(self):
        self.json("/api/add", {"key": "1:2026-11-23:1", "date": "2026-11-23"})

        status, data = self.json("/api/add", {"key": "1:2026-11-23:1", "date": "2026-11-23"})

        self.assertEqual(status, 409)
        self.assertEqual(len(self.kt.intakes), 1)

    def test_whole_day_skips_meals_already_added(self):
        self.json("/api/add", {"key": "1:2026-11-23:0", "date": "2026-11-23"})

        status, data = self.json("/api/add-day", {"date": "2026-11-23"})

        self.assertEqual(status, 200)
        self.assertEqual((len(data["added"]), len(data["skipped"])), (4, 1))
        self.assertEqual([e["ID_Cas"] for e in self.kt.intakes], [1, 2, 3, 4, 5])

    def test_label_text_matches_meal_key(self):
        text = (FIXTURES / "ocr" / "kase-r270.txt").read_text(encoding="utf-8")

        status, data = self.json("/api/match", {"text": text})

        self.assertEqual(status, 200)
        self.assertTrue(data["confident"])
        self.assertEqual(data["candidates"][0]["key"], "1:2026-11-23:1")

    def test_kt_rejection_is_reported_and_not_remembered(self):
        self.kt.reject_intake = (400, "Neplatná data")

        status, data = self.json("/api/add", {"key": "1:2026-11-23:1", "date": "2026-11-23"})

        self.assertEqual(status, 502)
        self.assertIn("Neplatná data", data["error"])
        self.kt.reject_intake = None
        self.assertEqual(self.json("/api/add", {"key": "1:2026-11-23:1", "date": "2026-11-23"})[0], 200)

    def test_malformed_requests_get_400(self):
        for body in ({"key": "x", "date": "2026-11-23"}, {"key": "1:2026-11-23:1", "date": "zitra"}):
            with self.subTest(body):
                self.assertEqual(self.json("/api/add", body)[0], 400)
        self.assertEqual(self.call("/api/add", None)[0], 400)

    def test_unknown_meal_key_gets_404(self):
        self.assertEqual(self.json("/api/add", {"key": "1:2026-11-23:9", "date": "2026-11-23"})[0], 404)

    def test_page_is_served_at_root(self):
        status, text = self.call("/")

        self.assertEqual(status, 200)
        self.assertIn("<title>", text)

    def test_server_without_the_page_answers_root_with_404(self):
        # the Docker image ships only the API: the page writes into the diary of the server's shared account
        with unittest.mock.patch("ffkt.app.PAGE", Path(tempfile.gettempdir()) / "ffkt-missing-page.html"):
            self.assertEqual(self.call("/")[0], 404)


PORRIDGE_KEY = "1:2026-11-23:1"
PORRIDGE_VALUES = {"energy": "1345", "energy_unit": "kj", "protein": "20", "carbohydrate": "33", "fat": "12",
                   "fiber": "4.8"}


class FoodApiTest(AppTest):
    def food(self, key=PORRIDGE_KEY):
        status, data = self.json(f"/api/food?key={key}")
        self.assertEqual(status, 200, data)
        prefix = "https://dine4fit.com/food/"
        self.assertTrue(data["url"].startswith(prefix), data)
        return data["url"][len(prefix):]

    def test_meal_is_created_as_kt_food_with_menu_values(self):
        guid = self.food()

        self.assertEqual(self.kt.foods, {guid: {
            "title": "FF Menu: Ovesná kaše s proteinem a borůvkami (1345 kJ)", "foodstuff_type_id": 1026,
            "unit_name": "porce", "unit_multiplier": "100", "foodstuff_unit": "100g",
            **PORRIDGE_VALUES, "sugar": "0", "salt": "0", "cholesterol": "0",
        }})
        self.assertEqual(len(self.kt.food_images[guid]), 3)

    def test_second_request_reuses_the_food(self):
        first = self.food()

        self.assertEqual(self.food(), first)
        self.assertEqual(len(self.kt.foods), 1)

    def test_restarted_service_reuses_the_food_without_asking_kt(self):
        first = self.food()
        logins = self.kt.logins
        restarted = Service(self.service.kt.__class__(self.kt.email, "x", base_url=self.kt.url), program=1,
                            store_path=self.service.store_path, fetch=fixture_fetch,
                            today=lambda: date(2026, 11, 23))

        self.assertEqual(restarted.food(restarted.find(PORRIDGE_KEY)), first)
        self.assertEqual(self.kt.logins, logins)

    def food_with_existing(self, title):
        self.kt.foods["a" * 32] = {"title": title, **PORRIDGE_VALUES}
        return self.food()

    def test_food_kt_already_has_is_reused(self):
        self.assertEqual(self.food_with_existing("FF Menu: Ovesná kaše s proteinem a borůvkami (1345 kJ)"), "a" * 32)
        self.assertEqual(len(self.kt.foods), 1)

    def test_food_from_an_older_version_without_energy_in_title_is_reused(self):
        self.assertEqual(self.food_with_existing("FF Menu: Ovesná kaše s proteinem a borůvkami"), "a" * 32)

    def test_other_food_with_the_same_values_is_not_reused(self):
        self.assertNotEqual(self.food_with_existing("Ovesná kaše domácí"), "a" * 32)

    def test_title_kt_already_has_gets_a_suffix(self):
        self.kt.foods["0" * 32] = {"title": "FF Menu: Ovesná kaše s proteinem a borůvkami (1345 kJ)"}

        guid = self.food()

        self.assertRegex(self.kt.foods[guid]["title"],
                         r"^FF Menu: Ovesná kaše s proteinem a borůvkami \(1345 kJ\) · [0-9a-f]{4}$")

    def test_expired_kt_session_logs_in_again(self):
        self.food("1:2026-11-23:0")
        self.kt.hashes.clear()

        self.food()

        self.assertEqual((self.kt.logins, len(self.kt.foods)), (2, 2))

    def test_overloaded_kt_is_retried(self):
        self.service.kt.retry_delays = (0, 0)
        self.kt.unavailable = 2

        self.food()

        self.assertEqual(len(self.kt.foods), 1)

    def test_kt_failure_is_reported_and_not_remembered(self):
        self.service.kt.retry_delays = (0, 0)
        self.kt.unavailable = 3

        status, data = self.json(f"/api/food?key={PORRIDGE_KEY}")

        self.assertEqual(status, 502, data)
        self.assertEqual(self.kt.foods, {})
        self.food()
        self.assertEqual(len(self.kt.foods), 1)

    def test_meal_outside_the_menu_gets_404(self):
        for key in ("1:2026-11-23:9", "1:2026-11-30:0", "1:2027-01-04:0"):
            with self.subTest(key):
                self.assertEqual(self.json(f"/api/food?key={key}")[0], 404)
        self.assertEqual(self.kt.foods, {})

    def test_malformed_key_gets_400(self):
        for key in ("", "x", "1:2026-13-45:0", "4:2026-11-23:0"):
            with self.subTest(key):
                self.assertEqual(self.json(f"/api/food?key={key}")[0], 400)


class TokenTest(AppTest):
    token = "s3cret"

    def test_api_requires_token_header(self):
        self.assertEqual(self.call("/api/menu?date=2026-11-23")[0], 403)
        self.assertEqual(self.call("/api/menu?date=2026-11-23", headers={"X-Token": "s3cret"})[0], 200)

    def test_page_itself_loads_without_token(self):
        self.assertEqual(self.call("/")[0], 200)

    def test_food_for_the_browser_extension_needs_no_token(self):
        self.assertEqual(self.call(f"/api/food?key={PORRIDGE_KEY}")[0], 200)


if __name__ == "__main__":
    unittest.main()
