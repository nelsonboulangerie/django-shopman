# Inventário de páginas Nuxt para a revisão de UX

Base: `7288b44624d195d5cbf37431184fe49ee71a43e0`, 29/10/2026.

Inventário estrutural de arquivos, não certificação funcional nem lista de URLs únicas. Páginas pai, índices aninhados e aliases podem compor o mesmo destino. Não inclui como páginas separadas os diálogos, modos e etapas de uma transação. Esses fluxos estão na análise por app do [plano de revisão](SHOPMAN-UX-PRODUCT-REVIEW-2026-10-29.md).

## Cobertura das superfícies

| Superfície | Papel registrado | Arquivos de página |
|---|---|---:|
| storefront | customer-storefront | 23 |
| hub | operator-launcher | 0 |
| pos | counter-sales | 13 |
| kds | kitchen-fulfillment | 3 |
| orders | operations-management | 13 |
| production | production-floor | 14 |
| marketing | marketing-management | 10 |
| bi | business-intelligence | 9 |
| purchase | procurement | 12 |
| kitchensink | developer-preview | 2 |
| status | public-status | 1 |

Total: **100 arquivos de página** em **11 superfícies**. A Central monta sua experiência diretamente em `app.vue`.

## Páginas por superfície

### storefront

Papel: `customer-storefront`. Tipo: `customer`. Destino: `digitalocean`.

| Arquivo | Caminho derivado do arquivo | Papel estrutural |
|---|---|---|
| [a.vue](../../surfaces/storefront-nuxt/app/pages/a.vue) | `/a` | Destino ou composição de página |
| [busca.vue](../../surfaces/storefront-nuxt/app/pages/busca.vue) | `/busca` | Destino ou composição de página |
| [colecao/[ref].vue](../../surfaces/storefront-nuxt/app/pages/colecao/[ref].vue) | `/colecao/[ref]` | Detalhe ou edição de registro |
| [conta/enderecos.vue](../../surfaces/storefront-nuxt/app/pages/conta/enderecos.vue) | `/conta/enderecos` | Destino ou composição de página |
| [conta/favoritos.vue](../../surfaces/storefront-nuxt/app/pages/conta/favoritos.vue) | `/conta/favoritos` | Destino ou composição de página |
| [conta/index.vue](../../surfaces/storefront-nuxt/app/pages/conta/index.vue) | `/conta` | Índice aninhado; conferir página pai |
| [conta/pedidos.vue](../../surfaces/storefront-nuxt/app/pages/conta/pedidos.vue) | `/conta/pedidos` | Destino ou composição de página |
| [conta/perfil.vue](../../surfaces/storefront-nuxt/app/pages/conta/perfil.vue) | `/conta/perfil` | Destino ou composição de página |
| [conta/preferencias.vue](../../surfaces/storefront-nuxt/app/pages/conta/preferencias.vue) | `/conta/preferencias` | Destino ou composição de página |
| [conta/seguranca.vue](../../surfaces/storefront-nuxt/app/pages/conta/seguranca.vue) | `/conta/seguranca` | Destino ou composição de página |
| [encerrar-acesso.vue](../../surfaces/storefront-nuxt/app/pages/encerrar-acesso.vue) | `/encerrar-acesso` | Destino ou composição de página |
| [entrar.vue](../../surfaces/storefront-nuxt/app/pages/entrar.vue) | `/entrar` | Destino ou composição de página |
| [faq.vue](../../surfaces/storefront-nuxt/app/pages/faq.vue) | `/faq` | Destino ou composição de página |
| [finalizar.vue](../../surfaces/storefront-nuxt/app/pages/finalizar.vue) | `/finalizar` | Destino ou composição de página |
| [gerenciar-aviso.vue](../../surfaces/storefront-nuxt/app/pages/gerenciar-aviso.vue) | `/gerenciar-aviso` | Destino ou composição de página |
| [index.vue](../../surfaces/storefront-nuxt/app/pages/index.vue) | `/` | Destino ou composição de página |
| [menu.vue](../../surfaces/storefront-nuxt/app/pages/menu.vue) | `/menu` | Destino ou composição de página |
| [oferta/[ref].vue](../../surfaces/storefront-nuxt/app/pages/oferta/[ref].vue) | `/oferta/[ref]` | Detalhe ou edição de registro |
| [pedido/[ref]/index.vue](../../surfaces/storefront-nuxt/app/pages/pedido/[ref]/index.vue) | `/pedido/[ref]` | Índice aninhado; conferir página pai |
| [privacidade.vue](../../surfaces/storefront-nuxt/app/pages/privacidade.vue) | `/privacidade` | Destino ou composição de página |
| [produto/[sku].vue](../../surfaces/storefront-nuxt/app/pages/produto/[sku].vue) | `/produto/[sku]` | Detalhe ou edição de registro |
| [sacola.vue](../../surfaces/storefront-nuxt/app/pages/sacola.vue) | `/sacola` | Destino ou composição de página |
| [termos.vue](../../surfaces/storefront-nuxt/app/pages/termos.vue) | `/termos` | Destino ou composição de página |

