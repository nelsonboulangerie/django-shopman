# EXCELÊNCIA-GESTOR: revisão de excelência do Gestor de pedidos

Siga `docs/coordination/ROUNDS/EXCELENCIA-base.md` (objetivo, lentes, método, entrega e
limites). Este arquivo diz só o que é do Gestor. Entregue em
`docs/plans/EXCELENCIA-GESTOR-PLANO.md`.

**Ênfase: Encomendas e pedidos agendados.** É o caso mais complexo da casa, e a maior parte do
esforço vai para ele, sem abandonar o resto.

## Perímetro (onde os WPs podem escrever)

- `surfaces/orders-nuxt/`, exceto a seção Entregas;
- o que só o Gestor consome no backstage: `projections/order_queue.py` e as APIs de pedido e
  de histórico.

## Fronteiras (registrar, não mexer)

- **A seção Entregas** (TaOn, `deliveries.vue`) tem frente própria, em execução: as decisões de
  16/11 estão na memória `project_entregas_revisao_decisoes_16_11`. Leia, não proponha WP ali.
- O widget do iFood (#2323, #2455).
- O `operator-kit/`.
- A Cozinha, que é quem diz "Em preparo".
- A aba Encomendas do PDV.
- O `lifecycle.py` e os services do `shop`.
- O Core em `packages/orderman`.

## Papéis

- Quem opera o Gestor no dia a dia, com PIN.
- O Gerente.
- O cliente, pela loja, para criar os pedidos.
- Nunca o superusuário.

## Jornadas pela UI

1. Pedido de hoje: chegar, aceitar no prazo e recusar com motivo.
2. Preparo, Pronto, retirada e entrega, até concluir.
3. **Encomenda de ponta a ponta**:
   - o cliente encomenda pela loja e paga antes;
   - o Gestor aceita dentro dos 60 min;
   - a encomenda vive na lista dos próximos dias;
   - no dia, aparece na área de Hoje e no PDV, a partir da mesma fonte;
   - o card chega à Cozinha no horário menos o preparo e a antecedência, e NÃO como
     "Em preparo";
   - depois, retirada ou entrega.
4. **Encomenda que dá errado**:
   - a fornada muda ou atrasa;
   - falta um item;
   - o cliente cancela antes do preparo e depois dele;
   - o pagamento não confirma;
   - a loja fecha;
   - a fila de espera e a vaga paga.
5. Cruze a virada do dia e o fechamento.
6. Estados fiscais: nota recusada, DANFE e entrega sem CPF. Cada um tem a ação ao lado ou sai
   da tela.

Para criar pedidos, use a loja da sua pilha.

## Histórico (não refaça)

- Memórias `project_laudo_encomendas_storefront_09_11`, `project_encomenda_hora_certa_kds_09_11`
  e `project_gestor_de_pedidos_ridiculamente_facil`. Confira o que de "KDS na hora certa" já
  está no `main`.
- `docs/plans/completed/GESTOR-PEDIDOS-PLAN.md` e `docs/plans/suite-ux-v2/orders/laudo-orders-board.md`.
- `docs/plans/backstage-app-audits-2026-08-29/` (WP-03).
- As rodadas `docs/coordination/ROUNDS/{S3,S4,S9,T5,T6}-encomendas-*`.
- `docs/plans/WP-DATA-E-PROMESSA.md`.

## Foco

- **A promessa ao cliente sobrevive ao tempo**: entre o aceite e a entrega, toda mudança de
  fornada, saldo ou horário chega ao Gestor antes de virar surpresa, já com a ação pronta
  (avisar, remarcar, trocar, estornar).
- **Ridiculamente fácil**: todo estado entende-se de relance e tem a ação de um toque. Alerta
  sem ação vira ação ou sai.
- **Uma verdade só** entre o Gestor, o PDV, a Cozinha e a loja, para o mesmo pedido.

## Benchmarks

O Gestor de Pedidos do iFood, Toast (pedidos agendados e KDS), Square, Shopify (retirada
agendada) e Hotplate (pré-venda por fornada, o caso mais próximo da casa).

## Pilha isolada

- Django em `:8060`, banco `shopman_exc_gestor`.
- Gestor em `:3164`, loja em `:3160`, Cozinha em `:3163`, PDV em `:3162`.
- Nenhuma outra porta.
