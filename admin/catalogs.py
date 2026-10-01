"""Katalogy (sezóny): založení nového z loňského, vazba na loňský katalog a rozdíly proti němu, soubory katalogu, využití fotek."""
import os, re, time, hashlib, unicodedata, collections
import db, generate
from schemas import SECTIONS, empty_product

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, '..'))
UP = os.path.join(HERE, 'uploads'); CACHE = os.path.join(HERE, 'cache')

KINDS = collections.OrderedDict([
    ('SS', dict(title='SPRING – SUMMER', cz='Letní', short='léto')),
    ('FW', dict(title='FALL – WINTER', cz='Zimní', short='zima')),
])
PHOTO_SLOTS = [('hero', 'hlavní fotka'), ('hero_inner', 'vnitřní stan'), ('hero_back', 'zadní pohled'), ('hero_reverse', 'rubová strana'), ('draw', 'rozkres rozměrů')]
COLOR_SLOTS = [('front', 'předek'), ('back', 'zadek'), ('art', 'rozkres')]

def slugify(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')
def norm(s): return re.sub(r'[^a-z0-9]+', '', unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower())

def code_for(kind, year):
    y = int(year) % 100
    return f'SS{y:02d}' if kind == 'SS' else f'FW{y:02d}_{(y + 1) % 100:02d}'
def year_label(kind, year):
    y = int(year)
    return str(y) if kind == 'SS' else f'{y % 100:02d}/{(y + 1) % 100:02d}'

def blank_catalog(kind, year, **kw):
    yl = year_label(kind, year)
    c = dict(code=code_for(kind, year), kind=kind, year_num=int(year), title=KINDS[kind]['title'], year=yl, doc_title=f'TRIMM — Katalog {kind} {yl}',
             hero='', prev='', status='draft', source='db', files=[])
    c.update(kw); return c

def create(kind, year, base='', copy_products=True, reset_new=True):
    """Nový katalog. Z výchozího (loňského) převezme sekce, technické strany, úvodní fotku a produkty; ten se zároveň stane „loňským“ pro porovnání."""
    if kind not in KINDS: raise ValueError('neznámý typ katalogu')
    cat = blank_catalog(kind, year)
    if db.get_catalog(cat['code']): raise ValueError(f'Katalog {cat["code"]} už existuje')
    b = db.get_catalog(base) if base else None
    if b: cat['prev'] = b['code']; cat['hero'] = b.get('hero') or ''
    db.save_catalog(cat)
    secs = db.list_sections(b['code']) if b else []
    if not secs: secs = [dict(key=k, title=s['title'], cz=s['cz'], color=s['color'], pages=[], sort=i) for i, (k, s) in enumerate(SECTIONS.items())]
    for s in secs: db.save_section(cat['code'], s)
    n = 0
    if b and b.get('source') == 'db' and copy_products:
        for p in db.list_products(b['code']):
            p['season'] = cat['code']; p.pop('prev_id', None)
            if reset_new: p['new'] = False
            db.save_product(p); n += 1
    return cat, n

# ---------- loňský katalog ----------
def prev_index(cat):
    """(druh, {klíč: záznam}) loňského katalogu: 'card' = produkty v databázi, 'image' = výřezy karet z PDF"""
    pc = db.get_catalog(cat.get('prev') or '') if cat else None
    if not pc: return None, None, {}
    if pc.get('source') == 'archive':
        cards = db.list_prev_cards(pc['code'])   # archiv bez vytěžených karet = není s čím porovnávat
        return ('image', pc, {c['key']: c for c in cards}) if cards else (None, None, {})
    return 'card', pc, {p['id']: p for p in db.list_products(pc['code'])}

def prev_key(q): return q.get('key') or q.get('id')

def match_prev(p, idx):
    pid = p.get('prev_id')
    if pid == '-': return None
    if pid: return idx.get(pid)
    return idx.get(p['id']) or idx.get(slugify(p['name']))

def diff(cur, prev, kind):
    """Rozdíly karty proti loňsku. U loňska z PDF (kind='image') se porovnává jen to, co šlo z PDF spolehlivě vytěžit."""
    d = dict(colors_added=[], colors_removed=[], changed=[], price=None, colors_count=None)
    pc = collections.OrderedDict((norm(c.get('name')), c.get('name')) for c in prev.get('colors') or [] if c.get('name'))
    cc = collections.OrderedDict((norm(c.get('name')), c.get('name')) for c in cur.get('colors') or [] if c.get('name'))
    if kind == 'card':
        d['colors_added'] = [v for k, v in cc.items() if k not in pc]; d['colors_removed'] = [v for k, v in pc.items() if k not in cc]
    elif prev.get('n_colors') and prev['n_colors'] != len(cur.get('colors') or []):   # názvy barev se z PDF nedají číst spolehlivě, počet vzorků ano
        d['colors_count'] = [prev['n_colors'], len(cur.get('colors') or [])]
    ch = d['changed']
    if norm(cur.get('name')) != norm(prev.get('name')): ch.append('název')
    if prev.get('desc') is not None and norm(cur.get('desc')) != norm(prev.get('desc')) and (kind == 'card' or prev.get('desc')): ch.append('popis')
    F, PF = cur.get('fields') or {}, prev.get('fields') or {}
    for k in list(F) + [k for k in PF if k not in F]:
        if kind == 'image' and not (F.get(k) and PF.get(k)): continue
        if norm(F.get(k)) != norm(PF.get(k)): ch.append(k.lower())
    for key, lbl in (('features', 'vlastnosti'), ('activities', 'aktivity')):
        a, b = {norm(x) for x in cur.get(key) or []}, {norm(x) for x in prev.get(key) or []}
        if a != b and (kind == 'card' or b): ch.append(lbl)
    if kind == 'card':
        if prev.get('price_min') != cur.get('price_min') or (prev.get('price_max') or prev.get('price_min')) != (cur.get('price_max') or cur.get('price_min')):
            d['price'] = [prev.get('price_min'), cur.get('price_min')]
        for key, lbl in (('serie', 'série'), ('typ', 'typ'), ('gender', 'pohlaví'), ('specs', 'specifikace'), ('sizes', 'velikosti')):
            if (cur.get(key) or None) != (prev.get(key) or None): ch.append(lbl)
        if [b.get('name') for b in cur.get('badges') or []] != [b.get('name') for b in prev.get('badges') or []]: ch.append('ikony')
        if any((cur.get(k) or None) != (prev.get(k) or None) for k, _ in PHOTO_SLOTS): ch.append('fotky')
        pcol = {norm(c.get('name')): c for c in prev.get('colors') or []}
        if any(norm(c.get('name')) in pcol and any((c.get(k) or None) != (pcol[norm(c.get('name'))].get(k) or None) for k, _ in COLOR_SLOTS) for c in cur.get('colors') or []): ch.append('fotky barev')
    d['status'] = 'changed' if (d['colors_added'] or d['colors_removed'] or d['colors_count'] or ch or d['price']) else 'same'
    return d

def overview(cat, products=None):
    """stav každého produktu proti loňsku + seznam loňských karet, které letos chybí"""
    kind, pc, idx = prev_index(cat)
    products = products if products is not None else db.list_products(cat['code'])
    st = {}; used = set()
    for p in products:
        q = match_prev(p, idx) if kind else None
        if not kind: st[p['id']] = None; continue
        if not q: st[p['id']] = dict(status='new'); continue
        used.add(prev_key(q)); d = diff(p, q, kind)
        cn = d['colors_count'] or [0, 0]
        st[p['id']] = dict(status=d['status'], added=len(d['colors_added']) or max(0, cn[1] - cn[0]), removed=len(d['colors_removed']) or max(0, cn[0] - cn[1]))
    removed = [dict(key=k, name=q['name'], section=q.get('section'), serie=q.get('serie') or '', page=q.get('page')) for k, q in idx.items() if k not in used]
    return dict(kind=kind, prev=pc['code'] if pc else None, status=st, removed=removed)

def prev_info(cat, p=None, key=None):
    """vše, co je potřeba k zobrazení loňské karty produktu (nebo loňské karty podle klíče)"""
    kind, pc, idx = prev_index(cat)
    if not kind: return dict(kind=None)
    q = idx.get(key) if key else match_prev(p, idx)
    out = dict(kind=kind, catalog=pc['code'], label=catalog_label(pc), found=bool(q), manual=bool(p and p.get('prev_id')))
    if not q: return out
    out.update(key=prev_key(q), name=q['name'], page=q.get('page'))
    if kind == 'image':
        out['image'] = q.get('image'); pdf = next((f['path'] for f in pc.get('files') or [] if f['path'].lower().endswith('.pdf')), None)
        if pdf and q.get('page'): out['pdf'] = f'/repo/{pdf}#page={q["page"]}'
        out['n_colors'] = q.get('n_colors')
    else:
        out['colors'] = [c.get('name') for c in q.get('colors') or []]; out['price_min'] = q.get('price_min')
    if p: out['diff'] = diff(p, q, kind)
    return out

def restore(cat, key):
    """vrátí do katalogu produkt, který byl loni a letos chybí"""
    kind, pc, idx = prev_index(cat); q = idx.get(key)
    if not q: raise ValueError('loňská karta nenalezena')
    if kind == 'card': p = dict(q); p.pop('prev_id', None); p['new'] = False
    else:
        sec = q.get('section') if q.get('section') in SECTIONS else 'tents'; p = empty_product(sec)
        p.update(name=q['name'], serie=q.get('serie') or '', desc=q.get('desc') or '', fields=q.get('fields') or {}, features=q.get('features') or [], activities=q.get('activities') or [],
                 colors=[dict(name=c['name'], codes=[], front=None, back=None, art=None, generic=False) for c in q.get('colors') or [] if c.get('name')])
    p['season'] = cat['code']; pid = base = (q.get('id') or slugify(q['name']) or 'produkt'); i = 2
    while db.get_product(cat['code'], pid): pid = f'{base}_{i}'; i += 1
    p['id'] = pid; p['prev_id'] = key if pid != key else None; p['sort'] = db.next_sort(cat['code'], p['section'])
    db.save_product(p); return p

# ---------- soubory a přehled ----------
def catalog_label(cat): return f'{cat["kind"]} {cat["year"]}' if cat.get('kind') else cat['code']

_pdf_pages = {}
def file_info(path, label):
    fp = os.path.join(REPO, path)
    if not os.path.exists(fp): return None
    st = os.stat(fp); d = dict(label=label, path=path, url='/repo/' + path, size=st.st_size, mtime=st.st_mtime, ext=os.path.splitext(path)[1].lower().lstrip('.'))
    if d['ext'] == 'pdf':
        k = (path, st.st_mtime)
        if k not in _pdf_pages:
            try:
                import fitz; doc = fitz.open(fp); _pdf_pages[k] = len(doc); doc.close()
            except Exception: _pdf_pages[k] = None
        d['pages'] = _pdf_pages[k]
    return d

def catalog_files(cat):
    out = []
    if cat.get('source') == 'db':
        cfg = generate.catalog_cfg(cat)
        for lbl, p in (('PDF · CZ', cfg['out_pdf']), ('Web (HTML)', cfg['out_html'])):
            f = file_info(os.path.relpath(p, REPO), lbl)
            if f: f['generated'] = True; out.append(f)
    for e in cat.get('files') or []:
        f = file_info(e['path'], e.get('label') or os.path.basename(e['path']))
        if f: out.append(f)
    return out

def summary(cat):
    files = catalog_files(cat); c = dict(cat); c['label'] = catalog_label(cat); c['files'] = files
    c['cover'] = cat.get('hero') or None; c['cover_pdf'] = next((f['path'] for f in files if f['ext'] == 'pdf'), None)
    if cat.get('source') == 'db':
        prods = db.list_products(cat['code']); ov = overview(cat, prods)
        c['n_products'] = len(prods); c['n_colors'] = sum(len(p.get('colors') or []) for p in prods); c['n_new_flag'] = sum(1 for p in prods if p.get('new'))
        if ov['kind']:
            cnt = collections.Counter(s['status'] for s in ov['status'].values() if s)
            c['vs_prev'] = dict(prev=ov['prev'], new=cnt['new'], changed=cnt['changed'], same=cnt['same'], removed=len(ov['removed']))
    else:
        c['n_products'] = len(db.list_prev_cards(cat['code'])) or None
    return c

def pdf_cover(path, width=560):
    """náhled první strany PDF (cache podle času změny souboru)"""
    fp = os.path.join(REPO, path)
    if '..' in path or not path.lower().endswith('.pdf') or not os.path.exists(fp): return None
    os.makedirs(os.path.join(CACHE, 'covers'), exist_ok=True)
    out = os.path.join(CACHE, 'covers', hashlib.md5(f'{path}|{os.path.getmtime(fp)}|{width}'.encode()).hexdigest() + '.jpg')
    if not os.path.exists(out):
        import fitz
        doc = fitz.open(fp); pg = doc[0]; pg.get_pixmap(matrix=fitz.Matrix(width / pg.rect.width, width / pg.rect.width)).save(out); doc.close()
    return out

def thumb(path, width=320):
    """zmenšenina nahraného obrázku pro přehledy (cache podle času změny)"""
    from PIL import Image
    fp = os.path.join(HERE, path)
    if '..' in path or not path.startswith('uploads/') or not os.path.exists(fp): return None
    os.makedirs(os.path.join(CACHE, 'thumbs'), exist_ok=True)
    h = hashlib.md5(f'{path}|{os.path.getmtime(fp)}|{width}'.encode()).hexdigest()
    for ext in ('jpg', 'png'):
        if os.path.exists(os.path.join(CACHE, 'thumbs', f'{h}.{ext}')): return os.path.join(CACHE, 'thumbs', f'{h}.{ext}')
    im = Image.open(fp); im.load(); alpha = im.mode in ('RGBA', 'LA', 'P')
    im = im.convert('RGBA' if alpha else 'RGB'); im.thumbnail((width, width))
    out = os.path.join(CACHE, 'thumbs', f'{h}.{"png" if alpha else "jpg"}')
    im.save(out, optimize=True) if alpha else im.save(out, quality=80)
    return out

# ---------- úložiště fotek ----------
def photo_usage():
    """{cesta: [kde je soubor použitý]} přes všechny katalogy"""
    use = collections.defaultdict(list)
    def add(path, **kw):
        if path: use[path].append(kw)
    for cat in db.list_catalogs():
        code = cat['code']; add(cat.get('hero'), catalog=code, what='úvodní fotka katalogu')
        for s in db.list_sections(code):
            for pg in s.get('pages') or []: add(pg, catalog=code, what=f'technická strana · {s["cz"]}')
        if cat.get('source') == 'archive':
            for c in db.list_prev_cards(code): add(c.get('image'), catalog=code, what=f'karta z PDF · {c["name"]}')
            continue
        for p in db.list_products(code):
            for k, lbl in PHOTO_SLOTS: add(p.get(k), catalog=code, id=p['id'], name=p['name'], what=lbl)
            for b in p.get('badges') or []: add(b.get('file'), catalog=code, id=p['id'], name=p['name'], what='ikona')
            for c in p.get('colors') or []:
                for k, lbl in COLOR_SLOTS: add(c.get(k), catalog=code, id=p['id'], name=p['name'], what=f'{lbl} · {c.get("name") or ""}')
    return use

FOLDERS = collections.OrderedDict([('foto', 'Fotky produktů'), ('rozkresy', 'Rozkresy'), ('ikony', 'Ikony'), ('ikony_produkt', 'Ikony z PDF'), ('pages', 'Technické strany'),
                                   ('hero', 'Úvodní fotky'), ('prev', 'Karty z loňských PDF'), ('ostatni', 'Ostatní')])

def storage(q='', folder='', used='', catalog=''):
    use = photo_usage(); out = []; counts = collections.Counter(); total = 0
    for root, dirs, files in os.walk(UP):
        rel = os.path.relpath(root, HERE).replace(os.sep, '/'); top = rel.split('/')[1] if '/' in rel else 'hero'
        for f in files:
            if not f.lower().endswith(('.jpg', '.jpeg', '.png')): continue
            path = f'{rel}/{f}'; u = use.get(path, []); st = os.stat(os.path.join(root, f)); counts[top] += 1; total += st.st_size
            if folder and top != folder: continue
            if q and q.lower() not in path.lower() and not any(q.lower() in (x.get('name') or '').lower() for x in u): continue
            if used == 'yes' and not u: continue
            if used == 'no' and u: continue
            if catalog and not any(x['catalog'] == catalog for x in u): continue
            out.append(dict(path=path, name=f, folder=top, size=st.st_size, mtime=st.st_mtime, uses=u))
    out.sort(key=lambda x: (x['folder'] == 'prev', -x['mtime']))
    return dict(files=out, counts=counts, total_size=total, folders=[dict(key=k, label=v, n=counts.get(k, 0)) for k, v in FOLDERS.items() if counts.get(k)] +
                [dict(key=k, label=k, n=n) for k, n in counts.items() if k not in FOLDERS])
