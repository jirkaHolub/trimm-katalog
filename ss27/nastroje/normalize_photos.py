"""Sjednocení fotek v ss27/foto: světlé pozadí -> bílé (záplavová výplň z rohů), ořez okrajů, jednotný okraj 4 %.
Idempotentní; volá se na konci build_data.py."""
import os, sys, json
from PIL import Image, ImageChops, ImageDraw
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.abspath(os.path.join(HERE,'..')); FOTO=os.path.join(ROOT,'foto')
SHADOW_FIX={'zena_mustard_dark_lagoon_front.jpg'}
ORIG=os.path.join(ROOT,'data','orig')
def border_stats(g):
    w,h=g.size; px=list(g.crop((0,0,w,2)).getdata())+list(g.crop((0,h-2,w,h)).getdata())+list(g.crop((0,0,2,h)).getdata())+list(g.crop((w-2,0,w,h)).getdata())
    return sum(px)/len(px), sum(1 for p in px if p<200)/len(px)
def normalize(path,pad=0.04):
    src=os.path.join(ORIG,os.path.basename(path))
    im=Image.open(src if os.path.exists(src) else path).convert('RGB'); w,h=im.size; g=im.convert('L'); mean,dark=border_stats(g)
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
    # stín: jen u ručně vybraných fotek (světle šedé plochy spojené s okrajem -> bílá)
    if os.path.basename(path) in SHADOW_FIX:
        px=im.load(); W_,H_=im.size; seen=set(); stack=[(x,0) for x in range(W_)]+[(x,H_-1) for x in range(W_)]+[(0,y) for y in range(H_)]+[(W_-1,y) for y in range(H_)]
        def light_grey(p):
            mx=max(p); mn=min(p); return mx>140 and (mx-mn)<=int(mx*0.12)
        while stack:
            x,y=stack.pop()
            if (x,y) in seen or not (0<=x<W_ and 0<=y<H_): continue
            seen.add((x,y)); p=px[x,y]
            if not light_grey(p): continue
            px[x,y]=(255,255,255)
            stack.extend(((x+1,y),(x-1,y),(x,y+1),(x,y-1)))
    bg=Image.new('RGB',im.size,(255,255,255)); diff=ImageChops.difference(im,bg).convert('L').point(lambda v:255 if v>22 else 0)
    bb=diff.getbbox()
    if not bb: return 'empty'
    cw,ch=bb[2]-bb[0],bb[3]-bb[1]; p=int(max(cw,ch)*pad)+2
    box=(max(0,bb[0]-p),max(0,bb[1]-p),min(w,bb[2]+p),min(h,bb[3]+p))
    out=im.crop(box)
    # okraj doplnit bílou, aby byl kolem produktu vždy stejný prostor
    canvas=Image.new('RGB',(cw+2*p,ch+2*p),(255,255,255)); canvas.paste(out,(p-(bb[0]-box[0]),p-(bb[1]-box[1])))
    canvas.thumbnail((900,900)); canvas.save(path,quality=86,optimize=True); return 'fixed' if (canvas.size!=im.size or mean<250) else 'ok'
if __name__=='__main__':
    files=sys.argv[1:] or [os.path.join(FOTO,f) for f in os.listdir(FOTO) if f.lower().endswith('.jpg')]
    import collections; st=collections.Counter(); life=[]
    status={}
    for f in files:
        r=normalize(f); st[r]+=1; status[os.path.basename(f)]=r
        if r=='lifestyle': life.append(os.path.basename(f))
    json.dump(status,open(os.path.join(ROOT,'data','photo_status.json'),'w'))
    print('normalize:',dict(st)); print('lifestyle (nebílé pozadí):',life)

