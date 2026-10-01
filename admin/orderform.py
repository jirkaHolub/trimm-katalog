"""Předobjednávkový formulář (Excel, řádek = model × barva × velikost) jako zdroj katalogu:
načtení, spárování modelů a barev s hotovými kartami, návrh změn a jejich provedení."""
import os, re, io, json, difflib, collections
import db, catalogs
from catalogs import slugify, norm, REPO
from schemas import SCHEMAS, SECTIONS, empty_product

SEC_BY_SK = {'T01': 'tents', 'T02': 'sleeping', 'T03': 'mattress', 'T04': 'backpacks', 'T05': 'backpacks', 'T06': 'backpacks', 'T08': 'sportswear'}
SIZES = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', '2XL', '3XL', 'XXXL', '4XL', '5XL', 'UNI', 'MIX']
COLS = [('model', ('model',)), ('item', ('polozka',)), ('color', ('barva',)), ('size', ('velikost',)), ('sk', ('sk',)), ('reg', ('registracnicislo',)),
        ('ean', ('carovykod', 'ean')), ('price', ('doporucenamoc', 'moc', 'dmoc')), ('order', ('poradi',))]

def _cell(v): return re.sub(r'\s+', ' ', str(v)).strip() if v not in (None, '') else ''
def color_name(s): return re.sub(r'\s*/\s*', '/', _cell(s))

_SZ = r'(?:\d?X{0,3}[SML]|\dXL|XL)\+?'
def is_size(t): return bool(re.fullmatch(rf'{_SZ}(?:[/-]{_SZ})?|\d{{2,3}}(?:-\d{{2,3}})?|uni|mix|\d+mm', t, re.I))

def color_vocab():
    """slova, ze kterých se skládají názvy barev ve všech katalozích (pro formuláře bez sloupce Barva)"""
    v = set()
    for c in db.list_catalogs():
        for p in (db.list_products(c['code']) if c.get('source') == 'db' else []):
            for col in p.get('colors') or []: v.update(w for w in re.split(r'[/\s]+', (col.get('name') or '').lower()) if w)
    return v

def split_item(item, model, vocab=()):
    """z „bunda AVALON XL white/black“ vrátí (velikost, barva) – pro formuláře bez sloupců Barva a Velikost"""
    toks = [t for i, t in enumerate(item.split(' ')) if i == 0 or t.lower() != 'trimm']; mt = norm(model); i = 1; acc = ''   # značka v textu položky není barva
    while i < len(toks) and not acc.startswith(mt) and (mt.startswith(acc + norm(toks[i])) or (acc + norm(toks[i])).startswith(mt)): acc += norm(toks[i]); i += 1
    known = lambda t: all(w in vocab for w in t.lower().split('/') if w)
    rest = toks[i:] if acc.startswith(mt) and acc else None
    if rest is None:   # název modelu v položce není: barva = koncová slova, která známe z jiných karet
        rest = toks[1:]; sizes = []
        while rest and is_size(rest[-1]) and len(rest) > 1: sizes.append(rest.pop())
        j = len(rest)
        while j > 0 and known(rest[j - 1]): j -= 1
        sizes += [t for t in rest[:j] if is_size(t)]
        return (sizes[0] if sizes else ''), color_name(' '.join(rest[j:] or rest))
    size = ''
    while rest and is_size(rest[0]) and len(rest) > 1: size = size or rest[0]; rest = rest[1:]
    while len(rest) > 1 and is_size(rest[-1]): size = size or rest[-1]; rest = rest[:-1]
    g = re.fullmatch(rf'({_SZ})([a-z].*)', rest[0]) if rest else None   # překlep „Lmustard“ = velikost L + mustard
    if g and known(g.group(2)) and not known(rest[0]): size = size or g.group(1); rest = [g.group(2)] + rest[1:]
    return size, color_name(' '.join(rest))

