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
def raw_rgba(xref):
    pix=fitz.Pixmap(d,xref)
    if pix.n-pix.alpha>=4 or pix.colorspace is None or pix.colorspace.n!=3: pix=fitz.Pixmap(fitz.csRGB,pix)
    im=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGBA')
    sm=d.extract_image(xref).get('smask')
    if sm:
        mp=fitz.Pixmap(d,sm); m=Image.open(io.BytesIO(mp.tobytes('png'))).convert('L').resize(im.size); im.putalpha(m)
    return im
def composite_photo(pno,x0,x1,y_top,y_bot,dpi=300):
    """Fotka produktu složená z původních rastrů na stránce (sazba je někdy ořezává rámečkem). Vrací (PIL RGB, Rect) nebo None."""
    infos=[]; tf={}
    for i in d[pno].get_image_info(xrefs=True):
        if not i.get('xref'): continue
        infos.append((fitz.Rect(i['bbox']),i['xref'])); tf[i['xref']]=i.get('transform')
    def incol_frac(b): return max(0,min(b.x1,x1)-max(b.x0,x0))/max(1,b.width)
    cand=[(b,x) for b,x in infos if b.width>=20 and b.height>=20 and b.y0<y_bot and b.y1>y_top and (x0-6<=(b.x0+b.x1)/2<=x1+6 or incol_frac(b)>=0.4)]
    if not cand: return None
    # bloky: sousedící dlaždice sloučit
    blocks=[]
    for b,x in cand: blocks.append([fitz.Rect(b),[(b,x)]])
    merged=True
    while merged:
        merged=False
        for i in range(len(blocks)):
            for j in range(i+1,len(blocks)):
                r2=blocks[j][0]
                if blocks[i][0].intersects(fitz.Rect(r2.x0-2,r2.y0-2,r2.x1+2,r2.y1+2)):
                    blocks[i][0]|=r2; blocks[i][1]+=blocks[j][1]; del blocks[j]; merged=True; break
            if merged: break
    incol=[bl for bl in blocks if x0-6<=(bl[0].x0+bl[0].x1)/2<=x1+6 and (bl[0].width>=100 or bl[0].height>=100)]
    if not incol: return None
    main=max(incol,key=lambda bl:bl[0].width*bl[0].height)[0]
    sel=[bl for bl in blocks if (bl[0].width>=60 or bl[0].height>=60) and (x0-6<=(bl[0].x0+bl[0].x1)/2<=x1+6 or (bl[0].intersects(main) and incol_frac(bl[0])>=0.4))]
    sel=[bl for bl in sel if max(bl[0].width,bl[0].height)>=45]   # malé kulaté badge ikony přes fotku vynechat
    items=[t for bl in sel for t in bl[1]]
    # duplicitní umístění (celý + oříznutý rastr se stejným počátkem): nechat větší
    keep=[]
    for b,x in items:
        dup=any(x2!=x and abs(b2.x0-b.x0)<1.5 and abs(b2.y0-b.y0)<1.5 and b2.contains(b) and (b2.width*b2.height)>(b.width*b.height) for b2,x2 in items)
        if not dup: keep.append((b,x))
    if not keep: return None
    u=fitz.Rect(keep[0][0])
    for b,_ in keep[1:]: u|=b
    sc=dpi/72; W=int(u.width*sc)+1; H=int(u.height*sc)+1
    if W<50 or H<50: return None
    # otočené/zrcadlené umístění rastru neskládáme (jen prostý posun+měřítko)
    for b,x in keep:
        t=tf.get(x)
        if t and (t[0]<=0 or t[3]<=0 or abs(t[1])>0.01*abs(t[0]) or abs(t[2])>0.01*abs(t[3])): return None
    canvas=Image.new('RGBA',(W,H),(255,255,255,255))
    order={x:i for i,(_,x) in enumerate(infos)}
    mainb=max(keep,key=lambda t:t[0].width*t[0].height)[0]
    for b,x in sorted(keep,key=lambda t:order.get(t[1],0)):
        try: im=raw_rgba(x)
        except Exception: return None
        im=im.resize((max(1,int(b.width*sc)),max(1,int(b.height*sc))))
        if b!=mainb and im.getextrema()[3][0]==255:
            # vložený rastr bez masky: bílé pozadí udělat průhledné, aby nepřekryl hlavní fotku bílým obdélníkem
            r,g,bb,a=im.split(); from PIL import ImageChops as IC
            mn=IC.darker(IC.darker(r,g),bb); alpha=mn.point(lambda v:0 if v>=246 else (255 if v<=232 else int((246-v)/14*255)))
            im.putalpha(alpha)
        canvas.alpha_composite(im,(int((b.x0-u.x0)*sc),int((b.y0-u.y0)*sc)))
    if os.environ.get('PHOTO_DEBUG'): print('   COMPOSITE items',[(x,[round(v) for v in b]) for b,x in keep])
    return canvas.convert('RGB'),u
