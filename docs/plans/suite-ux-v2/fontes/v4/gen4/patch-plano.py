p='/tmp/claude-0/-home-user-django-shopman/6667231e-7b74-5246-8272-59b33d376d49/scratchpad/ux/mock/src/plano-porque4.html'
s=open(p).read()
# chips: Todos ativo
s=s.replace('<button class="h-10 px-3 rounded-full border border-primary bg-primary/10 inline-flex items-center gap-2 op-label font-semibold"><i data-i="check" class="size-4 text-primary"></i>A planejar <span class="tnum text-muted-foreground">20</span></button>',
 '<button class="h-10 px-3 rounded-full border border-primary bg-primary/10 inline-flex items-center gap-2 op-label font-semibold"><i data-i="check" class="size-4 text-primary"></i>Todos <span class="tnum text-muted-foreground">24</span></button>\n        <button class="h-10 px-3 rounded-full border border-border bg-card inline-flex items-center gap-2 op-label"><span class="size-2 rounded-full bg-primary"></span>A planejar <span class="tnum text-muted-foreground">20</span></button>')
# cut Brioche block and move after the aggregate
a=s.index('        <!-- Brioche: já planejado -->'); b=s.index('        <!-- conjunto -->')
brioche=s[a:b]; s=s[:a]+s[b:]
agg_end=s.index('      </div>\n    </div>\n  </main>')
planned_hdr='''        <div class="px-4 h-9 flex items-center gap-2 border-t border-border bg-muted/60"><span class="op-eyebrow text-muted-foreground">Planejados</span><span class="op-micro tnum text-muted-foreground">4</span></div>
'''
rest='''        <div class="px-4 h-12 flex items-center gap-3 border-t border-border bg-success/5 op-label">
          <i data-i="check" class="size-4 text-success"></i><span>Ciabatta <b class="tnum">26</b> · Shokupan <b class="tnum">18</b> · Madeleine <b class="tnum">70</b></span><span class="text-muted-foreground op-micro">planejados às 15:12 como sugerido</span>
        </div>
'''
s=s[:agg_end]+planned_hdr+brioche.replace('class="prow bg-success/5"','class="prow bg-success/5 border-t border-border"')+rest+s[agg_end:]
s=s.replace('+15 produtos sem ressalva</b> <span class="text-muted-foreground">· sugestão com insumos ok, sem falta nem sobra repetida</span>','+16 produtos sem ressalva</b> <span class="text-muted-foreground">· insumos ok, sem encomenda, sem falta nem sobra repetida</span>')
s=s.replace('Madeleine 70, Shokupan 18, Ciabatta 26, Pain de Campagne 34, Kuro Pan 12 e mais 10','Pain de Campagne 34, Kuro Pan 12, Baguete Gergelim 30, Focaccia do dia 10 e mais 12')
s=s.replace('Planejar os 15 como sugerido','Planejar os 16 como sugerido')
s=s.replace('um "sim" do responsável para os 15','um "sim" do responsável para os 16')
s=s.replace('left:1070px;top:582px">6','left:1030px;top:446px">6').replace('left:1400px;top:666px">7','left:1400px;top:800px">7').replace('left:1400px;top:768px">8','left:1400px;top:620px">8')
s=s.replace('<span class="h-8 px-3 rounded-full bg-success/12 text-success op-label font-semibold inline-flex items-center gap-1.5"><i data-i="check" class="size-4"></i>Planejado 15:12</span>','<span class="h-8 px-3 rounded-full bg-success/12 text-success op-label font-semibold inline-flex items-center gap-1.5 whitespace-nowrap"><i data-i="check" class="size-4"></i>Planejado 15:12</span>')
open(p,'w').write(s)
print('ok')
