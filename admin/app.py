"""Aplikace na tvorbu katalogů TRIMM. Spuštění: python3 admin/app.py  ->  http://localhost:8765"""
import os, re, io, json, time, hashlib, threading, sys
try:
    from fastapi import FastAPI, UploadFile, File, Form, HTTPException
except ImportError:
    print('Chybí balíčky. Nainstaluj je příkazem:\n  ' + sys.executable + ' -m pip install --user fastapi "uvicorn[standard]" python-multipart pillow pymupdf openpyxl')
    sys.exit(1)
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
import db, generate, catalogs, orderform, auth, store
from typing import List
from schemas import SECTIONS, SCHEMAS, SPEC_LABELS, GENDERS, BADGE_LABELS, empty_product

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, '..'))
UP = os.path.join(HERE, 'uploads')
IMG = '/'   # odkud si náhledy karet berou obrázky
if not store.REMOTE: os.makedirs(UP, exist_ok=True)
app = FastAPI(title='TRIMM katalogy')
app.middleware('http')(auth.middleware)
app.include_router(auth.router)
if store.REMOTE:
    # online: soubor je buď v základu přibaleném k aplikaci (vrátí se rovnou), nebo ve Vercel Blob (přesměrování); HTML se vrací přímo kvůli relativním odkazům
    @app.get('/uploads/{path:path}')
    def uploads_file(path: str): return _file_response('uploads/' + path, 'public, max-age=86400, s-maxage=2592000')

    @app.get('/repo/{path:path}')
    def repo_file(path: str):
        up = path.startswith('admin/uploads/')
        return _file_response('uploads/' + path[len('admin/uploads/'):] if up else path, 'public, max-age=86400, s-maxage=2592000' if up else 'private, max-age=60')

    def _file_response(key, cache):
        st = store.stat(key)
        if not st: raise HTTPException(404)
        if key.lower().endswith(('.html', '.htm')): return HTMLResponse(store.read(key).decode('utf-8'), headers={'Cache-Control': 'no-store'})
        if st.get('blob'): return RedirectResponse(store.url(key, st), 302, headers={'Cache-Control': 'private, max-age=300'})
        return FileResponse(store.base_path(key), headers={'Cache-Control': cache})
else:
    app.mount('/uploads', StaticFiles(directory=UP), name='uploads')
    app.mount('/repo', StaticFiles(directory=REPO), name='repo')

from catalogs import slugify

def need_catalog(code, write=False):
    cat = db.get_catalog(code)
    if not cat: raise HTTPException(404, f'Katalog {code} neexistuje')
    if write and cat.get('source') != 'db': raise HTTPException(400, 'Archivní katalog (jen PDF) nemá produkty')
    if write and cat.get('status') == 'done': raise HTTPException(423, 'Katalog je uzavřený. Odemkni ho v nastavení katalogu.')
    return cat

@app.get('/', response_class=HTMLResponse)
def index(): return open(os.path.join(HERE, 'static', 'index.html'), encoding='utf-8').read()

# ---------- katalogy ----------
@app.get('/api/catalogs')
def catalogs_list():
    cats = [catalogs.summary(c) for c in db.list_catalogs()]
    cats.sort(key=lambda c: (-(c.get('year_num') or 0), 0 if c.get('kind') == 'FW' else 1))
    return dict(catalogs=cats, kinds=[dict(key=k, **v) for k, v in catalogs.KINDS.items()])

@app.post('/api/catalogs')
def catalog_create(body: dict):
    try: cat, n = catalogs.create(body.get('kind'), int(body.get('year')), body.get('base') or '', bool(body.get('copy_products', True)), bool(body.get('reset_new', True)))
    except ValueError as e: raise HTTPException(400, str(e))
    return dict(catalog=cat, copied=n)

