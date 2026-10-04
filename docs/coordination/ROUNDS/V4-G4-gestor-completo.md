# V4-G4: o Gestor completo, igual à v4

- **id:** V4-G4
- **branches:** `claude/v4-g4-gestor-dados` (PR A: dados do cartão) · `claude/v4-g4-gestor-fila` (PR B: a Fila "Precisa de você" e o painel do produto)
- **estado:** em andamento
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

(preenchido no PR B)
