# ENCOMENDAS-PDV-PLAN — a seção "Encomendas" do PDV

> **Origem:** pedido do dono, 26/09/2026, na conversa sobre a área de Sessões do PDV
> ("deveria se chamar Encomendas, para ficar como a opção de modalidade do pedido no
> PDV […] precisa ser muito bem pensada/projetada"). Desenho aprovado na mesma
> conversa, com a grade semanal e com reagendar e editar **dentro** do escopo.
>
> **Princípio (Core é sagrado):** quase tudo o que a seção precisa já existe, espalhado
> entre Gestor, lifecycle e Payman. O trabalho é **compor e expor no balcão**, não criar
> fluxo paralelo. Onde o sistema não tem a peça (reagendar, editar pedido de canal
> próprio), ela nasce como **serviço do orquestrador** (`shopman/shop/services/`),
> reaproveitando os primitivos listados abaixo — nunca como atalho na superfície.

## As decisões que já estão tomadas (não reabrir)

1. **O nome é "Encomendas"**, o mesmo do seletor de modalidade do PDV
   (`PosTabHeader`: *Balcão | Encomendas*).
2. **Encomenda = todo pedido com recebimento** — retirada ou entrega — **de qualquer
   canal** (PDV, loja online, iFood), **hoje ou depois**. É o corte do PDV (Encomendas
   aceita "Hoje") e é o que o painel de parede quer ver.
   ⚠️ Diverge de "encomenda" no lifecycle e no Gestor (*Agendados*), onde é só data
   futura. A seção diz o seu corte na tela; o lifecycle não muda.
3. **O PDV recebe o saldo na retirada** — o cliente e a gaveta estão no balcão. O dinheiro
   entra no turno do terminal.
4. **Reagendar e editar entram.**
5. **Grade semanal** é parte da seção.
6. A tela "Fichas de pedido" **deixa de existir como item da barra lateral** e vira o card
   **Via Pedido** da seção (a palavra do dono para o papel — ver
   `backstage/services/order_documents.py`).

## A seção: uma tela só, `/preorders` (redesenho aprovado pelo dono, 28/09/2026)

> A antesala de quatro cards (Cliente veio buscar · Hoje · Semana · Via Pedido, painel)
> foi o desenho de 26/09. Em 28/09 o dono o trocou por **uma tela**, com o panorama da
> semana no centro. Entregue pela #1231 (integração das frentes #1221 e #1222); a volta do
> detalhe com o recorte (`?back=`) pela PR "Encomendas: uma tela, com o panorama da semana
> no centro".

| Parte | Pergunta do balcão | Como é |
|---|---|---|
| **Busca** (sempre no topo, nasce focada) | "Vim buscar a encomenda da Ana" | nome, telefone, CPF, endereço ou número; em aberto de **qualquer** data; "Incluir concluídas" (30 dias) em seção **separada**; sem nada em aberto, oferece procurar nas concluídas; resultado único: Enter abre |
| **Dia** | "O que sai hoje?" | o dia escolhido (padrão hoje), agrupado por horário, ‹ › anda um dia |
| **Semana** (abre nela) | "Quanto temos para sábado?" | semana de **segunda** a domingo que contém o dia escolhido (`?week=2026-W40`), 7 colunas com contagem, total e "a receber"; tocar no dia abre o Dia; área estreita vira lista por dia |
| **Filtros** (chips com contagem) | "Quais faltam cobrar? Quais faltam imprimir?" | Recebimento Todas · Retiradas · Entregas; Pagamento Todas · A receber · Pagas (+ "Na conta da casa" quando existe; "a conferir" é aviso próprio, #1171); Via Pedido Todas · Falta imprimir |
| **Imprimir N vias** | "Imprimir a semana para o painel" | o lote da Via Pedido do que está **visível** (`order_ticket.select_refs`, agente local); `Order.data.ticket_printed_at` alimenta "Falta imprimir" e o sinal no card |

O estado inteiro (modo, data, filtros, busca) mora na URL (`presentation/preorders.parseView`).
As rotas antigas respondem 301 por uma release: `/preorders/today` → `?mode=day`,
`/preorders/week` → `?mode=week`, `/preorders/panel` e `/tickets` →
`?mode=week&print=pending`. Cada linha leva o recorte ao detalhe (`?back=`,
`presentation/preorderDetail.preorderDetailPath`), e a volta cai nele mesmo com o
detalhe recarregado ou aberto noutra aba.

O detalhe de uma encomenda (aberto de qualquer linha da tela) oferece, conforme o estado e a
permissão: **Receber e entregar**, **Reagendar**, **Editar**, **Cancelar**, **Imprimir Via
Pedido**.

## O que existe, e onde (levantamento de 26/09/2026)

| Capacidade | Existe? | Onde | O que falta |
|---|---|---|---|
| Listar/buscar | parcial | `backstage/projections/order_queue.build_two_zone_queue` (grupo *Agendados*, cards ricos, itens efetivos sem N+1) · `order_ticket.orders_for_period` | projeção do PDV com busca, hoje+futuro e **saldo** (`payment.captured_balance_q` × `order_composition.effective_total_q`) |
| Receber na retirada (dinheiro/cartão) | sim | `operator_orders.settle_delivery_cash` · `backstage/services/orders.py` | endpoint do PDV com o turno do terminal; ⚠️ o serviço compara com `order.total_q` (selado) — trocar por `effective_total_q` |
| Receber Pix/link pendente no balcão | sim (26/09) | `shop/services/counter_takeover.py` + `operator_orders.take_over_before_hand_over` | — (pergunta ao provedor, cancela a cobrança, cala os avisos, e só então o acerto canônico; pagamento tardio é estornado no mesmo meio) |
| Entregar | sim | `advance_order` READY→COMPLETED + `payment_gate` | expor |
| Cancelar fora da janela de 5 min | sim | `operator_orders.cancel_order` + `operator_cancel_policy` + PIN | expor; Caixa não cancela pronto/concluído (é do Gerente) |
| Devolver dinheiro | sim | `payment.pending_cash_refunds` · `refund_cash` | já está na antesala (*Precisa de você*) |
| **Reagendar** | **não** | peças: `lifecycle._schedule_preorder_activation`, `stock.hold/release`, `production_order_sync`, validadores de data | serviço `reschedule` (WP-E5) |
| **Editar itens** | sim (serviço + API, WP-E6 PR 1) | `order_edit.plan/edit` → `apply_final_items` (o mesmo do iFood) | a tela (WP-E6 PR 2) |
| Editar observação do cliente / recebimento | sim (serviço + API, WP-E6 PR 1) | `order_edit` (`order_notes`, retirada ↔ entrega com a taxa como linha) | a tela (WP-E6 PR 2) |

## Work packages

Uma frente = um branch = uma PR. A ordem é de dependência.

### WP-E1 — Leitura: a projeção das encomendas + API  *(sem decisão pendente)*
- Projeção em `backstage/projections/` sobre a base do `order_queue` (não duplicar a
  montagem do card): intervalo por **data combinada**, busca (ref, nome, telefone,
  `display_id` do iFood), saldo, situação, canal, recebimento, janela.
- Exclui venda de Balcão (a regra de `build_two_zone_queue`), cancelados e devolvidos.
- API `GET /api/v1/backstage/pos/preorders/` (`cashman.operate_pos` + `shop.manage_orders`).
- **Corrige o lote da Via Pedido**: `order_ticket.orders_for_period` passa a excluir venda
  de Balcão (hoje entra, por não ter `delivery_date`).
- `closing._upcoming_preorders` passa a ler `effective_total_q` e a dizer o que conta
  ("Vendidas hoje" não confere com a consulta).

### WP-E2 — PDV: a seção e as telas  *(sem decisão pendente; depende de E1)*
- Seção **Encomendas** visível com ou sem caixa aberto, só para quem tem
  `shop.manage_orders`. ✅ Desde 28/09 a porta é o item da barra lateral (com o selo das
  de hoje por entregar), não mais a antesala de quatro cards.
- Páginas `pages/preorders/` (URL em inglês, convenção das superfícies de operador):
  ✅ desde 28/09 são duas, a tela única (`index.vue`) e o detalhe (`[ref].vue`); a tela
  de lote morreu dentro do "Imprimir N vias", e `/tickets` responde 301 (bookmark de kiosk).
- "Fichas de pedido" sai da barra lateral (`PosFunctionRail`).
- Vocabulário: "Via Pedido", nunca "ficha"/"filipeta" na tela.

### WP-E3 — Receber e entregar no balcão  *(depende de E1/E2)*
- Endpoint do PDV que reusa `settle_delivery_cash` com o turno do terminal (dinheiro/cartão)
  e depois `advance_order` → COMPLETED, numa transação.
- `settle_delivery_cash`, `has_sufficient_captured_payment` e o `closing` passam a ler o
  total **efetivo** (pré-requisito de E6; corrige desde já pedido do iFood ajustado).
- Pix/link pendente recebido no balcão: converter a cobrança em pagamento do terminal pelo
  Payman — **sem** segunda cobrança viva (cancelar o link/intent pendente antes).
  ✅ Feito (decisão do dono, 26/09): `counter_takeover.take_over_pending_digital_charge`
  pergunta ao provedor (cliente que acabou de pagar → só entregar), cancela no provedor e
  no Payman, pula os avisos de cobrança da fila e grava `payment.counter_takeover`; o
  acerto canônico recebe na forma escolhida no balcão. O pagamento digital que chegar
  depois é estornado no MESMO meio, com alerta. iFood fica de fora.

### WP-E4 — Cancelar pelo PDV  *(depende de E2)*
- Expor `operator_orders.cancel_order` com a política e o PIN que já existem; devolução em
  dinheiro cai no *Precisa de você* como hoje.

### WP-E5 — Reagendar  *(serviço novo no orquestrador)*
Serviço `shopman/shop/services/reschedule.py` — `reschedule(order, *, date, slot, actor)`,
sob lock do pedido, transacional:
1. validar com as regras que já existem (`pos_sales_mode.validate_sales_mode`,
   `pos._validate_schedule`, `_max_preorder_days`, loja fechada/antecedência de
   `storefront/intents/checkout.py`);
2. reescrever `delivery_date`/`delivery_time_slot` e registrar a mudança (chave nova em
   `docs/reference/data-schemas.md` **antes** de usar);
3. **mover** a Directive `preorder.activate:{ref}` viva (editar `available_at`, padrão de
   `lifecycle.py` ~1057) — nunca criar outra; data nova = hoje ⇒ ativar agora;
4. achar o `preorder_reminder` pendente pelo `payload.order_ref` e cancelar/recriar (o
   `context` guarda a data congelada);
5. soltar e refazer os holds (`stock.release` + `stock.hold` com a data nova) — sem saldo na
   data nova ⇒ recusa com o motivo, nada muda;
6. religar a produção (`production_order_sync`: desfazer o vínculo da data antiga,
   `reconcile_production_order_links`);
7. avisar o cliente (conferir se há template; senão, WP de template);
8. de passagem: `activate_preorder` antecipado só loga e o comentário promete reagendar
   (`lifecycle.py` ~970) — a promessa vira código ou sai.

### WP-E6 — Editar  *(decidido pelo dono, 26–28/09; em duas PRs)*

**Decisões (26–28/09/2026):**
1. Editar no PRÓPRIO pedido (mesmo ref, pagamento e acompanhamento). Com a NFC-e já
   autorizada, **cancelar e refazer** — depois da #1173 a nota da encomenda só sai na
   saída da mercadoria, então quase sempre não há nota e a edição acontece.
2. Diferença a MAIS vira saldo a receber (retirada: "Receber e entregar"; entrega: na
   porta). A MENOS volta pelo **mesmo meio**: cartão online e Pix pelo gateway (estorno
   parcial), dinheiro pela gaveta (*Precisa de você*), maquininha por pendência guiada
   registrada. Meio que não devolve parte recusa com o motivo, nunca devolve em outro.
3. O editor É a tela de venda do PDV em **modo edição** (comanda virtual pré-montada,
   sem disparar cozinha, "Salvar alterações" com a prévia). Trocar retirada ↔ entrega
   entra (F7, taxa, CPF da entrega de 24/09); data/janela (F8) vai pelo reagendar na
   mesma operação.
4. Aviso ao cliente `order_updated` (template Meta `pedido_atualizado`) — ⚠️ texto em
   RASCUNHO, o dono revisa antes de qualquer submissão à Meta/ManyChat.

**PR 1 — serviço + API** (`claude/encomenda-editar`):
- `shop/services/order_edit.py`: `plan` (prévia, nada gravado) e `edit` (sob lock,
  transacional). Caminho comum `apply_final_items` (ajuste + `stock.reconcile_to_items`
  + `kds.reconcile_to_lines`) — o `_apply_patch` do iFood passa por ele.
  `reconcile_to_items(require_all=True)` recusa sem saldo na data (o iFood segue brando).
- Preço: o que já estava mantém o vendido; o que entra, catálogo no canal do pedido
  (`OffermanPricingBackend`); a mais com preço diferente vira linha própria. Descontos
  não são reavaliados; a taxa é linha `__DELIVERY_FEE__` do ajuste, pelo motor da venda
  (`pos.resolve_delivery_fee`).
- Pagamento segue a invariante do valor final (`amount_q`, `tenders`); pendências
  derivadas `payment.pending_cash_refunds` (agora também "encomenda reduzida") e
  `payment.pending_card_machine_refunds` + `record_card_machine_refund`.
- API: `POST orders/<ref>/edit/preview/` e `POST orders/<ref>/edit/` (revisão `edit`,
  409, `{detail, field, errors, error.code}`, PIN de gerente na redução paga);
  `POST pos/card-machine-refund/<ref>/`. Detalhe da encomenda expõe `edit` e a revisão
  certa do reagendar (o PDV mandava a revisão geral e o reagendar voltava 409).
- Leitores que somavam o selado passaram a ler o efetivo: vínculo de produção
  (`production_order_sync`), dinheiro na porta (`cash_due_on_delivery_q`), conciliação
  financeira, total do aviso (`order_total_display`).

**PR 2 — o modo edição na tela de venda** (`claude/encomenda-editar-tela`, depende da
PR 1): `shop/services/pos_edit_session.py` — a comanda virtual (`handle_type="pos_edit"`,
sem `tab_ref`, preço vendido, não dispara cozinha nem fecha venda) aberta por
`POST pos/preorders/<ref>/edit-session/`; `/?edit=<ref>` abre a venda nela, com
cabeçalho "Editando a encomenda …" + "Descartar alterações", "Salvar alterações" (F4)
com a prévia do servidor e o PIN; "Editar encomenda" e "Cancelar e refazer" no
detalhe; cards "Estorno na maquininha" e a devolução "encomenda ficou mais barata" no
*Precisa de você*.

**PR 3 — as pendências das duas primeiras** (`claude/encomenda-editar-pendencias`):
- **Gesto que o serviço não grava sai da tela**: no modo edição o carrinho fica sem
  desconto e sem observação de item (teclado só com "Qtd", seleção múltipla sem
  desconto em lote), com a frase do porquê; o chip do cliente (e o F6) não troca o
  cliente — diz por quê. Desconto de pedido, gorjeta e cupom moram no pagamento, que o
  modo edição não abre.
- **Cancelar e refazer com a venda pré-montada**: depois do cancelamento de sempre
  (política/PIN), `POST pos/preorders/<ref>/redo-tab/` (`pos_edit_session.open_redo_tab`)
  abre a comanda comum `Refazer <ref>` com itens (preço de hoje), cliente, recebimento,
  data e observação; pagamento e "CPF na nota" ficam para o fechamento. Data que não
  vale mais vem para a primeira data aceita, sem horário, com o aviso por extenso.
  Retomada enquanto aberta; recusada depois que uma venda fechou nela.
- **Peso na edição**: a peça nova entra pela etiqueta (ou pelo peso, se a loja lança
  pelo peso), uma linha por peça, com a mesma conversão da venda
  (`weighed_sale.resolve`) e o preço de catálogo do canal; a peça que já estava não
  muda de peso, e a comanda virtual a mostra com o peso e o preço vendidos (antes o
  parser a zerava para 1 kg).
- **CPF da entrega na edição**: a recusa `delivery_tax_id_*` abre o campo do documento
  na própria caixa de "Salvar alterações", com a conferência da venda
  (`presentation/taxId`); o cadastro só empresta o valor inicial.
- **Últimas vendas pela saída** (PR própria, `claude/ultimas-vendas-pela-saida`): entram também os pedidos do PDV com retirada concluída
  ou entrega despachada na janela da emissão tardia (a venda fiscal é a da saída,
  #1173); a linha diz "Retirada hoje às …" e o total é o efetivo.

### WP-E7 — Detalhe do pedido compartilhado com o Gestor  *(decidido pelo dono, 28/09; no ar)*

Decisão (28/09/2026, DRY/KISS): o detalhe do pedido do Gestor e o da encomenda no PDV
são **telas irmãs**. Entregue pela integração única de Encomendas (#1231, que juntou as
frentes preservadas #1221 e #1222):

- **Servidor:** um builder, um contrato: `order_queue.build_operator_order(order,
  context="orders"|"pos")` (`OperatorOrderProjection`). O contexto decide as ações no
  servidor: no `"pos"` só o que o balcão executa, mais o envelope `counter` (saldo,
  entregar, editar, reagendar, cancelar). Testes em `test_order_detail_context.py`.
- **Front:** `operator-kit/app/components/OperatorOrderDetail.vue` + presentation pura
  (`presentation/orderDetail.ts`, tipo em `types/orderDetail.ts`) com as seções comuns
  (resumo, contato, presente, cliente, fiscal, itens, observação, nota da cozinha,
  histórico com comentário quando o servidor oferece `comment`). Slots `summary`,
  `actions`, `after-profile`, `kitchen-note`; diálogos ficam em cada app; PIN pelo
  `OperatorManagerAuth`.
- **PDV:** ganhou cliente, fiscal e histórico com comentário (pela rota do Gestor). A
  volta respeita `?back=` (só caminho interno de `/preorders`) ou o histórico.
- **Testes na fonte (29/09):** vitest da presentation e do componente no
  operator-kit; no PDV, cliente/fiscal, comentário e volta.

## Fora de escopo, registrado

- Capacidade por janela de retirada (`pickup_slots` não tem) — só se o negócio pedir.
- Sinal / pagamento parcial — não existe no Payman; decisão de produto própria.
- Edição de pedido no Gestor.
