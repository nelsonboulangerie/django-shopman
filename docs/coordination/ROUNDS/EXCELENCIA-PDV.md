# EXCELÊNCIA-PDV: revisão de excelência do PDV

Siga `docs/coordination/ROUNDS/EXCELENCIA-base.md` (objetivo, lentes, método, entrega e
limites). Este arquivo diz só o que é do PDV. Entregue em `docs/plans/EXCELENCIA-PDV-PLANO.md`.

## Perímetro (onde os WPs podem escrever)

- `surfaces/pos-nuxt/`;
- o que só o PDV consome no backstage: as projections e os services do PDV e do caixa em
  `shopman/backstage/` (`pos`, `cash`, `closing`), e as APIs `pos_settings`,
  `pos_concurrency` e `seating`.

## Fronteiras (registrar, não mexer)

- `surfaces/operator-kit/`: PIN, trava do dispositivo, autorização do gerente e troca de
  operador. Os oito apps sentem a mudança.
- A Cozinha (KDS) e a Tela do cliente que o PDV abre.
- Os services de pedido, estoque, pagamento e promoção do `shop`.
- O Core em `packages/` (`cashman`, `orderman`, `stockman`).

## Papéis

- A Caixa, com PIN.
- O Gerente, escolhido da lista e assinando com o próprio PIN.
- Nunca o superusuário.

## Jornadas pela UI

1. Abrir o caixa.
2. Venda de balcão em dinheiro, Pix, cartão e maquininha.
3. Venda com cliente, desconto e gerente.
4. Item de fornada sem saldo, e item feito na hora (ADR-040).
5. Encomenda pelo PDV, do dia e de outro dia: assistente, dia e horário, sinal ou pago.
6. Aba Encomendas: receber e entregar, com a Tela do cliente acompanhando.
7. Cancelar e estornar.
8. Sem conexão (`docs/plans/WP-PDV-SEM-CONEXAO.md`).
9. Troca de operador e trava.
10. Fechamento do caixa pela Caixa e pela gerência.

Faça tudo em 375 px e no desktop, que é o uso principal do PDV.

## Histórico (não refaça)

- O laudo beta de 07/11 (memória `project_laudo_pdv_beta_07_11`, PRs #2209 a #2230).
- `docs/plans/PDV-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-10.md`.
- `docs/reference/backstage-pos-surface-contract.md` e ADR-013.
- As rodadas `docs/coordination/ROUNDS/{T1,T1b,T4,S8,V4-PDV,D42}-*`.

## Foco

- **A promessa ao balcão**: o que o operador vende ou promete para um dia precisa bater com a
  fornada e o saldo, inclusive quando a venda nasce sem conexão.
- **Dinheiro sem brecha**: troco, sangria, conta na casa, desconto e estorno, sempre com o
  gerente certo e o valor à vista.
- **Velocidade de balcão**: menos toques que o melhor concorrente, sem perder a conferência.

## Benchmarks

Square, Toast, Shopify POS e Lightspeed; no Brasil, Saipos e Consumer.

## Pilha isolada

- Django em `:8050`, banco `shopman_exc_pdv`.
- PDV em `:3152`, Cozinha em `:3153`.
- Nenhuma outra porta.
