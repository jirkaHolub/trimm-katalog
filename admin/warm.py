"""Po nasazení online verze projde zmenšeniny obrázků katalogů, aby je CDN Vercelu mělo uložené a první otevření katalogu bylo rychlé
(nasazením se uložené obrázky vyprázdní). Seznam obrázků se bere z lokální databáze; zmenšeniny jsou veřejné, přihlášení není potřeba.
Použití: python3 admin/warm.py https://trimm-katalog.vercel.app"""
import re, sys, time
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor
import db, generate

base = sys.argv[1].rstrip('/')
def get(path):
    t = time.time(); err = ''
    for attempt in range(3):
        try:
            r = urlopen(Request(base + path, headers={'User-Agent': 'katalog-warm'}), timeout=120); body = r.read()
            time.sleep(0.05)   # zvolna: prudká dávka požadavků z jedné adresy spustí ochranu Vercelu a ta adresu na pár minut odřízne
            return path, r.status, r.headers.get('x-vercel-cache'), len(body), time.time() - t
        except Exception as e: err = str(e)[:60]; time.sleep(1 + attempt)
    return path, 0, err, 0, time.time() - t

urls = set()
for cat in db.list_catalogs():
    if cat.get('source') != 'db': continue
    prods = db.list_products(cat['code'])
    urls |= set(re.findall(r'(/thumb/[^"\')]+)', generate.render_document(cat, prods, db.list_sections(cat['code']), '/')))
    for p in prods:
        t = p.get('hero') or next((c.get('front') for c in p['colors'] if c.get('front')), None)
        if t: urls.add(f'/thumb/{t}?w=120')
urls = sorted(u.replace('&amp;', '&') for u in urls); t0 = time.time()
with ThreadPoolExecutor(3) as ex: res = list(ex.map(get, urls))
bad = [r for r in res if r[1] != 200]
print(f'{len(urls)} obrázků, {sum(r[3] for r in res) / 1e6:.1f} MB, {time.time() - t0:.0f} s, z CDN už {sum(1 for r in res if r[2] == "HIT")}, chyb {len(bad)}')
for r in bad[:5]: print('  ', r[:3])
