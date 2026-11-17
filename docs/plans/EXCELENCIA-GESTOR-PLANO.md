# EXCELÊNCIA-GESTOR: laudo e plano do Gestor de pedidos

Compromisso: DEV-2026-028. Brief: `docs/coordination/ROUNDS/EXCELENCIA-GESTOR.md`, sobre a
base `docs/coordination/ROUNDS/EXCELENCIA-base.md`. Medido em 16/11/2026 contra o `main`
`d48286ec4`. Nenhum código de produção foi escrito.

Ênfase: **Encomendas e pedidos agendados**.

## Sumário

- **1 achado P0, 22 P1 e 29 P2** no perímetro do Gestor, mais 18 itens de fronteira.
- **A causa que mais se repete é de contrato, não de tela**: o card do Gestor conhece o
  *dia* da encomenda e não conhece a *hora combinada*, a *hora de ir à Cozinha* nem a
  *saúde da reserva*. Seis achados P1 e o P0 saem dessa falta.
- **O salto que mais impressiona**: "Promessa em risco". Quando a produção muda (lote
  cancelado, rendeu menos, atrasou), o Gestor mostra pedido a pedido quem ficou sem pão, com
  a ação pronta. Nenhum dos cinco benchmarks liga produção real a pedido aceito.
- **15 WPs em 6 ondas, mais um fora delas**. O primeiro a delegar é o **WP-G01** (a encomenda
  se anuncia), junto com o **WP-G00** (harness de operador de verdade). O **WP-G14** (canal
  Google: retirada item a item) entrou em 17/11/2026, pela issue #2652, e espera o WP-L01 da
  Loja no `main`.
- **4 decisões do dono**, no fim. Em 17/11/2026 ele respondeu sim à 2 e à 3, escolheu a API
  na 4 e decidiu a 1: no pedido não retirado, a casa fica só com o valor da perda.
