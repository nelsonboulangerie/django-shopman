# Contratos de projection compartilhados (BE↔FE)

> O artefato único que os dois lados são obrigados a respeitar.

## O problema que isto fecha

Antes (auditoria de 26/08/2026): o BE travava o que emite em asserts escritos à
mão, e o vitest dos apps Nuxt consumia fixtures TAMBÉM escritas à mão. Um rename
de chave feito "completo" (BE + teste BE + fixture FE, tudo junto, tudo verde)
passava por todos os gates e quebrava só na tela do cliente.

## O mecanismo

Os JSONs em [`contracts/projections/`](../../contracts/projections/) são o
contrato. Ninguém os edita à mão.

**Lado Django (gerador e guardião):**
`shopman/storefront/tests/test_shared_projection_contracts.py` constrói um
cenário canônico determinístico (um produto por estado de disponibilidade),
serializa a projection real e compara byte a byte com o snapshot commitado.
Valores presos ao relógio são normalizados (`<today>`/`<tomorrow>`/`<datetime>`)
— o contrato trava estrutura e valores estáveis, nunca o relógio.

**Lado Nuxt (consumidor):**
`surfaces/storefront-nuxt/tests/projectionContracts.test.ts` importa o MESMO
arquivo e (1) o atribui aos tipos TS — a atribuição roda no `npm run typecheck`
do Surfaces Gate, então rename de chave no BE reprova o typecheck do FE; (2) o
atravessa pelas funções de presentation reais — o FE nunca testa contra uma
forma que o BE não produz mais.

### Marketing v2

Marketing usa geração estrita, não fixture TypeScript manual:

| Artefato | Fonte/consumidor |
|---|---|
| `contracts/projections/marketing_v2.schema.json` | schema da projection v2 |
| `contracts/openapi/marketing_v2.openapi.json` | contrato HTTP OpenAPI 3.1 |
| `surfaces/marketing-nuxt/app/generated/marketingClient.ts` | cliente Nuxt gerado |

`python manage.py export_marketing_client` grava os três; `--check` compara a saída
em memória byte a byte com o repositório e é bloqueante no Runtime Gate. O contrato
cobre painel, detalhe de anúncio e histórico paginado, com ETag, versão, request ID e
erro estável. Projection v2 não transporta copy de UX, PII ou membership; ações vêm
resolvidas pelo backend. Rotas e ownership:
[`marketing-surface-contract.md`](marketing-surface-contract.md).

## Mudou o contrato de propósito?

```bash
SHOPMAN_UPDATE_CONTRACTS=1 .venv/bin/python -m pytest shopman/storefront/tests/test_shared_projection_contracts.py
```

Revise o diff de `contracts/projections/` (o FE consome esse arquivo), ajuste o
consumidor se preciso, e commite **BE + JSON + FE no mesmo PR**. O diff do JSON
é o anúncio da mudança de contrato — é para gritar no review.

## Estendendo a outras superfícies

O padrão é por superfície: um módulo gerador no app Django dono da projection,
um teste consumidor no app Nuxt dono da tela, e os JSONs em
`contracts/projections/<superficie>_<projection>.json`. Fatia atual:
`storefront_catalog`, `storefront_product_detail` e `marketing_v2`. Candidatas
seguintes: `order_tracking`, `pos` (comanda/checkout), `kds`, `order_queue`.
