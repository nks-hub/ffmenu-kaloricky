# FF Menu → Kalorické tabulky

Zapisuje jídla z krabičkové stravy FF Menu (ffmenu.cz) do deníku Kalorických tabulek s hodnotami z jídelníčku FF Menu: energie, bílkoviny, sacharidy, tuky, vláknina a cholesterol.

Jídlo jde zapsat třemi způsoby:

- vyfocením štítku z krabičky v mobilu,
- tlačítkem „Do KT“ přímo na stránce jídelníčku ffmenu.cz (doplněk do prohlížeče),
- příkazem, který zapíše celý den naráz.

## Jak to funguje

Služba v Pythonu (3.10+, bez dalších balíčků) čte veřejný jídelníček na `ffmenu.cz/jidelnicek` a do Kalorických tabulek zapisuje stejným rozhraním, jaké používá jejich Android aplikace. Do deníku jde položka typu „vložená hodnota“ s názvem `FF Menu: <jídlo>`, takže v KT není potřeba zakládat potraviny. Snídaně, svačiny, oběd a večeře jdou do odpovídajícího jídla dne. Extra protein z programu Muscle jde do druhé večeře.

Stejné jídlo se do jednoho dne zapíše jen jednou. Co už je zapsané, si služba pamatuje v `data/added.json`.

Na štítku z krabičky je jen název, makra a datum spotřeby. QR kód na štítku vede jen na úvodní stránku ffmenu.cz. Štítek proto přečte OCR (Tesseract v prohlížeči) a služba ho spáruje s jídelníčkem podle názvu a data. Podle maker pozná i program, protože stejné jídlo má v každém programu jinou porci.

## Instalace

```
python -m ffkt setup
python -m ffkt serve
```

`setup` se zeptá na e-mail a heslo do Kalorických tabulek, ověří přihlášení a zeptá se na tvůj program. Do `config.local.json` uloží MD5 hash hesla (stejný, jaký posílá aplikace KT), program a přístupový token pro mobil a doplněk. Soubor je v `.gitignore`, nikam ho nesdílej, hash hesla stačí k přihlášení do KT.

`serve` spustí stránku na portu 8077.

## Mobil: sken štítku

1. Na počítači otevři `http://127.0.0.1:8077` a rozbal „Otevřít v mobilu (QR)“.
2. QR naskenuj fotoaparátem v mobilu. Mobil musí být ve stejné síti jako počítač, na kterém služba běží.
3. Na stránce „Vyfotit štítek“: vyfoť štítek zblízka a zkontroluj nalezené jídlo. Tlačítko „Zapsat“ ho zapíše do dne nastaveného nahoře.

Bez focení jde jídlo zapsat i ze seznamu „Jídelníček dne“.

## Doplněk na ffmenu.cz

- Chrome / Edge: `chrome://extensions` → Režim pro vývojáře → Načíst rozbalené → složka `extension`.
- Firefox: `about:debugging` → Tento Firefox → Dočasně načíst doplněk → `extension/manifest.json`.

V nastavení doplňku (klik na jeho ikonu) vlož odkaz z QR kódu: adresu služby i s tokenem. Na `ffmenu.cz/jidelnicek` pak u každého jídla přibude tlačítko „Do KT“ a u každého dne „Celý den do KT“. Jídla zapsaná dřív jsou zelená.

## Celý den automaticky

```
python -m ffkt add-day                 # dnešek
python -m ffkt add-day --date 2026-11-24
python -m ffkt menu                    # jen vypíše dnešní jídelníček
```

Ve Windows to jde pouštět každý všední den ráno přes Plánovač úloh:

```
schtasks /Create /TN "FF Menu do KT" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 06:30 /TR "cmd /c cd /d C:\path\to\ffmenu-kaloricky && python -m ffkt add-day"
```

## Testy

```
python -m unittest discover -s tests
```

Testy v prohlížeči (stránka pro mobil s OCR na skutečných fotkách štítků a doplněk na stránce jídelníčku) potřebují Playwright a internet:

```
pip install playwright
python -m playwright install chromium
FFKT_E2E=1 python -m unittest discover -s tests -p test_e2e.py
```

Testy nahrazují Kalorické tabulky lokálním serverem `tests/fake_kt.py`. Ten dodržuje protokol, který posílá Android aplikace KT 3.14.71.

## Omezení

- Rozhraní Kalorických tabulek je neoficiální. Když ho KT změní, zápis přestane fungovat a služba vrátí chybu z KT.
- QR kód, který by načetla přímo aplikace KT, udělat nejde. Její čtečka přijímá jen čárové kódy EAN a odkazy KT přes službu Kochava.
- Jídelníček na další týden zveřejňuje FF Menu až během týdne. Do té doby je seznam pro další týden prázdný.
