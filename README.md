# FF Menu to Kalorické tabulky

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Chrome Manifest V3](https://img.shields.io/badge/Chrome-Manifest_V3-4285F4?logo=googlechrome&logoColor=white)](extension/manifest.json)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](ffkt)

> Chrome extension that puts a "Do KT" button on every meal of the [ffmenu.cz](https://www.ffmenu.cz/jidelnicek) weekly menu and writes the meal into your [Kalorické tabulky](https://www.kaloricketabulky.cz) diary with the energy and macros from the menu.

Česká verze: [README.cs.md](README.cs.md). Not affiliated with FF Menu (BeraTaste s.r.o.) or Kalorické tabulky (Dine4Fit, a.s.).

## Features

- 🍱 **Button per meal** - "Do KT" on each meal card and "Celý den do KT" (whole day) next to each day on ffmenu.cz/jidelnicek
- ⚖️ **Values from the menu** - energy, protein, carbohydrates, fat, fiber and cholesterol are read from the page, nothing is estimated
- 🕐 **Matching diary slot** - breakfast, morning snack, lunch, afternoon snack and dinner land in the same meal in Kalorické tabulky; the extra protein of the Muscle program goes to second dinner
- 🔁 **Each meal once** - a meal is written once per day and stays marked green after a reload
- 🔐 **Runs in the browser only** - the extension calls Kalorické tabulky directly and stores the MD5 hash of your password, not the password
- 📷 **Optional label scanner** - a Python service with a phone page that reads the box label with OCR (Tesseract.js) and matches it to the menu, plus a command that logs a whole day

## Requirements

- Chrome, Edge or another Chromium browser. Firefox 121+ loads the extension as well; its menu-page part was checked in Firefox 160.
- A Kalorické tabulky account that signs in with email and password.
- For the optional scanner: Python 3.12, no third-party packages.

## Installation

```
git clone https://github.com/nks-hub/ffmenu-kaloricky.git
```

1. Open `chrome://extensions`, turn on Developer mode, click "Load unpacked" and pick the `extension` folder.
2. Click the extension icon, enter your Kalorické tabulky email and password and press "Uložit a ověřit". The status line confirms the login and shows the energy unit (kJ or kcal) set in your account.

## Usage

Open [ffmenu.cz/jidelnicek](https://www.ffmenu.cz/jidelnicek) and pick your program. Every meal card gets a "Do KT" button and every day a "Celý den do KT" button. A meal goes into the diary for the day it belongs to on the menu, named `FF Menu: <meal>`, at a fixed time for its slot (7:00, 10:00, 12:00, 15:00, 18:00, 20:00). Written meals turn green.

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

Kalorické tabulky has no public API. The extension (`extension/background.js`) and the service (`ffkt/kt.py`) call the legacy XML endpoints on www.dine4fit.com that the Kalorické tabulky Android app 3.14.71 uses:

- `login.api.php` takes the email and the MD5 of the password and returns a session hash,
- `getInfo.php` returns the energy unit preferred in the account,
- `addPrijem.php` adds a diary entry typed in by value (`Typ: vlozenaHodnota`), so no food record is created in Kalorické tabulky.

The menu comes from the public HTML of ffmenu.cz/jidelnicek. The same dish has a different portion in each program, so the scanner uses the macros printed on the label to tell programs apart. The QR code on the label only links to the ffmenu.cz home page, which is why the scanner reads the label text.

## Testing

```
python -m unittest discover -s tests
```

Browser tests run the extension on the menu page and the phone page OCR on two real label photos. They need Playwright, Chromium and internet access:

```
pip install playwright
python -m playwright install chromium
FFKT_E2E=1 python -m unittest discover -s tests -p test_e2e.py
```

Tests never contact Kalorické tabulky. `tests/fake_kt.py` stands in for it, and in browser tests Chromium resolves www.dine4fit.com to that server, which uses the self-signed test certificate in `tests/fixtures/tls`.

## Limitations

- The Kalorické tabulky API is unofficial. If it changes, writing fails and the extension shows the error returned by Kalorické tabulky.
- The scanner in the Kalorické tabulky app reads EAN barcodes and Kalorické tabulky's own Kochava links only, so no QR code can add a meal through that app.
- FF Menu publishes the next week's menu during the week. Until then the extension has no buttons for it.

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
