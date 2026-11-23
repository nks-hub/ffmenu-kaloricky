"""Client for the legacy XML API of Kalorické tabulky (www.dine4fit.com), as called by KT Android 3.14.71."""
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE_URL = "https://www.dine4fit.com/"
# app version code and client id that the Android app appends to every legacy request
APP_PARAMS = {"v": "621", "pid": "aNdV2wl7"}
# conversion factor used by the app itself (DataTool.convert)
KJ_PER_KCAL = 4.1871
# 450 = logged out, 451 = token belongs to another user; both are fixed by logging in again
SESSION_LOST = {450, 451}


class KTError(Exception):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code


class KTClient:
    def __init__(self, email, password_md5, base_url=BASE_URL, timeout=20):
        self.email = email
        self.password_md5 = password_md5
        self.base_url = base_url
        self.timeout = timeout
        self.hash = None
        self._unit = None

    def _request(self, path, params, body=None):
        query = urllib.parse.urlencode({**params, **APP_PARAMS})
        request = urllib.request.Request(
            f"{self.base_url}{path}?{query}",
            data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json; charset=UTF-8", "User-Agent": "okhttp/4.12.0"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            root = ET.fromstring(response.read())
        if root.tag == "result":
            code = int(root.findtext("code", "0"))
            if not 200 <= code < 300:
                raise KTError(code, root.findtext("msg") or "")
        return root

    def login(self):
        root = self._request("login.api.php", {"Email": self.email, "Pass": self.password_md5})
        self.hash = root.findtext("hash")
        if not self.hash:
            raise KTError(0, "přihlášení nevrátilo hash uživatele")
        return self.hash

    def _authed(self, path, body=None):
        if self.hash is None:
            self.login()
        try:
            return self._request(path, {"HASH_Uzivatel": self.hash}, body)
        except KTError as error:
            if error.code not in SESSION_LOST:
                raise
            self.login()
            return self._request(path, {"HASH_Uzivatel": self.hash}, body)

    def energy_unit(self):
        """'kj' or 'kcal' as set in the KT account; the app assumes kcal when the field is missing."""
        if self._unit is None:
            self._unit = (self._authed("getInfo.php").findtext("preferUnit") or "kcal").lower()
        return self._unit

    def add_custom(self, day, time, day_time, name, kj, protein, carbs, fat, fiber, cholesterol):
        """Diary entry typed in by value ("vložená hodnota"), no KT food record needed."""
        energy = kj if self.energy_unit() == "kj" else round(kj / KJ_PER_KCAL, 1)
        self._authed("addPrijem.php", {
            "Datum": day.isoformat(),
            "Cas": time,
            "ID_Cas": day_time,
            "Polozky": [{
                "Typ": "vlozenaHodnota",
                "Nazev": name,
                "Energie": energy,
                "Bilkoviny": protein,
                "Sacharidy": carbs,
                "Tuky": fat,
                "Vlaknina": fiber,
                "Cholesterol": cholesterol,
            }],
        })
