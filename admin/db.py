"""SQLite úložiště: katalogy (sezóny), společné karty produktů, zařazení karet do katalogů, loňské karty z PDF.
Karta produktu (tabulka cards) je jedna pro všechny katalogy. Katalog se společnými kartami (v záznamu linked=True) má v products jen zařazení
karty (sekce, série, pořadí, novinka); uzavřený katalog má v products vlastní úplné kopie, aby se zpětně neměnil."""
import sqlite3, json, os, time, contextlib
HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, 'katalog.sqlite')
_ready = False

PG_URL = os.environ.get('DATABASE_URL')   # online (Vercel + Neon Postgres); bez něj lokální SQLite soubor

class _PG:
    """Postgres za stejným rozhraním, jaké kód používá u sqlite3: execute s otazníky, commit, close. Jedno sdílené spojení na proces."""
    conn = None
    def _open(self):
        import psycopg
        from psycopg.rows import dict_row
        _PG.conn = psycopg.connect(PG_URL, autocommit=True, row_factory=dict_row)
    def execute(self, sql, params=()):
        if sql.lstrip().upper().startswith('CREATE TABLE'): sql = sql.replace(' REAL', ' DOUBLE PRECISION')
        sql = sql.replace('?', '%s')
        for attempt in (0, 1):
            try:
                if _PG.conn is None or _PG.conn.closed: self._open()
                return _PG.conn.execute(sql, params)
            except Exception as e:
                import psycopg
                if attempt or not isinstance(e, (psycopg.OperationalError, psycopg.InterfaceError)): raise
                _PG.conn = None   # spojení mezitím spadlo (uspaná databáze) – zkusit jednou znovu
    def commit(self): pass
    def close(self): pass

SCHEMA = [
    '''CREATE TABLE IF NOT EXISTS products(
        id TEXT NOT NULL, season TEXT NOT NULL, section TEXT NOT NULL, serie TEXT, sort REAL NOT NULL DEFAULT 0,
        name TEXT NOT NULL, data TEXT NOT NULL, updated_at REAL, PRIMARY KEY(season, id))''',
    '''CREATE TABLE IF NOT EXISTS sections(
        key TEXT, season TEXT, title TEXT, cz TEXT, color TEXT, pages TEXT, sort INTEGER, PRIMARY KEY(key, season))''',
    'CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)',
    'CREATE TABLE IF NOT EXISTS catalogs(code TEXT PRIMARY KEY, data TEXT NOT NULL, created REAL)',
    # karty z katalogů, které existují jen jako PDF (výřez karty + vytěžený text)
    '''CREATE TABLE IF NOT EXISTS prev_cards(
        season TEXT NOT NULL, key TEXT NOT NULL, name TEXT NOT NULL, section TEXT, page INTEGER, image TEXT, data TEXT, PRIMARY KEY(season, key))''',
    # zálohy (verze) katalogu: meta = počty a otisky produktů pro rychlé porovnání, data = zabalený snímek
    # podněty uživatelů k aplikaci; image = přiložený obrázek jako data URL
    'CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY, created REAL, author TEXT, kind TEXT, text TEXT, page TEXT, meta TEXT, image TEXT, status TEXT, reply TEXT)',
    'CREATE TABLE IF NOT EXISTS cards(id TEXT PRIMARY KEY, name TEXT NOT NULL, data TEXT NOT NULL, updated_at REAL)',
    'CREATE TABLE IF NOT EXISTS backups(id TEXT PRIMARY KEY, code TEXT NOT NULL, created REAL, label TEXT, author TEXT, auto INTEGER, meta TEXT, data TEXT)',
]

