# V4-G4: o Gestor completo, igual à v4

- **id:** V4-G4
- **branches:** `claude/v4-g4-gestor-dados` (PR A: dados do cartão) · `claude/v4-g4-gestor-fila` (PR B: a Fila "Precisa de você" e o painel do produto)
- **PRs:** #1453 (A, mergeado) · #1460 (B, auto-merge)
- **estado:** entregue, esperando o CI e as perguntas ao dono
- **início (UTC):** 2026-10-04
- **escopo:** `surfaces/orders-nuxt`, o backend do backstage/shop que o alimenta e o mínimo aditivo no kit. O detalhe do pedido (`OperatorOrderDetail`, compartilhado com o PDV) fica como está.

## PR A: os dois dados que faltavam no cartão (UX-KIT-V2 os listou)

**Hora do pronto.** O Core já carimba `Order.ready_at`, mas só a primeira vez: depois do
pronto desfeito (`order_undo.undo_auto_ready`) ou do recall da Cozinha, o pedido volta a
pronto e o carimbo fica velho. O cartão passa a ler a ÚLTIMA entrada em READY no log de
eventos (`status_changed` com `new_status=ready`), numa consulta para o quadro inteiro
(`order_queue.ready_moments_for`), com `ready_at` de reserva. Nenhuma escrita nova,
nenhuma chave nova. Campo `ready_at_iso` no cartão; `dispatched_at_iso` (do Core) para o
"na rua há N min". O relógio do cartão diz "pronto há 6 min" e "na rua há 18 min".

**Volumes.** Não existe conceito de volume de saída no sistema (o único "volume" é o da
contagem do recebimento de Compras). Regra escolhida, a mais honesta: **volume é
declarado por quem embala**, nunca deduzido. `Order.data["volumes"]` (inteiro 1 a 99;
zero apaga), gesto "Declarar volumes" no ⋯ do cartão, endpoint
`POST /api/v1/backstage/orders/<ref>/volumes/` no protocolo de intenção (revisão própria
`volumes`, chave de idempotência, pessoa), evento `volumes_declared` no histórico e no
SSE do quadro. Sem declaração o cartão segue com "N itens". Pergunta ao dono no PR:
quem declara (a Saída, a estação que embala, o PDV) e se a Via do entregador deve
imprimir "Volume 1 de N".

## PR B: a Fila "Precisa de você" e o painel do produto

**A Fila "Precisa de você"** (`gestor-fila4.html`). O desktop (1024 px ou mais, fora do
posto Saída) abre na Fila; o tablet em pé, o celular e o posto Saída seguem com as colunas.
Alternador **Fila (F) | Supervisão (T)** (Supervisão = o quadro de três colunas de antes),
mais a tabela no mesmo trilho (V). Na Fila: ↑/↓ andam, Enter faz o gesto do item em foco, A
aceita o pedido novo em foco; o R continua "atualizar" (a prévia usava R para "Retirou", o
que colidiria).

Servidor, na MESMA leitura do quadro (`GET /api/v1/backstage/orders/`, sem endpoint novo):
- `shopman/backstage/projections/order_attention.py`: `card_attention` classifica cada
  cartão (`attention`: confirm · blocked · start · station · mark_ready · handoff · dispatch ·
  courier_back · settle, ou vazio) lendo as AÇÕES que o cartão já oferece; `attention_since_iso`,
  `goal_minutes`, `goal_label` ("meta 30", "no balcão").
- Metas: o pedido novo usa o prazo do canal (`confirmation.timeout_minutes` /
  `external_sla_minutes`); as outras são PROPOSTA (`STAGE_GOAL_MINUTES`: iniciar 5, estação
  e marcar pronto 20, balcão 10, despacho 30 da chegada, entregador 45, acerto 15). Pergunta
  ao dono no PR.
- `awareness` no `TwoZoneQueueProjection`: "O sistema fez" (eventos `status_changed` dos
  últimos 15 min de quem não é gente: pronto automático conferido contra
  `Order.data.auto_ready.at`, `confirmation.timeout`, `auto_reject_*`, `fulfillment.sync`),
  com `undo_action=undo-ready` enquanto a janela vale; "Agora no cardápio" (`ShelfOutage`
  abertos, um por produto) e os canais de venda (`channel_switch.effective_active`).
- SSE: `ShelfOutage` e `Channel` salvos publicam `backstage-orders-update` `{kind: "menu"}`.

**Painel do produto** (`catalogo-produto4.html`): 520 px, a linha do que ele é (SKU, preço,
coleção, Comprável/Vendável/Produzido), abas da v4, "N campos alterados" ao lado do Salvar e a
**Disponibilidade nos canais** (somente leitura, `channel_availability` no detalhe, do
`ShelfOutage`; canal de exibição segue o estoque do canal de origem e é "automático").

**Fora daqui (com motivo):** "Pausar" por canal e "Pausar em todos" com motivo no painel (o
motivo da pausa não é gravado em lugar nenhum; pausar segue no interruptor do canal, na
tabela); a hora provável de volta ("volta ~10:40, lote no forno") no painel; o interruptor do
iFood dentro da Fila (a linha leva aos Canais, onde o interruptor e a aprovação de gerente
moram); "Na Cozinha: próximo pronto em ~4 min" (não há previsão de pronto; a linha diz o mais
antigo).
