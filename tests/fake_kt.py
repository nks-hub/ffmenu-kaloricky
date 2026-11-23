"""Local stand-in for the www.dine4fit.com legacy API, built from what KT Android 3.14.71 sends and expects."""
import hashlib
import json
import re
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

# self-signed, for browser tests that map www.dine4fit.com to this server
TLS = Path(__file__).parent / "fixtures" / "tls"


class FakeKT:
    def __init__(self, email="jan@example.com", password="tajne heslo", unit="kj", tls=False):
        self.email = email
        self.password_md5 = hashlib.md5(password.encode()).hexdigest()
        self.unit = unit
        self.hashes = set()
        self.intakes = []
        self.logins = 0
        self.reject_intake = None
        # next N requests get the HAProxy 503 page that the real API returns while overloaded
        self.unavailable = 0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        if tls:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(TLS / "cert.pem", TLS / "key.pem")
            # handshake in the request thread: a browser preconnect that never sends ClientHello
            # would otherwise block the accept loop and stall every later request
            self.server.socket = context.wrap_socket(self.server.socket, server_side=True,
                                                     do_handshake_on_connect=False)
        self.scheme = "https" if tls else "http"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"{self.scheme}://127.0.0.1:{self.server.server_port}/"

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self._dispatch(None)

            def do_POST(self):
                self._dispatch(self.rfile.read(int(self.headers.get("Content-Length", 0))))

            def _reply(self, xml):
                data = xml.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/xml; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _result(self, code, msg=""):
                self._reply(f"<result><code>{code}</code><msg>{msg}</msg></result>")

            def _dispatch(self, body):
                if fake.unavailable:
                    fake.unavailable -= 1
                    page = b"<html><body><h1>503 Service Unavailable</h1>\nNo server is available to handle this request.\n</body></html>\n"
                    self.send_response(503)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(page)))
                    self.end_headers()
                    return self.wfile.write(page)
                url = urlsplit(self.path)
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                if q.get("v") != "621" or q.get("pid") != "aNdV2wl7":
                    return self._result(400, "neznámý klient")
                if url.path == "/login.api.php":
                    return self._login(q)
                if q.get("HASH_Uzivatel") not in fake.hashes:
                    return self._result(450, "Uživatel není přihlášen")
                if url.path == "/getInfo.php":
                    return self._reply(f"<uzivatel><email>{fake.email}</email>"
                                       f"<preferUnit>{fake.unit}</preferUnit></uzivatel>")
                if url.path == "/addPrijem.php" and body is not None:
                    return self._intake(body)
                self._result(404, "neznámá akce")

            def _login(self, q):
                if q.get("Email") != fake.email:
                    return self._result(406, f"Přihlašovací email {q.get('Email')} není registrován.")
                if q.get("Pass") != fake.password_md5:
                    return self._result(401, "Špatné heslo")
                fake.logins += 1
                token = f"h{fake.logins}"
                fake.hashes.add(token)
                self._reply(f"<result><code>200</code><hash>{token}</hash><userID>42</userID></result>")

            def _intake(self, body):
                if fake.reject_intake:
                    return self._result(*fake.reject_intake)
                data = json.loads(body)
                valid = (re.fullmatch(r"\d{4}-\d\d-\d\d", data.get("Datum", ""))
                         and re.fullmatch(r"\d\d:\d\d", data.get("Cas", ""))
                         and data.get("ID_Cas") in range(1, 7)
                         and data.get("Polozky")
                         and all(i.get("Typ") == "vlozenaHodnota" and i.get("Nazev")
                                 and isinstance(i.get("Energie"), (int, float)) for i in data["Polozky"]))
                if not valid:
                    return self._result(400, "Neplatná data")
                fake.intakes.append(data)
                self._result(200)

        return Handler