### hub

Papel: `operator-launcher`. Tipo: `operator`. Destino: `digitalocean`.

- [Entrada e fila da Central](../../surfaces/hub-nuxt/app/app.vue).

### pos

Papel: `counter-sales`. Tipo: `operator`. Destino: `digitalocean`.

| Arquivo | Caminho derivado do arquivo | Papel estrutural |
|---|---|---|
| [display.vue](../../surfaces/pos-nuxt/app/pages/display.vue) | `/display` | Destino ou composição de página |
| [index.vue](../../surfaces/pos-nuxt/app/pages/index.vue) | `/` | Destino ou composição de página |
| [preorders/[ref].vue](../../surfaces/pos-nuxt/app/pages/preorders/[ref].vue) | `/preorders/[ref]` | Detalhe ou edição de registro |
| [preorders/index.vue](../../surfaces/pos-nuxt/app/pages/preorders/index.vue) | `/preorders` | Índice aninhado; conferir página pai |
| [session/closing.vue](../../surfaces/pos-nuxt/app/pages/session/closing.vue) | `/session/closing` | Destino ou composição de página |
| [session/index.vue](../../surfaces/pos-nuxt/app/pages/session/index.vue) | `/session` | Índice aninhado; conferir página pai |
| [session/report.vue](../../surfaces/pos-nuxt/app/pages/session/report.vue) | `/session/report` | Destino ou composição de página |
| [settings/card-machines.vue](../../surfaces/pos-nuxt/app/pages/settings/card-machines.vue) | `/settings/card-machines` | Destino ou composição de página |
| [settings/kitchen.vue](../../surfaces/pos-nuxt/app/pages/settings/kitchen.vue) | `/settings/kitchen` | Destino ou composição de página |
| [settings/printers.vue](../../surfaces/pos-nuxt/app/pages/settings/printers.vue) | `/settings/printers` | Destino ou composição de página |
| [settings/seating.vue](../../surfaces/pos-nuxt/app/pages/settings/seating.vue) | `/settings/seating` | Destino ou composição de página |
| [settings/shortcuts.vue](../../surfaces/pos-nuxt/app/pages/settings/shortcuts.vue) | `/settings/shortcuts` | Destino ou composição de página |
| [settings/terminal.vue](../../surfaces/pos-nuxt/app/pages/settings/terminal.vue) | `/settings/terminal` | Destino ou composição de página |

### kds

Papel: `kitchen-fulfillment`. Tipo: `operator`. Destino: `digitalocean`.

| Arquivo | Caminho derivado do arquivo | Papel estrutural |
|---|---|---|
| [[ref].vue](../../surfaces/kds-nuxt/app/pages/[ref].vue) | `/[ref]` | Detalhe ou edição de registro |
| [index.vue](../../surfaces/kds-nuxt/app/pages/index.vue) | `/` | Destino ou composição de página |
| [pickup.vue](../../surfaces/kds-nuxt/app/pages/pickup.vue) | `/pickup` | Destino ou composição de página |

### orders

Papel: `operations-management`. Tipo: `operator`. Destino: `digitalocean`.

