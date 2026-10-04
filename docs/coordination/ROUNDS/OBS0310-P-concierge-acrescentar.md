# OBS0310-P — Concierge: acrescentar item a pedido já feito

- **id:** OBS0310-P
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; frente executada por subagente em worktree próprio)
- **branches:** claude/obs0310-concierge-acrescentar (#1447, registro, mergeado) e
  claude/obs0310-concierge-acrescentar-pedido (o código, PR de seguimento)
- **início (UTC):** 2026-10-03
- **pré-requisitos:** #1443 (memória da Concierge, pergunta "1 acrescentar / 2 pedido novo") e #1442 (regras da casa)

## Decisão final do dono (03/10)
"Se é possível fazer dentro dos guardrails do sistema, via PDV, por que a Concierge não poderia fazer?"
Substitui as duas rodadas anteriores do mesmo dia ("só o que o site faz" e "pedido fechado não recebe
acréscimo"), registradas abaixo como histórico.

- A Concierge **não oferece** acrescentar. Quando o **cliente pede** (inclusive escolhendo "1" na
  pergunta da memória do #1443), ela acrescenta pelo **mesmo serviço do PDV**,
  `shop/services/order_edit.py`, com as travas dele: até "em preparo", sem NFC-e autorizada, fora do
  iFood, estoque, preço do canal, desconto não recalculado, diferença a mais vira saldo a receber,
  aviso `order_updated` ao cliente. O `Order` segue imutável: o estado novo mora em
  `order.data["adjustment"]`, como em toda edição.
- Só **aumento** de itens nesta fatia. Tirar item, trocar recebimento ou data ficam com a equipe.
- Antes, **uma linha** com os dados do sistema; só o "sim" aplica.
- Histórico do pedido: "Itens acrescentados pela Concierge a pedido do cliente".
- Recusa do serviço: o motivo verdadeiro, e a oferta que existe: **pedido novo** (pedido do dia) ou
  **a equipe** (encomenda).

## Dois ajustes de omotenashi (coordenação, 03/10; não foram ao dono)
- **Encomenda recusada:** o motivo verdadeiro e a equipe já chamada na MESMA mensagem ("<motivo> Já
  chamei a equipe para ver isso com você."), sem pergunta extra. O handoff é criado de fato
  (`mark_handoff(ack_text=...)`: a frase substitui o aviso padrão e passa pelas regras da casa com o
  recibo do handoff, R6). Pedido do dia segue oferecendo pedido novo.
- **Uma mensagem só:** quando a edição vem da Concierge, a resposta leva o que o `order_updated` diria
  (`order_edit.money_for_customer`: total novo e destino da diferença) e o aviso não é enviado
  (`order_edit.edit(notify_customer=False)`). Edição vinda do PDV/Gestor segue avisando.

## O que mudou
- `shop/services/order_edit.py`: `plan`/`edit` aceitam `source` (`pos:edit` no balcão,
  `concierge:add` na Concierge). A origem vai para `adjustment.source`, `meta.added_by` da linha nova, o
  `event_id` (`concierge-edit:<ref>:<rev>`) e o evento `order_edited`. Nenhuma trava nova nem
  relaxada; o balcão segue igual (default `pos:edit`).
- `backstage/projections/order_queue.py`: o evento `order_edited` com `source = concierge:add` aparece
  no histórico do Gestor como "Itens acrescentados pela Concierge a pedido do cliente", com a mesma
  frase que o cliente recebeu no aviso.
- `storefront/concierge/order_addition.py` (novo): `propose` (só calcula, pelo `order_edit.plan`, e
  confere estoque para o dia do pedido) e `apply` (no "sim", recalcula; se o valor mudou, pergunta de
  novo; aplica pelo `order_edit.edit` e grava a nota na conversa). Pedido só do próprio cliente, pela
  identidade da conversa. Sem autoridade comercial do turno, nada muda.
- `storefront/concierge/dialogue.py`: o "1" virou a pergunta (`add_preview`, sem modelo, quando o
  produto veio do foco; com produto citado em texto, o modelo acha o SKU e chama `add_to_order`); nova
  pergunta pendente `confirm_add`, cujo "sim" aplica (`add_apply`) e o "não" mantém o pedido. O rótulo
  do horário entra em minúscula no meio da frase ("retirada hoje a partir das 9h").
- `storefront/concierge/tools.py` + `prompt.py`: ferramenta `add_to_order` (só a pergunta, nada muda)
  para o pedido em texto livre, com a regra "nunca ofereça".
- Frases da casa (editáveis no Admin): `CONCIERGE_ADD_CONFIRM`, `CONCIERGE_ADD_DONE`,
  `CONCIERGE_ADD_REFUSED_NEW`, `CONCIERGE_ADD_REFUSED_TEAM`.
- `docs/reference/data-schemas.md`: `pending.kind = confirm_add`, `source = concierge:add`.

## Testes
`shopman/storefront/tests/test_concierge_order_addition.py`: dentro da etapa (pergunta com os dados
do sistema, só o "sim" aplica, histórico, nota, aviso), pedido pago (saldo a receber), valor mudou
entre a pergunta e o "sim", pronto (motivo + pedido novo), NFC-e autorizada numa encomenda (motivo +
equipe), iFood, sem estoque na pergunta e sem estoque no "sim", pedido de outra pessoa (inclusive com
"sim" forjado na memória), sem autoridade comercial, "1"/"sim"/"não" na memória, e o turno de verdade
("1" e depois "sim").

## Histórico das rodadas do dia
1. "Mesmos poderes que o cliente teria no site": medido que o site não acrescenta item a pedido feito
   em etapa nenhuma (o `reorder` com `append` vai para a sacola; o `order_edit` só era chamado pelo
   PDV/Gestor e pelo `ORDER_PATCHED` do iFood). Nada mudou (#1447).
2. "Acrescentar é antes de fechar, na sacola": pedido fechado não recebia acréscimo. Só registro.
3. Decisão final, acima: o que o PDV faz dentro das travas, a Concierge faz quando o cliente pede.
