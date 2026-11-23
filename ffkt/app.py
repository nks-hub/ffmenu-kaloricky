"""HTTP service and command line that put FF Menu meals into the Kalorické tabulky diary."""
import argparse
import getpass
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import socket
import sys
import textwrap
import threading
import time
import urllib.error
import uuid
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .ffmenu import PROGRAMS, fetch_page, parse_menu, week_offset
from .kt import KJ_PER_KCAL, KTClient, KTError
from .match import CONFIDENT, rank

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "static" / "index.html"
CONFIG = ROOT / "config.local.json"
# diary time written for each KT slot (ID_Cas 1-6)
SLOT_TIMES = {1: "07:00", 2: "10:00", 3: "12:00", 4: "15:00", 5: "18:00", 6: "20:00"}
KEY = re.compile(r"(\d+):(\d{4}-\d\d-\d\d):(\d+)")
MENU_TTL = 3600
MAX_BODY = 64_000
# the KT scanner opens the food detail for QR codes starting with this (string qr_food_prefix in the app)
QR_FOOD_PREFIX = "https://dine4fit.com/food/"
# "Jídla a přílohy / Hotové pokrmy a polotovary" in GET api/v2/food-suggestion/category/list
READY_MEALS_CATEGORY = 1026


class AlreadyAdded(Exception):
    pass


class BadRequest(Exception):
    pass


class Service:
    def __init__(self, kt, program, store_path, fetch=fetch_page, today=date.today):
        self.kt = kt
        self.program = program
        self.store_path = Path(store_path)
        self.fetch = fetch
        self.today = today
        self._menus = {}
        self._lock = threading.Lock()
        self._food_lock = threading.Lock()
        self.foods_path = self.store_path.with_name("foods.json")

    def meals(self, variant, weeks):
        cached = self._menus.get((variant, weeks))
        if cached and time.monotonic() - cached[0] < MENU_TTL:
            return cached[1]
        try:
            meals = parse_menu(self.fetch(variant, weeks), variant)
        except urllib.error.HTTPError as error:
            # ffmenu.cz answers 404 for a week it has not published yet
            if error.code != 404:
                raise
            meals = []
        self._menus[(variant, weeks)] = (time.monotonic(), meals)
        return meals

    def day_menu(self, day, variant=None):
        variant = variant or self.program
        return [m for m in self.meals(variant, week_offset(day, self.today())) if m.day == day]

    def find(self, key):
        variant, day, slot = KEY.fullmatch(key).groups()
        for meal in self.day_menu(date.fromisoformat(day), int(variant)):
            if meal.slot == int(slot):
                return meal
        raise KeyError(key)

    def match(self, text):
        meals = [m for variant in PROGRAMS for weeks in (0, -1) for m in self.meals(variant, weeks)]
        return rank(text, meals, preferred=self.program)[:5]

    @staticmethod
    def _read(path, empty):
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else empty

    @staticmethod
    def _write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        # write-then-rename so a crash cannot leave a half-written file that loses earlier entries
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)

    def _records(self):
        return self._read(self.store_path, [])

    def added_keys(self, diary_day):
        return {r["key"] for r in self._records() if r["date"] == diary_day.isoformat()}

    def add(self, meal, diary_day):
        with self._lock:
            records = self._records()
            if any(r["key"] == meal.key and r["date"] == diary_day.isoformat() for r in records):
                raise AlreadyAdded(meal.key)
            self.kt.add_custom(day=diary_day, time=SLOT_TIMES[meal.day_time], day_time=meal.day_time,
                               name=f"FF Menu: {meal.name}", kj=meal.kj, protein=meal.protein,
                               carbs=meal.carbs, fat=meal.fat, fiber=meal.fiber,
                               cholesterol=meal.cholesterol)
            records.append({"date": diary_day.isoformat(), "key": meal.key, "name": meal.name,
                            "added": datetime.now().isoformat(timespec="seconds")})
            self._write(self.store_path, records)

    def food(self, meal):
        """GUID of the KT food for a menu meal: the one this account already has, or a new one."""
        values = food_values(meal)
        # the same dish comes back in later weeks and other programs with the same values
        cache_key = hashlib.md5(json.dumps([meal.name, values, meal.cholesterol]).encode()).hexdigest()
        # one at a time, so two visitors asking for a new dish together cannot create it twice
        with self._food_lock:
            foods = self._read(self.foods_path, {})
            if cache_key not in foods:
                foods[cache_key] = self._find_food(meal, values) or self._create_food(meal, values)
                self._write(self.foods_path, foods)
            return foods[cache_key]

    def _find_food(self, meal, values):
        name = f"FF Menu: {meal.name}"
        ours = [item for item in self.kt.duplicates(values)
                if item["title"] == name or item["title"].startswith(f"{name} (")]
        exact = [item for item in ours if item["title"] == food_title(meal)]
        return (exact or ours or [{}])[0].get("id")

    def _create_food(self, meal, values):
        # KT ignores the unit on creation (it keeps "100 g") and requires category, sugar and salt;
        # FF Menu publishes neither sugar nor salt, so they are 0
        data = {**values, "title": food_title(meal), "foodstuff_type_id": READY_MEALS_CATEGORY,
                "unit_name": "porce", "unit_multiplier": "100", "foodstuff_unit": "100g",
                "sugar": "0", "salt": "0", "cholesterol": f"{meal.cholesterol:g}"}
        photo = source_card(meal)
        try:
            return self.kt.create_food(data, photo)
        except KTError as error:
            # KT answers 500 for a title it already has; with other values the duplicate check misses it
            if error.code != 500:
                raise
            return self.kt.create_food({**data, "title": f"{data['title']} · {uuid.uuid4().hex[:4]}"}, photo)

    def add_day(self, day, variant=None, diary_day=None):
        added, skipped = [], []
        for meal in self.day_menu(day, variant):
            try:
                self.add(meal, diary_day or day)
                added.append(meal)
            except AlreadyAdded:
                skipped.append(meal)
        return added, skipped


