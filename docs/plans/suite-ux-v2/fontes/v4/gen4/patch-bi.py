D='/tmp/claude-0/-home-user-django-shopman/6667231e-7b74-5246-8272-59b33d376d49/scratchpad/ux/mock/'
p=D+'gen4/gen-bi-sobra4.py'; s=open(p).read()
rep={"'3 de 4 sábados','faltou de novo'":"'faltou 3 de 4','típico vende ~50; fez 44'",
"'1 de 4 sábados','primeira vez em 4',False),\n ('Bichon":"'faltou 1 de 4','típico ~24; fez 26',False),\n ('Bichon",
"'15:10','1 de 4 sábados','primeira vez em 4'":"'15:10','faltou 1 de 4','típico ~22; fez 24'",
"'sobrou em 3 de 4','sobra de 12 (R$ 61 de custo)'":"'sobrou 3 de 4','típico ~50; R$ 61 de custo'",
"'sobrou em 2 de 4','sobra de 7 (R$ 38)'":"'sobrou 2 de 4','típico ~34; R$ 38 de custo'",
"'sobrou em 2 de 4','sobra de 5 (R$ 33)'":"'sobrou 2 de 4','típico ~16; R$ 33 de custo'",
"'na medida em 3 de 4','sobrou 1'":"'na medida 3 de 4','típico ~34'",
"'na medida em 4 de 4','acabou perto de fechar'":"'na medida 4 de 4','acabou perto de fechar'",
"110px_250px_120px_100px_minmax(0,1.2fr)_150px":"110px_250px_100px_130px_minmax(0,1.2fr)_150px"}
for a,b in rep.items():
    if a in s: s=s.replace(a,b)
    else: print('miss',a)
open(p,'w').write(s)
t=D+'gen4/bi-sobra-tpl.html'; s=open(t).read()
s=s.replace("110px_250px_120px_100px_minmax(0,1.2fr)_150px","110px_250px_100px_130px_minmax(0,1.2fr)_150px")
s=s.replace("+4 na medida: Madeleine, Kuro Pan, Baguete Gergelim e Focaccia do dia","+4 produtos: Focaccia do dia (sobrou 6) · Madeleine, Kuro Pan e Baguete Gergelim (na medida)")
s=s.replace("<div>Sábados</div>","<div>Nos 4 sábados</div>")
s=s.replace('left:96px;top:18px">1','left:368px;top:20px">1').replace('left:96px;top:132px">5','left:486px;top:136px">5').replace('left:96px;top:320px">8','left:742px;top:286px">8').replace('left:1046px;top:18px">2','left:1040px;top:-2px">2')
open(t,'w').write(s)
