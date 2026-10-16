"""Jazyky katalogu. Čeština je zdroj (tak jsou karty uložené); ostatní jazyky mají v kartě vrstvu `i18n[lang]`
(desc, features, fields, typ, activities) a pevné texty (názvy polí, popisky, texty generátoru) ve slovníku níže.
Co v jazykové vrstvě chybí, generátor doplní z češtiny a přepočítá, kolik toho bylo."""
import re

LANGS = [('cs', 'Čeština'), ('en', 'English')]
CODES = [c for c, _ in LANGS]

# slovník pevných textů: klíč -> {lang: text}; čeština = klíč sám (u 'ui' klíčů) nebo uvedená hodnota
DICT = {
    'en': {
        # názvy polí v kartě (klíče jsou české názvy polí, jak jsou uložené v kartách)
        'fields': {
            'VNĚJŠÍ STAN': 'OUTER TENT', 'VNITŘNÍ STAN': 'INNER TENT', 'PODLAHA': 'FLOOR', 'KONSTRUKCE': 'POLES', 'KOLÍKY': 'PEGS',
            'ROZMĚR': 'DIMENSIONS', 'ROZMĚRY': 'DIMENSIONS', 'MATERIÁL': 'MATERIAL', 'VNITŘNÍ MATERIÁL': 'INNER MATERIAL',
            'VNĚJŠÍ MATERIÁL': 'OUTER MATERIAL', 'IZOLAČNÍ VRSTVA': 'INSULATION', 'ŠÍŘKA': 'WIDTH', 'VÝPLŇ': 'FILLING',
            'VENTIL': 'VALVE', 'MATERIÁL VÝPLNĚ': 'FILLING',
        },
        # popisky specifikací (ikony pod fotkou)
        'specs': {
            'persons': 'Persons', 'weight': 'Weight', 'volume': 'Volume', 'length': 'Length', 'width': 'Width', 'thickness': 'Thickness',
            'rvalue': 'R-value', 'dims': 'Dimensions', 'pack': 'Packed size', 'pcs': 'Pieces per pack', 'size': 'Sizes',
        },
        'genders': {'men': "Men's", 'women': "Women's", 'kids': "Kids'", 'uni': 'Unisex'},
        # typ produktu (interní klíč zůstává český, tohle je jen zobrazený text)
        'typ': {
            'stan': 'tent', 'zástěna': 'side wall', 'ložnice': 'bedroom', 'moskytiéra': 'mosquito net', 'podlážka': 'footprint',
            'konektor': 'connector', 'kolík': 'peg', 'tyčky': 'poles', 'náhradní': 'spare part', 's.p.': 'sleeping bag',
            'vložka': 'sleeping bag liner', 'kompresní': 'compression bag', 'bivakovací': 'bivy bag', 'karimatka': 'sleeping mat',
            'polštář': 'pillow', 'sedák': 'seat pad', 'batoh': 'backpack', 'lodní': 'dry bag', 'vodní': 'water bladder',
            'taška': 'bag', 'láhev': 'bottle', 'pláštěnka': 'rain cover', 'ledvinka': 'waist bag', 'peněženka': 'wallet',
            'bunda': 'jacket', 'kalhoty': 'pants', 'mikina': 'sweatshirt', 'tričko': 'T-shirt', 'vesta': 'vest', 'kšiltovka': 'cap',
            'šortky': 'shorts', 'nákrčník': 'neck gaiter', 'návleky': 'gaiters', 'pásek': 'belt', 'sukně': 'skirt', 'čepice': 'hat',
        },
        'typ_by_section': {'sportswear': {'pláštěnka': 'rain poncho'}},
        'activities': {
            'Adventure': 'Adventure', 'Běžecké lyžování': 'Cross-country skiing', 'Běžné nošení': 'Everyday wear', 'Cyklistika': 'Cycling',
            'Freeride a Snowboarding': 'Freeride & snowboarding', 'Jogging': 'Jogging', 'Lyžování': 'Skiing', 'Ski Alp': 'Ski touring',
            'Trekking': 'Trekking',
        },
        # podtituly sekcí (anglický název sekce je v s['title'])
        'sections': {'tents': 'Tents', 'sleeping': 'Sleeping bags', 'mattress': 'Mats and mattresses',
                     'backpacks': 'Backpacks, dry bags and bladders', 'sportswear': 'Clothing'},
        # texty generátoru (klíč = český text)
        'ui': {
            'VLASTNOSTI': 'FEATURES', 'AKTIVITY': 'ACTIVITIES', 'Novinka': 'New', 'DMOC': 'RRP', 'od': 'from', 'Kč': 'CZK',
            'Popis doplníme.': 'Description to follow.', 'foto doplníme': 'photo to follow', 'KATALOG · CZ': 'CATALOGUE · EN',
            'MODELŮ': 'MODELS', 'SÉRIÍ': 'SERIES', 'NOVINEK': 'NEW', 'modelů': 'models', 'Vyhledat model, barvu, typ': 'Search model, colour, type',
            'VŠE': 'ALL', 'VŠICHNI': 'ALL', 'PÁNSKÉ': 'MEN', 'DÁMSKÉ': 'WOMEN', 'DĚTSKÉ': 'KIDS',
            'CENY DMOC V KČ VČETNĚ DPH': 'RRP IN CZK INCL. VAT', 'ceny DMOC v Kč včetně DPH': 'RRP in CZK incl. VAT',
            'ZMĚNY VYHRAZENY': 'SUBJECT TO CHANGE', 'OBSAH': 'CONTENTS', 'CONTENT': '', 'Technické informace': 'Technical information',
            'Katalog': 'Catalogue', 'Obsah': 'Contents', 'Rozkres': 'Drawing', 'zadní strana': 'back view', 'vnitřní stan': 'inner tent',
            'rubová strana': 'reverse side', 'detail': 'detail', 'rozměry': 'dimensions', 'vizuál doplníme': 'visual to follow',
            'SERIE': 'SERIES', 'Počet osob': 'Persons', 'Hmotnost': 'Weight', 'Objem': 'Volume', 'Rozměr': 'Dimensions', 'Sbalený rozměr': 'Packed size',
        },
    },
}
TRANSLATED = ('desc', 'features', 'fields', 'typ', 'activities')   # co má jazyková vrstva v kartě

