"""Extrakce produktových dat z tiskového PDF katalogu SS26 (podklad pro SS27).
Výstup: ss27/data/pdf_products.json, ss27/data/pdf_photos/*.jpg (záložní fotky), ss27/data/pdf_pages/*.jpg (úvodní strany)."""
import fitz, re, json, os, sys, io
from PIL import Image
PDF=os.environ.get('SS_PDF','/Users/jirkaholub/Downloads/trimm_katalog_SS26_CZ_print.pdf')
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(HERE,'..','data')
d=fitz.open(PDF)
L='a-zA-ZÀ-ž'
def fix(t):
    t=t.replace('ﬂ ','fl').replace('ﬁ ','fi').replace('ﬂ','fl').replace('ﬁ','fi').replace('ﬀ','ff')
    t=re.sub(rf'(?<=[{L}]),(?=[{L}])','ť',t)
    t=re.sub(r'\((?=[a-zá-ž])','š',t)
    t=re.sub(rf'(?<=[{L}])\)(?=[{L}])','ň',t)
    t=re.sub(rf'(?<=[{L}])%(?=[{L}])','ř',t)
    t=re.sub(r'(?<![0-9 ])%(?=[a-zá-ž])','ř',t)
    t=re.sub(r'(^|(?<=\s))%(?=[a-zá-ž])','Ř',t)
    t=re.sub(rf'(?<=[a-zá-ž])\*(?=[{L}])','ů',t)
    t=re.sub(r'(?<=[a-zá-ž])(?<!kg)(?<!mm)\*(?=[\s\.,;:]|$)','ů',t)
    t=re.sub(rf'(?<=[{L}])[&!](?=[{L}0-9])',' ',t)
    t=t.replace("p' sob","působ").replace('$','ý').replace('#','š').replace('\\n','')
    t=t.replace('\x00','₂').replace('H O','H₂O').replace('H ₂ O','H₂O').replace('H₂ O','H₂O')
    t=re.sub(r'\s+',' ',t)
    return t.strip()
SECTIONS=[(13,40,'tents'),(41,56,'sleeping'),(57,68,'mattress'),(69,84,'backpacks'),(85,134,'sportswear')]
def section(pno1):
    for a,b,s in SECTIONS:
        if a<=pno1<=b: return s
LABELS=['VNĚJŠÍ STAN','VNITŘNÍ STAN','PODLAHA','KONSTRUKCE','ROZMĚR','ROZMĚRY','ŠÍŘKA','VNITŘNÍ MATERIÁL','VNĚJŠÍ MATERIÁL','IZOLAČNÍ VRSTVA','MATERIÁL','VÝPLŇ','VENTIL','MATERIÁL VÝPLNĚ','VLASTNOSTI','AKTIVITY','MATERIÁL / MATERIAL:','ROZMĚRY / DIMENSIONS:']
def is_label(t): return t.strip().rstrip(':').upper() in [l.rstrip(':') for l in LABELS] or t.strip() in LABELS
def headers(pno):
    p=d[pno]; hs=[]
    for b in p.get_text('dict')['blocks']:
        for l in b.get('lines',[]):
            for s in l['spans']:
                if s['size']>=15 and s['text'].strip() and s['bbox'][1]<90 and 'Bold' in s['font']:
                    hs.append([s['bbox'][0],s['bbox'][1],s['text'].strip()])
    hs.sort(key=lambda h:(round(h[0]/30),h[1]))
    cols=[]
    for x,y,t in hs:
        if cols and abs(cols[-1][1]-x)<30: cols[-1][0]+=' '+t
        else: cols.append([t,x,y])
    cols.sort(key=lambda c:c[1]); return cols
def page_columns(pno):
    cols=headers(pno)
    if not cols: return []
    xs=[c[1] for c in cols]; gaps=[b-a for a,b in zip(xs,xs[1:])]
    w=min(gaps) if gaps else 266
    if w>300: w=266
    return [(t,x-16,x-16+w,y) for t,x,y in cols]
def spans_in(pno,x0,x1):
    out=[]
    for b in d[pno].get_text('dict')['blocks']:
        for l in b.get('lines',[]):
            for s in l['spans']:
                if not s['text'].strip(): continue
                cx=(s['bbox'][0]+s['bbox'][2])/2
                if x0<=cx<x1: out.append(dict(x=s['bbox'][0],x1=s['bbox'][2],y=s['bbox'][1],y1=s['bbox'][3],font=s['font'],size=round(s['size'],1),text=s['text']))
    return out
def to_lines(spans):
    spans.sort(key=lambda s:(round(s['y']),s['x'])); lines=[]
    for s in spans:
        if lines and abs(lines[-1]['y']-s['y'])<3 and s['x']-lines[-1]['x1']<12:
            g=lines[-1]; sep='' if g['text'].endswith(' ') or s['text'].startswith(' ') or s['x']-g['x1']<1 else ' '
            g['text']+=sep+s['text']; g['x1']=max(g['x1'],s['x1']); g['fonts'].add((s['font'],s['size']))
        else: lines.append(dict(y=s['y'],y1=s['y1'],x=s['x'],x1=s['x1'],text=s['text'],fonts={(s['font'],s['size'])}))
    for l in lines:
        l['text']=fix(l['text']); l['bold']=any('Bold' in f or 'Black' in f for f,_ in l['fonts']); l['size']=max(s for _,s in l['fonts']); l['font']=sorted(l['fonts'])[0][0]
    return [l for l in lines if l['text']]
