# FF Menu do Kalorických tabulek

Doplněk pro Chrome, který na jídelníčku [ffmenu.cz](https://www.ffmenu.cz/jidelnicek) přidá u každého jídla tlačítko „Do KT“. Jídlo zapíše do deníku v [Kalorických tabulkách](https://www.kaloricketabulky.cz) s energií a makry z jídelníčku.

English version: [README.md](README.md). Projekt nemá nic společného s FF Menu (BeraTaste s.r.o.) ani s Kalorickými tabulkami (Dine4Fit, a.s.).

## Co umí

- U každého jídla na ffmenu.cz/jidelnicek je tlačítko „Do KT“, u každého dne „Celý den do KT“.
- Energii, bílkoviny, sacharidy, tuky, vlákninu a cholesterol čte ze stránky. Nic neodhaduje.
- Snídaně, dopolední svačina, oběd, odpolední svačina a večeře jdou do stejného jídla dne v Kalorických tabulkách. Extra protein z programu Muscle jde do druhé večeře.
- Jedno jídlo zapíše do jednoho dne jen jednou. Zapsaná jídla zůstanou zelená i po obnovení stránky.
- Běží jen v prohlížeči: s Kalorickými tabulkami mluví napřímo a heslo si neukládá, drží jen jeho MD5 hash.
- Volitelně je tu služba v Pythonu se stránkou pro mobil: přečte štítek z krabičky (OCR) a najde jídlo v jídelníčku. Umí taky zapsat celý den jedním příkazem.

## Instalace

1. Stáhni repozitář: `git clone https://github.com/nks-hub/ffmenu-kaloricky.git`.
2. V Chrome otevři `chrome://extensions`, zapni Režim pro vývojáře, klikni na „Načíst rozbalené“ a vyber složku `extension`.
3. Klikni na ikonu doplňku, zadej e-mail a heslo do Kalorických tabulek a dej „Uložit a ověřit“. Pod tlačítkem se ukáže, jestli přihlášení prošlo a jestli máš v KT nastavené kJ, nebo kcal.

Doplněk načte i Firefox 121 a novější. Část na stránce jídelníčku jsem zkoušel ve Firefoxu 160.

## Použití

Otevři [ffmenu.cz/jidelnicek](https://www.ffmenu.cz/jidelnicek) a vyber svůj program. Jídlo se zapíše do dne, ke kterému v jídelníčku patří, s názvem `FF Menu: <jídlo>` a pevným časem podle jídla dne (7:00, 10:00, 12:00, 15:00, 18:00, 20:00).

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

Kalorické tabulky veřejné API nemají. Doplněk i služba volají stejné XML rozhraní na www.dine4fit.com, jaké používá jejich aplikace pro Android 3.14.71: `login.api.php` (přihlášení), `getInfo.php` (jednotka energie v účtu) a `addPrijem.php` (zápis do deníku jako „vložená hodnota“, takže v KT nevzniká žádná potravina).

Jídelníček se čte z veřejné stránky ffmenu.cz/jidelnicek. QR kód na štítku vede jen na úvodní stránku ffmenu.cz, proto sken čte text štítku. Stejné jídlo má v každém programu jinou porci, program proto sken pozná podle maker na štítku.

## Testy

```
python -m unittest discover -s tests
FFKT_E2E=1 python -m unittest discover -s tests -p test_e2e.py   # v prohlížeči, potřebuje Playwright
```

Testy se ke Kalorickým tabulkám nepřipojují, nahrazuje je lokální server `tests/fake_kt.py`.

## Omezení

- Rozhraní Kalorických tabulek je neoficiální. Když ho změní, zápis selže a doplněk ukáže chybu, kterou KT vrátily.
- Čtečka v aplikaci Kalorické tabulky bere jen čárové kódy EAN a vlastní odkazy KT přes službu Kochava. QR kód, přes který by šlo jídlo přidat v aplikaci KT, proto udělat nejde.
- Jídelníček na další týden zveřejňuje FF Menu až během týdne. Do té doby pro něj doplněk tlačítka nemá.

## Licence

MIT, viz [LICENSE](LICENSE).
