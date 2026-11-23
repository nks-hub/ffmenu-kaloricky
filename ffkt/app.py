"""HTTP service and command line that put FF Menu meals into the Kalorické tabulky diary."""
import argparse
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import urllib.error
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

    def _records(self):
        if not self.store_path.exists():
            return []
        return json.loads(self.store_path.read_text(encoding="utf-8"))

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
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            # write-then-rename so a crash cannot leave a half-written log that loses earlier entries
            tmp = self.store_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.store_path)

    def add_day(self, day, variant=None, diary_day=None):
        added, skipped = [], []
        for meal in self.day_menu(day, variant):
            try:
                self.add(meal, diary_day or day)
                added.append(meal)
            except AlreadyAdded:
                skipped.append(meal)
        return added, skipped


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
            if url.path in ("/", "/index.html"):
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
            if token and not hmac.compare_digest(self.headers.get("X-Token", ""), token):
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
    if not CONFIG.exists():
        sys.exit(f"Chybí {CONFIG.name}. Spusť nejdřív: python -m ffkt setup")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


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
