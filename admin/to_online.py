"""Zkopírování lokální databáze katalogu (katalog.sqlite) do online databáze (Postgres).
Heslo k online databázi se z Vercelu nedá stáhnout, proto kopie běží na serveru: soubor se pošle na /api/setup/import
(viz auth.py, chráněno jednorázovým KATALOG_SETUP_TOKEN). Soubory se nekopírují: základ je v obrazu aplikace (Dockerfile.vercel)."""
import sqlite3
import db

TABLES = ('products', 'sections', 'settings', 'catalogs', 'prev_cards')

def copy(sqlite_path, force=False):
    src = sqlite3.connect(sqlite_path); src.row_factory = sqlite3.Row; dst = db.connect(); out = {}
    n = dst.execute('SELECT COUNT(*) n FROM catalogs').fetchone()['n']
    if n and not force: raise ValueError(f'Online databáze už obsahuje {n} katalogů. Pro přepsání pošli force=1.')
    for t in TABLES:
        rows = src.execute(f'SELECT * FROM {t}').fetchall(); dst.execute(f'DELETE FROM {t}'); out[t] = len(rows)
        if not rows: continue
        cols = rows[0].keys(); q = f'INSERT INTO {t}({",".join(cols)}) VALUES({",".join("%s" for _ in cols)})'
        with db._PG.conn.cursor() as cur: cur.executemany(q, [tuple(r) for r in rows])
    return out
