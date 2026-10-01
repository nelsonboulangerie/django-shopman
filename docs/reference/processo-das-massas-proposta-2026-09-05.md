> 🛑 **RASCUNHO NÃO VALIDADO.** Proposta do Claude de 05/09/2026; o dono vai revisar
> massa por massa no chat. **Não é dado da casa** (decisão D20, 01/10/2026). Nada daqui
> entra no seed, no banco nem em caminho de dado de produção; a trava é
> `shopman/shop/tests/test_seed_sem_processo_das_massas.py`.

# Processo das 11 massas (proposta de 05/09/2026, NÃO validada pela casa)

> ⚠️ **Leia isto antes de usar qualquer número abaixo.** Esta é a única tabela de
> temperatura e de tempo por etapa que existe para as massas da casa, e ela é uma
> **proposta do agente**, não uma medição da Nelson. Não é dado da casa, não é
> referência de produção e **não entra no seed nem no banco**.

## De onde veio

- **Fonte:** artifact do claude.ai `b8cd4fc0-c136-47d0-aac2-0a4c912e0e59`, "Fichas dos
  Pães", de 05/09/2026. A parte de processo dele não estava no repositório até aqui.
- **Resgatado em:** 01/10/2026, transcrito por inteiro: 11 massas, 92 etapas, colunas
  fase · etapa · tempo · temperatura · nota, sem edição de conteúdo.

## O que ela é, nas palavras do próprio artifact

- O artifact rotula a seção de processo como *"proposta minha — é a parte que eu menos sei"*.
- O rodapé dele diz o que falta: *"O que eu não sei e você sabe: tempos, temperatura da
  massa, ordem das dobras e o ponto de cada fermentação"*.

Ou seja: tempo, TMD (temperatura de massa desejada), temperatura de fermentação, ordem
das dobras e temperatura de forno abaixo são **chute informado de quem escreveu**, de
literatura de panificação, não do caderno do padeiro. Algumas linhas carregam uma
premissa de operação (o retardo em câmara da Tradição "é o que faz caber num forno só");
a premissa também é do artifact, e vale conferir junto com o número.

## Como usar (e como não usar)

- **Serve** como roteiro de conversa com o dono e com a padaria: uma linha por etapa,
  para alguém riscar e corrigir com o número verdadeiro.
- **Não serve** para popular `Recipe.steps` / `RecipeVersion.steps`, nem `target_seconds`,
  nem `temperature_celsius` (o campo opcional de temperatura da etapa existe desde a
  decisão D19, de 01/10/2026, e se preenche com o número do padeiro, nunca desta tabela). O formato das etapas gravadas está em
  [`packages/craftsman/shopman/craftsman/recipe_steps.py`](../../packages/craftsman/shopman/craftsman/recipe_steps.py);
  a modelagem de receita, em [`RECIPE-MODELING-BRIEF.md`](../plans/RECIPE-MODELING-BRIEF.md).
- **Vocabulário:** cada linha é uma **etapa** (decisão do dono, 01/10/2026; ver
  [`suite-vocabulary.md`](suite-vocabulary.md)). As **fases** (véspera, mistura, pointage,
  tourage, apprêt, forno) são o agrupamento que o artifact usou, não um campo do modelo.
- Os códigos de peça (BF, CGO, CI…) são os do artifact em 05/09; vários SKUs foram
  renomeados depois (rename de SKU de 22/09). Confira no catálogo vivo antes de cruzar.

---

## As tabelas, como estavam no artifact

<!-- massas=11 etapas=92 -->

### Massa Tradição

Peças: BF baguete · BAP lanche · BA bâtard · BAX italiano · BEP/BE gergelim · MIB mini · FE fendu · TB tabatière

| Fase | Etapa | Tempo | Temperatura | Nota |
|---|---|---|---|---|
| véspera | Refrescar o levain | 12 h | 24 °C | Maduro quando triplica e a cúpula começa a achatar. |
|  | Autólise | 60 min | ambiente | Só farinha e água. Sem sal, sem levain. |
| mistura | Autólise + levain, 1ª velocidade | 4 min |  |  |
|  | Sal, 2ª velocidade | 3 min | TMD 24 °C | Temperatura de massa desejada. |
|  | Bassinage, 1ª velocidade | 2 min |  | Os 113 g de água por quilo de farinha, aos poucos. |
| pointage | Fermentação em bloco | 3 h | 24 °C | Duas dobras: aos 45 e aos 90 minutos. |
|  | Divisão e pré-modelagem |  |  |  |
|  | Descanso de bancada | 20 min | ambiente |  |
|  | Modelagem |  |  |  |
| apprêt | Retardo em câmara | 12–15 h | 5 °C | Assa direto da geladeira, de manhã. É o que faz caber num forno só. |
| forno | Baguete de 280 g | 22 min | 250 °C | Vapor nos 10 primeiros minutos. |

