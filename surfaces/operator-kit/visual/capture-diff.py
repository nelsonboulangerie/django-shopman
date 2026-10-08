# Compara as capturas antes/depois do capture-before-after.mjs: fração de pixels que
# mudaram (limiar 24/255), do maior para o menor. Requer Pillow.
import sys, glob, os
from PIL import Image, ImageChops
d = sys.argv[1]
rows = []
for a in sorted(glob.glob(f"{d}/*__antes.png")):
    b = a.replace("__antes.png", "__depois.png")
    if not os.path.exists(b): continue
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if ia.size != ib.size:
        rows.append((1.0, os.path.basename(a)[:-11], f"tamanho {ia.size}->{ib.size}")); continue
    diff = ImageChops.difference(ia, ib).convert("L").point(lambda p: 255 if p > 24 else 0)
    n = sum(diff.histogram()[255:]) / (ia.size[0] * ia.size[1])
    rows.append((n, os.path.basename(a)[:-11], ""))
for n, name, note in sorted(rows, reverse=True):
    print(f"{n:7.4f} {name} {note}")
