# FF Menu to Kalorické tabulky

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Chrome Manifest V3](https://img.shields.io/badge/Chrome-Manifest_V3-4285F4?logo=googlechrome&logoColor=white)](extension/manifest.json)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](ffkt)

> Chrome extension that shows a QR code next to every meal of the [ffmenu.cz](https://www.ffmenu.cz/jidelnicek) weekly menu. Scanning it with the [Kalorické tabulky](https://www.kaloricketabulky.cz) app opens the meal, with the energy and macros from the menu, ready to be added to your diary.

Česká verze: [README.cs.md](README.cs.md). Not affiliated with FF Menu (BeraTaste s.r.o.) or Kalorické tabulky (Dine4Fit, a.s.).

## Features

- 📱 **QR code per meal** - every meal card on ffmenu.cz/jidelnicek gets a QR code that the barcode scanner of the Kalorické tabulky app opens as a food
- ⚖️ **Values from the menu** - energy, protein, carbohydrates, fat, fiber and cholesterol are read from the page, nothing is estimated
- 🔁 **One food per dish** - the extension creates each dish in Kalorické tabulky once and reuses it when the dish comes back
- 🔐 **Runs in the browser only** - the extension calls Kalorické tabulky directly and stores the MD5 hash of your password, not the password
- 📷 **Optional label scanner** - a Python service with a phone page that reads the box label with OCR (Tesseract.js) and matches it to the menu, plus a command that logs a whole day

## Requirements

- Chrome, Edge or another Chromium browser. Firefox 121+ loads the extension as well; its menu-page part was checked in Firefox 160.
- A Kalorické tabulky account that signs in with email and password.
- For the optional scanner: Python 3.12, no third-party packages.

## Installation

Chrome on Windows and macOS installs extensions from outside the Chrome Web Store only in Developer mode, so until the extension is in the store:

```
git clone https://github.com/nks-hub/ffmenu-kaloricky.git
cd ffmenu-kaloricky
python tools/build_extension.py   # writes dist/ffmenu-kt-<version>.zip
```

1. Unzip `dist/ffmenu-kt-<version>.zip` into a folder you keep (Chrome loads the extension from it on every start).
2. Open `chrome://extensions`, turn on Developer mode, click "Load unpacked" and pick that folder.
3. Click the extension icon, enter your Kalorické tabulky email and password and press "Uložit a ověřit". The status line confirms the login.

The same zip is the upload for the Chrome Web Store; the listing texts, privacy answers and graphics are in [store/listing.md](store/listing.md).

## Usage

Open [ffmenu.cz/jidelnicek](https://www.ffmenu.cz/jidelnicek) and pick your program. Below every meal a QR code appears. In the Kalorické tabulky app tap "Čárový kód", point the camera at the code and add the food that opens. The food is named `FF Menu: <meal> (<portion energy> kJ)` and one portion is entered as 100 g, because FF Menu does not publish the weight of a portion. Kalorické tabulky fails with an error on a title it already has, so a repeated title gets a four-character suffix.

The extension creates the food under your account the first time it shows the meal. Kalorické tabulky makes new foods available to all its users, so these foods are public in their database.

## Label scanner and daily import (optional)

```
python -m ffkt setup                    # Kalorické tabulky login and your program
python -m ffkt serve                    # phone page on port 8077
python -m ffkt add-day                  # log today's meals
python -m ffkt menu --date 2026-11-24   # print a day's menu
```

`setup` saves the login, your program and an access token to `config.local.json`. The file holds the MD5 hash of your password, which is enough to log in to Kalorické tabulky; it is git-ignored, keep it private.

For the phone, open `http://127.0.0.1:8077` on the computer, expand "Otevřít v mobilu (QR)" and scan the code with the phone camera. The phone has to be on the same network. "Vyfotit štítek" reads the label and offers the matching meal; on a Galaxy S21 with Chrome 157 one scan took 7 to 8 seconds.

To log every weekday automatically on Windows:

```
schtasks /Create /TN "FF Menu do KT" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 06:30 /TR "cmd /c cd /d C:\path\to\ffmenu-kaloricky && python -m ffkt add-day"
```

## How it works

Kalorické tabulky has no public API; everything below comes from the Kalorické tabulky Android app 3.14.71.

The scanner of the app treats a QR code that starts with `https://dine4fit.com/food/` (resource `qr_food_prefix`) as a food ID and opens that food. It also knows recipe links, venue links and its own Kochava smart links, and it cannot take nutrition values from a QR code. A meal therefore has to exist in Kalorické tabulky as a food first.

The extension (`extension/background.js`) logs in through `login.api.php` (email and MD5 of the password) and creates the food the way the app's "Přidat novou potravinu" does: `POST api/v1/food-suggestion/foodstuff` with the values per 100 g, category 1026 (Hotové pokrmy a polotovary) and the three photos the app requires (package, nutrition table, ingredients). FF Menu boxes have no nutrition table, so the photo is a generated card with the menu values and their source. Sugar and salt are required fields that FF Menu does not publish, so they are sent as 0.

The optional service (`ffkt/kt.py`) writes diary entries directly with `addPrijem.php` (`Typ: vlozenaHodnota`). The same dish has a different portion in each program, so its label scanner uses the macros printed on the label to tell programs apart. The QR code on the box label only links to the ffmenu.cz home page, which is why the scanner reads the label text.

## Testing

```
python -m unittest discover -s tests
```

Browser tests run the extension on the menu page, decode its QR codes from screenshots, and run the phone page OCR on two real label photos. They need Playwright, Chromium, zxing-cpp and internet access:

```
pip install playwright zxing-cpp pillow
python -m playwright install chromium
FFKT_E2E=1 python -m unittest discover -s tests -p test_e2e.py
```

These tests never contact Kalorické tabulky. `tests/fake_kt.py` stands in for it, and in browser tests Chromium resolves www.dine4fit.com to that server, which uses the self-signed test certificate in `tests/fixtures/tls`.

Live tests run the service and the extension against the real Kalorické tabulky and the live ffmenu.cz menu. They write a day of meals into the account, read the entries back through the API the Kalorické tabulky app uses for its diary screen, and delete them again. Use a throwaway account:

```
FFKT_LIVE=1 FFKT_KT_EMAIL=... FFKT_KT_PASSWORD=... python -m unittest discover -s tests -p test_live.py
```

## Limitations

- The Kalorické tabulky API is unofficial. If it changes, writing fails and the extension shows the error returned by Kalorické tabulky.
- Foods created by the extension are public in the Kalorické tabulky database and show sugar and salt as 0.
- Kalorické tabulky names the portion unit "100 g", so one FF Menu portion is entered as 100 g.
- FF Menu publishes the next week's menu during the week. Until then there are no QR codes for it.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-change`)
3. Commit your changes (`git commit -m "feat: add my change"`)
4. Push to the branch (`git push origin feat/my-change`)
5. Open a Pull Request

## Support

- 📧 **Email:** dev@nks-hub.cz
- 🐛 **Bug reports:** [GitHub Issues](https://github.com/nks-hub/ffmenu-kaloricky/issues)

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">Made with ❤️ by <a href="https://github.com/nks-hub">NKS Hub</a></p>
