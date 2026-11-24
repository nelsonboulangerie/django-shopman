# EXCELÊNCIA-PRODUCAO: laudo e plano do app Produção

Compromisso: DEV-2026-079. Brief: `docs/coordination/ROUNDS/EXCELENCIA-PRODUCAO.md`, sobre a
base `docs/coordination/ROUNDS/EXCELENCIA-base.md`. Medido em 23/11/2026 contra o `main`
`65c2e2550` (worktree em `7bdeb0c84`, um commit de docs à frente). Nenhum código de produção
foi escrito.

"Produção" aqui é o app dos lotes (`surfaces/production-nuxt`), nunca o ambiente de deploy.

Ênfase: **a fornada é a fonte da promessa**.

## Sumário

- **2 achados P0, 30 P1 e 21 P2** no perímetro da Produção, mais 16 itens de fronteira.
- **Os dois P0 foram medidos pela tela, com PIN de operador:**
  - quem opera o chão, sem a permissão de cancelar lote, digita 0 no Planejamento e **tira do
    plano o lote que lastreava uma encomenda paga e aceita**, sem nenhum aviso;
  - o lote que **rendeu menos que o encomendado não fecha**: a tela manda "informar pelo
    menos 6" e o botão "Revisar quantidade" não faz nada. O pão existe e não entra no estoque.
- **A causa que mais se repete é de desenho:** a Produção lê e trava por uma régua própria do
  "prometido" (o vínculo pedido × lote), diferente da que a loja, o PDV e o Gestor usam (as
  reservas da data). Onde a régua trava, o chão não consegue dizer a verdade; onde ela não
  olha, o gesto passa calado. Seis P1 e os dois P0 saem daí.
- **O salto que mais impressiona:** "A fornada responde". No momento do gesto (abrir, fechar,
  reduzir, cancelar) a Produção diz quem fica sem pão e entrega a saída pronta: "Rendeu 4 de
  40. Três encomendas ficam descobertas. Fechar com 4 e avisar o Gestor." Nenhum dos onze
  produtos pesquisados leva o gesto do padeiro até a promessa feita ao cliente.
- **23 WPs em 7 ondas** (o WP-F09 virou F09a e F09b em 24/11), cada um dimensionado para uma sessão Opus 5.5 em esforço médio. Os
  primeiros a delegar são o **WP-F01** (zerar não cancela, o P0 de permissão, só servidor) e
  o **WP-F00** (harness de operador de verdade), juntos.
- **5 decisões do dono, todas respondidas** pela recomendação (D-042, 23/11; a 2 e a 5
  reconfirmadas em 24/11). Ver a seção 10.
- **O vocabulário do brief está vencido.** O brief fala em "Planejado, Produzido, Concluído",
  "Quanto foi produzido?" e "Expedição". Desde 29/10/2026 valem as abas Planejamento,
  Preparação, Produção, Finalização e Qualidade, e as quantidades **planejado, previsto e
  realizado** (`docs/reference/suite-vocabulary.md:69`, com trava em
  `surfaces/production-nuxt/tests/lifecycleVocabulary.test.ts:30-38`). Este plano usa o
  vocabulário vigente. O grupo de quem opera o chão é **Cozinha** (`diofer` no seed), não
  "Produção" (`docs/guides/rbac-personas.md:47`).
- **O que este PR deixou de fora tem issue** (seção 12).

## 1. Como foi medido, e o que a medição não cobre