def food_values(meal):
    """Values of one FF Menu portion, declared as 100 g because the menu gives no portion weight."""
    return {"energy": f"{meal.kj:g}", "energy_unit": "kj", "protein": f"{meal.protein:g}",
            "carbohydrate": f"{meal.carbs:g}", "fat": f"{meal.fat:g}", "fiber": f"{meal.fiber:g}"}


def food_title(meal):
    return f"FF Menu: {meal.name} ({meal.kj:g} kJ)"


def _font(size):
    from PIL import ImageFont
    # DejaVu Sans in the Docker image (fonts-dejavu-core), Arial on Windows; the Pillow default font
    # has no Czech letters
    for name in ("DejaVuSans.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    raise RuntimeError("chybí písmo DejaVu Sans nebo Arial")


def source_card(meal):
    """JPEG with the menu values and their source; KT takes a new food only with photos."""
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (900, 560), "white")
    draw = ImageDraw.Draw(image)
    y = 30
    for line in textwrap.wrap(f"FF Menu: {meal.name}", 44):
        draw.text((30, y), line, fill="#111", font=_font(34))
        y += 44
    for line in (f"1 porce: {meal.kj:g} kJ ({round(meal.kj / KJ_PER_KCAL)} kcal)",
                 f"Bílkoviny {meal.protein:g} g, Sacharidy {meal.carbs:g} g, Tuky {meal.fat:g} g",
                 f"Vláknina {meal.fiber:g} g, Cholesterol {meal.cholesterol:g} mg",
                 "Cukry a sůl FF Menu neuvádí.",
                 f"Zdroj: www.ffmenu.cz/jidelnicek, {meal.program}, {meal.day:%d. %m. %Y}"):
        y += 56
        draw.text((30, y), line, fill="#111", font=_font(28))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=90)
    return out.getvalue()


