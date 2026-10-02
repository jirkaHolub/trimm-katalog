"""Generátor katalogu (HTML + PDF) z databáze. Přenesený z ss27/nastroje/build_html.py."""
import os, re, html, collections, math, subprocess, json
from PIL import Image
import db, store
from schemas import SECTIONS as SEC_DEF, SERIE_COLORS

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, '..'))
E = html.escape
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

def catalog_cfg(cat):
    """cesty a popisky pro generování z uloženého záznamu katalogu"""
    code = cat['code']; out_html = cat.get('out_html') or f'{code.lower()}/trimm_katalog_{code}.html'
    return dict(title=cat.get('title') or '', year=cat.get('year') or '', label=f'{cat.get("title") or ""} {cat.get("year") or ""}'.strip(),
                out_html=os.path.join(REPO, out_html), out_pdf=os.path.join(REPO, cat.get('out_pdf') or f'vystupy/trimm_katalog_{code}_CZ.pdf'),
                img_prefix='../' * (out_html.count('/')) + 'admin/', hero=cat.get('hero') or '', doc_title=cat.get('doc_title') or f'TRIMM — Katalog {code}')

def serie_key(s): return (s or 'OSTATNÍ').upper().replace(' SERIE', '').strip()
def serie_color(sec, s, sec_color):
    k = serie_key(s)
    if 'ACCESSORIES' in k: return '#777'
    return SERIE_COLORS.get(k, sec_color)
def slug(s): return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
def price(r):
    if not r.get('price_min'): return ''
    f = lambda v: f'{int(v):,}'.replace(',', ' ')
    return (f'od {f(r["price_min"])} Kč' if r.get('price_max') and r['price_max'] != r['price_min'] else f'{f(r["price_min"])} Kč')

I = {
 'weight':'<svg viewBox="0 0 24 24"><path d="M12 3a3 3 0 0 1 3 3H9a3 3 0 0 1 3-3z"/><path d="M5 8h14l2 12H3z"/></svg>',
 'pack':'<svg viewBox="0 0 24 24"><path d="M3 8l9-4 9 4v9l-9 4-9-4z"/><path d="M3 8l9 4 9-4M12 12v9"/></svg>',
 'persons':'<svg viewBox="0 0 24 24"><circle cx="12" cy="7" r="3.5"/><path d="M5 21a7 7 0 0 1 14 0"/></svg>',
 'dims':'<svg viewBox="0 0 24 24"><path d="M3 17L17 3l4 4L7 21z"/><path d="M8 12l2 2M11 9l2 2M14 6l2 2"/></svg>',
 'volume':'<svg viewBox="0 0 24 24"><path d="M6 3h12l1 18H5z"/><path d="M8 9h8"/></svg>',
 'length':'<svg viewBox="0 0 24 24"><path d="M3 12h18M3 8v8M21 8v8"/></svg>',
 'width':'<svg viewBox="0 0 24 24"><path d="M3 12h18M7 8l-4 4 4 4M17 8l4 4-4 4"/></svg>',
 'thickness':'<svg viewBox="0 0 24 24"><path d="M3 9h18v6H3z"/><path d="M12 3v6M12 15v6"/></svg>',
 'rvalue':'<svg viewBox="0 0 24 24"><path d="M12 3v18M6 6l12 12M6 18L18 6"/></svg>',
 'size':'<svg viewBox="0 0 24 24"><path d="M8 3l4 3 4-3 4 4-3 3v11H7V10L4 7z"/></svg>',
 'pcs':'<svg viewBox="0 0 24 24"><path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/></svg>',
 'men':'<svg viewBox="0 0 24 24"><circle cx="10" cy="14" r="6"/><path d="M14.5 9.5L21 3M15 3h6v6"/></svg>',
 'women':'<svg viewBox="0 0 24 24"><circle cx="12" cy="9" r="6"/><path d="M12 15v7M9 19h6"/></svg>',
 'kids':'<svg viewBox="0 0 24 24"><circle cx="12" cy="6" r="3"/><path d="M8 22v-8l-2-3 3-2h6l3 2-2 3v8"/></svg>',
 'uni':'<svg viewBox="0 0 24 24"><circle cx="8" cy="12" r="5"/><circle cx="16" cy="12" r="5"/></svg>',
}
def icon(k, title=''): return f'<span class="ic" title="{E(title)}">{I[k]}</span>'
GENDER_CZ = {'men': 'Pánské', 'women': 'Dámské', 'kids': 'Dětské', 'uni': 'Unisex'}
TYP_LABEL = {'s.p.': 'spací pytel', 'lodní': 'lodní vak', 'vodní': 'vodní vak', 'kompresní': 'kompresní vak', 'bivakovací': 'bivakovací pytel', 'náhradní': 'náhradní díl', 'tyčky': 'tyčky', 'vložka': 'vložka do spacáku'}
SMALL_TYP = {'polštář', 'peněženka', 'pásek', 'nákrčník', 'kšiltovka', 'čepice', 'láhev', 'kolík', 'tyčky', 'náhradní', 'konektor'}

