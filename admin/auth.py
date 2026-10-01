"""Přihlášení: účty e-mail + heslo, registrace jen z povolené domény a po schválení správcem, relace v podepsané cookie.
Lokální spuštění (python3 admin/app.py) běží bez přihlášení; na serveru je přihlášení zapnuté (vypne ho jen KATALOG_AUTH=0)."""
import os, re, hmac, time, sqlite3, hashlib, secrets, collections
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

HERE = os.path.dirname(os.path.abspath(__file__))
# účty jsou ve vlastní databázi mimo git – katalog.sqlite se verzuje a odesílá na GitHub, hesla tam nepatří
AUTH_DB = os.environ.get('KATALOG_AUTH_DB', os.path.join(HERE, 'users.sqlite'))
DOMAINS = [d.strip().lower() for d in os.environ.get('KATALOG_EMAIL_DOMAIN', 'trimm.cz').split(',') if d.strip()]
ENABLED = os.environ.get('KATALOG_AUTH', '1') != '0'   # app.py ho při lokálním spuštění vypne
COOKIE = 'katalog_session'; TTL = 30 * 24 * 3600
PUBLIC = ('/login', '/api/auth/login', '/api/auth/register', '/api/auth/me', '/setup', '/api/setup/admin', '/api/setup/import')
SETUP_TOKEN = os.environ.get('KATALOG_SETUP_TOKEN')   # jen po dobu prvního nastavení online verze; bez něj jsou /setup adresy vypnuté
# soubory repa, které se nesmí dát stáhnout ani přihlášenému (databáze s hesly, zdrojáky, git)
BLOCKED = re.compile(r'^/repo/(\.git|\.claude|admin/(cache/|[^/]+\.(sqlite|py|command|md)$))')

_made = False
def _con():
    global _made
    import db
    if db.PG_URL: con = db.connect()   # online jsou účty ve stejné databázi jako katalog (ta se nikam neverzuje)
    else: con = sqlite3.connect(AUTH_DB); con.row_factory = sqlite3.Row
    if _made and db.PG_URL: return con
    _made = True
    con.execute('CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, password TEXT NOT NULL, role TEXT NOT NULL DEFAULT \'user\', active INTEGER NOT NULL DEFAULT 0, created REAL, last_login REAL)')
    return con

_secret = None
def secret():
    global _secret
    if _secret: return _secret
    _secret = _load_secret(); return _secret
def _load_secret():
    if os.environ.get('KATALOG_SECRET'): return os.environ['KATALOG_SECRET'].encode()
    con = _con(); r = con.execute("SELECT value FROM config WHERE key='secret'").fetchone()
    if not r: con.execute("INSERT INTO config VALUES('secret', ?)", (secrets.token_hex(32),)); con.commit(); r = con.execute("SELECT value FROM config WHERE key='secret'").fetchone()
    con.close(); return r['value'].encode()

def hash_password(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    return f'pbkdf2${salt}$' + hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 200000).hex()
def check_password(pw, stored):
    try: _, salt, _h = stored.split('$')
    except ValueError: return False
    return hmac.compare_digest(hash_password(pw, salt), stored)

def norm_email(e): return (e or '').strip().lower()
def domain_ok(email): return bool(re.fullmatch(r'[a-z0-9._+-]+@[a-z0-9.-]+\.[a-z]{2,}', email)) and email.split('@')[1] in DOMAINS
def check_new_password(pw):
    if len(pw or '') < 8: raise HTTPException(400, 'Heslo musí mít aspoň 8 znaků.')

def get_user(email):
    con = _con(); r = con.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone(); con.close()
    return dict(r) if r else None
def list_users():
    con = _con(); rows = con.execute('SELECT email, role, active, created, last_login FROM users ORDER BY active, email').fetchall(); con.close()
    return [dict(r) for r in rows]
def save_user(email, password=None, role=None, active=None):
    con = _con(); u = con.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    if not u: con.execute('INSERT INTO users(email,password,role,active,created) VALUES(?,?,?,?,?)', (email, hash_password(password), role or 'user', int(bool(active)), time.time()))
    else:
        if password is not None: con.execute('UPDATE users SET password=? WHERE email=?', (hash_password(password), email))
        if role is not None: con.execute('UPDATE users SET role=? WHERE email=?', (role, email))
        if active is not None: con.execute('UPDATE users SET active=? WHERE email=?', (int(bool(active)), email))
    con.commit(); con.close()
    _seen.pop(email, None)
def delete_user(email):
    _seen.pop(email, None)
    con = _con(); con.execute('DELETE FROM users WHERE email=?', (email,)); con.commit(); con.close()

def make_token(email):
    body = f'{email}|{int(time.time()) + TTL}'
    return body + '|' + hmac.new(secret(), body.encode(), hashlib.sha256).hexdigest()
