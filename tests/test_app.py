import hashlib
import json
import tempfile
import threading
import unittest
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


class TokenTest(AppTest):
    token = "s3cret"

    def test_api_requires_token_header(self):
        self.assertEqual(self.call("/api/menu?date=2026-11-23")[0], 403)
        self.assertEqual(self.call("/api/menu?date=2026-11-23", headers={"X-Token": "s3cret"})[0], 200)

    def test_page_itself_loads_without_token(self):
        self.assertEqual(self.call("/")[0], 200)


if __name__ == "__main__":
    unittest.main()
