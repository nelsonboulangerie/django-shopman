# Planos Ativos

> Atualizado em 2026-10-21.

Este diretório deve conter apenas plano vivo, spec ativa ou backlog explícito.
Planos concluídos ficam em [`completed/`](completed/). Material histórico incerto
fica em [`_quarantine/`](_quarantine/).

O [inventário mecânico completo](INDEX.md) cobre todo arquivo que permanece na
árvore viva. A presença no inventário não atribui estado nem presume conclusão;
as tabelas abaixo são a classificação semântica explícita.

> A spec canônica de endereço do cliente saiu daqui: é referência viva em
> [`docs/reference/ADDRESS-UX-PLAN.md`](../reference/ADDRESS-UX-PLAN.md) (ler antes
> de tocar qualquer tela de endereço).

> `copy-wiring-backlog.txt` é **artefato de gate** (lido por
> `shopman/shop/tests/test_omotenashi_copy_keys.py::test_copy_wiring_backlog`):
> lista as chaves de copy ainda não religadas. Não mover nem renomear.

## Gate de go-live (⏳ bloqueados no dono / externo)

| Plano | Estado |
|-------|--------|
| [`GO-LIVE-READINESS-PLAN.md`](GO-LIVE-READINESS-PLAN.md) | **Fonte única do estado de go-live**, reauditada em 2026-10-21 na baseline `4541f0a8a040`: deploy, smoke, health, ready, drift e backup verificados; `production-readiness` tem 5 OK e 3 FAIL por perfil staging/mock, dinheiro/fiscal sem prova de produção e chaves de corte ausentes. Os demais gates externos e operacionais permanecem explícitos na matriz. |
| [`GO-LIVE-CREDENTIALS-MATRIX.md`](GO-LIVE-CREDENTIALS-MATRIX.md) | Contrato de nomes e maturidade: separa credencial declarada, adapter, boot gate, sandbox/homologação e produção; não contém valores nem presume escopo v1. |
| [`PRODUCT-V1-SCOPE-BACKLOG.md`](PRODUCT-V1-SCOPE-BACKLOG.md) | Índice-mestre de escopo do v1; gate de produto do go-live. |

## Ativos / em andamento (⏳)

