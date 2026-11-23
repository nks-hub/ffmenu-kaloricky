import unittest
from datetime import date
from pathlib import Path

from ffkt.ffmenu import parse_menu, week_offset

FIXTURES = Path(__file__).parent / "fixtures"


def load(name, variant):
    return parse_menu((FIXTURES / f"{name}.html").read_text(encoding="utf-8"), variant)


class ParseMenuTest(unittest.TestCase):
    def test_racio_week_has_five_meals_per_weekday_without_day_totals(self):
        meals = load("racio-6000", 1)

        self.assertEqual(len(meals), 25)
        self.assertEqual(sorted({m.day for m in meals}),
                         [date(2026, 11, d) for d in range(23, 28)])
        self.assertNotIn("Celkem", {m.name for m in meals})

    def test_first_meal_carries_label_values(self):
        meal = load("racio-6000", 1)[0]

        self.assertEqual(meal.day, date(2026, 11, 23))
        self.assertEqual(meal.kind, "Snídaně")
        self.assertEqual(meal.name, "Vajíčková pomazánka s žitným chlebem")
        self.assertEqual((meal.kj, meal.protein, meal.carbs, meal.fat), (1263, 24, 22, 13))
        self.assertEqual((meal.fiber, meal.cholesterol), (2.4, 0))
        self.assertEqual(meal.allergens, "1, 3, 7")
        self.assertEqual(meal.key, "1:2026-11-23:0")

    def test_snacks_map_to_morning_and_afternoon_slots(self):
        monday = [m for m in load("racio-6000", 1) if m.day == date(2026, 11, 23)]

        self.assertEqual([(m.kind, m.day_time) for m in monday], [
            ("Snídaně", 1), ("Svačina", 2), ("Oběd", 3), ("Svačina", 4), ("Večeře", 5)])

    def test_muscle_extra_protein_goes_to_second_dinner(self):
        monday = [m for m in load("muscle", 2) if m.day == date(2026, 11, 23)]

        self.assertEqual(len(monday), 6)
        self.assertEqual((monday[-1].kind, monday[-1].name, monday[-1].day_time),
                         ("Navíc", "Protein", 6))
        self.assertEqual(monday[-1].protein, 22.5)

    def test_same_dish_differs_between_programs(self):
        lunch_6000 = load("racio-6000", 1)[2]
        lunch_7500 = load("racio-7500", 5)[2]

        self.assertEqual(lunch_6000.name, lunch_7500.name)
        self.assertEqual((lunch_6000.kj, lunch_7500.kj), (1095, 1890))

    def test_page_without_menu_gives_no_meals(self):
        self.assertEqual(parse_menu("<html><h1>Jídelníček</h1></html>", 1), [])


class WeekOffsetTest(unittest.TestCase):
    def test_offsets_are_counted_from_monday(self):
        today = date(2026, 11, 25)
        self.assertEqual(week_offset(date(2026, 11, 23), today), 0)
        self.assertEqual(week_offset(date(2026, 11, 29), today), 0)
        self.assertEqual(week_offset(date(2026, 11, 30), today), 1)
        self.assertEqual(week_offset(date(2026, 11, 20), today), -1)


if __name__ == "__main__":
    unittest.main()
