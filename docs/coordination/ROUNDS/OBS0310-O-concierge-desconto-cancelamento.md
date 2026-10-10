# OBS0310-O: Concierge, desconto até o teto e cancelamento conforme a etapa

- **id:** OBS0310-O
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; frente executada por subagente em worktree próprio)
- **branches:** `claude/obs0310-concierge-desconto` (A) e `claude/obs0310-concierge-cancelamento` (B), um PR cada
- **base:** as regras da casa (OBS0310-M, PR #1442: R4 e R7); as duas frentes partiram da cabeça da #1442
  e são trazidas para o `main` quando ela entra.
- **decisões do dono:** 03/10/2026, citadas no topo de `concierge/discount.py` e `concierge/cancellation.py`.
- **PRs:** A #1444 · B #1445
- **início (UTC):** 2026-10-03

## A) Desconto da Concierge com teto configurável
- **Teto no Admin:** `ChannelConfig.pricing.concierge_discount_max_percent` (`Channel.config` do canal
  `whatsapp` ou `Shop.defaults`), em % do subtotal; padrão 2,5 (decisão do dono, 03/10; aceita decimal), 0 desliga,
  validado entre 0 e 100.
- **O valor é do sistema** (R1, R5): `discount.amount_for` arredonda o total para baixo no maior degrau
  redondo (R$ 10, 5, 1, 0,50, 0,10) cuja diferença cabe no teto. Com 2,5%, R$ 51,20 vira R$ 50,00
  (o exemplo do dono, que pede 2,34%); com 2% sairia R$ 51,00.
- **O caminho é o do site:** um cupom de uso único `CONCIERGE-…` (`promotions.issue_concierge_coupon`,
  Promotion de valor fixo restrita ao canal da Concierge, pedido mínimo = o subtotal em que o valor ainda
  cabe no teto) aplicado por `cart.validate_and_apply_coupon`, as mesmas portas do cupom digitado na loja.
  Valem canal, pedido mínimo, "maior desconto ganha" (cupom fixo não empilha em linha já descontada) e o
  uso contado no commit. Se as portas não aplicam nada, o cupom some (transação) e a resposta é a R7.
- **Uma vez por pedido:** `Session.data["concierge_discount"]`; o cupom que o cliente já usa nunca é trocado.
- **Auditável:** no commit, o evento `concierge_discount` (ator `concierge`) entra no histórico do pedido;
  o Gestor mostra "Desconto da Concierge" com valor e cupom. No Admin, a promoção diz de qual conversa veio.
- **R7 ajustada** na tabela: até o teto, a Concierge concede; acima, sem sacola ou com cupom já aplicado,
  quem decide é a equipe.

## B) Cancelamento conforme a etapa
- **Mesma régua do site:** a Concierge cancela sozinha só quando `customer_orders.can_cancel` deixaria o
  cliente cancelar pela conta (pedido `new`/`accepted`, pagamento não capturado), pelo mesmo serviço
  (`customer_orders.cancel(order, actor="concierge")`). Estorno, estoque, nota e o aviso de
  cancelamento seguem o lifecycle de qualquer cancelamento.
- **De quem:** só pedido do próprio cliente, pela identidade da conversa (`customer_identity_filter`);
  número de pedido de outra pessoa não acha nada e vai para a equipe. Mais de um pedido em aberto sem
  dizer qual também vai para a equipe.
- **Confirmação:** "Cancelo o pedido X, com 2 × Pão Francês? Responda sim ou não."
  (`Conversation.flags["pending_cancel"]`, vale 30 min); só o "sim" do turno seguinte cancela, o "não"
  mantém, qualquer outra fala desfaz a pergunta. Se a etapa mudou entre a pergunta e o "sim", vai para a
  equipe.
- **Transparente:** evento `concierge_cancelled` no pedido ("Cancelado pela Concierge a pedido do cliente",
  com a fala dele), `cancelled_by = "concierge"`, nota na conversa do Admin.
- **Dinheiro (R6):** a resposta diz o que o sistema fez com o pagamento, lido depois do cancelamento
  ("O pagamento pendente foi cancelado, e nada foi cobrado.", "A reserva no cartão foi desfeita…").
- **R4 ajustada:** cancelamento fora do autoatendimento (em preparo, pago, de outra pessoa) vai para a equipe.

## Como verificar
```
# no worktree, com PYTHONPATH apontando para packages/* do worktree
pytest shopman/storefront/tests/test_concierge_discount.py shopman/storefront/tests/test_concierge_cancellation.py
pytest shopman/storefront/tests -k concierge
```

## Respostas do dono (03/10)
- Pedido pago NÃO é cancelado pela Concierge: segue com a equipe, como está.
- Teto padrão do desconto: 2,5%.

## Fora desta frente
- Pedido pago não é cancelado pela Concierge: o site também não deixa o cliente (o estorno de pedido pago
  é decisão da equipe). Se o dono quiser estorno automático pela Concierge, é mudar a régua do site, para
  os dois caminhos.
