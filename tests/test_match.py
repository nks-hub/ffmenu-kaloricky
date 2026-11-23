import unittest
from datetime import date
from pathlib import Path

from ffkt.ffmenu import parse_menu
from ffkt.match import CONFIDENT, rank

FIXTURES = Path(__file__).parent / "fixtures"
MEALS = [meal
         for name, variant in (("racio-6000", 1), ("racio-7500", 5), ("muscle", 2))
         for meal in parse_menu((FIXTURES / f"{name}.html").read_text(encoding="utf-8"), variant)]


def ocr(name):
    return (FIXTURES / "ocr" / f"{name}.txt").read_text(encoding="utf-8")


class RankTest(unittest.TestCase):
    def test_upright_photo_of_porridge_label_finds_the_porridge(self):
        score, meal = rank(ocr("kase-r270"), MEALS, preferred=1)[0]

        self.assertEqual(meal.name, "Ovesná kaše s proteinem a borůvkami")
        self.assertEqual(meal.day, date(2026, 11, 23))
        self.assertGreaterEqual(score, CONFIDENT)

    def test_upright_photo_of_spread_label_finds_the_spread(self):
        score, meal = rank(ocr("pomazanka-r270"), MEALS, preferred=1)[0]

        self.assertEqual(meal.name, "Vajíčková pomazánka s žitným chlebem")
        self.assertGreaterEqual(score, CONFIDENT)

    def test_sideways_photos_stay_below_confidence(self):
        for name in ("kase-r0", "kase-r90", "pomazanka-r0", "pomazanka-r90"):
            with self.subTest(name):
                self.assertLess(rank(ocr(name), MEALS, preferred=1)[0][0], CONFIDENT)

    def test_identical_dishes_from_several_programs_are_listed_once(self):
        results = rank(ocr("kase-r270"), MEALS, preferred=1)
        porridges = [m for _, m in results if m.name.startswith("Ovesná kaše")]

        self.assertEqual(len(porridges), 1)
        self.assertEqual(porridges[0].variant, 1)

    def test_label_macros_pick_the_matching_program(self):
        text = "OBĚD KRŮTÍ PRSA, DUŠENÉ PIKANTNÍ ZELÍ A GRENAILLE Bílkoviny 32g Sacharidy 40g Tuky 18g"

        meal = rank(text, MEALS, preferred=1)[0][1]

        self.assertEqual((meal.variant, meal.kj), (5, 1890))

    def test_without_macros_the_preferred_program_wins(self):
        text = "KRŮTÍ PRSA, DUŠENÉ PIKANTNÍ ZELÍ A GRENAILLE"

        self.assertEqual(rank(text, MEALS, preferred=1)[0][1].variant, 1)
        self.assertEqual(rank(text, MEALS, preferred=5)[0][1].variant, 5)

    def test_label_date_selects_the_day_of_a_repeated_dish(self):
        names = {}
        for meal in MEALS:
            names.setdefault((meal.variant, meal.name), set()).add(meal.day)
        variant, name = next(k for k, days in names.items() if len(days) > 1)
        later = max(names[(variant, name)])

        text = f"{name.upper()} SPOTŘEBUJTE DO: {later.day}.{later.month}.{later.year}"
        meal = rank(text, MEALS, preferred=variant)[0][1]

        self.assertEqual((meal.name, meal.day), (name, later))


if __name__ == "__main__":
    unittest.main()
