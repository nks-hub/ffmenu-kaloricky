# Chrome Web Store listing

Texts and answers for the developer dashboard. Upload `dist/ffmenu-kt-<version>.zip` from `python tools/build_extension.py`.

## Store listing (cs)

**Name:** FF Menu do Kalorických tabulek

**Summary:** QR kód k jídlům z jídelníčku ffmenu.cz. Naskenuješ ho v aplikaci Kalorické tabulky a jídlo přidáš do deníku.

**Description:**

Na jídelníčku ffmenu.cz přidá ke každému jídlu tlačítko „Zobrazit QR pro Kalorické tabulky“ a k energii v kJ přepočet na kcal. V aplikaci Kalorické tabulky klepneš na „Čárový kód“, namíříš fotoaparát na kód a otevře se jídlo s energií, bílkovinami, sacharidy, tuky, vlákninou a cholesterolem z jídelníčku. Pak ho jen přidáš do deníku.

Jak to funguje: doplněk nechce žádné přihlášení. Po kliknutí pošle serveru doplňku, o které jídlo jde. Server si hodnoty přečte z jídelníčku ffmenu.cz a v Kalorických tabulkách jídlo vyhledá. Když tam ještě není, založí ho jako potravinu, stejně jako „Přidat novou potravinu“ v aplikaci. Kalorické tabulky nové potraviny zpřístupňují všem uživatelům.

Dobré vědět:
- Jedna porce FF Menu se v aplikaci zadává jako 100 g, protože FF Menu váhu porce neuvádí.
- Cukry a sůl FF Menu neuvádí, Kalorické tabulky je ale vyžadují, proto mají hodnotu 0.
- Neoficiální doplněk. Nesouvisí s FF Menu (BeraTaste s.r.o.) ani s Kalorickými tabulkami (Dine4Fit, a.s.).

**Category:** Lifestyle

**Language:** Czech

**Graphics:** store icon `extension/icons/icon-128.png`, screenshot `store/screenshot-1-menu.png` (1280×800), small promo tile `store/promo-440x280.png`.

## Privacy tab

**Single purpose:** Shows a QR code for each meal on the ffmenu.cz menu; the Kalorické tabulky app opens the meal from that code.

**Permission justifications:**
- Host `https://ffkt.nks-hub.cz/*` - the extension's server, which finds or creates the Kalorické tabulky food of a meal and returns its link for the QR code.
- Content script on `https://www.ffmenu.cz/jidelnicek*` - adds the QR buttons and the kcal values to the menu page.

**Remote code:** No. The QR code library (`lib/qrcode.js`, MIT) is bundled.

**Data usage:** None of the listed categories. The extension sends only the meal key (program, date, position on the menu) and stores nothing.

**Privacy policy URL:** https://github.com/nks-hub/ffmenu-kaloricky/blob/main/PRIVACY.md
