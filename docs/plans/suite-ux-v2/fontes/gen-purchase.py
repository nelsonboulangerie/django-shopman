import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
rows = [
    (
        "Açúcar",
        "ACUCAR-CRISTAL",
        "Insumo",
        "13 receitas: Cebolas Assadas, Creme de Baunilha, Massa Brioche…",
        ["Comprável", "Usado em receita"],
        "30.000 g",
        ("10.000", True),
        "g",
        True,
    ),
    (
        "Açúcar refinado",
        "ACUCAR-REFINADO",
        "Insumo",
        "2 receitas: Caramelo Salgado, Creme de Limão Siciliano",
        ["Comprável", "Usado em receita"],
        "5.000 g",
        ("", False),
        "g",
        False,
    ),
    (
        "Água filtrada",
        "AGUA-FILTRADA",
        "Insumo",
        "12 receitas: Levain, Massa Campagne, Massa Ciabatta…",
        ["Comprável", "Usado em receita"],
        "205.800 g",
        ("50.000", True),
        "g",
        False,
    ),
    (
        "Água Mineral com Gás Prata 310ml",
        "AGUA-GAS-PRATA-310",
        "Revenda",
        "à venda no PDV",
        ["Comprável", "Vendável"],
        "5 un",
        ("", False),
        "un",
        False,
    ),
    (
        "Água Mineral Prata 310ml",
        "AGUA-MINERAL-PRATA-310",
        "Revenda",
        "à venda no PDV",
        ["Comprável", "Vendável"],
        "53 un",
        ("", False),
        "un",
        False,
    ),
    (
        "Alecrim",
        "ALECRIM-FRESCO",
        "Insumo",
        "3 receitas: Béchamel, Focaccia do dia, Mini Focaccia Alecrim",
        ["Comprável", "Usado em receita"],
        "500 g",
        ("", False),
        "g",
        False,
    ),
    (
        "Alface americana",
        "ALFACE-AMERICANA",
        "Insumo",
        "1 receita: Salada da Casa",
        ["Comprável", "Usado em receita"],
        "2.000 g",
        ("1.000", True),
        "g",
        False,
    ),
    (
        "Alho",
        "ALHO",
        "Insumo",
        "4 receitas: Cebolas Assadas, Recheio de Frango, Pasta Autolizada…",
        ["Comprável", "Usado em receita"],
        "1.200 g",
        ("", False),
        "g",
        False,
    ),
    (
        "Amêndoa laminada",
        "AMENDOA-LAMINADA",
        "Insumo",
        "2 receitas: Croissant aux Amandes, Financier",
        ["Comprável", "Usado em receita"],
        "800 g",
        ("", False),
        "g",
        False,
    ),
]
out = []
for name, sku, kind, rec, roles, stock, (mv, ed), unit, sel in rows:
    tags = "".join(
        f'<span class="h-5 px-1.5 rounded border border-border op-micro text-muted-foreground inline-flex items-center whitespace-nowrap">{r}</span>'
        for r in roles
    )
    rowcls = "bg-primary/8 shadow-[inset_3px_0_0_var(--primary)]" if sel else ""
    if ed:
        inp = f'<label class="h-10 w-32 px-2.5 rounded-md border-2 border-primary bg-card inline-flex items-center gap-1.5"><span class="flex-1 tnum font-semibold text-right">{mv}</span><span class="op-micro text-muted-foreground">{unit}</span></label><span class="size-1.5 rounded-full bg-primary" title="Alterado"></span>'
    else:
        inp = f'<label class="h-10 w-32 px-2.5 rounded-md border border-input bg-card inline-flex items-center gap-1.5"><span class="flex-1 text-right op-micro text-muted-foreground">sem mínimo</span><span class="op-micro text-muted-foreground">{unit}</span></label><span class="size-1.5"></span>'
    rc = rec.split(":")[0]
    out.append(f"""<tr class="h-16 border-t border-border {rowcls}">
  <td class="pl-4 pr-2 max-w-0"><p class="truncate"><span class="font-semibold">{name}</span> <span class="op-micro text-muted-foreground">· {kind} · {rc}</span></p>
    <div class="flex items-center gap-1.5 mt-1 min-w-0 overflow-hidden whitespace-nowrap"><span class="op-micro font-mono text-muted-foreground mr-0.5 shrink-0">{sku}</span>{tags}</div></td>
  <td class="px-3 text-right tnum font-medium whitespace-nowrap">{stock}</td>
  <td class="px-3 text-muted-foreground whitespace-nowrap">sem consumo</td>
  <td class="px-3"><div class="flex items-center gap-1.5">{inp}</div></td>
  <td class="px-3 text-right tnum text-muted-foreground whitespace-nowrap">sem custo</td>
  <td class="px-3"><span class="h-6 px-2 rounded-full bg-warning/12 text-warning op-micro font-semibold inline-flex items-center gap-1.5"><span class="size-1.5 rounded-full bg-warning"></span>Revisar</span></td>
</tr>""")
p = "src/purchase-base.html"
s = open(p).read()
a = s.index("<!--ROWS-->")
b = s.index("<!--/ROWS-->")
s = s[:a] + "<!--ROWS-->\n" + "\n".join(out) + "\n" + s[b:]
open(p, "w").write(s)
