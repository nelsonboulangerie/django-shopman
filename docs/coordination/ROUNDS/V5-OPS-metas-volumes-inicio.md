# V5-OPS: metas por canal, volumes de qualquer superfície, quem iniciou no KDS

- **id:** V5-OPS
- **branch:** `claude/v5-ops`
- **início (UTC):** 2026-10-04
- **escopo:** backend do backstage/shop (projeções `order_attention` e `kds`, serviços de
  volumes e de ticket do KDS, a Via Pedido), `surfaces/orders-nuxt` (cartão e Saída) e
  `surfaces/kds-nuxt` (detalhe do ticket). Kit sem mudança.

## Decisões do dono (04/10/2026) e o que virou código

1. **Metas por etapa, variando por canal.** Padrões: iniciar 5, estação 15 (era 20),
   balcão 10, despacho 30 (da chegada), entregador 45, acerto 15. Moram em
   `ChannelConfig.fulfillment.stage_goal_minutes` (JSON em `Channel.config` ou
   `Shop.defaults`, cascata por chave, padrões em `shop/config.STAGE_GOAL_DEFAULTS`),
   sem campo novo. O admin do canal expõe pela aba "Preparo e entrega" (JSON).
   O pedido novo segue com o prazo da confirmação do canal.
2. **Volumes: quem embalou declara, onde estiver.** O mesmo gesto (− N +, Gravar, zero
   apaga) no cartão do Gestor (agora também pela etiqueta "N itens/volumes", um toque),
   na coluna/posto Saída e no detalhe do ticket do KDS (inclusive nos concluídos
   recentes). Mesmo endpoint (`orders/<ref>/volumes/`), aberto a quem opera o quadro
   (gerencia pedidos ou expede, que inclui a Cozinha). O evento `volumes_declared` traz
   `{volumes, actor, surface}`. Com N > 1 a Via Pedido (ficha que vai grampeada na
   sacola) sai N vezes, cada uma com "Volume k de N".
3. **KDS: quem iniciou e quando.** Sem migração: `Order.data["kds_started"]`
   (`{ticket_pk: {at, by}}`), escrito no primeiro início, mostrado no detalhe do ticket
   ("Iniciado por joyce às 14:05"). Ticket de comanda ainda sem pedido não registra.