@app.post('/api/archive')
async def archive_create(file: UploadFile = File(...), kind: str = Form('SS'), year: int = Form(...), label: str = Form('')):
    """katalog, který existuje jen jako hotové PDF (starší ročníky, katalog od grafika)"""
    cat = catalogs.blank_catalog(kind, year, source='archive', status='done')
    if db.get_catalog(cat['code']): raise HTTPException(400, f'Katalog {cat["code"]} už existuje – PDF k němu přidej na jeho kartě.')
    cat['files'] = [await _store_pdf(file, cat['code'], label)]; db.save_catalog(cat); return cat

async def _store_pdf(file, code, label=''):
    raw = await file.read()
    if raw[:5] != b'%PDF-': raise HTTPException(400, 'Soubor není PDF')
    base = slugify(os.path.splitext(file.filename)[0]) or 'katalog'; fn = f'{base}.pdf'; i = 2
    while store.exists(f'vystupy/{fn}'): fn = f'{base}_{i}.pdf'; i += 1
    store.write(f'vystupy/{fn}', raw, 'application/pdf', pages=catalogs.pdf_pages(raw))
    return dict(label=label.strip() or 'PDF', path=f'vystupy/{fn}')

@app.get('/api/c/{code}')
def catalog_get(code: str):
    cat = need_catalog(code); c = catalogs.summary(cat); c['sections'] = db.list_sections(code)
    c['section_defs'] = [dict(key=k, **v) for k, v in SECTIONS.items()]
    return c

@app.put('/api/c/{code}')
def catalog_update(code: str, body: dict):
    cat = need_catalog(code)
    for k in ('title', 'year', 'doc_title', 'hero', 'prev', 'status', 'note'):
        if k in body: cat[k] = body[k]
    if cat.get('prev') == code: cat['prev'] = ''
    db.save_catalog(cat)
    if 'sections' in body:
        keep = set()
        for i, s in enumerate(body['sections']):
            if s.get('key') not in SECTIONS: continue
            keep.add(s['key']); db.save_section(code, dict(key=s['key'], title=s.get('title') or SECTIONS[s['key']]['title'], cz=s.get('cz') or SECTIONS[s['key']]['cz'],
                                                           color=s.get('color') or SECTIONS[s['key']]['color'], pages=s.get('pages') or [], sort=i))
        for s in db.list_sections(code):
            if s['key'] not in keep:
                if db.list_products(code, s['key']): raise HTTPException(400, f'Sekce „{s["cz"]}“ obsahuje produkty, nejde odebrat.')
                db.delete_section(code, s['key'])
    return catalog_get(code)

@app.delete('/api/c/{code}')
def catalog_delete(code: str):
    cat = need_catalog(code)
    if cat.get('status') == 'done' and cat.get('source') == 'db': raise HTTPException(423, 'Uzavřený katalog nejde smazat. Nejdřív ho odemkni.')
    if any(c.get('prev') == code for c in db.list_catalogs()): raise HTTPException(400, 'Na tento katalog navazuje novější katalog jako na loňský.')
    db.delete_catalog(code); return dict(ok=True)

@app.post('/api/c/{code}/files')
async def catalog_file_add(code: str, file: UploadFile = File(...), label: str = Form('')):
    cat = need_catalog(code); cat.setdefault('files', []).append(await _store_pdf(file, code, label)); db.save_catalog(cat); return catalogs.summary(cat)

@app.delete('/api/c/{code}/files')
def catalog_file_remove(code: str, path: str):
    """odebere PDF ze seznamu u katalogu (soubor na disku zůstává)"""
    cat = need_catalog(code); cat['files'] = [f for f in cat.get('files') or [] if f['path'] != path]; db.save_catalog(cat); return catalogs.summary(cat)

@app.get('/api/pdfcover')
def pdfcover(path: str):
    fp = catalogs.pdf_cover(path)
    if not fp: raise HTTPException(404)
    return FileResponse(fp, headers={'Cache-Control': 'public, max-age=86400, s-maxage=2592000'} if store.REMOTE else None)

@app.get('/thumb/{path:path}')
def thumb(path: str, w: int = 320):
    fp = catalogs.thumb(path, min(max(w, 60), 800))
    if not fp: raise HTTPException(404)
    return FileResponse(fp, headers={'Cache-Control': 'public, max-age=86400, s-maxage=2592000' if store.REMOTE else 'max-age=3600'})

