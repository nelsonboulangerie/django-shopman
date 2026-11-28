# Brief: o redesenho da seção Encomendas do PDV

**Data:** 02/10/2026
**Frente:** 6 do turno de 02/10 (`docs/coordination/ORDERS/2026-10-03-turno.md:156-171`)
**Estado:** documento para o aval do dono. Nada de código nesta frente.
**Base medida:** `origin/main` em `e62b1dec6`. Todo `arquivo:linha` abaixo foi conferido
nesse commit; o que não foi está marcado **NÃO VERIFICADO**.

Caminhos curtos usados no texto:

- `index.vue` = `surfaces/pos-nuxt/app/pages/preorders/index.vue`
- `[ref].vue` = `surfaces/pos-nuxt/app/pages/preorders/[ref].vue`
- `preorders.ts` = `surfaces/pos-nuxt/app/presentation/preorders.ts`
- `kit/` = `surfaces/operator-kit/app/`
- os componentes `Pos*` moram em `surfaces/pos-nuxt/app/components/`

---

## 0. O pedido, e a tese

O dono pediu visão de produto: reconstruir o layout para ficar extremamente útil, bem
organizado e reutilizável pelos outros apps.

**A tese deste brief:** a seção Encomendas é a **agenda do balcão**. Ela responde a três
perguntas, nesta ordem de urgência:

1. **"Quem é esta pessoa na minha frente, e o que eu faço com ela?"** (achar, cobrar,
   entregar). É urgente e tem gente esperando.
2. **"O que sai hoje e o que falta fazer para isso?"** (conferir o dia, imprimir as vias,
   cobrar o que falta).
3. **"Como está a semana?"** (planejar, reagendar).

Hoje a tela responde às três, mas com peso igual, controles em dobro e o dinheiro em
quatro tamanhos. O redesenho não muda o que a tela sabe fazer: muda a ordem, tira o que
é repetido e transforma em peça da casa o que dois apps já fazem igual.

O que já foi decidido e **não se reabre aqui**: tela única, detalhe compartilhado com o
Gestor, estado na URL, busca global, Dia e Semana, filtros combináveis, impressão do
visível, ações decididas pelo servidor e volta ao mesmo recorte
(`docs/plans/WP-POS-ENCOMENDAS-UX-2026-09-29.md:18-19`). Onde este brief propõe mexer
em algo dessa lista, ele vira pergunta ao dono (seção 6).

### Como as Frentes 4, 5 e 7 se encaixam

| Frente | O que é | Relação com este brief |
|---|---|---|
| **4** | criar encomenda vira assistente de verdade (`PosOrderEntry.vue`, molde `marketing-nuxt/app/components/CampaignForm.vue:77-83`) | é a **entrada** da agenda. O passo "Quando" do assistente é o terceiro consumidor do seletor de horário (seção 4.1). A Frente 4 não espera esta: se a primitiva chegar antes, o assistente a usa; se não, usa o bloco atual e a troca vem depois |
| **5** | matar as redundâncias R1 a R5, sem aval | é a **primeira fatia** deste plano. Nada do redesenho começa antes dela (seção 3.1) |
| **6** | este documento | define o layout, as primitivas e as perguntas |
| **7** | as duas primitivas no kit | só depois do aval da seção 6. Este brief diz o contrato de cada uma (seção 4) |

---

## 1. As tarefas reais do operador

Ordem de **frequência provável**, deduzida do fluxo do balcão e não de medição: não há
telemetria de uso desta tela (**NÃO VERIFICADO** se existe). "Gesto" = um toque, um
clique ou um Enter. Digitação é contada à parte. O ponto de partida é a tela de
Comandas, onde o operador passa o dia.

