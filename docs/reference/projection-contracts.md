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

### Histórico do Gestor × B.I.: o eixo da data

O Histórico (`shopman/backstage/projections/order_history.py`,
`GET /api/v1/backstage/orders/history/`) conta o período pelo dia em que o pedido
**fechou** (`Coalesce(completed_at, cancelled_at, returned_at, updated_at)`). O B.I.
conta a venda pelo dia em que o pedido foi **feito** (`created_at`). Uma encomenda
feita num dia e retirada no outro cai em dias diferentes nas duas leituras.

Por isso o link "Abrir os N pedidos" do B.I. (`overShortOrdersHref`) manda
`basis=ordered` na URL do Gestor, que vira `date_basis=ordered` no endpoint: o
Histórico filtra por `created_at` e abre os mesmos N que o B.I. contou. Sem o
parâmetro (`date_basis=closed`, o padrão), vale o eixo do fechamento. Tirar o
recorte do produto tira o eixo junto. Trava:
`test_ordered_basis_counts_by_the_day_the_order_was_made` e
`surfaces/orders-nuxt/tests/history.test.ts` (beta 05/11/2026, ge:BI-03).

### Gestor: agenda com cobertura

A lista de Encomendas do Gestor ganha, por dia, a conta do prometido contra o
planejado (`shopman/backstage/projections/preorder_coverage.py`,
`GET /api/v1/backstage/orders/preorder-coverage/`, mesma permissão do quadro). A
resposta é `{coverage: {days: [...]}, generated_at, contract_version}`; cada dia
casa com o grupo da lista pelo `date` (o `commitment_date` do cartão).

| Fato | De onde sai |
|---|---|
| **Prometido** | soma dos itens que valem agora (`order_composition`, combo aberto nos componentes) dos pedidos `accepted`, `preparing` e `ready` com aquele `delivery_date`: os de data futura e, de hoje, só a encomenda (`is_preorder` ou `kitchen_released_at`) |
| **Planejado** | lotes do Craftsman do produto NAQUELA data (`WorkOrder.output_sku`, `target_date`): `quantity` do planejado e do em andamento, `finished` do pronto; `void` não conta |

A encomenda de uma data só é coberta pelo lote daquela data (dono, 18/11/2026), a
mesma regra de `order_promise`. Estado do produto: `covered`, `short`, `no_batch`,
`made_to_order` (política `demand_ok`) e `from_stock` (sem ficha ativa e sem lote: a
casa não produz); os dois últimos ficam fora da conta de lote e vêm com
`planned_qty`, `missing_qty` e `surplus_qty` vazios. Estado do dia: `short` >
`no_batch` > `covered`, ou `not_batch_based` quando nada depende de lote.
`production_url` abre o Planejamento da Produção no dia (`/plan?date=`) e vem vazio
sem endereço configurado ou para quem não opera a Produção.

É rota própria, e não campo do quadro: a conta só muda quando uma encomenda é aceita
ou um lote é planejado, e o quadro é relido a cada evento de pedido. Custo fixo de
consultas, qualquer que seja o número de pedidos. Trava:
`shopman/backstage/tests/test_preorder_coverage.py`.

### Central (hub): o número no canto do ícone

A Central (`shopman/backstage/projections/hub.py`, `GET /api/v1/backstage/hub/`) é uma
grade de ícones: cada app é o ícone e o nome, e no máximo um indicador, o número no
canto superior direito do ícone (`attention_count` do tile; dono, 04/11/2026).

**Para que serve o número:** quantas coisas estão paradas esperando um gesto de quem
está operando, agora, que esta pessoa pode resolver. Movimento e informação não contam
e não aparecem na Central; nem o que espera outra pessoa. Zero: o ícone fica limpo.

| App | Conta | Não conta | Fonte (`projections/hub_queue.py`) |
|---|---|---|---|
| Gestor de Pedidos | pedido novo para aceitar; aviso de erro ou crítico não visto que se resolve no pedido | pedidos ativos do dia | `_orders`, `_alerts` |
| Cozinha | pedido de estação que passou da meta | pedidos nas estações | `_kds` |
| PDV | nada | encomenda para retirar na próxima hora (espera o cliente chegar), encomendas do dia, caixa aberto ou fechado | `_preorders`, `_pos_cash` |
| Produção | lote iniciado que passou do tempo da receita; aviso de erro ou crítico não visto (insumo insuficiente, por exemplo) | lotes finalizados hoje | `_production`, `_alerts` |
| Marketing | anúncio esperando decisão | campanhas ligadas | `_marketing_status` |
| Compras | nada | pedido a caminho (espera o fornecedor) | `_purchase_status` |
| B.I. | nada | vendas do período | `_bi_status` |
| Loja online | nada | aberta, pedidos online | `_store_status` |

Permissão: cada fonte só roda para quem passa no predicado da porta do app
(`_SOURCES`), e os avisos só entram para quem opera o app onde eles se resolvem; o
número é sempre do que esta pessoa pode resolver. O nome falado do ícone é o app e o
que o número conta, por extenso ("Gestor de Pedidos, 1 para aceitar"). A frase
`status_attention` continua no contrato (o trocador de apps do kit a mostra); a do PDV
existe sem número. Travas: `shopman/backstage/tests/test_hub_queue.py`
(`test_o_numero_do_icone_conta_so_o_que_espera_um_gesto_de_quem_opera`) e
`surfaces/hub-nuxt/tests/hubAppIndicator.test.ts`.

### PDV: o lastro da encomenda (WP-E2, D-041)

A encomenda de outro dia promete o que o lote planejado PARA a data cobre. Duas chaves,
apuradas pelo servidor (`shop/services/stock.py`, `plan_backing_on` e `over_plan_lines`,
sobre `adapters/stock.planned_on_date`: saldos com `target_date == data` e as reservas
ativas presas a eles); o PDV só as diz:

| Onde | Chave | Forma |
|---|---|---|
| `GET /pos/schedule/` (`build_pos_schedule`) | `plan_by_sku` | `{sku: {planned_qty, unclaimed_qty}}` para os SKUs do carrinho com lote planejado na data; `{}` hoje |
| `POST /pos/sale/review/` | `preorder_over_plan` | `[{sku, name, date, requested_qty, planned_qty, unclaimed_qty}]`, com o motivo `preorder_over_plan` em `approval_reasons` |

`planned_qty` é o lote planejado para a data, sem descontar reservas; `unclaimed_qty`, o que
desse lote ainda não está preso a outra encomenda (nunca maior que `planned_qty`). **A sobra
de hoje e a vitrine não entram em nenhum dos dois** (dono, 18/11/2026: "não oferecemos pães
de um dia para o outro! eles não ficam disponíveis para encomenda!"). Passa do plano quando o
pedido é maior que `unclaimed_qty`: o Validar trava e só o gerente libera. A liberação é o
carimbo do WP-E1 (`issue_sale_approval`), com as linhas em `scope.over_plan`; o fechamento
recusa carimbo de outros números. SKU sem lote planejado na data fica de fora (data sem plano,
WP-E3). Travas: `shopman/shop/tests/test_pos_encomenda_acima_do_plano_bloqueia.py`,
`surfaces/pos-nuxt/tests/encomendaAcimaDoPlano.test.ts` e os testes de componente
`PosPaymentWorkspace.overPlan` e `PosCartPanel.plan`.

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