| Arquivo | Caminho derivado do arquivo | Papel estrutural |
|---|---|---|
| [[ref].vue](../../surfaces/orders-nuxt/app/pages/[ref].vue) | `/[ref]` | Detalhe ou edição de registro |
| [catalog.vue](../../surfaces/orders-nuxt/app/pages/catalog.vue) | `/catalog` | Destino ou composição de página |
| [channels/[ref]/catalog.vue](../../surfaces/orders-nuxt/app/pages/channels/[ref]/catalog.vue) | `/channels/[ref]/catalog` | Detalhe ou edição de registro |
| [checklists.vue](../../surfaces/orders-nuxt/app/pages/checklists.vue) | `/checklists` | Destino ou composição de página |
| [customers/[ref].vue](../../surfaces/orders-nuxt/app/pages/customers/[ref].vue) | `/customers/[ref]` | Detalhe ou edição de registro |
| [customers/groups.vue](../../surfaces/orders-nuxt/app/pages/customers/groups.vue) | `/customers/groups` | Destino ou composição de página |
| [customers/index.vue](../../surfaces/orders-nuxt/app/pages/customers/index.vue) | `/customers` | Índice aninhado; conferir página pai |
| [customers/merges.vue](../../surfaces/orders-nuxt/app/pages/customers/merges.vue) | `/customers/merges` | Destino ou composição de página |
| [feeds.vue](../../surfaces/orders-nuxt/app/pages/feeds.vue) | `/feeds` | Destino ou composição de página |
| [history.vue](../../surfaces/orders-nuxt/app/pages/history.vue) | `/history` | Destino ou composição de página |
| [index.vue](../../surfaces/orders-nuxt/app/pages/index.vue) | `/` | Destino ou composição de página |
| [settings.vue](../../surfaces/orders-nuxt/app/pages/settings.vue) | `/settings` | Destino ou composição de página |
| [workstations.vue](../../surfaces/orders-nuxt/app/pages/workstations.vue) | `/workstations` | Destino ou composição de página |

### production

Papel: `production-floor`. Tipo: `operator`. Destino: `digitalocean`.

| Arquivo | Caminho derivado do arquivo | Papel estrutural |
|---|---|---|
| [board.vue](../../surfaces/production-nuxt/app/pages/board.vue) | `/board` | Destino ou composição de página |
| [close.vue](../../surfaces/production-nuxt/app/pages/close.vue) | `/close` | Destino ou composição de página |
| [index.vue](../../surfaces/production-nuxt/app/pages/index.vue) | `/` | Destino ou composição de página |
| [mise-en-place.vue](../../surfaces/production-nuxt/app/pages/mise-en-place.vue) | `/mise-en-place` | Destino ou composição de página |
| [plan.vue](../../surfaces/production-nuxt/app/pages/plan.vue) | `/plan` | Destino ou composição de página |
| [quality.vue](../../surfaces/production-nuxt/app/pages/quality.vue) | `/quality` | Destino ou composição de página |
| [recipes/[ref]/edit.vue](../../surfaces/production-nuxt/app/pages/recipes/[ref]/edit.vue) | `/recipes/[ref]/edit` | Detalhe ou edição de registro |
| [recipes/[ref]/index.vue](../../surfaces/production-nuxt/app/pages/recipes/[ref]/index.vue) | `/recipes/[ref]` | Índice aninhado; conferir página pai |
| [recipes/compare.vue](../../surfaces/production-nuxt/app/pages/recipes/compare.vue) | `/recipes/compare` | Destino ou composição de página |
| [recipes/index.vue](../../surfaces/production-nuxt/app/pages/recipes/index.vue) | `/recipes` | Índice aninhado; conferir página pai |
| [recipes/new.vue](../../surfaces/production-nuxt/app/pages/recipes/new.vue) | `/recipes/new` | Destino ou composição de página |
| [recipes/review.vue](../../surfaces/production-nuxt/app/pages/recipes/review.vue) | `/recipes/review` | Destino ou composição de página |
| [reports.vue](../../surfaces/production-nuxt/app/pages/reports.vue) | `/reports` | Destino ou composição de página |
| [timers.vue](../../surfaces/production-nuxt/app/pages/timers.vue) | `/timers` | Destino ou composição de página |