def page_serie(pno):
    """label vpravo dole: EXTREME / SERIE, TENTS / ACCESSORIES, WATERPROOF ..."""
    parts=[]
    for b in d[pno].get_text('dict')['blocks']:
        for l in b.get('lines',[]):
            for s in l['spans']:
                if 8.5<=s['size']<=9.5 and s['bbox'][1]>580 and s['text'].strip(): parts.append((s['bbox'][1],s['bbox'][0],fix(s['text'])))
    parts.sort()
    t=' '.join(p[2] for p in parts)
    t=re.sub(r'\b\d{2,3}\b','',t).strip()  # číslo stránky
    return t or None
def parse_column(sec,name,x0,x1,pno):
    sp=spans_in(pno,x0,x1); w=x1-x0; split=x0+146 if w>=230 else x0+w*0.9
    vl=[t['x'] for t in sp if t['text'].strip().upper().startswith('VLASTNOSTI') and t['x']-x0>100]
    if vl: split=min(vl)-4
    left=to_lines([s for s in sp if s['x']<split or s['size']>=15]); right=to_lines([s for s in sp if not(s['x']<split or s['size']>=15)])
    P=dict(name=fix(name),page=pno+1,section=sec)
    flags=[]
    for l in left+right:
        if l['text'].lower()=='new': flags.append('new')
        if 'camel bag' in l['text'].lower(): flags.append('camelbag')
    P['flags']=sorted(set(flags))
    body=[l for l in left if l['size']<15 and l['text'].lower()!='new' and 'camel bag' not in l['text'].lower() and not (l['size']>=9.5 and re.fullmatch(r'\d{1,3}',l['text']))]
    labels=[l for l in body if is_label(l['text'])]
    first_label_y=min([l['y'] for l in labels]+[l['y'] for l in right if is_label(l['text'])]+[9999])
    # spec: tučné řádky nad prvním labelem (v obou podsloupcích), mimo MyriadPro kóty
    spec=[l['text'] for l in body+right if l['y']<first_label_y-2 and l['y']>50 and l['bold'] and 'DIN' in l['font'] and l['size']<9.5]
    temps=[l['text'] for l in body+right if l['y']<first_label_y-2 and 8.9<=l['size']<=9.4 and 'DIN' in l['font']]
    small=[l['text'] for l in body+right if l['y']<first_label_y-2 and l['size']<=5.5 and 'DIN' in l['font']]
    P['spec_raw']=spec; P['temps_raw']=temps; P['spec_small']=small
    # teploty spacáků podle pozice zleva: comfort, limit, extreme
    tp=[(t['x'],t['text'].strip()) for t in sp if 8.9<=t['size']<=9.4 and 'Bold' in t['font'] and t['y']<first_label_y-2 and re.fullmatch(r'[+-]?\s*\d{1,2}',t['text'].strip())]
    P['temps_pos']=[re.sub(r'\s+','',v) for x,v in sorted(tp)]
    # fields z levého sloupce
    fields={}; desc=[]; cur=None; last_field_y=first_label_y
    for l in body:
        if l['y']<first_label_y-2: continue
        if is_label(l['text']):
            cur=l['text'].rstrip(':').upper().replace(' / MATERIAL','').replace(' / DIMENSIONS',''); fields.setdefault(cur,[]); last_field_y=l['y']; continue
        if l['size']>=9.5: continue
        if 'Myriad' in l['font'] or 'DIN2014' in l['font']: continue
        if l['bold']:
            # popis: tučný text 6pt, ne label, po polích; ukončí se u čísel barev (jednociferné) nebo y>470
            if re.fullmatch(r'\d',l['text']) or l['y']>520: cur=None; continue
            desc.append(l['text']); cur=None
        else:
            if cur and l['y']<520: fields[cur].append(l['text'])
    P['fields']={k:fix(' '.join(v)) for k,v in fields.items()}
    P['desc']=fix(' '.join(desc))
    if P['desc'] and re.search(r'[A-Za-zÀ-ž0-9]$',P['desc']): P['desc']+='.'
    # pravý sloupec: VLASTNOSTI / AKTIVITY
    feats=[]; acts=[]; mode=None
    for l in right:
        t=l['text']
        if l['size']>=9.5 or 'Myriad' in l['font']: continue
        if t.upper().startswith('VLASTNOSTI'): mode='f'; continue
        if t.upper().startswith('AKTIVITY'): mode='a'; continue
        if is_label(t): mode=None; continue
        if l['y']>560 or re.fullmatch(r'\d',t) or l['bold']: continue
        if (l['x']-x0)>215 and not t.startswith('•'): continue
        if l['y']>520 and not t.startswith('•'): continue
        if mode is None: continue
        tgt=feats if mode=='f' else acts
        if t.startswith('•'): tgt.append(t[1:].strip())
        elif tgt and any(x.startswith('•') for x in [ll['text'] for ll in right]): tgt[-1]+=' '+t
        else: tgt.append(t)
    P['features']=[fix(f) for f in feats if f]; P['activities']=[fix(a) for a in acts if a]
    # záložní fotka z PDF: výřez sloupce nad specifikací, vyrenderovaný a oříznutý
    P['pdf_photo']=None
    try:
        spec_y=min([l['y'] for l in body+right if l['y']<first_label_y-2 and l['y']>50 and l['bold'] and 'DIN' in l['font'] and l['size']<9.5 and not re.fullmatch(r'\d',l['text'].strip()) and l['text'].strip().lower()!='new']+[first_label_y])
        head_y1=max([l['y1'] for l in left if l['size']>=15]+[66])
        cx0=x0+(x1-x0)*0.56 if sec=='sleeping' else x0+2
        cy0=head_y1+3
        if sec=='sleeping':
            ty=[t['y'] for t in sp if 8.9<=t['size']<=9.4 and 'Bold' in t['font'] and t['y']<first_label_y-2]
            cy1=(min(ty)-12) if ty else first_label_y-6
        else: cy1=max(spec_y-24,cy0+80)
        clip=fitz.Rect(cx0,cy0,x1-2,cy1)
        fn=re.sub(r'[^A-Za-z0-9]+','_',P['name']).strip('_')+'.jpg'
        out=os.path.join(DATA,'pdf_photos',fn); os.makedirs(os.path.dirname(out),exist_ok=True)
        if not os.path.exists(out):
            pix=d[pno].get_pixmap(dpi=220,clip=clip,colorspace=fitz.csRGB)
            img=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
            from PIL import ImageDraw
            W,H=img.size; scale=220/72
            if 'new' in P['flags']:
                # vybělit diagonální stužku "new" v pravém horním rohu (cca 42 pt trojúhelník na stránce)
                t=int(42*scale); ImageDraw.Draw(img).polygon([(W-t,0),(W,0),(W,t)],fill=(255,255,255))
            if sec=='mattress':
                # vybělit vzorník barev vlevo nahoře (do y=127 pt na stránce)
                nsw=max(1,len([t for t in sp if t['size']<=5.5 and 'DIN' in t['font'] and t['y']<first_label_y]))
                ImageDraw.Draw(img).rectangle([0,0,int(W*0.30),int((127+33*(nsw-1)-cy0)*scale)],fill=(255,255,255))
            from PIL import ImageChops
            bg=Image.new('RGB',img.size,(255,255,255)); diff=ImageChops.difference(img,bg).convert('L').point(lambda v:255 if v>18 else 0)
            bbox=diff.getbbox()
            if bbox: img=img.crop((max(0,bbox[0]-8),max(0,bbox[1]-8),min(img.width,bbox[2]+8),min(img.height,bbox[3]+8)))
            img.save(out,quality=88)
        P['pdf_photo']='data/pdf_photos/'+fn
    except Exception as e: P['pdf_photo_err']=str(e)
    return P