**Pilha isolada**, só as portas e o banco do brief: Django `:8090` com o worker de
directives, banco `shopman_exc_producao`, Produção `:3195`, loja `:3190` e Gestor `:3194`
(os quatro apps compilados). `migrate` e `seed --flush` rodaram até o fim. O relógio de teste
(`TEST_STACK_CONTROL_DIR`, #2585) foi usado para a virada do dia.

**Como operador de verdade.** A Gerente (`joyce`) entrou com senha e liberou o dispositivo;
quem opera o chão (`diofer`, grupo Cozinha) e a Gerente se identificaram na tela de bloqueio,
com PIN no teclado da tela. Nunca o superusuário. Cada gesto foi um toque na tela, dirigido
por Playwright (Chromium), em tablet deitado (1024 × 768, com toque), tablet em pé
(768 × 1024), celular (375 × 812), balcão (1366 × 768) e TV (1920 × 1080). A encomenda da
jornada 4 nasceu pela loja, com a jornada canonizada J3 do Gestor
(`surfaces/orders-nuxt/tests/operator/j3-aceitar-a-encomenda-com-o-dia.spec.ts`): a cliente
encomenda um Croissant para amanhã, paga, e a Caixa aceita. O banco foi lido só para conferir
o que cada gesto gravou; nenhum estado nasceu por API, Admin ou banco.

**Leitura de código.** `ProductionStageGrid.vue` (2.741 linhas), todas as páginas, componentes
e composables do app; `projections/production.py` (4.858), `services/production.py` (4.297),
as APIs de produção; e, só para as fronteiras, `shop/handlers/production_order_sync.py`,
`_stock_receivers.py`, `services/production_promise.py` e a ponte
`craftsman/contrib/stockman`. As provas de maior peso foram reconferidas linha a linha.

**Histórico.** Cada pendência dos planos e laudos antigos foi conferida contra o `main` de
hoje (seção 2).

**Benchmarks.** Onze produtos, por páginas públicas de produto, ajuda e changelog (seção 11).
Nada foi testado em conta real: toda ausência é **estimada pela documentação, não medida**.

**Limites, ditos com nome:**

| O que | Por quê | Como ficou provado |
|---|---|---|
| "Pedido à Produção" criado pelo PDV (data sem lote, WP-E3) | o PDV foi compilado e não foi percorrido: a janela foi gasta nas jornadas do chão | leitura de código, marcado **[código]**; a jornada J-P5 nasce no WP-F13 |
| Falta de insumo na abertura e no fim | o seed grava o lote como produzido sem baixar insumo (#2339), então a pilha não chega à falta por gesto de operador | **[código]**, com `caminho:linha` |
| Dia fechado e volta de feriado no Planejamento | o seed da pilha abre a loja 24 h todos os dias (`SHOPMAN_STAGING_AUTOPILOT`) e não há feriado na janela | sábado e domingo foram medidos; "fechado" ficou em **[código]** |
| Receitas: criar, publicar e comparar versões | a lista, "Nova receita" e "Conferir" foram abertas; o ciclo inteiro não foi percorrido | **[código]** |
| Etiquetas de pesagem e do lote, e timers tocando | pedem impressora e som no dispositivo | **[código]** |
| "Novo dia" depois de recarregar a grade | o relógio de teste vale só para o Django; o servidor do Nuxt segue a hora real | medido o que não depende disso: a grade aberta atravessando a meia-noite, e a Finalização do novo dia |
| Desempenho | outras revisões compilavam na mesma máquina (carga 7 a 8) | fora do laudo |

Capturas em `docs/coordination/EVIDENCE/EXCELENCIA-PRODUCAO/` (abreviado `EV/`).

## 2. Histórico: o que já está no `main` (não reauditar)

| Item | Onde está hoje |
|---|---|
| Contrato com revisão, chave de idempotência e prova de ação; capacidades por projeção | plano de 08/09 (P0.0 a P1.6); `services/production.py:219-333`, `api/_production_mutations.py:751-864` |
| SSE como invalidação na grade | #1754; `composables/useProductionBoard.ts:84-119` |
| Uma ação por produto na aba Produção, "Confirmar", sem subetapas; timers opcionais | #734, #735, #859 |
| Perda com motivo de um toque, graus de qualidade, perda total | ADR-017; medido: `EV/19-perda-motivo-em-um-toque.png` |
| Sugestão explicável ("Por quê"), dia da semana e estação da data-alvo, dias fechados fora da amostra, esgotamento extrapolado | #156, #1459, #1465, #1475; `PlanReasonCard.vue` |
| Encomenda compõe a sugestão sem histórico; sacola não entra na sugestão | #2855, #3269 |
| Lote cancelado, curto ou atrasado vira fato do pedido e "Promessa em risco" no Gestor | #2595, #2714, #3149, #2839 (medido: evento `production_hold_lost` e aviso `order_promise_lost`) |
| Acima do plano avisa a Produção; só o gerente libera; data sem lote vira pedido à Produção | #2598, #2679, #2932 (D-041) |
| Sobra de hoje não lastreia encomenda (na régua das reservas) | #2703; `shop/policies/promise_expiry_margin.py` |
| Cancelar o planejado pela matriz; 1024 px na matriz e no Planejamento | #2960, #2964, #2975 (o brief cita as issues #2957, #2959, #2966) |
| Cancelar lote que já entregou pão é recusado | #3232 |
| Custo congelado e margem por fornada, fechada pela validade | #2272, #2287 |
| Estação autônoma do Letreiro presa ao prefixo da API de Produção | #827; `backstage/station_trust.py:54-75` |

**Documentos que envelheceram:** `docs/reference/glossary.md:51-52` ainda chama as abas de
Abertura e Fechamento; o brief desta revisão usa o vocabulário de 16/09 (ver Sumário).

**Pontos fortes que nenhum WP pode regredir:**

1. Escrita com prova: cada mutação nasce de uma projeção daquele operador, data e revisão,
   com replay quando a resposta se perde (`composables/useProductionMutationGuard.ts:162-202`;
   `services/production.py:219-333`).
2. Dois tablets no mesmo lote: o segundo recebe 409 com o estado atual; duplo toque vira
   replay (`services/production.py:3455-3473`).
3. A recusa preserva o que foi digitado (`ProductionStageGrid.vue:570-599`). Medido: depois
   da recusa de 4, "Revisar quantidade" reabriu o painel e 40 passou.
4. A perda se declara com dois toques e um motivo pronto (`EV/19`), e o zero a mais pede
   conferência longe do Confirmar (`presentation/production.ts:445-471`).
5. A Finalização do novo dia avisa "8 lotes abertos de dias anteriores", com "Ver os lotes de
   23/11" (`EV/14`; `pages/close.vue:325-345`).
6. Ledger por append: o evento de fechamento guarda planejado, previsto, realizado e perda;
   a correção de qualidade não reescreve linhas (`craftsman/services/execution.py:655-672`).
7. Nenhuma tela estourou a largura em 375 px (medido nas oito rotas).

## 3. Roteiro percorrido pela UI

Papéis: Gerente (senha e PIN), Cozinha (PIN), cliente nova pela loja, Caixa pelo Gestor.

| Passo | O que a tela mostrou | Achado |
|---|---|---|
| Cozinha abre a Produção de hoje (1024) | oito lotes, cinco abertos; Croissant "6 un." com a sacola (`EV/01`) | - |
| Toca "Confirmar" no Croissant | o painel "Quanto está previsto?" abre ao lado e a lista some: nomes viram "Bi a.", "C", "K P", cabeçalho "PRODUTOSITUAÇÃO" sobreposto, o próprio botão cortado em "Confirm" (`EV/02`) | P1-06 |
| Digita 4 (abaixo das 6 encomendadas) e confirma | "Quantidade não cobre pedidos. Encomendado: 6.000 un. · informado: 4.000 un. Pedidos: PDV-261123-B72… Confira a contagem e informe pelo menos 6.000 un. Se saiu mesmo menos, nada foi registrado: avise quem cuida das encomendas" (`EV/03`) | P0-2 |
| "Revisar quantidade", digita 40 | passa: "Lote aberto: Croissant Manteiga × 40" | ponto forte 3 |
| Finalização: abre o Croissant, Normal 4, Finalizar | "Rendeu 4 de 40 previstos? Por que rendeu menos?" com campo de texto obrigatório e "Confirmar 4 unidades" desligado (`EV/04`) | P1-07 |
| Digita o motivo e confirma | a mesma recusa, agora sobre o pão já assado. "Revisar quantidade" não faz nada: o diálogo fica (`EV/05`) | P0-2 |
| Finalização da Ciabatta: Perda 2, Finalizar | sete motivos em botões grandes ("Assou demais: escuro, casca amarga"); fecha em dois toques (`EV/19`). Depois a tela pula sozinha para a Focaccia, que nem foi aberta, com o toast "Lote enviado para Qualidade (QC)." | P2-11, P2-12 |
| A mesma tela em 375 px | teclas de 36 px de largura; "Realizado 26 de 26" com 2 de perda (`EV/15`) | P1-08 |
| Planejamento de sábado | Croissant "374 · acabou cedo" contra 42 planejados por dia; o "Por quê" abre a conta: "260 média dos sábados + 114 margem" (`EV/11`) | P2-01 |
| "Planejar 315" (Madeleine, como sugerido) | planeja; o pedido vai com `source: manual`; o item passa a dizer "como sugerido" | P1-05 |
| Abre o planejado: "Corrigir quantidade", digita 0 | o botão vira "Remover do plano" para a Cozinha, que não pode cancelar lote (`EV/06`); toca e "Madeleine saiu do plano." | P0-1 |
| Cliente encomenda 1 Croissant para amanhã, paga; a Caixa aceita (J3) | pedido `NB-261123-B57`, reserva presa ao lote planejado de amanhã | - |
| Cozinha abre o Planejamento de amanhã | o lote do Croissant não mostra encomenda nenhuma; o conjunto dos outros produtos diz "sem encomenda" | P1-02, P1-04 |
| "Corrigir quantidade", 0, "Remover do plano" | nenhum aviso (`EV/07`); "Croissant Manteiga saiu do plano." (`EV/08`). No banco: lote cancelado por `production:diofer` com o motivo "Planejamento zerado na matriz"; a reserva do pedido pago foi solta | P0-1 |
| Cozinha replaneja o Croissant de amanhã (42) | "Planejado". No banco: a reserva do pedido pago continua solta | F-02 |
| Produção de hoje, de novo | o lote de HOJE agora diz "7 un. para 9h" e lista `NB-261123-B57`, a encomenda de AMANHÃ (`EV/10`) | P1-02 |
| Gerente abre "Cancelar lote…" no Croissant de hoje (7 un. encomendadas) | "O lote volta atrás e o vínculo com pedidos é desfeito.", motivo opcional, sem número, sem pedidos, sem hora (`EV/09`) | P1-01 |
| Sino da Cozinha | "Pedido ficou sem a produção prometida… Abrir o pedido", "Produção WO-2026-00028 (MDLN) está há 1047 min em andamento · pedido WO-2026-00028" (`EV/20`) | P1-15 |
| Grade aberta às 23h57; o relógio passa da meia-noite | às 0h04 a grade segue em "Hoje, seg 23/11" (`EV/13`) | P1-09 |
| Finalização às 0h04 | "8 lotes abertos de dias anteriores · Ver os lotes de 23/11" (`EV/14`); a Produção e a Preparação não dizem nada | P1-09 |
| Preparação, "Por insumo" | caixa de marcar de 16 px; "As marcações ficam somente neste dispositivo" (`EV/22`) | P1-19 |
| Tablet em pé: "Confirmar" | modal com campo de texto e "−" e "+" de 40 px; sem teclado na tela (`EV/23`) | P1-25 |
| Letreiro em 1920 × 1080 | linhas em 24 px, título "Lotes", "UN" em toda quantidade (`EV/18`) | P1-21 |
| Relatórios, como Gerente | "OP", datas "2026-11-17", "producao", "chef:ana", "Realizado 77 un. · 159,65 kg de 86 un. · 159,65 kg" (`EV/21`) | P2-05 |
| Gerente entra no app | convite "Vincular este dispositivo a um posto de trabalho? Ainda não há posto para este app…" sobre a tela | F-12 |

## 4. Laudo

Lentes: UX (UX/UI) · COPY · CONTR (contrato) · PERM (segurança e permissão) · OMO
(omotenashi-first) · MOB (mobile-first) · FLUXO (continuidade do fluxo) · PROM (a promessa de
produção).

Caminhos abreviados: `GRID` = `surfaces/production-nuxt/app/components/ProductionStageGrid.vue`
· `FE` = `surfaces/production-nuxt/app` · `PROJ` = `shopman/backstage/projections/production.py`
· `SVC` = `shopman/backstage/services/production.py` · `OPS` =
`shopman/backstage/api/operations.py` · `MUT` = `shopman/backstage/api/_production_mutations.py`
· `SHOPSVC` = `shopman/shop/services/production.py` · `SYNC` =
`shopman/shop/handlers/production_order_sync.py` · `RECV` =
`shopman/shop/handlers/_stock_receivers.py` · `CORE` = `packages/craftsman/shopman/craftsman`.

**[medido]** = visto na pilha, pela tela. **[código]** = leitura, não exercitado.

### 4.1 A causa de desenho

Existem **duas réguas** do que está prometido, e a Produção usa a que ninguém mais usa.

| | Régua das reservas (A) | Régua do vínculo (B) |
|---|---|---|
| O que é | reservas do Stockman contra o saldo planejado da data | `order.data.awaiting_wo_refs` ↔ `work_order.meta.committed_order_refs`, "contextual e desnormalizado" (`SYNC:1-7`) |
| Quem lê | loja, PDV, Gestor, a sugestão e a trava do Core | a Produção: o chip "N un.", "Ver encomendas", "N comprometidas" e as travas de abrir, fechar e reduzir (`PROJ:2988-3023`, `SVC:3476-3547`, `:3871-4016`) |
| Data | a da encomenda | qualquer lote com data **menor ou igual** à do pedido; ganha o criado primeiro (`SYNC:829-845`) |
| Estado | toda reserva de pedido | só pedido aceito, em preparo ou pronto (`SYNC:24`) |
| Data sem lote | demanda sem lote (`Hold.quant=None`) | não existe: sem lote, sem lista |

Três consequências, todas medidas:

1. **A régua B aponta para o lote errado.** A encomenda de amanhã (`NB-261123-B57`) ficou
   ligada ao lote de hoje, que passou a dizer "7 un." e a exigir 7 para fechar. O lote de
   amanhã, que é o que de fato a lastreia, não mostrava nada. Contraria a regra do dono de
   18/11 (a encomenda mede só o lote da data), que a régua A já cumpre.
2. **Onde a régua B trava, a verdade não se registra.** Abrir e fechar abaixo do vinculado
   são recusados sem saída (`SVC:1321-1327`, `:3320-3336`). O chão é impedido de dizer "rendeu
   menos", que é o caso de todo dia.
3. **Onde a régua B não olha, o gesto passa calado.** Zerar a célula e cancelar não consultam
   encomenda nenhuma (`SHOPSVC:846-855`; `SVC:451-494`). O gesto mais destrutivo é o mais livre.

Corrigir tela por tela não fecha. O conserto é a Produção **ler o prometido da régua A, uma
vez, na projeção** (por SKU e data: planejado, encomendado, livre, e os pedidos), e as travas
de encomenda virarem **aviso com a saída pronta**, porque o "Promessa em risco" do Gestor já
existe para resolver pedido a pedido (#2714, #3149).

### 4.2 P0

**P0-1. Zerar a célula do Planejamento cancela o lote, sem a permissão de cancelar e sem
olhar as encomendas.** Lentes: PERM, PROM. **[medido]**

- Prova pela tela: a Cozinha (`diofer`, sem `backstage.void_production`) abriu o Croissant de
  amanhã, "Corrigir quantidade", digitou 0. O botão virou "Remover do plano" (`EV/07`), sem
  uma palavra sobre a encomenda paga. Um toque: "Croissant Manteiga saiu do plano." (`EV/08`).
  No banco: `WO-2026-00034` em `void`, evento `voided` por `production:diofer` com o motivo
  "Planejamento zerado na matriz"; reserva de `order:NB-261123-B57` em `released`, com o
  evento `production_hold_lost` no pedido. O menu do mesmo operador não oferece "Cancelar
  lote…", e a regra da casa é "Cancelar lote é com o gerente" (#2150).
- Causa: `WorkOrderPlanView` pede `can_edit_plan` e `can_edit_planned`, nunca `can_void`
  (`OPS:5773-5790`); `set_planned_quantity` chama `CraftExecution.void` direto quando a
  quantidade é zero (`SHOPSVC:846-855`), com o motivo escrito pelo código. A guarda do pão já
  entregue (#3232) só roda em `apply_void` (`SVC:471`). A trava de encomenda do plano só
  confere a régua B (`SVC:1217-1232`), que não via esse pedido.
- O que já funciona: o Gestor recebe o aviso `order_promise_lost` e o pedido entra em
  "Promessa em risco". O defeito é a Produção cancelar sem autoridade e sem saber.

**P0-2. O lote que rende menos que o encomendado não fecha, e a tela pede um número falso.**
Lentes: PROM, FLUXO. **[medido]**

- Prova pela tela: na Finalização do Croissant (40 previstos, 6 encomendados), Normal 4, o
  motivo digitado, "Confirmar 4 unidades": "Confira a contagem e informe pelo menos 6.000 un.
  Se saiu mesmo menos, nada foi registrado: avise quem cuida das encomendas antes de confirmar
  este lote." Botões: "Cancelar" e "Revisar quantidade", que não faz nada (`EV/05`). O mesmo
  texto na abertura (`EV/03`).
- Causa: o servidor recusa fechado, sem exceção possível: "there is no approved
  partial-allocation contract" (`SVC:3320-3336`, `allow_override=False` em `:3546`; na
  abertura `:1321-1327`). A Finalização não escuta o `review` do diálogo: só liga `@confirm`
  (`FE/pages/close.vue:834-842`; o botão está em `FE/components/ShortageDialog.vue:153-156`).
  A tela de finalizar não mostra o encomendado antes do gesto (`QcCloseScreen.vue` não lê
  `committed_qty`).
- Agravante medido: o piso inclui encomenda de outro dia (4.1, item 1), então o lote de hoje
  pode travar por causa de um pedido de amanhã.
- Ficou obsoleto: desde o #3149 o lote curto vira fato do pedido e o Gestor resolve. A recusa
  hoje só impede a verdade de entrar. O pão assado fica fora do estoque, a loja não o vende, e
  a saída que resta ao operador é digitar 6.
- Depende da decisão 1.

### 4.3 P1 no perímetro

**A promessa**

- **P1-01. Cancelar um lote não diz o que está prometido, e o motivo pode nascer do código.**
  PROM, CONTR. **[medido]** Com 7 un. encomendadas, o diálogo diz só "O lote volta atrás e o
  vínculo com pedidos é desfeito." (`EV/09`; `GRID:2576-2586`). O motivo é texto livre e
  opcional; vazio, a tela grava "Cancelado pelo operador" (`GRID:740`), embora a ação
  projetada declare `confirmation_reason_required` (`PROJ:774-788`). O servidor só recusa
  quando já houve entrega (`SVC:451-478`).
- **P1-02. O chip, "Ver encomendas" e "N comprometidas" leem a régua errada.** PROM, CONTR.
  **[medido]** Ver 4.1. A leitura é do perímetro (`PROJ:2449-2454`, `:2988-3023`, `:3249-3285`);
  o alocador é fronteira (F-01).
- **P1-03. As travas de encomenda contam as linhas seladas do pedido, não o que a produção
  deve.** CONTR. **[código]** `required = sum(item.qty …)` (`SVC:3528-3531`, `:4004-4007`),
  enquanto o alocador desconta o que saiu da prateleira e trata o item editado (`SYNC:612-677`).
  Pedido já servido da vitrine bloqueia abrir e fechar sem motivo.
- **P1-04. O Planejamento afirma "sem encomenda" sem olhar a demanda da data, e a encomenda
  para data sem lote não tem lugar.** COPY, PROM. **[medido o texto, código a causa]** O
  conjunto "+N produtos sem ressalva · insumos ok, sem encomenda…" (`GRID:1749-1756`) usa
  `rowCommittedUnits`, que soma só vínculos de lotes que já existem
  (`FE/presentation/planningRows.ts:46-48`). Linha sem lote tem zero, mesmo com
  `suggestion.committed > 0`, que só aparece dentro do "?" (`FE/presentation/planningReason.ts:162-164`).
  Não há contador por data nem lista de pedidos (`PROJ:1404`, `:3632-3656`).
- **P1-05. Aplicar a sugestão grava "manual", e o porquê não fica com o lote.** CONTR (verdade
  para o B.I.). **[medido]** "Planejar 315" e "Planejar os 13 como sugerido" enviaram
  `"source":"manual"`: quem pode editar o planejado sempre manda manual (`GRID:1089`,
  `:411-419`). O "como sugerido" da tela é comparação feita no navegador. O porquê vive só em
  `meta.formula_basis`, é sobrescrito a cada ajuste e o evento não o leva (`SHOPSVC:896-898`).
  O caminho `suggested` ainda guarda um 500 latente: o `basis` vai cru, com `Decimal` e
  `date`, para um `JSONField` sem encoder (`SHOPSVC:1280-1297`; `CORE/models/work_order.py:128`)
  **[código]**.
- **P1-13. Reduzir o plano abaixo do encomendado devolve o erro do Core cru.** COPY, FLUXO.
  **[código]** A trava do vínculo oferece "Salvar com justificativa" (`SVC:1217-1232`); depois
  a do Core recusa sem exceção (`CORE/services/scheduling.py:332-333`, `:482-506`) e o texto
  sai como `[COMMITTED_HOLDS] Há 12.000 unidades comprometidas em encomendas`, porque
  `_operator_error` não conhece esse código (`SVC:89-91`). O mesmo com
  `[INSUFFICIENT_MATERIALS] Insufficient shared ingredients for rescheduled quantity`.
- **P1-20. O que a Produção vê de uma encomenda é um código e um número.** OMO, PROM.
  **[medido]** "PDV-261123-B72 · Aceito · 3 un." (`EV/10`): sem nome, sem hora de cada pedido,
  sem retirada ou entrega, sem o dia. O chip cola o total à hora do primeiro pedido: "7 un.
  para 9h" (`FE/presentation/production.ts:360-373`; contrato em
  `FE/generated/productionContract.ts:86-92`).

**O chão não para**

- **P1-06. O painel "Quanto está previsto?" esmaga a lista em 1024 px.** UX. **[medido]**
  `EV/02`. No tablet deitado, que é o uso principal, abrir o painel deixa a coluna do produto
  sem largura: os nomes somem e o botão da própria linha é cortado (`GRID:885-894`, `:1924-2044`,
  `:2081`). O #2964 tratou o nome a 1024 px com o painel fechado.
- **P1-07. Toda diferença entre previsto e realizado pede texto digitado.** OMO. **[medido]**
  `EV/04`. Uma unidade basta para abrir a folha, com `NuxtTextarea` obrigatório
  (`FE/components/QcCloseScreen.vue:352-369`, `:927-1001`). A perda, na mesma tela, tem
  motivos de um toque (`:1007-1027`). A decisão de 05/11 pede o motivo; não pede teclado.
- **P1-08. A tela de finalizar não serve em 375 px.** MOB. **[medido]** `EV/15`: teclas de
  36 px de largura (`QcCloseScreen.vue:727-730`, grade `minmax(0,1fr) 12rem` sem ponto de
  quebra). A régua do e2e começa em 390.
- **P1-22. A Finalização e o painel de abertura só sabem contar peça inteira.** CONTR, COPY.
  **[código]** `Math.round` em `FE/pages/close.vue:298-309`; teclado inteiro com teto calado
  de 9999 (`FE/presentation/qc.ts:255-264`); "unidades" e "previstos" sem unidade
  (`QcCloseScreen.vue:423`, `:691`). Os lotes de massa e creme são em gramas com decimais
  (`PROJ:1950`). No sentido contrário, o servidor aceita quantidade fracionada em produto
  contado por peça (`MUT:383`, `:399-403`).
- **P1-25. Fora do tablet deitado, o chão toca em alvos de 32 px e digita no teclado do
  sistema.** MOB, OMO. **[medido]** `EV/23`: em pé e no celular, "Confirmar" abre um modal com
  campo de texto (`GRID:2435-2444`) e passo de 1; "−" e "+" do Planejamento, "Planejar N" e os
  itens planejados têm 32 px (medido na lista de alvos). O teclado da tela só existe no painel
  encaixado (`GRID:2186-2192`).

**A hora e o forno**

- **P1-09. A virada do dia: a grade amanhece em ontem com o rótulo "Hoje", e o lote aberto de
  ontem some.** PROM, FLUXO. **[medido]** `EV/13`. `todayISO` é constante de montagem
  (`GRID:139`; também `FE/pages/mise-en-place.vue:26`, `close.vue:77`, `quality.vue:53`,
  `reports.vue:38`). Só o Letreiro trata a meia-noite (`FE/pages/board.vue:47-53`). No novo
  dia, só a Finalização avisa dos lotes abertos de ontem (`PROJ:2265-2277`); a grade, a
  Preparação e o Letreiro filtram `target_date == data` (`PROJ:1373`, `:2094-2096`, `:4784`).
- **P1-10. Abrir um lote na Finalização grava "retirou do forno", mesmo só navegando.** CONTR.
  **[código]** Com `?lot=` na URL e a ação habilitada, a tela chama `ovenFacts.concluded` e
  apaga o timer (`FE/pages/close.vue:398-443`); o par ‹ › navega por essa rota (`:598-605`).
  Um gesto de leitura virou escrita, com hora carimbada.
- **P1-11. "Finalizar" volta ao painel em silêncio quando a declaração do forno não passa.**
  UX. **[código]** `if (!recorded) { leaveLot(); return; }` (`close.vue:428-431`); o erro só é
  desenhado dentro do diálogo do timer (`:862-867`).
- **P1-12. O timer fica mudo depois de recarregar a página, e vive num dispositivo só.** OMO.
  **[código]** O `AudioContext` nasce só ao armar (`FE/composables/useFloorTimers.ts:161-172`,
  `:210-212`); o timer restaurado do `localStorage` (`:113-133`) vence sem som e a tela não
  avisa. O servidor já sabe que o lote foi enfornado e até quando
  (`FE/composables/useOvenFacts.ts:98-107`), e nenhuma outra tela mostra.
- **P1-16. O lote atrasado mede duração desde a abertura, não a hora prometida.** PROM.
  **[código]** `production_late` conta minutos (`shop/handlers/production_alerts.py:309-349`);
  o lote que nem abriu só vira "esquecido" no dia seguinte (`:352-387`). O Gestor recebe o
  atraso no mesmo dia, pela hora de ficar pronto. A leitura na Produção é do perímetro; o
  alerta é fronteira (F-04).

**Insumo**

- **P1-14. A falta de insumo só é conferida depois do pão assado, e ninguém pode autorizar.**
  PROM, FLUXO. **[código]** `apply_start` não confere insumo (`SVC:1283-1346`); só
  `apply_finish` (`:3339-3357`). `backstage.override_production_shortage` não está em nenhuma
  persona (`config/instances/nelson.json`; `shop/tests/test_group_permission_parity.py:156-160`
  isenta com "D1 pending"). O diálogo oferece só "Cancelar" (`ShortageDialog.vue:139-163`),
  sem link ao Compras, que o "Por quê" já tem (`PlanReasonCard.vue:204-213`). É a #2389 (a).
- **P1-23. A guarda confere a quantidade líquida, e a baixa consome a bruta.** CONTR.
  **[código]** `SVC:4147-4160` contra `CORE/services/execution.py:440-459`. Com fator de
  aproveitamento menor que 1, a guarda passa e a baixa falha com "O lote não foi fechado
  porque o estoque falhou" (`SVC:55-58`), sem nomes.
- **P1-24. Autorizar a falta pede "quem autorizou" em texto livre.** PERM. **[código]**
  `ShortageDialog.vue:123-133`; o desvio de fórmula repete
  (`AuthorizeFormulaDeviationDialog.vue:234-245`). A regra da casa de 28/10 é gerente da
  lista, com o próprio PIN.

**Tempo real e estados**

- **P1-17. "Ao vivo" é dito por quase toda tela, e só a grade tem push.** COPY, CONTR.
  **[código]** O selo aparece sempre que não há dado velho (`ProductionHeader.vue:142-181`);
  a grade calcula `realtime` e ninguém lê (`useProductionBoard.ts:80-82`, `:292`). O resto é
  poll: Finalização e Qualidade 30 s (`useQcKiosk.ts:54`), Letreiro 30 s, Preparação 60 s,
  avisos 60 s. O canal `/sse/production` já existe.
- **P1-18. Finalização e Qualidade ficam em branco se a primeira leitura falha.** FLUXO.
  **[código]** Não há ramo para `error && !kiosk` (`close.vue:652-669`, `quality.vue:396-407`);
  a grade tem (`GRID:1428-1434`).

**Preparação**

- **P1-19. O "Separado" mora no dispositivo, some com qualquer mudança da tela e não existe na
  lente padrão.** FLUXO, MOB. **[medido a caixa e a chave, código o resto]** Caixa de 16 px
  (`EV/22`); chave `preparacao:v2:<estação>:<data>:active-revision` no `localStorage`. O
  digest é o hash da projeção inteira (`shopman/backstage/api/projections.py:79-93`), então
  marcar "Mostrar ingredientes dos pré-preparos" ou uma entrada de estoque apagam as marcas,
  com a frase "O planejamento mudou" (`mise-en-place.vue:252-260`). A lente padrão, "Por
  preparo", não marca nada (`:467-563`). "Falta" não diz quanto nem o que fazer (`:370-379`).
- **P1-26. As etiquetas de pesagem ignoram o "Com massa velha" da tela.** CONTR. **[código]**
  O interruptor muda só o cartão (`FE/presentation/weighing.ts:108-141`); o papel sai de
  `ticket.ingredients` cru (`mise-en-place.vue:132-147`). Quem pesa pela etiqueta pesa outra
  receita.

**Letreiro, sino e estação**

- **P1-21. O Letreiro não se lê a dois metros e crava "UN".** UX, COPY. **[medido]** `EV/18`:
  linhas em 24 px em 1920 × 1080 (`board.vue:300`, teto do `clamp`); `${qty} UN` para massa em
  quilo (`FE/presentation/production.ts:475-478`); título "Lotes", "sem sinal" em 0,78rem
  (`board.vue:326-332`); o relógio anda com dado velho, sem "lido às".
- **P1-15. O sino da Produção fala de pedido e manda ao Gestor.** FLUXO, COPY. **[medido]**
  `EV/20`: a Cozinha lê "Pedido ficou sem a produção prometida… Abrir o pedido" e "Produção
  WO-2026-00028 (MDLN) está há 1047 min em andamento · pedido WO-2026-00028". O aviso
  "Planeje mais N" é da Produção e o botão dele leva ao pedido no Gestor
  (`backstage/projections/alerts.py:180-192`, `:528-535`). A casa do aviso é fronteira (F-03).
- **P1-27. A estação autônoma do Letreiro pode mutar em nome do totem.** PERM. **[código]**
  A conta do totem vale para toda rota sob `/api/v1/backstage/production/`
  (`backstage/station_trust.py:83`, `:351-375`), e as mutações moram ali. O teto
  `PRODUCTION_TRUSTED_STATION_CAPABILITIES` não é definido em lugar nenhum (`PROJ:4433-4438`).
  Se o totem estiver no grupo Cozinha, o tablet sem PIN planeja, abre e fecha.
- **P1-28. A etiqueta do lote identifica o produto, não o lote.** CONTR. **[código]** O QR é
  `shopman-lote:<SKU>` e abre o primeiro lote aberto daquele SKU
  (`FE/presentation/production.ts:334-357`). Com dois lotes do mesmo produto no dia, a
  etiqueta do segundo abre o primeiro.

**Conserto**

- **P1-29. O total digitado errado no fechamento não tem conserto.** CONTR. **[código]** A
  correção de qualidade mantém o total (`SVC:3047`), cancelar lote fechado é recusado
  (`:72-73`) e não existe reabrir. O conserto mexe no estoque (F-13).
- **P1-30. "Ir para o Planejamento" leva a amanhã depois do meio-dia.** FLUXO. **[código]**
  O vazio da Produção liga para `/plan` sem data (`GRID:1483-1488`), que abre em amanhã a
  partir das 12h (`useProductionBoard.ts:48-52`).

### 4.4 P2 no perímetro

| # | Achado | Lente | Prova |
|---|---|---|---|
| P2-01 | A sugestão chega a 6 a 9 vezes o plano (Croissant 374 no sábado, 282 na terça, contra 42) sem teto de capacidade; "Acabou às 11h em 4 dos últimos 4 terças" | PROM, COPY | **[medido]** `EV/11`, `EV/12`; depende do seed (F-09) |
| P2-02 | "Planejar os N como sugerido" envia um por um, com uma releitura a cada item (cerca de 4 s por produto na pilha) | UX | **[medido]**; `GRID:1161-1184` |
| P2-03 | "un." e o feminino cravados nos diálogos; "6.000 un." com casas decimais | COPY | **[medido]** `EV/03`; `GRID:842`, `:2129`, `:2417`, `:2689` |
| P2-04 | Um conceito, vários nomes: lote, "OP", "Ordens", "ordem de produção"; Letreiro, "Lotes", "painel"; "QC"; "fournil" | COPY | `reports.vue:182-205`, `board.vue:181`, `close.vue:271`, `timers.vue:73` |
| P2-05 | Relatórios: datas "2026-11-17", "producao", "chef:ana", "Tempo (min)", grandezas somadas ("77 un. · 159,65 kg") | COPY | **[medido]** `EV/21` |
| P2-06 | Travessão como valor vazio, e zero escondido atrás dele | COPY | `GRID:947-949`, `:1995`; `reports.vue:293-547` |
| P2-07 | Dado velho avisado em pílula solta, sem X | UX | `GRID:1438-1446`, `close.vue:642-650`, `quality.vue:386-394` |
| P2-08 | Digitar só no grau padrão não conta como alteração: "rendeu 18" some ao Voltar | UX | `QcCloseScreen.vue:525-532` |
| P2-09 | Dois toques num grau levam o lote inteiro para ele | UX | `QcCloseScreen.vue:303-337` |
| P2-10 | "Realizado 26 de 26" com 2 de perda | COPY | **[medido]** `EV/15` |
| P2-11 | Depois de finalizar, a tela pula para o próximo lote, mesmo um que nem foi aberto, e a Finalização lista "ainda não aberto" com "Finalizar" | FLUXO | **[medido]** |
| P2-12 | "Lote enviado para Qualidade (QC)."; "Somar 1 minutos"; "Planejado: Madeleine × 315" | COPY | **[medido]** |
| P2-13 | Na Produção, o lote fechado some e o progresso encolhe | UX | `GRID:193-195`, `:964-970` |
| P2-14 | A Qualidade troca de dia pelo menu de três pontos; as outras etapas, pelo seletor | UX | `quality.vue:118-134` |
| P2-15 | Letreiro: nome cortado em 22 letras; relógio no fuso do dispositivo | UX | `board.vue:110`, `:72-76` |
| P2-16 | "Perda" tem duas contas: previsto menos realizado no cartão e nos relatórios, só as linhas de perda na gestão do dia | CONTR | `PROJ:2991-2996`, `:3361-3363` contra `:2016-2028` |
| P2-17 | Abertura implícita grava início igual ao fim, e a produtividade faz média com duração zero; agrupa pelo nome declarado, não por quem tocou | CONTR | `CORE/services/execution.py:390-411`; `PROJ:3392-3413` |
| P2-18 | Não há trava de data: planeja, abre e fecha em data passada ou em dia já selado | PERM | `PROJ:4419`; `MUT:383` |
| P2-19 | Texto do servidor com SKU cru e jargão ("A mutação exige operador, revisão e chave idempotente", "…preservado para retry") e erro de campo fora do dialeto `{detail, field, errors}` | COPY, CONTR | `SVC:129-130`, `:352`, `:1116`; `MUT:287-301` |
| P2-20 | Receitas: erro na primeira leitura de "Conferir" sem "Tentar de novo"; comparar versões por número, sem dizer qual é a publicada; a nota do item não aparece (#2386) | UX | `recipes/review.vue:50-60`, `compare.vue:110-119`; `projections/recipe_book.py:197-216` |
| P2-21 | Nenhuma página usa `<MoreBelow />`; leitura de chaves antigas do `localStorage`; fundo branco fixo em dois diálogos | UX, CONTR | grep vazio; `useFloorTimers.ts:50-52`; `RegisterOldDoughDialog.vue:142` |

### 4.5 Reclassificados (não são defeito)

- **Etapas da receita sem carimbo de hora.** O verbo existe no Core e a Produção não o chama
  (`CORE/services/execution.py:197-285`). As etapas saíram do fluxo do chão por decisão de
  16/09 ("se obrigar engessa"). Vira a decisão 4, não achado.
- **Timer só no dispositivo.** Decisão de 16/09 e 18/09: timer é lembrete. O P1-12 trata o
  som e a visibilidade, não a natureza.
- **O Dono não entra na Produção** (`nelson.json`). Os "relatórios com valor agregado" do
  brief não existem no app: a margem por fornada mora só no B.I. É o desenho certo para a
  regra de 21/11 (Gerente não vê agregado financeiro). Os relatórios da Produção não têm
  custo nem receita (conferido em `EV/21`).
- **"Revisar quantidade" depois de recusa de plano** foi apontado na leitura como 409 por
  chave reusada (`useProductionBoard.ts:144-196`). Na abertura, medido, funciona. No plano não
  foi exercitado: fica como caso de teste do WP-F14.

## 5. Fronteiras (registrar, não mexer)

| # | O que é | Por que afeta a Produção | De quem é | Quem mais sente |
|---|---|---|---|---|
| F-01 | O alocador pedido × lote aceita lote de data anterior e escolhe o criado primeiro (`SYNC:829-845`; teste que consagra em `backstage/tests/test_production_order_sync.py:1115-1134`) **[medido]** | a régua B aponta para o lote errado e trava o fechamento de hoje por pedido de amanhã | `shop` | Gestor, Cozinha |
| F-02 | A reserva solta no cancelamento não volta quando o lote é replanejado (`RECV:86-93`; `shop/services/demand_anchor.py:50-55`) **[medido]** | "Remover do plano" e "Planejar" de novo deixam a encomenda paga sem reserva e o pão novo livre para outro | `shop` | Gestor, loja, PDV |
| F-03 | O aviso `order_demand_over_plan` é da Produção e não tem casa em `_ALERT_HOMES`; o sino da Produção mostra avisos de pedido com "Abrir o pedido"; "pedido WO-…"; minutos crus (`backstage/projections/alerts.py:180-192`, `:528-535`) **[medido]** | o gesto mora em `/plan?date=`, e o botão leva a outro app | backstage (sino compartilhado) | todos os apps de operador |
| F-04 | `production_late` mede minutos desde a abertura; lote não aberto só vira "esquecido" no dia seguinte (`shop/handlers/production_alerts.py:309-387`) | o Gestor sabe do atraso antes da Produção | `shop` | Gestor |
| F-05 | "Fica pronto às" vem do cadastro e da mediana de 30 dias da hora do toque (`shop/services/product_readiness.py:101-235`) | o atraso de hoje não muda a loja hoje; fechar lotes em bloco desloca a promessa por um mês | `shop` | loja, PDV, Gestor (#2560) |
| F-06 | O cliente segue lendo "Pedido garantido" depois do lote cancelado (`storefront/presentation/order_tracking.py:1124`) | a promessa quebrada não chega a quem pagou; nada é automático por desenho | Storefront | cliente |
| F-07 | O histórico de demanda conta a venda no dia em que o pedido foi criado, não no da entrega (`CORE/contrib/demand/backend.py:63-76`); N+1 do `_expand_bom` (#2354, #2351) | encomenda feita na segunda para sábado ensina segunda | Core (craftsman) | B.I. |
| F-08 | O validador de insumo do Core usa a quantidade líquida, e `adjust` valida enquanto `plan` não (`CORE/services/scheduling.py:521-613`) | metade do P1-23 | Core (craftsman) | - |
| F-09 | Seed: lote gravado como produzido sem baixar insumo (#2339); peças sem lote futuro (#2955); "Fechados por Diofer entre 0h09 e 23h59"; série de vendas que dá sugestão de 6 a 9 vezes o plano; aviso "sementes de validação: manteiga francesa…" | distorce a jornada 3 e o P2-01 na pilha | seed (`config`) | toda revisão em pilha |
| F-10 | Concessões do descritor: ninguém tem `override_production_shortage`, `quick_finish_production` nem `reveal_production_blind_map` (D1 pendente); não há persona só de leitura para o totem | P1-14 e P1-27 | `config/instances/nelson.json` | - |
| F-11 | O que falta **gravar** para o B.I. ler: o porquê da sugestão em todo plano, por append; os pedidos afetados no evento de cancelamento (`SYNC:726` os apaga); qual forno de verdade (hoje é a posição do lote, `SVC:1885`); perda e "rendeu menos" lidos em separado; lotes cancelados e motivos (`bi_production.py` só lê fechados); o ator do gesto | o B.I. aprende com dado incompleto | a Produção grava (WP-F17 e WP-F07 cobrem os dois primeiros); o B.I. lê | B.I. |
| F-12 | `operator-kit`: alvo padrão de 32 px (`operator-theme.css:22`); o convite "Vincular este dispositivo…" aparece para a Gerente dizendo que não há posto para o app; a Cozinha recebe 403 em `/operator/station/?surface=production` a cada tela; "Hydration completed but contains mismatches" no console **[medido]** | ruído na abertura de toda tela | `operator-kit` | todos os apps de operador |
| F-13 | Corrigir o total de um lote fechado mexe no ledger de estoque | P1-29 | Stockman e `shop` | loja, PDV |
| F-14 | `docs/reference/glossary.md:51-52` (Abertura e Fechamento) e o brief desta revisão (vocabulário de 16/09) | quem lê o doc escreve a palavra proibida pela trava | docs | - |
| F-15 | #2721 item 11: com um lote aberto, cancelar outro do mesmo SKU e dia pode soltar reserva que o aberto cobriria | "lido, não executado" na issue; reproduzir na J-P3 | `shop` | Gestor |
| F-16 | Compras: o link do "Por quê" vai à casa do Compras, não ao insumo (#2392) | P1-14 | Compras | - |

## 6. O salto

| # | Ideia | Ganho para quem usa | Custo |
|---|---|---|---|
| S1 | **A fornada responde.** No gesto (abrir, fechar, reduzir, cancelar), a Produção mostra quem fica sem pão, pelo nome e pela hora, e fecha com a verdade: "Rendeu 4 de 40. Três encomendas ficam descobertas (Marina 9h, …). Fechar com 4 e avisar o Gestor." O Gestor já tem o "Resolver" | o padeiro nunca mais digita número falso nem atravessa a loja para avisar; a Caixa sabe antes do cliente | WP-F01, F06, F07 e F10. Nenhum dos onze benchmarks faz |
| S2 | **Uma régua só, à vista antes de assar.** Por produto e data: planejado, encomendado e livre, da mesma leitura da loja e do PDV, inclusive em data sem lote ("Sábado: 12 Croissants encomendados, nenhum lote. Planejar 12") | "a Produção sabe, antes de assar, o que já está prometido"; o pedido à Produção ganha um lugar | WP-F08, F10, F13 |
| S3 | **O porquê em uma frase, e gravado.** Na linha: "42 = 6 encomendas + 30 de balcão + 6 de margem". No lote: sugerido, planejado, previsto e realizado, por append | o padeiro confia ou corrige em um relance; o B.I. aprende onde a casa discorda da conta | WP-F17 |
| S4 | **Chão sem teclado, em qualquer tablet.** Todo número pelo teclado da tela, todo motivo em um toque, o "Separado" valendo para a bancada inteira, o forno visível em toda tela ("no forno até 5h40") | luva e farinha não param o trabalho; trocar de tablet não perde nada | WP-F03, F09a, F09b, F12, F20 |
| S5 | **O Letreiro como painel de embarque de verdade.** Lido a dois metros, com o que cada lote lastreia ("12 encomendas às 9h") e o atraso medido contra a hora prometida | a equipe inteira vê a manhã de relance, e o que está em risco | WP-F04 e o lado de fronteira F-04 |

## 7. WPs

Regras comuns a todos:

- Cada WP cabe numa **sessão Opus 5.5 em esforço médio**, um branch e um PR. O brief aponta o
  que ler; o CLAUDE.md da raiz vale inteiro e não se repete aqui.
- A sessão segue a seção **"Teste como um operador de verdade"** de
  `docs/coordination/ROUNDS/EXCELENCIA-base.md`: pela UI, com o papel do roteiro (Cozinha
  `diofer` ou Gerente `joyce`, com PIN), nunca como superusuário, sem atalho de API, Admin ou
  banco, em tablet deitado (1024 × 768), 375 px e 1366 px.
- Como subir a pilha: a seção 1 deste plano e `surfaces/orders-nuxt/tests/operator/README.md`
  (a Produção sobe com `NUXT_SHOPMAN_ENVIRONMENT=test` e
  `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1`). Use portas e banco próprios.
- WP que muda tela mostra **prévia local ao dono antes de enfileirar**, auditada por script.
- WP que muda contrato regenera `app/generated/productionContract.ts`
  (`manage.py export_production_schema`) e commita os dois lados juntos.
- Vocabulário: `docs/reference/suite-vocabulary.md:69` e a trava
  `tests/lifecycleVocabulary.test.ts`. Na tela é **lote**; planejado, previsto, realizado.
- Mexeu em tela: rode também a suíte do `operator-kit` (as travas dele auditam os apps) e a
  suíte de navegador do app, que só roda na fila.
- Fora de todos: `packages/`, `shop/`, o `operator-kit`, o B.I., o Compras, a Cozinha.
- `OPS` (`api/operations.py`) é arquivo compartilhado com o Gestor: o WP que o toca mexe só
  nas views de produção.

Tamanhos: P (até meio dia) · M (um dia).

---

### WP-F00 · Harness de operador de verdade

- **Objetivo:** a Produção ganha uma suíte Playwright contra o Django da pilha, com login e
  PIN de verdade, e a jornada J-P1 nasce nela.
- **Achados que fecha:** a lacuna dos e2e (hoje só contra mock, `tests/e2e/README.md`).
- **Dependências:** nenhuma.
- **Arquivos:** `surfaces/production-nuxt/playwright.operator.config.ts` (novo),
  `tests/operator/**` (novo), `package.json` (script `test:operator`), `tests/e2e/README.md`.
- **Fora do escopo:** o CI; os e2e de mock, que continuam.
- **Pronto quando:**
  - roteiro: a Gerente libera o dispositivo; a Cozinha entra com PIN, confirma o previsto de
    um lote, finaliza com 2 de perda e um motivo; a Gerente confirma na Qualidade; o produto
    aparece disponível na loja. Capturas em 1024 e 375.
  - testes: `npm run test:operator` verde, com a J-P1 escrita com os mesmos papéis e passos.
- **Muda tela:** não. **Tamanho:** M.
- **Brief:** leia "Teste como um operador de verdade" na base, a seção 1 deste plano e
  `surfaces/orders-nuxt/tests/operator/` (README, `playwright.operator.config.ts` e
  `support/`). Reuse os gestos de `surfaces/operator-kit/tests/support/operatorGestures.ts`
  (login, bloqueio, PIN, dispositivo novo). A suíte recusa rodar sem as variáveis da pilha. O
  estado nasce pela tela, nunca por API. Escreva a J-P1 e o README de como subir a pilha.

### WP-F01 · Zerar não cancela (servidor)

- **Objetivo:** tirar um lote do plano passa a exigir a permissão de cancelar e as mesmas
  guardas do cancelamento.
- **Achados que fecha:** P0-1 (o lado do servidor).
- **Dependências:** nenhuma.
- **Arquivos:** `OPS` (só `WorkOrderPlanView`), `SVC` (`apply_planned`), testes em
  `shopman/backstage/tests/test_api_production_surface.py`.
- **Fora do escopo:** a tela (WP-F07); `SHOPSVC` e o Core.
- **Pronto quando:**
  - roteiro: a cliente encomenda pela loja para amanhã e paga, a Caixa aceita. A Cozinha abre
    o Planejamento de amanhã, corrige para 0 e é recusada com "Cancelar lote é com o gerente."
    O lote e a reserva seguem intactos. A Gerente faz o mesmo e o lote sai, com motivo.
  - testes: zero sem `can_void` devolve 403; zero em lote com pão entregue cai na guarda do
    #3232; o motivo gravado é o que a pessoa deu, nunca texto do código.
- **Muda tela:** não (a mensagem chega pelo caminho de erro que já existe). **Tamanho:** P.
- **Brief:** leia o P0-1. Em `apply_planned`, quantidade zero sobre lote existente segue o
  caminho de `apply_void` (`SVC:451-494`): exige `can_void`, roda
  `_refuse_void_with_deliveries` e leva o motivo do operador. A view passa a pedir a
  capacidade quando a quantidade é zero. Não crie guarda de encomenda aqui: o aviso é do
  WP-F07.

### WP-F02 · Desmontar a grade

- **Objetivo:** `ProductionStageGrid.vue` deixa de ser um arquivo de 2.741 linhas e vira uma
  grade que orquestra componentes, sem mudar nada do que a tela faz.
- **Achados que fecha:** nenhum direto; abre caminho para os WPs que hoje disputam o mesmo
  arquivo.
- **Dependências:** nenhuma.
- **Arquivos:** `GRID` e os componentes novos `LotCancelDialog.vue`, `PlanAdjustDialog.vue`,
  `LotStartPanel.vue` (o painel e o modal de "Quanto está previsto?"),
  `LotCommitmentsDialog.vue` e `PlanLens.vue` (os conjuntos do Planejamento).
- **Fora do escopo:** qualquer mudança de comportamento, de copy ou de layout.
- **Pronto quando:**
  - roteiro: a Cozinha planeja, corrige, abre e vê encomendas; a Gerente cancela. As capturas
    de antes e depois são iguais em 1024, 375 e 1366.
  - testes: a suíte de componentes e a de navegador do app verdes sem tocar em nenhuma
    asserção; nenhuma string de tela muda (diff de textos vazio).
- **Muda tela:** não. **Tamanho:** M.
- **Brief:** refatoração pura. Extraia cada diálogo com as props e os eventos que ele já usa;
  o estado segue na grade. Não renomeie texto nem classe. Se um teste precisar mudar, pare e
  diga por quê no PR.

### WP-F03 · Finalizar sem teclado, e em 375 px

- **Objetivo:** fechar um lote nunca pede digitar, e cabe no celular.
- **Achados que fecha:** P1-07, P1-08, P1-22 (o lado da Finalização), P2-08, P2-09, P2-10.
- **Dependências:** nenhuma.
- **Arquivos:** `FE/components/QcCloseScreen.vue`, `FE/presentation/qc.ts`, testes de
  componente e `tests/qc.test.ts`.
- **Fora do escopo:** a recusa por encomenda (WP-F06); `close.vue`.
- **Pronto quando:**
  - roteiro: a Cozinha fecha um lote que rendeu 2 a menos escolhendo um motivo em um toque;
    fecha um lote de massa em quilos com vírgula; repete tudo em 375 px com teclas de pelo
    menos 44 px. Capturas nos três tamanhos.
  - testes: componente (motivos de um toque, unidade do lote, layout de uma coluna abaixo de
    640 px) e a régua do e2e baixando para 375.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia P1-07, P1-08 e a decisão de 05/11 em #2150 (o motivo é pedido; a forma não
  foi decidida). Use para "rendeu menos" e "rendeu mais" o mesmo desenho dos motivos da perda
  (`QcCloseScreen.vue:1007-1027`), com "Outro" abrindo o texto. A lista de motivos nasce no
  seed e é editável onde a de perda é. A tela recebe a unidade do lote e diz "Realizado" só
  do que é vendável.

### WP-F04 · Letreiro a dois metros

- **Objetivo:** o Letreiro se lê de longe numa TV e diz a unidade certa.
- **Achados que fecha:** P1-21, P2-15.
- **Dependências:** nenhuma.
- **Arquivos:** `FE/pages/board.vue`, `FE/components/SplitFlap.vue`,
  `FE/presentation/production.ts` (`formatBoardQty`), `PROJ` (só `ForecastRowProjection`),
  contrato gerado.
- **Fora do escopo:** alertas na TV (#2420 segue como está); o que cada lote lastreia (fica
  para depois do WP-F08).
- **Pronto quando:**
  - roteiro: a estação autônoma abre o Letreiro em 1920 × 1080 e em tablet; uma pessoa lê
    produto, quantidade, hora e situação a dois metros (foto do monitor no PR); massa aparece
    em kg; sem conexão, o aviso é a maior coisa da tela e diz "lido às".
  - testes: `boardDisplay.test.ts` com a unidade e a escala; visual em 1920 e 1024.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia P1-21 e `docs/plans/PRODUCTION-FORECAST-BOARD-PLAN.md`. A escala cresce com
  a altura da tela, não com teto de tablet. O título é "Letreiro" ou nenhum. A unidade vem na
  projeção.

### WP-F05 · Receitas que se leem

- **Objetivo:** a nota do item aparece, comparar versões diz qual é qual, e o vazio da busca
  de insumo leva ao Compras.
- **Achados que fecha:** P2-20; issues #2386, #2387 (fatia 2), #2390.
- **Dependências:** nenhuma.
- **Arquivos:** `FE/pages/recipes/**`, `FE/components/IngredientPicker.vue`,
  `FE/presentation/recipeBook.ts`, `shopman/backstage/projections/recipe_book.py`, contrato
  gerado.
- **Fora do escopo:** importar tabelão (#2393); série materializada e `bi_production` por
  versão (#2387, fatia 3).
- **Pronto quando:**
  - roteiro: a Gerente cria uma receita, publica, edita e compara as duas versões lendo qual é
    a publicada e de quando; lê a nota "a conferir" de um item; busca um insumo que não existe
    e toca "Abrir o Compras". A Cozinha só lê. Capturas em 1366 e 375.
  - testes: projeção (nota e uso por versão), componentes, e a J-P9 contra o Django.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia as issues #2386, #2387 e #2390 e a D-012 em `DECISIONS.md`. O dado de uso
  por versão já existe (`recipe_book.py:591`, `:1593`) e a tela não o lê.

### WP-F06 · O lote curto fecha com a verdade

- **Objetivo:** o lote que rendeu menos que o encomendado fecha com o número real, e a tela
  diz antes quem fica descoberto.
- **Achados que fecha:** P0-2, P1-03.
- **Dependências:** decisão 1; WP-F01 no `main` (mesmo `SVC`).
- **Arquivos:** `SVC` (as guardas de abrir e fechar), `FE/components/ShortageDialog.vue`,
  `FE/pages/close.vue`, testes do service e da superfície.
- **Fora do escopo:** quem recebe o pão que rendeu (a ordem é do `shop`, `PLAN` do Stockman);
  avisar o cliente.
- **Pronto quando:**
  - roteiro: com 6 un. encomendadas e aceitas, a Cozinha finaliza o lote com 4. A tela diz
    "Rendeu 4. Faltam 2 para as encomendas" com os pedidos, e o botão é "Fechar com 4 e avisar
    o Gestor". O lote fecha, o estoque entra, e a Caixa vê os pedidos em "Promessa em risco"
    no Gestor. Capturas da Produção e do Gestor.
  - testes: fechar e abrir abaixo do encomendado deixam de recusar e registram o evento; a
    conta usa o que a produção deve, não as linhas seladas; a J-P4.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia o P0-2, a seção 4.1 e `shop/services/production_promise.py:199-241`
  (`announce_short_lot`, #3149). A recusa vira confirmação informada: o servidor devolve o
  envelope com os pedidos e uma possibilidade "confirmar"; a segunda chamada fecha. Confira
  pela tela que o Gestor recebe o fato; se não receber para pedido vinculado, pare e registre
  como fronteira.

### WP-F07 · Cancelar e remover dizem o que está em jogo

- **Objetivo:** quem cancela ou tira um lote do plano lê, antes de confirmar, quantas
  unidades e quais pedidos dependem dele, e dá o motivo em um toque.
- **Achados que fecha:** P0-1 (a tela), P1-01.
- **Dependências:** WP-F01 e WP-F02 no `main`.
- **Arquivos:** `LotCancelDialog.vue`, `PlanAdjustDialog.vue`, testes de componente.
- **Fora do escopo:** a leitura pela régua das reservas (WP-F08 e F10): aqui usa o que o
  cartão já traz.
- **Pronto quando:**
  - roteiro: a Gerente abre "Cancelar lote…" num lote com encomenda e lê "7 un. encomendadas:
    4 pedidos" antes do botão; escolhe o motivo; cancela. A Cozinha digita 0 e lê "Cancelar
    lote é com o gerente." no lugar do botão. Capturas em 1024 e 375.
  - testes: componente (o aviso com e sem encomenda; o motivo obrigatório; sem permissão não
    há botão); a J-P3.
- **Muda tela:** sim (prévia). **Tamanho:** P.
- **Brief:** leia P0-1 e P1-01. O motivo nunca nasce do código (`GRID:740` morre). Os motivos
  de um toque saem de uma lista curta com "Outro".

### WP-F08 · Uma régua só (servidor)

- **Objetivo:** a projeção da Produção publica, por produto e data, o prometido lido das
  reservas: planejado, encomendado, livre e os pedidos.
- **Achados que fecha:** P1-02 e P1-20 (o contrato), P1-04 (o dado).
- **Dependências:** nenhuma.
- **Arquivos:** `PROJ` (matriz e cartão), `FE/generated/productionContract.ts`,
  `FE/presentation/production.ts` (os tipos e o formato do chip), testes de projeção.
- **Fora do escopo:** o alocador (`SYNC`, F-01); as travas (WP-F06); a tela (WP-F10).
- **Pronto quando:**
  - roteiro: a cliente encomenda para amanhã e paga, a Caixa aceita. Pela API da projeção
    lida pela tela (sem mudança visual ainda), o lote de AMANHÃ traz 1 un. e o pedido, com
    nome curto, hora e retirada ou entrega; o de hoje não. Uma data sem lote traz a demanda.
  - testes: projeção com encomenda na data, em outra data, em data sem lote, acima do plano e
    paga ainda não aceita; contrato regenerado.
- **Muda tela:** não. **Tamanho:** M.
- **Brief:** leia a seção 4.1. A fonte é a mesma leitura que o PDV usa
  (`shop/adapters/stock.py:879-907`, `planned_on_date`, e as reservas de pedido da data),
  chamada por um adapter que já exista; não escreva consulta nova ao Stockman na projeção. O
  campo antigo do vínculo continua até o WP-F10 trocar a tela, e some junto (sem legado).

### WP-F09a · O "Separado" no servidor (#3524)

- **Objetivo:** a marca de "Separado" da Preparação passa a morar no servidor e vale para
  todos os tablets do dia (D-042, item 5).
- **Achados que fecha:** P1-19 (o lado do servidor).
- **Dependências:** nenhuma (decisão 5 respondida: servidor).
- **Arquivos:** só arquivos novos, mais o registro deles: `shopman/backstage/models/prep_checklist.py`
  (e `models/__init__.py`), a migração seguinte do `backstage`,
  `shopman/backstage/services/prep_checklist.py`, `shopman/backstage/api/production_checklist.py`
  (e a rota em `api/urls.py`), o Admin só leitura, testes.
- **Fora do escopo:** a tela (WP-F09b); `PROJ` e `SVC` (são de F08 e F06 nesta onda): a marca
  tem leitura e escrita próprias, ao lado da projeção da Preparação, sem entrar nela.
- **Pronto quando:**
  - roteiro: pela API que a tela vai usar, com a sessão de um operador da Cozinha com PIN,
    marcar e desmarcar três insumos do dia; ler de outro dispositivo (outro contexto de
    navegador) e ver as mesmas marcas, com quem marcou e a hora. A conferência pela tela fica
    com o F09b.
  - testes: marca por dia e por item (insumo, ou ingrediente de um preparo), presa à
    quantidade do momento; a marca cai quando a quantidade daquele item muda, e só então; quem
    marcou é o operador do PIN; desmarcar grava, não apaga a história; dois tablets marcando o
    mesmo item ao mesmo tempo dão um resultado só; a mudança emite o evento de produção que a
    grade já ouve (SSE, ADR-016); a estação autônoma do Letreiro não escreve.
- **Muda tela:** não. **Tamanho:** M.
- **Brief:** leia o P1-19, a D-042 (item 5 e "a regra que o item 5 deixa") e o ADR-016. Hoje a
  marca vive em `FE/composables/useMiseEnPlace.ts`, presa ao hash da projeção inteira, e por
  isso some sozinha. A chave da marca é o item e a data, nunca o hash. Confira a numeração da
  migração contra o `main` e os PRs abertos antes de abrir o PR. Permissão: a mesma de operar
  a Preparação; o Letreiro só lê.

### WP-F09b · Preparação que lembra, a tela (#3525)

- **Objetivo:** a tela da Preparação usa a marca do servidor, ela existe também na lente de
  pesagem, e a falta diz quanto e o que fazer.
- **Achados que fecha:** P1-19 (a tela), P1-26.
- **Dependências:** WP-F09a no `main`.
- **Arquivos:** `FE/pages/mise-en-place.vue`, `FE/composables/useMiseEnPlace.ts`,
  `useWeighing.ts`, `FE/presentation/weighing.ts`, `WeighingLabels.vue`, testes.
- **Fora do escopo:** sessão de pesagem com balança (D5 do plano de 08/09).
- **Pronto quando:**
  - roteiro: a Cozinha marca três insumos no tablet A; o tablet B, aberto na mesma tela, mostra
    as três marcas sem recarregar; liga "Mostrar ingredientes dos pré-preparos" e as marcas
    ficam; marca os ingredientes de uma massa na lente "Por preparo"; imprime a etiqueta com
    "Com massa velha" ligado e o papel traz o mesmo peso da tela; num insumo em falta lê
    "Faltam 300 g" com "Pedir no Compras". Capturas em 1024 e 375.
  - testes: o composable lê e grava pelo servidor (sem `localStorage` para a marca; a chave
    antiga some, sem leitura de legado); alvo de 44 px; a frase "as marcações ficam somente
    neste dispositivo" sai.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia P1-19, P1-26 e a D-042. A regra do pré-preparo continua: nunca mostra saldo
  nem falta (decisão de 03/07). Marcação otimista na tela, desfeita com aviso se o servidor
  recusar.

### WP-F10 · O prometido na tela

- **Objetivo:** o chip, "Ver encomendas" e "N comprometidas" passam a dizer o que a régua das
  reservas diz, com nome e hora.
- **Achados que fecha:** P1-02, P1-20 (a tela), P1-04 (o rótulo "sem encomenda").
- **Dependências:** WP-F08 e WP-F02 no `main`.
- **Arquivos:** `GRID` (a linha), `LotCommitmentsDialog.vue`,
  `FE/presentation/planningRows.ts`. O "N comprometidas" da Finalização troca de fonte no
  WP-F12, que é o dono de `close.vue` na onda.
- **Fora do escopo:** a faixa de datas sem lote (WP-F13).
- **Pronto quando:**
  - roteiro: com a encomenda de amanhã aceita, a Cozinha vê o chip no lote de amanhã ("1 un.
    · amanhã 9h") e nenhum no de hoje; abre a lista e lê "Clara · retirada · 9h · 1 un.". O
    conjunto do Planejamento só diz "sem encomenda" quando não há demanda na data. Capturas em
    1024 e 375.
  - testes: apresentação (o chip nunca soma total com a hora do primeiro pedido), componente.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia 4.1 e P1-20. Uma grandeza por rótulo (`docs/reference/omotenashi-copy.md`).
  A Produção vê o primeiro nome e a hora, nunca valor em dinheiro.

### WP-F11 · Falta de insumo com saída

- **Objetivo:** a falta é dita ao abrir o lote, com o nome e a quantidade, e ao fechar tem
  uma saída que não é texto livre.
- **Achados que fecha:** P1-14, P1-23, P1-24; issue #2389 (a).
- **Dependências:** decisão 3; WP-F06 no `main` (mesmos `SVC` e `ShortageDialog.vue`).
- **Arquivos:** `SVC` (`apply_start`, `_material_needs_for_work_order`),
  `ShortageDialog.vue`, `PROJ` (a checagem da sugestão), testes.
- **Fora do escopo:** o validador do Core (F-08); a concessão no descritor (F-10), que é a
  decisão 3.
- **Pronto quando:**
  - roteiro: com um insumo abaixo do necessário (entrada dada pelo Compras, pela tela), a
    Cozinha confirma o previsto e lê "Falta 300 g de manteiga" com "Pedir no Compras" e
    "Abrir assim mesmo"; ao fechar, quem pode autorizar escolhe o próprio nome e assina com o
    PIN. Capturas em 1024.
  - testes: a guarda e a baixa pela mesma quantidade (bruta); o envelope com a próxima ação;
    a J-P7.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia P1-14, P1-23 e a regra de 28/10 (gerente da lista, uma autorização). Na
  abertura a falta é aviso, não trava: o padeiro decide com a informação.

### WP-F12 · Forno honesto

- **Objetivo:** só um gesto declara "retirou do forno", o erro aparece, e o timer avisa
  quando está sem som.
- **Achados que fecha:** P1-10, P1-11, P1-12, P2-11, P2-12 (parte).
- **Dependências:** WP-F06 no `main` (mesmo `close.vue`).
- **Arquivos:** `FE/pages/close.vue`, `FE/composables/useOvenFacts.ts`,
  `useFloorTimers.ts`, `FE/pages/timers.vue`, `FloorTimerCard.vue`.
- **Fora do escopo:** timer no servidor (decisão de 16/09: é lembrete); etapas.
- **Pronto quando:**
  - roteiro: a Cozinha arma o timer de um lote, passa pelos lotes com ‹ › e nada é gravado;
    recarrega a página e lê "Som desligado. Toque para ligar." no cartão do timer; em outro
    tablet, o lote diz "No forno até 5h40". Capturas em 1024 e 375.
  - testes: navegar não chama a declaração; a falha da declaração mostra a mensagem na tela.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia P1-10 a P1-12 e a memória das decisões de timers de 18/09 (o toque no
  cartão depende do estado). Depois de finalizar, a tela volta à lista; só segue ao próximo
  lote aberto se a pessoa tocar.

### WP-F13 · Pedidos à Produção (#3526)

- **Objetivo:** a encomenda para data sem lote, ou acima do plano, tem um lugar no
  Planejamento, com o gesto de planejar ao lado.
- **Achados que fecha:** P1-04, P1-30.
- **Dependências:** WP-F08 e WP-F10 no `main`. A decisão 2 foi respondida (D-042, item 2):
  a Produção só planeja.
- **Arquivos:** `PlanLens.vue`, `FE/components/PlanReasonCard.vue`, `GRID` (os atalhos de
  vazio), testes.
- **Fora do escopo:** aceitar ou recusar o pedido na Produção (não será feito, D-042 item 2);
  falar com o cliente, que é do Gestor; a casa do aviso no sino (F-03).
- **Pronto quando:**
  - roteiro: a Caixa cria no PDV uma encomenda para uma data sem lote. A Cozinha abre o
    Planejamento daquela data e lê, no topo, "Encomendado sem lote: Croissant 12" com
    "Planejar 12"; planeja; a faixa some e a reserva do pedido fica presa ao lote novo
    (conferido no Gestor: sem "Promessa em risco"). Capturas em 1024 e 375.
  - testes: componente e a J-P5 (cliente pela loja, Caixa pelo PDV, Cozinha na Produção).
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia a D-041 e a D-042 em `DECISIONS.md`, #2598 e #2932. A Produção não ganha
  botão de recusar: se a casa não vai produzir, o pedido segue em "Promessa em risco" no Gestor
  e é lá que se fala com o cliente. O número
  vem da projeção do WP-F08. Os atalhos "Ir para o Planejamento" carregam a data da tela.

### WP-F14 · Erros que falam português

- **Objetivo:** nenhuma recusa da Produção chega ao operador com código do Core, inglês ou
  jargão.
- **Achados que fecha:** P1-13, P2-19.
- **Dependências:** WP-F11 no `main` (mesmo `SVC`).
- **Arquivos:** `SVC` (`_operator_error` e as mensagens), `MUT`, testes.
- **Fora do escopo:** mudar a regra do Core; `docs/reference/errors.md` só ganha a seção da
  Produção.
- **Pronto quando:**
  - roteiro: a Cozinha reduz o plano abaixo do encomendado e lê "Há 12 un. encomendadas para
    este dia. O plano não pode ficar abaixo disso." com "Ver encomendas"; "Revisar
    quantidade" depois dessa recusa aceita um número novo. Captura em 1024.
  - testes: cada código do Core (`COMMITTED_HOLDS`, `INSUFFICIENT_MATERIALS`,
    `DOWNSTREAM_DEFICIT`) tem tradução; `CraftError` e `StockError` nunca viram 500 em
    `authorize_formula_deviation` e `register_old_dough`; erro de campo no dialeto da casa.
- **Muda tela:** não. **Tamanho:** P.
- **Brief:** leia P1-13 e `docs/reference/errors.md`. As duas travas de redução viram uma
  mensagem só; a oferta "Salvar com justificativa" some onde o Core recusa de qualquer jeito.

### WP-F15 · Tempo real honesto

- **Objetivo:** "Ao vivo" só aparece onde é verdade, e toda tela de lote ouve o canal de
  produção.
- **Achados que fecha:** P1-17, P1-18, P2-07.
- **Dependências:** WP-F12 no `main` (mesmo `close.vue`).
- **Arquivos:** `FE/components/ProductionHeader.vue`, `FE/composables/useQcKiosk.ts`,
  `useProductionKds.ts`, `useMiseEnPlace.ts`, `useProductionForecast.ts`,
  `FE/pages/quality.vue`, `FE/pages/close.vue` (só o estado de erro).
- **Fora do escopo:** canais novos no servidor; o sino.
- **Pronto quando:**
  - roteiro: em dois tablets, a Cozinha confirma o previsto num e o lote aparece na
    Finalização do outro em menos de 3 s; com o Django parado, a Finalização mostra o erro
    com "Tentar de novo" e o selo deixa de dizer "Ao vivo". Capturas.
  - testes: composables (o evento refaz o fetch canônico; o poll fica como reserva).
- **Muda tela:** sim, pouco (prévia). **Tamanho:** M.
- **Brief:** leia ADR-016 e `useProductionBoard.ts:84-119`, que é o molde. O aviso de dado
  velho vai para `alerts` do `OperatorPageHeader`, com X.

### WP-F16 · A estação do Letreiro só lê

- **Objetivo:** a conta da estação autônoma nunca muta, qualquer que seja o grupo dela.
- **Achados que fecha:** P1-27.
- **Dependências:** WP-F11 no `main` (mesmo `PROJ`).
- **Arquivos:** `PROJ` (`resolve_production_access`), teste em
  `test_api_production_surface.py`.
- **Fora do escopo:** persona nova no descritor (F-10).
- **Pronto quando:**
  - roteiro: o tablet do Letreiro, sem PIN, abre `/` e não vê nenhum botão de ação; uma
    chamada de mutação com o cookie dele devolve 403.
  - testes: toda capacidade de escrita falsa para sessão de estação.
- **Muda tela:** não. **Tamanho:** P.
- **Brief:** leia `backstage/station_trust.py` e P1-27. O teto é fechado por padrão: a
  estação só lê, e abrir exceção é decisão escrita.

### WP-F17 · O porquê fica com o lote

- **Objetivo:** todo plano grava, por append, o que foi sugerido e por quê; a linha mostra a
  conta em uma frase.
- **Achados que fecha:** P1-05, P2-02; F-11 (os dois primeiros itens).
- **Dependências:** WP-F14 no `main` (mesmo `SVC`); WP-F13 no `main` (mesma `GRID`).
- **Arquivos:** `GRID` (`submitPlan` e o envio em lote), `SVC` (`apply_planned`),
  `FE/presentation/planningReason.ts`, `PlanLens.vue`, testes.
- **Fora do escopo:** `SHOPSVC` e o Core; o B.I.
- **Pronto quando:**
  - roteiro: a Cozinha planeja amanhã "como sugerido" e depois corrige um produto. No "Por
    quê" do lote lê "Sugerido 42, planejado 36". A linha mostra "42 = 6 encomendas + 30 de
    balcão + 6 de margem". Capturas em 1024 e 375. A J-P2.
  - testes: o envio leva a origem verdadeira; o porquê vai normalizado (sem `Decimal` cru) e
    fica no evento; plano manual grava a sugestão vigente.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia P1-05 e F-11. Normalize o porquê no service do backstage, que é quem chama
  o `shop`, e passe-o como `planning_meta`. "Planejar os N como sugerido" vira uma chamada só
  no servidor, ou N chamadas com uma releitura no fim.

### WP-F18 · Relatórios e palavras

- **Objetivo:** os relatórios e os textos soltos falam a língua da casa.
- **Achados que fecha:** P2-03 a P2-06, P2-12, P2-14, P2-16, P2-17 (a leitura).
- **Dependências:** nenhuma.
- **Arquivos:** `FE/pages/reports.vue`, `FE/presentation/reports.ts`,
  `FE/composables/useProductionReports.ts` e `docs/reference/glossary.md` (F-14). Os textos
  de `timers.vue` ficam no WP-F12 e os de `quality.vue` no WP-F15.
- **Fora do escopo:** `GRID`; o B.I.
- **Pronto quando:**
  - roteiro: a Gerente abre os Relatórios e lê "Lote", "17/11", o nome de quem fez, peça e
    quilo em colunas separadas, e uma perda só (a declarada), com "rendeu menos" ao lado.
    Capturas em 1366 e 375.
  - testes: `reports.test.ts`; a trava de vocabulário cobrindo "OP" e "QC".
- **Muda tela:** sim (prévia). **Tamanho:** P.
- **Brief:** leia P2-04, P2-05, P2-16 e `suite-vocabulary.md`. A Gerente vê o valor de cada
  registro; nada de soma em dinheiro (regra de 21/11): confira que a tela continua sem custo.

### WP-F19 · A virada do dia

- **Objetivo:** toda tela sabe que dia é hoje, à meia-noite, e o lote aberto de ontem
  aparece onde o operador está.
- **Achados que fecha:** P1-09, P2-18 (o aviso).
- **Dependências:** WP-F15, WP-F17 e WP-F18 no `main` (mesmos arquivos).
- **Arquivos:** composable novo `useProductionDay.ts`, `GRID`, `FE/pages/close.vue`,
  `mise-en-place.vue`, `quality.vue`, `reports.vue`, `PROJ` (`previous_open` no quadro).
- **Fora do escopo:** impedir escrita em dia selado (decisão futura).
- **Pronto quando:**
  - roteiro: com o relógio de teste, a Cozinha deixa a Produção aberta às 23h57; às 0h01 a
    tela passa a "Hoje, ter 24/11" e mostra "8 lotes abertos de ontem · Ver"; abrir um lote
    de outro dia avisa "Este lote é de 23/11". Capturas antes e depois.
  - testes: a regra de `FE/presentation/production.ts:163-179` usada por todas as telas; a
    J-P6 com `OPERATOR_CONTROL_DIR`.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia P1-09, `board.vue:47-53` (o único que trata a meia-noite) e
  `config/test_clock.py`. O servidor do Nuxt segue a hora real: a jornada acerta o relógio do
  navegador pelo Playwright.

### WP-F20 · O painel de abertura e os alvos do chão

- **Objetivo:** o painel "Quanto está previsto?" não esconde a lista, e todo tamanho de tela
  usa o teclado da tela e alvos de 44 px.
- **Achados que fecha:** P1-06, P1-25, P1-22 (o lado da abertura), P2-13.
- **Dependências:** WP-F02 no `main`.
- **Arquivos:** `LotStartPanel.vue`, `GRID` (o layout das colunas).
- **Fora do escopo:** o `operator-kit` (F-12): o tamanho maior é opção do app.
- **Pronto quando:**
  - roteiro: em 1024 × 768, com o painel aberto, a Cozinha lê o nome inteiro de todos os
    lotes; em pé e em 375, o mesmo teclado da tela aparece, sem o teclado do sistema; massa
    aceita vírgula. Capturas nos quatro tamanhos, comparadas com `EV/02` e `EV/23`.
  - testes: a sobreposição (`tests/e2e/overlap.spec.ts`) com o painel aberto em 1024; alvos.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia P1-06 com `EV/02` aberta. A lista encolhe por colunas (some PLANEJ. e a
  situação vira ponto), nunca pelo nome.

### WP-F21 · Tem mais abaixo, e a etiqueta é do lote

- **Objetivo:** o app usa `<MoreBelow />` e o próximo foco como o resto da suíte, e a
  etiqueta abre o lote certo.
- **Achados que fecha:** P1-28, P2-21; issue #2391.
- **Dependências:** WP-F19 no `main`.
- **Arquivos:** as páginas (`timers.vue`, `quality.vue`, `mise-en-place.vue`, `reports.vue`,
  `recipes/index.vue`), `GRID` (o fim da lista), `FE/presentation/production.ts`
  (`matchLotCode`), `useFloorTimers.ts` (chaves antigas).
- **Fora do escopo:** reimprimir etiquetas antigas.
- **Pronto quando:**
  - roteiro: em 375, cada tela com conteúdo abaixo da dobra mostra o aviso; com dois lotes do
    mesmo produto, a etiqueta do segundo abre o segundo. Capturas.
  - testes: `production.test.ts` (o código da etiqueta leva a ref do lote); e2e de Timers.
- **Muda tela:** sim, pouco (prévia). **Tamanho:** P.
- **Brief:** leia as seções "Tem mais abaixo" e "Próximo foco" de
  `surfaces/operator-kit/README.md` e a #2391. Sem leitura de chave antiga: pré go-live não
  há legado.

## 8. Jornadas a canonizar

Todas em `surfaces/production-nuxt/tests/operator/`, contra o Django da pilha, com o papel e
os passos da pessoa.

| # | Jornada | Papel | Passos | WP que escreve |
|---|---|---|---|---|
| J-P1 | A madrugada | Gerente (dispositivo); Cozinha com PIN | confirmar o previsto → finalizar com perda e motivo → a Gerente confirma a Qualidade → o produto aparece na loja | F00 |
| J-P2 | A véspera | Cozinha | abrir amanhã → ler o porquê → planejar como sugerido → corrigir um → ler sugerido e planejado | F17 |
| J-P3 | Zerar não cancela | cliente; Caixa; Cozinha; Gerente | encomendar e pagar → aceitar → a Cozinha tenta 0 e é recusada → a Gerente cancela lendo os pedidos → o Gestor mostra a promessa em risco | F01 (a recusa), F07 (a tela) |
| J-P4 | Rendeu menos que o encomendado | cliente; Caixa; Cozinha | encomendar para hoje → aceitar → finalizar abaixo → fechar com a verdade → "Promessa em risco" no Gestor | F06 |
| J-P5 | Pedido à Produção | cliente ou Caixa no PDV; Cozinha | encomendar para data sem lote → a Produção lê no Planejamento → planeja → a reserva prende | F13 |
| J-P6 | A virada do dia | Cozinha | tela aberta às 23h57 → 0h01 → o rótulo vira e os lotes de ontem aparecem | F19 |
| J-P7 | Falta de insumo | Cozinha; Gerente com PIN | abrir com falta → ler o que falta → fechar com autorização da lista | F11 |
| J-P8 | O Letreiro | estação autônoma | abrir em 1920 × 1080 → ler → perder a conexão | F04 (visual) |
| J-P9 | Receitas | Gerente; Cozinha | criar → publicar → editar → comparar; a Cozinha só lê | F05 |

## 9. Ondas

Dois WPs da mesma onda nunca tocam o mesmo arquivo. Os gargalos são `GRID`, `SVC`, `PROJ` e
`close.vue`: no máximo um WP por onda escreve em cada um.

| Onda | WPs em paralelo | `GRID` | `SVC` | `PROJ` | `close.vue` |
|---|---|---|---|---|---|
| 0 | **F00** · **F01** · **F02** · **F03** · **F04** · **F05** | F02 | F01 | F04 | - |
| 1 | **F06** · **F07** · **F08** · **F09a** · **F20** | F20 | F06 | F08 | F06 |
| 2 | **F09b** · **F10** · **F11** · **F12** | F10 | F11 | F11 | F12 |
| 3 | **F13** · **F14** · **F15** · **F16** | F13 | F14 | F16 | F15 |
| 4 | **F17** · **F18** | F17 | F17 | - | - |
| 5 | **F19** | F19 | - | F19 | F19 |
| 6 | **F21** | F21 | - | - | - |

Conferência dos arquivos por onda:

- Onda 0: F00 só cria `tests/operator/` e mexe em `package.json`; F01 fica com `OPS` e `SVC`;
  F02 com `GRID` e os componentes novos; F03 com `QcCloseScreen.vue` e `qc.ts`; F04 com
  `board.vue`, `SplitFlap.vue`, `presentation/production.ts` e o trecho do Letreiro em `PROJ`;
  F05 com `recipes/**` e `recipe_book.py`.
- Onda 1: F06 com `SVC`, `ShortageDialog.vue` e `close.vue`; F07 com `LotCancelDialog.vue` e
  `PlanAdjustDialog.vue`; F08 com `PROJ`, o contrato e `presentation/production.ts`; F09a só
  com arquivos novos (modelo, migração, service e API da marca) e a rota em `api/urls.py`; F20
  com `LotStartPanel.vue` e `GRID`.
- Onda 2: F09b com a Preparação (página, composables e etiquetas de pesagem); F10 com `GRID`,
  `LotCommitmentsDialog.vue` e `planningRows.ts`; F11 com `SVC`, `ShortageDialog.vue` e `PROJ`;
  F12 com `close.vue`, os composables de forno e timer e `timers.vue`.
- Onda 3: F13 com `PlanLens.vue`, `PlanReasonCard.vue` e `GRID`; F14 com `SVC` e `MUT`; F15
  com o cabeçalho, os composables de leitura, `quality.vue` e `close.vue`; F16 com `PROJ`.
- Onda 4: F17 com `GRID`, `SVC`, `planningReason.ts` e `PlanLens.vue`; F18 com os Relatórios.
- Ondas 5 e 6: F19 e depois F21, sozinhos, porque atravessam quase todas as páginas.

O contrato gerado (`productionContract.ts`) é regenerado por F04, F08 e F11, em ondas
diferentes. PR aberto a não atropelar: o #3357 (Dependabot) mexe no `package.json` do app;
o WP-F00 espera ele mergear ou rebaseia.

O P0-1 fecha na onda 0 (servidor) e ganha a tela na onda 1. O P0-2 fecha na onda 1, se a
decisão 1 vier antes.

## 10. Decisões do dono

**Respondidas.** O dono aceitou as cinco recomendações em 23/11/2026 (*"No mais, aceito as
sugestões"*; na 5: *"Sim, óbvio! No servidor, sempre! Não precisava nem ter perguntado!"*),
registradas na [D-042](../coordination/DECISIONS.md) (#3422). Em 24/11 ele reconfirmou a 2 e a
5 pela coordenação.

| Decisão | Resposta | Efeito |
|---|---|---|
| 1. Lote curto fecha com o número verdadeiro | **Sim** | WP-F06 liberado |
| 2. Encomenda para data sem lote | **1: a Produção só planeja**; quem fala com o cliente é o Gestor | WP-F13 liberado, sem botão de recusar |
| 3. Quem autoriza fechar com falta de insumo | **1: Gerente e Dono, da lista, com o próprio PIN** | WP-F11 liberado |
| 4. Etapas da receita no lote aberto (#2385) | **Sim, não será feito** | #2385 fechada como not planned |
| 5. "Separado" no servidor | **Sim**, para todos os tablets do dia | WP-F09 dividido em F09a (servidor) e F09b (tela) |

As perguntas, como foram feitas:

Procurado antes em `docs/coordination/DECISIONS.md`, `docs/reference/`, nos ADRs 007, 017,
028 e 040 e nas issues citadas: nenhuma das cinco tinha resposta escrita. Cada uma traz a
recomendação primeiro.

1. **Lote que rendeu menos que o encomendado: fecha com o número verdadeiro?** (bloqueia o
   WP-F06, o P0-2)
   Recomendação: **sim**. O lote fecha com o que rendeu, o pão entra no estoque, e os pedidos
   que ficaram descobertos aparecem em "Promessa em risco" no Gestor, que já tem o "Resolver"
   (trocar, remarcar, tirar o item, cancelar). Hoje o lote não fecha e a tela pede um número
   falso. *Sim ou não.*

2. **Encomenda para data sem lote (o que a D-041 deixou em aberto): como a Produção
   responde?** (bloqueia o WP-F13)
   Recomendação: **1**. A Produção só **planeja**: o pedido aparece no Planejamento daquela
   data com "Planejar N", e planejar prende a reserva. Se a casa não vai produzir, quem fala
   com o cliente é o Gestor.
   **2**: a Produção também aceita ou recusa o pedido na tela dela. *1 ou 2.*

3. **Quem autoriza fechar um lote com falta de insumo?** (bloqueia o WP-F11; hoje ninguém
   tem a permissão)
   Recomendação: **1**, a Gerente e o Dono, escolhidos da lista e assinando com o próprio
   PIN, como nas outras autorizações da casa.
   **2**: ninguém; o lote só fecha depois de o Compras dar entrada no insumo. *1 ou 2.*

4. **Etapas da receita no lote aberto, com "próxima etapa" e timer por etapa (#2385): fechar
   como "não será feito"?**
   Recomendação: **sim**. Em 16/09 as etapas saíram do fluxo do chão ("se não obrigar vira
   adereço, se obrigar engessa") e os timers viraram ferramenta livre. O carimbo de hora por
   etapa (pedido em 14/08) fica sem objeto enquanto valer essa decisão; continuam gravadas as
   horas de abrir, enfornar, retirar, fechar e confirmar a qualidade. *Sim ou não.*

5. **O "Separado" da Preparação vale para a bancada inteira (grava no servidor)?** (afeta o
   WP-F09)
   Recomendação: **sim**. Hoje a marca mora em um tablet; trocar de tablet ou de pessoa
   recomeça a conferência. Custa um registro novo no backstage (uma migração).
   Não: a marca continua por dispositivo, só deixa de sumir sozinha. *Sim ou não.*

Não viraram pergunta, porque derivam de regra já escrita: o motivo de "rendeu menos" em um
toque (o chão não digita); a estação do Letreiro só lê (falhar fechado); o gerente da lista
com PIN (28/10); a Produção não ver dinheiro (21/11).

Seguem do dono, fora deste plano e já registradas: as durações das quatro etiquetas de timer
do seed (corrige no Admin), as etapas reais das massas, e "rendimento" × "aproveitamento" no
B.I. (#2440).

## 11. Benchmarks

Pesquisa de 23/11/2026 em páginas públicas de produto, ajuda e changelog de Galley, meez,
Apicbase, MarketMan, FlexiBake, BakeSmart, Toast, Square for Restaurants e Hotplate, com
Cybake, Craftybase e Katana como comparação. Nada foi testado em conta real; toda ausência
abaixo é **estimada pela documentação, não medida**.

**O que os melhores fazem melhor, e vale de referência:**

| Quem | O que faz | Onde entra neste plano |
|---|---|---|
| Galley, FlexiBake | planejam de trás para a frente a partir da entrega: validade, preparo e dependência empurram a base para o dia anterior | já existe na Preparação (pré-preparos); reforça o WP-F13 |
| FlexiBake | o número do plano decomposto em colunas: em pedido, previsão, estoque, já agendado | S3 e WP-F17 (em uma frase, na linha) |
| FlexiBake | fecha pelo rendimento real e compara esperado e real ao longo do tempo | WP-F03 e F-11 |
| Apicbase | fechamento que já vem pronto: o que entra no estoque, lote e validade preenchidos, etiqueta sugerida | a Finalização já faz; WP-F21 fecha a etiqueta |
| Square | "disponível" diferente de "em mãos": desconta conta aberta, carrinho e agendado | a régua das reservas já é assim; WP-F08 leva à Produção |
| Hotplate | teto por janela de retirada; edição do pedido ajusta o estoque do "drop" | F-05 |
| Toast, Katana | total no nível do insumo sempre à vista; semáforo de insumo na tarefa | WP-F11 |
| Galley | versão de receita que se compara e se ramifica sem tocar a original | WP-F05 |

**O que nenhum faz:**

1. O gesto do padeiro não chega à promessa: fechar com menos, cancelar ou atrasar não aponta
   quais pedidos aceitos ficaram sem lastro. O Hotplate resolve pedido a pedido, à mão; o
   Katana mostra só para dentro. **É o S1.**
2. Nenhum declara quem recebe o que rendeu quando falta.
3. Nenhum trata "a fornada de sábado" como lastro vivo: planejado, encomendado, livre. O
   Toast admite na ajuda que não reserva item limitado para pedido futuro. **É o S2.**
4. O porquê do número, em uma frase, na tela do chão. **É o S3.**
5. A loja promete pelo relógio, não pelo forno (F-05).
6. Offline e chão de padaria: o Hotplate diz que não tem modo offline, o meez não tem app
   nativo, e timer só existe como duração de tarefa.

Leitura: os de receita ensinam versão e escala; os de padaria industrial ensinam pedido,
plano e rendimento; os de PDV e pré-venda ensinam a promessa. Nenhum junta as três pontas. A
casa já lastreia encomenda paga no lote planejado: está no vão que o mercado deixou, e o que
falta é a Produção enxergar e responder por esse elo.

## 12. Ficou de fora deste PR

- A execução dos WPs (#3364; eram 22, são 23 desde que o F09 se dividiu).
- As 16 fronteiras da seção 5, em especial F-01 e F-02, que são do `shop` e foram medidas
  (#3365).
- As jornadas não percorridas pela tela nesta revisão: pedido à Produção pelo PDV, falta de
  insumo, dia fechado e feriado, o ciclo das Receitas, etiquetas e timers tocando (#3366).

**As issues `ficou-de-fora` antigas da Produção:**

| Issue | Destino |
|---|---|
| #2385 etapas na execução | fechar como `not planned`, se a decisão 4 for sim |
| #2386 nota do item | absorvida pelo WP-F05 |
| #2387 reputação da versão | a fatia 2 é absorvida pelo WP-F05; a fatia 3 e o `bi_production` por versão continuam como estão (B.I.) |
| #2388 plano agrupado | continua como está: com 73 produtos, os conjuntos "sem ressalva" e "sem sugestão" já resolveram a leitura no tablet (medido); o agrupamento do servidor segue sem consumidor |
| #2389 insumos na abertura, ajustar previsto, "faltam X kg" | (a) absorvida pelo WP-F11; (b) continua como está (a diferença já se declara na Finalização); (c) fechar: está feita em `PlanReasonCard.vue:204-211` |
| #2390 link ao Compras na busca de insumo | absorvida pelo WP-F05 |
| #2391 `MoreBelow` e e2e nos Timers | absorvida e alargada ao app inteiro pelo WP-F21 |
| #2420 painel autônomo sem alertas e receitas | continua como está (decisão de segurança escrita); o WP-F16 fecha o teto de escrita |
| #2392 hora do esgotamento e link ao insumo | a hora já aparece no "Por quê"; o link ao insumo é F-16 |
