"""Ranks menu meals against OCR text read from an FF Menu box label."""
import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher

# a top score below this means the photo was sideways or unreadable
CONFIDENT = 0.6

MACROS = {"bilkoviny": "protein", "sacharidy": "carbs", "tuky": "fat"}


def normalize(text):
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip()


def _similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


def _name_score(name, words):
    tokens = [t for t in normalize(name).split() if len(t) >= 3]
    matched = sum(len(t) for t in tokens
                  if any(abs(len(t) - len(w)) <= 3 and _similar(t, w) >= 0.8 for w in words))
    return matched / sum(len(t) for t in tokens) if tokens else 0.0


def _label_dates(text):
    found = set()
    for d, m, y in re.findall(r"(\d{1,2})\.\s?(\d{1,2})\.\s?(20\d\d)", text):
        try:
            found.add(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    return found


def _label_macros(norm):
    """Gram values per macro; OCR often reads the trailing "g" of "12g" as "9", so 129 also counts as 12."""
    values = {}
    for word, number in re.findall(r"([a-z]{3,})\s*(\d{1,3})", norm):
        field = next((f for label, f in MACROS.items() if _similar(word, label) >= 0.75), None)
        if field:
            n = int(number)
            values.setdefault(field, set()).update({n, n // 10} if n >= 100 and number.endswith("9") else {n})
    return values


def rank(text, meals, preferred=None):
    """(score, meal) pairs, best first; dishes with identical values in several programs appear once."""
    norm = normalize(text)
    words = set(norm.split())
    dates = _label_dates(text)
    macros = _label_macros(norm)

    best = {}
    for meal in meals:
        score = _name_score(meal.name, words)
        if meal.day in dates:
            score += 0.3
        score += 0.1 * sum(round(getattr(meal, f)) in v for f, v in macros.items())
        if meal.variant == preferred:
            score += 0.05
        same = (meal.day, meal.name, meal.kj, meal.protein, meal.carbs, meal.fat)
        if same not in best or score > best[same][0]:
            best[same] = (score, meal)
    return sorted(best.values(), key=lambda pair: pair[0], reverse=True)
