import re, json, os, sys, time, html
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor
S=os.environ.get('SCRAPE_DIR',os.path.dirname(os.path.abspath(__file__)))  # zde: sitemap.xml, pages/, products_web.json
sm=open(f'{S}/sitemap.xml',encoding='utf-8').read()
urls=[]
for blk in re.findall(r'<url>(.*?)</url>',sm,re.S):
    loc=re.search(r'<loc>([^<]+)</loc>',blk).group(1)
    if re.match(r'https://www\.trimm\.eu/(en|sk)/',loc): continue
    path=loc.replace('https://www.trimm.eu/','').strip('/')
    if path.count('/')==1 and '<image:loc>' in blk: urls.append(loc)
# produkty mimo sitemapu (starší stránky, které web stále obsluhuje)
EXTRA=['spacak-trimm-gant','spacak-trimm-tramp','spacak-trimm-walker-flex','karimatka-trimm-charge-8-5','sortky-trimm-tracky','mikina-trimm-oasis']
for e in EXTRA+[x.strip() for x in os.environ.get('EXTRA_URLS','').split(',') if x.strip()]:
    u='https://www.trimm.eu/'+e.strip('/')+'/'
    if u not in urls: urls.append(u)
print('product urls',len(urls)); sys.stdout.flush()
UA={'User-Agent':'Mozilla/5.0 (Macintosh) katalog-builder'}
def fetch(u):
    slug=u.rstrip('/').split('/')[-1]; cat=u.rstrip('/').split('/')[-2]
    if cat=='www.trimm.eu': cat='root'
    fn=f'{S}/pages/{cat}__{slug}.html'
    if os.path.exists(fn): return fn
    for i in range(3):
        try:
            d=urlopen(Request(u,headers=UA),timeout=30).read()
            open(fn,'wb').write(d); return fn
        except Exception as e:
            time.sleep(2)
    print('FAIL',u); return None
with ThreadPoolExecutor(6) as ex:
    fns=list(ex.map(fetch,urls))
print('fetched',sum(1 for f in fns if f))
def strip(t): 
    t=re.sub(r'<script.*?</script>','',t,flags=re.S); t=re.sub(r'<[^>]+>',' ',t); return re.sub(r'\s+',' ',html.unescape(t)).strip()
out=[]
for u,fn in zip(urls,fns):
    if not fn: continue
    h=open(fn,encoding='utf-8',errors='replace').read()
    p={'url':u,'cat':u.rstrip('/').split('/')[-2].replace('www.trimm.eu','root'),'slug':u.rstrip('/').split('/')[-1]}
    m=re.search(r'<h1[^>]*>(.*?)</h1>',h,re.S); p['name']=strip(m.group(1)) if m else None
    m=re.search(r'"product"\s*:\s*(\{.*?\n\s*\})\s*,\s*"page',h,re.S)
    if not m: m=re.search(r'"product"\s*:\s*(\{.*?"codes"\s*:\s*\[.*?\].*?\})',h,re.S)
    if m:
        try: p['dl']=json.loads(m.group(1))
        except Exception as e: p['dl_err']=str(e); p['dl_raw']=m.group(1)[:3000]
    i=h.find('shoptet.variantsSplit.necessaryVariantData = ')
    if i>0:
        j=h.find('\n',i); raw=h[i+len('shoptet.variantsSplit.necessaryVariantData = '):j].strip().rstrip(';')
        try: p['variants']=json.loads(raw)
        except Exception as e: p['variants_err']=str(e)
    p['options']={}
    for sel in re.finditer(r'<select[^>]*>(.*?)</select>',h,re.S):
        for o in re.finditer(r'<option[^>]*value="(\d+)"[^>]*>([^<]*)</option>',sel.group(1)):
            p['options'][o.group(1)]=html.unescape(o.group(2).strip())
    p['gallery']=[]
    for m in re.finditer(r'https://cdn\.myshoptet\.com/usr/www\.trimm\.eu/user/shop/big/([^"?&\s]+)',h):
        if m.group(1) not in p['gallery']: p['gallery'].append(m.group(1))
    m=re.search(r'<div class="basic-description">(.*?)</div>\s*(?:</div>|<div class="(?!p1|p2))',h,re.S)
    if not m: m=re.search(r'<div class="basic-description">(.*?)<div class="(?:extended|description-right|p-detail)',h,re.S)
    p['desc_html']=m.group(1).strip() if m else None
    p['desc']=strip(m.group(1)) if m else None
    m=re.search(r'<table class="detail-parameters">(.*?)</table>',h,re.S)
    p['params']=[]
    if m:
        for tr in re.finditer(r'<tr[^>]*>(.*?)</tr>',m.group(1),re.S):
            cells=[strip(c) for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>',tr.group(1),re.S)]
            if cells and any(cells): p['params'].append(cells)
    # tabulka parametrů (klíč ve <th>, hodnota v <td>)
    p['params_kv']=[]
    for tr in re.finditer(r'<tr[^>]*>\s*<th>(.*?)</th>\s*<td>(.*?)</td>',h,re.S):
        k=strip(tr.group(1)).rstrip(':').strip().lstrip('? ').strip(); v=strip(tr.group(2))
        if k and v and 'Zvol' not in v and k not in ('Barva','Velikost','EAN','Kategorie'): p['params_kv'].append([k,v])
    # parameters tab (extended)
    m=re.search(r'<div[^>]*id="productParams"[^>]*>(.*?)</div>\s*</div>',h,re.S)
    p['params_tab']=strip(m.group(1))[:3000] if m else None
    out.append(p)
json.dump(out,open(f'{S}/products_web.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('saved',len(out))
