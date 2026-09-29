"""SQLite úložiště: produkty jako JSON záznam + pár sloupců pro řazení a filtrování."""
import sqlite3, json, os, time
HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, 'katalog.sqlite')

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute('''CREATE TABLE IF NOT EXISTS products(
        id TEXT PRIMARY KEY, season TEXT NOT NULL, section TEXT NOT NULL, serie TEXT, sort REAL NOT NULL DEFAULT 0,
        name TEXT NOT NULL, data TEXT NOT NULL, updated_at REAL)''')
    con.execute('''CREATE TABLE IF NOT EXISTS sections(
        key TEXT, season TEXT, title TEXT, cz TEXT, color TEXT, pages TEXT, sort INTEGER, PRIMARY KEY(key, season))''')
    con.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)')
    return con

def row_to_product(r):
    d = json.loads(r['data'])
    d['id'] = r['id']; d['season'] = r['season']; d['section'] = r['section']; d['serie'] = r['serie']; d['sort'] = r['sort']; d['name'] = r['name']
    return d

def list_products(season, section=None):
    con = connect()
    order = "CASE section WHEN 'tents' THEN 0 WHEN 'sleeping' THEN 1 WHEN 'mattress' THEN 2 WHEN 'backpacks' THEN 3 WHEN 'sportswear' THEN 4 ELSE 9 END"
    q = 'SELECT * FROM products WHERE season=?' + (' AND section=?' if section else '') + f' ORDER BY {order}, sort, name'
    rows = con.execute(q, (season, section) if section else (season,)).fetchall()
    con.close()
    return [row_to_product(r) for r in rows]

def get_product(pid):
    con = connect(); r = con.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone(); con.close()
    return row_to_product(r) if r else None

def save_product(p):
    con = connect()
    data = {k: v for k, v in p.items() if k not in ('id', 'season', 'section', 'serie', 'sort', 'name')}
    con.execute('INSERT INTO products(id,season,section,serie,sort,name,data,updated_at) VALUES(?,?,?,?,?,?,?,?) '
                'ON CONFLICT(id) DO UPDATE SET season=excluded.season, section=excluded.section, serie=excluded.serie, sort=excluded.sort, '
                'name=excluded.name, data=excluded.data, updated_at=excluded.updated_at',
                (p['id'], p['season'], p['section'], p.get('serie') or '', float(p.get('sort') or 0), p['name'], json.dumps(data, ensure_ascii=False), time.time()))
    con.commit(); con.close()

def delete_product(pid):
    con = connect(); con.execute('DELETE FROM products WHERE id=?', (pid,)); con.commit(); con.close()

def next_sort(season, section):
    con = connect(); r = con.execute('SELECT MAX(sort) m FROM products WHERE season=? AND section=?', (season, section)).fetchone(); con.close()
    return (r['m'] or 0) + 1

def renumber(season, section, ids):
    """Nastaví pořadí produktů v sekci podle zadaného seznamu id."""
    con = connect()
    for i, pid in enumerate(ids):
        con.execute('UPDATE products SET sort=? WHERE id=? AND season=? AND section=?', (float(i + 1), pid, season, section))
    con.commit(); con.close()

def list_sections(season):
    con = connect(); rows = con.execute('SELECT * FROM sections WHERE season=? ORDER BY sort', (season,)).fetchall(); con.close()
    return [dict(key=r['key'], title=r['title'], cz=r['cz'], color=r['color'], pages=json.loads(r['pages'] or '[]'), sort=r['sort']) for r in rows]

def save_section(season, s):
    con = connect()
    con.execute('INSERT INTO sections(key,season,title,cz,color,pages,sort) VALUES(?,?,?,?,?,?,?) ON CONFLICT(key,season) DO UPDATE SET '
                'title=excluded.title, cz=excluded.cz, color=excluded.color, pages=excluded.pages, sort=excluded.sort',
                (s['key'], season, s['title'], s['cz'], s['color'], json.dumps(s.get('pages') or []), int(s.get('sort') or 0)))
    con.commit(); con.close()

def get_setting(key, default=None):
    con = connect(); r = con.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone(); con.close()
    return json.loads(r['value']) if r else default

def set_setting(key, value):
    con = connect(); con.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value, ensure_ascii=False)))
    con.commit(); con.close()