def read_token(tok):
    try: email, exp, sig = (tok or '').rsplit('|', 2)
    except ValueError: return None
    if not hmac.compare_digest(sig, hmac.new(secret(), f'{email}|{exp}'.encode(), hashlib.sha256).hexdigest()) or int(exp) < time.time(): return None
    hit = _seen.get(email)   # ověření účtu v databázi stačí jednou za půl minuty, ne u každého obrázku
    if not hit or time.time() - hit[0] > 30: hit = _seen[email] = (time.time(), get_user(email))
    u = hit[1]
    return u if u and u['active'] else None
_seen = {}

def current(request: Request):
    if not ENABLED: return dict(email='', role='admin', active=1, local=True)
    return read_token(request.cookies.get(COOKIE))
def need_admin(request: Request):
    u = current(request)
    if not u or u['role'] != 'admin': raise HTTPException(403, 'Jen pro správce.')
    return u

async def middleware(request: Request, call_next):
    path = request.url.path
    if BLOCKED.match(path): return JSONResponse(dict(detail='Nedostupné'), 404)
    if ENABLED and path not in PUBLIC and not current(request):
        if path.startswith('/api/'): return JSONResponse(dict(detail='Nepřihlášeno'), 401)
        return RedirectResponse('/login', 302)
    return await call_next(request)

_fails = collections.defaultdict(list)   # ochrana proti hádání hesel: 8 chyb za 15 minut na e-mail i adresu
def _throttle(key):
    now = time.time(); _fails[key] = [t for t in _fails[key] if now - t < 900]
    if len(_fails[key]) >= 8: raise HTTPException(429, 'Příliš mnoho pokusů. Zkus to znovu za čtvrt hodiny.')

router = APIRouter()

@router.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    if not ENABLED or current(request): return RedirectResponse('/', 302)
    return open(os.path.join(HERE, 'static', 'login.html'), encoding='utf-8').read().replace('__DOMAINS__', ', '.join('@' + d for d in DOMAINS))

@router.post('/api/auth/login')
def login(body: dict, request: Request):
    email = norm_email(body.get('email')); ip = request.client.host if request.client else ''
    _throttle('e:' + email); _throttle('i:' + ip)
    u = get_user(email)
    if not u or not check_password(body.get('password') or '', u['password']):
        _fails['e:' + email].append(time.time()); _fails['i:' + ip].append(time.time()); raise HTTPException(401, 'Nesprávný e-mail nebo heslo.')
    if not u['active']: raise HTTPException(403, 'Účet ještě neschválil správce.')
    con = _con(); con.execute('UPDATE users SET last_login=? WHERE email=?', (time.time(), email)); con.commit(); con.close()
    r = JSONResponse(dict(ok=True))
    r.set_cookie(COOKIE, make_token(email), max_age=TTL, httponly=True, samesite='lax', secure=request.url.scheme == 'https' or request.headers.get('x-forwarded-proto') == 'https')
    return r

@router.post('/api/auth/register')
def register(body: dict, request: Request):
    email = norm_email(body.get('email')); _throttle('r:' + (request.client.host if request.client else '')); _fails['r:' + (request.client.host if request.client else '')].append(time.time())
    if not domain_ok(email): raise HTTPException(400, 'Registrovat se jde jen s e-mailem ' + ' nebo '.join('@' + d for d in DOMAINS) + '.')
    check_new_password(body.get('password'))
    if get_user(email): raise HTTPException(400, 'Účet s tímto e-mailem už existuje.')
    save_user(email, body['password'], 'user', False)
    return dict(ok=True, message='Účet je založený a čeká na schválení správcem.')

def _setup(token):
    if not SETUP_TOKEN or not hmac.compare_digest(token or '', SETUP_TOKEN): raise HTTPException(404)

@router.get('/setup', response_class=HTMLResponse)
def setup_page(token: str = ''):
    _setup(token)
    return '''<!DOCTYPE html><html lang="cs"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TRIMM katalogy – první správce</title>
<body style="font:14px Helvetica,Arial,sans-serif;background:#f4f4f2;display:flex;justify-content:center;padding:40px 16px"><form id="f" style="background:#fff;border:1px solid #e3e3e0;border-radius:8px;padding:28px;width:min(380px,100%)">
<b style="letter-spacing:.3em;font-size:18px">TRIMM</b><p style="color:#777;font-size:12px;margin:4px 0 18px">Založení prvního správce aplikace</p>
<label style="font-size:11px;font-weight:700">E-mail</label><input id="e" type="email" required style="width:100%;padding:9px;margin:3px 0 10px;border:1px solid #e3e3e0;border-radius:4px">
<label style="font-size:11px;font-weight:700">Heslo (aspoň 8 znaků)</label><input id="p" type="password" required minlength="8" style="width:100%;padding:9px;margin:3px 0 10px;border:1px solid #e3e3e0;border-radius:4px">
<button style="width:100%;padding:10px;border:0;border-radius:4px;background:#ff6b1a;color:#fff;font-weight:700;cursor:pointer">Založit správce</button><p id="m" style="font-size:12px;margin-top:12px"></p></form>
<script>f.onsubmit=async ev=>{ev.preventDefault();const r=await fetch('/api/setup/admin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:new URLSearchParams(location.search).get('token'),email:e.value,password:p.value})});
const j=await r.json().catch(()=>({}));m.textContent=r.ok?'Hotovo, přesměrovávám na přihlášení…':(j.detail||'Nepodařilo se.');if(r.ok)setTimeout(()=>location.href='/login',1200)}</script></body></html>'''

