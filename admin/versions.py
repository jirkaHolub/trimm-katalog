"""Verze katalogu: záloha je snímek produktů, sekcí (včetně technických stran) a nastavení titulní strany. Ke každé záloze se dá vrátit."""
import json, time, zlib, base64, hashlib, secrets
import db

CAT_KEYS = ('title', 'year', 'doc_title', 'hero', 'prev', 'note')   # stav (uzavřeno) a hotové soubory se nevrací
KEEP_AUTO = 10   # kolik automatických záloh se u katalogu drží

def _hash(o): return hashlib.md5(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:10]

def state(code):
    cat = db.get_catalog(code); prods = db.list_products(code)
    for p in prods: p.pop('season', None)
    return dict(catalog={k: cat.get(k) or '' for k in CAT_KEYS}, sections=db.list_sections(code), products=prods)

def fingerprint(st):
    return dict(n=len(st['products']), colors=sum(len(p.get('colors') or []) for p in st['products']),
                cat=_hash([st['catalog'], st['sections']]), h={p['id']: [_hash(p), p['name']] for p in st['products']})

def _same(a, b): return a.get('cat') == b.get('cat') and a.get('h') == b.get('h')

def create(code, label='', author='', auto=False):
    """Zazálohuje současný stav. Automatická záloha se nedělá, pokud se od poslední zálohy nic nezměnilo."""
    st = state(code); meta = fingerprint(st); old = db.list_backups(code)
    if auto and old and _same(old[0]['meta'], meta): return None
    b = dict(id=secrets.token_hex(6), code=code, created=time.time(), label=(label or '').strip()[:120], author=author or '', auto=auto, meta=meta,
             data=base64.b64encode(zlib.compress(json.dumps(st, ensure_ascii=False).encode('utf-8'), 9)).decode('ascii'))
    db.save_backup(b)
    if auto:
        for x in [x for x in old if x['auto']][KEEP_AUTO - 1:]: db.delete_backup(code, x['id'])
    return b['id']

def load(code, bid):
    b = db.get_backup(bid)
    if not b or b['code'] != code: raise ValueError('Záloha neexistuje')
    b['state'] = json.loads(zlib.decompress(base64.b64decode(b.pop('data'))).decode('utf-8')); return b

def changes(meta, cur):
    """co se v katalogu změnilo od zálohy (jména modelů)"""
    a, b = meta.get('h') or {}, cur['h']
    return dict(changed=[b[i][1] for i in b if i in a and a[i][0] != b[i][0]], added=[b[i][1] for i in b if i not in a],
                removed=[a[i][1] for i in a if i not in b], settings=meta.get('cat') != cur['cat'])

def listing(code):
    cur = fingerprint(state(code))
    return [dict(id=b['id'], created=b['created'], label=b['label'], author=b['author'], auto=b['auto'], n=b['meta'].get('n'), colors=b['meta'].get('colors'),
                 same=_same(b['meta'], cur), diff=changes(b['meta'], cur)) for b in db.list_backups(code)]

def name(b): return b['label'] if b['label'] and not b['auto'] else 'z ' + time.strftime('%d.%m.%Y %H:%M', time.localtime(b['created']))

def restore(code, bid, author=''):
    """Vrátí katalog k záloze. Současný stav se před tím sám zazálohuje, takže návrat jde vzít zpět."""
    b = load(code, bid); st = b['state']
    create(code, 'Před návratem k verzi ' + (name(b) if b['auto'] or not b['label'] else f'„{name(b)}“'), author, auto=True)
    db.set_products(code, st['products'], db.is_linked(code), overwrite=True, sections=st['sections'])   # u společných karet se vrátí i karty
    cat = db.get_catalog(code)
    for k in CAT_KEYS: cat[k] = st['catalog'].get(k) or ''
    if cat['prev'] and (cat['prev'] == code or not db.get_catalog(cat['prev'])): cat['prev'] = ''   # loňský katalog mezitím někdo smazal
    db.save_catalog(cat)
    return dict(ok=True, products=len(st['products']))
