"""Sjednocení fotek v ss27/foto: světlé pozadí -> bílé (záplavová výplň z rohů), ořez okrajů, jednotný okraj 4 %.
Idempotentní; volá se na konci build_data.py."""
import os, sys, json
from PIL import Image, ImageChops, ImageDraw
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.abspath(os.path.join(HERE,'..')); FOTO=os.path.join(ROOT,'foto')
def border_stats(g):
    w,h=g.size; px=list(g.crop((0,0,w,2)).getdata())+list(g.crop((0,h-2,w,h)).getdata())+list(g.crop((0,0,2,h)).getdata())+list(g.crop((w-2,0,w,h)).getdata())
    return sum(px)/len(px), sum(1 for p in px if p<200)/len(px)
def normalize(path,pad=0.04):
    im=Image.open(path).convert('RGB'); w,h=im.size; g=im.convert('L'); mean,dark=border_stats(g)
    k=max(4,min(w,h)//25)
    corners=[sum(g.crop(b).getdata())/(k*k) for b in [(0,0,k,k),(w-k,0,w,k),(0,h-k,k,h),(w-k,h-k,w,h)]]
    if (mean<215 or dark>0.15) and min(corners)<225: return 'lifestyle'
    # světle šedé pozadí -> bílé
    if mean<250:
        orig=im.copy()
        def nonwhite(x):
            return sum(1 for v in ImageChops.difference(x,Image.new('RGB',x.size,(255,255,255))).convert('L').point(lambda v:255 if v>22 else 0).getdata() if v)
        before=nonwhite(im)
        for pt in [(0,0),(w-1,0),(0,h-1),(w-1,h-1),(w//2,0),(w//2,h-1),(0,h//2),(w-1,h//2)]:
            if im.getpixel(pt)!=(255,255,255): ImageDraw.floodfill(im,pt,(255,255,255),thresh=28)
        if nonwhite(im)<0.85*before: im=orig  # výplň zasáhla produkt -> vrátit
    # stín u sytě barevných kusů: světle šedé pixely (bez sytosti) vybělit
    import colorsys
    sm=im.copy(); sm.thumbnail((100,100)); n_=sat=lg=0
    for px in sm.getdata():
        h_,s_,v_=colorsys.rgb_to_hsv(*[x/255 for x in px])
        if v_>0.96 and s_<0.08: continue
        n_+=1
        if s_>0.3: sat+=1
        elif s_<0.12 and 0.55<v_<0.96: lg+=1
    if n_ and sat/n_>0.35 and lg/n_>0.10:
        px=im.load(); W_,H_=im.size
        for yy in range(H_):
            for xx in range(W_):
                r_,g_,b_=px[xx,yy]; mx=max(r_,g_,b_); mn=min(r_,g_,b_)
                if mx>140 and mx<247 and (mx-mn)<=int(mx*0.12): px[xx,yy]=(255,255,255)
    bg=Image.new('RGB',im.size,(255,255,255)); diff=ImageChops.difference(im,bg).convert('L').point(lambda v:255 if v>22 else 0)
    bb=diff.getbbox()
    if not bb: return 'empty'
    cw,ch=bb[2]-bb[0],bb[3]-bb[1]; p=int(max(cw,ch)*pad)+2
    box=(max(0,bb[0]-p),max(0,bb[1]-p),min(w,bb[2]+p),min(h,bb[3]+p))
    out=im.crop(box)
    # okraj doplnit bílou, aby byl kolem produktu vždy stejný prostor
    canvas=Image.new('RGB',(cw+2*p,ch+2*p),(255,255,255)); canvas.paste(out,(p-(bb[0]-box[0]),p-(bb[1]-box[1])))
    if canvas.size!=im.size or mean<250:
        canvas.thumbnail((900,900)); canvas.save(path,quality=86,optimize=True); return 'fixed'
    return 'ok'
if __name__=='__main__':
    files=sys.argv[1:] or [os.path.join(FOTO,f) for f in os.listdir(FOTO) if f.lower().endswith('.jpg')]
    import collections; st=collections.Counter(); life=[]
    status={}
    for f in files:
        r=normalize(f); st[r]+=1; status[os.path.basename(f)]=r
        if r=='lifestyle': life.append(os.path.basename(f))
    json.dump(status,open(os.path.join(ROOT,'data','photo_status.json'),'w'))
    print('normalize:',dict(st)); print('lifestyle (nebílé pozadí):',life)