def t(lang, key, group='ui'):
    """pevný text ve zvoleném jazyce; čeština (nebo neznámý klíč) vrací klíč"""
    if lang == 'cs' or lang not in DICT: return key
    return DICT[lang].get(group, {}).get(key, key)

def typ_label(lang, typ, section=None):
    if not typ or lang == 'cs' or lang not in DICT: return typ
    d = DICT[lang]; return d.get('typ_by_section', {}).get(section or '', {}).get(typ) or d['typ'].get(typ, typ)

_PERSONS = re.compile(r'^(\d[\d\s\-–]*)\s*osob[ay]?$')
_DEC = re.compile(r'(?<=\d),(?=\d)')
def number_label(lang, s):
    """desetinná čárka -> tečka mimo češtinu (0,2 kg -> 0.2 kg); jinak beze změny"""
    return _DEC.sub('.', s) if lang != 'cs' and s else s
def size_label(lang, s):
    """velikost: '2-3 osoby' -> '2-3 persons', ostatní beze změny"""
    if lang == 'cs' or not s: return s
    m = _PERSONS.match(s.strip())
    if m: n = m.group(1).strip(); return n + (' person' if n == '1' else ' persons')
    return s

def _clean(s): return re.sub(r'\s+', ' ', (s or '').replace('•', '')).strip()

def localize(p, lang):
    """Kopie karty s texty ve zvoleném jazyce. Co chybí v i18n[lang], zůstane česky; `_missing` říká, co to bylo."""
    if lang == 'cs': return p
    L = (p.get('i18n') or {}).get(lang) or {}; q = dict(p); missing = []
    if p.get('desc'):
        if L.get('desc'): q['desc'] = L['desc']
        else: missing.append('desc')
    feats = p.get('features') or []
    if feats:
        tf = L.get('features') or []
        if len(tf) == len(feats) and all(tf): q['features'] = list(tf)
        else:
            q['features'] = [(tf[i] if i < len(tf) and tf[i] else f) for i, f in enumerate(feats)]; missing.append('features')
    F = p.get('fields') or {}
    if F:
        tv = L.get('fields') or {}; out = {}; miss = False
        for k, v in F.items():
            if not v: continue
            nv = tv.get(k) or ''
            if not nv and _has_cz(v): miss = True
            out[t(lang, k, 'fields')] = nv or v
        q['fields'] = out
        if miss: missing.append('fields')
    if p.get('typ'): q['typ_label'] = L.get('typ') or typ_label(lang, p['typ'], p.get('section'))
    acts = [_clean(a) for a in (p.get('activities') or []) if _clean(a)]
    if acts:
        ta = L.get('activities') or []
        q['activities'] = [(ta[i] if i < len(ta) and ta[i] else t(lang, a, 'activities')) for i, a in enumerate(acts)]
    S = {k: (number_label(lang, v) if isinstance(v, str) and k != 'size' else v) for k, v in (p.get('specs') or {}).items()}
    if S.get('size'): S['size'] = size_label(lang, S['size'])
    if S.get('persons'): S['persons'] = re.sub(r'\bos\.?$', 'pers.', S['persons'].strip())
    q['specs'] = S
    if q.get('fields'): q['fields'] = {k: number_label(lang, v) for k, v in q['fields'].items()}
    q['_missing'] = missing
    return q

_CZ = re.compile(r'[ěščřžýáíéůúňťďó]', re.I)
def _has_cz(s): return bool(_CZ.search(s or ''))

def status(p, lang):
    """stav překladu karty: 'full' | 'part' | 'none' | '' (není co překládat)"""
    if lang == 'cs': return ''
    need = []
    if p.get('desc'): need.append('desc')
    if p.get('features'): need.append('features')
    if any(_has_cz(v) for v in (p.get('fields') or {}).values()): need.append('fields')
    if not need: return ''
    L = (p.get('i18n') or {}).get(lang) or {}
    done = 0
    if 'desc' in need and L.get('desc'): done += 1
    if 'features' in need:
        tf = L.get('features') or []
        if len(tf) == len(p['features']) and all(tf): done += 1
    if 'fields' in need:
        tv = L.get('fields') or {}
        if all(tv.get(k) for k, v in p['fields'].items() if _has_cz(v)): done += 1
    return 'full' if done == len(need) else ('part' if done else 'none')

def catalog_label(cfg, lang):
    """název pro hlavičku/tiráž: SPRING – SUMMER 2027 je už anglicky, jen 'Katalog' v názvu dokumentu se překládá"""
    return cfg['label']

def out_paths(cfg, lang):
    """výstupy pro jazyk: čeština = uložené cesty, jiný jazyk dostane příponu _EN před koncovkou (PDF místo _CZ)"""
    if lang == 'cs': return cfg['out_html'], cfg['out_pdf']
    u = lang.upper()
    html = re.sub(r'\.html?$', f'_{u}.html', cfg['out_html'])
    pdf = re.sub(r'_CZ\.pdf$', f'_{u}.pdf', cfg['out_pdf'])
    if pdf == cfg['out_pdf']: pdf = re.sub(r'\.pdf$', f'_{u}.pdf', pdf)
    return html, pdf
