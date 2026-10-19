# Decisões de arquitetura (ADRs)

Este é o índice único das decisões de arquitetura. Cada ADR registra uma decisão e o
porquê dela; guias e referências descrevem a implementação corrente.

**Numeração é endereço, não ordem de importância.** Nunca renumere uma ADR válida. Em
caso de colisão, somente o arquivo mais novo recebe o próximo número livre, e todas as
referências desse contexto acompanham a mudança.

O status é exatamente um destes valores:

- `Proposto`
- `Aceito`
- `Aceito; emendado por ADR-NNN`
- `Substituído por ADR-NNN`

O dono é a parte arquitetural responsável por manter a decisão. O gate
`make adr-governance` confere número único, título e status canônicos, a bijeção entre
este índice e os arquivos e a relação em ambas as pontas: quando o status aponta para uma
ADR sucessora, o cabeçalho da sucessora deve referenciar a predecessora. O backlink não
altera o status da sucessora nem cria uma relação circular.

| # | Título | Status | Dono | Data | Tema |
|---|---|---|---|---|---|
| [001](adr-001-protocol-adapter.md) | Cores independentes, framework integrador, Protocol/Adapter para substituição | Aceito | Arquitetura dos kernels | 2026-04-15 | Fronteiras |
| [002](adr-002-centavos.md) | Convencao _q em centavos (int) para valores monetarios | Aceito | Suite | 2025-01-20 | Dinheiro |
| [003](adr-003-directives-sem-celery.md) | Directives sem Celery: fila interna + threshold de migração | Aceito | Orquestrador | 2025-01-20 | Assíncrono |
| [004](adr-004-string-refs.md) | String refs para identificadores cross-domain | Aceito | Arquitetura dos kernels | 2026-04-14 | Identidade técnica |
| [005](adr-005-orchestrator-as-coordination-center.md) | Orquestrador centralizado e decisao consciente de design | Aceito | Orquestrador | 2026-04-06 | Fronteiras |
| [006](adr-006-order-status-semantics.md) | Semântica canônica do ciclo de vida de Order | Aceito | Orderman | 2026-04-14 | Pedido |
| [007](adr-007-lifecycle-dispatch-functional.md) | Lifecycle dispatch funcional e config-driven | Aceito | Orquestrador | 2026-04-15 | Lifecycle |
| [008](adr-008-pdp-nutrition.md) | Ingredientes e informação nutricional no PDP — Product é superfície, Recipe é fonte opcional | Aceito | Offerman e Craftsman | 2026-04-17 | Catálogo |
| [009](adr-009-whatsapp-via-manychat.md) | WhatsApp via ManyChat: vendor lock-in consciente | Aceito | Orquestrador | 2026-04-18 | Comunicação |
| [010](adr-010-handler-contract-and-autodiscovery.md) | Contrato handler↔dispatch e roadmap de autodiscovery | Aceito | Orquestrador | 2026-04-24 | Directives |
| [011](adr-011-formula-and-cashshift.md) | Formula sem FormulaPlan e caixa como CashShift | Aceito; emendado por ADR-022 | Craftsman e Cashman | 2026-05-11 | Produção e caixa |
| [012](adr-012-headless-surface-contract.md) | Contrato headless de superficie: Projection com Actions | Aceito | Read-side | 2026-05-15 | Superfícies |
| [013](adr-013-pos-offline-policy-and-surface-ownership.md) | POS offline policy and surface ownership | Aceito | Superfície PDV | 2026-05-23 | Superfícies |
| [014](adr-014-surface-data-presentation-cut.md) | Corte dado/apresentação nas superfícies: Projection de dado vs Presentation | Aceito | Read-side | 2026-06-05 | Superfícies |
| [015](adr-015-backward-compat-policy-post-prod.md) | Política de backward-compat e migrations pós-produção | Aceito | Suite | 2026-06-26 | Evolução |
| [016](adr-016-sse-first-realtime.md) | Tempo real por SSE, cross-surface e site-wide | Aceito | Orquestrador | 2026-07-07 | Tempo real |
| [017](adr-017-quality-as-production-outcome.md) | Qualidade e o resultado da producao: nao e dominio novo | Aceito | Craftsman | 2026-08-07 | Produção |
| [018](adr-018-surface-is-channel-with-commerce-policy.md) | Superficie e canal: uma entidade, com politica comercial | Aceito | Orquestrador | 2026-08-08 | Canais |
| [019](adr-019-promotion-belongs-to-the-orchestrator.md) | A promocao tem um dono: orquestrador, escopada por canal, com renuncia de frete | Aceito | Orquestrador | 2026-08-08 | Preço e promoção |
| [020](adr-020-campaign-announces-it-does-not-sell.md) | Campanha anuncia, nao vende | Aceito | Orquestrador | 2026-08-08 | Marketing |
| [021](adr-021-bi-cross-suite-read-layer.md) | B.I. cross-suite: agregação é leitura, o ledger segue dono do fato | Aceito | Read-side de B.I. | 2026-08-14 | B.I. |
| [022](adr-022-cashman-ledger.md) | O caixa é um pacote do Core: `cashman`, livro imutável por turno | Aceito | Cashman | 2026-08-18 | Caixa |
| [023](adr-023-cost-live-and-frozen.md) | Custo: vivo para precificar, congelado no fato para contar história | Aceito | Buyman e Craftsman | 2026-08-19 | Custo |
| [024](adr-024-material-unit-base-and-purchase.md) | Conversão de unidade é cidadã de primeira classe: base única, conversões declaradas | Aceito | Buyman | 2026-08-19 | Compras |
| [025](adr-025-signal-idiom-on-commit.md) | O idioma dos eventos entre pacotes: anúncio depois do COMMIT | Proposto | Arquitetura dos kernels | 2026-08-19 | Eventos |
| [026](adr-026-concierge-lingua-do-modelo-dinheiro-do-codigo.md) | Concierge de WhatsApp: a língua é do modelo, o dinheiro é do código | Proposto | Orquestrador | 2026-09-03 | Conversação |
| [027](adr-027-recipe-book-authoring-vs-execution.md) | Inventário de receitas: autoria versionada separada da ficha de execução | Aceito | Craftsman | 2026-09-03 | Produção |
| [028](adr-028-production-internal-label-scope.md) | Pesagem e identificação interna não são rótulo de venda | Aceito | Craftsman e Backstage | 2026-09-10 | Produção |
| [029](adr-029-marketing-fire-logical-rate-limit.md) | Quota lógica do disparo manual de Marketing | Aceito | Marketing | 2026-09-11 | Marketing |
| [030](adr-030-operator-nuxt-dois-servicos.md) | Os oito apps Nuxt de operador em dois services | Aceito | Superfícies de operador | 2026-09-17 | Topologia |
| [031](adr-031-marketing-ceremony-proportional-to-consequence.md) | A cerimônia de confirmação do Marketing mede a consequência | Aceito; emendado por ADR-032 | Marketing | 2026-09-17 | Segurança operacional |
| [032](adr-032-marketing-ceremony-threshold-is-proportional.md) | O limiar da cerimônia é proporcional à casa, e mede pessoas | Aceito; emendado por ADR-033 | Marketing | 2026-09-17 | Segurança operacional |
| [033](adr-033-marketing-typed-phrase-follows-the-irreversible.md) | A frase digitada segue o que não tem desfazer | Aceito | Marketing | 2026-09-18 | Segurança operacional |
| [034](adr-034-legal-archive-cited-by-the-order.md) | O pedido cita a versão de Termos e Privacidade que valia, numa cópia que não muda | Aceito | Orderman | 2026-09-24 | Legal |
| [035](adr-035-entrega-sem-cpf-sai-presencial.md) | Entrega sem CPF é aceita em todo canal, e a NFC-e sai presencial | Aceito | Fiscal e Orquestrador | 2026-10-13 | Fiscal |
| [036](adr-036-loja-online-paga-ao-pedir.md) | Loja online paga ao pedir, com prazo de aceite e estorno automático | Aceito | Storefront e Payman | 2026-10-14 | Pagamento |
| [037](adr-037-decision-ownership.md) | Titularidade das decisões | Aceito | Suite | 2026-10-16 | Fronteiras |
| [038](adr-038-operator-surface-security-envelope.md) | Envelope de segurança compartilhado das surfaces de operador | Aceito | Operator Kit | 2026-09-09 | Segurança de superfície |
| [039](adr-039-persistent-stock-alert-occurrences.md) | “Avise-me” é assinatura persistente com ocorrências distintas | Aceito | Storefront e Orquestrador | 2026-09-11 | Comunicação |
| [040](adr-040-baixa-de-insumo-na-venda-do-feito-na-hora.md) | Baixa de insumo na venda do item feito na hora | Proposto | Orquestrador | 2026-10-19 | Estoque |
| [041](adr-041-topologia-das-superficies-apps-federados.md) | Topologia das superfícies: apps federados sob uma layer e uma Central | Proposto | Superfícies | 2026-10-19 | Topologia |