| # | Tarefa | Caminho hoje (arquivo:linha) | Gestos hoje |
|---|---|---|---|
| T1 | **Achar quem veio buscar** | Encomendas na barra lateral (`PosFunctionRail.vue:58-67`) → o campo já nasce focado (`index.vue:146-147`), e qualquer tecla com o foco fora cai nele (`index.vue:156-161`) → digitar 2 caracteres ou mais (`preorders.ts:480`) → Enter abre o resultado único (`index.vue:149-152`, `:200`), ou toque na linha (`PosPreorderRow.vue:47-52`) | **2** + digitação. Bom; é a tarefa mais bem resolvida da tela |
| T2 | **Conferir o dia ou a semana** | a seção abre na Semana (`preorders.ts:65`). Hoje: toque no cabeçalho do dia (`index.vue:440-448`) ou na aba Dia (`PosPreordersShell.vue:62`). Outra semana: ‹ › do Período (`kit/components/OperatorPeriodPicker.vue:146-176`). Uma data: abrir o Período → "Ir para o dia" → data → confirmar (`OperatorPeriodPicker.vue:157-163`, `:257-275`) | semana: **1**. hoje: **2**. outra semana: **2**. uma data: **4** + digitação |
| T3 | **Receber e entregar** | depois de T1: "Receber e entregar" (`[ref].vue:199-209`) → forma, se não for a combinada (`PosPreorderHandOverDialog.vue:76-85`) → valor em dinheiro, opcional (`:87-100`) → confirmar (`:108-110`) | **2 a 3** depois do detalhe; **4 a 5** desde Comandas, + digitação |
| T4 | **Imprimir a Via Pedido** | uma: "Imprimir Via Pedido" no detalhe (`[ref].vue:265-275`). Em lote: "Imprimir N vias" (`index.vue:340-348`), que imprime **tudo o que está visível, inclusive o que já saiu** (`index.vue:109`, `preorders.ts:463-465`). Para imprimir só o que falta: Filtrar → Via Pedido → Falta imprimir (`kit/components/FilterBar.vue:128-139`, `:160-168`, `:187-196`) e depois imprimir | uma: **1** depois do detalhe. lote do que falta: **4** |
| T5 | **Achar o que falta cobrar** | de relance: o "A receber" do período (`index.vue:320-323`), o de cada dia na grade (`:456-458`) e o de cada linha (`PosPreorderRow.vue:99-103`). Para ver só elas: Filtrar → Pagamento → A receber (`FilterBar.vue:128-196`) | de relance: **0**. lista só delas: **3** |
| T6 | **Reagendar** | detalhe → "Reagendar" (`[ref].vue:242-252`) → dia (`PosPreorderRescheduleDialog.vue:108-116`; "Outra data" custa mais) → horário, opcional (`:136-153`) → motivo, opcional (`:159-162`) → confirmar (`:166-168`) | **3 a 4** depois do detalhe, + digitação opcional |
| T7 | **Cancelar** | detalhe → "Cancelar encomenda" (`[ref].vue:253-263`) → motivo, opcional (`PosPreorderCancelDialog.vue:40-43`) → confirmar (`:46-48`). Paga: o PIN ou o crachá do gerente sobe por cima (`[ref].vue:306-316`) | **2** sem pagamento; **2 + autorização** com pagamento |
| T8 | **Editar** | detalhe → "Editar encomenda" (`[ref].vue:218-228`), que **sai da seção** para a tela de venda em modo edição (`[ref].vue:68-71`). Com NFC-e autorizada, o gesto vira "Cancelar e refazer" (`[ref].vue:229-241`) | **1** para chegar; o resto é a tela de venda |
| T9 | **Comentar** | detalhe → rolar até o Histórico, a **última** seção (`kit/components/OperatorOrderDetail.vue:294-328`) → digitar → "Comentar" (`:309-325`) | **1** + rolagem + digitação |

E uma que não está na lista e falta na tela: **T0, criar uma encomenda.** A seção não
tem "Nova encomenda" (nenhum botão em `index.vue`). O caminho é Comandas → abrir uma
comanda → trocar o modo para Encomendas (`PosTabHeader.vue:95-98`, `:158-175`). Isto é
território da Frente 4; aqui só se pergunta se a agenda ganha a porta (pergunta P6).

**Leitura da tabela.** T1 e T3 estão bem (o caminho mais urgente custa 4 a 5 gestos e
o campo já espera o operador). O custo está em três lugares:

- **recortes frequentes atrás de um menu de dois passos** (T4 e T5: 3 gestos para um
  recorte que o balcão usa todo dia);
- **o lote que reimprime** o que já saiu (T4), a menos que o operador lembre de filtrar;
- **o detalhe empilha cinco botões de largura inteira** e deixa o comentário no fim da
  página (T6 a T9), sem separar o gesto destrutivo dos outros.

---

## 2. O que se vê de relance, e o que é secundário

### 2.1 Na tela da seção

**De relance (sem tocar em nada):**

| O quê | Por quê | Onde está hoje |
|---|---|---|
| o campo "Cliente veio buscar?" | é a tarefa urgente, com gente esperando | `index.vue:181-206` (fica onde está) |
| **hoje**: quantas saem, quanto falta receber, quantas vias faltam, quantas com pagamento a conferir | é o que o balcão precisa para o dia. Hoje o resumo mistura total vendido e a receber (`index.vue:320-323`), e as vias que faltam só aparecem filtrando | espalhado |
| em cada encomenda: janela, quem, retirada ou entrega, o saldo (ou "pago"), se a Via Pedido saiu | é o que decide o gesto; as quatro primeiras coisas já são a linha (`PosPreorderRow.vue:75-104`) | linha |
| o dia de hoje destacado na semana | âncora | `index.vue:435`, `:443` (fica) |

**Secundário (existe, mas não disputa):**

| O quê | Para onde vai |
|---|---|
| a nota de escopo "Retiradas e entregas de todos os canais, pela data combinada." (`preorders.ts:35`, mostrada sempre em `index.vue:316-319`) | fica, porque é a ponte da divergência de vocabulário (seção 5.6), mas sai da linha do período e vira legenda discreta abaixo da grade |
| "Incluir concluídas" (`index.vue:202-205`) | só vale para a busca (`preorders.ts:56`) e hoje aparece mesmo sem busca. Passa a aparecer **só com busca digitada** |
| o total vendido do período ("3 encomendas · R$ 120,00", `preorders.ts:174-177`) | fica, menor, depois do que falta receber. Total vendido e saldo são grandezas diferentes (D4, `docs/reference/omotenashi-copy.md:183-200`), e o balcão age sobre o saldo |
| o aviso de impressora ausente (`index.vue:337-339`) | fica, colado ao botão de imprimir (já está) |