def parse(files):
    """files = [(název, bytes)] → dict(files, rows, models=[...], warnings)"""
    import openpyxl
    models = collections.OrderedDict(); warnings = []; n_rows = 0; vocab = None
    for fname, raw in files:
        try: wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
        except Exception as e: raise ValueError(f'{fname}: soubor nejde otevřít jako Excel (.xlsx) – {e}')
        found = False
        for ws in wb:
            rows = ws.iter_rows(values_only=True); head = None
            for r in rows:   # hlavička = první řádek se sloupcem Model
                h = [norm(v) for v in r]
                if 'model' in h: head = h; break
            if not head: continue
            ix = {k: next((i for i, h in enumerate(head) if any(h.startswith(a) for a in al)), None) for k, al in COLS}
            get = lambda r, k: _cell(r[ix[k]]) if ix[k] is not None and ix[k] < len(r) else ''
            found = True
            for r in rows:
                name = get(r, 'model')
                if not name: continue
                n_rows += 1; item = get(r, 'item'); sk = get(r, 'sk').upper(); typ = item.split(' ')[0].lower() if item else ''
                size, color = get(r, 'size'), color_name(get(r, 'color'))
                if ix['color'] is None and item:
                    vocab = color_vocab() if vocab is None else vocab
                    s2, color = split_item(item, name, vocab); size = size or s2
                m = models.get(norm(name))
                if not m:
                    section = SEC_BY_SK.get(sk) or next((k for k, s in SCHEMAS.items() if typ in s['typ']), 'sportswear')
                    m = models[norm(name)] = dict(key=norm(name), name=name, typ=typ, sk=sk, section=section, colors=collections.OrderedDict(), sizes=[], prices=[], file=fname)
                c = m['colors'].setdefault(norm(color), dict(name=color, codes=[]))
                code = (sk + get(r, 'reg')) if get(r, 'reg') else get(r, 'ean')
                if code and code not in c['codes']: c['codes'].append(code)
                if size and size not in m['sizes']: m['sizes'].append(size)
                pr = re.sub(r'[^\d.,]', '', get(r, 'price')).replace(',', '.')
                if pr:
                    try: m['prices'].append(int(float(pr)))
                    except ValueError: pass
        if not found: warnings.append(f'{fname}: nenašel jsem sloupec „Model“ – soubor jsem přeskočil.')
    out = []
    for m in models.values():
        m['colors'] = list(m['colors'].values()); m['price_min'] = min(m['prices']) if m['prices'] else None; m['price_max'] = max(m['prices']) if m['prices'] else None
        del m['prices']; out.append(m)
    if not out and not warnings: warnings.append('Ve formuláři nejsou žádné řádky s modelem.')
    return dict(files=[f for f, _ in files], rows=n_rows, models=out, warnings=warnings)

# ---------- uložení formuláře u katalogu ----------
def store(code, files, parsed):
    d = os.path.join(REPO, 'podklady', 'formulare', code); os.makedirs(d, exist_ok=True)
    for fname, raw in files: open(os.path.join(d, os.path.basename(fname)), 'wb').write(raw)
    db.set_setting(f'form:{code}', parsed)
def load(code): return db.get_setting(f'form:{code}')

# ---------- párování ----------
def _nodark(s): return norm('/'.join(re.sub(r'^dark\s+', '', t.strip()) for t in s.lower().split('/')))

def match_colors(have, want):
    """spáruje barvy karty s barvami formuláře: podle kódů, názvu, názvu bez „dark“, jednoznačného začátku → (páry, přidat, ubrat)"""
    pairs = []; fh = list(have); fw = list(want)
    def take(test):
        for w in list(fw):
            hit = [h for h in fh if test(h, w)]
            if len(hit) == 1: pairs.append((hit[0], w)); fh.remove(hit[0]); fw.remove(w)
    take(lambda h, w: bool(set(h.get('codes') or []) & set(w['codes'])))
    take(lambda h, w: norm(h.get('name')) == norm(w['name']))
    take(lambda h, w: _nodark(h.get('name') or '') == _nodark(w['name']))
    take(lambda h, w: bool(norm(w['name'])) and '/' in (h.get('name') or '') and norm(h['name']).startswith(norm(w['name'])))
    return pairs, fw, fh

def size_range(sizes):
    if not sizes: return None
    return sizes[0] if len(sizes) == 1 else f'{sizes[0]} – {sizes[-1]}'

def product_changes(p, m):
    pairs, add, rem = match_colors(p.get('colors') or [], m['colors'])
    ch = dict(colors_added=[c['name'] for c in add], colors_removed=[c.get('name') or '' for c in rem], price=None, sizes=None, name=None, typ=None)
    if m['price_min'] is not None and (p.get('price_min') != m['price_min'] or (p.get('price_max') or p.get('price_min')) != m['price_max']):
        ch['price'] = [[p.get('price_min'), p.get('price_max') or p.get('price_min')], [m['price_min'], m['price_max']]]
    if m['sizes'] and [norm(s) for s in p.get('sizes') or []] != [norm(s) for s in m['sizes']]: ch['sizes'] = [p.get('sizes') or [], m['sizes']]
    if norm(p['name']) != norm(m['name']): ch['name'] = [p['name'], m['name']]
    if m['typ'] and not p.get('typ'): ch['typ'] = m['typ']
    ch['any'] = bool(ch['colors_added'] or ch['colors_removed'] or ch['price'] or ch['sizes'] or ch['name'] or ch['typ'])
    return ch

