import math

D = "/tmp/claude-0/-home-user-django-shopman/6667231e-7b74-5246-8272-59b33d376d49/scratchpad/ux/mock"
OUT = D + "/src/salao-mesas4.html"


def chair(x, y, extra=False):
    cls = "border-dashed border-muted-foreground/70 bg-card" if extra else "border-foreground/25 bg-secondary"
    return f'<span class="absolute size-[14px] rounded-full border {cls}" style="left:{x - 7:.0f}px;top:{y - 7:.0f}px"></span>'


def table(name, kind, x, y, w, h, seats, extra=False, sel=False):
    out = []
    cx, cy = x + w / 2, y + h / 2
    if kind == "round":
        r = w / 2 + 11
        for i in range(seats):
            a = -math.pi / 2 + 2 * math.pi * i / seats
            out.append(chair(cx + r * math.cos(a), cy + r * math.sin(a), extra))
    else:
        if kind == "square" and seats == 4:
            pts = [(cx, y - 11), (cx, y + h + 11), (x - 11, cy), (x + w + 11, cy)]
        else:
            per = seats // 2
            pts = []
            for i in range(per):
                px = x + w * (i + 0.5) / per
                pts += [(px, y - 11), (px, y + h + 11)]
        for p in pts:
            out.append(chair(*p, extra=extra))
    rad = "rounded-full" if kind == "round" else "rounded-md"
    if extra:
        body = "border-2 border-dashed border-muted-foreground/70 bg-card/80"
    elif sel:
        body = "border-2 border-primary bg-primary/15 shadow-lg"
    else:
        body = "border border-foreground/30 bg-card shadow-sm"
    out.append(
        f'<div class="absolute {rad} {body} grid place-items-center text-center" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px"><div class="leading-none"><p class="op-label font-semibold">{name}</p><p class="op-micro text-muted-foreground tnum mt-0.5">{seats} lug.</p></div></div>'
    )
    if sel:
        for hx, hy in [(x - 5, y - 5), (x + w - 4, y - 5), (x - 5, y + h - 4), (x + w - 4, y + h - 4)]:
            out.append(
                f'<span class="absolute size-2.5 bg-card border-2 border-primary rounded-sm" style="left:{hx}px;top:{hy}px"></span>'
            )
        out.append(
            f'<span class="absolute h-3 w-px bg-primary" style="left:{cx:.0f}px;top:{y - 31}px"></span><span class="absolute size-6 rounded-full bg-card border-2 border-primary grid place-items-center text-primary" style="left:{cx - 12:.0f}px;top:{y - 55}px"><i data-i="rotate-cw" class="size-3.5"></i></span>'
        )
    return "\n".join(out)


T = []
T.append(table("M1", "round", 56, 74, 56, 56, 2))
T.append(table("M2", "round", 56, 196, 56, 56, 2))
T.append(table("M3", "round", 56, 318, 56, 56, 2))
T.append(table("M4", "square", 190, 74, 70, 70, 4))
T.append(table("M5", "square", 190, 250, 70, 70, 4))
T.append(table("M6", "long", 300, 372, 176, 60, 6))
T.append(table("M7", "square", 360, 172, 70, 70, 4, sel=True))
# ghost of M7's old spot (being dragged)
T.append(
    '<div class="absolute rounded-md border-2 border-dashed border-primary/40" style="left:458px;top:262px;width:70px;height:70px"></div><i data-i="move" class="size-5 text-primary absolute" style="left:432px;top:246px"></i>'
)
for i in range(6):
    sy = 72 + i * 60
    T.append(
        f'<div class="absolute size-10 rounded-full border border-foreground/30 bg-card grid place-items-center op-micro font-semibold" style="left:606px;top:{sy}px">B{i + 1}</div>'
    )
T.append(table("C1", "square", 70, 566, 70, 70, 4))
T.append(table("C2", "round", 250, 573, 56, 56, 2, extra=True))
T.append(table("C3", "square", 400, 566, 70, 70, 4, extra=True))
canvas = "\n".join(T)
html = open(D + "/gen4/salao-tpl.html").read().replace("%%CANVAS%%", canvas)
open(OUT, "w").write(html)
print("ok")
