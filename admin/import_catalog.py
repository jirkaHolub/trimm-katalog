"""Jednorázový import dnešního katalogu (ss27/data/catalog.json + fotky) do databáze administrace."""
import json, os, shutil, sys
import db
from schemas import SECTIONS, BADGE_LABELS

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, '..')); SS = os.path.join(REPO, 'ss27')
UP = os.path.join(HERE, 'uploads')
SEASON = 'SS27'
WIDE = {'BALANCE WIDE'}
SUB = {'foto': 'foto', 'foto_pdf': 'foto', 'foto_web': 'foto', 'rozkresy': 'rozkresy', 'ikony': 'ikony', 'data/pdf_icons': 'ikony_produkt', 'data/pdf_pages': 'pages'}

def copy_in(path):
    """zkopíruje soubor z ss27/<path> do admin/uploads/<sub>/<basename> a vrátí relativní cestu (vůči admin/)"""
    if not path: return None
    src = os.path.join(SS, path)
    if not os.path.exists(src): return None
    sub = next((v for k, v in SUB.items() if path.startswith(k + '/')), 'ostatni')
    dst_dir = os.path.join(UP, sub); os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(path))
    if not os.path.exists(dst): shutil.copy(src, dst)
    return f'uploads/{sub}/{os.path.basename(path)}'

def main():
    cat = json.load(open(os.path.join(SS, 'data', 'catalog.json'), encoding='utf-8'))
    n = 0; order = {s: 0 for s in SECTIONS}
    for r in cat:
        p = dict(id=r['id'], season=SEASON, section=r['section'], serie=r.get('serie') or '', name=r['name'], typ=r.get('typ') or '', gender=r.get('gender'),
                 sizes=r.get('sizes') or [], price_min=r.get('price_min'), price_max=r.get('price_max'), desc=r.get('desc') or '',
                 fields=r.get('fields') or {}, features=r.get('features') or [], activities=r.get('activities') or [], specs=r.get('specs') or {},
                 new=bool(r.get('new')), web_url=r.get('web_url'), sk=r.get('sk'), wide=r['name'] in WIDE,
                 hero=copy_in(r.get('hero')), hero_inner=copy_in(r.get('hero_inner')), draw=copy_in(r.get('draw')), colors=[], badges=[])
        for b in r.get('badges') or []:
            f = copy_in(b.get('file'))
            if f: p['badges'].append(dict(name=b.get('name') or os.path.splitext(os.path.basename(f))[0], file=f, label=b.get('label') or BADGE_LABELS.get(b.get('name') or '', '')))
        for c in r.get('colors') or []:
            p['colors'].append(dict(name=c['name'], codes=c.get('codes') or [], front=copy_in(c.get('front')), back=copy_in(c.get('back')), art=copy_in(c.get('art')),
                                    generic=bool(c.get('generic'))))
        order[r['section']] += 1; p['sort'] = order[r['section']]
        db.save_product(p); n += 1
    # sekce + technické strany
    PAGES = {'tents': [10, 12], 'sleeping': [44, 45, 46], 'mattress': [60, 61], 'backpacks': [71], 'sportswear': [88, 89, 90, 91, 92, 93]}
    for i, (k, s) in enumerate(SECTIONS.items()):
        pages = [copy_in(f'data/pdf_pages/p{pg:03d}.jpg') for pg in PAGES[k]]
        db.save_section(SEASON, dict(key=k, title=s['title'], cz=s['cz'], color=s['color'], pages=[x for x in pages if x], sort=i))
    # sada ikon (badge) pro výběr v administraci
    for f in sorted(os.listdir(os.path.join(SS, 'ikony'))):
        if f.lower().endswith('.png'): copy_in('ikony/' + f)
    # úvodní foto
    if os.path.exists(os.path.join(SS, 'hero-ss27.jpg')): shutil.copy(os.path.join(SS, 'hero-ss27.jpg'), os.path.join(UP, 'hero-ss27.jpg'))
    db.set_setting('seasons', ['SS27'])
    print('importováno', n, 'produktů; soubory v', os.path.relpath(UP, REPO))

if __name__ == '__main__':
    if os.path.exists(db.DB_PATH) and '--force' not in sys.argv:
        print('Databáze už existuje. Pro přepsání spusť s --force.'); sys.exit(1)
    if os.path.exists(db.DB_PATH): os.remove(db.DB_PATH)
    main()
