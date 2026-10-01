"""Jednorázové naplnění aplikace staršími katalogy (dá se pouštět opakovaně, existující záznamy jen doplní):
  catalogs  – záznam katalogu SS27 + archivní katalogy, které existují jen jako PDF (SS26, FW 25/26)
  ss26      – výřezy karet z tiskového PDF SS26 = „loňská karta“ pro SS27  (cesta k PDF: proměnná SS_PDF)
  fw        – import schváleného FW 26/27 z HTML v kořeni repa jako uzavřený katalog (základ pro příští zimu)
Spuštění: python3 admin/migrate.py [catalogs] [ss26] [fw]   (bez parametrů vše)"""
import os, re, sys, json, html, shutil
import db, catalogs
from catalogs import slugify, REPO, UP, HERE
from schemas import SECTIONS, empty_product

SS_PDF = os.environ.get('SS_PDF', os.path.expanduser('~/Downloads/trimm_katalog_SS26_CZ_print.pdf'))
SS_PDF_SMALL = os.path.expanduser('~/Downloads/trimm_katalog_SS26_CZ_compressed.pdf')

def ensure(cat, **force):
    old = db.get_catalog(cat['code'])
    if old: cat = dict(cat, **{k: v for k, v in old.items() if k not in force})
    cat.update(force); db.save_catalog(cat); return cat

def seed_catalogs():
    ensure(catalogs.blank_catalog('SS', 2027, hero='uploads/hero-ss27.jpg', prev='SS26', doc_title='TRIMM — Katalog SS 27', out_html='ss27/trimm_katalog_SS27.html',
                                  out_pdf='vystupy/trimm_katalog_SS27_CZ.pdf', files=[dict(label='Záloha před korekturou 28. 9. 2026', path='vystupy/trimm_katalog_SS27_zaloha_2026-09-28.pdf')]))
    dst = 'podklady/katalogy/trimm_katalog_SS26_CZ.pdf'
    if not os.path.exists(os.path.join(REPO, dst)) and os.path.exists(SS_PDF_SMALL): shutil.copy(SS_PDF_SMALL, os.path.join(REPO, dst))
    ensure(catalogs.blank_catalog('SS', 2026, source='archive', status='done', files=[dict(label='PDF · CZ', path=dst)] if os.path.exists(os.path.join(REPO, dst)) else []))
    ensure(catalogs.blank_catalog('FW', 2025, source='archive', status='done', files=[dict(label='PDF · CZ (tisk)', path='podklady/katalogy/trimm_katalog_FW_25_26_CZ_print.pdf')]))
    print('katalogy:', [c['code'] for c in db.list_catalogs()])

def import_ss26_cards():
    """karta = sloupec produktu na stránce tiskového PDF (bez záhlaví a patičky)"""
    import fitz
    prods = json.load(open(os.path.join(REPO, 'ss27', 'data', 'pdf_products.json'), encoding='utf-8'))
    doc = fitz.open(SS_PDF); out_dir = os.path.join(UP, 'prev', 'SS26'); os.makedirs(out_dir, exist_ok=True); n = 0
    for r in prods:
        key = slugify(r['name']); pg = doc[r['page'] - 1]; x0, x1 = r['col']
        clip = fitz.Rect(max(0, x0 - 3), 26, min(pg.rect.width, x1 + 3), 581)
        fn = f'{key}.jpg'; pg.get_pixmap(dpi=170, clip=clip).pil_save(os.path.join(out_dir, fn), quality=82, optimize=True)
        seen = []; colors = []
        for s in r.get('swatches') or []:
            if s.get('label') and s['label'] not in seen: seen.append(s['label']); colors.append(dict(name=s['label']))
        db.save_prev_card(dict(season='SS26', key=key, name=r['name'], section=r.get('section'), page=r['page'], image=f'uploads/prev/SS26/{fn}', serie=r.get('serie') or '',
                               fields=r.get('fields') or {}, desc=r.get('desc') or '', features=r.get('features') or [], activities=r.get('activities') or [], colors=colors,
                               n_colors=len(colors) or None))   # vzorky bez popisku jsou čísla ze specifikací, ne barvy
        n += 1
    print('SS26: karet', n)

