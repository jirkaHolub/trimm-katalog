"""Při sestavení obrazu aplikace připraví zmenšeniny všech souborů ze základu, aby se online jen posílaly z disku.
Šířky odpovídají tomu, co si bere katalog (generate.Renderer.src) a přehledy v aplikaci."""
import os, sys
from concurrent.futures import ProcessPoolExecutor
from PIL import Image

BASE = sys.argv[1] if len(sys.argv) > 1 else '/app/base'; OUT = BASE + '-thumbs'
WIDTHS = {'foto': (120, 200, 240, 700), 'rozkresy': (200, 240, 700), 'ikony': (240,), 'ikony_produkt': (240,), 'pages': (240, 1600), 'hero': (700, 800, 1600), 'ostatni': (200, 240, 700), 'prev': (240,)}

def one(job):
    key, width = job
    try:
        im = Image.open(os.path.join(BASE, key)); im.load(); alpha = im.mode in ('RGBA', 'LA', 'P')
        im = im.convert('RGBA' if alpha else 'RGB'); im.thumbnail((width, width))
        out = os.path.join(OUT, str(width), key + ('.png' if alpha else '.jpg')); os.makedirs(os.path.dirname(out), exist_ok=True)
        im.save(out) if alpha else im.save(out, quality=84 if width >= 600 else 80)
    except Exception as e: print('přeskočeno', key, e)

if __name__ == '__main__':
    jobs = []
    for root, _, files in os.walk(os.path.join(BASE, 'uploads')):
        for f in files:
            if not f.lower().endswith(('.jpg', '.jpeg', '.png')): continue
            key = os.path.relpath(os.path.join(root, f), BASE).replace(os.sep, '/'); parts = key.split('/')
            for w in WIDTHS.get(parts[1] if len(parts) > 2 else 'hero', (240, 700)): jobs.append((key, w))
    with ProcessPoolExecutor() as ex: list(ex.map(one, jobs, chunksize=32))
    print('zmenšenin', len(jobs))