def parse_column(sec,name,x0,x1,pno):
    sp=spans_in(pno,x0,x1); w=x1-x0; split=x0+146 if w>=230 else x0+w*0.9
    vl=[t['x'] for t in sp if t['text'].strip().upper().startswith('VLASTNOSTI') and t['x']-x0>100]
    if vl: split=min(vl)-4
    left=to_lines([s for s in sp if s['x']<split or s['size']>=15]); right=to_lines([s for s in sp if not(s['x']<split or s['size']>=15)]); right0=list(right)
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
    P['col']=[round(x0,1),round(x1,1)]; P['first_label_y']=round(first_label_y,1) if first_label_y<9999 else None
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
        head_y1=max([l['y1'] for l in left if l['size']>=15 and l['y']<200]+[66])
        cx0=x0+(x1-x0)*0.56 if (sec=='sleeping' and P['name'] not in ('HAVEN',)) else x0+2
        cy0=head_y1+3
        if sec=='sleeping':
            ty=[t['y'] for t in sp if 8.9<=t['size']<=9.4 and 'Bold' in t['font'] and t['y']<first_label_y-2]
            cy1=(min(ty)-12) if ty else first_label_y-6
        else: cy1=max(spec_y-24,cy0+80)
        clip=fitz.Rect(cx0,cy0,x1-2,cy1)
        # skutečný rozsah fotky podle rastrových obrázků na stránce (fotky často přesahují sloupec; dlaždice sloučit)
        blocks=[]
        for im_ in d[pno].get_image_info():
            b=fitz.Rect(im_['bbox'])
            if b.width<8 or b.height<8 or b.y0>=first_label_y-20 or b.y1<=head_y1-30: continue
            if not (x0-6<=(b.x0+b.x1)/2<=x1+6): continue
            blocks.append(b)
        merged=True
        while merged:
            merged=False
            for i in range(len(blocks)):
                for j in range(i+1,len(blocks)):
                    bj=blocks[j]
                    if blocks[i].intersects(fitz.Rect(bj.x0-2,bj.y0-2,bj.x1+2,bj.y1+2)): blocks[i]|=bj; del blocks[j]; merged=True; break
                if merged: break
        big=[b for b in blocks if b.width>=100 or b.height>=100]
        photo_u=None
        if big:
            u=fitz.Rect(big[0])
            for b in big[1:]: u|=b
            photo_u=u
            clip=fitz.Rect(u.x0-2,max(head_y1+1,u.y0-2),u.x1+2,min(cy1,u.y1+2))
        fn=re.sub(r'[^A-Za-z0-9]+','_',P['name']).strip('_')+'.jpg'
        out=os.path.join(DATA,'pdf_photos',fn); os.makedirs(os.path.dirname(out),exist_ok=True)
        if not os.path.exists(out):
            PDPI=300
            comp=composite_photo(pno,x0,x1,head_y1-40,cy1+30) if (os.environ.get('PHOTO_RENDER')!='1' and sec!='mattress') else None   # karimatky: render je věrnější
            pix=d[pno].get_pixmap(dpi=PDPI,clip=clip,colorspace=fitz.csRGB)
            img=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB'); P['pdf_photo_src']='render'
            if comp:
                from PIL import ImageChops as _IC
                def _content(im_):
                    m=_IC.difference(im_,Image.new('RGB',im_.size,(255,255,255))).convert('L').point(lambda v:255 if v>18 else 0)
                    bb=m.getbbox(); return ((bb[2]-bb[0])*(bb[3]-bb[1])) if bb else 0
                if _content(comp[0])>=0.85*_content(img): img,clip=comp[0],comp[1]; P['pdf_photo_src']='composite'
            from PIL import ImageDraw
            W,H=img.size; scale=PDPI/72
            # stužka "new" v pravém horním rohu: podle příznaku, nebo když je roh výrazně červený
            t=int(42*scale); corner=img.crop((max(0,W-t),0,W,min(H,t)))
            nred=sum(1 for r_,g_,b_ in corner.getdata() if r_>170 and g_<80 and b_<80); ncor=max(1,corner.width*corner.height)
            if 'new' in P['flags'] or nred/ncor>0.12:
                t2=int(60*scale); ImageDraw.Draw(img).polygon([(W-t2,0),(W,0),(W,t2)],fill=(255,255,255))
            if sec=='mattress':
                # vybělit vzorník barev vlevo nahoře: až po spodní okraj posledního popisku barvy (malý text v levé třetině sloupce)
                labs=[t for t in sp if t['size']<=6.5 and t['y']<spec_y-4 and t['y']>clip.y0 and clip.x0-2<=t['x']<clip.x0+0.4*clip.width and re.search(r'[A-Za-z]',t['text']) and not is_label(t['text'])]
                if labs:
                    xr=max(t['x1'] for t in labs)+16; ybot=max(t['y1'] for t in labs)+4
                    ImageDraw.Draw(img).rectangle([0,0,int((xr-clip.x0)*scale),int((ybot-clip.y0)*scale)],fill=(255,255,255))
                if os.environ.get('PHOTO_DEBUG'): print('   WHITEN',P['name'],[(t['text'],round(t['x']),round(t['y'])) for t in labs])
            from PIL import ImageChops
            bg=Image.new('RGB',img.size,(255,255,255)); diff=ImageChops.difference(img,bg).convert('L').point(lambda v:255 if v>18 else 0)
            bbox=diff.getbbox()
            if bbox: img=img.crop((max(0,bbox[0]-8),max(0,bbox[1]-8),min(img.width,bbox[2]+8),min(img.height,bbox[3]+8)))
            # odstranit drobné zbytky (vzorníky, číslice) oddělené bílou mezerou od hlavního obsahu
            def main_run(mask_line,minlen,mingap):
                runs=[];i=0;n=len(mask_line)
                while i<n:
                    if not mask_line[i]: i+=1; continue
                    j=i
                    while j<n and (mask_line[j] or any(mask_line[min(n-1,j+g)] for g in range(1,mingap))): j+=1
                    runs.append((i,j)); i=j
                keep=[r for r in runs if (r[1]-r[0])>=minlen]
                if not keep: return None
                return (keep[0][0],keep[-1][1])
            dm=ImageChops.difference(img,Image.new('RGB',img.size,(255,255,255))).convert('L').point(lambda v:255 if v>18 else 0)
            Wd,Hd=dm.size
            cols=[dm.crop((x,0,x+1,Hd)).getbbox() is not None for x in range(Wd)]
            rx=main_run(cols,int(Wd*0.12),max(6,int(Wd*0.03)))
            if rx and (rx[1]-rx[0])<Wd-4:
                img=img.crop((max(0,rx[0]-8),0,min(Wd,rx[1]+8),Hd)); dm=dm.crop((max(0,rx[0]-8),0,min(Wd,rx[1]+8),Hd)); Wd,Hd=dm.size
            rows=[dm.crop((0,y,Wd,y+1)).getbbox() is not None for y in range(Hd)]
            ry=main_run(rows,int(Hd*0.12),max(6,int(Hd*0.03)))
            if ry and (ry[1]-ry[0])<Hd-4: img=img.crop((0,max(0,ry[0]-8),Wd,min(Hd,ry[1]+8)))
            if os.environ.get('PHOTO_DEBUG'): print('   PHOTO',P['name'],'clip',[round(v) for v in clip],'cy1',round(cy1),'spec_y',round(spec_y),'bbox',bbox,'rx',rx,'ry',ry,'final',img.size)
            img.save(out,quality=88)
        P['pdf_photo']='data/pdf_photos/'+fn
    except Exception as e: P['pdf_photo_err']=str(e)
    # vzorníky barev z PDF (malé obrázky u čísel barev) -> data/pdf_swatch/<slug>_<n>.png + popisek
    P['swatches']=[]
    try:
        nums=[t for t in sp if re.fullmatch(r'\d',t['text'].strip()) and 'Bold' in t['font'] and 5.5<=t['size']<=6.5 and t['y']>60]
        names=[t for t in sp if 'Regul' in t['font'] and 4.5<=t['size']<=6.5 and t['text'].strip() and not is_label(t['text']) and not re.search(r'\d|•',t['text'])]
        for t in nums:
            x,y=t['x'],t['y']
            if y<330:   # vzorník vlevo, název vpravo dole; hranice = další číslo pod ním
                lab=[n for n in names if n['x']>x+5 and y-4<n['y']<y+32]
                ybot=(min(n['y'] for n in lab)-1) if lab else y+22
                box=fitz.Rect(x+8,y-4,x+0.44*(x1-x0),ybot)
            else:       # vzorník dole, název pod ním; hranice = polovina vzdálenosti k sousednímu číslu
                lab=[n for n in names if -8<=(n['x']-x)<26 and y<n['y']<y+100]
                lab.sort(key=lambda n:n['y'])
                right=[u['x'] for u in nums if u['x']>x+5 and abs(u['y']-y)<8]
                box=fitz.Rect(x-4,y+8,(x+41) if right else (x+64),(lab[0]['y']-2) if lab else y+70)
            label=fix(' '.join(n['text'] for n in sorted(lab,key=lambda n:(round(n['y']),n['x']))[:2])).strip()
            if box.width<10 or box.height<8: continue
            pix=d[pno].get_pixmap(dpi=300,clip=box,colorspace=fitz.csRGB)
            img=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
            from PIL import ImageChops
            bb=ImageChops.difference(img,Image.new('RGB',img.size,(255,255,255))).convert('L').point(lambda v:255 if v>18 else 0).getbbox()
            if not bb or (bb[2]-bb[0])<20 or (bb[3]-bb[1])<12: continue
            img=img.crop((max(0,bb[0]-4),max(0,bb[1]-4),min(img.width,bb[2]+4),min(img.height,bb[3]+4)))
            if sec=='sleeping' and img.width>1.5*img.height: img=img.rotate(90,expand=True)  # spacák naležato -> nastojato (kapuce nahoře)
            os.makedirs(os.path.join(DATA,'pdf_swatch'),exist_ok=True)
            fn=re.sub(r'[^A-Za-z0-9]+','_',P['name']).strip('_')+'_'+t['text'].strip()+'.png'
            img.save(os.path.join(DATA,'pdf_swatch',fn))
            P['swatches'].append(dict(n=t['text'].strip(),label=label,file='data/pdf_swatch/'+fn))
    except Exception as e: P['swatch_err']=str(e)
    # rozkres rozměrů (vektorová kresba pod popisem, nad spodní řadou vzorníků) -> data/pdf_draw/<slug>.png
    P['pdf_draw']=None
    try:
        if sec in ('tents','sleeping','mattress'):
            alll=left+right0
            bottom_nums=[t['y'] for t in sp if re.fullmatch(r'\d',t['text'].strip()) and 'Bold' in t['font'] and 5.5<=t['size']<=6.5 and t['y']>330]
            sw_top=(min(bottom_nums)-4) if bottom_nums else 578
            def is_text_line(l):
                t=l['text'].strip()
                if re.search(r'layer|padding|chambered|filling|hollow',t,re.I): return False
                t=re.sub(r'\d+([/,.]\d+)?\s*(cm|mm)','',t)
                return len(re.findall(r'[A-Za-zÀ-ž]',t))>=3
            txt=[l for l in alll if l['y']>first_label_y-2 and l['y1']<sw_top and l['size']<9.5 and is_text_line(l)]
            desc_bottom=max([l['y1'] for l in txt]+[first_label_y])
            band=fitz.Rect(x0,desc_bottom+2,x1,sw_top)
            if band.height>25:
                pix=d[pno].get_pixmap(dpi=300,clip=band,colorspace=fitz.csRGB)
                img=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
                from PIL import ImageChops
                bb=ImageChops.difference(img,Image.new('RGB',img.size,(255,255,255))).convert('L').point(lambda v:255 if v>22 else 0).getbbox()
                if bb and (bb[2]-bb[0])>200 and (bb[3]-bb[1])>80:
                    img=img.crop((max(0,bb[0]-10),max(0,bb[1]-10),min(img.width,bb[2]+10),min(img.height,bb[3]+10)))
                    os.makedirs(os.path.join(DATA,'pdf_draw'),exist_ok=True)
                    fn=re.sub(r'[^A-Za-z0-9]+','_',P['name']).strip('_')+'.png'
                    img.save(os.path.join(DATA,'pdf_draw',fn)); P['pdf_draw']='data/pdf_draw/'+fn
    except Exception as e: P['draw_err']=str(e)
    # pás ikon pod fotkou: oranžové ikony specifikací přeskočit, ostatní (badge: TAPED SEAMS, YKK, RAINCOVER, TRIGUARD…) uložit
    P['pdf_icons']=[]
    try:
        vals=[l for l in body+right0 if l['y']<first_label_y-2 and l['y']>50 and l['bold'] and 'DIN' in l['font'] and l['size']<8.5 and l['text'].strip().lower()!='new' and not re.fullmatch(r'\d',l['text'].strip())]
        if vals:
            vy=max(l['y'] for l in vals); vy=min(l['y'] for l in vals if l['y']>vy-14); vy1=max(l['y1'] for l in vals if l['y']>=vy-1)
            bx1=x1 if sec in ('tents','backpacks','sportswear') else x0+(x1-x0)*0.55   # spacáky/karimatky: fotka vpravo ve stejné výšce
            band=fitz.Rect(x0,vy-(46 if sec in ('backpacks','sportswear') else 36),bx1,vy1+2)
            pix=d[pno].get_pixmap(dpi=300,clip=band,colorspace=fitz.csRGB)
            img=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
            W,H=img.size; px=img.load()
            if os.environ.get('ICON_DEBUG'):
                os.makedirs(os.path.join(DATA,'pdf_icons'),exist_ok=True); img.save(os.path.join(DATA,'pdf_icons','_band_'+re.sub(r'[^A-Za-z0-9]+','_',P['name']).strip('_')+'.png'))
            colmask=[False]*W
            Hicons=max(10,int((vy-band.y0)*300/72)-3)   # dělit jen podle řádků ikon (bez řádku hodnot/popisků pod nimi)
            for x in range(W):
                for y in range(min(H,Hicons)):
                    r,g,b=px[x,y]
                    if r+g+b<420: colmask[x]=True; break
            comps=[]; x=0
            while x<W:
                if not colmask[x]: x+=1; continue
                s=x
                while x<W and (colmask[x] or any(colmask[min(W-1,x+k)] for k in range(1,9))): x+=1
                comps.append((s,x))
            os.makedirs(os.path.join(DATA,'pdf_icons'),exist_ok=True)
            base=re.sub(r'[^A-Za-z0-9]+','_',P['name']).strip('_')
            k=0
            for s,e in comps:
                if e-s<25: continue
                crop=img.crop((max(0,s-4),0,min(W,e+4),H))
                from PIL import ImageChops
                bb=ImageChops.difference(crop,Image.new('RGB',crop.size,(255,255,255))).convert('L').point(lambda v:255 if v>22 else 0).getbbox()
                if not bb: continue
                if bb[1]<=1:
                    # dotýká se horního okraje = zbytek fotky/stínu nad ikonou: odříznout horní běh řádků po první bílou mezeru
                    g=crop.convert('L'); Wc,Hc=g.size; rows=[min(g.crop((0,y,Wc,y+1)).getdata())<235 for y in range(Hc)]
                    y=0
                    while y<Hc and rows[y]: y+=1
                    while y<Hc and not rows[y]: y+=1
                    if y>=Hc-20: continue
                    crop=crop.crop((0,y,Wc,Hc))
                    bb=ImageChops.difference(crop,Image.new('RGB',crop.size,(255,255,255))).convert('L').point(lambda v:255 if v>22 else 0).getbbox()
                    if not bb: continue
                crop=crop.crop(bb)
                # klasifikace: oranžové ikony specifikací (kg, sbalený rozměr, osoby, objem, R-value, pohlaví, velikost)
                import colorsys
                n=0; orange=0; red=0; satn=0
                for r,g,b in crop.getdata():
                    if r+g+b>=720: continue
                    n+=1
                    h,sat,v=colorsys.rgb_to_hsv(r/255,g/255,b/255)
                    if sat>0.25: satn+=1
                    if sat>0.25 and 0.03<=h<=0.13: orange+=1
                    if sat>0.6 and v>0.6 and (h<0.03 or h>0.95): red+=1
                if os.environ.get('ICON_DEBUG'): print('   comp',P['name'],s,e,'n',n,'satn',satn,'orange',orange,'red',red,'bb',bb,'size',crop.size)
                if n<400 or (satn and orange/satn>0.6): continue
                if red/n>0.6 and (W-e)<12: continue   # stužka "new" u pravého okraje
                if crop.width<30 or crop.height<30: continue
                k+=1; fn=f'{base}_{k}.png'; crop.save(os.path.join(DATA,'pdf_icons',fn)); P['pdf_icons'].append('data/pdf_icons/'+fn)
    except Exception as e: P['icon_err']=str(e)
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
        if not os.path.exists(out): d[pno1-1].get_pixmap(dpi=160).save(out)
    # cover foto
    for im in d[0].get_image_info(xrefs=True):
        if im.get('xref'):
            pix=fitz.Pixmap(d,im['xref'])
            if pix.n-pix.alpha>=4: pix=fitz.Pixmap(fitz.csRGB,pix)
            pix.save(os.path.join(DATA,'cover_ss26.png')); break
if __name__=='__main__': main()
