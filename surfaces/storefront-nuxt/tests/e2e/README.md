# E2E (Playwright) — storefront

Dois níveis, por dependência de dados:

## 1. Independentes de backend (rodam aqui, no CI)

`resilience.spec.ts` e `guards.spec.ts` cobrem comportamentos do app que não
precisam de dados de negócio: shell degradado com backend vazio, banner offline
(reconexão), guard de `/conta` (redireciona ao login), página 404 (noindex).

Sobem automaticamente um **mock backend** (`mockBackend.mjs`, respostas `{}`
rápidas) e o `nuxt preview` apontado a ele.

```bash
npm run build          # e2e roda sobre o preview de produção
npm run test:e2e
```

## 2. Fluxo crítico com dados: mora no E2E do Django, e roda no CI

O caminho do Dia 1 (PDP → sacola → OTP → checkout → pedido → acompanhamento)
precisa do Django real semeado, e por isso não vive aqui. Ele está em
`shopman/shop/tests/e2e/test_storefront_e2e.py`, dirigido por esta loja Nuxt
(build de produção) contra o Django semeado, no job **Storefront E2E
(Playwright)** do `omotenashi-gate.yml`, em todo PR e na fila de merge:

- `test_11`: retirada com Pix, e o pedido aparece na fila do operador.
- `test_12`: **entrega com cartão**, e o pedido aparece no acompanhamento
  (`/pedido/<ref>`) já com o pagamento autorizado. O cartão passa pelo adapter
  `payment_stripe` de produção contra um Stripe falso local
  (`shopman/shop/tests/e2e/fake_stripe.py`): sem rede e sem credencial.

Para rodar localmente, da raiz do repositório:

```bash
make storefront-e2e                       # seed + Django + loja + Stripe falso
make storefront-e2e args="-k test_12"     # só o Dia 1
```

O antigo `criticalFlow.spec.ts` (sempre `skip`) foi apagado: o fluxo que ele
prometia é o `test_12`.