# ---------- produkty katalogu ----------
@app.get('/api/c/{code}/meta')
def meta(code: str):
    cat = need_catalog(code)
    badges = sorted(os.path.basename(f['key'])[:-4] for f in store.walk('uploads/ikony') if f['key'].endswith('.png') and f['key'].count('/') == 2)
    prods = db.list_products(code)
    series = {}
    for p in prods: series.setdefault(p['section'], []); (series[p['section']].append(p['serie']) if p['serie'] and p['serie'] not in series[p['section']] else None)
    typs = {k: set() for k in SCHEMAS}
    for p in prods: typs.setdefault(p['section'], set()).add(p.get('typ') or '')
    secs = db.list_sections(code)
    return dict(season=code, catalog=dict(cat, label=catalogs.catalog_label(cat)), sections=[dict(key=s['key'], title=s['title'], cz=s['cz'], color=s['color']) for s in secs if s['key'] in SCHEMAS],
                schemas=SCHEMAS, spec_labels=SPEC_LABELS, genders=GENDERS,
                badges=[dict(name=b, file=f'uploads/ikony/{b}.png', label=BADGE_LABELS.get(b, b)) for b in badges], series=series,
                typs={k: sorted(v | set(SCHEMAS[k]['typ'])) for k, v in typs.items() if k in SCHEMAS})

@app.get('/api/c/{code}/products')
def products(code: str, section: str = None):
    cat = need_catalog(code); prods = db.list_products(code); ov = catalogs.overview(cat, prods); out = []
    for p in prods:
        if section and p['section'] != section: continue
        out.append(dict(id=p['id'], name=p['name'], section=p['section'], serie=p['serie'], sort=p['sort'], typ=p.get('typ'), new=p.get('new'),
                        thumb=p.get('hero') or next((c.get('front') for c in p['colors'] if c.get('front')), None), n_colors=len(p['colors']), prev=ov['status'].get(p['id'])))
    return dict(products=out, removed=ov['removed'], prev=ov['prev'], prev_kind=ov['kind'])

@app.get('/api/c/{code}/products/{pid}')
def product(code: str, pid: str):
    p = db.get_product(code, pid)
    if not p: raise HTTPException(404)
    return p

@app.post('/api/c/{code}/products')
def create(code: str, body: dict):
    need_catalog(code, write=True)
    section = body.get('section') or 'tents'; name = (body.get('name') or 'NOVÝ PRODUKT').strip()
    p = empty_product(section); p.update(body); p['name'] = name; p['season'] = code
    base = slugify(name) or 'produkt'; pid = base; i = 2
    while db.get_product(code, pid): pid = f'{base}_{i}'; i += 1
    p['id'] = pid; p['sort'] = db.next_sort(code, section)
    db.save_product(p); return p

@app.put('/api/c/{code}/products/{pid}')
def update(code: str, pid: str, body: dict):
    need_catalog(code, write=True); old = db.get_product(code, pid)
    if not old: raise HTTPException(404)
    body['id'] = pid; body['season'] = code
    if body.get('section') != old['section']: body['sort'] = db.next_sort(code, body['section'])
    db.save_product(body); return db.get_product(code, pid)

@app.delete('/api/c/{code}/products/{pid}')
def delete(code: str, pid: str): need_catalog(code, write=True); db.delete_product(code, pid); return dict(ok=True)

@app.post('/api/c/{code}/reorder')
def reorder(code: str, body: dict):
    need_catalog(code, write=True); db.renumber(code, body['section'], body['ids']); return dict(ok=True)

# ---------- předobjednávkový formulář ----------
@app.post('/api/c/{code}/form')
async def form_upload(code: str, files: List[UploadFile] = File(...)):
    """nahraje formulář (i víc souborů: camp + oblečení), uloží ho ke katalogu a vrátí návrh změn"""
    need_catalog(code, write=True); fs = [(f.filename, await f.read()) for f in files]
    try: parsed = orderform.parse(fs)
    except ValueError as e: raise HTTPException(400, str(e))
    if not parsed['models']: raise HTTPException(400, ' '.join(parsed['warnings']) or 'Ve formuláři nejsou žádné modely.')
    orderform.store(code, fs, parsed); return orderform.plan(code, parsed)