### 2.2 No detalhe

**De relance:** quem (o nome grande), a situação do balcão e o saldo, o gesto principal
(receber e entregar, ou o motivo de não poder), e os itens.
**Secundário:** canal, contato, perfil do cliente, nota fiscal, observação, nota da
cozinha, histórico. Tudo isso já vem do `OperatorOrderDetail` do kit e fica.

Hoje o detalhe mostra **duas etiquetas de estado** lado a lado com vocabulários
diferentes: o status do pedido, do kit (`OperatorOrderDetail.vue:81-83`), e a situação
do balcão, do PDV (`[ref].vue:178-182`). E repete quem e o canal: no cabeçalho do PDV
(`[ref].vue:164-167`) e no resumo do kit (`OperatorOrderDetail.vue:84-85`, `:89-90`).
Pergunta P5.

---

## 3. Controles: o que sai, o que fica, e onde

### 3.1 As redundâncias da Frente 5 (conferidas)

| # | O que é | Caminho:linha | Recomendação |
|---|---|---|---|
| **R1** | Dia e Semana em **dois controles** que gravam o mesmo estado | abas da barra: `preorders.ts:126-132`, desenhadas por `PosPreordersShell.vue:62`. Período: `index.vue:308-314` (`presets: ['day','week']`) | **Fica o Período** (o controle de quadro da casa, decisão do dono de 02/10, `kit/presentation/dates.ts:8-10`, que já carrega ‹ › e "Voltar para hoje"). **Saem as abas.** Custo honesto: voltar do Dia para a Semana passa de 1 para 2 gestos; compensa porque a Semana é o padrão e o Dia abre tocando no dia da grade |
| **R2** | "Encomendas" com **duas navegações** para o mesmo destino | `PosFunctionRail.vue:58-67` e `PosPreordersShell.vue:64-71` | **Fica a barra lateral** (a porta da seção, decisão do dono de 26/09, `PosFunctionRail.vue:54-57`). O nome no começo da barra vira **título**, sem link. "Voltar ao início" já existe como "Voltar para hoje" e "Limpar filtros" |
| **R3** | "A receber" em **três escalas** (quatro, contando o detalhe) | `index.vue:322` (`text-sm font-semibold`), `index.vue:456` (`text-xs font-semibold`), `PosPreorderRow.vue:34-36` e `:101` (`text-sm` ou `text-xs` conforme o saldo), `[ref].vue:183` (`text-base`) | **Uma forma só para o saldo a receber:** mesmo tamanho e peso na linha, no dia e no resumo, com a palavra "A receber" escrita (cor nunca é o único portador de estado, `docs/engineering/nuxt_design_system.md:30`). O detalhe pode ser maior por ser o número principal da tela |
| **R4** | o mesmo mapa de cor de etiqueta copiado em **dois arquivos** | `PosPreorderRow.vue:24-29` e `[ref].vue:113-118`; o kit já tem `toneBadge` (`kit/presentation/orderDetail.ts:36-49`) | usar o `toneBadge` do kit. ⚠️ O kit pinta com paleta (`amber`, `red`, `green`, `blue`, `orderDetail.ts:39-45`) e o PDV com token (`warning`, `success`, `info`). A auditoria manda o token (`docs/reports/SURFACES-CONTROLS-AUDIT-2026-09-10.md:273`, `:303`). O conserto certo é **o kit passar para token** e o PDV usar o kit. Isso muda a cor do Gestor um pouco: fatia própria, com os testes do Gestor |
| **R5** | limpar filtro com **três gestos** e **duas palavras** | o X do chip (`FilterBar.vue:115-124`), "Limpar filtros" (`FilterBar.vue:141-150`), "Mostrar todas" no vazio (`index.vue:407-409`), e "Mostrar todas" do aviso de pagamento a conferir (`PosPreorderFilters.vue:61-67`), que com o filtro ligado faz o mesmo que o X do chip de Pagamento | o X do chip fica (tira **um** filtro, ato diferente). Para tirar **todos**, uma palavra só nos dois lugares: **"Limpar filtros"**, que é a do kit e já vale nos outros apps. O vazio continua oferecendo o gesto (estado vazio orienta, `docs/reference/design-surface-filter.md:168`). O botão do aviso fica só como "Mostrar só essas", e some quando o filtro já está ligado |

**Duas mais, achadas nesta leitura (entram na mesma fatia da Frente 5):**

| # | O que é | Caminho:linha | Recomendação |
|---|---|---|---|
| **R6** | código morto: o modo `compact` da linha | `PosPreorderRow.vue:17`, `:54-72`, e `compactMoneyLine` (`preorders.ts:218`). Nenhum chamador passa `compact` (`index.vue:256`, `:291`, `:421`, `:461`) | apagar o ramo e a função |
| **R7** | o dia vazio da grade diz a mesma coisa duas vezes | "Nenhuma encomenda" no cabeçalho (`index.vue:454`) e "Dia livre de encomendas" no corpo (`index.vue:463`) | uma frase só, no cabeçalho (anti-padrão "repetir informação em dois lugares próximos", `design-surface-filter.md:265`) |