def connect():
    global _ready
    if PG_URL:
        con = _PG()
        if not _ready:
            for q in SCHEMA: con.execute(q)
            _ready = True
        return con
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    if _ready: return con
    # starší databáze měla klíč jen podle id – produkt se stejným id pak nemohl být ve dvou katalozích
    if [r['name'] for r in con.execute('PRAGMA table_info(products)') if r['pk']] == ['id']:
        con.execute('ALTER TABLE products RENAME TO products_old')
        con.execute(SCHEMA[0].replace('IF NOT EXISTS ', ''))
        con.execute('INSERT INTO products SELECT id,season,section,serie,sort,name,data,updated_at FROM products_old')
        con.execute('DROP TABLE products_old'); con.commit()
    for q in SCHEMA: con.execute(q)
    _ready = True
    return con

@contextlib.contextmanager
def transaction():
    """Samostatné spojení pro zápisy, které se musí provést všechny, nebo žádný. Vrací funkci execute(sql, params)."""
    connect().close()
    if PG_URL:
        import psycopg
        with psycopg.connect(PG_URL) as c: yield lambda sql, params=(): c.execute(sql.replace('?', '%s'), params)
    else:
        con = sqlite3.connect(DB_PATH)
        try: yield con.execute; con.commit()
        finally: con.close()

# ---------- katalogy ----------
def row_to_catalog(r):
    d = json.loads(r['data']); d['code'] = r['code']; d['created'] = r['created']; return d

def list_catalogs():
    con = connect(); rows = con.execute('SELECT * FROM catalogs ORDER BY created DESC').fetchall(); con.close()
    return [row_to_catalog(r) for r in rows]

def get_catalog(code):
    con = connect(); r = con.execute('SELECT * FROM catalogs WHERE code=?', (code,)).fetchone(); con.close()
    return row_to_catalog(r) if r else None

def save_catalog(c):
    con = connect(); data = {k: v for k, v in c.items() if k not in ('code', 'created')}
    con.execute('INSERT INTO catalogs(code,data,created) VALUES(?,?,?) ON CONFLICT(code) DO UPDATE SET data=excluded.data',
                (c['code'], json.dumps(data, ensure_ascii=False), c.get('created') or time.time()))
    con.commit(); con.close()

def delete_catalog(code):
    con = connect()
    for t, col in (('products', 'season'), ('sections', 'season'), ('prev_cards', 'season'), ('backups', 'code'), ('catalogs', 'code')): con.execute(f'DELETE FROM {t} WHERE {col}=?', (code,))
    con.execute('DELETE FROM settings WHERE key=?', (f'form:{code}',))
    con.commit(); con.close()

# ---------- produkty ----------
PER_CATALOG = ('new', 'prev_id')   # co si katalog se společnými kartami drží u zařazení karty sám (vedle sekce, série a pořadí)
_COLS = ('id', 'season', 'section', 'serie', 'sort', 'name')
_SEL = 'SELECT p.*, c.name AS cname, c.data AS cdata FROM products p LEFT JOIN cards c ON c.id=p.id'

def _linked(con, season):
    r = con.execute('SELECT data FROM catalogs WHERE code=?', (season,)).fetchone()
    return bool(r and json.loads(r['data']).get('linked'))

def is_linked(season):
    con = connect(); x = _linked(con, season); con.close(); return x

def row_to_product(r, linked=False):
    d = json.loads(r['data'])
    if linked and r['cdata']: d = dict(json.loads(r['cdata']), **d); d.setdefault('new', False)
    d['id'] = r['id']; d['season'] = r['season']; d['section'] = r['section']; d['serie'] = r['serie']; d['sort'] = r['sort']
    d['name'] = r['cname'] if linked and r['cname'] else r['name']
    return d

def list_products(season, section=None):
    con = connect(); linked = _linked(con, season)
    q = _SEL + ' WHERE p.season=?' + (' AND p.section=?' if section else '')
    rows = con.execute(q, (season, section) if section else (season,)).fetchall()
    order = {r['key']: r['sort'] for r in con.execute('SELECT key, sort FROM sections WHERE season=?', (season,))}
    con.close()
    return sorted((row_to_product(r, linked) for r in rows), key=lambda p: (order.get(p['section'], 99), p['sort'], p['name']))