_shots = {}
def white_corners(im):
    im = im.convert('RGBA'); bg = Image.new('RGBA', im.size, (255, 255, 255, 255)); bg.alpha_composite(im); im = bg.convert('L'); w, h = im.size
    pts = [(3, 3), (w - 4, 3), (3, h - 4), (w - 4, h - 4), (w // 2, 3), (3, h // 2), (w - 4, h // 2)]
    return sum(im.getpixel(p) for p in pts) / len(pts) > 235

class Renderer:
    def __init__(self, img_prefix):
        self.pfx = img_prefix
        self.sized = img_prefix == '/'   # zobrazení přímo z aplikace: místo originálů (až 1600 px) posílat zmenšeniny podle velikosti v kartě
    def src(self, path, w=700):
        if self.sized and path.startswith('uploads/'): return E(f'/thumb/{path}?w={w}')
        return E(self.pfx + path)
    def is_product_shot(self, path):
        """produktová fotka na bílém pozadí (ne lifestylová) – jen taková se ukazuje jako zadní pohled"""
        try:
            st = store.stat(path) or {}
            if 'shot' in st: return bool(st['shot'])
            k = (path, st.get('mtime'))
            if k not in _shots:
                im = Image.open(store.local(path, st)); im.draft('L', (200, 200))   # JPEG se dekóduje rovnou zmenšený
                _shots[k] = white_corners(im)
            return _shots[k]
        except Exception: return False

    def spec_chips(self, r):
        S = r.get('specs') or {}; out = []
        def chip(k, v, t):
            if v: out.append(f'<span class="chip-spec">{icon(k, t)}<b>{E(str(v))}</b></span>')
        chip('persons', S.get('persons'), 'Počet osob'); chip('weight', S.get('weight'), 'Hmotnost'); chip('volume', S.get('volume'), 'Objem')
        chip('length', S.get('length'), 'Délka'); chip('width', S.get('width'), 'Šířka'); chip('thickness', S.get('thickness'), 'Tloušťka'); chip('rvalue', S.get('rvalue') and 'R ' + S['rvalue'], 'R-value')
        if r['section'] != 'tents': chip('dims', S.get('dims'), 'Rozměr')
        elif S.get('dims') and not (r.get('fields') or {}).get('ROZMĚR'): chip('dims', S.get('dims'), 'Rozměr')
        chip('pack', S.get('pack'), 'Sbalený rozměr'); chip('pcs', S.get('pcs'), 'Počet kusů v balení')
        return ''.join(out)
    def temps_html(self, r):
        T = (r.get('specs') or {}).get('temps')
        if not T or not any(T.get(k) for k in ('comfort', 'limit', 'extreme')): return ''
        def cell(lbl, v, cls): return f'<div class="t {cls}"><span class="tv">{E(str(v))}°</span><span class="tl">{lbl}</span></div>' if v not in (None, '') else ''
        return '<div class="temps">' + cell('comfort', T.get('comfort'), 'tc') + cell('limit', T.get('limit'), 'tli') + cell('extreme', T.get('extreme'), 'tex') + '</div>'
    def photos_html(self, r):
        cls = 'photo'
        if r.get('typ') in SMALL_TYP: cls += ' small'
        if r.get('wide'): cls += ' wide'
        if r.get('hero') and r.get('hero_back'):
            return f'<div class="{cls} has-hero"><img class="p-back" src="{self.src(r["hero_back"])}" alt="{E(r["name"])} – zadní strana" loading="lazy"><img class="p-front" src="{self.src(r["hero"])}" alt="{E(r["name"])}" loading="lazy"></div>'
        if r.get('hero') and r.get('hero_inner'):
            return f'<div class="{cls} has-hero two"><img class="p-hero" src="{self.src(r["hero"])}" alt="{E(r["name"])}" loading="lazy"><img class="p-inner" src="{self.src(r["hero_inner"])}" alt="{E(r["name"])} – vnitřní stan" loading="lazy"></div>'
        if r.get('hero'):
            return f'<div class="{cls} has-hero"><img class="p-hero" src="{self.src(r["hero"])}" alt="{E(r["name"])}" loading="lazy"></div>'
        fronts = [c for c in r['colors'] if c.get('front')]
        fronts = sorted(fronts, key=lambda c: (0 if c.get('main') else 1, 0 if c.get('back') else 1, 1 if c.get('generic') else 0, r['colors'].index(c)))
        if not fronts: return f'<div class="{cls}"><div class="ph"><span class="ph-n">{E(r["name"])}</span><span class="ph-t">foto doplníme</span></div></div>'
        c = fronts[0]; imgs = ''
        if r.get('hero_reverse'):   # oboustranná bunda: rub + zadek + předek (jako DOUBLE ve FW 26/27)
            cls += ' three'; imgs += f'<img class="p-rev" src="{self.src(r["hero_reverse"])}" alt="{E(r["name"])} – rubová strana" loading="lazy">'
        if c.get('back') and r['section'] in ('sportswear', 'backpacks') and self.is_product_shot(c['back']): imgs += f'<img class="p-back" src="{self.src(c["back"])}" alt="{E(r["name"])} – zadní strana" loading="lazy">'
        imgs += f'<img class="p-front" src="{self.src(c["front"])}" alt="{E(r["name"])}" loading="lazy">'
        return f'<div class="{cls}">{imgs}</div>'
    def badges_html(self, r):
        if not r.get('badges'): return ''
        return '<div class="badges">' + ''.join(f'<img src="{self.src(b["file"], 240)}" alt="{E(b.get("label") or "")}" title="{E(b.get("label") or "")}" loading="lazy">' for b in r['badges'] if b.get('file')) + '</div>'
    def draw_html(self, r):
        if not r.get('draw'): return ''
        return f'<div class="draw"><img src="{self.src(r["draw"])}" alt="{E(r["name"])} – rozměry" loading="lazy"></div>'
    def colors_html(self, r):
        items = []
        for i, c in enumerate(r['colors']):
            art = c.get('art') or (c.get('front') if not c.get('generic') else None)
            img = f'<img class="c-art{" c-photo" if not c.get("art") else ""}" src="{self.src(art, 200)}" alt="{E(r["name"])} {E(c["name"])}" loading="lazy">' if art else '<span class="c-none" title="vizuál doplníme"></span>'
            items.append(f'<div class="c-item" title="{E(c["name"])}"><div class="c-n">{i + 1}</div>{img}<div class="c-name">{E(c["name"])}</div></div>')
        return f'<div class="colors">{"".join(items)}</div>'
    def fields_html(self, r):
        return ''.join(f'<div class="mat"><span class="mat-l">{E(k)}</span><span class="mat-v">{E(v)}</span></div>' for k, v in (r.get('fields') or {}).items() if v)
    def feats_html(self, r):
        out = ''
        if r.get('features'): out += '<div class="feat"><div class="feat-l">VLASTNOSTI</div><ul>' + ''.join(f'<li>{E(f)}</li>' for f in r['features']) + '</ul></div>'
        if r.get('activities'): out += '<div class="feat"><div class="feat-l">AKTIVITY</div><ul>' + ''.join(f'<li>{E(f)}</li>' for f in r['activities']) + '</ul></div>'
        return out
    def est_height(self, r):
        ch = lambda t, w: max(1, math.ceil(len(t) / w))
        F = r.get('fields') or {}; S = r.get('specs') or {}
        left = sum(14 + 16 * ch(v, 42) + 9 for v in F.values() if v) + (17.5 * ch(r.get('desc') or '', 46) + 8 if r.get('desc') else 0)
        right = (18 + 16 * len(r.get('features') or []) + 12 if r.get('features') else 0) + (18 + 16 * len(r.get('activities') or []) + 12 if r.get('activities') else 0)
        for f in r.get('features') or []: right += 16 * (ch(f, 34) - 1)
        h = 22 + 46 + (300 if r.get('wide') else 240) + 44 + 32 + (50 if r.get('badges') else 0) + (46 if S.get('temps') else 0) + max(left, right)
        if r.get('draw'): h += 18 + 110
        n = len(r['colors']); h += 12 + (100 if n < 7 else 100 * math.ceil(n / 6))
        return h
    def card(self, r, sec_color):
        sec = r['section']; sk = serie_key(r.get('serie')); sc = serie_color(sec, r.get('serie'), sec_color)
        eh = self.est_height(r); dense = ' dense2' if eh > 1080 else (' dense' if eh > 960 else '')
        g = r.get('gender') or None; meta = ''
        if g: meta += f'<span class="g" title="{GENDER_CZ[g]}">{icon(g, GENDER_CZ[g])}<span>{GENDER_CZ[g]}</span></span>'
        meta += f'<span class="typ">{E(TYP_LABEL.get(r.get("typ") or "", r.get("typ") or ""))}</span>'
        S = r.get('specs') or {}
        if S.get('size'): meta += f'<span class="size">{E(S["size"])}</span>'
        badge = '<span class="new">Novinka</span>' if r.get('new') else ''
        search = ' '.join([r['name'], r.get('typ') or '', sk] + [c['name'] for c in r['colors']]).lower()
        desc = f'<p class="desc">{E(r["desc"])}</p>' if r.get('desc') else '<p class="desc ph-desc">Popis doplníme.</p>'
        return f'''<article class="card{dense}" id="m-{r['id']}" data-eh="{int(eh)}" data-sec="{sec}" data-serie="{E(slug(sk))}" data-g="{g or ''}" data-s="{E(search)}" style="--sc:{sc}">
<div class="head"><div class="head-l"><h3>{E(r['name'])}</h3>{badge}</div><span class="dmoc"><span class="dmoc-l">DMOC</span>{E(price(r))}</span></div>
{self.photos_html(r)}
<div class="meta">{meta}</div>
<div class="rest"><div class="specs">{self.spec_chips(r)}</div>
{self.badges_html(r)}
{self.temps_html(r)}
<div class="body"><div class="mats">{self.fields_html(r)}{desc}</div><div class="feats">{self.feats_html(r)}</div></div>
{self.draw_html(r)}
{self.colors_html(r)}</div>
</article>'''

def groups(items):
    g = []
    for r in items:
        k = serie_key(r.get('serie'))
        if g and g[-1][0] == k: g[-1][1].append(r)
        else: g.append((k, [r]))
    od = collections.OrderedDict(); seen = collections.Counter()
    for k, v in g:
        seen[k] += 1; od[k if seen[k] == 1 else f'{k} #{seen[k]}'] = v
    return od

def css(img_prefix, hero, label=''):
    return CSS_BASE.replace('__HERO__', (f'/thumb/{hero}?w=1600' if img_prefix == '/' else img_prefix + hero) if hero else '').replace('__LABEL__', label.replace('"', ''))

def render_document(cat, products, sections, img_prefix):
    R = Renderer(img_prefix); cfg = catalog_cfg(cat)
    by_sec = collections.OrderedDict((s['key'], []) for s in sections)
    for r in products:
        by_sec.setdefault(r['section'], []).append(r)
    toc = ''; body = ''; chips = ''
    for s in sections:
        sec = s['key']; items = by_sec.get(sec, []); gs = groups(items)
        toc += f'<div class="toc-sec" style="--tc:{s["color"]}"><a href="#sec-{sec}" class="toc-h"><span class="toc-dot"></span>{E(s["title"])}<span class="toc-cz">{E(s["cz"])}</span><span class="toc-cnt">{len(items)}</span></a><div class="toc-series">'
        tc = collections.OrderedDict()
        for k, v in gs.items(): tc.setdefault(k.split(' #')[0], [k, 0]); tc[k.split(' #')[0]][1] += len(v)
        toc += ''.join(f'<a href="#s-{sec}-{slug(k0)}" class="toc-s" data-sec="{sec}"><i style="background:{serie_color(sec, k0, s["color"])}"></i>{E(k0)}<span>{n}</span></a>' for k0, (k, n) in tc.items())
        toc += '</div></div>'
        chips += f'<button class="chip" data-f="{sec}" style="--tc:{s["color"]}">{E(s["cz"].upper())}</button>'
        pages = ''.join(f'<img src="{R.src(p, 1600)}" alt="Technické informace" loading="lazy">' for p in (s.get('pages') or []) if store.exists(p))
        info = f'<div class="info-pages">{pages}</div>' if pages else ''
        body += f'<section class="sec" id="sec-{sec}" data-sec="{sec}" style="--tc:{s["color"]}"><div class="sec-head"><div class="sec-bar"></div><div><h2>{E(s["title"])}</h2><div class="sec-cz">{E(s["cz"])}</div></div><span class="sec-cnt">{len(items)} modelů</span></div>{info}'
        for k, v in gs.items():
            k0 = k.split(' #')[0]; col = serie_color(sec, k0, s['color'])
            body += f'<div class="serie" id="s-{sec}-{slug(k)}" data-serie="{slug(k0)}" style="--sc:{col}"><div class="serie-head"><div class="serie-bar"></div><h3>{E(k0)}{"" if "ACCESSORIES" in k0 or k0 in ("WATERPROOF", "WATERBLADDER", "BACKPACKS") else " SERIE"}</h3><span class="serie-cnt">{len(v)}</span></div><div class="grid">'
            body += ''.join(R.card(r, s['color']) for r in v)
            body += '</div></div>'
        body += '</section>'
    n_new = sum(1 for r in products if r.get('new'))
    n_series = sum(len({k.split(' #')[0] for k in groups(v)}) for v in by_sec.values())
    return f'''<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<title>{E(cfg['doc_title'])}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{css(img_prefix, cfg['hero'], cfg['label'])}</style>
</head>
<body>
<section class="hero" aria-label="TRIMM {E(cfg['label'])}"><div><div class="brand">TRIMM · OUTDOOR PRODUCTS</div><h1>{E(cfg['title'])} <span>{E(cfg['year'])}</span></h1><div class="sub">KATALOG · CZ</div></div></section>
<section class="toc">
 <div class="toc-title">CONTENT</div>
 <div class="toc-grid">{toc}</div>
 <div class="stats-row">
  <div><div class="stat-n">{len(products)}</div><div class="stat-l">MODELŮ</div></div>
  <div><div class="stat-n">{n_series}</div><div class="stat-l">SÉRIÍ</div></div>
  <div><div class="stat-n">{n_new}</div><div class="stat-l">NOVINEK</div></div>
 </div>
</section>
<div class="fbar">
 <input type="search" id="q" placeholder="Vyhledat model, barvu, typ">
 <div class="chips f"><button class="chip active" data-f="all">VŠE</button>{chips}</div>
 <div class="chips g"><button class="chip active" data-g="all">VŠICHNI</button><button class="chip" data-g="men">PÁNSKÉ</button><button class="chip" data-g="women">DÁMSKÉ</button><button class="chip" data-g="kids">DĚTSKÉ</button></div>
 <span class="fcount" id="cnt"></span>
</div>
<main id="products">
{body}
</main>
<footer><b>TRIMM</b><br>Chebská 79/23, 322 00 Plzeň, Czech Republic<br>Tel.: +420 377 822 236 · E-mail: trimm@trimm.eu · www.trimm.eu<div class="sub">{E(cfg['label'])} · CENY DMOC V KČ VČETNĚ DPH · ZMĚNY VYHRAZENY</div></footer>
<script>{JS}</script>
</body>
</html>'''

def render_card_preview(r, img_prefix, sec_color=None):
    sec = dict(SEC_DEF.get(r['section'], {})); R = Renderer(img_prefix)
    if sec_color: sec['color'] = sec_color
    return f'''<!DOCTYPE html><html lang="cs"><head><meta charset="UTF-8"><style>{css(img_prefix, "")}
body{{background:#f6f6f4;padding:12px}}.grid{{grid-template-columns:1fr;max-width:460px;border:1px solid #e4e4e4}}.card{{min-height:0;border-right:none!important}}.card>.rest{{min-height:0}}</style></head>
<body><div class="grid" style="--tc:{sec.get('color', '#888')}">{R.card(r, sec.get('color', '#888'))}</div></body></html>'''

def build(season='SS27', pdf=True, log=print):
    cat = db.get_catalog(season)
    if not cat: raise ValueError(f'Katalog {season} neexistuje')
    cfg = catalog_cfg(cat)
    products = db.list_products(season); sections = db.list_sections(season)
    doc = render_document(cat, products, sections, cfg['img_prefix'])
    key_html = os.path.relpath(cfg['out_html'], REPO); key_pdf = os.path.relpath(cfg['out_pdf'], REPO); fn = os.path.basename(key_html)
    store.write(key_html, doc.encode('utf-8'), 'text/html; charset=utf-8', max_age=60)
    idx = os.path.dirname(key_html) + '/index.html'
    if not store.exists(idx):
        store.write(idx, f'<!DOCTYPE html>\n<html lang="cs">\n<head>\n<meta charset="utf-8">\n<title>{E(cfg["doc_title"])}</title>\n<meta http-equiv="refresh" content="0; url={fn}">\n<link rel="canonical" href="{fn}">\n</head>\n<body>\n<p>Přesměrování na <a href="{fn}">katalog</a>…</p>\n</body>\n</html>\n'.encode('utf-8'), 'text/html; charset=utf-8')
    log(f'HTML: {key_html} ({len(doc) // 1024} kB, {len(products)} modelů)')
    if pdf:
        if store.REMOTE:   # online: Chrome tiskne z dočasného souboru
            work = os.path.join(store.TMP, 'print'); os.makedirs(work, exist_ok=True); src = os.path.join(work, fn); out = os.path.join(work, os.path.basename(key_pdf))
            import catalogs
            root = store.overlay([k for k, u in catalogs.photo_usage().items() if any(x['catalog'] == season for x in u)])   # obrázky pod jednou složkou, ať je Chrome čte z disku
            open(src, 'w', encoding='utf-8').write(render_document(cat, products, sections, 'file://' + root + '/'))
        else:
            src = cfg['out_html']; out = cfg['out_pdf']; os.makedirs(os.path.dirname(out), exist_ok=True)
        if os.path.exists(out) and store.REMOTE: os.remove(out)
        cmd = [chrome_path(), '--headless=new', '--disable-gpu', '--no-pdf-header-footer', f'--print-to-pdf={out}', '--virtual-time-budget=30000',
               '--run-all-compositor-stages-before-draw'] + (['--no-sandbox', '--disable-dev-shm-usage', f'--user-data-dir={os.path.join(store.TMP, "chrome")}'] if store.REMOTE else []) + ['file://' + src]
        r = subprocess.run(cmd, capture_output=True, timeout=280 if store.REMOTE else 600)
        if not os.path.exists(out): raise RuntimeError('PDF se nepodařilo vytvořit: ' + (r.stderr.decode('utf-8', 'ignore')[-400:] or 'Chrome nic nevrátil'))
        try:
            import fitz; d = fitz.open(out); n = len(d); cnt = collections.Counter(p.get_text().count('DMOC') for p in d); d.close()
            log(f'PDF: {key_pdf} ({n} stran; stránky se 2 kartami: {cnt.get(2, 0)}, s 1: {cnt.get(1, 0)})')
        except Exception as e: n = None; log(f'PDF hotovo ({e})')
        if store.REMOTE: store.write(key_pdf, open(out, 'rb').read(), 'application/pdf', max_age=60, pages=n)
    return cfg

def chrome_path():
    for c in (os.environ.get('CHROME'), CHROME, '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome'):
        if c and os.path.exists(c): return c
    raise RuntimeError('Nenašel jsem Chrome/Chromium pro tisk PDF.')

def git_push(log=print, dirs=()):
    for cmd in (['git', 'add', '-A', 'admin', 'vystupy', *dirs], ['git', 'commit', '-q', '-m', 'Katalog: aktualizace z administrace'], ['git', 'push']):
        p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        log('$ ' + ' '.join(cmd) + (('\n' + (p.stdout + p.stderr).strip()) if (p.stdout + p.stderr).strip() else ''))

CSS_BASE = r'''
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#f6f6f4;--card:#fff;--text:#1a1a1a;--muted:#777;--border:#e4e4e4;--accent:#ff6b1a;--sc:#888;--tc:#888}
html{background:var(--bg);color:var(--text);font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:13px;line-height:1.5;-webkit-font-smoothing:antialiased}
body{width:min(100%,104rem);margin:0 auto;background:var(--bg)}
svg{width:1em;height:1em;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.ic{display:inline-flex;font-size:16px;color:var(--accent);margin-right:5px;vertical-align:middle}
.hero{position:relative;background:#fff url("__HERO__") center/cover no-repeat;min-height:420px;display:flex;align-items:flex-end;padding:60px;color:#fff;overflow:hidden}
.hero::after{content:'';position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,0) 35%,rgba(0,0,0,.6) 100%);mask:linear-gradient(90deg,#000 0,#000 55%,transparent 85%);-webkit-mask:linear-gradient(90deg,#000 0,#000 55%,transparent 85%)}
.hero>div{position:relative;z-index:1}
.hero .brand{font-size:14px;letter-spacing:.35em;font-weight:800;opacity:.9}
.hero h1{font-size:clamp(34px,6vw,84px);font-weight:900;letter-spacing:.02em;line-height:1;margin-top:10px}
.hero h1 span{color:#ffe600}
.hero .sub{margin-top:12px;font-size:13px;letter-spacing:.2em;opacity:.85}
.toc{background:#fff;border-bottom:1px solid var(--border);padding:44px 60px}
.toc-title{font-size:26px;font-weight:800;letter-spacing:.03em;margin-bottom:24px}
.toc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.toc-sec{background:#f7f7f5;border-left:5px solid var(--tc);border-radius:3px;padding:14px 16px}
.toc-h{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--text);font-size:13px;font-weight:800;letter-spacing:.06em}
.toc-h:hover{color:var(--tc)}
.toc-dot{width:10px;height:10px;border-radius:50%;background:var(--tc);flex-shrink:0}
.toc-cz{color:var(--muted);font-weight:400;letter-spacing:0;font-size:12px}
.toc-cnt{margin-left:auto;background:var(--tc);color:#fff;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:800}
.toc-series{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.toc-s{display:inline-flex;align-items:center;gap:6px;padding:4px 9px;background:#fff;border:1px solid var(--border);border-radius:20px;text-decoration:none;color:#333;font-size:10px;font-weight:700;letter-spacing:.05em}
.toc-s i{width:8px;height:8px;border-radius:50%;display:inline-block}
.toc-s span{color:var(--muted);font-weight:400}
.toc-s:hover{border-color:#999}
.stats-row{display:flex;gap:50px;margin-top:34px;padding-top:26px;border-top:1px solid var(--border)}
.stat-n{font-size:42px;font-weight:900;line-height:1}
.stat-l{font-size:10px;letter-spacing:.2em;color:var(--muted);margin-top:4px}
.fbar{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.97);backdrop-filter:blur(8px);border-bottom:1px solid var(--border);padding:12px 60px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.fbar input{flex:1;min-width:200px;max-width:320px;padding:9px 14px;border:1px solid var(--border);border-radius:3px;font:inherit;background:#f5f5f5}
.fbar input:focus{outline:none;border-color:var(--accent);background:#fff}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{padding:7px 14px;border:1px solid var(--border);background:#fff;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:.05em;cursor:pointer;white-space:nowrap;font-family:inherit}
.chip:hover{border-color:#999}
.chip.active{background:var(--tc,#1a1a1a);color:#fff;border-color:var(--tc,#1a1a1a)}
.chips.g .chip.active{background:#1a1a1a;border-color:#1a1a1a}
.fcount{margin-left:auto;font-size:11px;color:var(--muted)}
.sec{margin-top:40px;scroll-margin-top:70px}
.sec-head{background:#fff;border-top:10px solid var(--tc);padding:34px 60px 24px;display:flex;align-items:center;gap:18px;border-bottom:1px solid var(--border)}
.sec-bar{width:12px;height:54px;background:var(--tc);border-radius:2px}
.sec-head h2{font-size:32px;font-weight:900;letter-spacing:.04em;text-transform:uppercase;color:#071426;line-height:1.05}
.sec-cz{font-size:13px;color:var(--muted);letter-spacing:.1em;margin-top:4px;text-transform:uppercase}
.sec-cnt{margin-left:auto;background:var(--tc);color:#fff;padding:5px 14px;border-radius:20px;font-size:11px;font-weight:800;white-space:nowrap}
.info-pages{display:grid;grid-template-columns:repeat(auto-fit,minmax(460px,1fr));gap:14px;padding:18px 60px 24px;background:#fff;border-bottom:1px solid var(--border)}
.info-pages img{width:100%;height:auto;border:1px solid var(--border);background:#fff}
.serie{background:#fff;margin-top:26px;scroll-margin-top:70px}
.serie-head{padding:22px 60px 16px;display:flex;align-items:center;gap:14px;border-top:5px solid var(--sc);border-bottom:1px solid var(--border)}
.serie-bar{width:8px;height:36px;background:var(--sc);border-radius:2px}
.serie-head h3{font-size:22px;font-weight:900;letter-spacing:.05em;text-transform:uppercase;color:#071426}
.serie-cnt{margin-left:auto;background:var(--sc);color:#fff;padding:3px 12px;border-radius:20px;font-size:11px;font-weight:800}
.grid{display:grid;grid-template-columns:repeat(2,1fr);border-top:1px solid var(--border)}
.card{border-right:1px solid var(--border);border-bottom:1px solid var(--border);background:var(--card);display:flex;flex-direction:column;padding:22px 24px 0;min-height:820px}
.card:nth-child(2n){border-right:none}
.head{display:flex;align-items:flex-start;gap:10px;margin-bottom:8px}
.head h3{font-size:28px;font-weight:900;letter-spacing:.03em;line-height:1;text-transform:uppercase;color:#071426}
.head-l{display:flex;flex-direction:column;gap:5px;min-width:0}
.new{align-self:flex-start;color:var(--accent);font-size:10px;font-weight:900;letter-spacing:.18em;text-transform:uppercase;border-bottom:2px solid var(--accent);padding-bottom:1px}
.dmoc{margin-left:auto;font-size:13px;font-weight:900;color:#071426;white-space:nowrap}
.dmoc-l{color:#888;font-size:8px;font-weight:800;letter-spacing:.12em;margin-right:5px}
.photo{position:relative;height:240px;display:flex;align-items:center;justify-content:center;gap:4%;padding:4px;background:#fff;overflow:hidden}
.photo img{object-fit:contain;object-position:center;display:block}
.p-front{height:96%;max-width:62%}
.p-back{height:70%;max-width:34%}
.photo img:only-child{height:96%;max-width:85%}
.p-rev{height:80%;max-width:25%}
.photo.three{gap:2%}.photo.three .p-front{max-width:46%}.photo.three .p-back{max-width:25%}
.p-hero{height:96%;max-width:100%}
.photo.two{gap:2%}.photo.two .p-hero{height:96%;max-width:66%}.photo.two .p-inner{height:60%;max-width:32%}
.photo.small img{height:62%;max-width:60%}
.rest{display:flex;flex-direction:column;flex:1;min-height:0}
.head{min-height:46px}
@media screen{@supports (grid-template-rows:subgrid){
 /* název, fotka a řádek s typem leží v řadě karet vždy ve stejné výšce, i když má některá karta delší název nebo vyšší fotku */
 .card{display:grid;grid-template-rows:subgrid;grid-row:span 4;min-height:0}
 .card>.rest{min-height:470px}
}}
.photo.wide{height:300px}
.badges{display:flex;align-items:center;flex-wrap:wrap;gap:6px 10px;margin:2px 0 8px}
.badges img{height:40px;width:auto;max-width:150px;object-fit:contain}
.draw{margin-top:8px;padding:8px 0 2px;border-top:1px solid #eee;text-align:center}
.draw img{max-width:100%;max-height:130px;width:auto;object-fit:contain}
.ph{width:100%;height:100%;background:#f3f3f0;display:flex;flex-direction:column;align-items:center;justify-content:center;border-radius:3px}
.ph-n{font-size:20px;font-weight:900;letter-spacing:.08em;color:#c4c4c4}
.ph-t{font-size:9px;letter-spacing:.25em;text-transform:uppercase;color:#ccc;margin-top:4px}
.meta{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin:10px 0 6px;padding-bottom:8px;border-bottom:2px solid var(--sc);min-height:30px}
.meta .g{display:inline-flex;align-items:center;font-size:10px;font-weight:800;color:#333;letter-spacing:.05em;text-transform:uppercase}
.meta .typ{font-size:10px;font-weight:800;color:#666;letter-spacing:.08em;text-transform:uppercase}
.meta .size{font-size:11px;font-weight:900;color:var(--accent);letter-spacing:.04em}
.specs{display:flex;flex-wrap:wrap;gap:6px 14px;margin:6px 0 8px;min-height:1px}
.chip-spec{display:inline-flex;align-items:center;font-size:11.5px;color:#222;white-space:nowrap}
.chip-spec b{font-weight:700}
.temps{display:flex;gap:6px;margin:4px 0 10px}
.temps .t{flex:1;display:flex;flex-direction:column;align-items:center;padding:6px 4px;border-radius:3px;color:#fff}
.temps .tv{font-size:16px;font-weight:900;line-height:1}
.temps .tl{font-size:8px;letter-spacing:.15em;text-transform:uppercase;opacity:.9;margin-top:3px}
.tc{background:#f0a500}.tli{background:#2a8fc8}.tex{background:#e2001a}
.body{display:grid;grid-template-columns:1.05fr .95fr;column-gap:20px;flex:1;margin-top:4px}
.mat{margin-bottom:9px;line-height:1.3}
.mat-l{display:block;font-size:10px;font-weight:900;letter-spacing:.05em;text-transform:uppercase;color:#1a1a1a;margin-bottom:1px}
.mat-v{display:block;font-size:12px;color:#222;text-wrap:pretty}
.desc{font-size:12px;line-height:1.45;color:#444;margin-top:8px;text-wrap:pretty}
.ph-desc{color:#bbb;font-style:italic}
.feat{margin-bottom:12px}
.feat-l{font-size:10px;font-weight:900;letter-spacing:.05em;text-transform:uppercase;margin-bottom:4px}
.feat ul{list-style:none}
.feat li{font-size:12px;line-height:1.3;color:#1a1a1a;padding-left:10px;position:relative;text-wrap:pretty}
.feat li::before{content:'•';position:absolute;left:0;color:var(--sc);font-weight:900}
.colors{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:8px;padding:10px 0 14px;margin-top:12px;border-top:1px solid #eee;min-height:100px;align-items:start}
.card:has(.colors .c-item:nth-child(7)) .colors{grid-auto-flow:row;grid-template-columns:repeat(6,1fr)}
.c-item{text-align:center;min-width:0}
.c-n{font-size:11px;font-weight:800;color:#777;text-align:left;margin-bottom:3px}
.c-art{display:block;width:100%;max-width:70px;height:58px;object-fit:contain;object-position:center bottom;margin:0 auto 4px}
.c-photo{height:58px}
.c-none{display:block;width:100%;max-width:70px;height:58px;margin:0 auto 4px;background:repeating-linear-gradient(45deg,#f2f2f2 0 6px,#fafafa 6px 12px);border:1px dashed #ddd;border-radius:3px}
.c-name{font-size:9px;line-height:1.15;color:#555;text-transform:capitalize;word-break:break-word}
.hidden{display:none!important}
footer{background:#111;color:#888;padding:50px 60px;text-align:center;margin-top:40px;font-size:12px;line-height:1.7}
footer b{color:#fff;letter-spacing:.3em;font-size:16px}
footer .sub{font-size:10px;letter-spacing:.25em;margin-top:16px}
@media(max-width:700px){
 .hero,.toc,.fbar,.sec-head,.serie-head,.info,footer{padding-left:16px;padding-right:16px}
 .hero{min-height:300px;padding-top:30px;padding-bottom:30px}
 .grid{grid-template-columns:1fr}.card{border-right:none!important;min-height:0;padding:18px 16px 0}
 .body{grid-template-columns:1fr}.sec-head h2{font-size:22px}.head h3{font-size:24px}.info-pages{grid-template-columns:1fr}
}
@page{size:A4 landscape;margin:8mm 8mm 13mm 8mm;
 @bottom-left{content:"TRIMM · __LABEL__ · " string(sec);font:8px/1 'Helvetica Neue',Helvetica,Arial,sans-serif;color:#777;letter-spacing:.08em}
 @bottom-right{content:counter(page);font:700 9px/1 'Helvetica Neue',Helvetica,Arial,sans-serif;color:#444}}
@media print{
 body{width:100%;background:#fff}
 .fbar,footer,.stats-row{display:none}
 .hero{min-height:0;height:184mm;page-break-after:always;padding:40px}
 .toc{page-break-after:always;padding:30px 20px}
 .sec{page-break-before:always;margin-top:0}
 .sec-head{padding:20px 20px 14px;page-break-after:avoid}.sec-head h2{string-set:sec content()}
 .info-pages{display:block;padding:0;border:none;zoom:1.3889}
 .info-pages img{display:block;width:auto;max-width:100%;height:184mm;margin:0 auto;page-break-before:always;page-break-inside:avoid;border:none}
 .info-pages img:first-child{page-break-before:avoid;height:150mm;margin-top:6mm}
 .info-pages+.serie{page-break-before:always}
 main{zoom:.72}
 .photo{height:210px}.photo.wide{height:260px}
 .draw img{max-height:105px}
 .colors{min-height:0;padding:8px 0 6px;margin-top:8px}.c-art,.c-photo,.c-none{height:50px}
 .card.dense{zoom:.9}.card.dense2{zoom:.82}
 .grid{grid-template-columns:repeat(2,1fr)}
 .card{border-right:1px solid var(--border)!important;page-break-inside:avoid;break-inside:avoid;min-height:0;padding-bottom:10px}
 .card:nth-child(2n){border-right:none!important}
 .serie{margin-top:0;page-break-inside:auto;page-break-before:always}
 .info-pages+.serie,.sec-head+.serie{page-break-before:always}
 .serie-head{break-after:avoid;page-break-after:avoid;padding:14px 24px 10px}
 .card img{break-inside:avoid}
}
'''
JS = r'''
const q=document.getElementById('q'),cards=[...document.querySelectorAll('.card')],secs=[...document.querySelectorAll('.sec')],series=[...document.querySelectorAll('.serie')],cnt=document.getElementById('cnt');
let cf='all',cg='all';
function go(){const s=q.value.trim().toLowerCase();let n=0;
 cards.forEach(c=>{const ok=(cf==='all'||c.dataset.sec===cf)&&(cg==='all'||c.dataset.g===cg)&&(!s||c.dataset.s.includes(s));c.classList.toggle('hidden',!ok);if(ok)n++});
 series.forEach(x=>x.classList.toggle('hidden',!x.querySelector('.card:not(.hidden)')));
 secs.forEach(x=>x.classList.toggle('hidden',!x.querySelector('.card:not(.hidden)')));
 cnt.textContent=n+' modelů';}
function setF(f){cf=f;document.querySelectorAll('.chips.f .chip').forEach(x=>x.classList.toggle('active',x.dataset.f===f));go()}
function setG(g){cg=g;document.querySelectorAll('.chips.g .chip').forEach(x=>x.classList.toggle('active',x.dataset.g===g));go()}
q.addEventListener('input',go);
document.querySelectorAll('.chips.f .chip').forEach(c=>c.addEventListener('click',()=>setF(c.dataset.f)));
document.querySelectorAll('.chips.g .chip').forEach(c=>c.addEventListener('click',()=>setG(c.dataset.g)));
document.querySelectorAll('.toc-h,.toc-s').forEach(a=>a.addEventListener('click',()=>{setF('all')}));
const u=new URLSearchParams(location.search);
if(u.get('sec'))setF(u.get('sec'));if(u.get('g'))setG(u.get('g'));if(u.get('q')){q.value=u.get('q')}
go();
'''

if __name__ == '__main__':
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    build(args[0] if args else 'SS27', pdf='--no-pdf' not in sys.argv)
