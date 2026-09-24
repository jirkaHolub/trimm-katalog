"""Kontrola, zda vizuál barvy (rozkres / fotka varianty / zadní fotka) odpovídá názvu barvy.
Porovnává dominantní odstíny obrázku s očekávanou barvou podle názvu. Výstup: ss27/data/color_check.json + kontaktní list podezřelých."""
import json, os, re, colorsys, sys, collections
from PIL import Image
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.abspath(os.path.join(HERE,'..')); DATA=os.path.join(ROOT,'data')
# očekávané odstíny (H ve stupních, nebo 'grey'/'black'/'white'); None = neověřovat
HUES={'jeans blue':(195,240),'blue':(190,245),'dark lagoon':(175,215),'lagoon':(165,205),'sea blue':(185,230),'mid.blue':(195,240),'royal blue':(205,245),'navy':(200,255),'dark navy':(200,260),'azure':(180,220),'steel blue':(190,230),'blue melange':(195,245),'navy melange':(200,255),'transparent blue':(190,245),
      'red':(335,20),'dark red':(330,20),'bordo':(320,15),'bordo anodized':(320,20),'brick':(0,30),'neon pink':(290,350),'pink':(290,355),'pinky':(290,355),'salmon':(350,30),'purple':(250,310),
      'orange':(5,45),'dark orange':(0,40),'signal orange':(5,45),'neon orange':(5,45),'orange melange':(5,45),
      'lemon':(45,80),'yellow':(40,70),'mustard':(30,60),'gold':(30,60),
      'lime green':(55,110),'signal green':(60,120),'light green':(60,130),'kiwi green':(60,120),'green':(60,175),'warm green':(50,130),'olive':(35,110),'dark olive':(35,110),'army green':(45,120),'khaki':(15,90),'dark khaki':(15,90),'lite khaki':(15,90),'khaki melange':(15,90),'deep khaki':(15,90),
      'black':'dark','grafit black':'dark','black melange':'dark','dark grey':'grey','grey':'grey','grey melange':'grey','silver':'grey','white':'white','off white':'white','transparent white':'white','white dots':'white','sand':(20,65),'beige':(15,60),'dark brown':(5,50),'army brown':(10,55),'melange':'grey','camouflage':None,'camo m05':None,'transparent':None,'transparent khaki':None}
def dominant(path):
    im=Image.open(os.path.join(ROOT,path)).convert('RGB'); im.thumbnail((120,120))
    hues=collections.Counter(); n=0; dark=0; grey=0; white=0
    for px in im.getdata():
        h,s,v=colorsys.rgb_to_hsv(*[c/255 for c in px])
        if v>0.94 and s<0.1: continue  # pozadí
        n+=1
        if v<0.22: dark+=1
        elif s<0.18: (white if v>0.8 else grey).__class__  # noqa
        if s<0.18 and v>=0.22:
            if v>0.8: white+=1
            else: grey+=1
            continue
        if v>=0.22: hues[int(h*360)//10*10]+=1
    if n<30: return None
    sat=sum(hues.values()) or 1
    return dict(n=n,dark=dark/n,grey=grey/n,white=white/n,satshare=sat/n,hues={k:v/sat for k,v in hues.most_common(8)})
def in_range(h,rng):
    a,b=rng; h=h+5  # střed 10° binu
    return (a<=h<=b) if a<=b else (h>=a or h<=b)
def check(path,cname):
    d=dominant(path)
    if not d: return 'nelze',d
    toks=[t.strip().lower() for t in cname.split('/') if t.strip()]
    exp=[HUES.get(t,'?') for t in toks]
    if any(e is None for e in exp): return 'ok',d
    # každá pojmenovaná barva by měla mít nezanedbatelný podíl (>=6 %) v obrázku; první barva >=12 %
    res=[]
    for i,(t,e) in enumerate(zip(toks,exp)):
        need=0.12 if i==0 else 0.05
        if e=='?': res.append(True); continue
        if e=='dark': share=d['dark']+d['grey']*0.5
        elif e=='grey': share=d['grey']+d['dark']*0.5
        elif e=='white': share=d['white']+d['grey']*0.3
        else:
            share=sum(v for h,v in d['hues'].items() if in_range(h,e))
            if d['satshare']<0.08: share=0  # skoro žádné barevné plochy
        res.append(share>=need)
    if all(res): return 'ok',d
    if not res[0]: return 'NESEDÍ',d
    return 'částečně',d
if __name__=='__main__':
    C=json.load(open(os.path.join(DATA,'catalog.json'),encoding='utf-8'))
    out=[]; bad=[]
    for r in C:
        for c in r['colors']:
            for kind in ('art','front','back'):
                p=c.get(kind)
                if not p or (kind in ('front','back') and c.get('generic')): continue
                st,d=check(p,c['name'])
                out.append(dict(model=r['name'],color=c['name'],kind=kind,path=p,status=st,dom=d and {k:d[k] for k in ('dark','grey','white','hues')}))
                if st=='NESEDÍ': bad.append((r['name'],c['name'],kind,p))
    json.dump(out,open(os.path.join(DATA,'color_check.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    cnt=collections.Counter(o['status'] for o in out)
    print('kontrola vizuálů:',dict(cnt))
    for b in bad: print('  NESEDÍ:',b)
    # kontaktní list podezřelých
    if bad:
        ims=[]
        for n,cn,kind,p in bad[:60]:
            im=Image.open(os.path.join(ROOT,p)).convert('RGB'); im.thumbnail((140,140)); ims.append(im)
        W=len(ims)*150; sheet=Image.new('RGB',(W,150),'white'); x=0
        for im in ims: sheet.paste(im,(x,0)); x+=150
        sheet.save(os.path.join(DATA,'color_check_bad.jpg'),quality=80)
