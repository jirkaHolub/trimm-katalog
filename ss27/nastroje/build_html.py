"""Generuje ss27/trimm_katalog_SS27.html z ss27/data/catalog.json."""
import json, os, re, html, collections
from PIL import Image
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.abspath(os.path.join(HERE,'..')); DATA=os.path.join(ROOT,'data')
OUT=os.path.join(ROOT,'trimm_katalog_SS27.html')
cat=json.load(open(os.path.join(DATA,'catalog.json'),encoding='utf-8'))
E=html.escape

SECTIONS=collections.OrderedDict([
 ('tents',dict(title='TENTS COLLECTION',cz='Stany',color='#f39200',pages=[10,11,12])),
 ('sleeping',dict(title='SLEEPING BAGS COLLECTION',cz='Spací pytle',color='#1e73be',pages=[44,45,46])),
 ('mattress',dict(title='MATTRESS COLLECTION',cz='Karimatky a matrace',color='#3aa55d',pages=[60,61])),
 ('backpacks',dict(title='BACKPACKS & WATERPROOF COLLECTION',cz='Batohy, vodotěsné vaky a rezervoáry',color='#8e44ad',pages=[71])),
 ('sportswear',dict(title='SPORTSWEAR COLLECTION',cz='Oblečení',color='#b5c400',pages=[88,89,90,91,92,93])),
])
SERIE_COLORS={'EXTREME':'#e2001a','EXTREME DOWN':'#e2001a','ADVENTURE':'#f39200','TREKKING':'#009fe3','OUTDOOR':'#7ab929','FAMILY':'#9b2fae','SHELTERS':'#1d5fb0',
 'LITE':'#00a99d','COMFORT':'#8a6a3a','ACTIVE':'#8c8c8c','THERMOLAYER':'#c8a24a','DAYPACK':'#2a8fc8','CYKLO':'#e0a82e','TRAVEL LITE / TRAVEL':'#5c7c9a','WATERPROOF':'#0072bc','WATERBLADDER':'#00b3e6'}
def serie_key(s):
    s=(s or 'OSTATNÍ').upper().replace(' SERIE','').strip(); return s
def serie_color(sec,s):
    k=serie_key(s)
    if 'ACCESSORIES' in k: return '#777'
    return SERIE_COLORS.get(k,SECTIONS[sec]['color'])
def slug(s): return re.sub(r'[^a-z0-9]+','-',s.lower()).strip('-')
def price(r):
    if not r['price_min']: return ''
    f=lambda v:f'{v:,}'.replace(',',' ')
    return (f'od {f(r["price_min"])} Kč' if r['price_max']!=r['price_min'] else f'{f(r["price_min"])} Kč')

