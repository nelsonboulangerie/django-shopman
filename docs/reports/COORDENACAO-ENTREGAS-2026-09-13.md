# Coordenação de entregas — 13/09/2026

**Atualização posterior:** [correções SQL e validação conjunta do lote](COORDENACAO-AVANCO-2026-09-13.md). O registro abaixo preserva a fotografia inicial; o avanço posterior corrige pendências aqui ainda descritas como abertas.

**Decisão de publicação:** [revisão adicional do #631 e tentativa de integração](DECISAO-DEPLOY-2026-09-13.md), recusada pela política de aprovação antes da execução.

Apuração encerrada às 14:52 BRT / 17:52 UTC. Esta é uma fotografia verificável, não uma declaração de go-live nem de segurança absoluta.

## Resultado e limite da execução

Foram consultadas dez sessões principais, branches locais, GitHub via conector e o App Platform vivo. As cinco tentativas de retomar sessões foram recusadas: **zero mensagens entregues**. O ambiente exige aprovação para essa ferramenta, mas usa política `never`. A autorização de Pablo para coordenação e atualização segura está registrada; a ferramenta não a conseguiu executar. Não houve merge, deploy, ativação comercial, envio a clientes nem alteração de segredos.

A correção das falhas do PR #613 foi preparada e testada em cópia isolada. Commit local **`e2e3e00b7`**, base **`03bf0eb20ca30a5f19824002f6720f9a20da3557`**, branch `codex/coordination-maps-ci-20260913`, repositório `/private/tmp/shopman-coordination-maps-20260913`. Ela ainda não foi incorporada ao PR nem publicada.

- [Patch aplicável ao head do #613](../../output/coordination-20260913/0001-fix-maps-ci-contracts.patch).
- [Evidências sanitizadas de PRs, heads e workflows](../../output/coordination-20260913/evidence.json).
- [Manifesto anterior das 17 entregas do laudo](/Users/pablovalentini/.codex/visualizations/2026/09/13/01a09879-e552-76b0-9941-172559376d37/go-live-638/entrega-pr-638.md).

## Ambiente online observado agora

| Item | Evidência viva |
|---|---|
| Aplicação | `shopman-nelson`, `40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f` |
| Deployment ativo | `d3bd232b-6eb6-4676-a87f-f002800282da`, ACTIVE, 47/47 etapas |
| Atualização do deployment | 13/09/2026 02:05:26 UTC |
| Deployment em andamento | Nenhum no momento da consulta |
| Ambiente | `SHOPMAN_ENVIRONMENT=staging` |
| Pix | `shopman.shop.adapters.payment_mock` |
| Cartão | Adapter Stripe configurado; modo/credenciais reais não auditados nesta execução |
| Mocks | `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true` |
| OTP de teste | `SHOPMAN_EXPOSE_DEBUG_OTP=true` |
| Autopiloto de staging | `false` |
| Maps | Chave legada presente; chaves separadas de browser/servidor não aparecem no spec consultado. Valores secretos não foram exibidos |
| Autodeploy | `deploy_on_push.enabled=true` nos componentes de imagem consultados |

Sondas GET retornaram HTTP 200 em API `/health/`, API `/ready/`, home do menu, PDV, Gestor e Marketing `/health/ready`. Isso comprova disponibilidade básica, não jornadas completas, autenticação segura, identidade das imagens com o último `main` ou aptidão comercial.

O workflow versionado publica imagens quando `main` muda. Portanto, merge de código e deploy não podem ser tratados como etapas independentes sem verificar o comportamento dos componentes afetados. O backend e as superfícies podem ter imagens de commits diferentes por build seletivo; uma única referência de `main` não prova atualização integral.

## Inventário atual do GitHub

**13 PRs abertos**, verificados pelo conector. O CLI `gh` retornou HTTP 401; a leitura pelo conector funciona. Não é necessário reparar o CLI para continuar leituras.

| PR | Estado comprovado | O que falta |
|---|---|---|
| [#613 — Maps](https://github.com/nelsonboulangerie/django-shopman/pull/613) | Sem conflito; Runtime Gate falhou; demais workflows consultados verdes | Incorporar patch desta execução, novo CI, revisão e configurar/restringir credenciais antes da virada produtiva |
| [#614 — contrato público/privacidade/OAuth](https://github.com/nelsonboulangerie/django-shopman/pull/614) | Draft; três workflows consultados verdes | L1 inventário/contratos; L3 e L7 ainda têm código a executar; smoke legal após publicação; aprovação jurídica externa para alegação ampla de conformidade |
| [#631 — dependências L8](https://github.com/nelsonboulangerie/django-shopman/pull/631) | Sem conflito; três workflows consultados verdes | Revisão, integração coordenada e recontagem de alertas no main junto do #614 |
| [#634 — identidade de entrega/TikTok](https://github.com/nelsonboulangerie/django-shopman/pull/634) | Sem conflito; três workflows consultados verdes | Revisão da migração e release com TikTok ainda desligado; OAuth/auditoria/piloto são gates separados |
| [#638 — laudo](https://github.com/nelsonboulangerie/django-shopman/pull/638) | Documento; sem conflito; workflows verdes | Registrar apreciação/fechamento por achado. Integrar o documento não entrega suas correções |
| #616, #600, #428, #427, #235, #234, #233, #232 | Oito PRs de dependências com `mergeable=false` | Reconciliar versões e sobreposições, validar compatibilidade e testar. Não mesclar todos indiscriminadamente |

Verde aqui significa os workflows retornados para o head consultado. Não substitui revisão do diff, regras de proteção, revalidação da base nem homologação externa.

As **17 branches `codex/go-live-*` existem remotamente**, confirmadas em consulta. A busca de PRs abertos não contém PRs para elas. O relatório de implementação registra 3.116 testes principais aprovados na montagem local e duas falhas SQL preexistentes. Essa evidência não equivale a CI remoto do conjunto integrado.

## Bloqueios de código — trabalho nosso

1. **Entrega do laudo:** abrir os 17 PRs já descritos, revisar o conjunto e passar CI. Prioridade: identidade do checkout; captura antes da conclusão/emissão; recuperação da liquidação; concorrência de comandas e estação/gaveta. As correções já estão em branches, portanto não recomeçar a implementação.
2. **Duas falhas SQL no fluxo de unificação de clientes:** o relatório registra PostgreSQL recusando `FOR UPDATE` com `DISTINCT`. O código ainda contém essa combinação em `packages/guestman/shopman/guestman/contrib/merge/service.py:671`. Resolver preservando locks e provar migração/undo no PostgreSQL. Não foram corrigidas nem reexecutadas nesta auditoria.
3. **#613:** três defeitos de integração confirmados nos logs e corrigidos localmente, detalhados abaixo.
4. **#614 L3:** aplicar a decisão já aprovada de declaração de maioridade para marketing direto, inclusive idade desconhecida. Não pedir nova aprovação da mesma regra.
5. **#614 L7:** implementar/testar as contrações de retenção já aprovadas. O primeiro dry-run existe; descarte real e jobs produtivos continuam com gate próprio.
6. **Catálogo iFood no Gestor:** auditoria anterior confirma publicação desligada, perda de pausa durante envio e falsa indicação de sincronização; faltam categorias e cobertura de imagens/complementos. Testes do adapter de pedidos não encerram essas pendências de catálogo.
7. **Dependências:** resolver os oito PRs em conflito e verificar se atualizações antigas já foram absorvidas por outras branches. Atualização de versão não é, isoladamente, requisito para publicar toda correção funcional.

### Correção local do #613

Logs consultados: [Runtime Gate](https://github.com/nelsonboulangerie/django-shopman/actions/runs/34754316862), jobs `103716004857` e `103716004814`.

- `test_check_ids`: `SHOPMAN_E023` não estava documentado no cabeçalho do módulo. Registro adicionado.
- `test_import_boundaries`: `storefront/presentation/home.py` importava `shop.services.google_maps_credentials`. O helper de configuração, sem efeitos de escrita, foi movido para `shop.google_maps_credentials`; os consumidores e testes foram atualizados. Não foi adicionada exceção ao teste arquitetural.
- `Deploy checks`: a nova guarda E023 rejeitava o próprio fixture de CI por ausência de chaves separadas. O workflow agora declara duas chaves sintéticas distintas e chave legada vazia. A guarda de produção permanece exigente.

Validação: **27 testes aprovados** (credenciais, catálogo de IDs e fronteiras), Ruff e `git diff --check` aprovados; o fixture extraído do YAML foi aceito pela própria guarda E023. Nenhuma chamada ao Google. Uma primeira execução detectou imports editáveis apontando ao checkout compartilhado; a execução válida usou `PYTHONPATH` explícito para todos os pacotes da cópia isolada. CI integral remoto ainda pendente.

## Decisões/permissões de Pablo — sem repetir as já concedidas

O histórico recente manda manter a seção C adiada. A solicitação atual de atualização segura não foi interpretada como escolha automática de suas alternativas.

| Decisão | Por que ainda é humana | Consequência enquanto adiada |
|---|---|---|
| Proteção do Admin: 2FA ou acesso por IP autorizado | Define acesso e recuperação dos operadores | O rate limit pode ser entregue separadamente; aprovação de segurança do acesso produtivo permanece aberta |
| Como oferecer o salvamento de CPF novo da nota | Define consentimento/identidade e experiência do PDV | Manter comportamento atual, sem política nova embutida no conserto fiscal |
| Quando sair de staging e assumir configuração produtiva | Define operação comercial real, providers e janela de virada | Atualizar tecnicamente preservando o modo de testes; não declarar operação comercial pronta |
| Primeiro descarte de dados / jobs de retenção em produção | Exige revisar efeito concreto do dry-run | Implementação e testes podem avançar; execução destrutiva continua suspensa |
| Aceite visual dos novos impressos | Histórico contém design ainda não aprovado e depois “deixa assim por enquanto” | Preservar arte e prévias; não presumir aprovação de publicação |

Maioridade para marketing, matriz R01–R15 e várias autorizações técnicas de deploy **já foram dadas**. Retenção definitiva não deve reaparecer como se nenhuma decisão existisse. Teste TalkBack, piloto humano e drills precisam de participação/evidência operacional, não de um “pode continuar” genérico.

## Terceiros e configuração operacional

- **iFood:** chamado **33298264** sobre 403 intermitente constava “Em análise” na última evidência da sessão. O portal não foi reinspecionado nesta execução. A resposta do fornecedor é externa; os ensaios completos de Order/Events ainda são trabalho nosso. Catalog tem homologação própria. Não submeter com base apenas na elegibilidade do app.
- **Google Maps:** código de separação não restringe nem rotaciona chaves no Google Cloud. Falta executar/provar configuração autorizada. Isso é trabalho operacional dependente de acesso à conta, não prova de que o Google esteja impedindo avanço.
- **Google OAuth / privacidade:** L1 exige completar fatos sobre contratos, DPAs, países e mecanismos; revisão jurídica externa continua indicada pelo PR. Parte é coleta nossa, parte depende dos fornecedores/responsáveis.
- **ManyChat/Meta:** provar identidade estável da mensagem, janela, replay e handoff no flow real. Ausência de ID estável mantém mutações comerciais contidas; não inventar capacidade do provedor. Reusar a implementação e o plano canônico existentes.
- **TikTok:** revisão/auditoria de conta, OAuth e piloto são externos/operacionais. Não são pré-requisito para publicar correções centrais mantendo esse canal desligado.
- **Fiscal e alertas:** verificar validade/aceitação do certificado real, destinatário de plantão e entrega de alerta. Não foi comprovado certificado vencido nem efetividade de alerta externo nesta execução.

## Fila de execução e donos propostos

Esta fila está preparada, **não despachada**: a ferramenta recusou as retomadas. Ao restaurar capacidade de coordenação, centralizar merge/deploy em um único responsável e deixar as demais frentes prepararem código/CI em isolamento.

| Ordem | Frente | Entrega | Dependência |
|---|---|---|---|
| 1 | Laudo / integrador | Incorporar patch #613 e corrigir SQL do merge de clientes | Acesso de escrita e PostgreSQL de teste isolado |
| 2 | Laudo / checkout | `go-live-checkout-fix` → `go-live-stock-pause` | CI e revisão por head |
| 2 | Laudo / PDV | `pos-payment-fiscal` → `pos-settlement-recovery` → `pos-rounding` → `tab-concurrency` | Respeitar cadeia de bases; gaveta em revisão separada |
| 3 | Operação | Catálogo/auditoria, telefone, Admin rate limit, retentativas, notificações, alertas, workers, smoke | Revisar sobreposições com iFood e Marketing |
| 3 | Operação / Maps | Gates de produção → certificado; #613 | Preservar os dois registros E022/E023 ao resolver conflito em checks.py |
| 4 | Marketing | #631 e fatia tecnicamente completa de #614; #634 com canal desligado | Não confundir CI verde de draft com trabalho funcional terminado |
| 4 | iFood / Gestor | Corrigir catálogo e preparar ensaios completos em isolamento | Coordenar `catalog.py` com auditoria B7; fornecedor acompanha 403 |
| 5 | Integrador | Revalidar base, grafo de migrations, backup e digests; publicar uma onda por vez | Gates verdes, rollback aplicável, nenhum deploy concorrente |
| 6 | Integrador + operação | Conferir versão por componente, migrations, readiness e jornadas de checkout/PDV/Gestor | Um componente 200 não prova toda a release |
| 7 | Pablo + responsáveis | Seção C, testes humanos e virada comercial | Só após pacote técnico verificável e gates externos resolvidos |

As entregas anteriores de **PDV - Execução do plano de excelência**, **Gestor - Execução do plano de excelência**, **Storefront - Execução do plano de excelência** e **Corrigir fluxos críticos do PDV** têm publicação registrada no histórico. Isso encerra aqueles lotes, não os novos achados do laudo. Evitar republicar branches antigas inteiras ou tratar seus últimos commits locais como a versão a implantar.

Critério de conclusão: cada correção com PR/head identificados, revisão e CI; release comprovada por componente; jornada relevante validada; nenhum bloqueio de segurança ou integridade aberto; decisões e limitações externas explicitadas. “100% atualizado” não significa ativar todos os canais opcionais nem incorporar indiscriminadamente todos os PRs.

## Destravamento necessário

1. Retomar esta coordenação numa execução em que as ferramentas de comunicação entre sessões e de escrita aprovável possam operar. A rejeição desta execução é de política da ferramenta; repetir “autorizo” no texto, sozinho, não altera essa configuração.
2. Reusar este relatório, o manifesto das 17 branches e o patch, sem recomeçar auditorias ou pedir novamente decisões já dadas.
3. O bloqueio de criação dos 17 PRs está documentado na sessão anterior com a mesma exigência de aprovação. Não foi contornado por outro meio aqui. A disponibilidade de leitura do GitHub e da DigitalOcean não comprova permissão de mutação.

Sem essas condições, o trabalho produzido nesta execução fica local e revisável. Não há acompanhamento em segundo plano agendado nem sessões retomadas silenciosamente.
