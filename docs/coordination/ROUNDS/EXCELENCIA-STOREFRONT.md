# EXCELÊNCIA-STOREFRONT: revisão de excelência da loja

Siga `docs/coordination/ROUNDS/EXCELENCIA-base.md` (objetivo, lentes, método, entrega e
limites). Este arquivo diz só o que é da loja. Entregue em
`docs/plans/EXCELENCIA-STOREFRONT-PLANO.md`.

## Perímetro (onde os WPs podem escrever)

- `surfaces/storefront-nuxt/`;
- `shopman/storefront/` (`api`, `presentation`, `intents`, `services`), **exceto**
  `shopman/storefront/concierge/`.

## Fronteiras (registrar, não mexer)

- **A Concierge** tem frente própria, em execução (CONCIERGE-R3).
- O Gestor e o PDV, que recebem o pedido.
- Os services de disponibilidade, estoque, pagamento e promoção do `shop`.
- O `lifecycle.py`.
- O Core em `packages/`.

## A voz da loja (exceção escrita, não erro)

- Fala com o cliente em português, nas rotas e na copy.
- Usa "aparelho".
- Fala na voz feminina da Concierge.
- Para o cliente, só existe "Indisponível".

As regras estão no CLAUDE.md e em `docs/reference/omotenashi-copy.md`.

## Papéis

- O cliente novo, que entra por OTP.
- O cliente que volta.
- O operador do Gestor, com PIN, só para aceitar ou recusar o pedido.
- Nunca o superusuário.

## Jornadas pela UI

1. Cardápio, busca e produto: disponível, Indisponível, fornada futura e item que acaba
   enquanto o cliente olha.
2. A sacola.
3. Entrar: OTP e cliente que volta.
4. Finalizar: retirada e entrega, data e horário, endereço fora da área, cupom, Pix e cartão.
5. Acompanhamento até a entrega.
6. Cancelar antes do preparo e depois dele.
7. A conta.
8. **Encomenda**:
   - item de fornada futura;
   - a janela de 30 dias;
   - fornada anterior com saldo que libera a data;
   - o prazo de aceite;
   - a fila de espera com o pedido pago.
9. Loja fechada, corte e virada do dia.

Faça tudo em 375 px primeiro, depois em 1366 px.

## Histórico (não refaça)

- Memórias `project_laudo_storefront_beta_06_11` e `project_laudo_encomendas_storefront_09_11`
  (PRs #2188 a #2199, #2253, #2254, #2257 e #2289 a #2297).
- `docs/plans/WP-DATA-E-PROMESSA.md` e `docs/plans/WP-FICHA-DE-PRODUTO-E-PROMESSA.md`.
- `docs/reference/headless-surface-contract.md` e `docs/guides/storefront_backend_surface.md`.

## Foco

- **Nada que o cliente lê fica velho**: disponibilidade, data, horário, preço e estado do
  pedido refletem a produção e o estoque no momento da leitura (SSE primeiro, ADR-016) e no
  momento do pagamento.
- **A encomenda é a joia**: a experiência de reservar o pão de amanhã precisa ser melhor que
  ir à padaria.
- **Confiança no pagamento**: nunca cobrar o que não pode ser entregue, e nunca deixar dúvida
  sobre o que foi cobrado.

## Benchmarks

iFood, Rappi, o checkout da Shopify, Hotplate (pré-venda por fornada), Toast Online Ordering e
o pedido antecipado da Starbucks.

## Pilha isolada

- Django em `:8070`, banco `shopman_exc_loja`, com pagamento falso.
- Loja em `:3170`, Gestor em `:3174`.
- Nenhuma outra porta.
