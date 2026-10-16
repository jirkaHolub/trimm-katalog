"""Doplnění jazykové vrstvy karet z připraveného souboru i18n/<lang>.json (texty překládané mimo aplikaci).
Soubor má: features {cz: en}, values {cz hodnota pole: en}, desc {id produktu: en}. Stejný český popis u jiného produktu se doplní
automaticky. Doplňuje se jen to, co v kartě chybí (--force přepíše i vyplněné). Mění se jen klíč i18n – nic jiného v kartě.
CLI: python3 admin/translate.py en [--force]"""
import json, os, sys, re
import db, lang as LANG

HERE = os.path.dirname(os.path.abspath(__file__))

def load(lng):
    fp = os.path.join(HERE, 'i18n', f'{lng}.json')
    if not os.path.exists(fp): return None
    return json.load(open(fp, encoding='utf-8'))

def _norm(s): return re.sub(r'\s+', ' ', s or '').strip()

def proposal(p, lng, T, by_desc):
    """navržená vrstva i18n[lng] pro kartu (jen z připraveného souboru, bez strojového překladu)"""
    L = {}
    if p.get('desc'):
        d = T['desc'].get(p['id']) or by_desc.get(_norm(p['desc']))
        if d: L['desc'] = d
    if p.get('features'):
        tf = [T['features'].get(_norm(f)) or '' for f in p['features']]
        if any(tf): L['features'] = tf
    F = p.get('fields') or {}
    tv = {k: T['values'][_norm(v)] for k, v in F.items() if v and _norm(v) in T['values']}
    if tv: L['fields'] = tv
    return L

def fill(lng, force=False, log=print, codes=None):
    T = load(lng)
    if not T: raise ValueError(f'Chybí soubor i18n/{lng}.json')
    by_desc = {}
    cats = [c for c in db.list_catalogs() if c.get('source') == 'db' and (not codes or c['code'] in codes)]
    for c in cats:
        for p in db.list_products(c['code']):
            if p.get('desc') and p['id'] in T['desc']: by_desc.setdefault(_norm(p['desc']), T['desc'][p['id']])
    done = set(); changed = 0; stat = {'full': 0, 'part': 0, 'none': 0}
    for c in cats:
        for p in db.list_products(c['code']):
            key = p['id'] if c.get('linked') else (c['code'], p['id'])
            if key in done: continue
            done.add(key)
            new = proposal(p, lng, T, by_desc); i18n = dict(p.get('i18n') or {}); cur = dict(i18n.get(lng) or {})
            upd = dict(cur)
            for k, v in new.items():
                if k == 'features':
                    old = cur.get('features') or []
                    upd['features'] = [(o if (o and not force) else n) or o for o, n in zip(old + [''] * (len(v) - len(old)), v)]
                elif k == 'fields':
                    old = dict(cur.get('fields') or {})
                    for fk, fv in v.items():
                        if force or not old.get(fk): old[fk] = fv
                    upd['fields'] = old
                elif force or not cur.get(k): upd[k] = v
            if upd != cur:
                i18n[lng] = upd; p['i18n'] = i18n; db.save_product(p); changed += 1
            s = LANG.status(p, lng)
            if s: stat[s] += 1
    log(f'{lng.upper()}: upraveno {changed} karet; přeloženo úplně {stat["full"]}, částečně {stat["part"]}, vůbec {stat["none"]}')
    return dict(changed=changed, **stat)

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    fill(args[0] if args else 'en', force='--force' in sys.argv)
