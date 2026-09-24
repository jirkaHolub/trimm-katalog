"""Sloučení dat pro katalog SS27: Excel (sortiment, barvy, velikosti, DMOC) + PDF SS26 (texty, parametry) + web trimm.eu (fotky, popisy novinek).
Výstup: ss27/data/catalog.json, fotky do ss27/foto/, rozkresy do ss27/rozkresy/."""
import json, re, os, sys, io, collections, time
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor
import openpyxl
from PIL import Image
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.abspath(os.path.join(HERE,'..')); DATA=os.path.join(ROOT,'data')
REPO=os.path.abspath(os.path.join(ROOT,'..'))
XLSX=[os.path.expanduser('~/Downloads/objednávka_camp_SS27_DMOC.xlsx'),os.path.expanduser('~/Downloads/objednávka_oblečení_SS27_DMOC.xlsx')]
WEB=os.environ.get('WEB_JSON',os.path.join(DATA,'products_web.json'))
FOTO=os.path.join(ROOT,'foto'); ROZ=os.path.join(ROOT,'rozkresy'); os.makedirs(FOTO,exist_ok=True); os.makedirs(ROZ,exist_ok=True)
ALIAS={'HYDRA 2 5L':'HYDRA 1 5L','BALANCE JR':'BALANCE JUNIOR','YETTY 10 0':'YETTI 10 0','PARTY':'PARTY PARTY PLUS','PARTY PLUS':'PARTY PARTY PLUS'}
def nkey(s):
    s=s.upper().replace('½','1/2'); s=re.sub(r'[^A-Z0-9]+',' ',s).strip(); s=re.sub(r'\s+',' ',s); return s
def slug(s): return re.sub(r'[^a-z0-9]+','_',s.lower()).strip('_')
# ---------- Excel ----------
SIZE_ORDER=['XS','S','M','L','XL','XXL','3XL','4XL','5XL']
models=collections.OrderedDict()
for f in XLSX:
    ws=openpyxl.load_workbook(f,data_only=True).active
    for r in ws.iter_rows(min_row=2,values_only=True):
        if not r[5]: continue
        por,sk,reg,ean,item,model,color,size,qty,price,total,cur=r[:12]
        name=re.sub(r'\s+',' ',str(model)).strip()
        m=models.setdefault(name,dict(name=name,sk=sk,typ=str(item).split(' ')[0].lower(),colors=collections.OrderedDict(),sizes=[],prices=set(),order=por,file=os.path.basename(f)))
        col=re.sub(r'\s*/\s*','/',str(color).strip())
        c=m['colors'].setdefault(col,dict(name=col,codes=[]))
        c['codes'].append(f'{sk}{reg}')
        sz=str(size).strip()
        if sz not in m['sizes']: m['sizes'].append(sz)
        if price: m['prices'].add(int(price))
print('excel models',len(models))
# ---------- PDF ----------
pdf=json.load(open(os.path.join(DATA,'pdf_products.json'),encoding='utf-8'))
pdf_by={}
for i,p in enumerate(pdf): p['idx']=i; pdf_by.setdefault(nkey(p['name']),p)
# ---------- náhledy z webu a barevný podpis (pro párování zadních fotek) ----------
import colorsys
THUMBS=os.path.join(DATA,'thumbs'); os.makedirs(THUMBS,exist_ok=True)
_UA={'User-Agent':'Mozilla/5.0 katalog-builder'}
def thumb_path(fn):
    dst=os.path.join(THUMBS,fn.rsplit('.',1)[0]+'.jpg')
    if os.path.exists(dst): return dst
    for i in range(2):
        try:
            b_=urlopen(Request('https://cdn.myshoptet.com/usr/www.trimm.eu/user/shop/detail_small/'+fn,headers=_UA),timeout=30).read()
            im=Image.open(io.BytesIO(b_)).convert('RGB'); im.save(dst,quality=85); return dst
        except Exception: time.sleep(1)
    return None
def color_sig(path):
    try: im=Image.open(path).convert('RGB').resize((80,80))
    except Exception: return None
    hist=[0]*18; ach=[0,0,0]; tot=0
    for px in im.getdata():
        h_,s_,v_=colorsys.rgb_to_hsv(*[c/255 for c in px])
        if v_>0.96 and s_<0.08: continue
        tot+=1
        if s_<0.2 or v_<0.15:
            ach[0 if v_<0.35 else (2 if v_>0.72 else 1)]+=1; continue
        hist[int(h_*18)%18]+=1
    if tot<50: return None
    return [x/tot for x in hist]+[x/tot for x in ach]