- **O que este PR deixou de fora tem issue**: execução do plano (#2546), o lado de fronteira do
  P0 (#2547), o pedido de hoje com hora combinada (#2548), as demais fronteiras (#2549) e as
  jornadas ainda não percorridas pela UI (#2550).

## 1. Como foi medido, e o que a medição não cobre

**Pilha isolada** (só as portas e o banco do brief): Django `:8060`, banco
`shopman_exc_gestor`, Gestor `:3164`, loja `:3160`, Cozinha `:3163`, PDV `:3162`, com o
worker de directives. `migrate` e `seed --flush` rodaram até o fim (4.206 pedidos; 10 ativos).

**Leitura de código**: `order_queue.py` inteiro (3.658 linhas), `order_attention.py`, as
views de pedido e de histórico, todos os componentes e composables do painel, do detalhe e
do histórico. As provas de maior peso foram reconferidas linha a linha depois da primeira
leitura.

**Histórico**: cada item dos laudos de 09/11 e 12/11 foi conferido contra o `main` de hoje
(seção 2).

**Limites, ditos com nome:**

| O que | Por quê | Como ficou provado |
|---|---|---|
| Estados fiscais (nota recusada, DANFE, entrega sem CPF) pela UI | a pilha local não tem adapter fiscal (`SHOPMAN_W003` no boot: só existe `fiscal_focusnfe`, que é serviço externo) | leitura de código, com `caminho:linha` |
| Virada do dia e "encomenda no dia" pela UI | não há relógio de teste no servidor (nenhum `TEST_NOW` em `config/` nem em `shop/`) | leitura de código e dos testes de `test_preorder_kitchen_release.py` |
| Encomenda no seed | o seed não cria nenhuma encomenda futura nem pedido novo: os 10 ativos são de hoje e já aceitos | criadas pela loja da pilha |
| Desempenho | três revisões irmãs compilavam na mesma máquina (carga acima de 20, swap quase cheio); nada de tempo de resposta medido aqui vale como achado | fora do laudo |
| Jornadas que não foram percorridas pela UI | a máquina saturada consumiu a janela: a compilação do Gestor levou 35 min | preparo até a entrega com a Cozinha, cancelamento depois do preparo, fila de espera, loja fechada e a aba Encomendas do PDV ficaram por leitura de código; a issue de "ficou de fora" do PR carrega o roteiro que falta |

O roteiro percorrido pela UI está na seção 3.

## 2. Histórico: o que já está no `main` (não reauditar)

| Item do laudo antigo | Onde está hoje |
|---|---|
| Prazo de aceite 5/60 (5 min só no pedido do dia com a casa aberta) | #2254: `shopman/shop/lifecycle.py:1365-1380`, `shopman/shop/config.py:98-127` |
| Encomenda nova na Entrada e no contador | #2293: `shopman/backstage/projections/order_queue.py:1891-1899`, `:1810-1827` |
| Atraso medido contra a hora combinada | #2293: `shopman/backstage/projections/order_attention.py:264-303` |
| **"KDS na hora certa"**: o card chega à Cozinha em hora − preparo − antecedência, sem virar "Em preparo" | **#2303** (a memória de 12/11 dizia "sem frente"; está vencida): `lifecycle.py:1090-1118`, `:1177-1228`; política em `shopman/shop/policies/preorder_kitchen_policy.py:28-61` |
| B.I. com os dois tempos da encomenda | #2305: `shopman/backstage/projections/bi_preorder_kitchen.py` |
| Encomenda paga não é fila de espera; a varredura não solta a vaga paga | #2294: `shopman/shop/services/waitlist.py:455-518` |
| Reagendar para hoje e entregar no balcão baixa o estoque | #2295: `shopman/shop/services/operator_orders.py:1647-1678` |
| Inventário "ridiculamente fácil" de 25/09 (sino só de pedido, "Visto", alerta com "Abrir o pedido") | #1143 e #1144 |

**Em voo, travado:** #2292 (fechar dia no calendário avisa os pedidos marcados para ele) está
aberto e em `CONFLICTING` desde 12/11. PR em conflito não dispara workflow: não vai mergear
sozinho. Não é WP deste plano; é pendência a destravar (ver Fronteiras, F-12).

**Documentos que envelheceram:** `handlers/preorder.py:5-6` e
`docs/reference/cenarios-de-pedido.md:386` e `:399` ainda dizem "00:05/meia-noite";
`cenarios-de-pedido.md:269` e `:689` dizem que a devolução depois da venda existe "só no
Gestor", e ela não existe em superfície nenhuma (P1-17).

**Pontos fortes que nenhum WP pode regredir:**

1. Mutação à prova de corrida: chave de idempotência, `base_revision`, revalidação sob lock e
   recibo consultável quando a resposta se perde (`shopman/backstage/api/operations.py:2530-2616`;
   `surfaces/orders-nuxt/app/composables/useOrderIntention.ts:101-213`).
2. Capacidade decidida no servidor: cada ação chega com `enabled` e `reason` da mesma régua
   que o comando aplica (`operator_orders.py:2313-2447`; `order_queue.py:1003-1040`).
3. Tempo real honesto: o SSE só invalida, o fetch canônico é a verdade, e a tela recusa agir
   sobre leitura velha (`useOrdersBoard.ts:159-182`, `:413-452`).
4. Honestidade do dinheiro antes do gesto: "Pagamento simulado", destino do dinheiro antes de
   cancelar, cobrança vencida com o próximo passo (`order_queue.py:1261-1294`, `:2785-2825`).
5. Tela de falha de acesso que diz a verdade: "Você continua conectado, mas os pedidos não
   carregaram", com "Tentar de novo" (visto na pilha, com o Django reiniciando).

## 3. Roteiro percorrido pela UI

Papéis: cliente novo na loja (375 px), Gerente (senha, para abrir o dispositivo) e Caixa
com PIN, no Gestor (1366 px e 375 px). Nunca o superusuário. Pix simulado; o código de
entrada saiu no log local; nenhuma mensagem real.

| Passo | O que a tela mostrou | Achado |
|---|---|---|
| Cliente encomenda Pain de Campagne para amanhã, "A partir das 15h", e paga | a loja diz "Pagamento recebido. A loja confirma sua encomenda para amanhã · A partir das 15h" | - |
| Caixa olha o pedido novo no Painel (1366) | "T09 · Cancela Sozinho em 59:05 · Clara Teste · Loja online · Retirada · 1x Pain de Campagne". Nenhuma palavra "Encomenda", nem "amanhã", nem "15h" | P1-01 |
| Caixa abre "Recusar" (sem confirmar) | título "Recusar pedido", sem dizer qual; nada sobre o dinheiro; motivos "Não dá para entregar" numa retirada e "Pagamento não confirmado" num pedido pago; o botão de confirmar cortado na base em 850 px de altura. Acerto: "O cliente vai ler", com a frase do motivo | P1-11, P2-29 |
| Caixa abre o detalhe | "Amanhã · A partir das 15h" em letra miúda sob o total; "NFC-e não solicitada" sem ação; "Aparece no ticket da cozinha (KDS)"; atalhos "Sem cebola" num pão | P2-28 |
| Caixa aceita | o detalhe mostra "Aguardando o dia da encomenda. Encomenda para uma data futura. O preparo abre no dia combinado." em vermelho, e o aviso ao cliente "Falhou em todos os canais. Fale com o cliente por outro meio." sem botão | P2-26, P1-18 |
| Caixa volta ao Painel (1366) | **a encomenda sumiu**: "Novos 0 · Nenhum pedido novo agora.", o contador "Todos" caiu de 11 para 10 e a lista "Encomendas" fica abaixo da dobra, sem aviso | P1-09 |
| Caixa rola até a lista | "amanhã · T09 · Clara Teste · 1x Pain de Campagne · R$ 18,70". Sem hora, sem "Retirada", sem pagamento | P1-09 |
| A mesma lista em 375 px | "T09 · Clara Teste · 1… · R$ 18,70"; a linha fica colada à barra inferior | P2-02, P2-03 |
| Cliente lê o acompanhamento | "Encomenda confirmada. Pedido garantido para amanhã · A partir das 15h." | contexto do P0-1 |
| Cliente cancela antes do preparo | a loja avisa antes: "Cancelamos agora e devolvemos os R$ 18,70 do seu Pix para a mesma conta." | contraste com o P1-11 |
| Caixa abre o cancelado no Gestor | "Pix · Reembolsado" e, na linha do tempo, "Pagamento estornado": duas palavras para o mesmo fato; a frase que o cliente leu não existe ali | P2-25 |
| Histórico | "7 pedidos", sem dizer que são só os de hoje; hora sem rótulo; o cancelado aparece com "Pix · R$ 18,70", igual a um concluído | P1-21, P2-23 |
| Pedidos do seed no Painel, na Fila e na Tabela | "Pix expirado" em três formas no mesmo cartão (selo "Bloqueado", pílula "Por que espera", botão desligado) e uma saída só, "Cancelar pedido"; na Fila e na Tabela nem essa. "Entregar J40" no Painel é "Marcar como retirado" na Tabela. "meta 5" sem unidade. "Aguardando Encomendas" é a estação da Cozinha, ao lado da lista "Encomendas" | P1-16, P1-12, P2-27 |
| Gestor no celular (375) | o convite "Vincular este dispositivo a um posto de trabalho?" ocupa um quarto da tela acima do app; cabe um cartão | F-16 |
| Entrada depois de sessão vencida | o login respondeu 200 e a tela caiu em "Sua sessão terminou": uma resposta atrasada, ainda com o cookie velho, apagou o novo. Visto uma vez, na pilha | F-17 |

## 4. Laudo

Lentes: UX (UX/UI) · COPY · CONTR (contrato) · PERM (segurança e permissão) · OMO
(omotenashi-first) · MOB (mobile-first) · FLUXO (continuidade do fluxo) · PROM (a promessa de
produção).

Caminhos abreviados: `OQ` = `shopman/backstage/projections/order_queue.py` · `OA` =
`shopman/backstage/projections/order_attention.py` · `OPS` =
`shopman/backstage/api/operations.py` · `OO` = `shopman/shop/services/operator_orders.py` ·
`LC` = `shopman/shop/lifecycle.py` · `FE` = `surfaces/orders-nuxt/app`.

### 4.1 A causa de desenho

O card do Gestor carrega **um** fato de tempo da encomenda: `commitment_date`, e só o exibe
enquanto a data é futura (`OQ:2231-2232`, `:2322-2324`). Faltam três fatos, e cada um explica
uma família de achados:

| Fato que falta no contrato do card | Onde ele já existe no servidor | Achados que saem daí |
|---|---|---|
| A **hora combinada** (janela de retirada ou entrega) | `fulfillment_window.window_label` e `promised_at` (`shopman/shop/services/fulfillment_window.py:150-226`); hoje só o detalhe recebe (`OQ:1407-1421`) | P1-01, P1-06, P1-07, P1-09 |
| A **hora de ir à Cozinha** | `lifecycle.preorder_activation_at` e `kitchen_released_at` (`LC:1090-1118`, `:1231-1239`); a projection não lê nenhum dos dois | P1-02, P1-03, P1-04, P1-05 |
| A **saúde da reserva** (o pão prometido ainda tem lastro?) | holds do Stockman e vínculo com o lote (`awaiting_wo_refs`) | P0-1, P1-22, P2-19 |

Corrigir tela por tela não fecha: o conserto é publicar os três fatos **uma vez**, no card, e
deixar Painel, Fila, Tabela, lista de Encomendas, sino e detalhe lerem dali.

### 4.2 P0

| # | Achado | Lente | Prova | Causa |
|---|---|---|---|---|
| **P0-1** | **Lote cancelado depois do aceite solta a reserva da encomenda paga, e o Gestor não fica sabendo.** A linha "Produção de X: não começou" some do card, que passa a parecer sem pendência. O cliente pagou, a casa aceitou, e ninguém é avisado de que o pão não vai existir. | PROM, CONTR | `shopman/shop/handlers/_stock_receivers.py:36-50` (solta "primeiro a sacola, depois o pedido"), `:70-76` (`stock.release(..., reason="Produção cancelada")`), `:86-110` (avisa só `Session` aberta, nunca pedido aceito); `shopman/shop/handlers/production_order_sync.py:171-175` e `:672-687` (remove a ref do lote do pedido em silêncio); `OQ:2645-2677` (o card só lê `awaiting_wo_refs`; `if not wo: continue`); `FE/presentation/board.ts:1284-1300` (o estado "cancelada" existe na tela e nunca chega) | O vínculo pedido × lote é informativo e some no cancelamento. Não existe no contrato nenhum campo de "reserva perdida" ou "lote mudou". |

O conserto tem dois lados. **No perímetro** (WP-G08): a projection deriva, na leitura, a
saúde da reserva de cada pedido aceito e publica `promise_risk` com a ação ao lado. **Na
fronteira** (F-6, #2547): o cancelamento do lote vira fato do pedido (evento e alerta), para o aviso
chegar por push, e não só quando alguém olhar o painel.

### 4.3 P1 no perímetro

**A encomenda no tempo**

| # | Achado | Lente | Prova | Causa |
|---|---|---|---|---|
| P1-01 | **Aceite cego.** No Painel de mesa, na Fila, na Tabela e no "Aceitar" do sino, o pedido novo não diz que é encomenda nem para quando. O operador tem 60 min para aceitar sem ver a data nem a hora que está prometendo. | UX, PROM | `FE/components/OrderCard.vue:503-627` (cartão enxuto sem o selo; o selo só existe no cartão cheio, `:808`); `FE/components/OrderBoardColumn.vue:141`, `:190` (`:compact="!phone"`); `FE/components/QueueView.vue:436-476`; `FE/pages/index.vue:2026-2086`; `FE/composables/useAlerts.ts:158-191` | A hora combinada não está no contrato do card, e o cartão enxuto cortou o único selo de data. |
| P1-02 | **No dia, a encomenda cai em "Em preparo" à meia-noite, com "Iniciar preparo" como botão principal e sem a hora combinada.** O toque libera a Cozinha na hora, antes de hora − preparo − antecedência. | PROM, FLUXO | `OQ:2048-2051` e `:1909` (deixa de ser "futura" na virada); `OO:308-309`, `:2145-2155` (o bloqueio só vale para data futura); `OO:612-626` e `LC:1242-1271` (o toque antecipa a liberação) | "É do dia" e "já é hora de produzir" são dois fatos; a projection só conhece o primeiro. |
| P1-03 | **Na Fila, a encomenda do dia nasce âmbar e, sem hora combinada, vermelha "atrasada".** | OMO, CONTR | `OA:170-172` (toda encomenda aceita do dia vira `start`); `OA:238-247` (o "desde" é o aceite, dias atrás); `OA:288-291` (sem horário a meta cai em 5 min); `FE/presentation/queue.ts:75-81` | Régua de fração de meta, em minutos, aplicada a uma espera de dias. |
| P1-04 | **Alarme à meia-noite.** Toda encomenda do novo dia volta a tocar o aviso insistente, e os "já vistos" de ontem zeram. | OMO | `FE/composables/useOrdersBoard.ts:77-94`, `:115-116`, `:389-411`; `FE/presentation/board.ts:710-739` | A memória do "já vi" é por dia civil, e a encomenda vira tratável exatamente às 00:00. |
| P1-05 | **"há 3d 4h" no cartão e "Na Cozinha: o mais antigo há 3d".** É o tempo desde a compra, lido como tempo de preparo. | COPY (D1, D4) | `FE/presentation/board.ts:1222`, `:790`; `FE/presentation/queue.ts:273`, `:301-304`, `:474` | `created_at` usado como relógio de etapa. |
| P1-06 | **Pedido de hoje com hora combinada: o cartão do Painel não mostra a hora.** Só aparece como meta na Fila e no detalhe. | UX, PROM | `OQ:2232`, `:2324`; `FE/components/OrderCard.vue:804-810`; `FE/components/QueueView.vue:326-328` | Mesmo eixo do P1-01: o display da data só existe para data futura. |
| P1-07 | **Encomenda vencida não tem nome.** A de ontem, não iniciada, lê "combinado para as 18:00" sem o dia; nada diz "era para ontem". | COPY (D3), PROM | `OA:302`; `OQ:2231-2232`, `:2324` | A frase formata só a hora, e o card apaga a data quando ela deixa de ser futura. |
| P1-08 | **Pronto e não retirado é beco.** Na loja online, pedido em "Pronto" não se cancela nem com gerente; a tela mostra "Pedido em Pronto não pode ser cancelado." sem ação. O contorno é "Voltar para a cozinha" e cancelar dali, que burla a régua de gerente. Não existe gesto de não comparecimento. | FLUXO, PERM | `packages/orderman/shopman/orderman/models/order.py:60-72` (`READY` não vai a `CANCELLED`); `config/instances/nelson.json:158-196` (só o canal `pdv` declara a transição); `shopman/shop/services/cancellation.py:190-194`; `FE/pages/[ref].vue:1163-1169`; `shopman/shop/services/kds.py:1039-1050` | A régua de transições do canal e a política de cancelamento foram escritas para canais diferentes, e "não retirado" nunca virou estado. |
| P1-09 | **A encomenda aceita some da tela, e a lista onde ela vai morar não responde nada.** Depois do aceite o Painel diz "Nenhum pedido novo agora.", o contador cai e a lista "Encomendas" fica abaixo da dobra, sem aviso, também em 1366 px. A linha mostra código, nome, itens e total: não diz hora, retirada ou entrega, pagamento nem produção. O único sinal, "Precisa de você", aparece justamente em quem espera um fato de fora (pagamento). | UX, COPY (D1), FLUXO | visto na pilha (seção 3); `FE/components/OrderPreorderList.vue:49-68`; `FE/pages/index.vue:2237`; `OA:173` (ali a única atenção possível é `blocked`) | A lista foi posta depois do painel de altura cheia, e a linha foi desenhada sem os fatos que o card já tem. |
| P1-10 | **O Gestor mostra a encomenda e não a remarca.** O atalho leva à lista geral de Encomendas do PDV, e não ao pedido, embora a rota por pedido exista. | FLUXO | `OPS:3155-3179` (o endpoint existe, com `shop.manage_orders`); `FE/components/OrderPreorderList.vue:15-18` (`/preorders` genérico); `surfaces/pos-nuxt/app/pages/preorders/[ref].vue` (a rota existe) | Decisão D-003: remarcar e editar moram no PDV até a concierge nascer. O atalho ficou genérico. |

**Ação ao lado do estado**

| # | Achado | Lente | Prova | Causa |
|---|---|---|---|---|
| P1-11 | **Recusar pelo painel não diz qual pedido, não diz o que acontece com o dinheiro, e o erro da recusa aparece no cartão, atrás do diálogo aberto.** A loja diz ao cliente ("devolvemos os R$ 18,70 do seu Pix") o que o Gestor não diz a quem opera. Os motivos não olham o pedido: "Não dá para entregar" numa retirada, "Pagamento não confirmado" num pedido pago. | UX, CONTR, OMO | `FE/pages/index.vue:2267-2280` (diálogo sem o efeito do dinheiro); `OQ:862-869` (`cancel_money_effect` só no detalhe); `FE/pages/index.vue:1187-1191`; `FE/composables/useOrdersBoard.ts:627-644`; `FE/components/OrderReasonDialog.vue:14-28` (sem prop de erro) | O campo não está no contrato do card, e o lugar do erro é o cartão enquanto o gesto mora num modal. |
| P1-12 | **Bloqueio sem ação e motivo escondido.** Na Fila, o bloqueio é pílula com motivo e nenhum gesto (o cartão tem "Cancelar pedido" pronto para o mesmo caso). O "Aceitar" travado só explica o porquê em `title`, que não existe no toque. | FLUXO, MOB | `FE/components/QueueView.vue:477-489` contra `FE/components/OrderCard.vue:329-340`; `OQ:2844-2852`; `FE/components/OrderCardActions.vue:89-92`; `FE/components/QueueView.vue:637-643` | A ação foi implementada só no cartão; o motivo, só em atributo de hover. |
| P1-13 | **"NFC-e não autorizada" é texto cinza igual aos outros estados, sem o motivo da recusa, com "Reprocessar NFC-e" dentro do ⋮.** O alerta manda "Abra o pedido e toque em Reprocessar" e o link chega sem âncora. | FLUXO, OMO | `OQ:3039-3051`, `:744-747` (a projeção não carrega o motivo); `FE/pages/[ref].vue:626-637`; `shopman/shop/handlers/fiscal.py:88-95`; `shopman/backstage/projections/alerts.py:209-213` | O estado de falha foi tratado como mais uma pílula informativa. |
| P1-14 | **A DANFE da sacola não existe no detalhe.** O gesto de imprimir e reimprimir vive só no card do painel. | FLUXO | `useDanfePrint` só em `FE/pages/index.vue:108`; `danfe_*` só no card (`OQ:550-560`), ausente de `OperatorOrderProjection` (`OQ:669-878`) | O gesto nasceu no card e o contrato do detalhe não o herdou. |
| P1-15 | **Estorno pendente ou recusado é invisível.** O pedido cancelado continua lendo "Pix · Pago". A falha vira alerta cuja frase é "o suporte resolve", e o único reenvio é o Admin do Payman, com permissão só do grupo Dono. | CONTR, PERM | `OQ:115-129`; `shopman/shop/services/payment.py:1915-1931`, `:1948-1952`, `:2190-2213`; `shopman/shop/adapters/payman_refund.py:1-8`; `config/instances/nelson.json:2064-2082` | O estado do estorno nunca virou campo do detalhe, e o Gerente precisa do Dono para um pedido. |
| P1-16 | **Cobrança vencida em pedido aceito: o fato aparece em três formas e a única saída é cancelar.** No cartão, selo "Bloqueado", pílula "Por que espera" e um botão desligado "Pix expirado"; só o popover oferece "Cancelar pedido". Na Fila e na Tabela o "próximo passo" é o mesmo botão desligado. Não há cobrar de novo nem avisar o cliente. | FLUXO, COPY (D2) | visto na pilha (seção 3); `FE/components/OrderCard.vue:321`, `:329-340`; `FE/components/QueueView.vue:477-489`; `OQ:1216-1223` (reenviar só quando o método é link) | Um estado foi desenhado como rótulo dentro de um botão, e o gesto de cobrar de novo não existe para Pix. |
| P1-17 | **Devolução não tem porta de entrada.** O serviço existe e ninguém o chama; o Histórico anuncia "concluídos, cancelados e devolvidos" e a referência de cenários diz "só no Gestor". | FLUXO | `shopman/shop/handlers/returns.py:40` (`initiate_return` sem chamador fora dos testes); `FE/pages/history.vue:181`; `docs/reference/cenarios-de-pedido.md:269` | O serviço nunca ganhou rota nem tela. |
| P1-18 | **"Avisar o cliente" abre conversa em branco, e o recibo de aviso com falha instrui sem botão.** | OMO, COPY (D1) | `OQ:3171` (`https://wa.me/{digits}` sem texto); `surfaces/operator-kit/app/components/OperatorOrderContact.vue:21-52`; `shopman/backstage/projections/notification_receipts.py:172-176`; `FE/components/OrderNotificationReceipts.vue:36-88` | O contato é atalho de discagem, não mensagem. A issue #2407 carrega o "Reenviar/Copiar mensagem". |
| P1-19 | **Quatro avisos do sino levam a um detalhe que não tem o gesto que a frase pede:** nota a cancelar ("Leve o caso ao contador"), estorno que falhou, etapa travada ("não refaça a etapa à mão") e encomenda sem pagamento na hora da Cozinha ("Cobre o cliente ou cancele"). | OMO | `shopman/shop/handlers/fiscal.py:604-614`; `payment.py:2202-2213`; `LC:245-256`, `:1528-1531`; `alerts.py:261-268`; `OQ:1216-1223` | "Todo aviso com pedido leva ao pedido" não garante que o pedido tenha a ação. |
| P1-20 | **Quem só expede abre um pedido pelo sino e lê "Pedido não encontrado ou falha ao carregar."** | COPY, PERM | `shopman/backstage/services/alerts.py:32-33`; `OPS:2343-2344`; `FE/pages/[ref].vue:1285-1296`; `FE/presentation/gestorSections.ts:307-314` | O 403 de permissão cai no mesmo texto do 404. |
| P1-21 | **A busca do Histórico está presa a "hoje" e não diz.** Buscar um nome devolve "Nenhum pedido com esses filtros", com o período padrão invisível. | COPY (D3), FLUXO | `FE/presentation/history.ts:122-136`; `FE/pages/history.vue:65`, `:78-91`; `shopman/backstage/projections/order_history.py:319-320` | Busca e período compostos como recortes independentes. |
| P1-22 | **Pedido pago do dia que espera o lote perde o selo e o bloqueio.** "Iniciar preparo" fica livre com o pão ainda por assar. | PROM | `shopman/shop/services/waitlist.py:514-518` (devolve `none` para o pago); `OQ:2076-2093`; `OO:310-311`, `:2129-2139` | Efeito colateral do #2294: o selo do Gestor pegava carona no estado da fila de espera. |

### 4.4 P2 no perímetro

| # | Achado | Lente | Prova |
|---|---|---|---|
| P2-01 | Botões secundários ignoram `disabled` ("Recusar", "Receber na retirada") | CONTR | `FE/components/OrderCardActions.vue:70` contra `FE/presentation/board.ts:561`, `:586` |
| P2-02 | Lista de Encomendas a 375 px: larguras fixas sem quebra; os itens somem | MOB | `FE/components/OrderPreorderList.vue:51-67` |
| P2-03 | No celular, a lista de Encomendas fica uma tela abaixo, sem aviso; nenhum `<MoreBelow />` no app | MOB | `FE/components/OrderBoardColumn.vue:86-89`; `FE/pages/index.vue:2237` |
| P2-04 | Cartão enxuto corta "Retirada/Entrega" primeiro e não mostra pagamento, presente nem observação | UX | `FE/components/OrderCard.vue:552-559` |
| P2-05 | O relógio do painel ancora no primeiro pedido novo; sem pedido novo, cai no relógio do dispositivo | CONTR | `FE/pages/index.vue:779` |
| P2-06 | "Hoje" recalculado no cliente com o fuso do dispositivo, com o servidor já mandando `service_day` | CONTR | `FE/presentation/queue.ts:226-240`; `FE/components/QueueView.vue:183-188` |
| P2-07 | "Hoje" lido várias vezes na mesma projeção: numa leitura que cruza a meia-noite a encomenda pode sair das duas listas por um ciclo (suspeita, não provada em execução) | CONTR | `OQ:1909`, `:1913-1916`, `:2051`, `:2232` |
| P2-08 | Dia de serviço = dia civil: casa que fecha depois da meia-noite vê as encomendas de amanhã entrarem no turno em curso | CONTR | `OQ:1933-1937` |
| P2-09 | Campos mortos no card (`status_color`, `fulfillment_icon`, `fiscal_state`, `payment_status_label`, `waitlist_deadline_iso`, `change_for_q` e outros): "Pagamento simulado" e "Cobrança recusada" nunca chegam ao card | CONTR | `OQ:396-603`; sem leitor em `FE` nem no kit |
| P2-10 | Código legado vivo: `build_order_queue` sem view consumidora; docstring de `preorders` contradiz o código | CONTR | `OQ:908-1000`, `:936-942` |
| P2-11 | A mesma coisa derivada em dois lugares: rótulo do próximo passo, nome do canal, "tem algo a fazer" | CONTR | `OQ:85-91` × `OO:2345-2349`; `FE/presentation/board.ts:616-627`, `:728-737` × `OA:152` |
| P2-12 | Identificadores em português: `autorizado`, `bloqueio`, `aberto` | CONTR | `OQ:1028`, `:1186`, `:2215`; `FE/pages/[ref].vue:1807` |
| P2-13 | Rótulo que mente: "Abrir e reprocessar" só abre; a Tabela vazia diz "Nenhum pedido precisa de você agora." sendo a lista de todos | COPY (D1) | `FE/components/OrderCard.vue:400-404`; `FE/pages/index.vue:2022` |
| P2-14 | Zero como código secreto: "Em branco usa o total de…"; "Zero apaga: o cartão volta a contar itens." | COPY (D5) | `FE/pages/index.vue:2324`; `FE/components/OrderCardMenu.vue:145` |
| P2-15 | Nota de rodapé do engenheiro no fim da Fila ("Aviso ao cliente só sai depois da janela de desfazer…") | COPY (D6, D8) | `FE/components/QueueView.vue:861-862` |
| P2-16 | Pílula "Por que espera" esconde o fato ("Cobrança recusada") atrás do toque | COPY (D2) | `FE/components/OrderCard.vue:321` |
| P2-17 | "fila" para a tela inteira ("Falha ao atualizar a fila", "Imprimir fila") colide com o modo Fila; "Reembolsado" convive com "Estornado"; evento sem rótulo sai em inglês | COPY (D7) | `FE/pages/index.vue:1848`; `shopman/backstage/presentation/status.py:83`; `OQ:3392`, `:3421`, `:3565-3568` |
| P2-18 | Travessão em texto de tela: `channelLabel` devolve "—" sem canal | COPY | `FE/presentation/board.ts:626` |
| P2-19 | Produção no card sem hora e sem ação: "Produção de X: não começou" | PROM | `FE/presentation/board.ts:1293-1300` |
| P2-20 | O detalhe não mostra o lote que o pedido espera (campo enviado e não lido) | PROM | `OQ:1147`; sem uso em `FE/pages/[ref].vue` |
| P2-21 | A saída para entrega no detalhe é outro diálogo, sem o "vai junto" do painel | FLUXO | `FE/pages/index.vue:2298` × `FE/pages/[ref].vue:1718-1783` |
| P2-22 | Frases que nomeiam controle inexistente: "Reenvie ou copie o link." sem "Copiar link"; "Confira o envio com o responsável" | COPY (D1, D3) | `OQ:3018`, `:2986` |
| P2-23 | Histórico: o "dia" erra no devolvido e no cancelado depois de concluído; a hora da linha não tem rótulo; "hoje" não vira à meia-noite; sem sinal de estorno na linha | CONTR, COPY | `shopman/backstage/projections/order_history.py:150`, `:299-302`; `FE/pages/history.vue:29`, `:271-274` |
| P2-24 | O seed não cria encomenda futura, pedido novo nem estado fiscal: o caso mais complexo da casa não tem massa de teste | CONTR | `config/management/commands/seed.py`; medido no banco da pilha |
| P2-25 | Dinheiro do cancelado: "Pix · Reembolsado" no resumo e "Pagamento estornado" na linha do tempo, na mesma tela; a frase que o cliente lê ("Devolvemos os R$ 18,70 do seu Pix para a mesma conta") não existe no Gestor | CONTR, COPY (D7) | visto na pilha; `shopman/backstage/presentation/status.py:83`; `OQ:1270-1272`; `shopman/shop/projections/order_tracking.py:667-682` |
| P2-26 | Estado saudável com cor de erro: "Aguardando o dia da encomenda" aparece em vermelho no detalhe, e o botão principal vira o mesmo rótulo, desligado | UX | visto na pilha; `FE/pages/[ref].vue` (aviso do bloqueio do avanço); frase em `OO:105-107` |
| P2-27 | Um gesto com dois nomes ("Entregar J40" no Painel, "Marcar como retirado" na Tabela); "meta 5" sem unidade na Fila; "Aguardando Encomendas" (a estação da Cozinha) ao lado da lista "Encomendas" | COPY (D3, D7) | visto na pilha; `FE/pages/index.vue` (Tabela), `FE/components/QueueView.vue` (meta), `FE/presentation/kitchen.ts` |
| P2-28 | Jargão e instrução ao operador no detalhe: "Aparece no ticket da cozinha (KDS)"; "Atalhos gerais do pedido. Use apenas os que se aplicam aos itens.", com "Sem cebola" num pedido de pão | COPY (D6, D7), OMO | visto na pilha; `FE/pages/[ref].vue` |
| P2-29 | Diálogo de recusa em 850 px de altura: o botão de confirmar fica cortado na base, depois de oito motivos, da frase ao cliente e da observação | UX, MOB | visto na pilha; `FE/components/OrderReasonDialog.vue` |

### 4.5 Reclassificados (não são defeito)

- **Recusar pedido pago sem gerente.** A auditoria apontou a assimetria com o cancelar. É
  desenho escrito: ADR-036 §4 ("recusou ou venceu, o dinheiro volta sozinho"). Fica só a nota
  de que a exceção não está escrita em `operator_cancel_policy`.
- **Editar a encomenda no Gestor.** D-002 e D-003 decidiram: o editor só nasce com a
  concierge; hoje é atalho para o PDV. O que sobra é o atalho genérico (P1-10).

## 5. Fronteiras (registrar, não mexer)

`order_queue.py` **não é só do Gestor**: Central (`hub_queue.py:194`), PDV Encomendas
(`preorders.py:530-706`), Cozinha (`kds.py:32`), Entregas (`deliveries.py:148-272`), busca da
suíte e clientes importam dele. Todo WP que muda o contrato do card ou do detalhe roda os
testes dessas projeções e regenera `contracts/projections/*.json`.

| # | O que é | Por que afeta o Gestor | De quem é | Quem mais sente |
|---|---|---|---|---|
| F-1 | Canal com `prep_start` automático vira "Em preparo" no aceite; o ticket nasce "Pendente" (`LC:1004-1011`; só `web` declara `operator`, `nelson.json:287`) | o Gestor diz "Em preparo" sem ninguém ter começado, e o cliente do WhatsApp é avisado disso | lifecycle e config do canal | Cozinha, loja, WhatsApp |
| F-2 | PDV Encomendas chama de "Pago" a encomenda que o Gestor ainda mostra como "Novo" e pode cancelar em 60 min (`preorders.py:680-688`) | o balcão promete o que o Gestor ainda não aceitou | PDV | PDV |
| F-3 | A TV do salão diz "Pronto para retirar" na janela de desfazer do Gestor (`kds.py:860`) | o "Desfazer" faz o pronto sumir da TV | Cozinha | cliente |
| F-4 | Duas estimativas de "fica pronto às": mediana atual no Gestor (`OA:343-368`), tempo fixo na loja (`order_tracking.py:1905-1910`) | o operador diz uma hora e o cliente lê outra | loja | WhatsApp |
| F-5 | **Pedido de hoje com hora combinada vai à Cozinha no aceite** (feito às 9h para as 17h): a espera só vale com `is_preorder`, que é falso no mesmo dia (`LC:1058-1065`; `packages/orderman/shopman/orderman/services/commit.py:493`) | card em preparo horas antes; produto "na hora" feito cedo demais | lifecycle e Core | Cozinha, loja |
| F-6 | **Lote cancelado, atrasado ou que rende menos não vira fato do pedido** (`_stock_receivers.py:54-114`; `production_order_sync.py:171-175`; `production_late` é de público `production` e não nomeia os pedidos) | a promessa quebra sem push ao Gestor (P0-1) | shop (estoque) e Produção | loja, PDV |
| F-7 | O fechamento do dia não olha pedido aberto nem encomenda de hoje não retirada (`shopman/backstage/services/closing.py:80-177`) | pedido de ontem fica no painel sem dono | Central e fechamento | PDV |
| F-8 | "O que é encomenda" tem quatro réguas: commit, Gestor, Cozinha e PDV (`commit.py:493`; `OQ:2048-2051`; `kds.py:1330-1336`; `order_ticket.py:154-157`) e o Gestor e o PDV leem de consultas diferentes (`OQ:1830-1965` × `preorders.py:330-377`) | "uma verdade só" não se sustenta por construção | shop (helper único) | PDV, Cozinha, Central |
| F-9 | Encomenda não paga reagendada para hoje perde `is_preorder` (`shopman/shop/services/reschedule.py:137`) | volta a ser lida como fila e não espera a hora da Cozinha | shop | PDV |
| F-10 | Estorno no gateway só no Admin do Payman, permissão só do Dono | P1-15: o Gerente não resolve um pedido sem o Dono | Payman e `nelson.json` | PDV |
| F-11 | Card fiscal, contato e erro genérico do detalhe moram no `operator-kit` (`OperatorOrderDetail.vue:617-644`; `OperatorOrderContact.vue`) | o conserto do P1-13 e do P1-18 neste plano é uma faixa do próprio Gestor, acima do componente do kit | operator-kit | PDV (detalhe do pedido) |
| F-12 | #2292 (fechar dia avisa os pedidos) em `CONFLICTING` desde 12/11 | encomenda paga em dia fechado sem aviso | quem abriu o #2292 | Admin |
| F-13 | Frases de bloqueio e de alerta escritas no shop: "O preparo abre no dia combinado." sem a data (`OO:105-107`), "Atualize o quadro." (`LC:102`, palavra vetada em 14/11), "o suporte resolve" | chegam ao Gestor como texto de tela | shop | todo app com sino |
| F-14 | A hora da suíte em "12h45" é frente própria (`claude/suite-hora-12h45`) | o detalhe mistura "às 14h32", "14:32" e "03/10 14:32" (`OQ:3020-3028`, `:3654-3658`) | frente da hora | todos |
| F-15 | Seção Entregas e widget do iFood | fora por brief | frentes próprias (DEV-2026-026; #2323, #2455) | - |
| F-16 | No celular, o convite "Vincular este dispositivo a um posto de trabalho?" ocupa um quarto da tela acima do app (visto em 375 px) | sobra um cartão por tela a quem acompanha do telefone | operator-kit | todos os apps de operador |
| F-17 | Entrar logo depois de a sessão vencer pode cair em "Sua sessão terminou": a resposta atrasada de uma chamada com o cookie velho apaga o novo (visto uma vez; `surfaces/operator-kit/server/utils/operatorCookies.ts:158-205` repassa a expiração vazia) | o operador digita a senha duas vezes | operator-kit (BFF) | todos os apps de operador |
| F-18 | Na loja, a primeira adição à sacola num navegador novo se perdeu ao abrir a Sacola (visto uma vez, não reproduzido), e a linha da sacola mostrou "R$ 22,00" com total "R$ 18,70" | é por onde nasce todo pedido do Gestor | Storefront (revisão irmã) | - |

## 6. O salto

| # | Ideia | Ganho para quem opera | Custo | Benchmark |
|---|---|---|---|---|
| S1 | **Promessa em risco.** Quando o lote é cancelado, atrasa ou rende menos, o Gestor lista pedido a pedido quem ficou sem lastro, do mais próximo ao mais distante, cada um com a ação pronta: avisar com a mensagem escrita, remarcar, cancelar com estorno. | A casa descobre antes do cliente, e não na retirada. Resolve o P0-1. | WP-G08 (leitura, no perímetro). O push depende da F-6. | Nenhum faz: a Toast declara que não reserva estoque para pedido futuro; no Hotplate o "prepped" é contador isolado. |
| S2 | **Relógio da promessa.** Toda encomenda mostra duas horas: "Vai para a Cozinha às 16h15 · combinado 17h". Antes da hora, o gesto é "Adiantar", secundário e consciente. A margem muda de cor antes de quebrar. | Acaba o "Iniciar preparo" às 00:00 e o falso atraso. Fecha P1-02 a P1-07. | WP-G01 e WP-G02. | A Toast e a Square disparam por horário menos tempo fixo, mas não mostram ao operador a hora do disparo no cartão. |
| S3 | **Agenda com cobertura.** A lista dos próximos dias vira agenda por dia: quantas encomendas, quantos de cada produto prometidos e quanto a Produção planejou. "Sábado: 42 Kuro Pan prometidos, 38 planejados." | O furo aparece dias antes, quando ainda dá para planejar mais um lote. | WP-G10, depois do G03 e do G08. Leitura do plano da Produção, sem escrever nele. | O Hotplate tem a soma do prometido (Prep list); ninguém cruza com o planejado. |
| S4 | **Não veio, não se perde.** "Não retirado" encerra a espera do pedido pronto, com o destino do dinheiro e do produto perecível no mesmo gesto. | Fecha o beco do P1-08 e o pão volta ao balcão em vez de vencer na prateleira da Saída. | WP-G11, depende da decisão 1 e de transição nova no canal (fronteira). | Nenhum documenta: só política escrita ("no-show não reembolsa"). |
| S5 | **Remarcar com resposta.** A mudança vira proposta ao cliente (novo horário, outro dia ou estorno), e o Gestor vê quem aceitou e quem falta. | Remarcar 12 encomendas de um lote cancelado deixa de ser 12 conversas. | Alto e fora do perímetro: precisa de tela na loja e de aviso. Fica como direção, sem WP neste plano. | O Hotplate só tem SMS em massa, sem resposta por pedido. |

## 7. WPs

Regras comuns a todos:

- A sessão segue a seção **"Teste como um operador de verdade"** de
  `docs/coordination/ROUNDS/EXCELENCIA-base.md`: pela UI, com o papel do roteiro, nunca como
  superusuário, sem atalho de API, Admin ou banco, em 375 px e em 1366 px.
- WP que muda tela mostra **prévia local ao dono antes de enfileirar**.
- WP que muda contrato regenera `contracts/projections/*.json` e roda os testes das projeções
  vizinhas (Central, PDV Encomendas, Cozinha, Entregas).
- Copy pelas regras de `docs/reference/omotenashi-copy.md` e
  `docs/reference/suite-vocabulary.md`; em tela de operador é **lote**, nunca "fornada".
- Fora de todos: a seção Entregas, o widget do iFood, o `operator-kit`, `lifecycle.py`, os
  services do `shop` e `packages/`.

Tamanhos: P (até meio dia) · M (um dia) · G (uma sessão cheia).

---

### WP-G00 · Harness de operador de verdade

- **Objetivo:** o Gestor ganha uma suíte Playwright que roda contra o Django da pilha, com
  login e PIN de verdade, e a jornada J1 nasce nela.
- **Achados que fecha:** P2-24 (a parte de massa de teste que cabe no próprio teste).
- **Dependências:** nenhuma.
- **Arquivos:** `surfaces/orders-nuxt/playwright.operator.config.ts` (novo),
  `surfaces/orders-nuxt/tests/operator/**` (novo), `surfaces/orders-nuxt/package.json`
  (script `test:operator`), `surfaces/orders-nuxt/tests/e2e/README.md`.
- **Fora do escopo:** o CI (`surfaces-gate.yml`); os e2e de backend simulado, que continuam.
- **Pronto quando:**
  - roteiro: Gerente provisiona o dispositivo, Caixa entra com PIN; cliente novo faz na loja
    um pedido de retirada para hoje e paga; o Caixa aceita, inicia, a Cozinha dá Pronto, o
    Caixa entrega. Capturas em 375 e 1366.
  - testes: `npm run test:operator` verde, com a J1 escrita com os mesmos papéis e passos.
- **Muda tela:** não. **Tamanho:** M.
- **Brief:** leia `docs/coordination/ROUNDS/EXCELENCIA-base.md` ("Teste como um operador de
  verdade"), a seção 1 deste plano, `surfaces/orders-nuxt/tests/e2e/README.md` e
  `playwright.integration.config.ts`. Monte uma suíte nova em `tests/operator/` que sobe o
  Gestor compilado contra um Django já de pé (URL por variável de ambiente; a suíte recusa
  rodar sem ela). Os papéis vêm de `shopman/shop/management/commands/setup_operators.py`. O
  pedido nasce pela loja, nunca por API. Escreva a J1 e um README de como subir a pilha.

### WP-G01 · A encomenda se anuncia

- **Objetivo:** todo pedido com data ou hora combinada diz isso, com as mesmas palavras, em
  toda forma em que aparece.
- **Achados que fecha:** P1-01, P1-06, P1-07, P2-04.
- **Dependências:** nenhuma.
- **Arquivos:** `shopman/backstage/projections/order_queue.py` (card), o tipo do card em
  `surfaces/orders-nuxt/app/types/`, `OrderCard.vue`, `QueueView.vue`, `pages/index.vue`
  (Tabela), `composables/useAlerts.ts`, `presentation/board.ts`, testes e contrato gerado.
- **Fora do escopo:** hora de ir à Cozinha (G02); lista de Encomendas (G03).
- **Pronto quando:**
  - roteiro: cliente encomenda pela loja para daqui a dois dias, com janela, e paga. O Caixa
    vê o pedido novo no Painel, na Fila, na Tabela e no sino, e nos quatro lê "Encomenda" com
    o dia e a janela antes de aceitar. Um pedido de hoje com hora combinada mostra a hora no
    cartão. Capturas em 375 e 1366.
  - testes: projeção (`schedule_label` e o estado "vencida" no card), componentes, e a J3
    (aceite com a data à vista).
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia a seção 4.1 e os achados P1-01, P1-06 e P1-07. Publique no card o rótulo
  curto da promessa a partir de `fulfillment_window.window_label` e `promised_at` (a mesma
  função do detalhe, `order_queue.py:1407-1421`), para hoje, futuro e passado: o passado tem
  nome próprio ("Era para ontem, 18h"). Mostre no cartão enxuto, na linha da Fila, na Tabela e
  no "Aceitar" do sino. Não mude o `commitment_date_display` de quem já o lê sem conferir
  Central e PDV. Vocabulário: "Encomenda", nunca "Agendado".

### WP-G02 · A hora da Cozinha no Gestor

- **Objetivo:** a encomenda do dia só pede gesto quando chega a hora dela, e o cartão diz
  quando é.
- **Achados que fecha:** P1-02, P1-03, P1-04, P1-05.
- **Dependências:** WP-G01.
- **Arquivos:** `order_queue.py` (card), `order_attention.py`, `OrderCard.vue`,
  `QueueView.vue`, `presentation/queue.ts`, `presentation/board.ts`,
  `composables/useOrdersBoard.ts`, testes e contrato.
- **Fora do escopo:** `lifecycle.py` e a política de preparo; o pedido de hoje com hora
  combinada que vai cedo à Cozinha (F-5).
- **Pronto quando:**
  - roteiro: com uma encomenda aceita para hoje às 17h, o Caixa abre o Gestor de manhã e lê
    "Vai para a Cozinha às 16h15 · combinado 17h", sem âmbar, sem alarme, com "Adiantar" como
    gesto secundário. Depois da hora, o cartão pede "Iniciar preparo" e o relógio conta da
    chegada à Cozinha. Capturas em 375 e 1366.
  - testes: `order_attention` (sem `attention` antes da liberação; relógio a partir de
    `kitchen_released_at`), `useOrdersBoard` (a virada do dia não zera os vistos de quem já
    estava na tela), componentes. A J4 fica coberta por teste de projeção com relógio
    congelado e por teste de componente: a pilha não tem relógio de teste.
- **Muda tela:** sim (prévia). **Tamanho:** G.
- **Brief:** leia a seção 4.1, os achados P1-02 a P1-05,
  `shopman/shop/policies/preorder_kitchen_policy.py` e
  `shopman/shop/tests/test_preorder_kitchen_release.py`. Publique no card `kitchen_release_at`
  (de `lifecycle.preorder_activation_at`, só leitura) e `kitchen_released_at`. Antes da
  liberação, `resolve_attention` devolve vazio e o gesto de iniciar é secundário, com o rótulo
  "Adiantar". O tempo de etapa conta da liberação ou do início, nunca de `created_at`. A
  decisão de 06/11 continua valendo: a verdade é da Cozinha e o Gestor é atalho.

### WP-G03 · A lista de Encomendas que responde

- **Objetivo:** a lista dos próximos dias responde, por linha, quando, como, se está paga e
  se a produção cobre, e leva ao pedido certo no PDV para remarcar.
- **Achados que fecha:** P1-09, P1-10, P2-02, P2-03.
- **O que não pode faltar:** quem aceita uma encomenda vê para onde ela foi (o aceite
  aponta a linha em "Encomendas"), e a lista é alcançável sem rolar às cegas.
- **Dependências:** WP-G01.
- **Arquivos:** `OrderPreorderList.vue`, `presentation/preorderList.ts` (novo),
  `pages/index.vue` (posição da lista e `<MoreBelow />`), testes.
- **Fora do escopo:** editar ou remarcar dentro do Gestor (D-002, D-003); a cobertura de
  produção por dia (G10).
- **Pronto quando:**
  - roteiro: o Caixa aceita uma encomenda e vê, sem rolar, que ela foi para "Encomendas" e
    em que dia. Com três encomendas aceitas em dois dias diferentes, lê em cada linha o
    dia, a janela, "Retirada" ou "Entrega" e o pagamento; a que espera pagamento diz
    "Aguardando pagamento", e não "Precisa de você"; "Remarcar no PDV" abre aquela encomenda
    no PDV. Em 375 px a linha quebra em duas e a tela avisa que há encomendas abaixo. Capturas
    em 375 e 1366.
  - testes: apresentação pura e componente; a J3 ganha o passo "vive na lista dos próximos
    dias".
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia os achados P1-09 e P1-10 e a seção "Tem mais abaixo" do
  `surfaces/operator-kit/README.md`. A linha usa os campos que o WP-G01 publicou e os que o
  card já tem (`fulfillment_label`, `awaiting_work_orders`, pagamento). O atalho aponta para
  `/preorders/<ref>` do PDV, pela mesma `useOperatorAppLink`. Não crie rota de remarcar no
  Gestor.

### WP-G04 · Histórico honesto

- **Objetivo:** quem procura um pedido no Histórico acha, e a linha diz de que dia e de que
  dinheiro está falando.
- **Achados que fecha:** P1-21, P2-23.
- **Dependências:** nenhuma.
- **Arquivos:** `pages/history.vue`, `presentation/history.ts`,
  `composables/useOrderHistory.ts`, `shopman/backstage/api/order_history.py`,
  `shopman/backstage/projections/order_history.py`, testes.
- **Fora do escopo:** exportação (vira issue `ficou-de-fora` do próprio WP, se o dono quiser).
- **Pronto quando:**
  - roteiro: o Gerente busca pelo nome um cliente que comprou ontem; a tela diz que procurou
    só em hoje e oferece "Buscar nos últimos 28 dias"; a linha do cancelado diz o destino do
    dinheiro; a hora da linha tem rótulo. Capturas em 375 e 1366.
  - testes: projeção (dia pelo carimbo do status atual), apresentação, e a J7.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia o achado P1-21 e a linha P2-23. O período padrão aparece escrito mesmo
  quando é o padrão. O "hoje" vem do servidor. Não mude o eixo do B.I. (`date_basis`).

### WP-G05 · O detalhe tem o gesto

- **Objetivo:** o detalhe do pedido abre com uma faixa "O que falta neste pedido", e cada
  linha dela tem o botão que resolve.
- **Achados que fecha:** P1-13, P1-14, P1-15 (a parte visível), P1-16, P1-19, P1-20, P2-20,
  P2-22, P2-25, P2-26, P2-28.
- **Dependências:** nenhuma de código; roda depois do G02 porque toca `order_queue.py`.
- **Arquivos:** `order_queue.py` (detalhe), `pages/[ref].vue`,
  `components/OrderDetailPending.vue` (novo), `composables/useOrderDetail.ts`,
  `presentation/gestorSections.ts`, testes e contrato.
- **Fora do escopo:** o `operator-kit` (a faixa é do Gestor, acima do componente do kit,
  F-11); tentar o estorno de novo (G13, decisão 3); o texto dos alertas (F-13).
- **Pronto quando:**
  - roteiro: o Gerente cancela, com PIN, uma encomenda paga antes do preparo; o detalhe do
    cancelado diz "Estorno pedido" e depois "Estornado", com a mesma frase que o cliente lê
    na loja. Quem só expede abre um pedido pelo sino e lê por que não pode abrir, e não "não
    encontrado". Capturas em 375 e 1366.
  - testes: projeção (cada pendência com a sua ação; estorno em três estados; DANFE no
    detalhe), componente, e as J5 e J8. Os estados fiscais ficam por teste de projeção: a
    pilha não emite nota (seção 1).
- **Muda tela:** sim (prévia). **Tamanho:** G.
- **Brief:** leia os achados P1-13 a P1-16, P1-19 e P1-20 e a fronteira F-11. O detalhe ganha
  no contrato uma lista de pendências, cada uma com rótulo, motivo e a ação já existente
  (reprocessar a nota, imprimir a DANFE, reenviar a cobrança). A cobrança vencida (P1-16)
  entra ali como um fato só, com o gesto ao lado; espera saudável não usa cor de erro. O dinheiro do cancelado usa o
  mesmo `cancelled_money` que a loja lê. O 403 do detalhe ganha texto próprio. Não escreva no
  `operator-kit`.

### WP-G06 · Recusar e bloquear sem surpresa

- **Objetivo:** quem recusa sabe o que acontece com o dinheiro antes de confirmar, e todo
  bloqueio tem o motivo à vista e o gesto ao lado.
- **Achados que fecha:** P1-11, P1-12, P2-01, P2-13, P2-16, P2-29.
- **Dependências:** nenhuma.
- **Arquivos:** `pages/index.vue` (diálogo de recusa), `OrderReasonDialog.vue`,
  `OrderCardActions.vue`, `OrderCardNotices.vue`, testes.
- **Fora do escopo:** quem pode recusar (ADR-036); `QueueView.vue`, que é do G08 na mesma
  onda: a ação do bloqueio na Fila entra lá.
- **Pronto quando:**
  - roteiro: o Caixa recusa um pedido pago e lê no diálogo "O Pix de R$ 48,00 volta ao
    cliente" antes de confirmar; com a rede cortada, o erro aparece dentro do diálogo. No
    tablet, o "Aceitar" travado mostra o motivo sem depender de hover. Capturas em 375 e 1366.
  - testes: componentes, e a J2.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia os achados P1-11 e P1-12. O efeito do dinheiro vem do detalhe do pedido,
  buscado ao abrir o diálogo: não acrescente campo ao card neste WP. O diálogo diz qual
  pedido (código, cliente e total), esconde o motivo que contradiz o pedido (entrega numa
  retirada, pagamento não confirmado num pago), mantém o confirmar sempre à vista e recebe o
  erro e o `field`. Botão secundário respeita `disabled` e mostra o motivo como texto.

### WP-G07 · Avisar o cliente com um toque (decisão 4: pela API, 17/11/2026)

- **Objetivo:** "Avisar o cliente" envia a mensagem certa para o caso com um toque, pela API,
  e o pedido guarda o que foi enviado. O recibo com falha tem o botão que a frase pede.
- **Achados que fecha:** P1-18. Fecha a #2407 se cobrir o "Copiar mensagem".
- **Dependências:** WP-G05 e WP-G12 (mesmo arquivo `[ref].vue`); a #2421 resolvida antes ou
  dentro deste WP; os três modelos aprovados pela Meta.
- **Arquivos:** `presentation/contactRequest.ts`, `pages/[ref].vue`,
  `OrderNotificationReceipts.vue`, a rota em `operations.py` e `urls.py`, testes. O envio usa o
  caminho de notificação que o `shop` já tem; se ele precisar mudar, é fronteira: pare,
  escreva o que falta no PR e abra a issue.
- **Fora do escopo:** contato no card do painel (#2434, privacidade); mensagem livre digitada
  pelo operador.
- **Pronto quando:**
  - roteiro: no detalhe de uma encomenda, o Caixa escolhe "Vai atrasar", "Faltou um item" ou
    "Precisamos remarcar", lê a mensagem com o nome, o pedido e a hora já escritos, na voz da
    casa, e toca em enviar. A tela diz que enviou, o recibo aparece no pedido, e a falha de
    envio aparece como falha, com o plano B (abrir o WhatsApp do operador com o mesmo texto).
    O roteiro roda com o adapter de simulação: nenhuma mensagem real é enviada pelo teste.
    Capturas em 375 e 1366.
  - testes: apresentação pura das três mensagens, a rota (permissão, idempotência, falha do
    provedor) e o componente.
- **Muda tela:** sim (prévia, e a copy das três mensagens passa pelo dono antes de ir à
  aprovação da Meta). **Tamanho:** G.
- **Brief:** leia o achado P1-18, a decisão 4 na seção 10, a voz da concierge em
  `docs/reference/omotenashi-copy.md`, a #2407 e a #2421. Um toque, sem campo para preencher.
  Sem travessão; emoji só os da casa. Nunca diga "enviado" sem a confirmação do provedor.

### WP-G08 · Promessa em risco

- **Objetivo:** todo pedido aceito cuja reserva perdeu lastro aparece no Gestor com esse nome
  e com a ação ao lado.
- **Achados que fecha:** P0-1 (lado do Gestor), P1-22, P2-19; a ação do bloqueio na Fila
  (resto do P1-12).
- **Dependências:** WP-G02.
- **Arquivos:** `shopman/backstage/projections/order_promise.py` (novo), `order_queue.py`
  (uma chamada), `OrderCard.vue`, `QueueView.vue`, `presentation/board.ts`,
  `presentation/queue.ts`, testes e contrato.
- **Fora do escopo:** o evento e o alerta no cancelamento do lote (F-6); remarcar com resposta
  do cliente (S5).
- **Pronto quando:**
  - roteiro: com uma encomenda paga e aceita que depende de um lote planejado, quem opera a
    Produção cancela o lote pela tela dela. O Gestor mostra o pedido em "Promessa em risco",
    dizendo qual item ficou sem lastro, com "Avisar o cliente", "Remarcar no PDV" e "Cancelar
    pedido". Um pedido pago do dia que espera o lote volta a ter o selo e o bloqueio.
    Capturas em 375 e 1366.
  - testes: projeção (reserva íntegra, parcial e perdida; lote cancelado, atrasado e com
    rendimento menor), componentes, e a J6.
- **Muda tela:** sim (prévia). **Tamanho:** G.
- **Brief:** leia o P0-1, a fronteira F-6, `shopman/shop/handlers/_stock_receivers.py` e
  `production_order_sync.py` (só para entender; não mexa). A leitura é de holds e de lotes,
  numa consulta por painel e não por pedido. O selo deixa de depender do estado da fila de
  espera (`waitlist.py:514-518`). A J6 precisa da Produção na pilha, com o papel Cozinha.

### WP-G09 · Contrato limpo

- **Objetivo:** o contrato do Gestor fica só com o que alguém lê, com um relógio e um "hoje".
- **Achados que fecha:** P2-05 a P2-12, P2-17, P2-18, P2-27.
- **Dependências:** WP-G08.
- **Arquivos:** `order_queue.py`, `pages/index.vue`, `QueueView.vue`, `presentation/board.ts`,
  `presentation/queue.ts`, `presentation/kitchen.ts`, tipos, testes e contrato.
- **Fora do escopo:** o formato "12h45" (F-14); `useNowTick` do kit.
- **Pronto quando:**
  - roteiro: o Caixa percorre Painel, Fila e Tabela e não vê diferença além das palavras
    corrigidas; "Pagamento simulado" e "Cobrança recusada" aparecem no cartão. Capturas em 375
    e 1366.
  - testes: os de projeção das vizinhas (Central, PDV Encomendas, Cozinha) verdes; trava nova
    que reprova campo do card sem leitor.
- **Muda tela:** sim, pouco (prévia). **Tamanho:** M.
- **Brief:** leia as linhas P2-05 a P2-12 e a seção 5 (quem mais importa `order_queue.py`).
  Antes de apagar um campo, prove com busca que nem o Gestor, nem o kit, nem as vizinhas o
  leem. Um `today` por projeção; o relógio do painel ancora em `generated_at`.

### WP-G10 · Agenda com cobertura

- **Objetivo:** a lista dos próximos dias mostra, por dia, o prometido de cada produto ao
  lado do que a Produção planejou.
- **Achados que fecha:** nenhum do laudo; é o salto S3.
- **Dependências:** WP-G03 e WP-G08.
- **Arquivos:** `shopman/backstage/projections/preorder_coverage.py` (novo),
  `shopman/backstage/api/urls.py` e `operations.py` (uma rota de leitura),
  `OrderPreorderList.vue`, `components/PreorderDayCoverage.vue` (novo), testes e contrato.
- **Fora do escopo:** planejar ou alterar lote a partir do Gestor.
- **Pronto quando:**
  - roteiro: com encomendas que somam mais do que o lote planejado de um dia, o Gerente lê no
    cabeçalho daquele dia o que falta e abre a Produção naquele dia. Capturas em 375 e 1366.
  - testes: projeção e componente.
- **Muda tela:** sim (prévia). **Tamanho:** G.
- **Brief:** leia o salto S3 e o `production-nuxt` só para saber para onde o atalho aponta.
  Leitura do plano por dia e produto, sem escrever. Em tela de operador é "lote".

### WP-G11 · Não retirado (decisão 1: a casa fica só com a perda, 17/11/2026)

- **Objetivo:** o pedido pronto que ninguém veio buscar tem saída, com o destino do dinheiro
  e do produto.
- **Achados que fecha:** P1-08.
- **Dependências:** a regra da retenção escrita nos Termos da loja e mostrada à cliente antes
  de pagar a encomenda (frente da loja, #2613); o lado do `shop` no `main`
  (política, serviço, régua do pagamento, conciliação, perda, transição dos canais: fronteira,
  frente da coordenação); a #2604; WP-G12 (mesmos arquivos).
- **Arquivos:** `operations.py` e `urls.py` (a rota), `pages/[ref].vue`, `OrderCardMenu.vue`,
  testes.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia o P1-08 e o mapa da decisão 1 na seção 10. Gesto de Gerente, da lista, com
  PIN, numa autorização só. A prévia vem calculada do servidor: destino de cada linha, o
  dinheiro por extenso e o texto ao cliente, antes de confirmar. Antes da hora o item aparece
  desabilitado com o motivo; no iFood o item não aparece.

### WP-G12 · Registrar devolução (decisão 2: sim, 17/11/2026)

- **Objetivo:** a devolução ganha a porta que o Histórico e a referência já anunciam.
- **Achados que fecha:** P1-17.
- **Dependências:** nenhuma pendente. Divide arquivos com o WP-G11 (que espera a decisão 1 e
  entra depois), com o WP-G07 e com o WP-G13: nunca ao mesmo tempo que eles.
- **Arquivos:** `operations.py` e `urls.py` (rota sobre `ReturnService.initiate_return`),
  `pages/[ref].vue`, `components/OrderReturnDialog.vue` (novo), testes;
  `docs/reference/cenarios-de-pedido.md` (a linha que hoje mente).
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia o P1-17 e `shopman/shop/handlers/returns.py`. Itens, quantidade, motivo e
  PIN de Gerente; o diálogo diz o valor que volta antes de confirmar.

### WP-G13 · Tentar o estorno de novo (decisão 3: sim, 17/11/2026)

- **Objetivo:** o Gerente resolve o estorno que falhou sem o Dono e sem o Admin.
- **Achados que fecha:** P1-15 (a parte da ação).
- **Dependências:** WP-G05 e WP-G12 (mesmos arquivos).
- **Arquivos:** `operations.py` e `urls.py` (rota sobre `payment.refund_intent_at_gateway`),
  `OrderDetailPending.vue`, testes.
- **Muda tela:** sim (prévia). **Tamanho:** P.
- **Brief:** leia o P1-15 e a F-10. A mesma assinatura do cancelamento de pedido pago; chave
  de idempotência por tentativa.

### WP-G14 · Canal Google: a retirada diz a verdade, item a item (17/11/2026, issue #2652)

- **Objetivo:** o que a casa envia ao Google sobre a retirada de cada item é o mesmo fato que a
  Loja mostra ao cliente, e a aba Canais diz se o Google aprovou ou negou os dois recursos da
  loja física, sem o dono depender do e-mail.
- **Achado que fecha (medido no `main` em 17/11/2026, fora do laudo original):**
  `shopman/shop/adapters/catalog_projection_google.py:186-200` (`build_local_inventory`) envia
  `pickupSla: "SAME_DAY"` fixo para todo item, inclusive o que só fica pronto amanhã. O Google
  cruza o inventário local com a página do produto; a divergência sozinha nega a "retirada no
  mesmo dia" (recusa de 01/11/2026 no Merchant Center, issue #2652). O
  `display_catalog.DisplayItem` nem carrega o dia de pronto: só `available`.
- **Dependências:** **WP-L01 da Loja no `main`** (#2582, a promessa de quando). A outra metade
  da issue é da Loja (WP-L02, a página do produto nomeia a loja e diz quando fica pronto) e
  **não** é deste WP. Não divide arquivo com nenhum outro WP do Gestor.
- **Duas entregas, dois PRs:**
  - **G14a · o envio (não muda tela, vai direto para a fila).** O `pickupSla` sai, item a
    item, do dia em que o item fica pronto: `SAME_DAY` se é hoje, `NEXT_DAY` se é amanhã,
    `TWO_DAY` a `SEVEN_DAY` e `MULTI_WEEK` além disso (valores da Merchant API, conferidos na
    referência de `LocalInventoryAttributes` em 17/11/2026). Arquivos:
    `shop/adapters/catalog_projection_google.py`, `shop/services/display_catalog.py` (o item
    passa a carregar o dia de pronto), `shop/tests/test_catalog_projection_google.py`.
  - **G14b · a aba Canais (muda tela, prévia local do dono antes da fila).** O card do Google
    ganha dois itens no checklist: "Retirada no mesmo dia" e "Disponibilidade na loja", cada
    um com o estado que o Google devolve. Arquivos: `backstage/projections/channel_health.py`,
    `backstage/tests/test_channel_health.py`, `contracts/projections/*.json`, e no Gestor
    `presentation/channelHealth.ts`, `types/channelHealth.ts`,
    `components/ChannelHealthChecklist.vue` e os testes deles.
- **Muda tela:** G14a não; G14b sim (prévia). **Tamanho:** M (G14a) + M (G14b).
- **Fronteira declarada:** o G14a escreve em `shop/adapters` e num service do `shop`
  (`display_catalog.py`), que as regras comuns deixam fora. É exceção atribuída pela
  coordenação em 17/11/2026 e vale só para esses dois arquivos.
- **Três coisas que a sessão mede antes de escrever, porque o plano não as provou:**
  1. **De onde vem o fato.** O WP-L01 junta a promessa em
     `shopman/storefront/services/promise_facts.py`, e o `shop` não importa o `storefront`. O
     envio ao Google precisa ler os mesmos services do `shop` que o L01 lê
     (`waitlist.next_batch_availability_for_skus`, `availability.stock_on_dates`,
     `product_readiness.ready_times_for`) ou o fato desce para o `shop` num lugar só. O que
     não pode: uma segunda conta do dia de pronto. A prova é um teste que, para os mesmos
     SKUs e o mesmo instante, compara o dia que vai ao Google com o dia do `ready_promise`.
  2. **Quando o envio se refaz.** "Pronto hoje" vira "pronto amanhã" quando passa o corte do
     dia ou quando um lote é cancelado. Medir a cadência do envio ao Google e dizer no PR em
     quanto tempo o `pickupSla` acompanha a virada.
  3. **O que o Google devolve sobre os recursos.** A Merchant API tem
     `accounts/{conta}/omnichannelSettings` (leitura), com `pickup.state` e `inStock.state`
     em `ACTIVE`, `FAILED`, `RUNNING` ou `ACTION_REQUIRED`. Pela referência (17/11/2026)
     **o recurso não traz o motivo da recusa em texto**. Conferir com uma leitura na conta
     real se o motivo vem por outro recurso (só leitura, e usar a credencial da conta pede a
     palavra do dono, pela coordenação); se não vier, Canais mostra o estado e diz onde o
     motivo está (Merchant Center), e o PR declara isso em vez de inventar texto.
- **Critérios de pronto:**
  - item que só fica pronto amanhã vai com `NEXT_DAY`; o de hoje, com `SAME_DAY`; teste por
    caso, com relógio congelado antes e depois do corte;
  - **item sem promessa não anuncia retirada** (recomendação: o dado que falta fecha a
    promessa, nunca cai em `SAME_DAY`); a sessão confere como a API aceita esse caso;
  - o código da loja no Perfil da Empresa (`store_code`) está preenchido no ambiente vivo;
    vazio, o inventário local não é enviado (`catalog_projection_google.py:349`) e Canais
    passa a dizer isso como item do checklist, com a ação no Admin;
  - Canais mostra os dois recursos com estado legível ao operador, sem nome de API nem
    variável (defeito D6 de `docs/reference/omotenashi-copy.md`), e a leitura que falha diz
    que falhou em vez de mostrar "aprovado";
  - nenhuma chamada ao Google nos testes (respostas gravadas); na conta real, só leitura e
    só com a palavra do dono.
- **Fora deste WP:** pedir a revisão dos dois recursos no Merchant Center. É ação do dono,
  pela coordenação, e só depois de G14a, G14b e WP-L02 no ar (pedir antes repete a recusa).
- **Brief:** leia a issue #2652 inteira (corpo e os dois comentários), o cabeçalho de
  `catalog_projection_google.py`, `display_catalog.py` e `promise_facts.py` do WP-L01. Comece
  pelo G14a.

## 8. Jornadas a canonizar

Todas em `surfaces/orders-nuxt/tests/operator/`, contra o Django da pilha, com o papel e os
passos da pessoa.

| # | Jornada | Papel | Passos | WP que escreve |
|---|---|---|---|---|
| J1 | Pedido de hoje, de ponta a ponta | cliente novo; Caixa com PIN; Cozinha | pedir e pagar na loja → aceitar → iniciar → Pronto na Cozinha → entregar | G00 |
| J2 | Recusar com motivo | cliente; Caixa | pedir e pagar → recusar com motivo → ler o destino do dinheiro → o cliente lê o cancelamento | G06 |
| J3 | Encomenda: do pedido à lista dos próximos dias | cliente que volta; Caixa | encomendar para outro dia e pagar → aceitar lendo dia e janela → ver na lista dos próximos dias → abrir no PDV | G01 (até o aceite), G03 (a lista) |
| J4 | Encomenda no dia: a hora da Cozinha | Caixa | abrir o Gestor antes e depois da hora de ir à Cozinha | G02, por projeção com relógio congelado e componente (a pilha não tem relógio de teste) |
| J5 | Cancelar encomenda paga e ver o dinheiro | Gerente com PIN | cancelar antes do preparo → detalhe diz "Estorno pedido" → "Estornado" | G05 |
| J6 | Lote cancelado vira promessa em risco | Cozinha na Produção; Caixa no Gestor | cancelar o lote → o Gestor mostra o pedido em risco com a ação | G08 |
| J7 | Achar o pedido de ontem | Gerente | buscar pelo nome → ampliar o período → abrir o pedido | G04 |
| J8 | Quem só expede abre o sino | Cozinha | abrir um alerta de pedido → ler por que não abre o detalhe | G05 |

## 9. Ondas

Dois WPs da mesma onda nunca tocam o mesmo arquivo. `order_queue.py` é o gargalo: no máximo
um WP por onda escreve nele.

| Onda | WPs em paralelo | Quem escreve em `order_queue.py` |
|---|---|---|
| 0 | **G00** (harness) · **G01** (a encomenda se anuncia) | G01 |
| 1 | **G02** (hora da Cozinha) · **G03** (lista de Encomendas) · **G04** (Histórico) | G02 |
| 2 | **G05** (o detalhe tem o gesto) · **G06** (recusar e bloquear) | G05 |
| 3 | **G07** (avisar o cliente, depois do G12) · **G08** (promessa em risco) | G08 |
| 4 | **G09** (contrato limpo) · **G10** (agenda com cobertura) | G09 |
| 5 | **G12 → G11 → G13**, em fila (mesmos arquivos). G12 e G13 liberados em 17/11/2026; o G11 espera os Termos da loja e o lado do `shop`, e se demorar o G13 passa à frente | nenhum |
| fora das ondas | **G14** (canal Google), em dois PRs: G14a (envio) e depois G14b (Canais). Espera o WP-L01 da Loja no `main` (#2582) e não divide arquivo com nenhum outro WP do Gestor | nenhum |

Conferência dos arquivos por onda:

- Onda 0: G00 só cria arquivos em `tests/operator/` e mexe em `package.json`.
- Onda 1: G02 fica com `OrderCard.vue`, `QueueView.vue`, `queue.ts`, `board.ts` e
  `useOrdersBoard.ts`; G03 com `OrderPreorderList.vue` e `pages/index.vue`; G04 com o
  Histórico.
- Onda 2: G05 fica com `[ref].vue` e `gestorSections.ts`; G06 com `pages/index.vue`,
  `OrderReasonDialog.vue`, `OrderCardActions.vue` e `OrderCardNotices.vue`.
- Onda 3: G07 fica com `[ref].vue`, `contactRequest.ts`, `OrderNotificationReceipts.vue` e a
  rota de envio em `operations.py` e `urls.py` (por isso só depois do G12);
  G08 com `OrderCard.vue`, `QueueView.vue`, `board.ts` e `queue.ts`.
- Onda 4: G09 fica com `pages/index.vue`, `QueueView.vue`, `board.ts`, `queue.ts` e
  `kitchen.ts`; G10 com
  `OrderPreorderList.vue`, `operations.py` e `urls.py`.
- Fora das ondas: G14a fica com `catalog_projection_google.py` e `display_catalog.py`; G14b
  com `channel_health.py`, `channelHealth.ts` e `ChannelHealthChecklist.vue`. Nenhum outro WP
  deste plano abre esses arquivos.

## 10. Decisões do dono

Procurado antes em `docs/coordination/DECISIONS.md`, `docs/reference/` e ADR-035 e ADR-036:
nenhuma das quatro tinha resposta escrita.

**Respostas do dono em 17/11/2026** (falas literais, dadas à coordenação e conferidas no
transcript dela):

| Decisão | Resposta | Efeito |
|---|---|---|
| 1. "Não retirado" | **Decidida no principal: a casa fica só com o valor da perda.** "Dependendo do horário isso vira perda! Precisa de alguma regra para isso. Sugestões? Sobre o dinheiro, depende de como está o status do pagamento e da forma de pagamento: estorno, retorno do troco para o Caixa, simples cancelamento com motivo (BI)... um mapa de decisões." O mapa e as respostas estão abaixo. | WP-G11 espera os Termos da loja e o lado do `shop`. |
| 2. Devolução pelo Gestor | **Sim** ("2) ok"). | WP-G12 liberado (PR #2607). |
| 3. Gerente tenta de novo o estorno que falhou | **Sim** ("3) ok"). | WP-G13 liberado. |
| 4. Três mensagens prontas de "Avisar o cliente" | **Pela API, não pelo WhatsApp do operador.** "API, claro! Deve ser ridiculamente facil para o operador, alem de sempre buscarmos as soluções mais simples, robustas e ELEGANTES!!!" | WP-G07 muda de desenho (abaixo). |

**Decisão 4, como fica.** As três mensagens saem pela API (ManyChat), com um toque no Gestor,
e o envio fica registrado no pedido. Como é mensagem que a casa inicia pela API, cada uma das
três precisa de **um modelo aprovado pela Meta**; a aprovação é etapa do WP-G07 e pode ter
custo por mensagem, conforme a tabela da Meta. O link `wa.me` (o WhatsApp do próprio operador
com o texto pronto) fica só como plano B, quando o envio pela API falha, e a tela avisa que
falhou. Pré-requisito: a #2421 (o ManyChat responde sucesso sem entregar) resolvida antes ou
dentro do WP-G07, porque "enviado" que não chegou é pior que não enviar.

**Decisão 1, o mapa (coordenação, 17/11/2026).** A regra cabe numa frase: **o dinheiro
segue o produto.** Produto que volta a ser vendável devolve o dinheiro ao cliente; produto que
vira perda deixa com a casa o valor daquela perda. O pedido termina sempre como cancelado, com
motivo próprio (`not_picked_up`), e a retenção fica escrita num bloco só
(`order.data["no_show"]`).

| Caso | Dinheiro | Produto |
|---|---|---|
| Não pago (cobrar na retirada) | nada a devolver | vendável volta ao balcão no mesmo lote; o resto vira perda com motivo |
| Conta da casa | a dívida das linhas devolvidas morre; a das perdidas segue a pergunta 1 | igual |
| Pago em dinheiro | o devolvível entra em "Devolver em dinheiro" e espera o cliente; o retido fica na gaveta | igual |
| Pago na maquininha | o devolvível vira "Estornar na maquininha"; o retido fica | igual |
| Pago por Pix ou cartão online | estorno automático do devolvível; o retido não volta | igual |
| iFood | fora do gesto: quem encerra é o iFood | nada local |
| Entrega que já saiu | não é "não retirado": é devolução | segue a devolução |

Hora: o botão aparece, para o **não pago**, depois da hora combinada mais a tolerância; para o
**pago**, só a partir do corte do dia. Antes da hora o item aparece desabilitado, com o motivo.
Quem faz é o Gerente, escolhido da lista, com PIN, numa autorização só; a tela mostra antes de
confirmar o destino de cada linha, o dinheiro por extenso e o texto que o cliente recebe.

**As cinco perguntas do mapa, e como ficaram em 17/11/2026:**

1. Pedido pago em que parte virou perda: **a casa fica só com o valor do que virou perda e
   devolve o resto.** Resposta literal do dono: "Sim, só a perda. Mas isso precisa estar
   amparado em algum documento do tipo Políticas comerciais, Termos de serviço ou algo que o
   valha, confere?"
2. O pedido pago espera o corte do dia para o botão aparecer: **sim** (padrão).
3. Tolerância do não pago: **60 minutos** depois da hora combinada (padrão).
4. Corte do dia: **no fechamento** (padrão de 0 minuto antes de fechar). A recomendação era
   30 minutos antes, mas os Termos da loja já prometem que a loja "guarda até o fim do
   expediente do dia combinado" (`surfaces/storefront-nuxt/app/pages/termos.vue`), e o gesto
   não pode chegar antes da promessa (#2613).
5. O fechamento do dia segura enquanto houver pedido pronto não resolvido: **sim**, lista e
   resolve com uma autorização só (padrão).

Só a 1 tem a palavra escrita do dono. As de 2 a 5 entram como padrão pela recomendação: a
coordenação informa que ele as viu e não discordou. Os valores de 2 a 4 ficam editáveis no
Admin (`Shop.defaults["no_show"]`), nunca em env, e a casa troca sem código.

**Pré-requisito que a resposta do dono criou.** Reter o valor da perda só vale se a regra
estiver escrita nos Termos da loja (ou política comercial equivalente) e aparecer à cliente
**antes de pagar a encomenda**. Sem isso o WP-G11 não liga a retenção. É frente da loja
(Storefront e documentos legais), fora deste plano, na issue #2613: a cláusula do pedido não
retirado, a linha no checkout antes do pagamento, a versão nova dos Termos arquivada e a
leitura de advogado ou contador antes de publicar.

Para o contador, não para o dono: valor retido de pedido que não saiu pede algum documento?

**O que o mapa mediu e muda o WP-G11.** O gesto no Gestor é a parte pequena. Antes dele, o
`shop` precisa de: a política e o serviço de não retirado, a régua do pagamento que aceite o
retido, a conciliação financeira que não acuse o retido como erro, a perda das linhas vencidas,
a transição `ready→cancelled` nos canais `web` e `whatsapp`, e a lista no fechamento do dia.
Tudo isso é fronteira deste plano (services do `shop`) e vira frente própria da coordenação.
Defeito achado no caminho: o produto de pedido cancelado volta ao balcão com o lote de hoje,
de validade renovada (#2604); entra antes do WP-G11 ou junto.

**Ordem depois das respostas.** Decisão liberada não desfaz a fila dos arquivos: G12, G11 e
G07 escrevem em `pages/[ref].vue`, e G12, G11 e G13 escrevem em `operations.py` e `urls.py`.
A fila fica **G12, depois G11, depois G13**, e o **G07 depois do G05 e do G12**, nunca dois ao
mesmo tempo. O G11 só começa com a regra nos Termos da loja e com o lado do `shop` no `main`;
se ele demorar, o G13 passa à frente.

As perguntas como foram feitas em 16/11/2026:

1. **Pedido pronto que ninguém veio buscar: criar o gesto "Não retirado"?** Recomendo **sim**:
   gesto do Gerente, com PIN, que encerra o pedido e devolve o produto ao balcão. Sobre o
   dinheiro, responda **1** ou **2**. **1 (recomendado):** fica com a casa, e o estorno é um
   segundo gesto, caso a caso. **2:** volta sozinho ao cliente. Bloqueia o WP-G11.
2. **Devolução depois da venda: abrir no Gestor?** Recomendo **sim**: itens, motivo e PIN de
   Gerente, com o valor que volta escrito antes de confirmar. Hoje o serviço existe e nenhuma
   tela o chama. Bloqueia o WP-G12.
3. **Estorno que falhou: o Gerente pode tentar de novo pelo Gestor?** Recomendo **sim**, com a
   mesma assinatura do cancelamento de pedido pago. Hoje só o Dono, pelo Admin. Bloqueia o
   WP-G13.
4. **As três mensagens prontas de "Avisar o cliente" (vai atrasar, faltou um item, precisamos
   remarcar) saem pelo WhatsApp do próprio operador, sem envio automático?** Recomendo
   **sim**: custo zero, e a casa confere antes de enviar. A copy passa por você na prévia.
   Bloqueia o WP-G07.

Uma decisão de fronteira fica registrada sem bloquear este plano: **o pedido de hoje com hora
combinada deve esperar a hora da Cozinha, como a encomenda?** (F-5, #2548). Recomendo sim; é frente
do `lifecycle`, e o WP-G02 já mostra a hora no cartão para o que existe hoje.

## 11. Benchmarks

Pesquisa de 16/11/2026 em documentação oficial e centrais de ajuda (o portal de
desenvolvedores do iFood e a ajuda da Shopify bloquearam leitura direta; para os dois valem o
blog de parceiros e trechos de busca).

**O que eles fazem melhor**

| Mecanismo | Quem | Onde entra neste plano |
|---|---|---|
| Disparo do agendado em horário menos preparo, com "Fire Now" manual | Toast | já no `main` (#2303); o G02 mostra a hora e dá o "Adiantar" |
| Capacidade por janela de 15 min que esconde o horário cheio | Toast, Square | fora do Gestor (loja) |
| Limites em camadas, com estoque compartilhado por seção | Hotplate | fora do Gestor (loja e catálogo) |
| Lista de produção viva, com o prometido somado por dia e por horário | Hotplate | G10, cruzada com o planejado |
| Aviso em massa a quem tem pedido aberto | Hotplate | S5, como direção |
| Reembolso por item que devolve o estoque | Hotplate | G12 (devolução) |
| Negociação estruturada com prazo e "Substituir itens" | iFood | S5, como direção |
| Adiar a retirada com aviso ao cliente | Square | G07 (mensagem pronta) |
| O cliente avisa que chegou por link | Square | fora (loja); anotado |
| Lembretes em 24 h, 2 h e 15 min | Hotplate | fora (avisos) |

**O que nenhum deles faz**

1. Ligar produção real a pedido aceito: "o lote rendeu 38, há 42 prometidos, estes 4
   quebram" (S1).
2. Avisar antes de a promessa quebrar, por pedido, com a ação pronta (S1, S2).
3. Prender o agendado ao lote, e não só ao relógio (S2, S3).
4. Remarcar em lote com resposta individual do cliente (S5).
5. Dar destino ao produto perecível do não comparecimento (S4).

Fontes principais: `support.toasttab.com/en/article/Scheduling-Future-Orders`,
`doc.toasttab.com/doc/platformguide/adminQuoteTimeStrategies.html`,
`squareup.com/help/us/en/article/8608`, `squareup.com/help/us/en/article/8325`,
`help.hotplate.com/en/articles/13709527`, `help.hotplate.com/en/articles/13720613`,
`help.hotplate.com/en/articles/13718368`, `blog-parceiros.ifood.com.br/gestor-de-pedidos-ifood/`,
`help.shopify.com/en/manual/sell-in-person/shopify-pos/order-management/local-pickup-for-online-orders`.
A seção "o que nenhum faz" é ausência na documentação pública, não teste dos produtos.
