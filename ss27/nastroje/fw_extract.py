"""Vytáhne data produktů z FW 26/27 HTML katalogu (kořen repa) jako záložní zdroj pro SS27 → ss27/data/fw_products.json"""
import re, json, os, html
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.abspath(os.path.join(HERE,'..')); REPO=os.path.abspath(os.path.join(ROOT,'..'))
FW=os.path.join(REPO,'trimm_katalog_FW_26_27_3.html')
h=open(FW,encoding='utf-8').read()
def strip(t): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',t))).strip()
out={}
for m in re.finditer(r'<article class="product-card"(.*?)</article>',h,re.S):
    a=m.group(1)
    name=re.search(r'data-model="([^"]+)"',a).group(1)
    p=dict(name=name,typ=(re.search(r'data-typ="([^"]*)"',a) or [None,None])[1],serie=re.search(r'data-serie="([^"]*)"',a).group(1))
    p['front']=(re.search(r'class="photo-front" src="([^"]+)"',a) or [None,None])[1]
    p['back']=(re.search(r'class="photo-back" src="([^"]+)"',a) or [None,None])[1]
    d=re.search(r'<p class="card-desc">(.*?)</p>',a,re.S); p['desc']=strip(d.group(1)) if d else ''
    if 'placeholder' in (d.group(0) if d else ''): p['desc']=''
    p['fields']={}
    for mb in re.finditer(r'<span class="mat-label">(.*?)</span>\s*<span class="mat-value">(.*?)</span>',a,re.S):
        v=strip(mb.group(2))
        if v and 'placeholder' not in mb.group(2): p['fields'][strip(mb.group(1))]=v
    p['features']=[];p['activities']=[]
    for chunk in a.split('<div class="feat-block">')[1:]:
        lbl=re.search(r'<div class="feat-label">(.*?)</div>',chunk,re.S); lbl=strip(lbl.group(1)) if lbl else ''
        items=[strip(y) for x in re.findall(r'<li>(.*?)</li>|<span class="act-tag">(.*?)</span>',chunk,re.S) for y in x if y]
        (p['features'] if 'VLASTN' in lbl.upper() else p['activities']).extend(items)
    p['colors']=[]
    for ci in re.finditer(r'<div class="color-item">(.*?)</div></div>',a,re.S):
        c=ci.group(1); nm=re.search(r'class="color-name">([^<]*)',c); art=re.search(r'class="variant-art" src="([^"]+)"',c)
        p['colors'].append(dict(name=strip(nm.group(1)) if nm else '',art=art.group(1) if art else None))
    sz=re.search(r'class="size-range">(.*?)</span>',a); p['size']=strip(sz.group(1)) if sz else None
    out[name.upper()]=p
json.dump(out,open(os.path.join(ROOT,'data','fw_products.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('FW products',len(out))
for k in ['THERM','MICRON VEST','SMOOTH','ERWI HARD','THERM LADY 1/2 ZIP']:
    p=out.get(k); print(k, p and (p['front'],p['back'],len(p['desc']),list(p['fields'])[:3],len(p['features']),p['activities'][:3],[(c['name'],c['art']) for c in p['colors']][:4]))
