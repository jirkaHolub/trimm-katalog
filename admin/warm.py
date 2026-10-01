"""Po nasazení online verze projde obrázky živých katalogů, aby je CDN Vercelu mělo uložené a první otevření katalogu bylo rychlé.
Použití: python3 admin/warm.py https://trimm-katalog.vercel.app <soubor s cookie relace: katalog_session=…>"""
import re, sys, time, json
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor

base = sys.argv[1].rstrip('/'); cookie = open(sys.argv[2]).read().strip()
def get(path):
    t = time.time(); err = ''
    for attempt in range(3):
        try:
            r = urlopen(Request(base + path, headers={'Cookie': cookie, 'User-Agent': 'katalog-warm'}), timeout=120); body = r.read()
            time.sleep(0.05)   # zvolna: prudká dávka požadavků z jedné adresy spustí ochranu Vercelu a ta adresu na pár minut odřízne
            return path, r.status, r.headers.get('x-vercel-cache'), len(body), time.time() - t, body
        except Exception as e: err = str(e)[:60]; time.sleep(1 + attempt)
    return path, 0, err, 0, time.time() - t, b''

cats = [c['code'] for c in json.loads(get('/api/catalogs')[5])['catalogs'] if c['source'] == 'db']
urls = set()
for code in cats:
    html = get('/nahled/' + code)[5].decode('utf-8', 'ignore')
    urls |= set(re.findall(r'(/thumb/[^"\')]+)', html))
    for p in json.loads(get(f'/api/c/{code}/products')[5])['products']:
        if p.get('thumb'): urls.add(f'/thumb/{p["thumb"]}?w=120')
urls = sorted(u.replace('&amp;', '&') for u in urls); t0 = time.time()
with ThreadPoolExecutor(3) as ex: res = list(ex.map(get, urls))
bad = [r for r in res if r[1] != 200]
print(f'{len(urls)} obrázků, {sum(r[3] for r in res) / 1e6:.1f} MB, {time.time() - t0:.0f} s, z CDN už {sum(1 for r in res if r[2] == "HIT")}, chyb {len(bad)}')
for r in bad[:5]: print('  ', r[:3])
