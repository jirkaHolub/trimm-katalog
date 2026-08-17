#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vygeneruje anglickou verzi katalogu z české.

    python3 build_en.py

Čte  trimm_katalog_FW_26_27_3.html  (zdroj pravdy, CZ)
     i18n/en.json                   (slovník CZ -> EN)
Píše trimm_katalog_FW_26_27_3_en.html

Čeština se upravuje vždy jen ve zdrojovém CZ souboru; EN se přegeneruje.
Nový/změněný český text, který ve slovníku chybí, skript vypíše jako
CHYBĚJÍCÍ PŘEKLAD a v EN souboru ho nechá česky.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'trimm_katalog_FW_26_27_3.html')
DICT = os.path.join(HERE, 'i18n', 'en.json')
OUT = os.path.join(HERE, 'trimm_katalog_FW_26_27_3_en.html')

missing = []


def translate_tag(html, pattern, table, kind):
    """Přeloží text uvnitř konkrétní značky, jinam nesahá."""
    def repl(m):
        before, cz, after = m.group(1), m.group(2), m.group(3)
        en = table.get(cz)
        if en is None:
            missing.append((kind, cz))
            en = cz
        return before + en + after
    return re.sub(pattern, repl, html, flags=re.S)


def main():
    html = open(SRC, encoding='utf-8').read()
    d = json.load(open(DICT, encoding='utf-8'))

    # 1) popisy produktů
    html = translate_tag(
        html, r'(<p class="card-desc">)(.*?)(</p>)', d['descriptions'], 'popis')

    # 2) vlastnosti (seznam <li> uvnitř karet)
    html = translate_tag(
        html, r'(<li>)(.*?)(</li>)', d['features'], 'vlastnost')

    # 3) aktivity
    html = translate_tag(
        html, r'(<span class="act-tag">)(.*?)(</span>)', d['activities'], 'aktivita')

    # 4) popisky materiálů a sekcí
    html = translate_tag(
        html, r'(<span class="mat-label">)(.*?)(</span>)', d['mat_labels'], 'materiál')
    html = translate_tag(
        html, r'(<div class="feat-label">)(.*?)(</div>)', d['feat_labels'], 'sekce')

    # 5) typ produktu (drží vyhledávání – hledá se i podle data-typ)
    html = translate_tag(
        html, r'(data-typ=")([^"]*)(")', d['types'], 'typ')
    # a stejný typ v zástupném dlaždici bez fotky
    html = translate_tag(
        html, r'(<span class="ph-typ">)(.*?)(</span>)', d['types'], 'typ')

    # 6) alt texty fotek
    html = html.replace(' – zadní strana"', ' – back"')

    # 7) ceny (DMOC) se v anglické verzi nezobrazují – vystřihnou se z HTML,
    #    aby se korunové ceny do EN katalogu vůbec nedostaly
    html, n_prices = re.subn(
        r'<span class="dmoc-price"><span class="dmoc-label">[^<]*</span>[^<]*</span>',
        '', html)

    # 8) UI, hlavička, patička
    for cz, en in d['ui']:
        html = html.replace(cz, en)

    # 9) přehození aktivní záložky v přepínači jazyka
    html = html.replace('hreflang="cs" class="active"', 'hreflang="cs"')
    html = html.replace('hreflang="en">EN', 'hreflang="en" class="active">EN')

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(html)

    print('zapsáno %s (%.1f kB)' % (os.path.basename(OUT), os.path.getsize(OUT) / 1024))
    print('odstraněno cen (DMOC): %d' % n_prices)

    if missing:
        print('\nCHYBĚJÍCÍ PŘEKLADY (%d) – doplň do i18n/en.json:' % len(missing))
        seen = set()
        for kind, cz in missing:
            if (kind, cz) in seen:
                continue
            seen.add((kind, cz))
            print('  [%s] %s' % (kind, cz))
        return 1

    # kontrola: zbyla v EN verzi čeština?
    body = re.sub(r'data:image/[^"\')]+', '', html)
    body = re.sub(r'<style>.*?</style>|<script>.*?</script>', '', body, flags=re.S)
    leftovers = sorted(set(re.findall(r'[^<>"\s]*[ěščřžýáíéúůťďňĚŠČŘŽÝÁÍÉÚŮŤĎŇ][^<>"\s]*', body)))
    if leftovers:
        print('\nPOZOR, v EN verzi zůstala česká slova (%d):' % len(leftovers))
        print(' ', ', '.join(leftovers[:40]))
        return 1

    print('kontrola: žádná čeština nezůstala')
    return 0


if __name__ == '__main__':
    sys.exit(main())