@app.get('/api/c/{code}/form')
def form_plan(code: str):
    need_catalog(code); return orderform.plan(code) or dict(none=True)

@app.post('/api/c/{code}/form/apply')
def form_apply(code: str, body: dict):
    need_catalog(code, write=True)
    try: return orderform.apply(code, body)
    except ValueError as e: raise HTTPException(400, str(e))

# ---------- loňská karta ----------
@app.post('/api/c/{code}/prev')
def prev_card(code: str, body: dict):
    """loňská karta k rozpracovanému produktu (posílá se celý záznam, aby rozdíly odpovídaly neuloženým úpravám) nebo podle klíče"""
    cat = need_catalog(code)
    if body.get('key'): return catalogs.prev_info(cat, key=body['key'])
    p = body.get('product') or {}; p.setdefault('id', ''); p.setdefault('name', '')
    return catalogs.prev_info(cat, p)

@app.get('/api/c/{code}/prevlist')
def prev_list(code: str):
    kind, pc, idx = catalogs.prev_index(need_catalog(code))
    return [dict(key=k, name=q['name'], section=q.get('section'), page=q.get('page')) for k, q in idx.items()]

@app.post('/api/c/{code}/restore')
def restore(code: str, body: dict):
    try: return catalogs.restore(need_catalog(code, write=True), body['key'])
    except ValueError as e: raise HTTPException(400, str(e))

@app.post('/api/upload')
async def upload(file: UploadFile = File(...), kind: str = Form('foto'), name: str = Form('')):
    """kind: foto | rozkresy | ikony | pages | hero | inner (PNG s průhledností)"""
    raw = await file.read()
    im = Image.open(io.BytesIO(raw)); im.load()
    sub = 'foto' if kind in ('foto', 'inner') else (kind if kind in ('rozkresy', 'ikony', 'pages', 'hero') else 'ostatni')
    h = hashlib.md5(raw).hexdigest()[:8]; base = slugify(name or os.path.splitext(file.filename)[0]) or 'obr'
    keep_alpha = kind in ('inner', 'rozkresy', 'ikony') and im.mode in ('RGBA', 'LA', 'P') and (im.convert('RGBA').getextrema()[3][0] < 255)
    if keep_alpha:
        im = im.convert('RGBA'); im.thumbnail((1600, 1600)); fn = f'{base}_{h}.png'; _put_image(im, f'uploads/{sub}/{fn}', 'PNG', optimize=True)
    else:
        if im.mode in ('RGBA', 'LA', 'P'):
            bg = Image.new('RGB', im.size, (255, 255, 255)); im = im.convert('RGBA'); bg.paste(im, mask=im.split()[-1]); im = bg
        big = 3000 if kind in ('hero', 'pages') else 1600
        im = im.convert('RGB'); im.thumbnail((big, big)); fn = f'{base}_{h}.jpg'; _put_image(im, f'uploads/{sub}/{fn}', 'JPEG', quality=88, optimize=True)
    return dict(path=f'uploads/{sub}/{fn}', w=im.width, h=im.height)

def _put_image(im, key, fmt, **kw):
    b = io.BytesIO(); im.save(b, fmt, **kw); store.write(key, b.getvalue(), shot=generate.white_corners(im))

def _save_image(im, sub, base, force_png=False):
    has_alpha = im.mode in ('RGBA', 'LA') and im.getextrema()[-1][0] < 255
    b = io.BytesIO()
    if has_alpha or force_png:
        im = im.convert('RGBA'); im.save(b, 'PNG', optimize=True); ext = 'png'
    else:
        if im.mode != 'RGB':
            bg = Image.new('RGB', im.size, (255, 255, 255)); im = im.convert('RGBA'); bg.paste(im, mask=im.split()[-1]); im = bg
        im.save(b, 'JPEG', quality=88, optimize=True); ext = 'jpg'
    h = hashlib.md5(b.getvalue()).hexdigest()[:8]; fn = f'{base}_{h}.{ext}'
    store.write(f'uploads/{sub}/{fn}', b.getvalue(), shot=generate.white_corners(im))
    return dict(path=f'uploads/{sub}/{fn}', w=im.width, h=im.height)