def meal_json(meal, **extra):
    return {"key": meal.key, "variant": meal.variant, "program": meal.program, "day": meal.day.isoformat(),
            "kind": meal.kind, "name": meal.name, "kj": meal.kj, "kcal": round(meal.kj / KJ_PER_KCAL),
            "protein": meal.protein, "carbs": meal.carbs, "fat": meal.fat, "fiber": meal.fiber,
            "allergens": meal.allergens, "day_time": meal.day_time, **extra}


def lan_address():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            # connecting a UDP socket sends nothing; it only picks the interface of the default route
            sock.connect(("192.0.2.1", 80))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def _date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise BadRequest(f"neplatné datum: {value!r}") from None


def _variant(value, default):
    if value in (None, ""):
        return default
    if not str(value).isdigit() or int(value) not in PROGRAMS:
        raise BadRequest(f"neznámý program: {value!r}")
    return int(value)


def make_server(service, host, port, token=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, status, payload, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, status, data):
            self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path in ("/", "/index.html") and PAGE.exists():
                return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            self._api(url, None)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._json(413, {"error": "příliš velký požadavek"})
            self._api(urlsplit(self.path), self.rfile.read(length))

        def _api(self, url, raw):
            if not url.path.startswith("/api/"):
                return self._json(404, {"error": "nenalezeno"})
            # the browser extension asks for foods without a token; it can only get meals of the menu
            if token and url.path != "/api/food" and not hmac.compare_digest(
                    self.headers.get("X-Token", ""), token):
                return self._json(403, {"error": "chybí nebo nesedí přístupový token"})
            try:
                body = None
                if raw is not None:
                    try:
                        body = json.loads(raw or b"null")
                    except ValueError:
                        raise BadRequest("tělo požadavku není JSON") from None
                    if not isinstance(body, dict):
                        raise BadRequest("tělo požadavku musí být JSON objekt")
                status, data = route(url.path, {k: v[0] for k, v in parse_qs(url.query).items()}, body)
            except BadRequest as error:
                status, data = 400, {"error": str(error)}
            except KTError as error:
                status, data = 502, {"error": f"Kalorické tabulky odmítly zápis ({error})"}
            except (urllib.error.URLError, TimeoutError) as error:
                status, data = 502, {"error": f"server není dostupný: {error}"}
            self._json(status, data)

    def route(path, query, body):
        if path == "/api/menu" and body is None:
            day = _date(query.get("date") or service.today().isoformat())
            diary = _date(query.get("diary") or day.isoformat())
            variant = _variant(query.get("program"), service.program)
            added = service.added_keys(diary)
            meals = [meal_json(m, added=m.key in added) for m in service.day_menu(day, variant)]
            return 200, {"date": day.isoformat(), "program": variant, "programs": PROGRAMS, "meals": meals}
        if path == "/api/food" and body is None:
            match = KEY.fullmatch(query.get("key", ""))
            if not match:
                raise BadRequest(f"neplatný klíč jídla: {query.get('key')!r}")
            _variant(match[1], None)
            # only the weeks ffmenu.cz shows, so a request cannot make the server fetch any week
            if abs(week_offset(_date(match[2]), service.today())) > 1:
                return 404, {"error": "jídlo v jídelníčku není"}
            try:
                meal = service.find(match[0])
            except KeyError:
                return 404, {"error": "jídlo v jídelníčku není"}
            return 200, {"url": QR_FOOD_PREFIX + service.food(meal)}
        if path == "/api/pair" and body is None:
            fragment = f"#t={token}" if token else ""
            return 200, {"url": f"http://{lan_address()}:{server.server_port}/{fragment}"}
        if body is None:
            raise BadRequest("chybí tělo požadavku")
        if path == "/api/match":
            text = body.get("text")
            if not isinstance(text, str) or not text.strip():
                raise BadRequest("chybí text ze štítku")
            results = service.match(text)
            return 200, {"confident": bool(results) and results[0][0] >= CONFIDENT,
                         "candidates": [meal_json(m, score=round(s, 2)) for s, m in results]}
        if path == "/api/add":
            key = body.get("key")
            if not isinstance(key, str) or not KEY.fullmatch(key):
                raise BadRequest(f"neplatný klíč jídla: {key!r}")
            diary = _date(body.get("date"))
            try:
                meal = service.find(key)
            except KeyError:
                return 404, {"error": "jídlo v jídelníčku není"}
            try:
                service.add(meal, diary)
            except AlreadyAdded:
                return 409, {"error": "tohle jídlo už je v deníku pro tento den zapsané"}
            return 200, {"added": meal_json(meal)}
        if path == "/api/add-day":
            day = _date(body.get("date"))
            added, skipped = service.add_day(day, _variant(body.get("program"), service.program))
            return 200, {"added": [meal_json(m) for m in added], "skipped": [meal_json(m) for m in skipped]}
        return 404, {"error": "nenalezeno"}

    server = ThreadingHTTPServer((host, port), Handler)
    return server