### Massa Campagne

Peças: CGO/CGR campagne · CF baguette campagne · CPX passas e castanhas

| Fase | Etapa | Tempo | Temperatura | Nota |
|---|---|---|---|---|
| véspera | Refrescar o levain | 12 h | 24 °C |  |
|  | Autólise | 60 min | ambiente | Só a T55. Integral e centeio entram na mistura final. |
| mistura | Autólise + levain, 1ª velocidade | 4 min |  |  |
|  | Integral, centeio e sal, 2ª velocidade | 4 min | TMD 24 °C |  |
|  | Bassinage, 1ª velocidade | 2 min |  | 243 g de água — é bastante, vá devagar. |
| pointage | Fermentação em bloco | 3 h 30 | 24 °C | Três dobras: 45, 90 e 135 minutos. O integral pede mais estrutura. |
|  | Divisão, pré-modelagem, descanso | 25 min | ambiente |  |
|  | Modelagem em banneton |  |  |  |
| apprêt | Retardo em câmara | 14–16 h | 5 °C |  |
| forno | Campagne de 340 g | 35 min | 240 °C | Vapor nos 15 primeiros minutos. |

### Massa Ciabatta

Peças: CI ciabatta

| Fase | Etapa | Tempo | Temperatura | Nota |
|---|---|---|---|---|
| véspera | Refrescar o levain | 12 h | 24 °C |  |
|  | Autólise | 60 min | ambiente |  |
| mistura | Autólise + levain, 1ª velocidade | 3 min |  |  |
|  | Sal, 2ª velocidade | 3 min | TMD 25 °C |  |
|  | Bassinage, 1ª velocidade | 3 min |  | 149 g de água no fim. A massa tem que ficar lisa antes de cada adição. |
| pointage | Fermentação em bloco | 3 h | 25 °C | Três dobras na bacia: 30, 60 e 90 minutos. |
| apprêt | Virar na farinha e cortar | 45 min | ambiente | Sem modelagem. Corte direto e leve ao forno. |
| forno | Ciabatta de 205 g | 18 min | 250 °C | Vapor nos 8 primeiros minutos. |

### Massa Focaccia

Peças: FOA alecrim · CBT · FOC · MIF · MICBT · MIFOC  (NOVA — separada da ciabatta)

| Fase | Etapa | Tempo | Temperatura | Nota |
|---|---|---|---|---|
| véspera | Refrescar o levain | 12 h | 24 °C |  |
|  | Autólise | 60 min | ambiente |  |
| mistura | Autólise + levain, 1ª velocidade | 3 min |  |  |
|  | Sal e azeite, 2ª velocidade | 4 min | TMD 25 °C | O azeite entra depois do glúten formado. |
|  | Bassinage, 1ª velocidade | 2 min |  |  |
| pointage | Fermentação em bloco | 2 h | 25 °C | Duas dobras: 40 e 80 minutos. |
|  | Estender na assadeira untada |  |  | Deixe relaxar 20 min se resistir. |
| apprêt | Fermentação na assadeira | 60 min | 26 °C | Covinhas com a ponta dos dedos, azeite e sal grosso na hora de assar. |
| forno | Focaccia | 20 min | 230 °C | Sem vapor. |

### Massa Forma

Peças: FA shokupan · JO caranguejo · ME melonpan

| Fase | Etapa | Tempo | Temperatura | Nota |
|---|---|---|---|---|
| véspera | Yudane | 8–12 h | 4 °C | Água fervente sobre a farinha, mistura 3 min, esfria e vai para a geladeira. |
| mistura | Tudo menos a manteiga, 1ª velocidade | 5 min |  |  |
|  | 2ª velocidade | 8 min |  | Até véu — a forma exige glúten bem desenvolvido. |
|  | Manteiga, 2ª velocidade | 4 min | TMD 27 °C |  |
| pointage | Fermentação em bloco | 60 min | 28 °C |  |
|  | Divisão e boleamento |  |  |  |
|  | Descanso de bancada | 15 min | ambiente |  |
|  | Modelagem em rolo, na forma |  |  |  |
| apprêt | Fermentação final | 70 min | 30 °C | Até 80% da altura da forma. |
| forno | Shokupan de 400 g | 30 min | 190 °C | Com tampa, se for pullman. |

### Massa Kuropan

Peças: KP kuro pan · KBB kuro pan burger

