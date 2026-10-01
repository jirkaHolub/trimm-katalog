# Aplikace na tvorbu katalogů TRIMM

Správa všech katalogů (letních SS i zimních FW), produktů, fotek a generování HTML + PDF.

## Spuštění
Dvojklik na `admin/start.command` (poprvé macOS možná zeptá na povolení), nebo v Terminálu:
```
python3 admin/app.py
```
Otevře se http://localhost:8765. Potřebuje Python 3.9+, balíčky `fastapi`, `uvicorn`, `python-multipart`, `pillow`, `pymupdf`, `openpyxl`
(`python3 -m pip install --user fastapi "uvicorn[standard]" python-multipart pillow pymupdf openpyxl`) a Google Chrome (tisk PDF).

## Přihlášení (pro provoz na serveru)
Lokálně (`python3 admin/app.py`, `start.command`) běží aplikace bez přihlášení. Na serveru (spuštění přes `uvicorn app:app`) je přihlášení zapnuté.
- Účet = e-mail + heslo. Registrovat se jde jen s e-mailem z povolené domény (`KATALOG_EMAIL_DOMAIN`, výchozí `trimm.cz`, víc domén čárkou)
  a nový účet musí schválit správce na stránce „Uživatelé“. Správce tam účty i přidává, blokuje, maže a nastavuje hesla.
- První správce: `python3 admin/auth.py jmeno@trimm.cz` (heslo se zadá skrytě; tímto příkazem jde založit i účet mimo doménu).
- Účty jsou v `admin/users.sqlite` (není v gitu; jinde přes `KATALOG_AUTH_DB`). Podpis relací: `KATALOG_SECRET`, jinak se vygeneruje.
- `KATALOG_AUTH=1` zapne přihlášení i lokálně, `KATALOG_AUTH=0` ho vypne na serveru.

## Soubory
- `katalog.sqlite` – databáze: katalogy, jejich sekce a produkty, karty vytěžené ze starších PDF (verzovaná v gitu)
- `uploads/` – úložiště fotek: fotky, rozkresy, ikony, technické strany, úvodní fotky, `prev/` = výřezy karet z loňských PDF
- `cache/` – zmenšeniny a náhledy PDF (generují se samy, nejsou v gitu)
- `schemas.py` – co se u které kategorie vyplňuje
- `catalogs.py` – založení katalogu z loňského, porovnání s loňskem, přehled souborů a využití fotek
- `orderform.py` – načtení předobjednávkového formuláře (Excel), párování s kartami, návrh a provedení změn
- `generate.py` – generátor katalogu (HTML do `<kód>/`, PDF do `vystupy/`); z příkazové řádky `python3 admin/generate.py SS27 [--no-pdf]`
- `migrate.py` – jednorázové naplnění staršími katalogy (SS26 z tiskového PDF, FW 26/27 z HTML)
- `import_catalog.py` – původní import SS27 z pipeline (`ss27/data/catalog.json`); `--force` přepíše databázi

## Úvodní stránka – katalogy
- Karta každého katalogu s hotovými soubory (PDF, web), počty modelů a změnami oproti loňsku.
- „+ Letní katalog“ / „+ Zimní katalog“ založí nový ročník z loňského: převezme produkty, barvy, fotky, sekce, technické strany
  a úvodní fotku. Loňský katalog se nemění a slouží k porovnání.
- „+ Hotové PDF do archivu“ přidá katalog, který existuje jen jako PDF.
- Hotový katalog jde v nastavení uzavřít (nejde pak omylem přepsat) a zase odemknout.

## Nový katalog z předobjednávkového formuláře
1. Na úvodní stránce „+ Letní katalog“ / „+ Zimní katalog“, vyber loňský katalog a přilož formulář (.xlsx, camp i oblečení najednou).
   Formulář jde nahrát i později nebo znovu (nová verze) v záložce „Objednávkový formulář“ u katalogu.
2. Aplikace spáruje modely formuláře s hotovými kartami podle názvu a barvy podle kódů a názvů a ukáže návrh:
   změny u hotových karet (ceny, přidané a ubrané barvy, velikosti), modely bez karty a karty, které ve formuláři nejsou.
3. Model bez karty: převezme se hotová karta z jiného katalogu (pokud tam je), založí se prázdná, nebo se označí jako přejmenovaný model.
4. Teprve „Provést změny v katalogu“ katalog upraví. Texty, fotky, rozkresy a ikony hotových karet zůstávají.
Formulář stačí se sloupci Model, Položka a cena; sloupce Barva, Velikost, SK a Registrační číslo se použijí, když tam jsou
(bez nich se barva a velikost čtou z textu položky). Nahrané soubory se ukládají do `podklady/formulare/<kód>/`.

## Práce na katalogu
1. Vlevo vyber produkt (filtr podle kategorie, hledání). Šipky ▲▼ mění pořadí v kategorii.
   Druhá řada filtrů ukazuje stav oproti loňsku: nové, změněné, beze změny a vyřazené (loni byly, letos chybí – jdou vrátit).
2. Uprav pole, barvy, štítky. Ulož (Cmd+S).
   Fotky: přetáhni soubor do políčka, vlož ze schránky (Cmd+V nad políčkem) nebo použij lištu po najetí myší:
   ✎ upravit (ořez tažením, otočení, zrcadlení, oříznutí okrajů, vybělení nebo zprůhlednění pozadí), ⬆ nahrát, ☰ úložiště už nahraných fotek, 🌐 fotky z trimm.eu (podle odkazu u produktu) nebo z URL, × odebrat.
3. Vpravo je náhled karty a loňská karta téhož produktu (přepínač Letos / Loni / Vedle sebe) s výpisem změn:
   přidané a ubrané barvy, cena, upravená pole. Když se produkt přejmenoval, loňskou kartu mu přiřadíš ručně („jiná karta“).
4. „Nastavení katalogu“: nadpis a ročník, úvodní fotka, loňský katalog pro porovnání, sekce a technické strany, hotová PDF.
5. „Vygenerovat katalog“ vytvoří HTML a PDF, volitelně odešle na GitHub.

## Úložiště fotek
Všechny nahrané soubory na jednom místě: hledání podle názvu souboru i produktu, složky, filtr použité / nepoužité a podle katalogu.
U každého souboru je vidět, kde je použitý. Smazat jde jen soubor, který žádný katalog nepoužívá.
