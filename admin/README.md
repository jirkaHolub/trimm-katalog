# Administrace katalogu TRIMM

Jednoduchá aplikace pro správu produktů katalogu a generování HTML + PDF.

## Spuštění
Dvojklik na `admin/start.command` (poprvé macOS možná zeptá na povolení), nebo v Terminálu:
```
python3 admin/app.py
```
Otevře se http://localhost:8765. Potřebuje Python 3.9+, balíčky `fastapi`, `uvicorn`, `python-multipart`, `pillow`, `pymupdf`
(`python3 -m pip install --user fastapi "uvicorn[standard]" python-multipart pillow pymupdf`) a Google Chrome (tisk PDF).

## Soubory
- `katalog.sqlite` – databáze produktů (verzovaná v gitu)
- `uploads/` – fotky, rozkresy, ikony, technické strany (verzované, katalog na ně odkazuje)
- `schemas.py` – co se u které kategorie vyplňuje
- `generate.py` – generátor katalogu (HTML do `ss27/`, PDF do `vystupy/`)
- `import_catalog.py` – jednorázový import z původní pipeline (`ss27/data/catalog.json`); `--force` přepíše databázi

## Práce
1. Vlevo vyber produkt (filtr podle kategorie, hledání). Šipky ▲▼ mění pořadí v kategorii.
2. Uprav pole, barvy, štítky. Vpravo je náhled karty. Ulož (Cmd+S).
   Fotky: přetáhni soubor do políčka, vlož ze schránky (Cmd+V nad políčkem) nebo použij lištu po najetí myší:
   ✎ upravit (ořez tažením, otočení, zrcadlení, oříznutí okrajů, vybělení nebo zprůhlednění pozadí), ⬆ nahrát, ☰ knihovna už nahraných fotek, 🌐 fotky z trimm.eu (podle odkazu u produktu) nebo z URL, × odebrat.
3. „Vygenerovat katalog“ vytvoří HTML a PDF, volitelně odešle na GitHub.