def main():
    prods=[]; serie=None
    for pno1 in range(13,135):
        pno=pno1-1; sec=section(pno1)
        s=page_serie(pno)
        if s and len(s)<40: serie=s
        cols=page_columns(pno)
        if not cols: continue
        # divider pages ("TENTS DETAIL – EXTREME SERIE") přeskočit
        if any('DETAIL' in c[0] or 'CONTENT' in c[0] or 'COLLECTION' in c[0] for c in cols): continue
        for name,x0,x1,y in cols:
            if (name.lower().startswith('party') and 'accessories' in name.lower()) or name.startswith('EN 13537'): continue
            P=parse_column(sec,name,x0,x1,pno); P['serie']=serie; prods.append(P)
    json.dump(prods,open(os.path.join(DATA,'pdf_products.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    print('products',len(prods))
    # úvodní/technické strany jako obrázky
    os.makedirs(os.path.join(DATA,'pdf_pages'),exist_ok=True)
    for pno1 in [4,6,7,8,10,11,12,13,16,21,26,29,32,42,43,44,45,46,58,59,60,61,70,71,86,87,88,89,90,91,92,93]:
        out=os.path.join(DATA,'pdf_pages',f'p{pno1:03d}.jpg')
        if not os.path.exists(out): d[pno1-1].get_pixmap(dpi=110).save(out)
    # cover foto
    for im in d[0].get_image_info(xrefs=True):
        if im.get('xref'):
            pix=fitz.Pixmap(d,im['xref'])
            if pix.n-pix.alpha>=4: pix=fitz.Pixmap(fitz.csRGB,pix)
            pix.save(os.path.join(DATA,'cover_ss26.png')); break
if __name__=='__main__': main()
