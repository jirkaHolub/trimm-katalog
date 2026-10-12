"""Tisková sazba katalogu (PDF): pevné strany A4 na šířku. Obálka, obsah s čísly stran, technické strany na spad,
produktové strany po dvou kartách s kartou roztaženou na celou výšku strany, zadní strana.
Web (HTML) dál vzniká v generate.render_document; tady se skládá jen dokument, který Chrome vytiskne do PDF."""
import os, html, hashlib, collections
from urllib.parse import quote
from PIL import Image
import store, generate
from generate import Renderer, serie_key, serie_color, groups, catalog_cfg, CSS_BASE

E = html.escape
HERE = os.path.dirname(os.path.abspath(__file__))
PER_PAGE = 2
# technické strany jsou exporty z tiskového PDF včetně spadávky a ořezových značek: tolik se z každé strany ořízne na čistý formát
TRIM_X, TRIM_Y = 0.0243, 0.0330

def _url(fp): return 'file://' + quote(fp)

def print_image(fp, px):
    """Obrázek připravený pro tisk. Průhledné PNG se položí na bílou (strana je bílá) a uloží jako JPEG – v PDF jinak zabírají
    několikanásobek; co je větší, než se na papíře využije, se zmenší."""
    st = os.stat(fp)
    out = os.path.join(store.cache_dir('print'), hashlib.md5(f'{fp}|{st.st_mtime}|{st.st_size}|{px}'.encode()).hexdigest() + '.jpg')
    if os.path.exists(out): return out
    with Image.open(fp) as im:
        png = im.format == 'PNG' or im.mode in ('RGBA', 'LA', 'P')
        if not png and max(im.size) <= px * 1.15: return fp   # běžná fotka v rozumné velikosti jde do PDF beze změny
        im = im.convert('RGBA'); bg = Image.new('RGBA', im.size, (255, 255, 255, 255)); bg.alpha_composite(im); im = bg.convert('RGB')
        if max(im.size) > px: im.thumbnail((px, px), Image.LANCZOS)
        im.save(out, quality=92 if px <= 420 else 90, subsampling=0, optimize=True)   # bez podvzorkování barev, ať zůstanou ostré linky rozkresů
    return out

class PrintRenderer(Renderer):
    """Obrázky bere z disku, upravené pro tisk (print_image)."""
    SIZES = {200: 320, 240: 360}   # šířka, kterou si karta říká pro web -> px pro tisk; ostatní (hlavní fotky, rozkres rozměrů) 1600
    def __init__(self, root):
        super().__init__(_url(root) + '/'); self.root = root
    def src(self, path, w=700):
        fp = os.path.join(self.root, path)
        if not store.REMOTE:   # online se kvůli času tiskne z originálů
            try: fp = print_image(fp, self.SIZES.get(w, 1600))
            except Exception: pass
        return E(_url(fp))
    TALL = .55   # poměr šířka/výška hlavní fotky, od kterého jde fotka vedle textu (spacáky, karimatky, vložky – na šířku by byla maličká)
    def tall(self, r):
        if not r.get('hero') or r.get('hero_back') or r.get('hero_inner') or r.get('hero_reverse') or r.get('typ') in generate.SMALL_TYP: return False
        try:
            with Image.open(os.path.join(self.root, r['hero'])) as im: w, h = im.size
        except Exception: return False
        return w / h < self.TALL
    def card_cls(self, r): return ' tall' if self.tall(r) else ''
    def assemble(self, r, P):
        if not self.tall(r): return super().assemble(r, P)
        # vysoká fotka: sloupec vlevo vedle textu, rozkres a barvy pod tím přes celou šířku
        return f'''{P["head"]}
<div class="side"><div class="tphoto">{P["photo"]}</div><div class="col">{P["meta"]}{P["specs"]}
{P["badges"]}
{P["temps"]}
{P["body"]}</div></div>
<div class="rest">{P["draw"]}
{P["colors"]}</div>'''