def _others(code):
    """hotové karty v ostatních katalozích (od nejnovějšího): {název: (katalog, produkt)}"""
    idx = {}
    cats = sorted((c for c in db.list_catalogs() if c['code'] != code and c.get('source') == 'db'), key=lambda c: -(c.get('year_num') or 0))
    for c in cats:
        for p in db.list_products(c['code']): idx.setdefault(norm(p['name']), (c, p))
    return idx

def plan(code, form=None):
    """návrh: co se u kterých karet změní, které modely jsou nové a které karty ve formuláři chybí"""
    form = form or load(code)
    if not form: return None
    prods = db.list_products(code); by_name = {}
    for p in prods: by_name.setdefault(norm(p['name']), p)
    by_id = {p['id']: p for p in prods}; others = _others(code)
    matched, new, used = [], [], set()
    for m in form['models']:
        p = by_name.get(m['key']) or by_id.get(slugify(m['name']))
        if p and p['id'] not in used:
            used.add(p['id']); ch = product_changes(p, m)
            matched.append(dict(key=m['key'], name=m['name'], pid=p['id'], section=p['section'], changes=ch)); continue
        src = others.get(m['key'])
        new.append(dict(key=m['key'], name=m['name'], section=m['section'], typ=m['typ'], price_min=m['price_min'], price_max=m['price_max'], colors=[c['name'] for c in m['colors']],
                        sizes=m['sizes'], source=dict(catalog=src[0]['code'], label=catalogs.catalog_label(src[0]), id=src[1]['id']) if src else None, suggest=None))
    in_form = {m['section'] for m in form['models']} | {x['section'] for x in matched}
    missing = [p for p in prods if p['id'] not in used and p['section'] in in_form]   # sekce, kterou formulář vůbec neobsahuje (např. jen oblečení), se nevyřazuje
    skipped = collections.Counter(p['section'] for p in prods if p['id'] not in used and p['section'] not in in_form)
    rank = {m['key']: i for i, m in enumerate(form['models'])}; order = form_order(prods, {x['pid']: rank[x['key']] for x in matched})
    # přejmenované modely: nový název ve formuláři je hodně podobný kartě, která ve formuláři chybí
    free = {p['id']: norm(p['name']) for p in missing}
    for n in new:
        best = max(free.items(), key=lambda kv: difflib.SequenceMatcher(None, n['key'], kv[1]).ratio(), default=None)
        if best and difflib.SequenceMatcher(None, n['key'], best[1]).ratio() >= 0.8 and by_id[best[0]]['section'] == n['section']: n['suggest'] = best[0]; free.pop(best[0])
    return dict(files=form['files'], rows=form['rows'], n_models=len(form['models']), warnings=form.get('warnings') or [], matched=matched, new=new,
                skipped=dict(skipped), order=dict(moved=order['moved'], splits=order['splits']),
                missing=[dict(pid=p['id'], name=p['name'], section=p['section'], serie=p.get('serie') or '', n_colors=len(p.get('colors') or [])) for p in missing])

def form_order(prods, rank):
    """pořadí produktů v sekcích přesně podle formuláře (rank = {id karty: pořadí modelu ve formuláři});
    karta, která ve formuláři není, zůstane za svým dosavadním předchůdcem"""
    by_sec = collections.OrderedDict(); moved = 0; splits = []
    for p in prods: by_sec.setdefault(p['section'], []).append(p)
    ids = {}
    for sec, cur in by_sec.items():
        if not any(p['id'] in rank for p in cur): continue
        key = {}; last = -1
        for j, p in enumerate(cur):
            if p['id'] in rank: last = rank[p['id']]; key[p['id']] = (last, 0, 0)
            else: key[p['id']] = (last, 1, j)
        new = sorted(cur, key=lambda p: key[p['id']]); ids[sec] = [p['id'] for p in new]
        moved += sum(1 for a, b in zip(cur, new) if a['id'] != b['id'])
        runs = []
        for p in new:
            if runs and runs[-1][0] == (p.get('serie') or ''): runs[-1][1].append(p['name'])
            else: runs.append([p.get('serie') or '', [p['name']]])
        # krátký blok (do 3 karet) uprostřed jiné série nebo oddělený od zbytku své série: v katalogu z něj vznikne další nadpis série
        for i in range(1, len(runs)):
            lone = sum(1 for r in runs if r[0] == runs[i][0]) > 1 or (i + 1 < len(runs) and runs[i - 1][0] == runs[i + 1][0])
            if len(runs[i][1]) <= 3 and lone: splits.append(dict(section=sec, serie=runs[i][0], after=runs[i - 1][0], names=runs[i][1]))
    return dict(ids=ids, moved=moved, splits=splits)

