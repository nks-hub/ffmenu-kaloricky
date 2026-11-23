import hashlib
import unittest
from datetime import date

from fake_kt import FakeKT
from ffkt.kt import KTClient, KTError


def md5(text):
    return hashlib.md5(text.encode()).hexdigest()


PORRIDGE = dict(day=date(2026, 11, 23), time="10:00", day_time=2,
                name="FF Menu: Ovesná kaše s proteinem a borůvkami",
                kj=1345, protein=20, carbs=33, fat=12, fiber=4.8, cholesterol=0)


class KTClientTest(unittest.TestCase):
    def setUp(self):
        self.kt = FakeKT()
        self.addCleanup(self.kt.close)
        self.client = KTClient("jan@example.com", md5("tajne heslo"), base_url=self.kt.url)

    def test_custom_intake_is_written_with_label_values(self):
        self.client.add_custom(**PORRIDGE)

        self.assertEqual(self.kt.intakes, [{
            "Datum": "2026-11-23", "Cas": "10:00", "ID_Cas": 2,
            "Polozky": [{
                "Typ": "vlozenaHodnota", "Nazev": "FF Menu: Ovesná kaše s proteinem a borůvkami",
                "Energie": 1345, "Bilkoviny": 20, "Sacharidy": 33, "Tuky": 12,
                "Vlaknina": 4.8, "Cholesterol": 0,
            }],
        }])

    def test_energy_is_converted_for_accounts_counting_kcal(self):
        self.kt.unit = "kcal"

        self.client.add_custom(**PORRIDGE)

        self.assertEqual(self.kt.intakes[0]["Polozky"][0]["Energie"], 321.2)

    def test_expired_session_logs_in_again_and_writes_once(self):
        self.client.add_custom(**PORRIDGE)
        self.kt.hashes.clear()

        self.client.add_custom(**PORRIDGE)

        self.assertEqual(self.kt.logins, 2)
        self.assertEqual(len(self.kt.intakes), 2)

    def test_unknown_email_reports_server_message(self):
        client = KTClient("nikdo@example.com", md5("x"), base_url=self.kt.url)

        with self.assertRaises(KTError) as error:
            client.login()

        self.assertEqual(error.exception.code, 406)
        self.assertIn("nikdo@example.com", str(error.exception))

    def test_rejected_intake_raises_instead_of_retrying(self):
        self.kt.reject_intake = (400, "Neplatná data")

        with self.assertRaises(KTError) as error:
            self.client.add_custom(**PORRIDGE)

        self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.kt.logins, 1)


if __name__ == "__main__":
    unittest.main()
