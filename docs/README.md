# Documentação — Django Shopman

> Índice geral de toda a documentação do projeto.

---

## Hierarquia de Documentos

| Documento | Papel |
|-----------|-------|
| [`README.md`](../README.md) | Visão geral + entrada rápida (quickstart, caminhos de uso, ecossistema) |
| [`docs/status.md`](status.md) | Estado factual — o que funciona, versões, contagem de testes real |
| [`docs/architecture.md`](architecture.md) | Verdade arquitetural — camadas, Protocol/Adapter, dependências |
| [`docs/reference/runtime-dependencies.md`](reference/runtime-dependencies.md) | Runtime canônico — PostgreSQL, Redis, fallback local e Django 6 |
| [`docs/guides/deploy.md`](guides/deploy.md) | Deploy sem Docker manual — imagem app, release step e wrappers `make deploy-*` |
| [`docs/runbooks/README.md`](runbooks/README.md) | Incidentes operacionais P1/P2 e comandos `make diagnose-*` |
| [`docs/ROADMAP.md`](ROADMAP.md) | Roadmap ativo de correções e próximos passos |
| [`docs/decisions/README.md`](decisions/README.md) | Índice canônico e completo das ADRs |
| [`docs/plans/README.md`](plans/README.md) | Classificação semântica dos planos vivos e backlog explícito |
| [`docs/plans/INDEX.md`](plans/INDEX.md) | Inventário mecânico completo da árvore viva de planos |
| [`docs/plans/OPERATION-RUNBOOKS-PLAN.md`](plans/OPERATION-RUNBOOKS-PLAN.md) | Runbooks, comandos de diagnóstico, healthcheck profundo e reconciliação diária |
| [`docs/guides/production-upgrades.md`](guides/production-upgrades.md) | Migração e upgrade em produção (sucede o playbook WP-GAP-07, arquivado em `plans/completed/`) |
| [`docs/plans/completed/`](plans/completed/) | Planos concluídos; histórico preservado, não fonte de estado atual |
| [`docs/reports/`](reports/) | Relatórios e evidências históricas |
| [`docs/governance/`](governance/) | Baselines versionadas dos gates documentais |

---

## Início Rápido

| Documento | Descrição |
|-----------|-----------|
| [README.md](../README.md) | Visão geral do projeto, quickstart, estrutura |
| [Quickstart](getting-started/quickstart.md) | Pré-requisitos, instalação, seed, primeiro acesso |
| [Dia na Padaria](getting-started/dia-na-padaria.md) | Tutorial narrativo completo — um dia de operação |

---

## Arquitetura

| Documento | Descrição |
|-----------|-----------|
| [Arquitetura](architecture.md) | Diagrama das 7 camadas + orquestrador, Protocol/Adapter, dependências |

### Decisões Arquiteturais (ADRs)

O [índice canônico de ADRs](decisions/README.md) é a única lista de decisões,
com numeração, título, status, dono, data e tema. Ele é validado por
`make adr-governance`; este índice geral não mantém uma cópia parcial. O contrato
transversal das superfícies nasce na
[ADR-012](decisions/adr-012-headless-surface-contract.md) e é detalhado na
[referência headless](reference/headless-surface-contract.md).

---

## Guias

Guias de domínio seguem a estrutura: Conceitos → Modelos → Serviços → Protocols → Exemplos.