def info_page(root, path):
    """Technická strana oříznutá na čistý formát. Původní číslo strany v barevném pruhu dole se zatře a vrátí se poloha pruhu
    (zlomky šířky/výšky), aby se do něj dalo vysadit číslo podle skutečného stránkování."""
    src = os.path.join(root, path); st = os.stat(src)
    out = os.path.join(store.cache_dir('print'), hashlib.md5(f'{path}|{st.st_mtime}|{st.st_size}|3'.encode()).hexdigest())
    meta = out + '.txt'
    if not (os.path.exists(out + '.jpg') and os.path.exists(meta)):
        im = Image.open(src).convert('RGB'); W, H = im.size
        im = im.crop((round(W * TRIM_X), round(H * TRIM_Y), round(W * (1 - TRIM_X)), round(H * (1 - TRIM_Y)))); W, H = im.size
        bar = _find_bar(im)
        if bar:
            x0, x1, y0, col = bar; im.paste(col, (x0, y0, x1, H))
            open(meta, 'w').write(f'{x0 / W} {x1 / W} {y0 / H} #{col[0]:02x}{col[1]:02x}{col[2]:02x}')
        else: open(meta, 'w').write('')
        im.save(out + '.jpg', quality=86, optimize=True)
    m = open(meta).read().split()
    return out + '.jpg', (dict(x0=float(m[0]), x1=float(m[1]), y0=float(m[2]), color=m[3]) if m else None)