### marketing

Papel: `marketing-management`. Tipo: `operator`. Destino: `digitalocean`.

| Arquivo | Caminho derivado do arquivo | Papel estrutural |
|---|---|---|
| [announcements/[id].vue](../../surfaces/marketing-nuxt/app/pages/announcements/[id].vue) | `/announcements/[id]` | Detalhe ou edição de registro |
| [history.vue](../../surfaces/marketing-nuxt/app/pages/history.vue) | `/history` | Destino ou composição de página |
| [index.vue](../../surfaces/marketing-nuxt/app/pages/index.vue) | `/` | Destino ou composição de página |
| [scheduled.vue](../../surfaces/marketing-nuxt/app/pages/scheduled.vue) | `/scheduled` | Destino ou composição de página |
| [second-control/[ref].vue](../../surfaces/marketing-nuxt/app/pages/second-control/[ref].vue) | `/second-control/[ref]` | Detalhe ou edição de registro |
| [settings/campaigns.vue](../../surfaces/marketing-nuxt/app/pages/settings/campaigns.vue) | `/settings/campaigns` | Destino ou composição de página |
| [settings/index.vue](../../surfaces/marketing-nuxt/app/pages/settings/index.vue) | `/settings` | Índice aninhado; conferir página pai |
| [settings/offers.vue](../../surfaces/marketing-nuxt/app/pages/settings/offers.vue) | `/settings/offers` | Destino ou composição de página |
| [settings/platforms.vue](../../surfaces/marketing-nuxt/app/pages/settings/platforms.vue) | `/settings/platforms` | Destino ou composição de página |
| [settings/templates.vue](../../surfaces/marketing-nuxt/app/pages/settings/templates.vue) | `/settings/templates` | Destino ou composição de página |

### bi

Papel: `business-intelligence`. Tipo: `operator`. Destino: `digitalocean`.

| Arquivo | Caminho derivado do arquivo | Papel estrutural |
|---|---|---|
| [cash.vue](../../surfaces/bi-nuxt/app/pages/cash.vue) | `/cash` | Destino ou composição de página |
| [customers.vue](../../surfaces/bi-nuxt/app/pages/customers.vue) | `/customers` | Destino ou composição de página |
| [delivery.vue](../../surfaces/bi-nuxt/app/pages/delivery.vue) | `/delivery` | Destino ou composição de página |
| [explore.vue](../../surfaces/bi-nuxt/app/pages/explore.vue) | `/explore` | Destino ou composição de página |
| [forecast.vue](../../surfaces/bi-nuxt/app/pages/forecast.vue) | `/forecast` | Destino ou composição de página |
| [index.vue](../../surfaces/bi-nuxt/app/pages/index.vue) | `/` | Destino ou composição de página |
| [profiles.vue](../../surfaces/bi-nuxt/app/pages/profiles.vue) | `/profiles` | Destino ou composição de página |
| [sales.vue](../../surfaces/bi-nuxt/app/pages/sales.vue) | `/sales` | Destino ou composição de página |
| [scenarios.vue](../../surfaces/bi-nuxt/app/pages/scenarios.vue) | `/scenarios` | Destino ou composição de página |

### purchase

Papel: `procurement`. Tipo: `operator`. Destino: `digitalocean`.