### 3.2 A tela da seção, depois

```
+-rail-+ +- Encomendas ------------------- [<] [ Semana: 28/09 a 04/10 ] [>] -+
|      | |                                                                    |
| Enc. | |  Cliente veio buscar?  [ Nome, telefone, CPF ou CNPJ, ...       ]  |
| (3)  | |                                                                    |
|      | |  HOJE   6 saem   A receber R$ 240,00   3 sem Via Pedido   1 a conferir
|      | |  [A receber 4] [Sem Via Pedido 3] [Retiradas] [Entregas]            |
|      | |  [Filtrar v]                                [ Imprimir 3 vias ]     |
|      | |                                                                    |
|      | |  +- Seg 28/09 -+ +- Ter 29/09 -+ +# Hoje, qua 30/09 #+ +- Qui ... |
|      | |  | 2 . R$ 80   | | 0           | | 6 . A receber R$240 | |          |
|      | |  | 10:00 Ana   | |             | | 09:00 Rui  A receber |          |
|      | |  | ...         | |             | | 10:00 Ana  Pago      |          |
|      | |                                                                    |
|      | |  Retiradas e entregas de todos os canais, pela data combinada.    |
+------+ +--------------------------------------------------------------------+
```

| Região | Pergunta que responde | Controles | Muda o quê |
|---|---|---|---|
| **Barra da seção** (`OperatorAppBar`) | onde estou, que período | título "Encomendas" (sem link, R2) e o **Período** (R1) | o Período sobe para a barra: é o mesmo lugar em que a Produção, o KDS e o B.I. o põem (`kit/presentation/dates.ts:8-10`) |
| **Cliente veio buscar?** | quem é esta pessoa | o campo; "Incluir concluídas" só com busca | igual, menos o interruptor fora de hora |
| **Hoje** | o que falta para o dia | uma linha de fatos de hoje, sempre de hoje, qualquer que seja o período escolhido | **nova**, feita só com o que a lista já traz (`to_receive_q`, `ticket_printed`, `payment_state`: `surfaces/pos-nuxt/app/types/preorders.ts:44`, `:53`, `:66`). Sem leitura nova de API. ⚠️ Se a semana escolhida não contém hoje, a linha precisa de uma leitura de hoje: o selo da barra lateral já faz essa leitura (`preorders.ts:529-532`); **NÃO VERIFICADO** se dá para reaproveitar sem segunda chamada |
| **Recortes** | ver só o que importa agora | chips de um toque para os recortes de todo dia, e o "Filtrar" do kit para o resto. Pergunta P1 | hoje os mesmos recortes custam 3 gestos atrás do menu de dois passos |
| **Lote** | imprimir as vias | "Imprimir N vias", na linha dos recortes | o que ele imprime é a pergunta P2 |
| **Período** | a agenda | Semana (grade) ou Dia (por janela) | igual (`index.vue:413-466`) |

### 3.3 A linha da encomenda, depois

Uma forma só, nos três lugares em que aparece (dia, semana, busca):

```
[retirada]  10:00   Ana Souza                       A receber R$ 48,00
                    #1234 . WhatsApp . 2 itens          Via impressa
```

