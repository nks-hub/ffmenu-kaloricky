# Chrome Web Store listing

Texts and answers for the developer dashboard. Upload `dist/ffmenu-kt-<version>.zip` from `python tools/build_extension.py`.

## Store listing (cs)

**Name:** FF Menu do Kalorických tabulek

**Summary:** QR kód k jídlům z jídelníčku ffmenu.cz. Naskenuješ ho v aplikaci Kalorické tabulky a jídlo přidáš do deníku.

**Description:**

Na jídelníčku ffmenu.cz přidá ke každému jídlu tlačítko „Zobrazit QR pro Kalorické tabulky“ a k energii v kJ přepočet na kcal. V aplikaci Kalorické tabulky klepneš na „Čárový kód“, namíříš fotoaparát na kód a otevře se jídlo s energií, bílkovinami, sacharidy, tuky, vlákninou a cholesterolem z jídelníčku. Pak ho jen přidáš do deníku.

Jak to funguje: v nastavení doplňku zadáš e-mail a heslo do Kalorických tabulek. Doplněk si uloží jen MD5 hash hesla. Po kliknutí jídlo v Kalorických tabulkách vyhledá. Když tam ještě není, založí ho pod tvým účtem jako potravinu, stejně jako „Přidat novou potravinu“ v aplikaci. Kalorické tabulky nové potraviny zpřístupňují všem uživatelům.

Dobré vědět:
- Jedna porce FF Menu se v aplikaci zadává jako 100 g, protože FF Menu váhu porce neuvádí.
- Cukry a sůl FF Menu neuvádí, Kalorické tabulky je ale vyžadují, proto mají hodnotu 0.
- Neoficiální doplněk. Nesouvisí s FF Menu (BeraTaste s.r.o.) ani s Kalorickými tabulkami (Dine4Fit, a.s.).

**Category:** Lifestyle

**Language:** Czech

**Graphics:** store icon `extension/icons/icon-128.png`, screenshots `store/screenshot-1-menu.png` and `store/screenshot-2-options.png` (1280×800), small promo tile `store/promo-440x280.png`.

## Privacy tab

**Single purpose:** Shows a QR code for each meal on the ffmenu.cz menu; the Kalorické tabulky app opens the meal from that code.

**Permission justifications:**
- `storage` - keeps the Kalorické tabulky email, the MD5 hash of the password, the session hash and the IDs of foods already created, so a dish is created only once.
- Host `https://www.dine4fit.com/*` - the Kalorické tabulky API: logging in and creating the meal as a food.
- Content script on `https://www.ffmenu.cz/jidelnicek*` - reads the meal values from the menu page and shows the QR codes.

**Remote code:** No. The QR code library (`lib/qrcode.js`, MIT) is bundled.

**Data usage:** Authentication information (email and password hash for Kalorické tabulky). It stays in the browser and is sent only to Kalorické tabulky. It is not sold, not transferred to third parties and not used for anything else than the single purpose.

**Privacy policy URL:** https://github.com/nks-hub/ffmenu-kaloricky/blob/main/PRIVACY.md