| Guia | Escopo | Descrição |
|------|--------|-----------|
| [Offerman](guides/offerman.md) | `shopman.offerman` | Catálogo, preços, listings, bundles, coleções |
| [Stockman](guides/stockman.md) | `shopman.stockman` | Estoque, holds, moves, posições, planejamento |
| [Craftsman](guides/craftsman.md) | `shopman.craftsman` | Receitas, work orders, BOM, coeficiente francês |
| [Orderman](guides/orderman.md) | `shopman.orderman` | Pedidos, sessões, canais, directives, fulfillment |
| [Guestman](guides/guestman.md) | `shopman.guestman` | Clientes, contatos, grupos, loyalty, consent, RFM |
| [Doorman](guides/doorman.md) | `shopman.doorman` | Auth OTP, device trust, bridge tokens, magic links |
| [Payments](guides/payments.md) | `shopman.payman` | Pagamentos, PIX, Stripe, intents, lifecycle |
| [Caixa](guides/cashman.md) | `shopman.cashman` | Terminal, turno (custódia) e livro-caixa imutável; fechamento cego como lançamento |
| [Lifecycle](guides/lifecycle.md) | `shopman/shop` | Orquestrador: Lifecycle, Services, Adapters, Rules |
| [Fechamento do dia](guides/day-closing.md) | `shopman` | Sobras, não vendidos, D-1 em `ontem`, às cegas vs vendas |
| [WhatsApp Access Link](guides/whatsapp-access-link.md) | auth | Login WhatsApp-first por access link (`NB-XxXx`) |
| [Concierge de WhatsApp](guides/whatsapp-concierge.md) | `shopman/storefront/concierge` | Pedido por conversa no WhatsApp: env, flow no ManyChat, transcrições no Admin, kill switch |
| [Storefront backend surface](guides/storefront_backend_surface.md) | `shopman/storefront` | API headless + projections da loja |
| [Cidade aproximada do dispositivo](guides/geolite2-city.md) | `shopman/shop/services/ip_location.py` | Base GeoLite2 local na imagem, limiar de confiança de 50 km, chave de build e a atualização que NÃO é automática |
| [Backstage realtime](guides/backstage-realtime.md) | `shopman/backstage` | SSE, canais nomeados e fallback de polling |
| [Backstage accessibility](guides/backstage-accessibility.md) | superfícies operador | Acessibilidade das telas de operador |
| [UX/UI canônica de operador](guides/operator-surface-ux.md) | superfícies Nuxt de operador | Como um app novo nasce visualmente canônico: operator-kit, Nuxt UI/Reka, Omotenashi e validação por dispositivo |
| [Operations](guides/operations.md) | operação | Rotinas operacionais do dia a dia |
| [Backup e restore](guides/backup-and-restore.md) | dados | As três camadas: Postgres gerenciado, cofre de dados curados (`export_backup`/`import_backup`), ciclo com Google Sheets |
| [Operator security hardening](guides/operator-security-hardening.md) | operação | PIN, lock de operador, sessões staff |
| [RBAC personas](guides/rbac-personas.md) | operação | Grupos/permissões por persona |
| [Demo personas](guides/demo-personas.md) | demo | Personas do seed Nelson |
| [Omotenashi QA](guides/omotenashi-qa.md) | QA | Matriz de QA omotenashi (mobile/tablet/desktop) |
| [Catalog exports](guides/catalog_exports.md) | catálogo | Exportação de catálogo (feeds/sync externo) |
| [Piloto automático de staging](guides/staging-autopilot.md) | staging | Pedido anda sozinho até "concluído", loja 24/7, sem operador |
| [Deploy](guides/deploy.md) | infra | Imagem app, compose profiles e `make deploy-*` |
| [Deploy DigitalOcean](guides/deploy-digitalocean.md) | infra | App Platform, staging e gotchas de spec/secrets |
| [Production upgrades](guides/production-upgrades.md) | infra | Upgrades pós-go-live (expand-contract, ADR-015) |

---

## Referência Técnica

Documentação de consulta rápida gerada a partir do código.

