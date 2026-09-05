# Decisões de arquitetura (ADRs)

Cada ADR registra **uma decisão e o porquê dela**, para que ninguém precise
redescutir do zero o que já foi resolvido. Um ADR não é documentação de como o
código funciona — isso vive nos [guias](../guides/) e na
[referência](../reference/).

**Numeração é endereço, não ordem de importância.** Nunca renumere: o número é
citado em código, em outros ADRs, em PR e em memória de sessão. Ao adicionar,
pegue o próximo livre e acrescente uma linha aqui.

## Fundamentos

| # | Decisão |
|---|---|
| [001](adr-001-protocol-adapter.md) | Cores independentes, framework integrador, Protocol/Adapter para substituição |
| [004](adr-004-string-refs.md) | String refs para identificadores cross-domain |
| [005](adr-005-orchestrator-as-coordination-center.md) | Orquestrador centralizado e decisão consciente de design |
| [025](adr-025-signal-idiom-on-commit.md) | O idioma dos eventos entre pacotes: anúncio depois do COMMIT |

## Dinheiro e custo

| # | Decisão |
|---|---|
| [002](adr-002-centavos.md) | Convenção `_q` em centavos (int) para valores monetários |
| [022](adr-022-cashman-ledger.md) | O caixa é um pacote do Core: `cashman`, livro imutável por turno |
| [023](adr-023-cost-live-and-frozen.md) | Custo: vivo para precificar, congelado no fato para contar história |

## Pedido e lifecycle

| # | Decisão |
|---|---|
| [006](adr-006-order-status-semantics.md) | Semântica canônica do ciclo de vida de Order |
| [007](adr-007-lifecycle-dispatch-functional.md) | Lifecycle dispatch funcional e config-driven |
| [010](adr-010-handler-contract-and-autodiscovery.md) | Contrato handler↔dispatch e roadmap de autodiscovery |
| [003](adr-003-directives-sem-celery.md) | Directives sem Celery: fila interna + threshold de migração |

## Superfícies

| # | Decisão |
|---|---|
| [012](adr-012-headless-surface-contract.md) | Contrato headless de superfície: Projection com Actions |
| [013](adr-013-pos-offline-policy-and-surface-ownership.md) | Política offline do PDV e dono da superfície |
| [014](adr-014-surface-data-presentation-cut.md) | Corte dado/apresentação: Projection de dado vs Presentation |
| [016](adr-016-sse-first-realtime.md) | Tempo real por SSE, cross-surface e site-wide |
| [018](adr-018-surface-is-channel-with-commerce-policy.md) | Superfície é canal: uma entidade, com política comercial |

## Catálogo, produção e compras

| # | Decisão |
|---|---|
| [008](adr-008-pdp-nutrition.md) | Ingredientes e nutricional no PDP — Product é superfície, Recipe é fonte |
| [011](adr-011-formula-and-cashshift.md) | Fórmula sem FormulaPlan e caixa como CashShift |
| [017](adr-017-quality-as-production-outcome.md) | Qualidade é resultado da produção, não domínio novo |
| [024](adr-024-material-unit-base-and-purchase.md) | Conversão de unidade é cidadã de primeira classe: base única, conversões declaradas |
| [027](adr-027-recipe-book-authoring-vs-execution.md) | Inventário de receitas: autoria versionada separada da ficha de execução |

## Comercial e comunicação

| # | Decisão |
|---|---|
| [019](adr-019-promotion-belongs-to-the-orchestrator.md) | A promoção tem um dono: orquestrador, escopada por canal, com renúncia de frete |
| [020](adr-020-campaign-announces-it-does-not-sell.md) | Campanha anuncia, não vende |
| [009](adr-009-whatsapp-via-manychat.md) | WhatsApp via ManyChat: vendor lock-in consciente |
| [026](adr-026-concierge-lingua-do-modelo-dinheiro-do-codigo.md) | Concierge de WhatsApp: a língua é do modelo, o dinheiro é do código |

## B.I. e operação continuada

| # | Decisão |
|---|---|
| [021](adr-021-bi-cross-suite-read-layer.md) | B.I. cross-suite: agregação é leitura, o ledger segue dono do fato |
| [015](adr-015-backward-compat-policy-post-prod.md) | Política de backward-compat e migrations pós-produção |
