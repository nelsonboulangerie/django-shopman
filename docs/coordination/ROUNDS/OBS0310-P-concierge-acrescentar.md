# OBS0310-P — Concierge: acrescentar item ao pedido aberto

- **id:** OBS0310-P
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; frente executada por subagente em worktree próprio)
- **branch:** claude/obs0310-concierge-acrescentar
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

## O que mudou
Nada no código. Pela regra do pedido ("se o site não tem essa capacidade em etapa nenhuma, não invente
backend"), a escolha "1" continua indo para a equipe (`dialogue.resolve`, `reason="add_to_open_order"`,
#1443), e o cliente recebe o aviso de atendimento humano, que a regra R6 (#1442) só deixa sair com o
recibo do handoff. Nenhuma frase promete o acréscimo.

## Pergunta ao dono
Abrir ao cliente, no site, "acrescentar item ao pedido" (pelo `order_edit`, até "em preparo", com a
diferença virando saldo a receber ou novo Pix)? Se sim, a Concierge passa a fazer o mesmo, pelo mesmo
caminho. 1 = sim, abrir no site e na Concierge; 2 = não, acréscimo segue com a equipe.