# ---------- provedení ----------
def _photo_index(code):
    """fotky a rozkresy barev z ostatních katalogů: {(model, barva): záznam barvy} – nová barva tak dostane hotové obrázky, pokud už někde jsou"""
    idx = {}
    for c in db.list_catalogs():
        if c['code'] == code or c.get('source') != 'db': continue
        for p in db.list_products(c['code']):
            for col in p.get('colors') or []:
                if col.get('front') or col.get('art'): idx.setdefault((norm(p['name']), norm(col.get('name'))), col)
    return idx

def update_product(p, m, opts, photos):
    pairs, add, rem = match_colors(p.get('colors') or [], m['colors'])
    for h, w in pairs:
        h['codes'] = w['codes']
        if opts.get('rename_colors'): h['name'] = w['name']
    if opts.get('remove_colors', True): p['colors'] = [c for c in p['colors'] if not any(c is r for r in rem)]
    if opts.get('add_colors', True):
        for w in add:
            src = photos.get((m['key'], norm(w['name']))) or {}
            p['colors'].append(dict(name=w['name'], codes=w['codes'], front=src.get('front'), back=src.get('back'), art=src.get('art'), generic=False))
    if opts.get('prices', True) and m['price_min'] is not None: p['price_min'] = m['price_min']; p['price_max'] = m['price_max']
    if opts.get('sizes', True) and m['sizes'] and [norm(s) for s in p.get('sizes') or []] != [norm(s) for s in m['sizes']]:
        p['sizes'] = m['sizes']
        if SCHEMAS[p['section']]['gender']: p.setdefault('specs', {})['size'] = size_range(m['sizes'])
    if opts.get('rename', True) and (norm(p.get('name')) != m['key'] or not p.get('name')): p['name'] = m['name']
    if m['typ'] and not p.get('typ'): p['typ'] = m['typ']
    if m.get('sk'): p['sk'] = m['sk']
    return p

def apply(code, body):
    """body: opts{prices,add_colors,remove_colors,sizes,rename_colors,order}, skip[klíče modelů], new{klíč: 'create'|'copy'|'pair:<id>'|'skip'}, remove[id karet]"""
    form = load(code)
    if not form: raise ValueError('U katalogu není nahraný formulář')
    pl = plan(code, form); opts = body.get('opts') or {}; skip = set(body.get('skip') or []); choice = body.get('new') or {}
    models = {m['key']: m for m in form['models']}; photos = _photo_index(code); res = collections.Counter()
    serie_of = {}
    for p in db.list_products(code): serie_of.setdefault((p['section'], p.get('typ')), p.get('serie') or '')
    for x in pl['matched']:
        if x['key'] in skip or not x['changes']['any']: continue
        p = update_product(db.get_product(code, x['pid']), models[x['key']], opts, photos); db.save_product(p); res['updated'] += 1
    for n in pl['new']:
        m = models[n['key']]; act = choice.get(n['key']) or ('pair:' + n['suggest'] if n['suggest'] else 'copy' if n['source'] else 'create')
        if act == 'skip': continue
        if act.startswith('pair:'):
            p = db.get_product(code, act[5:])
            if not p: continue
            db.save_product(update_product(p, m, dict(opts, rename=True), photos)); res['paired'] += 1; continue
        if act == 'copy' and n['source']:
            p = db.get_product(n['source']['catalog'], n['source']['id']); p.pop('prev_id', None); res['copied'] += 1
            if p['section'] not in {s['key'] for s in db.list_sections(code)}: p['section'] = m['section']
        else:
            p = empty_product(m['section']); p['serie'] = serie_of.get((m['section'], m['typ']), ''); p['typ'] = m['typ']; res['created'] += 1
        p['season'] = code; p['new'] = True; pid = base = slugify(m['name']) or 'produkt'; i = 2
        while db.get_product(code, pid): pid = f'{base}_{i}'; i += 1
        p['id'] = pid; p['sort'] = db.next_sort(code, p['section'])
        db.save_product(update_product(p, m, dict(opts, add_colors=True, remove_colors=True, prices=True, sizes=True, rename=True), photos))
    paired = {choice.get(n['key'], '')[5:] for n in pl['new'] if (choice.get(n['key']) or '').startswith('pair:')} | {n['suggest'] for n in pl['new'] if n['suggest'] and n['key'] not in choice}
    for pid in body.get('remove') or []:
        if pid in paired or not any(x['pid'] == pid for x in pl['missing']): continue
        db.delete_product(code, pid); res['removed'] += 1
    if opts.get('order', True):
        pl2 = plan(code, form); rank = {m['key']: i for i, m in enumerate(form['models'])}
        o = form_order(db.list_products(code), {x['pid']: rank[x['key']] for x in pl2['matched']})
        for sec, ids in o['ids'].items(): db.renumber(code, sec, ids)
        res['moved'] = o['moved']
    return dict(res)
