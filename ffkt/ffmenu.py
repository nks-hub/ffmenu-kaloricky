"""Weekly menu of ffmenu.cz, scraped from the public /jidelnicek page."""
import html
import re
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta

BASE_URL = "https://www.ffmenu.cz/jidelnicek"

# product_variant_id values from the program switch on /jidelnicek
PROGRAMS = {
    1: "Racio 6 000 kJ",
    5: "Racio 7 500 kJ",
    6: "Racio 9 000 kJ",
    7: "Racio 10 500 kJ",
    9: "Racio 12 000 kJ",
    2: "Muscle",
    3: "Low carb",
}

MONTHS = {name: i for i, name in enumerate(
    "ledna února března dubna května června července srpna září října listopadu prosince".split(), 1)}

# KT diary slots (ID_Cas): 1 breakfast, 2 morning snack, 3 lunch, 4 afternoon snack, 5 dinner, 6 second dinner
DAY_TIMES = {"Snídaně": 1, "Oběd": 3, "Večeře": 5}


@dataclass(frozen=True)
class Meal:
    variant: int
    day: date
    slot: int
    kind: str
    name: str
    kj: float
    protein: float
    carbs: float
    fat: float
    fiber: float
    cholesterol: float
    allergens: str
    day_time: int

    @property
    def key(self):
        return f"{self.variant}:{self.day.isoformat()}:{self.slot}"

    @property
    def program(self):
        return PROGRAMS.get(self.variant, str(self.variant))


def fetch_page(variant, weeks=0):
    url = f"{BASE_URL}?product_variant_id={variant}&weeks={weeks}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def week_offset(day, today):
    """The `weeks` URL parameter that shows the menu containing `day`."""
    return ((day - timedelta(days=day.weekday())) - (today - timedelta(days=today.weekday()))).days // 7


def _number(text):
    return float(re.sub(r"\s", "", text).replace(",", "."))


def _day(heading):
    match = re.search(r"(\d{1,2})\.\s*(\w+)\s+(\d{4})", html.unescape(heading))
    return date(int(match[3]), MONTHS[match[2]], int(match[1]))


def _day_time(kind, seen_lunch):
    if kind in DAY_TIMES:
        return DAY_TIMES[kind]
    if kind == "Svačina":
        return 4 if seen_lunch else 2
    return 6


def parse_menu(page, variant):
    meals = []
    for block in page.split("<div class='section-h3'>")[1:]:
        day = _day(re.search(r"<h2>(.*?)</h2>", block, re.S)[1])
        seen_lunch = False
        # the day ends with a "Celkem" (day total) card that has no meal name
        meal_part = block.split("flex-column justify-content-center")[0]
        cards = meal_part.split("position-relative product-select-container")[1:]
        for slot, card in enumerate(cards):
            card = html.unescape(card)
            kind = re.search(r"news-slider-tag[^>]*>([^<]+)<", card)[1].strip()
            values = {k: _number(v) for k, v in
                      re.findall(r"<small>([^<]+)</small>\s*<br>\s*(\d[\d\s,]*)", card)}
            day_time = _day_time(kind, seen_lunch)
            seen_lunch = seen_lunch or kind == "Oběd"
            meals.append(Meal(
                variant=variant,
                day=day,
                slot=slot,
                kind=kind,
                name=re.search(r"font-weight-bold'>([^<]+)</div>", card)[1].strip(),
                kj=_number(re.search(r"([\d\xa0 ]+)\s*kJ", card)[1]),
                protein=values["Bílkoviny"],
                carbs=values["Sacharidy"],
                fat=values["Tuky"],
                fiber=values.get("Vláknina", 0.0),
                cholesterol=values.get("Cholesterol", 0.0),
                allergens=" ".join(re.search(r"Alergeny:\s*([^<]*)<", card)[1].split()),
                day_time=day_time,
            ))
    return meals