def _find_bar(im):
    """barevný pruh s číslem strany v dolním rohu: (x0, x1, y0, barva) nebo None"""
    W, H = im.size; px = im.load(); y = H - max(3, H // 150)
    def sat(p): mx, mn = max(p), min(p); return mx > 90 and (mx - mn) / mx > .45
    runs = []; start = None
    for x in range(W + 1):
        on = x < W and sat(px[x, y])
        if on and start is None: start = x
        if not on and start is not None: runs.append((start, x)); start = None
    runs = [r for r in runs if r[1] - r[0] > W * .15 and (r[0] < W * .02 or r[1] > W * .98)]
    if not runs: return None
    x0, x1 = max(runs, key=lambda r: r[1] - r[0]); xm = (x0 + x1) // 2
    col = sorted(px[x, y] for x in range(x0, x1, max(1, (x1 - x0) // 60)))[30 if x1 - x0 > 60 else 0]
    near = lambda p: sum(abs(a - b) for a, b in zip(p, col)) < 60
    y0 = y
    while y0 > H * .8 and near(px[xm, y0 - 1]): y0 -= 1
    if H - y0 < H * .015: return None
    return (0 if x0 < W * .02 else x0), (W if x1 > W * .98 else x1), y0, col

# Sekce, kde se karty zmenšují a fotky dostávají místo společně pro celou sérii (stejně stavěné karty – linky pak při listování
# neuskakují). U oblečení, batohů a doplňků se řeší každá strana zvlášť, aby karty s málem textu nepřišly o velkou fotku.
FIT_BY_SERIE = {'tents', 'sleeping', 'mattress'}

def paginate(products, sections, root):
    """Rozvržení stran. Série v sekci na sebe navazují bez prázdných míst; nová sekce začíná na nové straně."""
    by_sec = collections.OrderedDict((s['key'], []) for s in sections)
    for r in products: by_sec.setdefault(r['section'], []).append(r)
    pages = [dict(kind='cover'), dict(kind='toc')]; toc = []
    for s in sections:
        items = by_sec.get(s['key'], []); infos = [p for p in (s.get('pages') or []) if os.path.exists(os.path.join(root, p))]
        if not items and not infos: continue
        entry = dict(sec=s, page=len(pages) + 1, n=len(items), series=[]); toc.append(entry)
        for p in infos: pages.append(dict(kind='info', sec=s, path=p))
        first = {}; flat = []
        for k, v in groups(items).items():
            for r in v: flat.append((k.split(' #')[0], r))
        for i in range(0, len(flat), PER_PAGE):
            chunk = flat[i:i + PER_PAGE]; pages.append(dict(kind='prod', sec=s, cards=chunk))
            for k, r in chunk: first.setdefault(k, len(pages))
        cnt = collections.Counter(k for k, r in flat)
        entry['series'] = [dict(name=k, page=pg, n=cnt[k], color=serie_color(s['key'], k, s['color'])) for k, pg in first.items()]
    pages.append(dict(kind='back'))
    return pages, toc

def serie_label(k): return k + ('' if 'ACCESSORIES' in k or k in ('WATERPROOF', 'WATERBLADDER', 'BACKPACKS') else ' SERIE')

def render(cat, products, sections, root):
    """(html, osnova pro záložky PDF [[úroveň, název, strana]])"""
    R = PrintRenderer(root); cfg = catalog_cfg(cat); pages, toc = paginate(products, sections, root); out = []; outline = []
    foot = f'TRIMM · {E(cfg["label"])}'
    def corner(n, color, x0=None, x1=None, y0=None):
        """barevný roh s číslem strany: sudá vlevo, lichá vpravo (u technických stran tam, kde je pruh v předloze)"""
        if x0 is None: side = 'l' if n % 2 == 0 else 'r'; st = ''
        else: side = 'l' if x0 < .5 else 'r'; st = f'left:{x0 * 100:.3f}%;width:{(x1 - x0) * 100:.3f}%;top:{y0 * 100:.3f}%;height:auto;bottom:0;'
        return f'<div class="pn {side}" style="{st}background:{color}"><span>{n}</span></div>'
    for i, p in enumerate(pages):
        n = i + 1; k = p['kind']
        if k == 'cover':
            hero = f' style="background-image:url(&quot;{E(_url(os.path.join(root, cfg["hero"])))}&quot;)"' if cfg['hero'] else ''
            out.append(f'<section class="pg cover"{hero}><div class="cv"><div class="brand">TRIMM · OUTDOOR PRODUCTS</div><h1>{E(cfg["title"])} <span>{E(cfg["year"])}</span></h1><div class="sub">KATALOG · CZ</div></div></section>')
            outline.append([1, cfg['label'] or 'Katalog', n])
        elif k == 'toc':
            cols = ''
            for t in toc:
                s = t['sec']; rows = ''.join(f'<a class="tr" href="#pg-{x["page"]}"><i style="background:{x["color"]}"></i><span class="tn">{E(serie_label(x["name"]))}</span><span class="td"></span><span class="tp">{x["page"]}</span></a>' for x in t['series'])
                cols += f'<div class="ts" style="--tc:{s["color"]}"><a class="th" href="#pg-{t["page"]}"><span class="tt">{E(s["title"])}</span><span class="tp">{t["page"]}</span></a><div class="tcz">{E(s["cz"])} · {t["n"]} modelů</div>{rows}</div>'
            out.append(f'<section class="pg tocp" id="pg-{n}"><div class="toc-k">OBSAH <span>CONTENT</span></div><div class="toc-c">{cols}</div><div class="pf-t r">{foot}</div>{corner(n, "#1a1a1a")}</section>')
            outline.append([1, 'Obsah', n])
        elif k == 'info':
            s = p['sec']; fp, bar = info_page(root, p['path'])
            num = corner(n, bar['color'], bar['x0'], bar['x1'], bar['y0']) if bar else ''
            out.append(f'<section class="pg info" id="pg-{n}"><img src="{E(_url(fp))}" alt="Technické informace – {E(s["cz"])}">{num}</section>')
        elif k == 'prod':
            s = p['sec']; seen = []; slots = ''
            for sk, r in p['cards']:
                if sk not in seen: seen.append(sk)
                col = serie_color(s['key'], sk, s['color'])
                slots += f'<div class="slot" style="--sc:{col}"><div class="ov"><i></i>{E(serie_label(sk))}</div><div class="cw">{R.card(r, s["color"])}</div></div>'
            sk0 = p['cards'][0][0]   # skupina pro společné zmenšení karet a výšku fotky: celá série (sekce + série první karty na straně), jinak jen tato strana
            grp = f'{s["key"]}|{sk0}' if s['key'] in FIT_BY_SERIE and 'ACCESSORIES' not in sk0 else f'pg-{n}'
            out.append(f'<section class="pg prod" id="pg-{n}" data-grp="{E(grp)}" style="--tc:{s["color"]}"><header class="phd"><b>{E(s["title"])}</b><span class="phd-cz">{E(s["cz"])}</span></header>'
                       f'<div class="slots">{slots}</div><div class="pf-t {"r" if n % 2 == 0 else "l"}">{foot} · ceny DMOC v Kč včetně DPH</div>{corner(n, s["color"])}</section>')
        else:
            out.append(f'<section class="pg back" id="pg-{n}"><div><b>TRIMM</b><p>Chebská 79/23, 322 00 Plzeň, Czech Republic<br>Tel.: +420 377 822 236 · E-mail: trimm@trimm.eu · www.trimm.eu</p><div class="sub">{E(cfg["label"])} · CENY DMOC V KČ VČETNĚ DPH · ZMĚNY VYHRAZENY</div></div></section>')
    for t in toc:
        outline.append([1, f'{t["sec"]["title"]} – {t["sec"]["cz"]}', t['page']])
        outline += [[2, serie_label(x['name']), x['page']] for x in t['series']]
    doc = f'''<!DOCTYPE html>
<html lang="cs"><head><meta charset="UTF-8"><title>{E(cfg['doc_title'])}</title>
<style>{CSS_BASE.split('@page{')[0]}{CSS}</style></head>
<body>{''.join(out).replace(' loading="lazy"', '')}<script>{JS}</script></body></html>'''
    return doc, outline

CSS = r'''
@page{size:297mm 210mm;margin:0}
html{background:#fff}
body{width:auto;margin:0;background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.pg{position:relative;width:297mm;height:209.9mm;overflow:hidden;background:#fff;break-after:page;break-inside:avoid}
.pg:last-of-type{break-after:auto}
/* číslo strany v barevném rohu a drobná patička */
.pn{position:absolute;bottom:0;height:8mm;width:95mm;color:#fff;display:flex;align-items:center;font:300 12pt/1 'Helvetica Neue',Helvetica,Arial,sans-serif;letter-spacing:.02em}
.pn.l{left:0;justify-content:flex-start;padding-left:15mm}.pn.r{right:0;justify-content:flex-end;padding-right:15mm}
.info .pn.l{padding-left:4.6%}.info .pn.r{padding-right:4.6%}
.pf-t{position:absolute;bottom:2.6mm;font-size:6.5pt;letter-spacing:.14em;text-transform:uppercase;color:#9a9a9a}
.pf-t.l{left:12mm}.pf-t.r{right:12mm}
/* obálka */
.cover{background:#fff center/cover no-repeat;color:#fff;display:flex;align-items:flex-end}
.cover::after{content:'';position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,0) 40%,rgba(0,0,0,.55) 100%);-webkit-mask:linear-gradient(90deg,#000 0,#000 50%,transparent 82%)}
.cv{position:relative;z-index:1;padding:0 0 20mm 18mm}
.cv .brand{font-size:11pt;letter-spacing:.38em;font-weight:800}
.cv h1{font-size:54pt;font-weight:900;letter-spacing:.015em;line-height:1;margin-top:4mm}.cv h1 span{color:#ffe600}
.cv .sub{margin-top:4mm;font-size:10pt;letter-spacing:.24em}
/* obsah */
.tocp{padding:20mm 18mm 16mm}
.toc-k{font-size:30pt;font-weight:900;letter-spacing:.02em;color:#071426;line-height:1}.toc-k span{font-weight:300;color:#b5b5b5;margin-left:3mm;font-size:16pt;letter-spacing:.12em}
.toc-c{margin-top:12mm;column-count:3;column-gap:12mm}
.ts{break-inside:avoid;margin-bottom:9mm;border-top:1.2mm solid var(--tc);padding-top:3mm}
.th{display:flex;align-items:baseline;text-decoration:none;color:#071426;font-weight:900;font-size:12pt;letter-spacing:.04em}
.th .tp{margin-left:auto;font-size:12pt}
.tcz{font-size:7.5pt;letter-spacing:.12em;text-transform:uppercase;color:#8a8a8a;margin:.8mm 0 2.2mm}
.tr{display:flex;align-items:baseline;gap:2mm;text-decoration:none;color:#222;font-size:8.5pt;font-weight:700;letter-spacing:.05em;padding:.9mm 0}
.tr i{width:2.2mm;height:2.2mm;border-radius:50%;flex-shrink:0;align-self:center}
.tr .td{flex:1;border-bottom:.25mm dotted #bdbdbd;transform:translateY(-.8mm)}
.tr .tp{font-weight:400;color:#555;min-width:6mm;text-align:right}
/* technické strany na spad */
.info img{position:absolute;inset:0;width:100%;height:100%;object-fit:fill}
/* produktové strany */
.prod{padding:9mm 12mm 12mm;display:flex;flex-direction:column}
.phd{display:flex;align-items:baseline;gap:3mm;padding-bottom:2.6mm;border-bottom:.9mm solid var(--tc);flex-shrink:0}
.phd b{font-size:13pt;font-weight:900;letter-spacing:.05em;text-transform:uppercase;color:#071426}
.phd-cz{font-size:7.5pt;letter-spacing:.16em;text-transform:uppercase;color:#8a8a8a}
.slots{flex:1;min-height:0;display:grid;grid-template-columns:1fr 1fr;margin-top:3.5mm}
.slot{min-width:0;min-height:0;display:flex;flex-direction:column;padding:0 7mm 0 0}
.slot+.slot{padding:0 0 0 7mm;border-left:.25mm solid #dcdcdc}
.ov{flex-shrink:0;display:flex;align-items:center;gap:1.6mm;font-size:6.8pt;font-weight:800;letter-spacing:.16em;color:var(--sc);text-transform:uppercase;margin-bottom:1.6mm}
.ov i{width:5mm;height:.7mm;background:var(--sc)}
.cw{flex:1;min-height:0;overflow:hidden}
.prod .card{border:none!important;padding:0;min-height:0;background:none;display:flex;flex-direction:column}
.prod .head{min-height:0;margin-bottom:4px;align-items:baseline}
.prod .dmoc{font-size:15px}.prod .dmoc-l{font-size:8.5px}
.prod .photo{flex:1000 1 0;height:auto;min-height:145px;max-height:430px;padding:6px 4px}
.prod .photo.wide{max-height:470px}
.prod .photo.small{min-height:110px;max-height:290px}
.prod .card.tall .side{display:flex;gap:14px;min-height:330px;max-height:none;margin-top:2px;flex:1000 1 0}
.prod .card.tall .tphoto{flex:0 0 31%;position:relative;min-width:0}
.prod .card.tall .tphoto .photo{position:absolute;inset:4px 2px 6px;height:auto;min-height:0;max-height:none;padding:0;flex:none}
.prod .card.tall .tphoto .photo img{height:100%;max-width:100%}
.prod .card.tall .col{flex:1;min-width:0;display:flex;flex-direction:column}
.prod .card.tall .col .meta{margin-top:0}
.prod .card.tall .body{flex:0 0 auto}
.prod .card.tall .rest{flex:0 0 auto;margin-top:auto}
.prod .meta{flex-shrink:0;margin:6px 0 6px}
.prod .rest{flex:1 1 auto;min-height:0}
.prod .draw img{max-height:120px}
.prod .colors{min-height:0;padding:8px 0 0;margin-top:10px}
.prod .c-art,.prod .c-photo,.prod .c-none{height:60px;max-width:78px}
/* zadní strana */
.back{background:#111;color:#9a9a9a;display:flex;align-items:center;justify-content:center;text-align:center;font-size:10pt;line-height:1.8}
.back b{color:#fff;font-size:26pt;letter-spacing:.34em;display:block;margin-bottom:6mm}
.back .sub{font-size:7pt;letter-spacing:.26em;margin-top:8mm}
'''

# Karta se roztáhne na celou výšku strany: volné místo dostane fotka. Když se text nevejde, zmenší se celá karta.
# Zmenšení i výška fotky se počítají společně pro celou sérii (data-grp), ne pro každou stranu zvlášť – linky pod fotkou,
# nad rozkresem a nad barvami pak sedí ve stejné výšce na všech stranách série a při listování neuskakují.
JS = r'''
function fitCards(){
 const MIN=.5,MAX=.86;   // MAX drží písmo na všech stranách v podobné velikosti (text 7,7 b.) a nechává víc místa fotce
 const groups=new Map();
 document.querySelectorAll('.pg.prod').forEach(pg=>{const k=pg.dataset.grp||pg.id;if(!groups.has(k))groups.set(k,[]);groups.get(k).push(pg)});
 groups.forEach(pgs=>{
  const cws=pgs.flatMap(pg=>[...pg.querySelectorAll('.cw')]);
  // výška karty s fotkou na nejmenší přípustné výšce při zmenšení z (v zobrazených px)
  // pružný prvek karty: blok fotka + text (.side, vysoká fotka) nebo samotná fotka (.photo)
  const fx=c=>c.querySelector('.side')||c.querySelector('.photo');
  // .photo dostává pevnou výšku, .side jen minimální (text vedle fotky může být vyšší a nesmí se oříznout)
  const prop=ph=>ph.classList.contains('side')?'minHeight':'height';
  const nat=(cw,z)=>{const c=cw.firstElementChild,ph=fx(c);c.style.zoom=z;c.style.height='auto';ph.style.flex='none';ph.style.minHeight='';ph.style[prop(ph)]=getComputedStyle(ph).minHeight;
   const h=c.getBoundingClientRect().height;ph.style.flex='';ph.style.height='';ph.style.minHeight='';return h};
  const need=cw=>{const H=cw.getBoundingClientRect().height,ok=z=>nat(cw,z)<=H+.5;
   if(ok(MAX))return MAX;if(!ok(MIN)){cw.dataset.over=1;return MIN}
   let lo=MIN,hi=MAX;for(let i=0;i<7;i++){const m=(lo+hi)/2;ok(m)?lo=m:hi=m}return lo};
  const z=Math.min(...cws.map(need));
  // volné místo dostane fotka – na všech kartách skupiny stejně, aby linky pod fotkami seděly v jedné výšce
  const extra=Math.max(0,Math.min(...cws.map(cw=>(cw.getBoundingClientRect().height-nat(cw,z))/z)));
  cws.forEach(cw=>{const c=cw.firstElementChild,ph=fx(c),cs=getComputedStyle(ph);
   const mx=parseFloat(cs.maxHeight),v=parseFloat(cs.minHeight)+extra;
   c.style.zoom=z;c.style.height=(cw.clientHeight/z)+'px';ph.style.flex='none';ph.style[prop(ph)]=(isNaN(mx)?v:Math.min(v,mx))+'px'});
  pgs.forEach(pg=>pg.dataset.z=z.toFixed(3));
 });
 document.documentElement.dataset.fit='1';
}
if(document.readyState==='complete')fitCards();else addEventListener('load',fitCards);
'''