| Documento | Conteúdo |
|-----------|----------|
| [Protocols e Adapters](reference/protocols.md) | Mapa de todos os protocols, dataclasses e adapters disponíveis |
| [Runtime dependencies](reference/runtime-dependencies.md) | Contrato PostgreSQL/Redis/SQLite, SSE, deploy e Django 6 |
| [Deploy](guides/deploy.md) | Docker/compose encapsulado por Makefile, release checks e app ASGI |
| [Runbooks operacionais](runbooks/README.md) | Webhook, pagamento, Redis, PostgreSQL, worker, estoque e estado da loja |
| [Configurações](reference/settings.md) | Settings por app (STOCKMAN, CRAFTSMAN, DOORMAN, SHOPMAN_*, etc.) com defaults |
| [Management Commands](reference/commands.md) | Comandos disponíveis com flags, exemplos e cron recomendado |
| [Exceções e Erros](reference/errors.md) | Hierarquia de exceções, códigos de erro e quando ocorrem |
| [Cenários de pedido](reference/cenarios-de-pedido.md) | Balcão, encomenda imediata e agendada no PDV, loja/WhatsApp e iFood, com retirada e entrega: caminho feliz, exceções, matriz OK/LACUNA/ATRITO, status e prioridades |
| [Comprovante de Entrega](reference/comprovante-de-entrega.md) | Avisos ao cliente: aceite × entrega, o que cada canal comprova, quais avisos são críticos e por quê |
| [Sinais (Signals)](reference/signals.md) | Sinais emitidos e consumidos por cada app, payload e fluxos |
| [Glossário](reference/glossary.md) | Termos de domínio: Quant, Hold, Move, Session, Order, Channel, etc. |
| [Mapa semântico dos pacotes](reference/semantic-map.md) | Pergunta canônica, verbos, estados, sinais e eventos de cada diretório físico de `packages/` |
| [Data Schemas](reference/data-schemas.md) | Inventário de chaves em Session.data, Order.data, Directive.payload |
| [Headless Surface Contract](reference/headless-surface-contract.md) | Contrato canônico para Nuxt, Ionic, ManyChat, POS e futuras superfícies: Projection com Actions |
| [Contrato da superfície Marketing](reference/marketing-surface-contract.md) | Ownership, rotas verificadas, plataformas, capabilities, flags, probes e estado de rollout |
| [ManyChat Conversation Projection](reference/manychat-conversation-projection.md) | Contrato conversacional derivado de tracking, payment e channel policy canônicos |
| [Remote Mutation Contract](reference/remote-mutation-contract.md) | Mutations remotas idempotentes sobre services canônicos |
| [Vocabulários fechados das superfícies](reference/suite-vocabulary.md) | Objeto, atos e grandezas do PDV, da Produção/KDS e da loja; os gestos com um nome só nos nove apps; o que já foi decidido e não se reabre |
| [Omotenashi Copy](reference/omotenashi-copy.md) | Critérios da linguagem de UI: a definição, o teste de uma frase, os oito defeitos nomeados, as travas e a ordem da varredura |
| [Filtro de Design de Superfícies](reference/design-surface-filter.md) | Checklist transversal para UI: tipografia, ícones, espaçamento, contraste, foco, responsividade e estados |
| [Baselines visuais e tema do operator-kit](reference/operator-visual-baselines.md) | Como uma mudança de tema do kit regenera as baselines das consumidoras, com aceite do dono e sem baseline cega |

---

## Mapa de Apps

```
packages/                            shopman/
├── refs         (refs tipadas)      ├── shop/              (orquestrador)
├── utils        (utilitários)       │   ├── handlers/      (directive handlers)
├── watchman     (auditoria)         │   ├── adapters/      (integrações swappable)
├── offerman     (catálogo)          │   ├── config.py      (ChannelConfig)
├── stockman     (estoque)           │   ├── services/      (orquestração)
├── craftsman    (produção)          │   ├── lifecycle.py   (dispatcher config-driven)
├── orderman     (pedidos)           │   ├── rules/         (RuleConfig engine)
├── guestman     (clientes)          │   └── views/         (health/readiness)
├── doorman      (autenticação)      ├── storefront/       (API headless do cliente)
├── payman       (pagamentos)        └── backstage/        (API headless operador + Admin)
├── buyman       (compras)
├── fiscalman    (fiscal NFC-e)      surfaces/  11 apps Nuxt registrados + layer + router
└── cashman      (caixa e livro)     config/    settings, urls e descritores de instância
```

---

## Roadmap e Planos

| Documento | Descrição |
|-----------|-----------|
| [ROADMAP.md](ROADMAP.md) | Roadmap executivo vivo e dívidas técnicas atuais |
| [plans/README.md](plans/README.md) | Índice dos planos ativos e backlog planejado |
| [plans/completed/REMOTE-MULTISURFACE-PLAN.md](plans/completed/REMOTE-MULTISURFACE-PLAN.md) | WPs de pedido remoto multi-superfície, WhatsApp-first/mobile-first, com Django/Penguin apenas como referência madura |
| [plans/completed/](plans/completed/) | Planos de execução concluídos e evidências históricas arquivadas |

---

## Mapa de Nomes (suite antiga → repo atual)

Para quem conhece a suite antiga (`django-shopman-suite`):

| Nome Antigo | Nome Atual | App Label |
|-------------|-----------|-----------|
| commons | shopman.utils | `utils` |
| offerman | shopman.offerman | `offerman` |
| stockman | shopman.stockman | `stockman` |
| craftsman | shopman.craftsman | `craftsman` |
| orderman | shopman.orderman | `orderman` |
| guestman | shopman.guestman | `guestman` |
| doorman | shopman.doorman | `doorman` |