@router.post('/api/setup/admin')
def setup_admin(body: dict):
    """první správce – smí mít e-mail i mimo povolenou doménu"""
    _setup(body.get('token')); email = norm_email(body.get('email'))
    if body.get('remove'): delete_user(email); return dict(ok=True, removed=email)
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[a-z]{2,}', email): raise HTTPException(400, 'Neplatný e-mail.')
    check_new_password(body.get('password')); save_user(email, body['password'], 'admin', True); return dict(ok=True)

@router.post('/api/setup/import')
async def setup_import(request: Request, token: str = '', force: int = 0):
    """tělo požadavku = soubor katalog.sqlite; zkopíruje ho do online databáze"""
    _setup(token)
    import tempfile, to_online
    with tempfile.NamedTemporaryFile(suffix='.sqlite') as f:
        f.write(await request.body()); f.flush()
        try: return to_online.copy(f.name, bool(force))
        except ValueError as e: raise HTTPException(400, str(e))

@router.post('/api/auth/logout')
def logout():
    r = JSONResponse(dict(ok=True)); r.delete_cookie(COOKIE); return r

@router.get('/api/auth/me')
def me(request: Request):
    u = current(request)
    import store
    return dict(auth=ENABLED, online=store.REMOTE, email=u['email'] if u else None, role=u['role'] if u else None, domains=DOMAINS,
                pending=sum(1 for x in list_users() if not x['active']) if u and u['role'] == 'admin' and ENABLED else 0)

@router.post('/api/auth/password')
def change_password(body: dict, request: Request):
    u = current(request)
    if not u or u.get('local'): raise HTTPException(400, 'Nejsi přihlášený.')
    if not check_password(body.get('old') or '', get_user(u['email'])['password']): raise HTTPException(400, 'Současné heslo nesouhlasí.')
    check_new_password(body.get('new')); save_user(u['email'], password=body['new']); return dict(ok=True)

@router.get('/api/users')
def users(request: Request): need_admin(request); return list_users()

@router.post('/api/users')
def user_create(body: dict, request: Request):
    need_admin(request); email = norm_email(body.get('email'))
    if not domain_ok(email): raise HTTPException(400, 'E-mail musí být ' + ' nebo '.join('@' + d for d in DOMAINS) + '.')
    if get_user(email): raise HTTPException(400, 'Účet už existuje.')
    check_new_password(body.get('password')); save_user(email, body['password'], 'admin' if body.get('role') == 'admin' else 'user', True); return dict(ok=True)

@router.put('/api/users/{email}')
def user_update(email: str, body: dict, request: Request):
    me_ = need_admin(request); u = get_user(email)
    if not u: raise HTTPException(404)
    if email == me_['email'] and (body.get('active') is False or body.get('role') == 'user'): raise HTTPException(400, 'Sám sobě nejde odebrat přístup ani práva správce.')
    if body.get('password') is not None: check_new_password(body['password'])
    save_user(email, body.get('password'), body.get('role') if body.get('role') in ('admin', 'user') else None, body.get('active')); return dict(ok=True)

@router.delete('/api/users/{email}')
def user_delete(email: str, request: Request):
    me_ = need_admin(request)
    if email == me_['email']: raise HTTPException(400, 'Vlastní účet smazat nejde.')
    delete_user(email); return dict(ok=True)

if __name__ == '__main__':
    # první správce (nebo reset hesla): python3 admin/auth.py spravce@trimm.cz   – heslo se zadá skrytě
    import sys, getpass
    if len(sys.argv) < 2: print('Použití: python3 admin/auth.py <e-mail> [--user]'); sys.exit(1)
    email = norm_email(sys.argv[1]); pw = getpass.getpass('Heslo (aspoň 8 znaků): ')
    if len(pw) < 8 or pw != getpass.getpass('Heslo znovu: '): print('Hesla se neshodují nebo je heslo krátké.'); sys.exit(1)
    if not domain_ok(email): print(f'Pozor: {email} není z povolené domény ({", ".join(DOMAINS)}). Účet zakládám jako výjimku z příkazové řádky.')
    save_user(email, pw, 'user' if '--user' in sys.argv else 'admin', True); print('Účet uložen:', email)