def _load_upload(path):
    if not path.startswith('uploads/') or '..' in path: raise HTTPException(400, 'neplatná cesta')
    if not store.exists(path): raise HTTPException(404, 'soubor neexistuje')
    im = Image.open(store.local(path)); im.load(); return im, path.split('/')[1], re.sub(r'_[0-9a-f]{8}$', '', os.path.splitext(os.path.basename(path))[0])

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
    """Úprava fotky: op = rotate(deg) | flip | crop(x,y,w,h v poměrech 0–1) | trim | pad(factor) | whiten(thresh) | alpha(thresh)"""
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
    elif op == 'pad':
        # factor < 1: zmenšit = přidat okraj (bílý, u PNG průhledný); factor > 1: zvětšit = ubrat okraj, ale nikdy neoříznout samotný produkt
        f = float(body.get('factor', 0.9)); w, h = im.size; alpha = im.mode == 'RGBA'
        if f < 1:
            nw, nh = int(round(w / f)), int(round(h / f)); src = im if alpha else im.convert('RGB')
            canvas = Image.new('RGBA' if alpha else 'RGB', (nw, nh), (255, 255, 255, 0) if alpha else (255, 255, 255))
            canvas.paste(src, ((nw - w) // 2, (nh - h) // 2)); im = canvas; im.thumbnail((3000, 3000)); force_png = alpha
        else:
            if alpha: bb = im.split()[-1].point(lambda v: 255 if v > 8 else 0).getbbox()
            else: bb = ImageChops.difference(im.convert('RGB'), Image.new('RGB', im.size, (255, 255, 255))).convert('L').point(lambda v: 255 if v > 18 else 0).getbbox()
            bb = bb or (0, 0, w, h); dx, dy = (w - w / f) / 2, (h - h / f) / 2
            box = (int(min(dx, bb[0])), int(min(dy, bb[1])), int(max(w - dx, bb[2])), int(max(h - dy, bb[3])))
            if box == (0, 0, w, h): raise HTTPException(400, 'Fotka už nemá žádný okraj, který by šel ubrat. Produkt je až u kraje.')
            im = im.crop(box); force_png = alpha
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

@app.post('/api/compose')
def compose(body: dict):
    """složí hlavní fotku batohu: zadní pohled menší vlevo, přední větší vpravo (jako v SS26)"""
    from PIL import ImageChops
    def load_trim(path):
        im, sub, base = _load_upload(path); rgb = im.convert('RGB')
        m = _edge_mask(rgb, int(body.get('thresh', 30))); rgb = Image.composite(Image.new('RGB', rgb.size, (255, 255, 255)), rgb, m)
        bb = ImageChops.difference(rgb, Image.new('RGB', rgb.size, (255, 255, 255))).convert('L').point(lambda v: 255 if v > 18 else 0).getbbox()
        return (rgb.crop(bb) if bb else rgb), base
    front, base = load_trim(body['front']); back, _ = load_trim(body['back'])
    H = 1200; fr = front.resize((int(front.width * H / front.height), H)); bh = int(H * float(body.get('back_scale', 0.72))); bk = back.resize((int(back.width * bh / back.height), bh))
    gap = int(H * float(body.get('gap', -0.04)))   # záporná mezera = mírný překryv
    W = bk.width + gap + fr.width; canvas = Image.new('RGB', (max(W, 1), H), (255, 255, 255))
    canvas.paste(bk, (0, H - bk.height)); canvas.paste(fr, (bk.width + gap, 0))
    pad = int(H * 0.03); out = Image.new('RGB', (canvas.width + 2 * pad, H + 2 * pad), (255, 255, 255)); out.paste(canvas, (pad, pad))
    return _save_image(out, 'foto', re.sub(r'_front$', '', base) + '_composite')

@app.get('/api/library')
def library(q: str = '', sub: str = ''):
    out = []
    for f in store.walk('uploads'):
        parts = f['key'].split('/'); d = parts[1] if len(parts) > 2 else ''; name = parts[-1]
        if not d or (sub and d != sub) or (d in ('pages', 'prev') and sub != d) or not name.lower().endswith(('.jpg', '.jpeg', '.png')): continue
        if q and q.lower() not in name.lower(): continue
        out.append(dict(path=f['key'], name=name, sub=d, mtime=f['mtime']))
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

@app.get('/api/storage')
def storage(q: str = '', folder: str = '', used: str = '', catalog: str = ''):
    return catalogs.storage(q, folder, used, catalog)

@app.delete('/api/storage')
def storage_delete(path: str):
    """smaže soubor z úložiště – jen když ho žádný katalog nepoužívá"""
    if not path.startswith('uploads/') or '..' in path: raise HTTPException(400, 'neplatná cesta')
    use = catalogs.photo_usage().get(path)
    if use: raise HTTPException(400, f'Soubor je použitý ({use[0]["catalog"]} · {use[0].get("name") or use[0]["what"]}).')
    store.delete(path)
    return dict(ok=True)

@app.get('/api/c/{code}/preview/{pid}', response_class=HTMLResponse)
def preview(code: str, pid: str):
    p = db.get_product(code, pid)
    if not p: raise HTTPException(404)
    return generate.render_card_preview(p, IMG, _sec_color(code, p['section']))

@app.post('/api/c/{code}/preview', response_class=HTMLResponse)
def preview_draft(code: str, body: dict):
    body.setdefault('colors', []); body.setdefault('id', 'draft'); body.setdefault('name', '')
    return generate.render_card_preview(body, IMG, _sec_color(code, body.get('section')))

@app.get('/nahled/{code}', response_class=HTMLResponse)
def live_catalog(code: str):
    """celý katalog vykreslený rovnou z databáze – ukazuje uložené změny hned, bez generování"""
    cat = need_catalog(code)
    return HTMLResponse(generate.render_document(cat, db.list_products(code), db.list_sections(code), IMG), headers={'Cache-Control': 'no-store'})

def _sec_color(code, section): return next((s['color'] for s in db.list_sections(code) if s['key'] == section), None)

_gen_lock = threading.Lock()
@app.post('/api/c/{code}/generate')
def gen(code: str, body: dict):
    cat = need_catalog(code, write=True)
    if not _gen_lock.acquire(blocking=False): raise HTTPException(409, 'Generování už běží')
    log = []; cfg = generate.catalog_cfg(cat)
    try:
        generate.build(code, pdf=bool(body.get('pdf', True)), log=log.append)
        if body.get('push') and not store.REMOTE: generate.git_push(log=log.append, dirs=[os.path.relpath(os.path.dirname(cfg['out_html']), REPO)])
    except Exception as e: log.append('CHYBA: ' + str(e))
    finally: _gen_lock.release()
    return dict(log='\n'.join(log), html='/repo/' + os.path.relpath(cfg['out_html'], REPO), pdf=store.url(os.path.relpath(cfg['out_pdf'], REPO)))

if __name__ == '__main__':
    import uvicorn, webbrowser, socket
    if 'KATALOG_AUTH' not in os.environ: auth.ENABLED = False   # lokální spuštění na vlastním počítači je bez přihlášení
    if not os.path.exists(db.DB_PATH): print('Databáze neexistuje, spusť nejdřív: python3 admin/import_catalog.py')
    port = int(os.environ.get('PORT', 8765))
    for cand in range(port, port + 10):
        with socket.socket() as sk:
            if sk.connect_ex(('127.0.0.1', cand)) != 0: port = cand; break
    url = f'http://localhost:{port}'
    print(f'Administrace běží na {url}  (ukončení: Ctrl+C)')
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
