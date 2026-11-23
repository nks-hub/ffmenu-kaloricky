# FF Menu do Kalorických tabulek

Doplněk pro Chrome, který na jídelníčku [ffmenu.cz](https://www.ffmenu.cz/jidelnicek) ukáže u každého jídla QR kód. Když ho naskenuješ v aplikaci [Kalorické tabulky](https://www.kaloricketabulky.cz), otevře se jídlo s energií a makry z jídelníčku a přidáš ho do deníku.

English version: [README.md](README.md). Projekt nemá nic společného s FF Menu (BeraTaste s.r.o.) ani s Kalorickými tabulkami (Dine4Fit, a.s.).

## Co umí

- U každého jídla na ffmenu.cz/jidelnicek je QR kód, který čtečka v aplikaci Kalorické tabulky otevře jako potravinu.
- Energii, bílkoviny, sacharidy, tuky, vlákninu a cholesterol čte ze stránky. Nic neodhaduje.
- Každé jídlo v Kalorických tabulkách založí jen jednou. Když se jídlo v dalším týdnu vrátí, použije stejnou potravinu.
- Běží jen v prohlížeči: s Kalorickými tabulkami mluví napřímo a heslo si neukládá, drží jen jeho MD5 hash.
- Volitelně je tu služba v Pythonu se stránkou pro mobil: přečte štítek z krabičky (OCR) a najde jídlo v jídelníčku. Umí taky zapsat celý den jedním příkazem.

## Instalace

Chrome na Windows a macOS instaluje doplňky mimo Chrome Web Store jen v režimu pro vývojáře. Než bude doplněk v obchodě, instaluje se takhle:

1. Stáhni repozitář a sestav balíček: `git clone https://github.com/nks-hub/ffmenu-kaloricky.git`, pak v jeho složce `python tools/build_extension.py`. Vznikne `dist/ffmenu-kt-<verze>.zip`.
2. Zip rozbal do složky, kterou nebudeš mazat, protože Chrome z ní doplněk načítá při každém spuštění.
3. V Chrome otevři `chrome://extensions`, zapni Režim pro vývojáře, klikni na „Načíst rozbalené“ a vyber tu složku.
4. Klikni na ikonu doplňku, zadej e-mail a heslo do Kalorických tabulek a dej „Uložit a ověřit“. Pod tlačítkem se ukáže, jestli přihlášení prošlo.

Stejný zip se nahrává do Chrome Web Store. Texty zápisu, odpovědi k ochraně soukromí a obrázky jsou v [store/listing.md](store/listing.md).

Doplněk načte i Firefox 121 a novější. Část na stránce jídelníčku jsem zkoušel ve Firefoxu 160.

## Použití

Otevři [ffmenu.cz/jidelnicek](https://www.ffmenu.cz/jidelnicek) a vyber svůj program. Pod každým jídlem se objeví QR kód. V aplikaci Kalorické tabulky klepni na „Čárový kód“, namiř fotoaparát na kód a otevřenou potravinu přidej. Jmenuje se `FF Menu: <jídlo>` a jedna porce se zadává jako 100 g, protože FF Menu váhu porce neuvádí.

Potravinu doplněk založí pod tvým účtem, když jídlo poprvé zobrazí. Kalorické tabulky nové potraviny zpřístupňují všem uživatelům, takže jsou v jejich databázi veřejné.

## Sken štítku a celý den naráz (volitelné)

```
python -m ffkt setup                    # přihlášení do KT a tvůj program
python -m ffkt serve                    # stránka pro mobil na portu 8077
python -m ffkt add-day                  # zapíše dnešní jídla
python -m ffkt menu --date 2026-11-24   # vypíše jídelníček dne
```

`setup` uloží přihlášení, program a přístupový token do `config.local.json`. Je v něm MD5 hash hesla a ten k přihlášení do KT stačí. Soubor je v `.gitignore`, nikam ho neposílej.

V mobilu: na počítači otevři `http://127.0.0.1:8077`, rozbal „Otevřít v mobilu (QR)“ a QR naskenuj fotoaparátem. Mobil musí být ve stejné síti. Tlačítko „Vyfotit štítek“ přečte štítek a nabídne jídlo. Na Galaxy S21 s Chrome 157 trval jeden sken 7 až 8 sekund.

Celý den každý všední den ráno přes Plánovač úloh ve Windows:

```
schtasks /Create /TN "FF Menu do KT" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 06:30 /TR "cmd /c cd /d C:\cesta\k\ffmenu-kaloricky && python -m ffkt add-day"
```

## Jak to funguje

Kalorické tabulky veřejné API nemají. Všechno níž pochází z jejich aplikace pro Android 3.14.71.

Čtečka v aplikaci bere QR kód, který začíná `https://dine4fit.com/food/`, jako ID potraviny a tu otevře. Zná ještě odkazy na recepty, podniky a vlastní odkazy přes službu Kochava. Hodnoty živin z QR kódu přečíst neumí, takže jídlo musí v Kalorických tabulkách nejdřív existovat jako potravina.

Doplněk se přihlásí přes `login.api.php` a potravinu založí stejně jako „Přidat novou potravinu“ v aplikaci: `POST api/v1/food-suggestion/foodstuff` s hodnotami na 100 g, kategorií 1026 (Hotové pokrmy a polotovary) a třemi fotkami, které aplikace vyžaduje (obal, nutriční tabulka, složení). Krabičky FF Menu tabulku nemají, proto je fotkou vygenerovaná karta s hodnotami z jídelníčku a se zdrojem. Cukry a sůl jsou povinné, FF Menu je neuvádí, a tak se posílají jako 0.

Volitelná služba (`ffkt/kt.py`) zapisuje do deníku napřímo přes `addPrijem.php` jako „vloženou hodnotu“. QR kód na štítku krabičky vede jen na úvodní stránku ffmenu.cz, proto sken štítku čte jeho text a program pozná podle maker.

## Testy

```
python -m unittest discover -s tests
FFKT_E2E=1 python -m unittest discover -s tests -p test_e2e.py   # v prohlížeči, potřebuje Playwright
```

Tyhle testy se ke Kalorickým tabulkám nepřipojují, nahrazuje je lokální server `tests/fake_kt.py`.

Živé testy pouštějí službu i doplněk proti skutečným Kalorickým tabulkám a živému jídelníčku ffmenu.cz. Zapíšou jídla jednoho dne do účtu, přečtou je zpátky přes rozhraní, ze kterého aplikace KT kreslí deník, a zase je smažou. Pouštěj je jen s testovacím účtem:

```
FFKT_LIVE=1 FFKT_KT_EMAIL=... FFKT_KT_PASSWORD=... python -m unittest discover -s tests -p test_live.py
```

## Omezení

- Rozhraní Kalorických tabulek je neoficiální. Když ho změní, zápis selže a doplněk ukáže chybu, kterou KT vrátily.
- Potraviny založené doplňkem jsou v databázi Kalorických tabulek veřejné a mají cukry a sůl 0.
- Kalorické tabulky jednotku porce pojmenují „100 g“, takže jedna porce FF Menu se zadává jako 100 g.
- Jídelníček na další týden zveřejňuje FF Menu až během týdne. Do té doby pro něj QR kódy nejsou.

## Licence

MIT, viz [LICENSE](LICENSE).