| Arquivo | Caminho derivado do arquivo | Papel estrutural |
|---|---|---|
| [base/costs.vue](../../surfaces/purchase-nuxt/app/pages/base/costs.vue) | `/base/costs` | Destino ou composição de página |
| [base/count.vue](../../surfaces/purchase-nuxt/app/pages/base/count.vue) | `/base/count` | Destino ou composição de página |
| [base/index.vue](../../surfaces/purchase-nuxt/app/pages/base/index.vue) | `/base` | Índice aninhado; conferir página pai |
| [base/materials/[sku].vue](../../surfaces/purchase-nuxt/app/pages/base/materials/[sku].vue) | `/base/materials/[sku]` | Detalhe ou edição de registro |
| [base/materials/index.vue](../../surfaces/purchase-nuxt/app/pages/base/materials/index.vue) | `/base/materials` | Índice aninhado; conferir página pai |
| [base/materials.vue](../../surfaces/purchase-nuxt/app/pages/base/materials.vue) | `/base/materials` | Página pai; compõe páginas filhas |
| [base/suppliers/[ref].vue](../../surfaces/purchase-nuxt/app/pages/base/suppliers/[ref].vue) | `/base/suppliers/[ref]` | Detalhe ou edição de registro |
| [base/suppliers/index.vue](../../surfaces/purchase-nuxt/app/pages/base/suppliers/index.vue) | `/base/suppliers` | Índice aninhado; conferir página pai |
| [base/suppliers.vue](../../surfaces/purchase-nuxt/app/pages/base/suppliers.vue) | `/base/suppliers` | Página pai; compõe páginas filhas |
| [buy.vue](../../surfaces/purchase-nuxt/app/pages/buy.vue) | `/buy` | Destino ou composição de página |
| [index.vue](../../surfaces/purchase-nuxt/app/pages/index.vue) | `/` | Destino ou composição de página |
| [receive.vue](../../surfaces/purchase-nuxt/app/pages/receive.vue) | `/receive` | Destino ou composição de página |

### kitchensink

Papel: `developer-preview`. Tipo: `internal`. Destino: `preview`.

| Arquivo | Caminho derivado do arquivo | Papel estrutural |
|---|---|---|
| [index.vue](../../surfaces/kitchensink-nuxt/app/pages/index.vue) | `/` | Destino ou composição de página |
| [suite.vue](../../surfaces/kitchensink-nuxt/app/pages/suite.vue) | `/suite` | Destino ou composição de página |

### status

Papel: `public-status`. Tipo: `customer`. Destino: `external`.

| Arquivo | Caminho derivado do arquivo | Papel estrutural |
|---|---|---|
| [index.vue](../../surfaces/status-nuxt/app/pages/index.vue) | `/` | Destino ou composição de página |

## Fontes de navegação a reconciliar

| App | Fonte principal |
|---|---|
| pos | [sections.ts](../../surfaces/pos-nuxt/app/presentation/sections.ts) |
| kds | [sections.ts](../../surfaces/kds-nuxt/app/presentation/sections.ts) |
| orders | [gestorSections.ts](../../surfaces/orders-nuxt/app/presentation/gestorSections.ts) |
| production | [productionSections.ts](../../surfaces/production-nuxt/app/presentation/productionSections.ts) |
| purchase | [purchaseSections.ts](../../surfaces/purchase-nuxt/app/presentation/purchaseSections.ts) |
| marketing | [useMarketingSections.ts](../../surfaces/marketing-nuxt/app/composables/useMarketingSections.ts) |
| bi | [biSections.ts](../../surfaces/bi-nuxt/app/presentation/biSections.ts) |
| hub | [app.vue](../../surfaces/hub-nuxt/app/app.vue) |
| storefront | [AppBottomNav.vue](../../surfaces/storefront-nuxt/app/components/AppBottomNav.vue) |
| status | [index.vue](../../surfaces/status-nuxt/app/pages/index.vue) |
| kitchensink | [index.vue](../../surfaces/kitchensink-nuxt/app/pages/index.vue) |

A rota derivada não resolve `routeRules`, `definePageMeta`, redirecionamentos ou restrições de acesso. Não usar esta coluna para publicar links operacionais sem conferir o roteamento do app.

## Cobertura que a etapa de prévias precisa acrescentar

- Estados e ações de cada tarefa, inclusive os que vivem na mesma URL.
- Permissões mínimas e combinadas, posto fixo e pessoa com múltiplas funções.
- Relação entre cada função atual e seu destino proposto por dispositivo.
- Links entre apps com contexto e retorno; acesso por busca e por link direto.
- Checkout, pagamento, recebimento e publicação com respostas de sucesso, recusa e resultado desconhecido simuladas.
- Monitores passivos e rotas públicas sem sessão de operador.

Este inventário não declara concluída a validação visual ou de usabilidade de todas essas páginas.
