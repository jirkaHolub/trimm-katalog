"""Úložiště souborů aplikace. Klíč souboru je cesta, jak ji aplikace používá odjakživa: 'uploads/foto/x.jpg' (nahrané soubory)
nebo cesta v repu ('vystupy/x.pdf').
Lokálně = složky repa. Online (Vercel) = dvě vrstvy:
  základ    – soubory z repa přibalené do obrazu aplikace při nasazení (jen ke čtení, KATALOG_BASE_DIR)
  přírůstky – vše, co vznikne online (nové fotky, vygenerovaná PDF), jde do Vercel Blob a eviduje se v tabulce `files`;
              smazání souboru ze základu je v tabulce jako záznam s deleted
Tarif Hobby dovoluje jen 2 000 zápisů do Blob měsíčně, proto se tam neposílá celý archiv, jen přírůstky."""
import os, json, time, mimetypes
from urllib.parse import quote
from urllib.request import urlopen, Request

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, '..'))
TOKEN = os.environ.get('BLOB_READ_WRITE_TOKEN'); REMOTE = bool(TOKEN and os.environ.get('DATABASE_URL'))
TMP = os.environ.get('KATALOG_TMP', '/tmp/katalog'); BASE_DIR = os.environ.get('KATALOG_BASE_DIR', '/app/base')
# veřejná adresa úložiště se dá odvodit z tokenu: vercel_blob_rw_<id úložiště>_<tajná část>
BASE = os.environ.get('KATALOG_BLOB_BASE') or (f'https://{TOKEN.split("_")[3].lower()}.public.blob.vercel-storage.com' if TOKEN and len(TOKEN.split('_')) > 4 else '')

def fs_path(key):
    """skutečná cesta v repu (lokální režim)"""
    return os.path.join(HERE, key) if key.startswith('uploads/') else os.path.join(REPO, key)
def base_path(key): return os.path.join(BASE_DIR, key)
def cache_dir(name):
    d = os.path.join(TMP if REMOTE else HERE, 'cache', name); os.makedirs(d, exist_ok=True); return d
def safe(key): return bool(key) and '..' not in key and not key.startswith('/')

def _db():
    import db
    con = db.connect()
    con.execute('CREATE TABLE IF NOT EXISTS files(key TEXT PRIMARY KEY, size BIGINT, mtime REAL, meta TEXT)')
    return con

def _row(key):
    con = _db(); r = con.execute('SELECT * FROM files WHERE key=?', (key,)).fetchone(); con.close()
    return dict(json.loads(r['meta'] or '{}'), size=r['size'], mtime=r['mtime'], blob=True) if r else None

def stat(key):
    """dict(size, mtime, + uložené údaje jako pages, shot; blob=True u souboru v Blob) nebo None, když soubor není"""
    if not safe(key): return None
    if REMOTE:
        r = _row(key)
        if r: return None if r.get('deleted') else r
    fp = base_path(key) if REMOTE else fs_path(key)
    if not os.path.isfile(fp): return None
    st = os.stat(fp); return dict(size=st.st_size, mtime=st.st_mtime)
def exists(key): return stat(key) is not None

def url(key, st=None):
    """adresa, ze které soubor načte prohlížeč"""
    if REMOTE:
        st = st or stat(key)
        if st and st.get('blob'): return f'{BASE}/{quote(key)}?v={int(st["mtime"])}'
    return ('/' + key) if key.startswith('uploads/') else '/repo/' + key

def set_meta(key, **meta):
    if not REMOTE: return
    con = _db(); r = con.execute('SELECT meta FROM files WHERE key=?', (key,)).fetchone()
    if r: con.execute('UPDATE files SET meta=? WHERE key=?', (json.dumps(dict(json.loads(r['meta'] or '{}'), **meta)), key)); con.commit()
    con.close()

def local(key, st=None):
    """cesta k souboru na disku pro čtení (PIL, PyMuPDF); soubor z Blob se nejdřív stáhne do dočasné složky"""
    if not REMOTE: return fs_path(key)
    st = st or stat(key)
    if not st or not st.get('blob'): return base_path(key)
    fp = os.path.join(TMP, 'blob', f'{int(st["mtime"])}', key)
    if not os.path.exists(fp):
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        data = urlopen(Request(url(key, st), headers={'User-Agent': 'katalog'}), timeout=120).read()
        tmp = fp + f'.{os.getpid()}.part'; open(tmp, 'wb').write(data); os.replace(tmp, fp)
    return fp

def read(key): return open(local(key), 'rb').read()

def overlay(keys):
    """složka, ve které jsou zadané soubory pod svými klíči (odkazy na základ / stažené z Blob) – pro tisk PDF z file://"""
    root = os.path.join(TMP, 'overlay')
    for key in set(k for k in keys if k and safe(k)):
        src = local(key); dst = os.path.join(root, key)
        if not os.path.exists(src): continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.islink(dst) or os.path.exists(dst):
            if os.path.realpath(dst) == os.path.realpath(src): continue
            os.remove(dst)
        os.symlink(src, dst)
    return root

def write(key, data, content_type=None, max_age=None, **meta):
    """uloží soubor; online ho nahraje do Blob a zapíše do tabulky files"""
    if not safe(key): raise ValueError('neplatná cesta')
    if not REMOTE:
        fp = fs_path(key); os.makedirs(os.path.dirname(fp), exist_ok=True); open(fp, 'wb').write(data); return
    from vercel import blob
    blob.put(key, data, access='public', content_type=content_type or mimetypes.guess_type(key)[0] or 'application/octet-stream',
             add_random_suffix=False, overwrite=True, cache_control_max_age=max_age, token=TOKEN, multipart=len(data) > 20 * 1024 * 1024)
    index(key, len(data), time.time(), **meta)

def index(key, size, mtime, **meta):
    con = _db()
    con.execute('INSERT INTO files(key,size,mtime,meta) VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET size=excluded.size, mtime=excluded.mtime, meta=excluded.meta',
                (key, size, mtime, json.dumps(meta)))
    con.commit(); con.close()

def delete(key):
    if not safe(key): return
    if not REMOTE:
        if os.path.exists(fs_path(key)): os.remove(fs_path(key))
        return
    r = _row(key)
    if r and not r.get('deleted'):
        from vercel import blob
        blob.delete([f'{BASE}/{quote(key)}'], token=TOKEN)
    con = _db(); con.execute('DELETE FROM files WHERE key=?', (key,)); con.commit(); con.close()
    if os.path.isfile(base_path(key)): index(key, 0, time.time(), deleted=True)   # soubor ze základu smazat nejde, jen ho skrýt

def _walk_dir(root0, prefix):
    out = []
    for root, dirs, files in os.walk(root0):
        for f in files:
            fp = os.path.join(root, f); st = os.stat(fp); out.append(dict(key=prefix + os.path.relpath(fp, root0).replace(os.sep, '/'), size=st.st_size, mtime=st.st_mtime))
    return out

def walk(prefix):
    """všechny soubory pod složkou: [dict(key, size, mtime)]"""
    prefix = prefix.rstrip('/') + '/'
    if not REMOTE: return _walk_dir(fs_path(prefix), prefix)
    files = {f['key']: f for f in _walk_dir(base_path(prefix), prefix)}
    con = _db(); rows = con.execute('SELECT key, size, mtime, meta FROM files WHERE key LIKE ?', (prefix + '%',)).fetchall(); con.close()
    for r in rows:
        if json.loads(r['meta'] or '{}').get('deleted'): files.pop(r['key'], None)
        else: files[r['key']] = dict(key=r['key'], size=r['size'], mtime=r['mtime'])
    return list(files.values())
