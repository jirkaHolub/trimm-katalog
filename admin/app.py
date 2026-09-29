"""Administrace katalogu TRIMM. Spuštění: python3 admin/app.py  ->  http://localhost:8765"""
import os, re, io, json, hashlib, unicodedata, threading, sys
try:
    from fastapi import FastAPI, UploadFile, File, Form, HTTPException
except ImportError:
    print('Chybí balíčky. Nainstaluj je příkazem:\n  ' + sys.executable + ' -m pip install --user fastapi "uvicorn[standard]" python-multipart pillow pymupdf')
    sys.exit(1)
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
import db, generate
from schemas import SECTIONS, SCHEMAS, SPEC_LABELS, GENDERS, BADGE_LABELS, empty_product

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, '..'))
UP = os.path.join(HERE, 'uploads'); os.makedirs(UP, exist_ok=True)
app = FastAPI(title='TRIMM katalog – administrace')
app.mount('/uploads', StaticFiles(directory=UP), name='uploads')
app.mount('/repo', StaticFiles(directory=REPO), name='repo')

def slugify(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')

@app.get('/', response_class=HTMLResponse)
def index(): return open(os.path.join(HERE, 'static', 'index.html'), encoding='utf-8').read()

@app.get('/api/meta')
def meta():
    season = 'SS27'
    badges = sorted(f[:-4] for f in os.listdir(os.path.join(UP, 'ikony')) if f.endswith('.png')) if os.path.isdir(os.path.join(UP, 'ikony')) else []
    prods = db.list_products(season)
    series = {}
    for p in prods: series.setdefault(p['section'], []); (series[p['section']].append(p['serie']) if p['serie'] and p['serie'] not in series[p['section']] else None)
    typs = {}
    for p in prods: typs.setdefault(p['section'], set()).add(p.get('typ') or '')
    return dict(season=season, sections=[dict(key=k, **v) for k, v in SECTIONS.items()], schemas=SCHEMAS, spec_labels=SPEC_LABELS, genders=GENDERS,
                badges=[dict(name=b, file=f'uploads/ikony/{b}.png', label=BADGE_LABELS.get(b, b)) for b in badges], series=series,
                typs={k: sorted(v | set(SCHEMAS[k]['typ'])) for k, v in typs.items()})

@app.get('/api/products')
def products(section: str = None):
    out = []
    for p in db.list_products('SS27', section):
        out.append(dict(id=p['id'], name=p['name'], section=p['section'], serie=p['serie'], sort=p['sort'], typ=p.get('typ'), new=p.get('new'),
                        thumb=p.get('hero') or next((c.get('front') for c in p['colors'] if c.get('front')), None), n_colors=len(p['colors'])))
    return out

@app.get('/api/products/{pid}')
def product(pid: str):
    p = db.get_product(pid)
    if not p: raise HTTPException(404)
    return p

@app.post('/api/products')
def create(body: dict):
    section = body.get('section') or 'tents'; name = (body.get('name') or 'NOVÝ PRODUKT').strip()
    p = empty_product(section); p.update(body); p['name'] = name; p['season'] = 'SS27'
    base = slugify(name) or 'produkt'; pid = base; i = 2
    while db.get_product(pid): pid = f'{base}_{i}'; i += 1
    p['id'] = pid; p['sort'] = db.next_sort('SS27', section)
    db.save_product(p); return p

@app.put('/api/products/{pid}')
def update(pid: str, body: dict):
    old = db.get_product(pid)
    if not old: raise HTTPException(404)
    body['id'] = pid; body['season'] = 'SS27'
    if body.get('section') != old['section']: body['sort'] = db.next_sort('SS27', body['section'])
    db.save_product(body); return db.get_product(pid)

@app.delete('/api/products/{pid}')
def delete(pid: str): db.delete_product(pid); return dict(ok=True)

@app.post('/api/reorder')
def reorder(body: dict):
    db.renumber('SS27', body['section'], body['ids']); return dict(ok=True)

@app.post('/api/upload')
async def upload(file: UploadFile = File(...), kind: str = Form('foto'), name: str = Form('')):
    """kind: foto | rozkresy | ikony | pages | inner (PNG s průhledností)"""
    raw = await file.read()
    im = Image.open(io.BytesIO(raw)); im.load()
    sub = 'foto' if kind in ('foto', 'inner') else kind; os.makedirs(os.path.join(UP, sub), exist_ok=True)
    h = hashlib.md5(raw).hexdigest()[:8]; base = slugify(name or os.path.splitext(file.filename)[0]) or 'obr'
    keep_alpha = kind in ('inner', 'rozkresy', 'ikony') and im.mode in ('RGBA', 'LA', 'P') and (im.convert('RGBA').getextrema()[3][0] < 255)
    if keep_alpha:
        im = im.convert('RGBA'); im.thumbnail((1600, 1600)); fn = f'{base}_{h}.png'; im.save(os.path.join(UP, sub, fn), optimize=True)
    else:
        if im.mode in ('RGBA', 'LA', 'P'):
            bg = Image.new('RGB', im.size, (255, 255, 255)); im = im.convert('RGBA'); bg.paste(im, mask=im.split()[-1]); im = bg
        im = im.convert('RGB'); im.thumbnail((1600, 1600)); fn = f'{base}_{h}.jpg'; im.save(os.path.join(UP, sub, fn), quality=88, optimize=True)
    return dict(path=f'uploads/{sub}/{fn}', w=im.width, h=im.height)

def _save_image(im, sub, base, force_png=False):
    os.makedirs(os.path.join(UP, sub), exist_ok=True)
    has_alpha = im.mode in ('RGBA', 'LA') and im.getextrema()[-1][0] < 255
    b = io.BytesIO()
    if has_alpha or force_png:
        im = im.convert('RGBA'); im.save(b, 'PNG', optimize=True); ext = 'png'
    else:
        if im.mode != 'RGB':
            bg = Image.new('RGB', im.size, (255, 255, 255)); im = im.convert('RGBA'); bg.paste(im, mask=im.split()[-1]); im = bg
        im.save(b, 'JPEG', quality=88, optimize=True); ext = 'jpg'
    h = hashlib.md5(b.getvalue()).hexdigest()[:8]; fn = f'{base}_{h}.{ext}'
    open(os.path.join(UP, sub, fn), 'wb').write(b.getvalue())
    return dict(path=f'uploads/{sub}/{fn}', w=im.width, h=im.height)

def _load_upload(path):
    if not path.startswith('uploads/') or '..' in path: raise HTTPException(400, 'neplatná cesta')
    fp = os.path.join(HERE, path)
    if not os.path.exists(fp): raise HTTPException(404, 'soubor neexistuje')
    im = Image.open(fp); im.load(); return im, path.split('/')[1], re.sub(r'_[0-9a-f]{8}$', '', os.path.splitext(os.path.basename(path))[0])

def _edge_mask(im, thresh):
    """maska pozadí: pixely blízké bílé/světle šedé napojené na okraj obrázku"""
    from PIL import ImageDraw, ImageChops
    rgb = im.convert('RGB'); w, h = rgb.size
    r, g, b = rgb.split(); mn = ImageChops.darker(ImageChops.darker(r, g), b); mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    sat = ImageChops.subtract(mx, mn)
    cand = ImageChops.darker(mn.point(lambda v: 255 if v >= 255 - thresh * 2 else 0), sat.point(lambda v: 255 if v <= max(12, thresh // 2) else 0))
    pad = Image.new('L', (w + 2, h + 2), 255); pad.paste(cand, (1, 1))
    for pt in ((0, 0), (w + 1, 0), (0, h + 1), (w + 1, h + 1), (w // 2, 0), (w // 2, h + 1), (0, h // 2), (w + 1, h // 2)):
        if pad.getpixel(pt) == 255: ImageDraw.floodfill(pad, pt, 128)
    return pad.crop((1, 1, w + 1, h + 1)).point(lambda v: 255 if v == 128 else 0)

@app.post('/api/edit')
def edit(body: dict):
    """Úprava fotky: op = rotate(deg) | flip | crop(x,y,w,h v poměrech 0–1) | trim | whiten(thresh) | alpha(thresh)"""
    im, sub, base = _load_upload(body['path']); op = body.get('op'); force_png = False
    from PIL import ImageOps, ImageChops, ImageFilter
    if op == 'rotate':
        fill = (255, 255, 255, 0) if im.mode == 'RGBA' else (255, 255, 255)
        im = im.convert('RGBA' if im.mode == 'RGBA' else 'RGB').rotate(-int(body.get('deg', 90)), expand=True, fillcolor=fill)
    elif op == 'flip': im = ImageOps.mirror(im)
    elif op == 'crop':
        w, h = im.size; x0 = int(w * float(body['x'])); y0 = int(h * float(body['y'])); x1 = int(w * (float(body['x']) + float(body['w']))); y1 = int(h * (float(body['y']) + float(body['h'])))
        im = im.crop((max(0, x0), max(0, y0), min(w, max(x0 + 1, x1)), min(h, max(y0 + 1, y1))))
    elif op == 'trim':
        if im.mode == 'RGBA': bb = im.split()[-1].point(lambda v: 255 if v > 8 else 0).getbbox()
        else: bb = ImageChops.difference(im.convert('RGB'), Image.new('RGB', im.size, (255, 255, 255))).convert('L').point(lambda v: 255 if v > 18 else 0).getbbox()
        if bb:
            pad = int(max(bb[2] - bb[0], bb[3] - bb[1]) * 0.03); w, h = im.size
            im = im.crop((max(0, bb[0] - pad), max(0, bb[1] - pad), min(w, bb[2] + pad), min(h, bb[3] + pad)))
    elif op in ('whiten', 'alpha'):
        thresh = int(body.get('thresh', 30)); m = _edge_mask(im, thresh)
        if op == 'whiten':
            rgb = im.convert('RGB'); im = Image.composite(Image.new('RGB', im.size, (255, 255, 255)), rgb, m)
        else:
            rgba = im.convert('RGBA'); alpha = ImageChops.invert(m).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
            if rgba.getextrema()[3][0] < 255: alpha = ImageChops.darker(alpha, rgba.split()[3])
            rgba.putalpha(alpha); im = rgba; force_png = True
    else: raise HTTPException(400, 'neznámá operace')
    return _save_image(im, sub, base, force_png)

@app.get('/api/library')
def library(q: str = '', sub: str = ''):
    out = []
    for d in sorted(os.listdir(UP)):
        if not os.path.isdir(os.path.join(UP, d)) or (sub and d != sub) or d == 'pages': continue
        for f in os.listdir(os.path.join(UP, d)):
            if not f.lower().endswith(('.jpg', '.jpeg', '.png')): continue
            if q and q.lower() not in f.lower(): continue
            fp = os.path.join(UP, d, f); out.append(dict(path=f'uploads/{d}/{f}', name=f, sub=d, mtime=os.path.getmtime(fp)))
    out.sort(key=lambda x: -x['mtime']); return out[:400]

@app.post('/api/fetch')
def fetch_url(body: dict):
    """stáhne obrázek z URL (např. trimm.eu) a uloží ho jako nahraný soubor"""
    from urllib.request import Request, urlopen
    url = body['url']; kind = body.get('kind', 'foto')
    raw = urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0 katalog-admin'}), timeout=60).read()
    im = Image.open(io.BytesIO(raw)); im.load(); im.thumbnail((1600, 1600))
    base = slugify(body.get('name') or os.path.splitext(os.path.basename(url.split('?')[0]))[0]) or 'obr'
    return _save_image(im, 'foto' if kind in ('foto', 'inner') else kind, base)

@app.get('/api/webgallery')
def webgallery(url: str):
    """seznam produktových fotek na stránce trimm.eu"""
    from urllib.request import Request, urlopen
    try: html_ = urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0 katalog-admin'}), timeout=60).read().decode('utf-8', 'ignore')
    except Exception as e: raise HTTPException(400, f'Stránku se nepodařilo načíst: {e}')
    files = []
    for m in re.finditer(r'user/shop/(?:big|detail|orig|detail_small)/([^"\'?\s]+\.(?:jpe?g|png))', html_, re.I):
        fn = m.group(1)
        if fn not in files: files.append(fn)
    base = 'https://cdn.myshoptet.com/usr/www.trimm.eu/user/shop/'
    return [dict(name=fn, thumb=base + 'detail_small/' + fn, url=base + 'orig/' + fn) for fn in files]

@app.get('/api/preview/{pid}', response_class=HTMLResponse)
def preview(pid: str):
    p = db.get_product(pid)
    if not p: raise HTTPException(404)
    return generate.render_card_preview(p, '/')

@app.post('/api/preview', response_class=HTMLResponse)
def preview_draft(body: dict):
    body.setdefault('colors', []); body.setdefault('id', 'draft'); body.setdefault('name', '')
    return generate.render_card_preview(body, '/')

_gen_lock = threading.Lock()
@app.post('/api/generate')
def gen(body: dict):
    if not _gen_lock.acquire(blocking=False): raise HTTPException(409, 'Generování už běží')
    log = []
    try:
        generate.build('SS27', pdf=bool(body.get('pdf', True)), log=log.append)
        if body.get('push'): generate.git_push(log=log.append)
    except Exception as e: log.append('CHYBA: ' + str(e))
    finally: _gen_lock.release()
    return dict(log='\n'.join(log), html='/repo/ss27/trimm_katalog_SS27.html', pdf='/repo/vystupy/trimm_katalog_SS27_CZ.pdf')

if __name__ == '__main__':
    import uvicorn, webbrowser, socket
    if not os.path.exists(db.DB_PATH): print('Databáze neexistuje, spusť nejdřív: python3 admin/import_catalog.py')
    port = int(os.environ.get('PORT', 8765))
    for cand in range(port, port + 10):
        with socket.socket() as sk:
            if sk.connect_ex(('127.0.0.1', cand)) != 0: port = cand; break
    url = f'http://localhost:{port}'
    print(f'Administrace běží na {url}  (ukončení: Ctrl+C)')
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
