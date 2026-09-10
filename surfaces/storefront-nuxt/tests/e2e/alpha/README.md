# Suíte E2E do storefront contra o alpha

Suíte de revisão alpha dirigida por UI (Playwright) contra
`https://alpha.nelsonboulangerie.com.br` — sem mock: interage com a loja real,
login por OTP (código de teste exibido pelo ambiente), pedidos reais (retirada e
entrega), pagamento (captura simulada do adaptador mock) e acompanhamento.

## Rodar

```bash
npm ci                      # na primeira vez (surfaces/storefront-nuxt)
npx playwright test --config=tests/e2e/alpha/playwright.config.ts
```

Cobertura (25 testes):

| Spec | O que cobre |
|---|---|
| `01-smoke` | home, menu, PDP, busca, 404, terms/privacy, sem erros de console |
| `02-happy-path` | login → menu → carrinho → checkout (retirada) → pedido → tracking |
| `03-personas` | convidado (guardas), cliente recorrente (conta/histórico), entrega com CEP novo |
| `04-scenarios` | coleção, oferta, busca vazia, cupom inválido, favoritos, refazer, cancelamento |
| `05-edge-cases` | telefone inválido, OTP errado, quantidade, sacola vazia, loja fechada, checkout vazio |

## Cuidados

- **Rate-limit do login**: o alpha limita `request-code` a 5/min por IP.
  `helpers.ts` faz pacing de 75s entre logins e retry de 60s quando limitado;
  por isso `workers: 1` e sem paralelismo entre workers.
- **Horário de funcionamento**: fechado (fora de Seg–Sáb 9h–18h), o checkout
  agenda para o dia seguinte ("encomendar para o próximo dia"); aberto, o passo
  "Quando" oferece Hoje e o pedido do mesmo dia passa por aceite otimista →
  captura do Pix (mock). A suíte cobre o fluxo agendado em qualquer horário e o
  do mesmo dia quando a loja está aberta.
- **Dados**: os testes criam pedidos reais no alpha (prefixo de cliente
  "QA Alpha Tester", telefone 11 99999-9999) — apagar via Admin quando não
  forem mais úteis.