def import_fw():
    code = 'FW26_27'
    if db.count_products(code): print('FW 26/27 už je naimportovaný'); return
    h = open(os.path.join(REPO, 'trimm_katalog_FW_26_27_3.html'), encoding='utf-8').read()
    strip = lambda t: re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t))).strip()
    def copy_in(path, sub):
        if not path or not os.path.exists(os.path.join(REPO, path)): return None
        os.makedirs(os.path.join(UP, sub), exist_ok=True); dst = os.path.join(UP, sub, os.path.basename(path))
        if not os.path.exists(dst): shutil.copy(os.path.join(REPO, path), dst)
        return f'uploads/{sub}/{os.path.basename(path)}'
    SERIE = {'ski': 'SKI SERIE', 'snow-city': 'SNOW & CITY SERIE', 'outdoor': 'OUTDOOR SERIE', 'active': 'ACTIVE SERIE', 'thermolayer': 'THERMOLAYER SERIE',
             'backpacks': 'BACKPACKS', 'accessories': 'SPORTSWEAR ACCESSORIES'}
    hero = None
    if os.path.exists(os.path.join(REPO, 'hero-fw-26-27.jpg')): hero = copy_in('hero-fw-26-27.jpg', 'hero')
    files = [dict(label=l, path=p) for l, p in (('PDF · CZ', 'vystupy/trimm_katalog_FW_26_27_CZ.pdf'), ('PDF · EN', 'vystupy/trimm_katalog_FW_26_27_EN.pdf'),
             ('PDF · CZ na výšku', 'vystupy/trimm_katalog_FW_26_27_CZ_na_vysku.pdf'), ('PDF · EN na výšku', 'vystupy/trimm_katalog_FW_26_27_EN_na_vysku.pdf'),
             ('Web (HTML) · CZ', 'trimm_katalog_FW_26_27_3.html'), ('Web (HTML) · EN', 'trimm_katalog_FW_26_27_3_en.html')) if os.path.exists(os.path.join(REPO, p))]
    ensure(catalogs.blank_catalog('FW', 2026, hero=hero or '', prev='FW25_26', status='done', files=files, note='Schválený katalog sestavený mimo aplikaci; data převzatá z jeho HTML.'))
    for i, k in enumerate(('sportswear', 'backpacks')): db.save_section(code, dict(key=k, title=SECTIONS[k]['title'], cz=SECTIONS[k]['cz'], color=SECTIONS[k]['color'], pages=[], sort=i))
    order = {}; n = 0
    for m in re.finditer(r'<article class="product-card"(.*?)</article>', h, re.S):
        a = m.group(1); name = html.unescape(re.search(r'data-model="([^"]+)"', a).group(1)); sk = re.search(r'data-serie="([^"]*)"', a).group(1)
        section = 'backpacks' if sk == 'backpacks' else 'sportswear'; p = empty_product(section)
        g = re.search(r'<span class="icon-gender"[^>]*>(.*?)</span>', a, re.S); g = g.group(1) if g else ''
        men, women, kids = 'polyline points="15,3' in g, 'cy="9" r="6"' in g, 'cy="6" r="3"' in g
        pr = re.search(r'dmoc-label">DMOC</span>\s*(?:od\s*)?([\d\s ]+)', a); price = int(re.sub(r'\D', '', pr.group(1))) if pr and re.sub(r'\D', '', pr.group(1)) else None
        d = re.search(r'<p class="card-desc">(.*?)</p>', a, re.S); sz = re.search(r'class="size-range">(.*?)</span>', a)
        p.update(name=name, season=code, serie=SERIE.get(sk, sk.upper()), typ=(re.search(r'data-typ="([^"]*)"', a) or [None, ''])[1],
                 gender=None if section == 'backpacks' else ('uni' if men and women else 'men' if men else 'women' if women else 'kids' if kids else None),
                 price_min=price, price_max=price, desc=strip(d.group(1)) if d and 'placeholder' not in d.group(0) else '')
        if sz and strip(sz.group(1)): p['specs']['size'] = strip(sz.group(1))
        for mb in re.finditer(r'<span class="mat-label">(.*?)</span>\s*<span class="mat-value">(.*?)</span>', a, re.S):
            if strip(mb.group(2)) and 'placeholder' not in mb.group(2): p['fields'][strip(mb.group(1))] = strip(mb.group(2))
        for chunk in a.split('<div class="feat-block">')[1:]:
            lbl = re.search(r'<div class="feat-label">(.*?)</div>', chunk, re.S); lbl = strip(lbl.group(1)) if lbl else ''
            items = [strip(y) for x in re.findall(r'<li>(.*?)</li>|<span class="act-tag">(.*?)</span>', chunk, re.S) for y in x if y]
            (p['features'] if 'VLASTN' in lbl.upper() else p['activities']).extend(items)
        for ci in re.finditer(r'<div class="color-item">(.*?)</div></div>', a, re.S):
            c = ci.group(1); nm = re.search(r'class="color-name">([^<]*)', c); art = re.search(r'class="variant-art" src="([^"]+)"', c)
            p['colors'].append(dict(name=strip(nm.group(1)) if nm else '', codes=[], front=None, back=None, art=copy_in(html.unescape(art.group(1)), 'rozkresy') if art else None, generic=False))
        front = (re.search(r'class="photo-front" src="([^"]+)"', a) or [None, None])[1]; back = (re.search(r'class="photo-back" src="([^"]+)"', a) or [None, None])[1]
        if front:
            if not p['colors']: p['colors'].append(dict(name='', codes=[], front=None, back=None, art=None, generic=True))
            fs = slugify(os.path.basename(html.unescape(front)))
            c = max(p['colors'], key=lambda c: len(slugify(c['name'])) if c['name'] and slugify(c['name']) in fs else -1)
            c['front'] = copy_in(html.unescape(front), 'foto'); c['back'] = copy_in(html.unescape(back), 'foto') if back else None; c['main'] = True
        pid = base = slugify(name) or 'produkt'; i = 2
        while db.get_product(code, pid): pid = f'{base}_{i}'; i += 1
        order[section] = order.get(section, 0) + 1; p['id'] = pid; p['sort'] = order[section]
        db.save_product(p); n += 1
    print('FW 26/27: produktů', n)

if __name__ == '__main__':
    steps = sys.argv[1:] or ['catalogs', 'ss26', 'fw']
    if 'catalogs' in steps: seed_catalogs()
    if 'ss26' in steps:
        if os.path.exists(SS_PDF): import_ss26_cards()
        else: print('SS26: tiskové PDF nenalezeno (' + SS_PDF + ') – nastav SS_PDF=/cesta/k/pdf')
    if 'fw' in steps: import_fw()
