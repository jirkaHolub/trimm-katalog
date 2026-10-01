"""Definice kategorií: která pole, specifikace a fotky se u produktu vyplňují."""
import collections

SECTIONS = collections.OrderedDict([
    ('tents',      dict(title='TENTS COLLECTION',                 cz='Stany',                                color='#f39200')),
    ('sleeping',   dict(title='SLEEPING BAGS COLLECTION',         cz='Spací pytle',                          color='#1e73be')),
    ('mattress',   dict(title='MATTRESS COLLECTION',              cz='Karimatky a matrace',                  color='#3aa55d')),
    ('backpacks',  dict(title='BACKPACKS & WATERPROOF COLLECTION', cz='Batohy, vodotěsné vaky a rezervoáry', color='#8e44ad')),
    ('sportswear', dict(title='SPORTSWEAR COLLECTION',            cz='Oblečení',                             color='#b5c400')),
])

SERIE_COLORS = {'EXTREME': '#e2001a', 'EXTREME DOWN': '#e2001a', 'ADVENTURE': '#f39200', 'TREKKING': '#009fe3', 'OUTDOOR': '#7ab929',
                'FAMILY': '#9b2fae', 'SHELTERS': '#1d5fb0', 'LITE': '#00a99d', 'COMFORT': '#8a6a3a', 'ACTIVE': '#8c8c8c', 'THERMOLAYER': '#c8a24a',
                'SKI': '#e22d2d', 'SNOW & CITY': '#2a8fc8', 'BACKPACKS': '#9a3aa8', 'SPORTSWEAR ACCESSORIES': '#e0a82e',
                'DAYPACK': '#2a8fc8', 'CYKLO': '#e0a82e', 'TRAVEL LITE / TRAVEL': '#5c7c9a', 'WATERPROOF': '#0072bc', 'WATERBLADDER': '#00b3e6'}

# specifikace = ikonové "čipy" pod fotkou
SPEC_LABELS = collections.OrderedDict([
    ('persons', 'Počet osob'), ('weight', 'Hmotnost'), ('volume', 'Objem'), ('length', 'Délka'), ('width', 'Šířka'),
    ('thickness', 'Tloušťka'), ('rvalue', 'R-value'), ('dims', 'Rozměr'), ('pack', 'Sbalený rozměr'), ('pcs', 'Počet kusů v balení'), ('size', 'Velikosti'),
])

SCHEMAS = {
    'tents': dict(
        fields=['VNĚJŠÍ STAN', 'VNITŘNÍ STAN', 'PODLAHA', 'KONSTRUKCE', 'KOLÍKY', 'ROZMĚR', 'MATERIÁL'],
        specs=['persons', 'weight', 'pack', 'dims', 'pcs'],
        photos=[('hero', 'Hlavní fotka'), ('hero_inner', 'Vnitřní stan'), ('draw', 'Rozkres rozměrů')],
        color_photos=['front', 'art'], temps=False, gender=False,
        typ=['stan', 'zástěna', 'ložnice', 'moskytiéra', 'podlážka', 'konektor', 'kolík', 'tyčky', 'náhradní'],
    ),
    'sleeping': dict(
        fields=['VNITŘNÍ MATERIÁL', 'VNĚJŠÍ MATERIÁL', 'IZOLAČNÍ VRSTVA', 'MATERIÁL', 'ŠÍŘKA', 'ROZMĚR'],
        specs=['weight', 'pack', 'length', 'width', 'dims'],
        photos=[('hero', 'Hlavní fotka'), ('draw', 'Rozkres rozměrů')],
        color_photos=['front', 'art'], temps=True, gender=False,
        typ=['s.p.', 'vložka', 'kompresní', 'bivakovací'],
    ),
    'mattress': dict(
        fields=['MATERIÁL', 'VÝPLŇ', 'VENTIL', 'ROZMĚR'],
        specs=['dims', 'thickness', 'rvalue', 'weight', 'pack'],
        photos=[('hero', 'Hlavní fotka'), ('draw', 'Rozkres rozměrů')],
        color_photos=['front', 'art'], temps=False, gender=False,
        typ=['karimatka', 'polštář', 'sedák'],
    ),
    'backpacks': dict(
        fields=['MATERIÁL', 'ROZMĚR'],
        specs=['volume', 'weight', 'dims', 'pack'],
        photos=[('hero', 'Přední pohled'), ('hero_back', 'Zadní pohled'), ('draw', 'Rozkres')],
        color_photos=['front', 'back', 'art'], temps=False, gender=False,
        typ=['batoh', 'lodní', 'vodní', 'taška', 'láhev', 'pláštěnka', 'ledvinka', 'peněženka'],
    ),
    'sportswear': dict(
        fields=['VNĚJŠÍ MATERIÁL', 'VNITŘNÍ MATERIÁL', 'MATERIÁL VÝPLNĚ', 'MATERIÁL'],
        specs=['size'],
        photos=[],
        color_photos=['front', 'back', 'art'], temps=False, gender=True,
        typ=['bunda', 'kalhoty', 'mikina', 'tričko', 'vesta', 'kšiltovka', 'pláštěnka', 'šortky', 'nákrčník', 'návleky', 'pásek', 'sukně', 'čepice'],
    ),
}

GENDERS = collections.OrderedDict([('', '—'), ('men', 'Pánské'), ('women', 'Dámské'), ('kids', 'Dětské'), ('uni', 'Unisex')])

BADGE_LABELS = {
    'taped_seams': 'Lepené švy', 'ykk': 'Zipy YKK', 'raincover_inside': 'Integrovaná pláštěnka', 'camel_bag_ready': 'Příprava pro vodní rezervoár',
    'siliconized': 'Silikonizovaný materiál', 'utx_duraflex': 'Přezky UTX Duraflex', 'teflon': 'Teflon', 'primaloft': 'Primaloft', 'cobrax': 'Cobrax',
    'dupont_sorona': 'DuPont Sorona', 'triguard_softshell': 'Triguard Softshell', 'triguard_softshell_lite': 'Triguard Softshell Lite',
    'triguard_bi_stretch': 'Triguard Bi-Stretch', 'triguard_3l_membrane_extreme': 'Triguard 3L Membrane Extreme', 'triguard_25l_membrane': 'Triguard 2.5L Membrane',
    'triguard_stretch_2l': 'Triguard Stretch 2L Membrane', 'triguard_membrane': 'Triguard Membrane', 'triguard_windshield': 'Triguard Windshield',
    'triguard_coating': 'Triguard Coating', 'triguard_stretch_logo': 'Triguard Stretch', 'peg_shape': 'Tvar kolíku', 'mummy_shape': 'Tvar mumie', 'dac': 'Tyče DAC',
    'female_symbol': 'Dámské', 'male_symbol': 'Pánské', 'shirt_size': 'Velikosti',
}

def empty_product(section):
    return dict(id='', name='', section=section, serie='', typ='', gender=None, sizes=[], price_min=None, price_max=None, desc='',
                fields={}, features=[], activities=[], specs={}, colors=[], badges=[], new=False, hero=None, hero_inner=None, draw=None)
