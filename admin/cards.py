"""Společné karty produktů: jedna karta pro všechny katalogy. Rozpracovaný katalog karty jen skládá (sekce, série, pořadí, novinka),
uzavřením si udělá vlastní kopie, aby se už neměnil. Převod starší databáze: python3 admin/cards.py"""
import db, versions

def _core(p): return {k: v for k, v in db.card_data(p).items() if k not in ('section', 'serie')}, p['name']

def freeze(code):
    """uzavření katalogu: zařazené karty se zkopírují do katalogu"""
    if db.is_linked(code): db.set_products(code, db.list_products(code), linked=False)

def link(code):
    """napojí katalog s vlastními kopiemi na společné karty; chybějící karty založí z jeho kopií, existující platí"""
    if not db.is_linked(code): db.set_products(code, db.list_products(code), linked=True)

def matches(code):
    """vlastní kopie katalogu jsou shodné se společnými kartami (od uzavření se nic nezměnilo)"""
    cards = {c['id']: c for c in db.list_cards()}
    return all(p['id'] in cards and _core(p) == _core(cards[p['id']]) for p in db.list_products(code))

def differing(code):
    cards = {c['id']: c for c in db.list_cards()}
    return [p['name'] for p in db.list_products(code) if p['id'] in cards and _core(p) != _core(cards[p['id']])]

def take(code, q):
    """Produkt z jiného katalogu připravený k vložení do katalogu code. Společná karta se stejným id se připojí (platí její současný obsah), jinak vznikne kopie."""
    if db.is_linked(code) and q.get('id') and not db.get_product(code, q['id']):
        c = db.get_card(q['id'])
        if c: return dict(c, season=code)
    p = dict(q, season=code); p['id'] = db.free_id(code, q.get('id') or 'produkt'); return p

def add(code, ids):
    """zařadí existující karty do katalogu"""
    secs = {s['key'] for s in db.list_sections(code)}; out = dict(added=0, skipped=[])
    for cid in ids:
        c = db.get_card(cid)
        if not c or db.get_product(code, cid): continue
        if c.get('section') not in secs: out['skipped'].append(c['name']); continue
        db.save_product(dict(c, season=code, new=False, sort=db.next_sort(code, c['section']))); out['added'] += 1
    return out

def listing():
    cats = {c['code']: c for c in db.list_catalogs()}; use = db.card_usage(); out = []
    for c in db.list_cards():
        colors = c.get('colors') or []
        out.append(dict(id=c['id'], name=c['name'], section=c.get('section'), serie=c.get('serie') or '', typ=c.get('typ'), n_colors=len(colors), price_min=c.get('price_min'),
                        thumb=c.get('hero') or next((x.get('front') for x in colors if x.get('front')), None),
                        catalogs=[dict(code=k, linked=bool(cats[k].get('linked'))) for k in sorted(use.get(c['id'], [])) if k in cats]))
    return out

def remove(cid):
    cats = {c['code']: c for c in db.list_catalogs()}
    used = [k for k in db.card_usage().get(cid, []) if cats.get(k, {}).get('linked')]
    if used: raise ValueError('Karta je zařazená v katalogu ' + ', '.join(used) + '. Nejdřív ji z něj odeber.')
    db.delete_card(cid)

def migrate(log=print):
    """Převod na společné karty. Rozpracované katalogy (od nejnovějšího) určí obsah karet a napojí se na ně; uzavřené si nechají
    vlastní kopie a doplní jen karty, které jinde nejsou. Dá se pustit opakovaně."""
    cats = sorted((c for c in db.list_catalogs() if c.get('source') == 'db'), key=lambda c: (c.get('status') == 'done', -(c.get('year_num') or 0)))
    for c in cats:
        code = c['code']; n0 = len(db.list_cards())
        if c.get('linked'): log(f'{code}: už používá společné karty'); continue
        versions.create(code, 'Před převodem na společné karty', auto=False)
        if c.get('status') == 'done': db.add_cards(db.list_products(code)); what = 'uzavřený, nechává si vlastní kopie'
        else: link(code); what = 'napojen na společné karty'
        log(f'{code}: {what}, nových karet {len(db.list_cards()) - n0}')
    db.set_setting('cards_migrated', True)
    return dict(cards=len(db.list_cards()))

if __name__ == '__main__':
    print(migrate())
