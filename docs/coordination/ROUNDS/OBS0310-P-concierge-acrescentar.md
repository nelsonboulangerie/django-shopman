# OBS0310-P — Concierge: acrescentar item ao pedido aberto

- **id:** OBS0310-P
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; frente executada por subagente em worktree próprio)
- **branch:** claude/obs0310-concierge-acrescentar
- **PR:** #1447
- **início (UTC):** 2026-10-03
- **pré-requisitos:** #1443 (memória da Concierge, pergunta "1 acrescentar / 2 pedido novo") e #1442 (regras da casa)

## O pedido
Decisão do dono (03/10): "a Concierge tem os mesmos poderes que o cliente teria no site". Se o SITE
deixa o cliente acrescentar item a um pedido aberto numa etapa, a Concierge acrescenta sozinha, pelo
mesmo serviço e com as mesmas travas. Se o site não tem essa capacidade em etapa nenhuma, não se
inventa backend: fica como está.

## O que foi medido (main em `1f4089352`)
O site NÃO deixa o cliente acrescentar item a um pedido já feito, em etapa nenhuma.

- Ações que o acompanhamento do pedido oferece ao cliente
  (`shopman/shop/projections/order_tracking.py`): `reorder`, `cancel_order`, `request_cancellation`,
  `rate_order`, `mock_confirm_payment`, `copy_pix`, `pay_card`, `confirm_received`, `retry_payment`.
  Nenhuma edita itens.
- `POST /api/v1/orders/<ref>/reorder/` com `mode: "append"` (`storefront/api/surface.py`,
  `OrderReorderView`) acrescenta os itens do pedido antigo à SACOLA, não ao pedido. O resultado é um
  pedido novo, que é a opção 2 da Concierge.
- Nenhuma rota de `shopman/storefront/api/urls.py` nem página de `surfaces/storefront-nuxt` edita itens
  de um pedido existente.
- A capacidade de editar existe, mas é do OPERADOR: `shopman/shop/services/order_edit.py`
  (`plan`/`edit`/`apply_final_items`, régua `state_refusal`: até "em preparo", sem NFC-e autorizada,
  fora do iFood), chamada só pelo PDV/Gestor (`backstage/api/operations.py`, permissão de backstage) e
  pelo `ORDER_PATCHED` do iFood. Ela decide diferença a mais (saldo a receber) e a menos (estorno pelo
  mesmo meio), coisas que o site nunca expôs ao cliente.

## Decisão do dono (03/10)
Ele imaginava acrescentar ANTES de fechar o pedido: na sacola (sessão), que já é mutável e que a
Concierge já edita (`set_item`). Não era editar pedido fechado.

- **Pedido fechado não recebe acréscimo pela Concierge.** Ela não usa o `order_edit`, que segue sendo
  só do operador.
- **"Mais X" depois de fechado vira pedido novo ou equipe.** É o que a pergunta "1 acrescentar / 2
  pedido novo" da memória (#1443) já faz: o "1" vai para a equipe (que edita pelo PDV/Gestor), o "2"
  monta um pedido novo.
- Uma rodada intermediária chegou a pedir a implementação pelo `order_edit`; foi suspensa antes de
  qualquer código.

## O que mudou
Nada no código. Só este registro. As regras R4 e R6 (#1442) ficam como estão: a frase de equipe só sai
com o recibo do handoff, e nenhuma frase promete o acréscimo.
