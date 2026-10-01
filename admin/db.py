"""SQLite úložiště: katalogy (sezóny), produkty jako JSON záznam + pár sloupců pro řazení a filtrování, loňské karty z PDF."""
import sqlite3, json, os, time
HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, 'katalog.sqlite')
_ready = False

def connect():
    global _ready
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    if _ready: return con
    con.execute('''CREATE TABLE IF NOT EXISTS products(
        id TEXT NOT NULL, season TEXT NOT NULL, section TEXT NOT NULL, serie TEXT, sort REAL NOT NULL DEFAULT 0,
        name TEXT NOT NULL, data TEXT NOT NULL, updated_at REAL, PRIMARY KEY(season, id))''')
    # starší databáze měla klíč jen podle id – produkt se stejným id pak nemohl být ve dvou katalozích
    if [r['name'] for r in con.execute('PRAGMA table_info(products)') if r['pk']] == ['id']:
        con.execute('ALTER TABLE products RENAME TO products_old')
        con.execute('''CREATE TABLE products(
            id TEXT NOT NULL, season TEXT NOT NULL, section TEXT NOT NULL, serie TEXT, sort REAL NOT NULL DEFAULT 0,
            name TEXT NOT NULL, data TEXT NOT NULL, updated_at REAL, PRIMARY KEY(season, id))''')
        con.execute('INSERT INTO products SELECT id,season,section,serie,sort,name,data,updated_at FROM products_old')
        con.execute('DROP TABLE products_old'); con.commit()
    con.execute('''CREATE TABLE IF NOT EXISTS sections(
        key TEXT, season TEXT, title TEXT, cz TEXT, color TEXT, pages TEXT, sort INTEGER, PRIMARY KEY(key, season))''')
    con.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS catalogs(code TEXT PRIMARY KEY, data TEXT NOT NULL, created REAL)')
    # karty z katalogů, které existují jen jako PDF (výřez karty + vytěžený text)
    con.execute('''CREATE TABLE IF NOT EXISTS prev_cards(
        season TEXT NOT NULL, key TEXT NOT NULL, name TEXT NOT NULL, section TEXT, page INTEGER, image TEXT, data TEXT, PRIMARY KEY(season, key))''')
    _ready = True
    return con

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
    for t, col in (('products', 'season'), ('sections', 'season'), ('prev_cards', 'season'), ('catalogs', 'code')): con.execute(f'DELETE FROM {t} WHERE {col}=?', (code,))
    con.execute('DELETE FROM settings WHERE key=?', (f'form:{code}',))
    con.commit(); con.close()

# ---------- produkty ----------
def row_to_product(r):
    d = json.loads(r['data'])
    d['id'] = r['id']; d['season'] = r['season']; d['section'] = r['section']; d['serie'] = r['serie']; d['sort'] = r['sort']; d['name'] = r['name']
    return d

def list_products(season, section=None):
    con = connect()
    q = 'SELECT * FROM products WHERE season=?' + (' AND section=?' if section else '')
    rows = con.execute(q, (season, section) if section else (season,)).fetchall()
    order = {r['key']: r['sort'] for r in con.execute('SELECT key, sort FROM sections WHERE season=?', (season,))}
    con.close()
    return sorted((row_to_product(r) for r in rows), key=lambda p: (order.get(p['section'], 99), p['sort'], p['name']))

def get_product(season, pid):
    con = connect(); r = con.execute('SELECT * FROM products WHERE season=? AND id=?', (season, pid)).fetchone(); con.close()
    return row_to_product(r) if r else None

def save_product(p):
    con = connect()
    data = {k: v for k, v in p.items() if k not in ('id', 'season', 'section', 'serie', 'sort', 'name')}
    con.execute('INSERT INTO products(id,season,section,serie,sort,name,data,updated_at) VALUES(?,?,?,?,?,?,?,?) '
                'ON CONFLICT(season,id) DO UPDATE SET section=excluded.section, serie=excluded.serie, sort=excluded.sort, '
                'name=excluded.name, data=excluded.data, updated_at=excluded.updated_at',
                (p['id'], p['season'], p['section'], p.get('serie') or '', float(p.get('sort') or 0), p['name'], json.dumps(data, ensure_ascii=False), time.time()))
    con.commit(); con.close()

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
    return [dict(key=r['key'], title=r['title'], cz=r['cz'], color=r['color'], pages=json.loads(r['pages'] or '[]'), sort=r['sort']) for r in rows]

def save_section(season, s):
    con = connect()
    con.execute('INSERT INTO sections(key,season,title,cz,color,pages,sort) VALUES(?,?,?,?,?,?,?) ON CONFLICT(key,season) DO UPDATE SET '
                'title=excluded.title, cz=excluded.cz, color=excluded.color, pages=excluded.pages, sort=excluded.sort',
                (s['key'], season, s['title'], s['cz'], s['color'], json.dumps(s.get('pages') or []), int(s.get('sort') or 0)))
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