| Fase | Etapa | Tempo | Temperatura | Nota |
|---|---|---|---|---|
| véspera | Yudane | 8–12 h | 4 °C |  |
| mistura | Tudo menos a manteiga, 1ª velocidade | 5 min |  | O cacau entra aqui, com a farinha. |
|  | 2ª velocidade | 8 min |  |  |
|  | Manteiga, 2ª velocidade | 4 min | TMD 27 °C |  |
| pointage | Fermentação em bloco | 60 min | 28 °C |  |
|  | Divisão, boleamento, descanso | 15 min | ambiente |  |
|  | Modelagem |  |  |  |
| apprêt | Fermentação final | 70 min | 30 °C |  |
| forno | Kuro Pan de 280 g | 25 min | 180 °C | Mais baixo que a Forma: o cacau queima antes de a massa assar. |

### Massa Butter

Peças: CH challah · HO/MIHO hot dog · DL deli · COC/CO cornet · PH hambúrguer · PHO hot dog

| Fase | Etapa | Tempo | Temperatura | Nota |
|---|---|---|---|---|
| mistura | Tudo menos a manteiga, 1ª velocidade | 4 min |  |  |
|  | 2ª velocidade | 6 min |  |  |
|  | Manteiga, 2ª velocidade | 4 min | TMD 26 °C |  |
| pointage | Fermentação em bloco | 60 min | 26 °C |  |
|  | Divisão, boleamento, descanso | 15 min | ambiente |  |
|  | Modelagem |  |  |  |
| apprêt | Fermentação final | 75 min | 28 °C |  |
| forno | Peça de 100 g | 14 min | 180 °C | Challah de 300 g: 25 min. Pincelar com ovo antes. |

### Massa Brioche

Peças: BN nanterre · BCH chocolat · ANU/ANP/ANC bichinhos · MBBBG/BBB buns

| Fase | Etapa | Tempo | Temperatura | Nota |
|---|---|---|---|---|
| mistura | Tudo menos a manteiga, 1ª velocidade | 5 min |  |  |
|  | 2ª velocidade | 12 min |  | Até véu firme, antes de qualquer manteiga. |
|  | Manteiga em três vezes, 2ª velocidade | 8 min | TMD 24 °C | Acima de 26 °C a manteiga separa. É a etapa crítica. |
| pointage | Fermentação em bloco | 60 min | ambiente |  |
|  | Retardo em câmara | 12 h | 4 °C | Obrigatório. Brioche quente não modela. |
|  | Divisão e modelagem, com a massa gelada |  |  |  |
| apprêt | Fermentação final | 2 h 30 | 26 °C | Nunca acima de 28 °C. |
| forno | Nanterre de 240 g | 28 min | 170 °C | Peça de 30 g: 10 min. Pincelar com ovo. |

### Massa Pita

Peças: PI pita

| Fase | Etapa | Tempo | Temperatura | Nota |
|---|---|---|---|---|
| mistura | Tudo junto | 8 min | TMD 26 °C | Massa magra, mistura simples. |
| pointage | Fermentação em bloco | 60 min | 26 °C |  |
|  | Divisão e boleamento |  |  |  |
|  | Descanso de bancada | 20 min | ambiente |  |
|  | Abrir em disco de 3 mm |  |  |  |
| apprêt | Descanso antes do forno | 20 min | ambiente |  |
| forno | Pita de 30 g | 3 min | 280 °C | Infla sozinha. Se não inflar, o forno está frio. |

### Massa Croissant

Peças: CT croissant · CM mini · PC pain au chocolat · PR aux raisins · CPQ presunto e queijo

| Fase | Etapa | Tempo | Temperatura | Nota |
|---|---|---|---|---|
| mistura | Détrempe, 1ª velocidade | 4 min | TMD 22 °C | Mistura curta: glúten demais atrapalha a laminação. |
| pointage | Fermentação em bloco | 30 min | ambiente |  |
|  | Bloquear | 60 min | 4 °C |  |
| tourage | Três voltas simples | 30 min entre cada | 4 °C | A manteiga e a massa têm que estar na mesma consistência. |
|  | Abrir a 3,5 mm, cortar e enrolar |  | 4 °C |  |
| apprêt | Fermentação final | 2 h 30 | 26 °C | Nunca acima de 28 °C — a manteiga escorre e o folhado morre. |
| forno | Croissant de 80 g | 18 min | 180 °C | Pincelar com ovo antes. |

### Massa Folhado

Peças: CN folhado do dia · BH bichon · MA maçã · FF/MFF folhado de frango  (SEM fermento)

| Fase | Etapa | Tempo | Temperatura | Nota |
|---|---|---|---|---|
| mistura | Détrempe, 1ª velocidade | 3 min |  | Sem fermento. Sem desenvolver glúten. |
| pointage | Repouso | 60 min | 4 °C |  |
| tourage | Seis voltas simples | 45 min entre cada | 4 °C | Ou três duplas e uma simples, se preferir. |
|  | Repouso final antes de cortar | 2 h | 4 °C | Se cortar antes, a massa encolhe no forno. |
| forno | Folhado de 80 g | 22 min | 200 °C | Sem vapor. Furar a massa onde não deve crescer. |
