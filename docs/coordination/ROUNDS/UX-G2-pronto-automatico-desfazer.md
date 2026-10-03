# UX-G2 — "Pronto" automático no Gestor e desfazer de 5 s em Entregar/Despachar

- **id:** UX-G2
- **branch:** claude/ux-g2-pronto-automatico-desfazer
- **PR:** #1423
- **estado final:** pronto, na fila
- **início (UTC):** 2026-10-03

## Objetivo
SUITE-UX-FUNCTION-PLAN §2 L1, §5.1 (linha "Avançar para 'pronto' quando a Cozinha conclui"),
§13 e §15 (decisões do dono):
1. Quando a Cozinha conclui todas as estações do pedido, ele vai a "pronto" sozinho; o cartão do
   Gestor diz "Pronto · automático · desfazer"; o "Marcar pronto" manual sai do cartão e fica no
   menu do pedido; o aviso ao cliente só sai depois da janela de desfazer.
2. Entregar e Despachar (Gestor e Saída da Cozinha) ganham desfazer de 5 s no servidor; o aviso ao
   cliente e o fim do pedido só valem quando o prazo acaba.

## O que já existia
`kds.on_all_tickets_done` já levava o pedido a READY quando todos os tickets (inclusive os da
estação sem tela, concluídos pela Saída) terminavam; a fase `on_ready` (aviso de pronto, nota da
sacola, corrida) e o `readyToPickup` do iFood saíam na hora. Entregar/Despachar gravavam a
transição no toque, sem desfazer. O KDS já tinha desfazer de 5 s no "Finalizar" (cliente) e o
recall de 30 min.

## O que mudou
- **Config por canal** (`ChannelConfig.fulfillment`): `auto_ready` (padrão ligado),
  `ready_undo_seconds` (30), `handoff_undo_seconds` (5). 0 desliga a janela.
- **`shop/services/order_undo.py`** (novo): as duas janelas, desfazer e gravação.
  - Pronto automático: `order.data.auto_ready` gravado antes da transição (token, prazo, ticket
    que fechou o pedido). `lifecycle.enqueue_phase` agenda `on_ready` para o fim da janela com
    `hold_token`; o handler da fase vira no-op se o pronto foi desfeito ou recolhido. Desfazer
    reabre o ticket e volta a PREPARING. Saída antes do prazo roda a fase do pronto antes da
    saída (`release_ready_hold`). Recall do KDS limpa o registro.
  - Entregar/Despachar: `advance_order(undo_window=True)` (só Gestor e Saída) valida tudo e grava
    `order.data.pending_handoff` + directive `order.handoff_commit` no fim da janela, que roda a
    MESMA `advance_order` com os argumentos do toque. Desfazer apaga o registro. Repetir o toque
    é a mesma saída; outro destino é conflito. Fato de fora (iFood, entregador) grava a saída
    tocada na hora. Gravação recusada vira alerta `handoff_refused`.
- **API**: `orders/<ref>/undo-handoff/`, `orders/<ref>/undo-ready/` (intenção idempotente, como as
  outras ações), `kds/expedition/<pk>/undo/`; a ação da Saída devolve os campos da janela.
- **Projeções**: `UndoProjection` (`undo`) no card e no detalhe do Gestor; ações `undo-handoff` e
  `undo-ready`; "Marcar pronto" com ticket aberto na cozinha vem com `priority="menu"`; card da
  Saída com `handoff_label`/`handoff_undo_until_iso`/`handoff_token`. Contratos regenerados.
- **Gestor (orders-nuxt)**: linha "o sistema fez · desfazer" no card e no detalhe ("Pronto ·
  automático · aviso ao cliente sai em 0:24 · Desfazer"; "Entregue às 14:02 · Desfazer 5 s");
  "Marcar pronto" no menu ⋯ do detalhe.
- **Saída (kds-nuxt)**: o card fica no lugar com "Saiu/Entregue às HH:MM · Desfazer N s".
- `docs/reference/data-schemas.md`: `auto_ready`, `pending_handoff`, `order.handoff_commit`,
  `hold_token`.

## Efeitos externos
Esperam a janela: aviso de pronto ao cliente, nota da sacola de entrega e corrida automática
(fase `on_ready`); em Entregar/Despachar, tudo (status e avisos ao cliente, `on_dispatched`/
`on_completed`: NFC-e, fidelidade; status ao iFood; troco no livro do caixa; reserva da
maquininha; DANFE do despacho; auto-conclusão da entrega; tickets fechados).
Não espera: o `readyToPickup` do iFood no pronto automático (chama o entregador do iFood, é
exigido antes do despacho e o iFood não tem "desfazer pronto"; o despacho do entregador dele
pode chegar dentro da janela). O card mostra "iFood já avisado".

## Evidência
- `pytest shopman/shop/tests/test_order_undo.py` 32 passed; `shopman/backstage/tests/test_api_order_undo.py` 7 passed.
- Suítes inteiras locais (`-n 4`): shop 10931 passed / 27 failed, todas falhando igual no
  `origin/main` (comparação lado a lado); backstage 7550 passed / 4 failed que passam em série.
- CI do PR: shop, backstage, storefront, orders-nuxt, kds-nuxt, operator-kit verdes.
- orders-nuxt vitest 532 passed, typecheck 0 erros, eslint 0 erros; kds-nuxt vitest 118 passed,
  typecheck e eslint limpos; travas de vocabulário (Python 2242 passed; kit 6 passed).

## Fora
- "Marketing — cadeia completa" vermelho no CI: `npm audit` do marketing-nuxt (não tocado aqui).
- A Saída da Cozinha não recebe SSE do pedido de saída tocado no Gestor; vê na leitura seguinte
  (poll 15 s) e um toque nela é a mesma saída (replay).