def get_product(season, pid):
    con = connect(); linked = _linked(con, season); r = con.execute(_SEL + ' WHERE p.season=? AND p.id=?', (season, pid)).fetchone(); con.close()
    return row_to_product(r, linked) if r else None

def _product_row(p):
    data = {k: v for k, v in p.items() if k not in _COLS}
    return (p['id'], p['season'], p['section'], p.get('serie') or '', float(p.get('sort') or 0), p['name'], json.dumps(data, ensure_ascii=False), time.time())

def _link(p): return dict({k: p.get(k) for k in _COLS}, **{k: p[k] for k in PER_CATALOG if p.get(k)})

def card_data(p):
    """obsah karty společný všem katalogům (sekce a série v něm zůstávají jako výchozí zařazení)"""
    return {k: v for k, v in p.items() if k not in ('id', 'name', 'season', 'sort') + PER_CATALOG}

def _put_card(ex, p, keep=False):
    ex('INSERT INTO cards(id,name,data,updated_at) VALUES(?,?,?,?) ON CONFLICT(id) DO ' +
       ('NOTHING' if keep else 'UPDATE SET name=excluded.name, data=excluded.data, updated_at=excluded.updated_at'),
       (p['id'], p['name'], json.dumps(card_data(p), ensure_ascii=False), time.time()))

_UPSERT = ('INSERT INTO products(id,season,section,serie,sort,name,data,updated_at) VALUES(?,?,?,?,?,?,?,?) '
           'ON CONFLICT(season,id) DO UPDATE SET section=excluded.section, serie=excluded.serie, sort=excluded.sort, '
           'name=excluded.name, data=excluded.data, updated_at=excluded.updated_at')

def save_product(p):
    """V katalogu se společnými kartami se obsah uloží do karty (změna se projeví ve všech takových katalozích) a do katalogu jen zařazení."""
    con = connect()
    if _linked(con, p['season']): _put_card(con.execute, p); p = _link(p)
    con.execute(_UPSERT, _product_row(p))
    con.commit(); con.close()

def set_products(season, products, linked, overwrite=False, sections=None):
    """Nahradí obsah katalogu naráz (nebo vůbec) a nastaví, zda používá společné karty. overwrite = přepsat i existující karty; sections = nahradit i sekce."""
    cat = get_catalog(season); data = {k: v for k, v in cat.items() if k not in ('code', 'created')}; data['linked'] = bool(linked)
    with transaction() as ex:
        ex('UPDATE catalogs SET data=? WHERE code=?', (json.dumps(data, ensure_ascii=False), season))
        ex('DELETE FROM products WHERE season=?', (season,))
        if sections is not None:
            ex('DELETE FROM sections WHERE season=?', (season,))
            for s in sections:
                ex('INSERT INTO sections(key,season,title,cz,color,pages,sort) VALUES(?,?,?,?,?,?,?)',
                   (s['key'], season, s['title'], s['cz'], s['color'], _pages_dump(s), int(s.get('sort') or 0)))
        for p in products:
            p = dict(p, season=season)
            if linked: _put_card(ex, p, keep=not overwrite); p = _link(p)
            ex(_UPSERT, _product_row(p))

def free_id(season, base):
    """id, které v katalogu ještě není – a u katalogu se společnými kartami ani mezi kartami"""
    con = connect(); linked = _linked(con, season); pid = base; i = 2
    while con.execute('SELECT 1 x FROM products WHERE season=? AND id=?', (season, pid)).fetchone() or (linked and con.execute('SELECT 1 x FROM cards WHERE id=?', (pid,)).fetchone()):
        pid = f'{base}_{i}'; i += 1
    con.close(); return pid

# ---------- společné karty ----------
def _row_to_card(r): return dict(json.loads(r['data']), id=r['id'], name=r['name'])

def list_cards():
    con = connect(); rows = con.execute('SELECT * FROM cards').fetchall(); con.close()
    return sorted((_row_to_card(r) for r in rows), key=lambda c: c['name'])

