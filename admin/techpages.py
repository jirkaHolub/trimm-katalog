"""Technické strany v dalších jazycích: z textové vrstvy zdrojového PDF (SS26) se odstraní české texty, vysází se překlad
z i18n/pages.py a strana se vyrenderuje jako uploads/pages/<lang>/pNNN.jpg (stejný rozměr jako české pNNN.jpg).
CLI: python3 admin/techpages.py es [10 12 ...]   (bez čísel = všechny strany jazyka)"""
import os, re, sys, html
import fitz

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
SRC = os.path.join(REPO, 'podklady', 'katalogy', 'trimm_katalog_SS26_CZ.pdf')
sys.path.insert(0, os.path.join(HERE, 'i18n'))
from pages import PAGES, SERIES

WIDTH = 3000   # šířka výsledného obrázku (jako české strany)
REDACT = dict(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE, text=fitz.PDF_REDACT_TEXT_REMOVE)

def _hex(c): return f'#{c:06x}'
def _weight(font): return 'bold' if re.search(r'Bold|Black|Heavy|Medium', font) else 'normal'
def _rect(objs):
    r = fitz.Rect(objs[0]['bbox'])
    for o in objs[1:]: r |= fitz.Rect(o['bbox'])
    return r
def _shrink(r, k=.28):   # redakce jen „jádra“ řádku, ať nesáhne na sousední řádky
    h = r.height * k; return fitz.Rect(r.x0, r.y0 + h, r.x1, r.y1 - h)

def _series(txt):
    """názvy sérií v řádcích „* Extreme series…“ obarvit a ztučnit jako v originále"""
    def rep(m):
        return f'<span style="color:{SERIES[m.group(1)]};font-weight:bold">{m.group(0)}</span>'
    return re.sub(r'\b(Extreme|Adventure|Trekking|Outdoor|Family|Shelters)( series| serie)?\b', rep, txt)

def _css(span, align='left', extra=''):
    return (f'font-family:sans-serif;font-size:{span["size"]:.2f}pt;line-height:1.22;color:{_hex(span["color"])};'
            f'font-weight:{_weight(span["font"])};text-align:{align};{extra}')

def translate_page(page, entries, lang):
    blocks = {i: b for i, b in enumerate(page.get_text('dict')['blocks']) if b.get('lines')}
    jobs = []; missing = []
    items = entries.items() if isinstance(entries, dict) else enumerate(entries)
    for key, val in items:
        if isinstance(val, tuple) and val[0] == 'span':
            _, cz, new = val; hit = False
            for b in blocks.values():
                for l in b['lines']:
                    for s in l['spans']:
                        if cz in s['text']:
                            hit = True; r = fitz.Rect(s['bbox']); txt = s['text'].replace(cz, new).strip()
                            jobs.append((_shrink(r), fitz.Rect(r.x0, r.y0, r.x1 + 40, r.y1 + 1), html.escape(txt), _css(s)))
            if not hit: missing.append(cz)
            continue
        b = blocks.get(key)
        if not b: missing.append(key); continue
        lines = b['lines']
        if isinstance(val, dict) and 'lines' in val:
            ls = lines[:val['lines']]; r = _rect(ls); align = val.get('align', 'left'); grow = r.width * val.get('grow', .15 if align == 'center' else .6)
            box = fitz.Rect(r.x0 - (grow / 2 if align == 'center' else grow if align == 'right' else 0), r.y0 - 1,
                            r.x1 + (grow / 2 if align == 'center' else 0 if align == 'right' else grow), r.y1 + 1)
            for l in ls: jobs.append((_shrink(fitz.Rect(l['bbox'])), None, None, None))
            jobs.append((None, box, val['text'], _css(ls[0]['spans'][0], align)))
            continue
        # odstavec (případně s popiskem CZ nahoře nebo s nadpisem)
        first = lines[0]['spans'][0]; label = ''.join(s['text'] for s in lines[0]['spans']).strip() in ('CZ', 'CZ:', 'CZ -')
        opt = val if isinstance(val, dict) else {}
        if isinstance(val, dict) and 'text' in val: val = val['text']
        body_lines = lines[1:] if (label or isinstance(val, dict)) else lines
        body_span = body_lines[0]['spans'][0] if body_lines else first
        for l in lines: jobs.append((_shrink(fitz.Rect(l['bbox'])), None, None, None))
        r = _rect(lines); box = fitz.Rect(r.x0, r.y0 - .5, r.x1 + 2 + opt.get('grow', 0), r.y1 + 4 + opt.get('down', 0))
        if label:
            jobs.append((None, fitz.Rect(first['bbox']) + (0, -1, 30, 1), lang.upper(), _css(first)))
            box = fitz.Rect(r.x0, _rect(body_lines).y0 - .5, box.x1, box.y1)
        if isinstance(val, dict) and 'head' in val:   # nadpis + text
            head = f'<div style="{_css(first)}">{html.escape(val["head"])}</div>'
            body = re.sub(r'<i>(.*?)</i>', lambda m: '<span style="font-style:italic">' + _series(m.group(1)) + '</span>', val['body'], flags=re.S)
            jobs.append((None, box, head + f'<div style="{_css(body_span)}">{body}</div>', ''))
        else:
            jobs.append((None, box, f'<div style="{_css(body_span)}">{val}</div>', ''))
    for red, *_ in jobs:
        if red is not None: page.add_redact_annot(red)
    page.apply_redactions(**REDACT)
    for _, box, content, css in jobs:
        if box is None: continue
        htm = content if css == '' else f'<div style="{css}">{content}</div>'
        page.insert_htmlbox(box, htm, scale_low=0.5)
    return missing

def build(lang, numbers=None):
    out_dir = os.path.join(HERE, 'uploads', 'pages', lang); os.makedirs(out_dir, exist_ok=True); done = []
    for n, entries in sorted(PAGES[lang].items()):
        if numbers and n not in numbers: continue
        d = fitz.open(SRC); page = d[n - 1]
        miss = translate_page(page, entries, lang)
        z = WIDTH / page.rect.width; pix = page.get_pixmap(matrix=fitz.Matrix(z, z))
        fp = os.path.join(out_dir, f'p{n:03d}.jpg'); pix.save(fp, jpg_quality=90)
        done.append(fp); print(f'{lang} p{n:03d} -> {os.path.relpath(fp, REPO)}' + (f'  NENALEZENO: {miss}' if miss else ''))
    return done

if __name__ == '__main__':
    lang = sys.argv[1] if len(sys.argv) > 1 else 'es'
    build(lang, [int(x) for x in sys.argv[2:]] or None)
