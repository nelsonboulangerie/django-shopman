# ROADMAP — Django Shopman

> Atualizado em 2026-08-13 (faxina pré-alpha; antes: 2026-07-11, pós PRs #53–#69). Este documento é o
> mapa executivo vivo. Estado factual fica em [`status.md`](status.md); planos
> detalhados ficam em [`plans/README.md`](plans/README.md).

## Estado Atual (factual, 2026-08-13)

- **Headless completo**: Django serve API JSON + projections; superfícies são 7 apps
  Nuxt 4 SSR + layer `operator-kit` (ver [`status.md`](status.md)).
- **Alpha destravado** (2026-08): checkout, cascata completa, SSE e virada do dia
  exercitados de ponta a ponta no staging; PDV endurecido pelo teste de estresse;
  gaveta e crachá construídos (falta QA físico). Ver
  [`reports/alpha-readiness-2026-08-12.md`](reports/alpha-readiness-2026-08-12.md).
- **11 core apps** pip-instaláveis, incluindo Buyman (compras, Fase 1) e Fiscalman
  (NFC-e, S0–S4).
- **Suite ~6.500 testes** (~2.200 cores + ~4.250 framework + tools; medido 2026-08-13), CI com Runtime Gate
  (PostgreSQL + Redis), Surfaces Gate (typecheck Nuxt) e gates de docs/copy/admin.
- **Auth WhatsApp-first por access link** (`NB-XxXx`) mergeada; reverse-OTP aposentado.
- **iFood direto** (polling + sync de catálogo) em staging; **Machine** (logística
  externa/courier) construída aguardando credenciais.
- **Copy omotenashi**: backlog zerado; registro `OmotenashiCopy` é fonte única.
- **Hardening pré-alpha** de 2026-07-11: 16 PRs (#53–#69) fechando achados da
  auditoria [`reports/analise_pre_alpha_2026-07-11.md`](reports/analise_pre_alpha_2026-07-11.md)
  — oversell, dialeto de erro, directives, tz, POS anti-fraude, suíte hermética,
  rotas/chaves em inglês, baseline selado.
- **Staging** DigitalOcean App Platform ativo (deploy manual `create-deployment`).

## Próximos Passos

| Prioridade | Frente | Entrega esperada | Plano / dono |
|------------|--------|------------------|--------------|
| P1 | Go-live Lote C | 2FA/IP allowlist do Admin, corte v1, QA final e data. | [`plans/GO-LIVE-READINESS-PLAN.md`](plans/GO-LIVE-READINESS-PLAN.md) — bloqueado no dono |
| P1 | Credenciais go-live | WhatsApp Meta, Focus NFe produção, iFood homologação, Machine creds. | [`plans/GO-LIVE-CREDENTIALS-MATRIX.md`](plans/GO-LIVE-CREDENTIALS-MATRIX.md) — lado do dono |
| P1 | Access link F3 | Fluxo ManyChat do access link + URLs de staging. | [`plans/ACCESS-LINK-UNIFICATION-PLAN.md`](plans/ACCESS-LINK-UNIFICATION-PLAN.md) — lado do dono |
| P2 | Fiscalman S5 | NF-e mod. 55 / itens resale; e2e homolog Focus; contador valida NCM/CSC/IBPT. | [`plans/FISCALMAN-PLAN.md`](plans/FISCALMAN-PLAN.md) |
| P2 | QA físico | Som/térmica da produção; QA visual em dispositivo real (staging). | [`plans/completed/PRODUCTION-EXCELLENCE-PLAN.md`](plans/completed/PRODUCTION-EXCELLENCE-PLAN.md) (resta só QA físico) |
| P2 | Impressão DANFE NFC-e no PDV | Obrigação legal para venda presencial — incontornável antes de operação fiscal plena. | pós-alpha, ver [`plans/POS-FASE-C-REVISION.md`](plans/POS-FASE-C-REVISION.md) |
| P3 | ManyChat conversacional | Pedido inbound por chat (ManyChat → session → confirmação). | [`plans/MANYCHAT-CONVERSACIONAL-PLAN.md`](plans/MANYCHAT-CONVERSACIONAL-PLAN.md) |
| P3 | Buyman Fases 2–4 | PurchaseOrder, recebimento, reposição. | [`plans/BUYMAN-PROCUREMENT-PLAN.md`](plans/BUYMAN-PROCUREMENT-PLAN.md) — pós-go-live |
| P3 | Tempo real de forno (BI da fornada) | Definição benzida (2026-08-13): start = armar o timer (enfornou), stop = Concluir declarado no timer (retirou); fim de timer sem resposta e Confirmar do QC NÃO medem tempo. Exige promover o timer (hoje localStorage) a fato do servidor. O QC segue dono do fato COMERCIAL (partição/lote). | frente separada, sem plano ainda — sem tabela de agregação (doutrina anti-BI) |
| P3 | Pre-prod real | Executar playbook às vésperas do primeiro deploy com dado real. | [`plans/WP-GAP-07-pre-prod-migration-playbook.md`](plans/WP-GAP-07-pre-prod-migration-playbook.md) |

## Dívida Técnica Viva

| Dívida | Impacto | Próxima ação |
|--------|---------|--------------|
| **D-1 é interino, superado por lote/validade** (ADR-017 + QC-FORNADA) | ✅ **Fundação construída** (ADR-017 §1–8): partição de fornada, catálogos de grau/defeito, N lotes com percentual congelado, relatório de qualidade. O D-1 velho segue operante em paralelo (D1Rule 50%, posição "ontem", `cleanup_d1`, bucket do POS, badge F3). Cliente protegido (`excluded_positions=["ontem"]`). | **Consumidores** que substituem o D-1: preço por lote na venda (`percent_for_lot`), write-off de lote com desconto no fechamento, gate `sells_nonconforming`/validade por canal, quiosque de QC (ADR-017 §9). Só então remover D1Rule/"ontem"/`cleanup_d1`/F3. Até lá, **não construir nada novo sobre D-1**. |
| Gateway sandbox e snapshot real pendentes | Smoke local existe; falta provar divergência contra provedores reais. | Executar `make smoke-gateways-sandbox` com credenciais/staging reais. |
| PostgreSQL pequeno exige disciplina de conexões | Sem pool, `CONN_MAX_AGE=60` saturou o Postgres da DO. | Staging usa pool em modo transaction; validar latência antes de repetir em produção. |
| QA visual/manual ainda não cobre mundo real | Gates headless não provam toque real, teclado virtual, rede degradada. | Rodar dispositivo físico/staging antes de release real. |
| ManyChat webhook ainda pulado | Fluxo ManyChat → session → confirmação não reimplementado. | Retomar junto com canais externos. |
| Playwright E2E opcional | A suite existe, mas só roda quando Playwright está instalado. | Decidir se vira gate antes de piloto público. |
| Migração futura para CSP nativo do Django 6 | `django-csp` funciona, mas Django 6 tem CSP nativo a avaliar. | Avaliar isoladamente, sem misturar com features. |
| Media persistente na App Platform | Static resolvido por WhiteNoise; uploads não devem depender de filesystem efêmero. | Decidir Spaces/S3-compatible antes de piloto público com uploads reais. |

## Visão de produto (registro de intenção — dono: Pablo)

> Carimbo 2026-07-11: itens abaixo são direção, não compromisso datado.

- **Hub cross-channel**: Gestor como hub único de canais (espírito iFood) —
  [`plans/CROSS-CHANNEL-CATALOG-HUB-PLAN.md`](plans/CROSS-CHANNEL-CATALOG-HUB-PLAN.md).
- **Feeds de catálogo Google/Meta/WhatsApp** —
  [`plans/CATALOG-FEEDS-GOOGLE-META.md`](plans/CATALOG-FEEDS-GOOGLE-META.md) e
  [`plans/CATALOG-SYNC-EXTERNO-PLAN.md`](plans/CATALOG-SYNC-EXTERNO-PLAN.md).
- **POS**: tela do cliente (estilo Odoo), split por item, offline-first (WP-9+).
- **Storefront**: scroll inteligente, auto-fill de teleporte, avaliação do cliente.
- **Notação visual de pâtonnage** para etiquetas (nunca perder —
  [`plans/PRODUCTION-FORECAST-BOARD-PLAN.md`](plans/PRODUCTION-FORECAST-BOARD-PLAN.md) é vizinho).
- **Mudar número de telefone** ([`plans/CHANGE-PHONE-NUMBER-PLAN.md`](plans/CHANGE-PHONE-NUMBER-PLAN.md))
  — telefone é identidade; só se valer a pena.
- **SEO como capítulo próprio** — [`plans/SEO-PLAN.md`](plans/SEO-PLAN.md).

## Critério Para Produção Real

Antes de abrir tráfego real, o mínimo honesto é:

1. `Runtime Gate` verde no commit de release.
2. `make release-readiness-strict` verde com evidência manual e pre-prod reais.
3. `check --deploy` verde com secrets e hosts reais do ambiente.
4. Gateway sandbox validado para pagamento, refund, webhook duplicado e evento
   fora de ordem.
5. Reconciliação diária interna provada e snapshot de gateway validado em staging.
6. QA manual Omotenashi registrado para cliente, operador, cozinha e gerente.
7. Runbook de incidente para gateway fora, webhook atrasado, estoque divergente,
   pedido pago sem confirmação e rollback.