def get_card(cid):
    con = connect(); r = con.execute('SELECT * FROM cards WHERE id=?', (cid,)).fetchone(); con.close()
    return _row_to_card(r) if r else None

def add_cards(products):
    """založí karty, které ještě neexistují (existující nechá být)"""
    with transaction() as ex:
        for p in products: _put_card(ex, p, keep=True)

def delete_card(cid):
    con = connect(); con.execute('DELETE FROM cards WHERE id=?', (cid,)); con.commit(); con.close()

def card_usage():
    """{id: [kódy katalogů, ve kterých produkt s tímto id je]}"""
    con = connect(); rows = con.execute('SELECT id, season FROM products').fetchall(); con.close(); use = {}
    for r in rows: use.setdefault(r['id'], []).append(r['season'])
    return use

def delete_product(season, pid):
    con = connect(); con.execute('DELETE FROM products WHERE season=? AND id=?', (season, pid)); con.commit(); con.close()

def count_products(season):
    con = connect(); n = con.execute('SELECT COUNT(*) n FROM products WHERE season=?', (season,)).fetchone()['n']; con.close(); return n

def next_sort(season, section):
    con = connect(); r = con.execute('SELECT MAX(sort) m FROM products WHERE season=? AND section=?', (season, section)).fetchone(); con.close()
    return (r['m'] or 0) + 1

def renumber(season, section, ids):
    """Nastaví pořadí produktů v sekci podle zadaného seznamu id."""
    con = connect()
    for i, pid in enumerate(ids):
        con.execute('UPDATE products SET sort=? WHERE id=? AND season=? AND section=?', (float(i + 1), pid, season, section))
    con.commit(); con.close()

# ---------- sekce ----------
def list_sections(season):
    con = connect(); rows = con.execute('SELECT * FROM sections WHERE season=? ORDER BY sort', (season,)).fetchall(); con.close()
    return [dict(key=r['key'], title=r['title'], cz=r['cz'], color=r['color'], sort=r['sort'], **_pages_load(r['pages'])) for r in rows]

def _pages_load(raw):
    """technické strany: list = jen české; dict = {cs: [...], en: [...]} -> pages (cs) + pages_i18n (ostatní jazyky)"""
    v = json.loads(raw or '[]')
    if isinstance(v, dict): return dict(pages=v.get('cs') or [], pages_i18n={k: p for k, p in v.items() if k != 'cs' and p})
    return dict(pages=v or [], pages_i18n={})
def _pages_dump(s):
    extra = {k: p for k, p in (s.get('pages_i18n') or {}).items() if p}
    return json.dumps(dict(cs=s.get('pages') or [], **extra) if extra else (s.get('pages') or []))

def save_section(season, s):
    con = connect()
    con.execute('INSERT INTO sections(key,season,title,cz,color,pages,sort) VALUES(?,?,?,?,?,?,?) ON CONFLICT(key,season) DO UPDATE SET '
                'title=excluded.title, cz=excluded.cz, color=excluded.color, pages=excluded.pages, sort=excluded.sort',
                (s['key'], season, s['title'], s['cz'], s['color'], _pages_dump(s), int(s.get('sort') or 0)))
    con.commit(); con.close()

def delete_section(season, key):
    con = connect(); con.execute('DELETE FROM sections WHERE season=? AND key=?', (season, key)); con.commit(); con.close()

# ---------- loňské karty z PDF ----------
def row_to_card(r):
    d = json.loads(r['data'] or '{}'); d.update(key=r['key'], season=r['season'], name=r['name'], section=r['section'], page=r['page'], image=r['image']); return d

def list_prev_cards(season):
    con = connect(); rows = con.execute('SELECT * FROM prev_cards WHERE season=? ORDER BY page, key', (season,)).fetchall(); con.close()
    return [row_to_card(r) for r in rows]

