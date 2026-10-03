D='/tmp/claude-0/-home-user-django-shopman/6667231e-7b74-5246-8272-59b33d376d49/scratchpad/ux/mock'
SCALE=70  # unidades -> largura total da barra (px por un.)
BW=200
def bar(made,sold,lost=0,typ=None):
    px=lambda u: round(u/SCALE*BW)
    h=f'<div class="relative h-3.5" style="width:{BW}px">'
    h+=f'<div class="absolute inset-y-0 left-0 rounded-sm bg-muted border border-border" style="width:{px(made)}px"></div>'
    h+=f'<div class="absolute inset-y-0 left-0 rounded-sm bg-primary" style="width:{px(sold)}px"></div>'
    if lost:
        h+=f'<div class="absolute inset-y-0 rounded-r-sm border border-dashed border-destructive/70 bg-destructive/10" style="left:{px(sold)}px;width:{px(lost)}px"></div>'
    if typ is not None:
        h+=f'<div class="absolute -top-1 -bottom-1 w-0.5 bg-foreground" style="left:{px(typ)}px" title="vendeu num sábado típico"></div>'
    h+='</div>'
    return h
V={'f':('Faltou','destructive'),'s':('Sobrou','warning'),'m':('Na medida','success')}
def pill(k,extra=''):
    t,c=V[k]
    return f'<span class="h-6 px-2 rounded-full bg-{c}/12 text-{c} op-micro font-semibold inline-flex items-center gap-1.5"><span class="size-1.5 rounded-full bg-{c}"></span>{t}{extra}</span>'
rows=[
 # name sku k made sold lost typ acabou parecidos vs open
 ('Croissant Manteiga','CRO','f',44,44,14,50,'<b class="text-destructive">10:40</b>','faltou 3 de 4','típico vende ~50; fez 44',True),
 ('Ciabatta','CI','f',26,26,4,24,'13:20','faltou 1 de 4','típico ~24; fez 26',False),
 ('Bichon au Citron','BICH','f',24,24,6,22,'15:10','faltou 1 de 4','típico ~22; fez 24',False),
 ('Baguette de Tradition','BGT','s',60,48,0,50,'não acabou','sobrou 3 de 4','típico ~50; R$ 61 de custo',False),
 ('Pain de Campagne','CPBG','s',40,33,0,34,'não acabou','sobrou 2 de 4','típico ~34; R$ 38 de custo',False),
 ('Brioche Nanterre','BRNT','s',20,15,0,16,'não acabou','sobrou 2 de 4','típico ~16; R$ 33 de custo',False),
 ('Pain au Chocolat','PCHOC','m',36,35,0,34,'17:30','na medida 3 de 4','típico ~34',False),
 ('Shokupan','FORMA','m',18,18,0,17,'17:50','na medida 4 de 4','acabou perto de fechar',False),
]
out=[]
for (n,sku,k,made,sold,lost,typ,ac,par,vs,op) in rows:
    diff = f'<span class="text-destructive font-semibold">~{lost} perdidas</span>' if k=='f' else (f'<span class="text-warning font-semibold">sobrou {made-sold}</span>' if k=='s' else f'<span class="text-success font-semibold">{"sobrou "+str(made-sold) if made>sold else "zerou"}</span>')
    cls='bg-primary/5' if op else ''
    out.append(f'''<div class="grid grid-cols-[minmax(0,1.3fr)_110px_250px_100px_130px_minmax(0,1.2fr)_150px] items-center h-[50px] border-b border-border px-4 gap-3 {cls}">
  <div class="min-w-0"><p class="op-body font-medium truncate">{n} <span class="op-micro font-mono text-muted-foreground">{sku}</span></p></div>
  <div>{pill(k)}</div>
  <div class="flex flex-col gap-1">{bar(made,sold,lost,typ)}<p class="op-micro tnum text-muted-foreground">fez <b class="text-foreground">{made}</b> · vendeu <b class="text-foreground">{sold}</b> · {diff}</p></div>
  <div class="op-label tnum">{ac}</div>
  <div class="op-label tnum text-muted-foreground">{par.split(" ",1)[0] if False else ""}{par}</div>
  <div class="op-micro text-muted-foreground truncate">{vs}</div>
  <div class="flex justify-end"><button class="h-9 px-2.5 rounded-md {'bg-secondary font-semibold' if op else ''} op-label inline-flex items-center gap-1.5">Ver lotes e vendas<i data-i="{'chevron-up' if op else 'chevron-down'}" class="size-4"></i></button></div>
</div>''')
    if op:
        hours=[('07',8),('08',12),('09',14),('10',10),('11',0),('12',0)]
        hb=''.join(f'<div class="flex flex-col items-center gap-1"><div class="w-7 rounded-t-sm {"bg-primary" if v else "border border-dashed border-destructive/60 bg-destructive/8"}" style="height:{(v or 9)*4}px"></div><span class="op-micro tnum text-muted-foreground">{h}h</span></div>' for h,v in hours)
        out.append(f'''<div class="px-4 py-3 border-b border-border bg-primary/5 grid grid-cols-[1.1fr_1fr_1.25fr] gap-5">
  <div><p class="op-eyebrow text-muted-foreground mb-1.5">Lotes de sábado</p>
    <a class="flex items-center gap-2 h-8 op-label"><span class="font-mono text-primary underline underline-offset-2">WO-0412</span><span class="tnum text-muted-foreground">saiu 06:30</span><span class="ml-auto tnum font-semibold">24 un.</span><i data-i="arrow-up-right" class="size-3.5 text-muted-foreground"></i></a>
    <a class="flex items-center gap-2 h-8 op-label border-t border-border"><span class="font-mono text-primary underline underline-offset-2">WO-0418</span><span class="tnum text-muted-foreground">saiu 08:20</span><span class="ml-auto tnum font-semibold">20 un.</span><i data-i="arrow-up-right" class="size-3.5 text-muted-foreground"></i></a>
    <p class="op-micro text-muted-foreground mt-1">Sem 3º lote: o plano dizia 44.</p></div>
  <div><p class="op-eyebrow text-muted-foreground mb-1.5">Vendas por hora</p>
    <div class="flex items-end gap-2 h-[78px]">{hb}</div>
    <p class="op-micro text-destructive mt-0.5">acabou 10:40 · tracejado = estimativa</p></div>
  <div><p class="op-eyebrow text-muted-foreground mb-1.5">Depois que acabou</p>
    <p class="op-label leading-6">iFood, Meta e Google indisponíveis às 10:40 <span class="op-micro text-muted-foreground">(automático)</span></p>
    <p class="op-label leading-6">"Me avise" do site: <b>5 clientes</b></p>
    <div class="flex items-center gap-3 mt-1.5">
      <a class="op-label font-semibold text-primary underline underline-offset-2">Abrir os 44 pedidos</a>
      <a class="op-label font-semibold text-primary underline underline-offset-2">Os 4 sábados</a>
    </div></div>
</div>''')
html=open(D+'/gen4/bi-sobra-tpl.html').read().replace('%%ROWS%%','\n'.join(out))
open(D+'/src/bi-sobra4.html','w').write(html)
print('ok')
