# Compara as capturas antes/depois do capture-before-after.mjs: fração de pixels que
# mudaram (limiar 24/255), do maior para o menor. Requer Pillow.
import glob
import os
import sys

from PIL import Image, ImageChops

THRESHOLD = 24
SUFFIX_BEFORE = "__antes.png"
SUFFIX_AFTER = "__depois.png"


def compare(directory: str) -> list[tuple[float, str, str]]:
    rows = []
    for before in sorted(glob.glob(f"{directory}/*{SUFFIX_BEFORE}")):
        after = before.replace(SUFFIX_BEFORE, SUFFIX_AFTER)
        if not os.path.exists(after):
            continue
        name = os.path.basename(before)[: -len(SUFFIX_BEFORE)]
        image_before = Image.open(before).convert("RGB")
        image_after = Image.open(after).convert("RGB")
        if image_before.size != image_after.size:
            rows.append((1.0, name, f"tamanho {image_before.size}->{image_after.size}"))
            continue
        diff = ImageChops.difference(image_before, image_after).convert("L")
        diff = diff.point(lambda p: 255 if p > THRESHOLD else 0)
        width, height = image_before.size
        rows.append((sum(diff.histogram()[255:]) / (width * height), name, ""))
    return sorted(rows, reverse=True)


def main() -> int:
    for fraction, name, note in compare(sys.argv[1]):
        print(f"{fraction:7.4f} {name} {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