| Plano | Estado |
|-------|--------|
| [Revisão de produto e UX dos apps Nuxt](SHOPMAN-UX-PRODUCT-REVIEW-2026-10-29.md) | Análise e prévias locais em 29/10/2026. Gestor e Compras com lateral única ou dois níveis, mobile-first, cabeçalho e navegação entre apps. Nenhuma variante aprovada; implementação e deploy continuam sem autorização. |
| [`WP-RELEASE-01-versoes-de-apps-sem-quebra.md`](WP-RELEASE-01-versoes-de-apps-sem-quebra.md) | Estratégia executável para build imutável, promoção alpha → produção, convivência V1/V2, canário e rollback; Marketing V2 será o piloto. |
| [`SUITE-UX-PLAN.md`](SUITE-UX-PLAN.md) | Medição das três varreduras de 22/09 (navegação e cabeçalhos · primitivas · fronteira e copy) e o redesenho da suíte em 9 WPs. Diagnóstico: nenhum app está mal desenhado, **o que não existe é o entre** — o token de 44px é respeitado 214× no Gestor e **zero** em cinco apps. WP-UX-1 (barra de seções canônica) entregue; WP-UX-3, 4 e 7 em PR; 5 decisões de vocabulário e produto esperando o dono na §4. |
| [`WP-TELAS-DE-PAREDE.md`](WP-TELAS-DE-PAREDE.md) | Exploração (18/09), nada implementado — **as 5 decisões do dono já estão tomadas**. Inventário achou **5** superfícies passivas; a mais madura (menuboard) não estava na lista. Telas **não** tem domínio próprio (ADR-018): é capability de rota + seção do Hub + sujeito `display` de device trust. Pareamento por código vence encurtador; `TrustedDevice.DISPLAY` já existe. Decidido: seção "Telas" · **zero 301, nenhum legado** · letreiro ganha SSE (sobe p/ Fase 3) · tabela `Screen` em `shop/models/` · device trust de tela **eterno**, com revogação visível como contrapartida. 4 fases, nenhuma bloqueada. |
| [`FISCALMAN-PLAN.md`](FISCALMAN-PLAN.md) | S0–S4 concluídos e verdes; resta S5 (NF-e mod. 55/resale) + contador valida NCM/CSC/IBPT. |
| [`IFOOD-DIRECT-INTEGRATION-PLAN.md`](IFOOD-DIRECT-INTEGRATION-PLAN.md) | Integração direta entregue; ensaio autorizado na loja de teste concluído em 20/10 com restauração exata (#1929, #1962). Credenciais e homologação comercial de produção continuam externas e pendentes. |
| [`DELIVERY-EXTERNAL-LOGISTICS-PLAN.md`](DELIVERY-EXTERNAL-LOGISTICS-PLAN.md) | Machine (courier) construída e `Signature-V2` verificada no webhook; fora do código, credenciais centrais e homologação continuam pendentes. |
| [`DELIVERY-GEOCODING-AND-FEEDBACK-PLAN.md`](DELIVERY-GEOCODING-AND-FEEDBACK-PLAN.md) | Cascata de geocoding entregue; pendente robustez multi-provedor + feedback omotenashi. |
| [`OPERATION-DOMAIN-PLAN.md`](OPERATION-DOMAIN-PLAN.md) | Baseline de modelos/Admin implementado; próxima camada (superfície de execução, BI) aberta. |
| [`OPERATION-RUNBOOKS-PLAN.md`](OPERATION-RUNBOOKS-PLAN.md) | Baseline de runbooks/diagnose concluído; snapshot/smoke real de gateway bloqueado por credenciais. |
| [`OMOTENASHI-FIRST-FULLNESS-PLAN.md`](OMOTENASHI-FIRST-FULLNESS-PLAN.md) | Algumas rodadas entregues; maioria dos WP-OF-* não executados. |
| [`EXCELLENCE-AUDIT-2026-07.md`](EXCELLENCE-AUDIT-2026-07.md) | Auditoria-mãe (16 lentes); Onda 0 executada; Ondas 1–3 abertas. |
| [`WP-PROGRESSIVE-SSR-SSE-CONTINUITY.md`](WP-PROGRESSIVE-SSR-SSE-CONTINUITY.md) | Exploração ativa do SSR de Continuidade Semântica; baseline preservada, piloto e gates definidos; implementação ainda não autorizada. |
| [`SEO-PLAN.md`](SEO-PLAN.md) | SEO técnico entregue; capítulo permanente (conteúdo/keywords futuros). |

## Backlog / futuro (📋)

| Plano | Estado |
|-------|--------|
| [`WHATSAPP-CONCIERGE-PLAN.md`](WHATSAPP-CONCIERGE-PLAN.md) | Concierge de WhatsApp: pedido por conversa com modelo de linguagem, ferramentas determinísticas, resposta assíncrona via ManyChat ([ADR-026](../decisions/adr-026-concierge-lingua-do-modelo-dinheiro-do-codigo.md)); código da F1 escrito, aguarda palavra do dono. |
| [`WP-SUGESTAO-ADICIONAL-E-SUBSTITUTO.md`](WP-SUGESTAO-ADICIONAL-E-SUBSTITUTO.md) | Um motor de sugestão (adicional que combina, substituto à altura) para site e concierge; proposto, aguarda o dono. |
| [`WP-ATRIBUTOS-DE-PRODUTO.md`](WP-ATRIBUTOS-DE-PRODUTO.md) | Atributos de produto com definição (registro no `shop`, valores no metadata, zero legado, Core intocado); proposto. |
| [`PRODUCTION-FORECAST-BOARD-PLAN.md`](PRODUCTION-FORECAST-BOARD-PLAN.md) | Painel estilo aeroporto para vendas/encomendas (o que dá para prometer por data). |
| [`STATUS-BAR-CTA-CONFIG-PLAN.md`](STATUS-BAR-CTA-CONFIG-PLAN.md) | CTA da status-bar (Ligar/Mensagem) configurável; base entregue no PR #21, resto aberto. |


## Concluídos em 2026-10-19 (faxina da frente 10)

Arquivados em [`completed/`](completed/) depois de conferir cada plano contra o código
do `main` (uma ou duas buscas por plano). O que restava neles era ação do dono ou de
terceiro (credencial, contador, hardware, ativação de flag), item já rastreado em
frente própria (iFood, Concierge V2, TEF Stone, Google Merchant push) ou plano
substituído por outro. Detalhe do que falta para o go-live: seção 10 de
[`COORDENACAO-GO-LIVE.md`](COORDENACAO-GO-LIVE.md).

- `completed/ACCESS-LINK-UNIFICATION-PLAN.md`
- `completed/ALPHA-READINESS-AUDIT.md`
- `completed/AVAILABILITY-ADMIN-PLAN.md`
- `completed/AVAILABILITY-SALE-PRODUCTION-PLAN.md`
- `completed/BI-CONSUMPTION-PROFILES.md`
- `completed/BI-DATA-FOUNDATION-PLAN.md`
- `completed/BI-FORECAST-PLAN.md`
- `completed/BI-INSIGHTS-MAP.md`
- `completed/BI-PLAN.md`
- `completed/BI-QUESTION-CATALOG.md`
- `completed/BUYMAN-PROCUREMENT-PLAN.md`
- `completed/CARDAPIO-2027-SEED-PLAN.md`
- `completed/CASH-LEDGER-ARCHITECTURE.md`
- `completed/CASHMAN-PLAN.md`
- `completed/CATALOG-FEEDS-GOOGLE-META.md`
- `completed/CATALOG-IMAGES-OFF-GITHUB-PLAN.md`
- `completed/CATALOG-SYNC-EXTERNO-PLAN.md`
- `completed/CHANGE-PHONE-NUMBER-PLAN.md`
- `completed/CONCIERGE-ARQUITETURA-ALVO.md`
- `completed/CONCIERGE-MANYCHAT-CANONICAL-FLOW-2026-09-12.md`
- `completed/CONVERSATIONAL-SALES-EXECUTION-PROMPT-2026-09-11.md`
- `completed/CONVERSATIONAL-SALES-OPERATIONAL-EXCELLENCE-PLAN-2026-09-11.md`
- `completed/CROSS-CHANNEL-CATALOG-HUB-PLAN.md`
- `completed/CUSTOMER-PANEL-PLAN.md`
- `completed/D1-RETIREMENT-PLAN.md`
- `completed/ENCOMENDA-ROUTING-PLAN.md`
- `completed/ENCOMENDAS-PDV-PLAN.md`
- `completed/GESTOR-CATALOG-STOCK-AWARE.md`
- `completed/GESTOR-UX-STANDARDIZATION.md`
- `completed/GO-LIVE-ACCELERATION-PLAN-2026-09-29.md`
- `completed/GO-LIVE-RECOVERY-EXECUTION-PROGRAM-2026-09-28.md`
- `completed/GO-LIVE-SMS-WHATSAPP-STATUS.md`
- `completed/INTENT-PILOT-PLAN.md`
- `completed/LEVA-CONTADOR-ADVOGADO.md`
- `completed/MANYCHAT-CONVERSACIONAL-PLAN.md`
- `completed/MARKETING-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md`
- `completed/MARKETING-UX-PLAN.md`
- `completed/NIGHT-SHIFT-BRIEF-2026-09-30.md`
- `completed/NOTIFICATION-ROBUSTNESS-PLAN.md`
- `completed/NUXT-45-MIGRATION-PLAN.md`
- `completed/OMOTENASHI-EMPTY-STATES-AND-ERROR-ACTIONS.md`
- `completed/ORDERS-OPERATIONAL-EXCELLENCE-EXECUTION-PROMPT-2026-09-10.md`
- `completed/ORDERS-OPERATIONAL-EXCELLENCE-PLAN-2026-09-10.md`
- `completed/PDV-QUANDO-E-DIVIDIR-PLAN.md`
- `completed/POS-FASE-C-REVISION.md`
- `completed/POS-FIRST-CLASS-PLAN.md`
- `completed/POS-HARDWARE-READINESS-HANDOFF.md`
- `completed/POS-REDESIGN-PLAN.md`
- `completed/PRIVACY-CANONICAL-FENCE-MATRIX-2026-09-16.md`
- `completed/PROJECTION-UI-PLAN.md`
- `completed/QC-FORNADA.md`
- `completed/RECIPE-INVENTORY-PLAN.md`
- `completed/SECURITY-ACCOUNT-NOTIFICATIONS.md`
- `completed/SIGN-IN-AUDIT-PLAN.md`
- `completed/SOCIAL-PIM-SPECS.md`
- `completed/STOCK-UX-PLAN.md`
- `completed/STOREFRONT-GAPS-ACTION-PLAN.md`
- `completed/STOREFRONT-OPERATIONAL-EXCELLENCE-PLAN-2026-09-10.md`
- `completed/UNIT-CONVERSION-PLAN.md`
- `completed/WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN.md`
- `completed/WP-ALPHA-FIX-01-producao-e-efi.md`
- `completed/WP-ATRIBUTOS-RENAME-CHAVES-LEGADAS.md`
- `completed/WP-BASE-UNIT-LIQUIDS-KG.md`
- `completed/WP-BI-CANON-LAUDO.md`
- `completed/WP-CANONICAL-GO-LIVE-TRUTH-2026-09-28.md`
- `completed/WP-CHECKOUT-ADDRESS-LOCATION-DIVERGENCE-2026-09-28.md`
- `completed/WP-CHECKOUT-ADDRESS-MAP-CONFIRMATION-2026-09-28.md`
- `completed/WP-COMMERCIAL-GO-LIVE-CUTOVER-2026-09-28.md`
- `completed/WP-DELIVERY-SECURITY-AND-CI-CLOSURE-2026-09-28.md`
- `completed/WP-DORMANT-PR-TRIAGE-2026-09-28.md`
- `completed/WP-ENCOMENDAS-UNIFIED-INTEGRATION-2026-09-28.md`
- `completed/WP-ENRIQUECIMENTO-INSUMOS-GTIN.md`
- `completed/WP-FC-NA-SUGESTAO-DE-COMPRA.md`
- `completed/WP-FICHA-EM-GRAMAS-DE-SKU-POR-UNIDADE.md`
- `completed/WP-GAP-07-pre-prod-migration-playbook.md`
- `completed/WP-GESTOR-CANON-LAUDO.md`
- `completed/WP-GO-LIVE-RECOVERY-ROOT-AND-CRITICAL-WIP-2026-09-28.md`
- `completed/WP-IFOOD-SINGLE-TENANT-BENCHMARK-2026-09-28.md`
- `completed/WP-LINHA-COM-IDENTIDADE-NO-PDV.md`
- `completed/WP-LOCK-01-estacao-travada-nao-e-sessao-encerrada.md`
- `completed/WP-LOYALTY-RESTORE-01-devolucao-do-resgate.md`
- `completed/WP-LOYALTY-REVOKE-01-estorno-no-cancelamento.md`
- `completed/WP-MARKETING-OFFERS-COUPONS-RESCUE-2026-09-28.md`
- `completed/WP-MAXMIND-CHAVE-DO-DONO.md`
- `completed/WP-P2E-WAITLIST-FERMATA.md`
- `completed/WP-PAGAMENTO-LINK-E-TEF.md`
- `completed/WP-PDV-COLUNA-COMANDA.md`
- `completed/WP-POS-ENCOMENDAS-REDESENHO-BRIEF.md`
- `completed/WP-POS-ENCOMENDAS-UX-2026-09-29.md`
- `completed/WP-POS-STATION-DEVICE-CUSTODY-2026-09-29.md`
- `completed/WP-PWA-CONFORMIDADE.md`
- `completed/WP-PWA-EXECUCAO-PROMPT-F0.md`
- `completed/WP-PWA-EXECUCAO.md`
- `completed/WP-REPOSITORY-WORKTREE-BRANCH-HYGIENE-2026-09-28.md`
- `completed/WP-STOREFRONT-FOCUS-AND-IFOOD-LEARNINGS-INTEGRATION-2026-09-28.md`
- `completed/WP-SUPERFICIES-MESMO-TRILHO.md`
- `completed/WP-UNIDADE-BASE-GRAMA.md`
- `completed/WP-UX-13-AUDITORIA-EXAUSTIVA-DOS-APPS-NUXT.md`
- `completed/admin-unfold-reconstruction-plan.md`
- `completed/codex/CODEX-GESTOR-PEDIDOS-2026-09-10.md`
- `completed/codex/CODEX-MARKETING-2026-09-10.md`
- `completed/codex/CODEX-PDV-2026-09-10.md`
- `completed/codex/CODEX-PRODUCAO-2026-09-10.md`
- `completed/concierge-teste-deeliv.md`

## Concluídos Recentemente (2026-07-11)

Arquivados em [`completed/`](completed/) nesta reorganização:

| Plano | Evidência |
|-------|-----------|
| `completed/BACKSTAGE-EXCELLENCE-HARDENING-PLAN.md` | 5 superfícies de operador + OperatorRail + Central; deployado em staging (PR #36). |
| `completed/STOREFRONT-EXCELLENCE-HARDENING-PLAN.md` | WP-S0..S6 concluídos; lint 0, suíte verde. |
| `completed/PRODUCTION-EXCELLENCE-PLAN.md` | WP-PE0..6 entregues + staging; **resta só QA físico** (som/térmica), vivo no ROADMAP. |
| `completed/GO-LIVE-ALPHA-AUDIT.md` | Lotes 1–6 corrigidos com teste por bug (status ✅ no próprio doc, 2026-07-02). |
| `completed/OPERATOR-PIN-SELFSERVICE-PLAN.md` | PIN autoatendimento + reset por gerente (PR #32). |
| `completed/COPY-CONSOLIDATION-PLAN.md` + `completed/COPY-BACKLOG-UNBUILT.md` | Burndown omotenashi fechado, backlog de copy zerado (PRs #49–#53). |
| `completed/STOCK-SUBSTITUTE-1CLICK-PLAN.md` | Substituto acionável em 1 toque entregue; duplicata em `plans/` removida. |
| `completed/VALIDITY-SHELFLIFE-REVIEW.md` | Retrato de 2026-06 arquivado: P0 ligado (WP-B5); o caminho de validade virou o modelo de lote (ADR-017, C1–C6). |
| `completed/CORE-SOVEREIGNTY-PLAN.md` + `MISSION` + `REVIEW` | Missão F1–F6 e WP7/WP10/WP11/WP12 concluída; trio arquivado junto após os gates finais. |

Histórico anterior (auditoria 2026-06-28, 28 planos) e demais planos concluídos: ver [`completed/`](completed/).