- janela primeiro, porque é a ordem em que o balcão trabalha;
- o saldo na forma única de R3;
- a etiqueta de situação só quando ela diz algo que o saldo não diz ("Pronto", "Saiu
  para entrega"); "A receber" e "Pago" já estão no dinheiro e a etiqueta repetiria;
- "Via impressa" escrita, além do ícone (`PosPreorderRow.vue:88-94` hoje é só ícone com
  `aria-label`).

### 3.4 O detalhe, depois

```
< Voltar às encomendas
+- detalhe do pedido (kit, igual ao Gestor) -+  +- Balcão --------------------+
| resumo . cliente . nota fiscal . itens .   |  | Ana Souza                   |
| observação . nota da cozinha . histórico   |  | Pronto . Falta R$ 48,00     |
| (Comentar no histórico)                    |  | [ Receber R$ 48,00 e       ]|
|                                            |  | [ entregar                 ]|
|                                            |  | [Imprimir Via] [Reagendar]  |
|                                            |  | [Editar encomenda]          |
|                                            |  | Comentar ...                |
|                                            |  | ---------------------------- |
|                                            |  | Cancelar encomenda          |
+--------------------------------------------+  +-----------------------------+
```

- **Em tela larga, o painel do Balcão fica à direita e fixo**: saldo e gestos sempre à
  vista enquanto o operador confere os itens. Em tela estreita, o painel vem **antes** do
  detalhe, na mesma ordem de hoje (gesto depois do resumo). Uma árvore só, com grade CSS;
  nada de duas árvores por tamanho de tela (`WP-POS-ENCOMENDAS-UX-2026-09-29.md:24`,
  `:104`). Pergunta P3.
- **O gesto principal ocupa a largura**; os de uso médio (Imprimir, Reagendar, Editar)
  ficam lado a lado, menores; **Cancelar fica separado**, no pé do painel
  (`design-surface-filter.md:222`; ação perigosa não ganha destaque maior que a segura,
  `nuxt_design_system.md:37-38`). Hoje são cinco botões de largura inteira empilhados
  (`[ref].vue:199-275`), e o comentário diz o contrário do que o código faz ("cancelar
  fica ao lado, menor", `[ref].vue:187`).
- **Comentar sobe para o painel** como atalho que leva ao campo do histórico (o campo
  continua do kit, `OperatorOrderDetail.vue:309-325`). **NÃO VERIFICADO** se o atalho
  basta ou se o campo precisa de slot no kit; a decisão fica para a fatia.
- O nome no topo do painel substitui o cabeçalho do PDV (`[ref].vue:164-167`), que
  repetia o que o resumo do kit já diz.

---

## 4. O que vira primitiva reutilizável

A regra da casa: promover ao `operator-kit` **só quando dois consumidores reais provarem a
mesma semântica**; necessidade exclusiva continua local (`nuxt_design_system.md:18-19`).

### 4.1 `OperatorSchedulePicker`: dia + horário + prontidão

**O que é:** a escolha de **quando** a casa cumpre um pedido. O dia pela "Escolha rápida
de dia" do kit (`kit/components/OperatorDayPicker.vue`, Tipo 1 em `dates.ts:4-6`), as
janelas do dia com a impossível **à vista e apagada com o motivo**, a frase de prontidão
dita uma vez, "A combinar", os três estados do vazio (carregando, falhou, não há), e a
regra de que **trocar o dia limpa a janela**.

**Os dois consumidores reais, hoje duplicados linha a linha:**

| Peça | `PosScheduleModal.vue` (abrir a venda) | `PosPreorderRescheduleDialog.vue` (reagendar) |
|---|---|---|
| dia | `:105-116` | `:104-120` |
| frase de prontidão | `:63`, `:118-122` | `:84`, `:122` |
| "A combinar" | `:125-135` | `:125-135` |
| grade de janelas, apagada com motivo | `:137-161` | `:136-153` |
| vazio em três estados | `:66-73`, `:162-164` | `:154-156` |
| trocar o dia limpa a janela | `:84-90` | `:71-78` |

**Por que vale, além da duplicação:** as duas cópias **já divergiram**, e cada divergência
é um defeito esperando:

- o reagendar **não passa o limite de dias da casa** (`max`): a venda passa
  (`PosScheduleModal.vue:111`), o reagendar não (`PosPreorderRescheduleDialog.vue:108-116`).
  O servidor recusa depois, mas o operador só descobre ao confirmar;
- o reagendar **não avisa o conflito** da janela escolhida que ficou impossível: a venda
  avisa (`PosScheduleModal.vue:64`, `:169`), o reagendar não;
- os rótulos "Dia" e "Horário" têm duas receitas (`PosScheduleModal.vue:106` contra
  `PosPreorderRescheduleDialog.vue:105`).

**O terceiro consumidor** é o passo "Quando" do assistente da Frente 4. Por isso a peça
nasce **sem moldura de diálogo**: é o conteúdo, e cada consumidor põe a moldura que quer
(diálogo, passo de assistente).

**Contrato proposto:** entra o hoje da loja, as datas operáveis, o limite, as janelas
anotadas, o item que segura e a hora em que libera, e o estado da leitura; sai o par dia
e janela. **Quem busca as janelas continua sendo o consumidor** (a venda já busca em
`usePosSale.ts:818`, o reagendar em `PosPreorderRescheduleDialog.vue:38-61`); a peça não
decide o que a casa pode prometer (`nuxt_design_system.md:22-23`).

⚠️ **Os dois consumidores de hoje são do mesmo app.** Nenhum outro app oferece reagendar:
a rota é a mesma do Gestor (`usePosPreorderActions.ts:152-160`), mas o `orders-nuxt` não
tem tela que a use (só o tipo gerado, `orders-nuxt/app/generated/ordersContract.ts:505`).
A regra permite o kit com dois consumidores; o espírito dela ("necessidade exclusiva
continua local") pede local enquanto só o PDV usa. Pergunta P4.

### 4.2 `OperatorReasonDialog`: motivo + confirmação destrutiva

**O que é:** o diálogo que pergunta o motivo de um gesto destrutivo que o cliente vai
ler, diz a consequência e confirma.

**Os dois consumidores reais, em dois apps:**

| | `PosPreorderCancelDialog.vue` (PDV) | `OrderReasonDialog.vue` (Gestor, `surfaces/orders-nuxt/app/components/`) |
|---|---|---|
| ato | cancelar encomenda | recusar ou cancelar pedido (`:93`) |
| consequência dita | sim: o reembolso e onde ele aparece (`:33-36`) | não: diz só para onde vai o motivo (`:94-100`) |
| motivos prontos da casa | não | sim, cadastrados no Admin (`:132-168`) |
| motivo codificado do iFood | não | sim (`:119-129`) |
| "Outros" exige texto | não se aplica | sim (`:65`, `:156-179`) |
| motivo vazio | permitido | permitido no cancelar, proibido no recusar (`:62-66`) |
| proteção de texto digitado ao fechar | não | sim, mas por `window.confirm` (`:52-55`), que foge do contrato de modal da casa (`nuxt_design_system.md:34-36`) |
| botões | `UiButton` | `<button>` à mão (`:183-193`), receita que a auditoria aponta (`SURFACES-CONTROLS-AUDIT-2026-09-10.md:112`, `:188`) |
| autorização do gerente | depois, por cima (`[ref].vue:306-316`) | **NÃO VERIFICADO** se o Gestor faz igual |

**Por que vale:** é o mesmo ato (dizer ao cliente por que o pedido não segue) com duas
caras e duas regras. A peça junta o melhor de cada um: a consequência escrita do PDV, os
motivos prontos e o "Outros" honesto do Gestor, o descarte protegido sem
`window.confirm`, os botões da casa.

**Contrato proposto:** título, consequência, motivos prontos (opcional), motivos
codificados (opcional), se o motivo é exigido, rótulo do botão de confirmar, ocupado,
erro. Sai o par motivo e código. A autorização do gerente **continua fora** (o
`OperatorManagerAuth` do kit já é a peça, `[ref].vue:306`).

⚠️ **Dependência invertida:** o kit usa o `UiDialog` do app hospedeiro
(`SURFACES-CONTROLS-AUDIT-2026-09-10.md:221-227`). PDV e Gestor têm o `UiDialog`; um
terceiro app sem ele quebraria. A peça herda o limite que o `OperatorManagerAuth` já tem;
resolver isso é outra frente.

⚠️ **No PDV, os motivos prontos não chegam:** a leitura do detalhe no contexto do balcão
manda a lista vazia (`shopman/backstage/projections/order_queue.py:565`). Ligar exige uma
mudança pequena no servidor. Pergunta P7.

**Consumidores futuros possíveis**, sem semântica conferida: `PosCancelSaleDialog.vue`
(motivo + gerente, `:72-91`), e diálogos de motivo da Produção e do KDS
(`production-nuxt/app/components/ShortageDialog.vue`,
`kds-nuxt/app/components/KdsExpeditionCard.vue`): **NÃO VERIFICADO**.

### 4.3 O que **não** vira primitiva (ainda)

- **A barra de ações do detalhe.** PDV (`[ref].vue:188-279`) e Gestor
  (`orders-nuxt/app/pages/[ref].vue:262-312`) desenham o mesmo conceito (gesto decidido
  pelo servidor; quando não pode, diz por quê), com o mesmo tipo no kit
  (`kit/types/orderDetail.ts:19-25`). Mas o PDV lê capacidades próprias do balcão
  (`counter.hand_over`, `counter.edit`) e o Gestor lê `can_*`; a semântica ainda não é a
  mesma. Fica local e é candidata quando os dois lerem `actions`.
- **A linha "Hoje".** Um consumidor só. Fica no PDV.
- **Os chips de recorte direto** (P1). Se o dono aprovar, são uma variante do `FilterBar`
  do kit (dimensão com atalho), não um componente novo; o Gestor é o segundo consumidor
  provável (**NÃO VERIFICADO**).

---

## 5. As restrições da casa

1. **Composição** (`docs/engineering/nuxt_design_system.md:14-24`): reusar `Ui*` antes de
   classe local; kit só com dois consumidores reais; página coordena, componente
   apresenta, composable orquestra, `presentation/` transforma sem I/O; **nenhuma camada
   visual deriva autorização, preço, estoque, prazo ou transição**. A linha "Hoje" e os
   chips contam o que a lista já traz; não decidem nada.
2. **Ergonomia** (mesmo arquivo, `:27-38`): um título por página; `text-xs` só para
   etiqueta e metadado (o saldo a receber não é metadado, R3); `tabular-nums`; alvo de
   44 px; modal com nome, descrição, foco e trap; ação perigosa sem destaque maior.
3. **Controles** (`docs/reports/SURFACES-CONTROLS-AUDIT-2026-09-10.md`): token, não
   paleta (`:273`, `:290`, `:303`); `rounded-lg` é contra a regra escrita (`:283`, e o
   próprio `OperatorOrderDetail` usa, `OperatorOrderDetail.vue:79`); foco num mecanismo
   só (`:163-175`); campo e botão na mesma altura (`:157-161`); o kit não pode depender de
   mais `Ui*` do hospedeiro sem decidir isso (`:221-227`).
4. **Admin/Unfold** (`docs/reference/unfold_canonical_inventory.md`): esta seção é Nuxt e
   não toca o Admin. A única ponte é a P7: os motivos prontos de cancelamento são
   cadastrados no Admin (`orders-nuxt/app/pages/[ref].vue:161`). Se a P7 for sim, o
   cadastro continua lá, como está; tela de Admin nova ou alterada segue o inventário e
   o `make admin`.
5. **Filtro de design** (`docs/reference/design-surface-filter.md`): foco primeiro e uma
   intenção dominante (`:17-18`, `:163`); um jeito canônico por intenção (`:19-20`, a raiz
   de R1, R2 e R5); badge é estado, não frase (`:125`); ação destrutiva separada,
   confirmada e com motivo (`:222`); pagamento pendente aparece antes do administrativo
   (`:223-224`); não repetir informação em lugares próximos (`:265`, a raiz de R7 e do
   cabeçalho duplicado do detalhe).
6. **O WP em vigor** (`docs/plans/WP-POS-ENCOMENDAS-UX-2026-09-29.md`): preservar tudo da
   linha `:18`; não reabrir a linha `:19`; uma árvore semanal (`:104`, `:126`); nenhuma
   leitura nova de API (`:104`); cinco tamanhos de tela (`:55`); **não mexer no
   `orders-nuxt` nem no detalhe compartilhado sem WP e PR próprios** (`:69`, `:84`). Por
   isso R4 (kit em token) e P5 (etiqueta única) são fatias separadas.
7. **Vocabulário** (`docs/reference/suite-vocabulary.md`): **encomenda** é "pedido para
   uma data futura" (`:128`), e a seção mostra também a retirada de hoje por decisão do
   dono, dita na tela (`preorders.ts:15-18`, `:35`). A colisão é conhecida e não se reabre;
   a nota de escopo fica (seção 2.1). **Item = unidade, nunca linha** (`:62`, `:147-150`):
   "2 itens" na linha da encomenda conta unidades. **Tentar de novo** é o rótulo de
   repetir (`:85-92`; já está, `index.vue:233`, `:377`). **Validar** é o ato da venda no
   PDV (`:134`); na encomenda o gesto é **Receber e entregar**, que já existe e não muda.
   **Dispositivo**, nunca a outra palavra (`:47-50`); **maquininha** para o cartão (`:48`,
   já usada em `PosPreorderHandOverDialog.vue:102`). ⚠️ "Encomendas" nomeia **duas coisas**
   no PDV: a seção (barra lateral) e o modo da venda (`PosTabHeader.vue:96-97`). É D7(b), colisão no mesmo app
   (`omotenashi-copy.md:270-274`) e é da Frente 4: este brief só registra.
8. **Copy** (`docs/reference/omotenashi-copy.md`): o teste de uma frase (`:75-92`); só o
   último passo diz o verbo do ato (`:143-146`; "Receber R$ 48,00 e entregar" está certo
   porque é o último); grandezas não se somam (D4, `:183-200`; total vendido e a receber
   ficam separados); zero não é código (D5, `:202-229`; "Nenhuma encomenda", nunca "0");
   nada de nota de rodapé do engenheiro (D6, `:231-251`). Sem travessão em texto de tela.

### 5.1 O que não pode regredir do Gestor (PR #1231)

O detalhe é **um componente do kit** usado pelos dois apps (`OperatorOrderDetail.vue:1-17`;
Gestor em `orders-nuxt/app/pages/[ref].vue:248-374`). O PR #1231 (mergeado em 29/09)
criou o componente, o contrato e os testes. Qualquer fatia deste plano mantém verdes, sem
reduzir asserção:

- `surfaces/operator-kit/tests/components/OperatorOrderDetail.test.ts` (em especial
  `:83`, "saldo no resumo, barra de ações depois dele", e `:174-196`, comentar);
- `surfaces/operator-kit/tests/orderDetail.test.ts`;
- `surfaces/orders-nuxt/tests/components/orderDetailActions.test.ts` e
  `OrderReasonDialog.test.ts`;
- `surfaces/pos-nuxt/tests/pages/preorders.test.ts` (as descrições em `:161-602`, em
  especial `:529`, "o botão imprime exatamente o visível", que muda se a P2 for 2, e
  `:542`, "oferece mostrar todas", que muda de rótulo com R5);
- `surfaces/pos-nuxt/tests/preordersPresentation.test.ts`;
- `shopman/backstage/tests/test_order_detail_context.py` e `test_pos_preorders.py`.

E, no componente: **os quatro slots e a ordem deles** (`#summary`, `#actions`,
`#after-profile`, `#kitchen-note`, `OperatorOrderDetail.vue:111`, `:208`, `:249`, `:286`),
que o Gestor preenche todos (`orders-nuxt/app/pages/[ref].vue:257`, `:262`, `:314`, `:332`);
o comentário só com a ação `comment` do servidor (`OperatorOrderDetail.vue:54`, `:309`); os
`data-*` que os testes leem.

O painel do Balcão (3.4) **não mexe no kit**: o PDV deixa de usar o slot `#actions` e
põe os gestos ao lado. O teste do kit continua testando o slot, que o Gestor usa.

Os retratos visuais do PDV (`surfaces/pos-nuxt/tests/visual/baselines/preorders-*.png`,
quatro arquivos) **vão mudar**. Só regera quem tem o browser da CI, numa sessão só
(`CLAUDE.md`, seção de coordenação).

---

## 6. Perguntas ao dono

Cada uma se responde com **sim**, **não**, **1** ou **2**. A recomendação vem entre
parênteses.

| # | Pergunta | Resposta |
|---|---|---|
| **P1** | Os recortes de todo dia (**A receber**, **Sem Via Pedido**, **Retiradas**, **Entregas**) viram botões de um toque na tela, e o "Filtrar" fica para o resto? Hoje cada um custa 3 toques. (Recomendo **sim**.) | sim / não |
| **P2** | O "Imprimir N vias" imprime: **1** = tudo o que está na tela, como hoje, inclusive as vias que já saíram; **2** = só as que ainda não saíram, e a reimpressão fica no detalhe de cada encomenda. (Recomendo **2**.) | 1 / 2 |
| **P3** | No detalhe, em tela larga, o saldo e os botões ficam num painel fixo à direita, sempre à vista enquanto se conferem os itens? (Recomendo **sim**.) | sim / não |
| **P4** | O seletor de dia e horário (hoje copiado em dois lugares do PDV): **1** = vira peça do PDV agora e vai para o kit quando outro app precisar; **2** = já nasce no kit. (Recomendo **1**.) | 1 / 2 |
| **P5** | No detalhe da encomenda, aparecem duas etiquetas de estado lado a lado (a do pedido, como no Gestor, e a do balcão, como "A receber"). No PDV fica **só a do balcão**? O Gestor não muda. (Recomendo **sim**.) | sim / não |
| **P6** | A seção Encomendas ganha um botão **"Nova encomenda"**, que abre a venda já no modo Encomendas? Hoje só se cria uma encomenda pela tela de Comandas. (Recomendo **sim**, com a Frente 4.) | sim / não |
| **P7** | Cancelar uma encomenda no balcão oferece **os mesmos motivos prontos do Gestor** (os que se cadastram no Admin)? Pede uma mudança pequena no servidor. (Recomendo **sim**.) | sim / não |

---

## 7. Plano de entrega em fatias

Cada fatia é **um PR**. O que depende do aval está marcado.

| Fatia | O que entrega | Arquivos principais | Depende de |
|---|---|---|---|
| **S0** (Frente 5) | R1 (saem as abas, fica o Período) e R2 (sai o link duplicado) | `preorders.ts`, `PosPreordersShell.vue`, `index.vue`, testes | nada; **primeira** |
| **S1** (Frente 5) | R3 (uma forma de saldo), R5 (uma palavra para limpar), R6 (código morto), R7 (vazio duplicado), "Incluir concluídas" só com busca | `index.vue`, `PosPreorderRow.vue`, `PosPreorderFilters.vue`, `preorders.ts`, testes | S0 |
| **S2** | R4: o `toneBadge` do kit passa para token, e o PDV usa o do kit | `kit/presentation/orderDetail.ts`, `PosPreorderRow.vue`, `[ref].vue`, testes do kit e do Gestor | S1. Mexe no Gestor: PR próprio (`WP-POS-ENCOMENDAS-UX-2026-09-29.md:69`) |
| **S3** | a tela da seção: Período na barra, linha "Hoje", linha da encomenda única (3.2 e 3.3), nota de escopo como legenda | `index.vue`, `PosPreorderRow.vue`, presentation, retratos | S1; **aval P1** para os chips (sem P1, sai sem os chips) |
| **S4** | o lote: imprimir só o que falta (ou manter) | `index.vue`, `preorders.ts`, teste `:529` | **aval P2** |
| **S5** | o detalhe: painel do Balcão, hierarquia dos gestos, Cancelar separado, Comentar no painel | `[ref].vue`, testes do detalhe, retratos | **aval P3**; S2 |
| **S6** | a etiqueta única no detalhe do PDV | `kit/components/OperatorOrderDetail.vue` (uma opção nova, padrão igual a hoje), `[ref].vue`, testes do kit | **aval P5**; S5 |
| **S7** (Frente 7) | `OperatorReasonDialog` no kit; o cancelar do PDV e o `OrderReasonDialog` do Gestor passam a usá-lo | `kit/components/`, `PosPreorderCancelDialog.vue`, `orders-nuxt/app/components/OrderReasonDialog.vue`, testes | aval do brief (a Frente 7 espera por ele, `docs/coordination/BOARD.md:34`) |
| **S7b** | os motivos prontos chegam ao balcão | `shopman/backstage/projections/order_queue.py:565`, contrato, testes | **aval P7**; S7 |
| **S8** (Frente 7) | o seletor de dia e horário; a venda e o reagendar passam a usá-lo, e o reagendar ganha o limite e o aviso de conflito | `PosScheduleModal.vue`, `PosPreorderRescheduleDialog.vue`, e o kit se a P4 for 2 | **aval P4** |
| **S9** | "Nova encomenda" na seção | `index.vue`, rota de abertura da venda no modo Encomendas | **aval P6**; coordenar com a Frente 4 |

**Ordem:** S0 → S1 → (S2, S3, S7, S8 em paralelo, cada um no seu branch) → S4, S5 → S6,
S7b, S9. A Frente 4 corre em paralelo e consome a S8 quando ela chegar.

**Gates de toda fatia** (os do WP em vigor, `WP-POS-ENCOMENDAS-UX-2026-09-29.md:97-112`):
nenhum teste do #1231 removido; cinco tamanhos de tela sem corte; busca focada e Enter
no resultado único; filtros e volta do detalhe preservam a URL; uma árvore semanal;
nenhuma leitura nova de API; `npm run lint`, `typecheck`, `test` e `build` no PDV, e no
kit e no Gestor quando a fatia os toca.