def load_config():
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    # Docker: the account comes from the environment; a missing token is random, so the diary stays closed
    if os.environ.get("FFKT_KT_EMAIL"):
        return {"kt_email": os.environ["FFKT_KT_EMAIL"],
                "kt_password_md5": hashlib.md5(os.environ["FFKT_KT_PASSWORD"].encode()).hexdigest(),
                "program": int(os.environ.get("FFKT_PROGRAM", 1)),
                "token": os.environ.get("FFKT_TOKEN") or secrets.token_urlsafe(16)}
    sys.exit(f"Chybí {CONFIG.name}. Spusť nejdřív: python -m ffkt setup")


def service_from_config(config):
    kt = KTClient(config["kt_email"], config["kt_password_md5"])
    return Service(kt, program=config.get("program", 1), store_path=ROOT / config.get("store", "data/added.json"))


def setup():
    email = input("E-mail do Kalorických tabulek: ").strip()
    password_md5 = hashlib.md5(getpass.getpass("Heslo: ").encode()).hexdigest()
    try:
        KTClient(email, password_md5).login()
    except KTError as error:
        sys.exit(f"Přihlášení se nepovedlo: {error}")
    for variant, name in PROGRAMS.items():
        print(f"  {variant}: {name}")
    program = _variant(input("Tvůj program FF Menu [1]: ").strip(), 1)
    CONFIG.write_text(json.dumps({"kt_email": email, "kt_password_md5": password_md5, "program": program,
                                  "token": secrets.token_urlsafe(16)}, indent=1), encoding="utf-8")
    print(f"Uloženo do {CONFIG}")


def print_day(meals, added=()):
    for meal in meals:
        mark = "✓" if meal.key in added else " "
        print(f"{mark} {meal.kind:<9} {meal.name:<50} {meal.kj:>5.0f} kJ  "
              f"B {meal.protein:g}  S {meal.carbs:g}  T {meal.fat:g}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m ffkt", description="FF Menu → Kalorické tabulky")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup", help="přihlášení do KT a výběr programu")
    serve = commands.add_parser("serve", help="spustí stránku pro mobil a API pro doplněk")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8077)
    for name, text in (("menu", "vypíše jídelníček dne"), ("add-day", "zapíše celý den do deníku")):
        command = commands.add_parser(name, help=text)
        command.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)

    if args.command == "setup":
        return setup()
    config = load_config()
    service = service_from_config(config)
    if args.command == "serve":
        server = make_server(service, args.host, args.port, token=config.get("token"))
        fragment = f"#t={config['token']}" if config.get("token") else ""
        print(f"Běží na http://127.0.0.1:{args.port}/ (v mobilu http://{lan_address()}:{args.port}/{fragment})")
        server.serve_forever()
    elif args.command == "menu":
        print_day(service.day_menu(args.date), service.added_keys(args.date))
    elif args.command == "add-day":
        try:
            added, skipped = service.add_day(args.date)
        except KTError as error:
            sys.exit(f"Kalorické tabulky odmítly zápis: {error}")
        print(f"Zapsáno {len(added)}, přeskočeno (už bylo) {len(skipped)}")
        print_day(added + skipped, {m.key for m in added + skipped})
