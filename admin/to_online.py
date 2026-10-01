"""Jednorázové zkopírování lokální databáze katalogu (katalog.sqlite) do online databáze (Postgres).
Spuštění: DATABASE_URL=… python3 admin/to_online.py [--force]   – bez --force odmítne přepsat online katalogy, které už existují.
Soubory se nekopírují: základ je v obrazu aplikace z repa (viz Dockerfile.vercel)."""
import os, sys, sqlite3
import db

def main():
    if not db.PG_URL: print('Chybí DATABASE_URL.'); sys.exit(1)
    src = sqlite3.connect(db.DB_PATH); src.row_factory = sqlite3.Row; dst = db.connect()
    n = dst.execute('SELECT COUNT(*) n FROM catalogs').fetchone()['n']
    if n and '--force' not in sys.argv: print(f'Online databáze už obsahuje {n} katalogů. Pro přepsání spusť s --force.'); sys.exit(1)
    for t in ('products', 'sections', 'settings', 'catalogs', 'prev_cards'):
        rows = src.execute(f'SELECT * FROM {t}').fetchall(); dst.execute(f'DELETE FROM {t}')
        if not rows: continue
        cols = rows[0].keys(); q = f'INSERT INTO {t}({",".join(cols)}) VALUES({",".join("%s" for _ in cols)})'
        with db._PG.conn.cursor() as cur: cur.executemany(q, [tuple(r) for r in rows])
        print(t, len(rows))

if __name__ == '__main__': main()