def save_prev_card(c):
    con = connect(); data = {k: v for k, v in c.items() if k not in ('key', 'season', 'name', 'section', 'page', 'image')}
    con.execute('INSERT INTO prev_cards(season,key,name,section,page,image,data) VALUES(?,?,?,?,?,?,?) ON CONFLICT(season,key) DO UPDATE SET '
                'name=excluded.name, section=excluded.section, page=excluded.page, image=excluded.image, data=excluded.data',
                (c['season'], c['key'], c['name'], c.get('section'), c.get('page'), c.get('image'), json.dumps(data, ensure_ascii=False)))
    con.commit(); con.close()

def get_setting(key, default=None):
    con = connect(); r = con.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone(); con.close()
    return json.loads(r['value']) if r else default

def set_setting(key, value):
    con = connect(); con.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value, ensure_ascii=False)))
    con.commit(); con.close()

# ---------- zálohy (verze) katalogu ----------
def list_backups(code):
    con = connect(); rows = con.execute('SELECT id,code,created,label,author,auto,meta FROM backups WHERE code=? ORDER BY created DESC', (code,)).fetchall(); con.close()
    return [dict(id=r['id'], code=r['code'], created=r['created'], label=r['label'], author=r['author'], auto=bool(r['auto']), meta=json.loads(r['meta'] or '{}')) for r in rows]

def get_backup(bid):
    con = connect(); r = con.execute('SELECT * FROM backups WHERE id=?', (bid,)).fetchone(); con.close()
    return dict(id=r['id'], code=r['code'], created=r['created'], label=r['label'], author=r['author'], auto=bool(r['auto']), data=r['data']) if r else None

def save_backup(b):
    con = connect()
    con.execute('INSERT INTO backups(id,code,created,label,author,auto,meta,data) VALUES(?,?,?,?,?,?,?,?)',
                (b['id'], b['code'], b['created'], b['label'], b['author'], int(b['auto']), json.dumps(b['meta'], ensure_ascii=False), b['data']))
    con.commit(); con.close()

def rename_backup(code, bid, label):
    con = connect(); con.execute('UPDATE backups SET label=?, auto=0 WHERE id=? AND code=?', (label, bid, code)); con.commit(); con.close()

def delete_backup(code, bid):
    con = connect(); con.execute('DELETE FROM backups WHERE id=? AND code=?', (bid, code)); con.commit(); con.close()

# ---------- podněty uživatelů ----------
def list_feedback(author=None):
    con = connect(); q = "SELECT id,created,author,kind,text,page,meta,status,reply, CASE WHEN image<>'' THEN 1 ELSE 0 END AS has_image FROM feedback"
    rows = con.execute(q + (' WHERE author=?' if author is not None else '') + ' ORDER BY created DESC', (author,) if author is not None else ()).fetchall(); con.close()
    return [dict(id=r['id'], created=r['created'], author=r['author'], kind=r['kind'], text=r['text'], page=r['page'], meta=json.loads(r['meta'] or '{}'),
                 status=r['status'], reply=r['reply'] or '', has_image=bool(r['has_image'])) for r in rows]

def get_feedback(fid):
    con = connect(); r = con.execute('SELECT id,author,image FROM feedback WHERE id=?', (fid,)).fetchone(); con.close()
    return dict(id=r['id'], author=r['author'], image=r['image']) if r else None

def add_feedback(f):
    con = connect()
    con.execute('INSERT INTO feedback(id,created,author,kind,text,page,meta,image,status,reply) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (f['id'], time.time(), f['author'], f['kind'], f['text'], f['page'], json.dumps(f.get('meta') or {}, ensure_ascii=False), f.get('image') or '', 'new', ''))
    con.commit(); con.close()

def update_feedback(fid, **kw):
    con = connect()
    for k in ('status', 'reply'):
        if k in kw: con.execute(f'UPDATE feedback SET {k}=? WHERE id=?', (kw[k], fid))
    con.commit(); con.close()

def delete_feedback(fid):
    con = connect(); con.execute('DELETE FROM feedback WHERE id=?', (fid,)); con.commit(); con.close()
