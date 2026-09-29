"""Administrace katalogu TRIMM. Spuštění: python3 admin/app.py  ->  http://localhost:8765"""
import os, re, io, json, hashlib, unicodedata, threading
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
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
    import uvicorn, webbrowser, threading
    if not os.path.exists(db.DB_PATH): print('Databáze neexistuje, spusť nejdřív: python3 admin/import_catalog.py')
    threading.Timer(1.0, lambda: webbrowser.open('http://localhost:8765')).start()
    uvicorn.run(app, host='127.0.0.1', port=8765, log_level='warning')