def sig_sim(a,b_): return sum(min(x,y) for x,y in zip(a,b_))
def is_product_thumb(path):
    try:
        g=Image.open(path).convert('L'); w,h=g.size; k=max(3,min(w,h)//20)
        return min(sum(g.crop(bx).getdata())/(k*k) for bx in [(0,0,k,k),(w-k,0,w,k),(0,h-k,k,h),(w-k,h-k,w,h)])>225
    except Exception: return False
# ---------- FW 26/27 katalog (záložní zdroj) ----------
FWP={}
_fwf=os.path.join(DATA,'fw_products.json')
if os.path.exists(_fwf):
    for k,v in json.load(open(_fwf,encoding='utf-8')).items(): FWP[nkey(k)]=v
def fw_path(p):
    if not p: return None
    for cand in [os.path.join(REPO,p),os.path.join(REPO,'archiv','resized-nepouzite',os.path.basename(p)),os.path.join(REPO,'archiv','rozkresy-nepouzite',os.path.basename(p))]:
        if os.path.exists(cand): return cand
    return None
# ---------- web ----------
web=json.load(open(WEB,encoding='utf-8'))
code2var={}
for p in web:
    opts=p.get('options',{})
    for k,v in (p.get('variants') or {}).items():
        # klíč "4-1749-5-30": parametr 4 = barva (id 1749)
        ids=k.split('-'); col=None
        for a,b in zip(ids[::2],ids[1::2]):
            if a=='4': col=opts.get(b)
        img=v.get('variantImage') or {}
        code2var[v['code']]=dict(product=p,color=col,img=(img.get('big') or img.get('detail') or ''),key=k)
def img_id(url):
    m=re.search(r'/user/shop/[a-z_]+/(\d+)(?:-(\d+))?_',url); return (int(m.group(1)),int(m.group(2) or 0)) if m else None
def orig_url(fn): return 'https://cdn.myshoptet.com/usr/www.trimm.eu/user/shop/orig/'+fn
def gallery_map(p):
    g={}
    for fn in p.get('gallery',[]):
        i=img_id('/user/shop/big/'+fn)
        if i: g[i]=fn
    return g
# ---------- sekce / série ----------
SEC_ORDER=['tents','sleeping','mattress','backpacks','sportswear']
SEC_BY_SK={'T01':'tents','T02':'sleeping','T03':'mattress','T04':'backpacks','T05':'backpacks','T06':'backpacks','T08':'sportswear'}
def base_name(n):
    k=nkey(n)
    for suf in [' LADY JR',' JR',' LADY',' PANTS',' VEST',' SHORT',' 1 2 ZIP',' UNI',' CONNECTOR',' BEDROOM',' MOSQUITO NET',' FLOOR',' WALL REGULAR',' WALL ZIPPER',' WALL WINDOW',' WALL']:
        if k.endswith(suf): return k[:-len(suf)]
    return k
# ---------- parsování specifikací ----------
def num(s): return s.replace(',', '.')
def parse_specs(sec,m,p):
    S={}
    raw=' '.join(p['spec_raw']) if p else ''
    raw=re.sub(r'\bcm\b','cm',raw)
    w=re.search(r'(\d+(?:[,.]\d+)?)\s*kg\b',raw) or re.search(r'(\d+(?:[,.]\d+)?)\s*[gG]\b',raw)
    if w: S['weight']=w.group(0).replace('G','g').replace(' ',' ')
    if sec=='tents':
        pk=re.search(r'(\d+)\s*x\s*(\d+)\s*x\s*(\d+)\s*cm',raw,re.I)
        if pk: S['pack']=f'{pk.group(1)} × {pk.group(2)} × {pk.group(3)} cm'
        pk2=re.search(r'(\d+)\s*X\s*(\d+)\s*(MM|CM)\b(?!\s*\d)',raw)
        if 'PEG' in m['name'].upper() or 'POLES' in m['name'].upper():
            sz=re.search(r'(\d+(?:[,.]\d+)?\s*(?:X\s*\d+(?:[,.]\d+)?\s*)+(?:MM|CM))',raw) or re.search(r'(\d+\s*CM\s*X\s*\d+(?:,\d+)?\s*MM)',raw)
            if sz: S['dims']=sz.group(1).lower().replace(' x ',' × ').replace('x','×')
            pcs=re.findall(r'(?<![\d,.x×])\b([2-9]|1\d)\b(?![\d,.]|\s*(?:x|mm|cm|g|kg|X))',raw)
            if pcs: S['pcs']=pcs[-1]+' ks'
        if 'FOOTPRINT' in m['name'].upper():
            d=re.findall(r'(\d+)\s*X\s*(\d+)\s*CM',raw)
            if d: S['dims']=f'{d[0][0]} × {d[0][1]} cm'
            if len(d)>1: S['pack']=f'{d[1][0]} × {d[1][1]} cm'
        persons=[s for s in m['sizes'] if 'osob' in s]
        if persons: S['persons']=persons[0].replace('osoby','os.').replace('osoba','os.').replace('osob','os.')
        if p and p['fields'].get('ROZMĚR'): S['dims']=p['fields']['ROZMĚR']
        if p and p['fields'].get('ROZMĚRY') and 'dims' not in S: S['dims']=p['fields']['ROZMĚRY']
    elif sec=='sleeping':
        pk=re.search(r'(\d+)\s*x\s*(\d+)\s*/\s*(\d+)\s*cm',raw) or re.search(r'(\d+)\s*x\s*(\d+)\s*cm',raw) or re.search(r'(\d+)\s*x\s*(\d+)\s*/\s*(\d+)',raw)
        if pk: S['pack']=pk.group(0).replace(' x ',' × ').replace('/',' / ').replace('  ',' ')+('' if 'cm' in pk.group(0) else ' cm')
        ln=[s for s in m['sizes'] if s.endswith('cm')]
        if ln: S['length']=' / '.join(ln)
        elif re.search(r'(\d{3})\s*cm',raw): S['length']=' / '.join(dict.fromkeys(re.findall(r'(\d{3})\s*cm',raw)))
        if p and len(p.get('temps_pos') or [])==3:
            c,l,e=p['temps_pos']; S['temps']={'comfort':c,'limit':l,'extreme':e}
        elif p and p['temps_raw']:
            T={}
            for t in p['temps_raw']:
                n=re.search(r'([+-]?\s*\d+)',t)
                if not n: continue
                v=n.group(1).replace(' ','')
                if 'comfort' in t: T['comfort']=v
                elif 'extreme' in t: T['extreme']=v
                else: T['limit']=v
            S['temps']=T
        if p and p['fields'].get('ŠÍŘKA'): S['width']=p['fields']['ŠÍŘKA']
        if p and p['fields'].get('ROZMĚRY'): S['dims']=p['fields']['ROZMĚRY']
    elif sec=='mattress':
        th=re.search(r'(\d+(?:\.\d+)?)\s*$',m['name'])
        if th: S['thickness']=th.group(1).replace('.',',')+' cm'
        r2=raw
        sz=re.search(r'(?<!ø )(?<!ø)(?<![\d,])(\d{2,3})\s*x\s*(\d{2,3})\s*x',r2)
        if sz and int(sz.group(1))>=30:
            S['dims']=f'{sz.group(1)} × {sz.group(2)} × {S.get("thickness","")}'.strip(' ×'); r2=r2.replace(sz.group(0),' ')
        pk=re.search(r'ø\s*(\d+(?:,\d+)?)\s*x\s*(?:R-value\s*)?(\d+(?:,\d+)?)',r2)
        if pk: S['pack']=f'ø {pk.group(1)} × {pk.group(2)} cm'
        decs=[d for d in re.findall(r'(?<![\d,.])(\d{1,2}[,.]\d)(?![\d,.])(?!\s*(?:cm|x|×|kg))',raw) if d.replace('.',',')+' cm'!=S.get('thickness') and d.replace('.',',')+' kg'!=S.get('weight','').replace('\u00a0',' ')]
        if 'R-value' in raw and decs: S['rvalue']=decs[-1].replace('.',',')
    elif sec=='backpacks':
        v=re.search(r'(\d+(?:[,.]\d+)?(?:\s*-\s*\d+)?)\s*l\b',raw)
        if v: S['volume']=v.group(1).replace(' ','')+' l'
        d=re.search(r'(\d+\s*x\s*\d+(?:\s*x\s*\d+)?\s*cm)',raw)
        if d: S['dims']=d.group(1).replace(' x ',' × ')
    else:
        pass
    # velikosti
    sz=[s for s in m['sizes'] if s not in ('None','')]
    if sec=='sportswear' or m['sk']=='T08':
        letters=[s for s in SIZE_ORDER if s in sz]
        if letters: S['size']=letters[0]+' – '+letters[-1] if len(letters)>1 else letters[0]
        else:
            nums=sorted([int(s) for s in sz if s.isdigit()])
            if nums: S['size']=f'{nums[0]} – {nums[-1]}'
            elif sz: S['size']=', '.join(sz)
    return S
# ---------- sestavení ----------
def gender(m):
    k=nkey(m['name']); t=m['typ']
    if m['sk']!='T08': return None
    if t in ('kšiltovka','nákrčník','pláštěnka','návleky','pásek','čepice'): return 'uni'
    if ' JR' in k or k.endswith(' JR'): return 'kids'
    if 'LADY' in k.split() or k.endswith('A') and False: return 'women'
    # ženské varianty s příponou -A (ORADA, INTENSA, FOXTERA, JURRA, CONTRA, MAROLA, ZENA, CALDA...)
    if k in ('ORADA','INTENSA','FOXTERA','JURRA','CONTRA','CONTRA PANTS','MAROLA','MAROLA PANTS','ZENONA','ZENA','ZENA VEST','ZENA PANTS','CALDA','FJORDA','TIMERA','TAIPA','TRACKA','RONDA','RONDA SHORT','VERONA','NEXA','NEONA'): return 'women'
    if 'UNI' in k.split(): return 'uni'
    return 'men'
catalog=[]; unmatched_pdf=set(pdf_by); log=[]
for name,m in models.items():
    k=nkey(name); pk=ALIAS.get(k,k)
    p=pdf_by.get(pk)
    if p: unmatched_pdf.discard(pk)
    sec=p['section'] if p else SEC_BY_SK.get(m['sk'],'sportswear')
    # web
    wp=None; wvars={}
    for cname,c in m['colors'].items():
        for code in c['codes']:
            v=code2var.get(code)
            if v:
                wp=wp or v['product']; wvars.setdefault(cname,v); break
    rec=dict(id=slug(name),name=name,section=sec,serie=p['serie'] if p else None,typ=m['typ'],sk=m['sk'],gender=gender(m),
             sizes=m['sizes'],price_min=min(m['prices']) if m['prices'] else None,price_max=max(m['prices']) if m['prices'] else None,
             desc=p['desc'] if p else None,fields=p['fields'] if p else {},features=p['features'] if p else [],activities=p['activities'] if p else [],
             specs=parse_specs(sec,m,p),pdf_page=p['page'] if p else None,pdf_order=p['idx'] if p else None,web_url=wp['url'] if wp else None,
             desc_web=(wp['desc'] if wp else None),src=('pdf' if p else 'new'),colors=[])
    if not p and wp and wp.get('desc') and 'není dostupný' not in wp['desc']:
        rec['desc']=re.sub(r'\s+',' ',wp['desc']); rec['desc']=re.sub(r'\s+-(?=\S)',' · ',rec['desc']).lstrip('· ').strip()[:700]
        rec['desc']=re.sub(r'\s*·\s*[^·]*:\s*$','',rec['desc']).strip()
        if ' · ' in rec['desc'] and ':' in rec['desc'].split(' · ',1)[1]: rec['desc']=rec['desc'].split(' · ',1)[0].strip()
        if len(rec['desc'])<20: rec['desc']=None
        elif re.search(r'[A-Za-zÀ-ž0-9]$',rec['desc']): rec['desc']+='.'
    MANUAL_DESC={'PARTY S WALL REGULAR':'Zástěna k přístřešku PARTY S. Poskytuje stín a závětří; lze kombinovat s dalšími zástěnami.','PARTY S WALL ZIPPER':'Zástěna se zipem k přístřešku PARTY S. Zip umožňuje pohodlný průchod, poskytuje stín a závětří.','PARTY S WALL WINDOW':'Zástěna se zipem a okénky k přístřešku PARTY S. Zip umožňuje průchod, okénka propouštějí světlo.'}
    if not rec['desc'] and name in MANUAL_DESC: rec['desc']=MANUAL_DESC[name]
    # záložní vrstva: tabulka parametrů z webu (doplní jen chybějící údaje)
    if wp and wp.get('params_kv'):
        kv={}
        for k,v in wp['params_kv']: kv.setdefault(k,v)
        S=rec['specs']; F=rec['fields']
        def fld(key,label):
            v=kv.get(key)
            if v and not F.get(label): F[label]=v.replace('H2O','H₂O')
        is_tent=(sec=='tents' and m['typ']=='stan')
        fld('Vnější materiál','VNĚJŠÍ STAN' if is_tent else ('VNĚJŠÍ MATERIÁL' if sec=='sportswear' else 'MATERIÁL'))
        if sec!='sportswear': fld('Materiál','MATERIÁL')
        fld('Vnitřní materiál','VNITŘNÍ STAN' if is_tent else 'VNITŘNÍ MATERIÁL'); fld('Materiál výplně','MATERIÁL VÝPLNĚ'); fld('Izolační vrstva','IZOLAČNÍ VRSTVA')
        fld('Podlážka','PODLAHA'); fld('Materiál podlážky','PODLAHA'); fld('Konstrukce','KONSTRUKCE'); fld('Materiál konstrukce','KONSTRUKCE'); fld('Materiál kolíků','KOLÍKY')
        fld('Výplň','VÝPLŇ'); fld('Ventil','VENTIL'); fld('Rozměr','ROZMĚR'); fld('Rozměry výrobku','ROZMĚR')
        w=kv.get('Hmotnost v Kg') or kv.get('Váha')
        if w and not S.get('weight'):
            try:
                x=float(str(w).replace(',','.').replace('kg','').strip()); S['weight']=(f'{x:g}'.replace('.',',')+'\u00a0kg') if x>=1 or x==0 else (f'{x:g}'.replace('.',',')+'\u00a0kg')
            except ValueError: pass
        if kv.get('Rozměr sbalený') and not S.get('pack'): S['pack']=re.sub(r'\s*x\s*',' × ',kv['Rozměr sbalený'])
        if kv.get('Počet kusů v sadě') and not S.get('pcs'): S['pcs']=kv['Počet kusů v sadě']+' ks'
        if kv.get('R-hodnota') and not S.get('rvalue'): S['rvalue']=kv['R-hodnota'].replace('.',',')
        if kv.get('Komfortní teplota') and not S.get('temps'):
            S['temps']={'comfort':kv['Komfortní teplota'].replace('°C','').replace(' ',''),'limit':(kv.get('Limitní teplota') or '').replace('°C','').replace(' ',''),'extreme':(kv.get('Extrémní teplota') or '').replace('°C','').replace(' ','')}
        vl=kv.get('Vlastnosti') or kv.get('Vlastnosti produktu')
        if vl and not rec['features']: rec['features']=[x.strip() for x in vl.split(',') if x.strip()]
        if kv.get('Aktivity') and not rec['activities']: rec['activities']=[x.strip() for x in kv['Aktivity'].split(',') if x.strip()]
        # doplňující údaje z odrážek v popisu na webu (-počet osob: N -hlavní výhody: ...)
        wd=wp.get('desc') or ''
        mo=re.search(r'počet osob:\s*(\d+)',wd)
        if mo and int(mo.group(1))>0 and not S.get('persons'): S['persons']=mo.group(1)+' os.'
        mo=re.search(r'hlavní výhody:\s*(.+?)\s*$',wd)
        if mo and mo.group(1).strip():
            hv=mo.group(1).strip(); hv=hv[0].upper()+hv[1:]
            if hv not in rec['features']: rec['features'].append(hv)
    # novinka = nebyl v SS26 (ani na stránkách příslušenství PARTY, které nemají vlastní produktový sloupec)
    IN_SS26_EXTRA={'MACAO CONNECTOR','PARTY BEDROOM','PARTY CONNECTOR','PARTY FLOOR','PARTY MOSQUITO NET','PARTY WALL','PARTY S BEDROOM','PARTY S CONNECTOR','PARTY S FLOOR','PARTY S MOSQUITO NET','PARTY S WALL REGULAR','PARTY S WALL WINDOW','PARTY S WALL ZIPPER'}
    rec['new']=(p is None) and name not in IN_SS26_EXTRA
    fw=FWP.get(nkey(name))
    if fw:
        if not rec['desc'] and fw.get('desc'): rec['desc']=fw['desc']; rec['src_desc']='fw'
        if not rec['fields'] and fw.get('fields'): rec['fields']=fw['fields']
        if not rec['features'] and fw.get('features'): rec['features']=fw['features']
        if not rec['activities'] and fw.get('activities'): rec['activities']=fw['activities']
    if not rec['serie'] and p is None:
        b=base_name(name); bp=pdf_by.get(b) or pdf_by.get(ALIAS.get(b,b))
        rec['serie']=bp['serie'] if bp else None; rec['base']=b
    gal=gallery_map(wp) if wp else {}
    variant_fronts={img_id(v['img']) for v in wvars.values() if v.get('img')}
    variant_fns={re.search(r'/user/shop/[a-z_]+/([^?]+)',v['img']).group(1) for v in wvars.values() if v.get('img')}
    gal_sigs={}
    if sec=='sportswear' and wp:
        for fn in wp.get('gallery',[]):
            if fn.lower().endswith('.png'): continue
            t=thumb_path(fn)
            if t: gal_sigs[fn]=color_sig(t)
    shared=collections.Counter(img_id(v['img']) for v in wvars.values() if v.get('img'))
    for i,(cname,c) in enumerate(m['colors'].items()):
        col=dict(n=i+1,name=cname,codes=c['codes'],front=None,back=None,art=None,src=None)
        if wvars.get(cname) and wvars[cname].get('img') and shared[img_id(wvars[cname]['img'])]>1: col['generic']=True
        v=wvars.get(cname)
        # fotky v galerii pojmenované podle barvy, např. 'gant-red-dark-red-front.jpg' / '...-back.jpg'
        if wp:
            cs=slug(cname).replace('_','-'); named_front=named_back=None
            own_pids={img_id(v['img'])[0] for v in wvars.values() if v.get('img') and img_id(v['img'])}
            if not own_pids and wp.get('gallery'):
                _i=img_id('/user/shop/big/'+wp['gallery'][0]); own_pids={_i[0]} if _i else set()
            for fn in wp.get('gallery',[]):
                gid=img_id('/user/shop/big/'+fn)
                if not gid or gid[0] not in own_pids or fn.lower().endswith('symboly.png'): continue
                base=fn.split('_',1)[-1].lower().rsplit('.',1)[0]
                side='back' if re.search(r'-(back|b)$',base) else ('front' if re.search(r'-(front|f)$',base) else None)
                core=re.sub(r'-(front|back|f|b)$','',base).replace('-mid-','-').replace('mid-','')
                if re.search(r'-(detail|technical)',base): continue
                # celá barva musí být na konci názvu (za názvem modelu)
                if core.endswith('-'+cs) or core==cs:
                    if side=='back': named_back=named_back or fn
                    else: named_front=named_front or fn
            if named_front and (not v or not v.get('img') or col.get('generic')):
                col['front_url']=orig_url(named_front); col['src']='web'; col.pop('generic',None); col['named']=True
                if named_back: col['back_url']=orig_url(named_back)
                rec['colors'].append(col); continue
            if named_back: col['back_url']=orig_url(named_back)
        if v and v.get('img'):
            fid=img_id(v['img'])
            col['front_url']=orig_url(re.search(r'/user/shop/[a-z_]+/([^?]+)',v['img']).group(1)); col['src']='web'
            ffn=re.search(r'/user/shop/[a-z_]+/([^?]+)',v['img']).group(1)
            if col.get('back_url'): pass
            elif gal_sigs and gal_sigs.get(ffn):
                # zadní pohled = nejpodobnější barva v galerii (mimo přední fotky ostatních variant), práh 0,6
                best=None
                fpid=img_id('/user/shop/big/'+ffn)
                # kandidáti: stejný produkt (id obrázku), přednostně sousední pořadí (dvojice přední/zadní), pak ostatní
                cands=[]
                for fn,sg in gal_sigs.items():
                    if fn==ffn or fn in variant_fns or not sg: continue
                    cid=img_id('/user/shop/big/'+fn)
                    if not cid or not fpid or cid[0]!=fpid[0]: continue
                    if not is_product_thumb(thumb_path(fn)): continue
                    sm=sig_sim(gal_sigs[ffn],sg); dist=abs(cid[1]-fpid[1])
                    cands.append((dist,0 if cid[1]>fpid[1] else 1,-sm,fn,sm))
                cands.sort()
                for dist,_,__,fn,sm in cands:
                    if dist<=2 and sm>=0.7: best=(sm,fn); break
                if best is None:
                    good=[(sm,fn) for dist,_,__,fn,sm in cands if sm>=0.85]
                    if good: best=max(good)
                def top_hue(sg):
                    h=sg[:18]; return h.index(max(h)) if max(h)>0.25 else None
                if best and best[0]>=0.75:
                    th_f=top_hue(gal_sigs[ffn]); th_b=top_hue(gal_sigs[best[1]])
                    if th_f is None or th_b is None or min(abs(th_f-th_b),18-abs(th_f-th_b))<=1:
                        col['back_url']=orig_url(best[1]); col['back_sim']=round(best[0],2)
            elif fid and sec!='sportswear':
                for cand in [(fid[0],fid[1]+1),(fid[0],fid[1]-1)]:
                    if cand in gal and cand not in variant_fronts and not gal[cand].lower().endswith('.png'):
                        col['back_url']=orig_url(gal[cand]); break
        # rozkres
        rk=slug(name+' '+cname)
        rec['colors'].append(col)
    rec['_rozkey']=[slug(name+' '+c) for c in m['colors']]
    catalog.append(rec)
print('unmatched PDF products (not in SS27 Excel):',sorted(unmatched_pdf))
# ---------- řazení: podle PDF, novinky za základní model ----------
pos={}
for r in catalog:
    if r['pdf_order'] is not None: pos[r['id']]=r['pdf_order']
for r in catalog:
    if r['pdf_order'] is None:
        b=r.get('base'); anchor=None
        for o in catalog:
            if o['pdf_order'] is not None and nkey(o['name'])==b: anchor=o
        if anchor is None:
            # poslední produkt stejné sekce
            cands=[o for o in catalog if o['pdf_order'] is not None and o['section']==r['section']]
            anchor=cands[-1] if cands else None
        r['sort']=(anchor['pdf_order'] if anchor else 9999)+0.5
        if anchor and not r['serie']: r['serie']=anchor['serie']
    else: r['sort']=r['pdf_order']
catalog.sort(key=lambda r:(SEC_ORDER.index(r['section']),r['sort'],r['name']))
# ---------- rozkresy ----------
rozsrc={}
for f in os.listdir(os.path.join(REPO,'rozkresy_web')):
    rozsrc[re.sub(r'(\.[a-z]+)?\.png$','',f.lower())]=f
for f in os.listdir(os.path.join(REPO,'podklady','rozkresy-nove')):
    rozsrc.setdefault(re.sub(r'\.png$','',f.lower()),os.path.join('..','podklady','rozkresy-nove',f))
import shutil
nroz=0
for r in catalog:
    for c,key in zip(r['colors'],r['_rozkey']):
        f=rozsrc.get(key)
        if f:
            src=os.path.join(REPO,'rozkresy_web',f) if not f.startswith('..') else os.path.join(REPO,f[3:])
            dst=os.path.join(ROZ,key+'.png')
            if not os.path.exists(dst): shutil.copy(src,dst)
            c['art']='rozkresy/'+key+'.png'; nroz+=1
    del r['_rozkey']
for r in catalog:
    fw=FWP.get(nkey(r['name']))
    if not fw: continue
    def cn(s): return re.sub(r'[^a-z0-9]+','',s.lower())
    for c in r['colors']:
        if c['art']: continue
        hit=[x for x in fw['colors'] if x.get('art') and (cn(x['name'])==cn(c['name']) or cn(x['name']).startswith(cn(c['name'])+'') and len(cn(c['name']))>=8 and '/' in c['name'])]
        if not hit:
            SYN={'grafitblack':'grey','darkgrey':'grey'}
            def ft(s): t=cn(s.split('/')[0]); return SYN.get(t,t)
            mine=[x for x in r['colors'] if ft(x['name'])==ft(c['name'])]
            theirs=[x for x in fw['colors'] if x.get('art') and ft(x['name'])==ft(c['name'])]
            if len(mine)==1 and len(theirs)==1: hit=theirs
        if hit and fw_path(hit[0]['art']):
            key=slug(r['name']+' '+c['name']); dst=os.path.join(ROZ,key+'.png')
            if not os.path.exists(dst): shutil.copy(fw_path(hit[0]['art']),dst)
            c['art']='rozkresy/'+key+'.png'; nroz+=1
print('rozkresy matched',nroz)
# ---------- fotky ----------
UA={'User-Agent':'Mozilla/5.0 katalog-builder'}
_URLMAP_F=os.path.join(DATA,'photo_urls.json')
_URLMAP=json.load(open(_URLMAP_F)) if os.path.exists(_URLMAP_F) else {}
def fetch_resize(url,dst,maxw=900):
    key=os.path.basename(dst)
    if os.path.exists(dst) and _URLMAP.get(key)==url: return True
    _URLMAP[key]=url
    for i in range(3):
        try:
            b=urlopen(Request(url,headers=UA),timeout=40).read()
            im=Image.open(io.BytesIO(b)); im.load()
            if im.mode in ('RGBA','LA','P'):
                bg=Image.new('RGB',im.size,(255,255,255)); im=im.convert('RGBA'); bg.paste(im,mask=im.split()[-1]); im=bg
            im=im.convert('RGB'); im.thumbnail((maxw,maxw)); im.save(dst,quality=84,optimize=True); return True
        except Exception as e:
            err=e; time.sleep(1.5)
    print('DL FAIL',url,err); return False
jobs=[]
for r in catalog:
    for c in r['colors']:
        base=slug(r['name']+' '+c['name'])
        if c.get('front_url'):
            c['front']='foto/'+base+'_front.jpg'; jobs.append((c['front_url'],os.path.join(FOTO,base+'_front.jpg')))
        if c.get('back_url'):
            c['back']='foto/'+base+'_back.jpg'; jobs.append((c['back_url'],os.path.join(FOTO,base+'_back.jpg')))
print('downloading',len(jobs),'images'); sys.stdout.flush()
with ThreadPoolExecutor(6) as ex: res=list(ex.map(lambda j:fetch_resize(*j),jobs))
json.dump(_URLMAP,open(_URLMAP_F,'w'))
# fallbacky: FW resized/ a PDF výřez
fw=os.path.join(REPO,'resized'); fwfiles={f.lower():f for f in os.listdir(fw)}
for _f in os.listdir(os.path.join(REPO,'archiv','resized-nepouzite')):
    fwfiles.setdefault(_f.lower(),os.path.join('..','archiv','resized-nepouzite',_f))
pdfph={slug(p['name']):p['pdf_photo'] for p in pdf if p.get('pdf_photo')}
pdfcol={slug(p['name']):(p.get('spec_small') or [''])[0] for p in pdf}
stats=collections.Counter()
for r in catalog:
    for c in r['colors']:
        if c['front'] and os.path.exists(os.path.join(ROOT,c['front'])) and not c.get('generic'): stats['web']+=1; continue
        orig_front=c['front'] if (c['front'] and os.path.exists(os.path.join(ROOT,c['front']))) else None
        c['front']=None
        base=(r['name']+' '+c['name']); fwkey=re.sub(r'[^a-z0-9]+','_',base.lower()).strip('_')
        cand=[k for k in fwfiles if k.startswith(fwkey+'_front') or k==fwkey+'_front.jpg']
        if cand:
            src=os.path.join(fw,fwfiles[cand[0]]) if not fwfiles[cand[0]].startswith('..') else os.path.join(REPO,fwfiles[cand[0]][3:]); dst=os.path.join(FOTO,slug(base)+'_front.jpg'); shutil.copy(src,dst); c['front']='foto/'+slug(base)+'_front.jpg'; c['src']='fw'; stats['fw']+=1; c.pop('generic',None)
            bk=fwfiles.get(cand[0].replace('_front','_back'))
            if bk: shutil.copy(os.path.join(fw,bk) if not bk.startswith('..') else os.path.join(REPO,bk[3:]),os.path.join(FOTO,slug(base)+'_back.jpg')); c['back']='foto/'+slug(base)+'_back.jpg'
            continue
        fwrec=FWP.get(nkey(r['name']))
        if fwrec and fw_path(fwrec.get('front')):
            # barva z názvu souboru FW fotky (MODEL_barva_front.jpg); bez barvy = generická (jen k první barvě)
            fb=os.path.basename(fwrec['front']).lower(); fb=re.sub(r'\.(jpg|jpeg|png)$','',fb); fb=re.sub(r'_front$','',fb)
            mslug=re.sub(r'[^a-z0-9]+','_',r['name'].lower()).strip('_')
            fcol=fb[len(mslug):].strip('_') if fb.startswith(mslug) else None
            cslug=re.sub(r'[^a-z0-9]+','_',c['name'].lower()).strip('_')
            if fcol==cslug or (not fcol and c is r['colors'][0]):
                dst=os.path.join(FOTO,slug(base)+'_front.jpg'); shutil.copy(fw_path(fwrec['front']),dst); c['front']='foto/'+slug(base)+'_front.jpg'; c['src']='fw'; stats['fw']+=1
                if not fcol: c['generic']=True
                if fw_path(fwrec.get('back')): shutil.copy(fw_path(fwrec['back']),os.path.join(FOTO,slug(base)+'_back.jpg')); c['back']='foto/'+slug(base)+'_back.jpg'
                continue
        # podklady/fotky: 'Micron_lady_vest_mustard_grey_front.png' apod. (přesná barva, nebo jednoznačný první token)
        fp=os.path.join(REPO,'podklady','fotky')
        if os.path.isdir(fp):
            mslug2=re.sub(r'[^a-z0-9]+','_',r['name'].lower()).strip('_')
            def tok(s): t=re.sub(r'[^a-z0-9]+','',s.split('/')[0].lower()); return {'grafitblack':'grey','darkgrey':'grey'}.get(t,t)
            cands_exact=[]; cands_first=[]
            for f in os.listdir(fp):
                fl=re.sub(r'[^a-z0-9]+','_',f.lower().rsplit('.',1)[0]).strip('_')
                if not fl.startswith(mslug2+'_') or not fl.endswith('_front'): continue
                colpart=fl[len(mslug2)+1:-6]
                if colpart==re.sub(r'[^a-z0-9]+','_',c['name'].lower()).strip('_'): cands_exact.append(f)
                elif colpart and colpart.replace('_','').startswith(tok(c['name'])) and len([x for x in r['colors'] if tok(x['name'])==tok(c['name'])])==1: cands_first.append(f)
            cand2=cands_exact or (cands_first if len({x for x in cands_first})==1 else [])
            if cand2:
                im=Image.open(os.path.join(fp,cand2[0])).convert('RGBA'); bgc=Image.new('RGB',im.size,(255,255,255)); bgc.paste(im,mask=im.split()[-1]); bgc.thumbnail((900,900))
                dst=os.path.join(FOTO,slug(base)+'_front.jpg'); bgc.save(dst,quality=84); c['front']='foto/'+slug(base)+'_front.jpg'; c['src']='fw'; stats['fw']+=1
                bk=cand2[0].replace('front','back')
                if os.path.exists(os.path.join(fp,bk)):
                    im=Image.open(os.path.join(fp,bk)).convert('RGBA'); bgc=Image.new('RGB',im.size,(255,255,255)); bgc.paste(im,mask=im.split()[-1]); bgc.thumbnail((900,900)); bgc.save(os.path.join(FOTO,slug(base)+'_back.jpg'),quality=84); c['back']='foto/'+slug(base)+'_back.jpg'
                continue
        # podklady/fotky-jednotlive (např. 'smooth black.jpg')
        fj=os.path.join(REPO,'podklady','fotky-jednotlive')
        cand=[f for f in os.listdir(fj) if re.sub(r'[^a-z0-9]+','_',f.lower().rsplit('.',1)[0]).strip('_') in (fwkey,fwkey+'_f',fwkey+'_front')] if os.path.isdir(fj) else []
        if cand:
            im=Image.open(os.path.join(fj,cand[0])).convert('RGB'); im.thumbnail((900,900)); dst=os.path.join(FOTO,slug(base)+'_front.jpg'); im.save(dst,quality=84); c['front']='foto/'+slug(base)+'_front.jpg'; c['src']='fw'; stats['fw']+=1; continue
        k=slug(r['name']); pk=ALIAS.get(nkey(r['name']),None)
        ph=pdfph.get(k) or (pdfph.get(slug(pk)) if pk else None)
        # výřez z PDF patří barvě uvedené v PDF jako první; jinak generický k první barvě
        pcol=(pdfcol.get(k) or (pdfcol.get(slug(pk)) if pk else None) or '')
        if ph and not (slug(pcol)==slug(c['name']) or (not pcol and c is r['colors'][0]) or (slug(pcol) not in [slug(x['name']) for x in r['colors']] and c is r['colors'][0])):
            ph=None
        if ph and slug(pcol)!=slug(c['name']): c['generic']=True
        if ph:
            dst=os.path.join(FOTO,slug(base)+'_front.jpg'); shutil.copy(os.path.join(ROOT,ph),dst); c['front']='foto/'+slug(base)+'_front.jpg'; c['src']='pdf'; stats['pdf']+=1
        elif orig_front: c['front']=orig_front; stats['web']+=1
        else: stats['none']+=1
    for c in r['colors']:
        c.pop('front_url',None); c.pop('back_url',None)
print('photo sources',stats)
# PARTY camouflage: web má jen lifestyle fotku, vezmeme vzorník z SS26 PDF (str. 34)
try:
    import fitz
    _pdf=fitz.open(os.environ.get('SS_PDF','/Users/jirkaholub/Downloads/trimm_katalog_SS26_CZ_print.pdf'))
    for r in catalog:
        if r['name']=='PARTY':
            for c in r['colors']:
                if 'camo' in c['name'].lower():
                    dst=os.path.join(FOTO,slug(r['name']+' '+c['name'])+'_front.jpg')
                    _pdf[33].get_pixmap(dpi=400,clip=fitz.Rect(106,518,162,552),colorspace=fitz.csRGB).save(dst); c['front']='foto/'+os.path.basename(dst); c['back']=None; c['src']='pdf'
except Exception as e: print('PARTY camo swatch:',e)
# sjednocení fotek
ORIG=os.path.join(DATA,'orig'); os.makedirs(ORIG,exist_ok=True)
for _f in os.listdir(FOTO):
    if _f.lower().endswith('.jpg') and not os.path.exists(os.path.join(ORIG,_f)): shutil.copy(os.path.join(FOTO,_f),os.path.join(ORIG,_f))
import subprocess; subprocess.run([sys.executable,os.path.join(HERE,'normalize_photos.py')])
_ps=json.load(open(os.path.join(DATA,'photo_status.json')))
for r in catalog:
    for c in r['colors']:
        if c.get('back') and _ps.get(os.path.basename(c['back']))=='lifestyle': c['back']=None
        if c.get('front') and _ps.get(os.path.basename(c['front']))=='lifestyle': c['front_lifestyle']=True
for r in catalog:
    for c in r['colors']:
        if c.get('generic') and not c.get('named') and c.get('src')!='fw' and (c.get('back_sim') or 0)<0.85: c['back']=None
# doplnění zadních pohledů z FW katalogu (dvojice front/back), pokud web zadní nemá
fwdir=os.path.join(REPO,'resized'); fwl={f.lower():f for f in os.listdir(fwdir)}
for f in os.listdir(os.path.join(REPO,'archiv','resized-nepouzite')): fwl.setdefault(f.lower(),os.path.join('..','archiv','resized-nepouzite',f))
def fwfile(k):
    f=fwl.get(k); return None if not f else (os.path.join(fwdir,f) if not f.startswith('..') else os.path.join(REPO,f[3:]))
for r in catalog:
    if r['section']!='sportswear': continue
    mslug=re.sub(r'[^a-z0-9]+','_',r['name'].lower()).strip('_')
    need=[c for c in r['colors'] if c.get('front') and not c.get('back') and not c.get('generic')]
    for c in need:
        cslug=re.sub(r'[^a-z0-9]+','_',c['name'].lower()).strip('_'); base=slug(r['name']+' '+c['name'])
        ff=fwfile(f'{mslug}_{cslug}_front.jpg'); fb=fwfile(f'{mslug}_{cslug}_back.jpg')
        if ff and fb:
            shutil.copy(ff,os.path.join(FOTO,base+'_front.jpg')); shutil.copy(fb,os.path.join(FOTO,base+'_back.jpg'))
            c['front']='foto/'+base+'_front.jpg'; c['back']='foto/'+base+'_back.jpg'; c['src']='fw'; c['fw_pair']='exact'
    # dvojice z podklady/fotky (MODEL_barva_front/back.png), přesná barva nebo jednoznačný první token
    fp=os.path.join(REPO,'podklady','fotky')
    if os.path.isdir(fp):
        def tok2(s): t=re.sub(r'[^a-z0-9]+','',s.split('/')[0].lower()); return {'grafitblack':'grey','darkgrey':'grey'}.get(t,t)
        for c in [c for c in r['colors'] if c.get('front') and not c.get('back') and not c.get('generic')]:
            cs2=re.sub(r'[^a-z0-9]+','_',c['name'].lower()).strip('_'); hits=[]
            for f in os.listdir(fp):
                fl=re.sub(r'[^a-z0-9]+','_',f.lower().rsplit('.',1)[0]).strip('_')
                if not fl.startswith(mslug+'_') or not fl.endswith('_front'): continue
                colpart=fl[len(mslug)+1:-6]
                if colpart==cs2 or (colpart.replace('_','').startswith(tok2(c['name'])) and len([x for x in r['colors'] if tok2(x['name'])==tok2(c['name'])])==1): hits.append(f)
            for f in hits[:1]:
                bkf=os.path.join(fp,f.replace('front','back'))
                if not os.path.exists(bkf): continue
                base=slug(r['name']+' '+c['name'])
                for src,dst in ((os.path.join(fp,f),base+'_front.jpg'),(bkf,base+'_back.jpg')):
                    im=Image.open(src).convert('RGBA'); bgc=Image.new('RGB',im.size,(255,255,255)); bgc.paste(im,mask=im.split()[-1]); bgc.thumbnail((900,900)); bgc.save(os.path.join(FOTO,dst),quality=84)
                c['front']='foto/'+base+'_front.jpg'; c['back']='foto/'+base+'_back.jpg'; c['src']='fw'; c['fw_pair']='podklady'
    # když žádná barva modelu nemá zadní pohled: použít libovolnou FW dvojici MODEL_<jiná barva>_front/back jako obecnou hlavní fotku
    if not any(c.get('back') for c in r['colors']):
        pair=None
        for k,f in sorted(fwl.items()):
            if k.startswith(mslug+'_') and k.endswith('_front.jpg') and (k[:-10]+'_back.jpg') in fwl:
                pair=(fwfile(k),fwfile(k[:-10]+'_back.jpg')); break
        if not pair and os.path.isdir(os.path.join(REPO,'podklady','fotky')):
            for f in sorted(os.listdir(os.path.join(REPO,'podklady','fotky'))):
                fl=re.sub(r'[^a-z0-9]+','_',f.lower().rsplit('.',1)[0]).strip('_'); bkf=f.replace('front','back')
                if fl.startswith(mslug+'_') and fl.endswith('_front') and os.path.exists(os.path.join(REPO,'podklady','fotky',bkf)):
                    pair=(os.path.join(REPO,'podklady','fotky',f),os.path.join(REPO,'podklady','fotky',bkf)); break
        if pair:
            c=r['colors'][0]; base=slug(r['name']+' '+c['name'])
            for src,dst in ((pair[0],base+'_front.jpg'),(pair[1],base+'_back.jpg')):
                im=Image.open(src).convert('RGBA'); bgc=Image.new('RGB',im.size,(255,255,255)); bgc.paste(im,mask=im.split()[-1]); bgc.thumbnail((900,900)); bgc.save(os.path.join(FOTO,dst),quality=84)
            c['front']='foto/'+base+'_front.jpg'; c['back']='foto/'+base+'_back.jpg'; c['src']='fw'; c['generic']=True; c['fw_pair']='other-color'
    # generická FW dvojice MODEL_front/back: přiřadit barvě, jejíž webová fotka jí nejvíc odpovídá
    gf=fwfile(f'{mslug}_front.jpg'); gb=fwfile(f'{mslug}_back.jpg')
    if gf and gb:
        sg=color_sig(gf); best=None
        for c in r['colors']:
            if not c.get('front') or c.get('generic'): continue
            s2=color_sig(os.path.join(ROOT,c['front']))
            if sg and s2:
                sm=sig_sim(sg,s2)
                if best is None or sm>best[0]: best=(sm,c)
        if best and best[0]>=0.8 and not best[1].get('back'):
            c=best[1]; base=slug(r['name']+' '+c['name'])
            shutil.copy(gf,os.path.join(FOTO,base+'_front.jpg')); shutil.copy(gb,os.path.join(FOTO,base+'_back.jpg'))
            c['front']='foto/'+base+'_front.jpg'; c['back']='foto/'+base+'_back.jpg'; c['src']='fw'; c['fw_pair']=round(best[0],2)
import subprocess; subprocess.run([sys.executable,os.path.join(HERE,'normalize_photos.py')],stdout=subprocess.DEVNULL)
json.dump(catalog,open(os.path.join(DATA,'catalog.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('catalog',len(catalog),'models; sections',collections.Counter(r['section'] for r in catalog))
print('no photo at all:',[r['name'] for r in catalog if not any(c['front'] for c in r['colors'])])
print('no desc:',[r['name'] for r in catalog if not r['desc']])