# ---- ikony ----
I={
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
def icon(k,title=''): return f'<span class="ic" title="{E(title)}">{I[k]}</span>'
GENDER_CZ={'men':'Pánské','women':'Dámské','kids':'Dětské','uni':'Unisex'}
TYP_LABEL={'s.p.':'spací pytel','lodní':'lodní vak','vodní':'vodní vak','kompresní':'kompresní vak','bivakovací':'bivakovací pytel','náhradní':'náhradní díl','tyčky':'tyčky','vložka':'vložka do spacáku'}

def spec_chips(r):
    S=r['specs']; out=[]
    def chip(k,v,t):
        if v: out.append(f'<span class="chip-spec">{icon(k,t)}<b>{E(str(v))}</b></span>')
    chip('persons',S.get('persons'),'Počet osob'); chip('weight',S.get('weight'),'Hmotnost'); chip('volume',S.get('volume'),'Objem')
    chip('length',S.get('length'),'Délka'); chip('width',S.get('width'),'Šířka'); chip('thickness',S.get('thickness'),'Tloušťka'); chip('rvalue',S.get('rvalue') and 'R '+S['rvalue'],'R-value')
    if r['section']!='tents': chip('dims',S.get('dims'),'Rozměr')
    elif S.get('dims') and not r['fields'].get('ROZMĚR'): chip('dims',S.get('dims'),'Rozměr')
    chip('pack',S.get('pack'),'Sbalený rozměr'); chip('pcs',S.get('pcs'),'Počet kusů v balení')
    return ''.join(out)
def temps_html(r):
    T=r['specs'].get('temps')
    if not T: return ''
    def cell(lbl,v,cls): return f'<div class="t {cls}"><span class="tv">{E(v)}°</span><span class="tl">{lbl}</span></div>' if v is not None else ''
    return '<div class="temps">'+cell('comfort',T.get('comfort'),'tc')+cell('limit',T.get('limit'),'tli')+cell('extreme',T.get('extreme'),'tex')+'</div>'
def is_product_shot(path):
    try:
        im=Image.open(os.path.join(ROOT,path)).convert('L'); w,h=im.size; pts=[(3,3),(w-4,3),(3,h-4),(w-4,h-4),(w//2,3),(3,h//2),(w-4,h//2)]
        return sum(im.getpixel(p) for p in pts)/len(pts)>235
    except Exception: return False
def photos_html(r):
    MAIN_COLOR={'CUBE LADY':'pinky'}
    fronts=[c for c in r['colors'] if c.get('front')]
    # hlavní fotka karty: přednost má barva s kompletní dvojicí (přední + zadní), pak barevně specifická, generická až nakonec
    ov=MAIN_COLOR.get(r['name'],'').lower()
    fronts=sorted(fronts,key=lambda c:(0 if c['name'].lower()==ov else 1, 0 if c.get('back') else 1, 1 if c.get('generic') else 0, r['colors'].index(c)))
    if not fronts: return f'<div class="photo"><div class="ph"><span class="ph-n">{E(r["name"])}</span><span class="ph-t">foto doplníme</span></div></div>'
    c=fronts[0]; imgs=''
    if c.get('back') and r['section']=='sportswear' and is_product_shot(c['back']): imgs+=f'<img class="p-back" src="{E(c["back"])}" alt="{E(r["name"])} – zadní strana" loading="lazy">'
    imgs+=f'<img class="p-front" src="{E(c["front"])}" alt="{E(r["name"])}" loading="lazy">'
    return f'<div class="photo">{imgs}</div>'
def colors_html(r):
    items=[]
    for c in r['colors']:
        art=c.get('art') or (c.get('front') if not c.get('generic') else None)
        img=f'<img class="c-art{" c-photo" if not c.get("art") else ""}" src="{E(art)}" alt="{E(r["name"])} {E(c["name"])}" loading="lazy">' if art else '<span class="c-none" title="vizuál doplníme"></span>'
        items.append(f'<div class="c-item" title="{E(c["name"])}"><div class="c-n">{c["n"]}</div>{img}<div class="c-name">{E(c["name"])}</div></div>')
    return f'<div class="colors">{"".join(items)}</div>'
def fields_html(r):
    out=[]
    for k,v in r['fields'].items():
        if not v: continue
        out.append(f'<div class="mat"><span class="mat-l">{E(k)}</span><span class="mat-v">{E(v)}</span></div>')
    return ''.join(out)
def feats_html(r):
    out=''
    if r['features']: out+='<div class="feat"><div class="feat-l">VLASTNOSTI</div><ul>'+''.join(f'<li>{E(f)}</li>' for f in r['features'])+'</ul></div>'
    if r['activities']: out+='<div class="feat"><div class="feat-l">AKTIVITY</div><ul>'+''.join(f'<li>{E(f)}</li>' for f in r['activities'])+'</ul></div>'
    return out
def card(r):
    sec=r['section']; sk=serie_key(r['serie']); sc=serie_color(sec,r['serie'])
    g=r.get('gender'); meta=''
    if g: meta+=f'<span class="g" title="{GENDER_CZ[g]}">{icon(g,GENDER_CZ[g])}<span>{GENDER_CZ[g]}</span></span>'
    meta+=f'<span class="typ">{E(TYP_LABEL.get(r["typ"],r["typ"]))}</span>'
    if r['specs'].get('size'): meta+=f'<span class="size">{E(r["specs"]["size"])}</span>'
    badge='<span class="new">Novinka</span>' if r.get('new') else ''
    search=' '.join([r['name'],r['typ'],sk]+[c['name'] for c in r['colors']]).lower()
    desc=f'<p class="desc">{E(r["desc"])}</p>' if r['desc'] else '<p class="desc ph-desc">Popis doplníme.</p>'
    return f'''<article class="card" id="m-{r['id']}" data-sec="{sec}" data-serie="{E(slug(sk))}" data-g="{g or ''}" data-s="{E(search)}" style="--sc:{sc}">
<div class="head"><div class="head-l"><h3>{E(r['name'])}</h3>{badge}</div><span class="dmoc"><span class="dmoc-l">DMOC</span>{E(price(r))}</span></div>
{photos_html(r)}
<div class="meta">{meta}</div>
<div class="specs">{spec_chips(r)}</div>
{temps_html(r)}
<div class="body"><div class="mats">{fields_html(r)}{desc}</div><div class="feats">{feats_html(r)}</div></div>
{colors_html(r)}
</article>'''

# ---- sestavení sekcí ----
by_sec=collections.OrderedDict((s,[]) for s in SECTIONS)
for r in cat: by_sec[r['section']].append(r)
def groups(items):
    g=collections.OrderedDict()
    for r in items: g.setdefault(serie_key(r['serie']),[]).append(r)
    return g
toc=''; body=''; chips=''
for sec,meta in SECTIONS.items():
    items=by_sec[sec]; gs=groups(items)
    toc+=f'<div class="toc-sec" style="--tc:{meta["color"]}"><a href="#sec-{sec}" class="toc-h"><span class="toc-dot"></span>{E(meta["title"])}<span class="toc-cz">{E(meta["cz"])}</span><span class="toc-cnt">{len(items)}</span></a><div class="toc-series">'
    toc+=''.join(f'<a href="#s-{sec}-{slug(k)}" class="toc-s" data-sec="{sec}"><i style="background:{serie_color(sec,k)}"></i>{E(k)}<span>{len(v)}</span></a>' for k,v in gs.items())
    toc+='</div></div>'
    chips+=f'<button class="chip" data-f="{sec}" style="--tc:{meta["color"]}">{E(meta["cz"].upper())}</button>'
    pages=''.join(f'<img src="data/pdf_pages/p{p:03d}.jpg" alt="Technické informace – strana {p}" loading="lazy">' for p in meta['pages'] if os.path.exists(os.path.join(DATA,'pdf_pages',f'p{p:03d}.jpg')))
    info=''
    body+=f'<section class="sec" id="sec-{sec}" data-sec="{sec}" style="--tc:{meta["color"]}"><div class="sec-head"><div class="sec-bar"></div><div><h2>{E(meta["title"])}</h2><div class="sec-cz">{E(meta["cz"])}</div></div><span class="sec-cnt">{len(items)} modelů</span></div>{info}'
    for k,v in gs.items():
        col=serie_color(sec,k)
        body+=f'<div class="serie" id="s-{sec}-{slug(k)}" data-serie="{slug(k)}" style="--sc:{col}"><div class="serie-head"><div class="serie-bar"></div><h3>{E(k)}{"" if "ACCESSORIES" in k or k in ("WATERPROOF","WATERBLADDER") else " SERIE"}</h3><span class="serie-cnt">{len(v)}</span></div><div class="grid">'
        body+=''.join(card(r) for r in v)
        body+='</div></div>'
    body+='</section>'

# hero
hero_src=os.path.join(ROOT,'hero-ss27.jpg')
if not os.path.exists(hero_src) and os.path.exists(os.path.join(DATA,'cover_ss26.png')):
    im=Image.open(os.path.join(DATA,'cover_ss26.png')).convert('RGB'); im.thumbnail((2000,2000)); im.save(hero_src,quality=82)
n_new=sum(1 for r in cat if r.get('new'))
CSS='''
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#f6f6f4;--card:#fff;--text:#1a1a1a;--muted:#777;--border:#e4e4e4;--accent:#ff6b1a;--sc:#888;--tc:#888}
html{background:var(--bg);color:var(--text);font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:13px;line-height:1.5;-webkit-font-smoothing:antialiased}
body{width:min(100%,104rem);margin:0 auto;background:var(--bg)}
svg{width:1em;height:1em;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.ic{display:inline-flex;font-size:16px;color:var(--accent);margin-right:5px;vertical-align:middle}
/* HERO */
.hero{position:relative;background:#fff url("hero-ss27.jpg") center/cover no-repeat;min-height:420px;display:flex;align-items:flex-end;padding:60px;color:#fff;overflow:hidden}
.hero::after{content:'';position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,0) 35%,rgba(0,0,0,.6) 100%);mask:linear-gradient(90deg,#000 0,#000 55%,transparent 85%);-webkit-mask:linear-gradient(90deg,#000 0,#000 55%,transparent 85%)}
.hero>div{position:relative;z-index:1}
.hero .brand{font-size:14px;letter-spacing:.35em;font-weight:800;opacity:.9}
.hero h1{font-size:clamp(34px,6vw,84px);font-weight:900;letter-spacing:.02em;line-height:1;margin-top:10px}
.hero h1 span{color:#ffe600}
.hero .sub{margin-top:12px;font-size:13px;letter-spacing:.2em;opacity:.85}
/* TOC */
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
/* FILTER */
.fbar{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.97);backdrop-filter:blur(8px);border-bottom:1px solid var(--border);padding:12px 60px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.fbar input{flex:1;min-width:200px;max-width:320px;padding:9px 14px;border:1px solid var(--border);border-radius:3px;font:inherit;background:#f5f5f5}
.fbar input:focus{outline:none;border-color:var(--accent);background:#fff}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{padding:7px 14px;border:1px solid var(--border);background:#fff;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:.05em;cursor:pointer;white-space:nowrap;font-family:inherit}
.chip:hover{border-color:#999}
.chip.active{background:var(--tc,#1a1a1a);color:#fff;border-color:var(--tc,#1a1a1a)}
.chips.g .chip.active{background:#1a1a1a;border-color:#1a1a1a}
.fcount{margin-left:auto;font-size:11px;color:var(--muted)}
/* SECTIONS */
.sec{margin-top:40px;scroll-margin-top:70px}
.sec-head{background:#fff;border-top:10px solid var(--tc);padding:34px 60px 24px;display:flex;align-items:center;gap:18px;border-bottom:1px solid var(--border)}
.sec-bar{width:12px;height:54px;background:var(--tc);border-radius:2px}
.sec-head h2{font-size:32px;font-weight:900;letter-spacing:.04em;text-transform:uppercase;color:#071426;line-height:1.05}
.sec-cz{font-size:13px;color:var(--muted);letter-spacing:.1em;margin-top:4px;text-transform:uppercase}
.sec-cnt{margin-left:auto;background:var(--tc);color:#fff;padding:5px 14px;border-radius:20px;font-size:11px;font-weight:800;white-space:nowrap}
.info{background:#fff;border-bottom:1px solid var(--border);padding:0 60px}
.info summary{cursor:pointer;padding:14px 0;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#444;list-style:none;display:flex;align-items:center;gap:10px}
.info summary::before{content:'+';display:inline-flex;width:22px;height:22px;border-radius:50%;background:var(--tc);color:#fff;align-items:center;justify-content:center;font-weight:900}
.info[open] summary::before{content:'–'}
.info-pages{display:grid;grid-template-columns:repeat(auto-fit,minmax(460px,1fr));gap:14px;padding:6px 0 24px}
.info-pages img{width:100%;height:auto;border:1px solid var(--border);background:#fff}
.serie{background:#fff;margin-top:26px;scroll-margin-top:70px}
.serie-head{padding:22px 60px 16px;display:flex;align-items:center;gap:14px;border-top:5px solid var(--sc);border-bottom:1px solid var(--border)}
.serie-bar{width:8px;height:36px;background:var(--sc);border-radius:2px}
.serie-head h3{font-size:22px;font-weight:900;letter-spacing:.05em;text-transform:uppercase;color:#071426}
.serie-cnt{margin-left:auto;background:var(--sc);color:#fff;padding:3px 12px;border-radius:20px;font-size:11px;font-weight:800}
/* GRID + CARD */
.grid{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid var(--border)}
.card{border-right:1px solid var(--border);border-bottom:1px solid var(--border);background:var(--card);display:flex;flex-direction:column;padding:22px 24px 0;min-height:820px}
.card:nth-child(3n){border-right:none}
.head{display:flex;align-items:flex-start;gap:10px;margin-bottom:8px}
.head h3{font-size:28px;font-weight:900;letter-spacing:.03em;line-height:1;text-transform:uppercase;color:#071426}
.head-l{display:flex;flex-direction:column;gap:5px;min-width:0}
.new{align-self:flex-start;color:var(--accent);font-size:10px;font-weight:900;letter-spacing:.18em;text-transform:uppercase;border-bottom:2px solid var(--accent);padding-bottom:1px}
.dmoc{margin-left:auto;font-size:13px;font-weight:900;color:#071426;white-space:nowrap}
.dmoc-l{color:#888;font-size:8px;font-weight:800;letter-spacing:.12em;margin-right:5px}
.photo{position:relative;height:240px;display:flex;align-items:flex-end;justify-content:center;gap:4%;padding:4px;background:#fff;overflow:hidden}
.photo img{object-fit:contain;object-position:bottom center;display:block}
.p-front{height:96%;max-width:62%}
.p-back{height:70%;max-width:34%}
.photo img:only-child{height:96%;max-width:85%}
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
@media(max-width:1100px){.grid{grid-template-columns:repeat(2,1fr)}.card:nth-child(3n){border-right:1px solid var(--border)}.card:nth-child(2n){border-right:none}}
@media(max-width:700px){
 .hero,.toc,.fbar,.sec-head,.serie-head,.info,footer{padding-left:16px;padding-right:16px}
 .hero{min-height:300px;padding-top:30px;padding-bottom:30px}
 .grid{grid-template-columns:1fr}.card{border-right:none!important;min-height:0;padding:18px 16px 0}
 .body{grid-template-columns:1fr}.sec-head h2{font-size:22px}.head h3{font-size:24px}.info-pages{grid-template-columns:1fr}
}
@media print{.fbar,.info{display:none}.card{page-break-inside:avoid}.sec{page-break-before:always}}
'''
JS='''
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
const u=new URLSearchParams(location.search);if(u.get('sec'))setF(u.get('sec'));if(u.get('g'))setG(u.get('g'));if(u.get('q')){q.value=u.get('q')}
go();
'''
n_series=sum(len(groups(v)) for v in by_sec.values())
doc=f'''<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<title>TRIMM — Katalog SS 27</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}</style>
</head>
<body>
<section class="hero" aria-label="TRIMM Spring-Summer 2027"><div><div class="brand">TRIMM · OUTDOOR PRODUCTS</div><h1>SPRING – SUMMER <span>2027</span></h1><div class="sub">KATALOG · CZ</div></div></section>
<section class="toc">
 <div class="toc-title">CONTENT</div>
 <div class="toc-grid">{toc}</div>
 <div class="stats-row">
  <div><div class="stat-n">{len(cat)}</div><div class="stat-l">MODELŮ</div></div>
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
<footer><b>TRIMM</b><br>Chebská 79/23, 322 00 Plzeň, Czech Republic<br>Tel.: +420 377 822 236 · E-mail: trimm@trimm.eu · www.trimm.eu<div class="sub">SPRING – SUMMER 2027 · CENY DMOC V KČ VČETNĚ DPH · ZMĚNY VYHRAZENY</div></footer>
<script>{JS}</script>
</body>
</html>'''
open(OUT,'w',encoding='utf-8').write(doc)
print('written',OUT,len(doc)//1024,'kB; models',len(cat),'new',n_new)
