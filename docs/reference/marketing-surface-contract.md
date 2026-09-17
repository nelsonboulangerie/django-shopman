# Contrato da superfície Marketing

- **Proprietário:** Produto/Marketing (operação), Platform/SRE (entrega) e DPO
  (consentimento/auditoria)
- **Última verificação:** 2026-09-17
- **Verificado contra:** rotas, projeções, permissões e specs de deploy do `HEAD`
- **Gate de deriva:** `make marketing-docs`

Este é o mapa factual do Marketing. Identificadores de código e protocolo permanecem
estáveis em inglês; a apresentação ao operador é pt-BR. Histórico de plano ou relatório
não substitui este contrato.

## Responsabilidade e canais

O `marketing-nuxt` é o único cockpit operacional. Django decide estado, público,
consentimento, autorização, horário, oferta, artefato e ações possíveis. Admin/Unfold
mostra somente auditoria agregada para `shop.audit_marketing`, sem escrita concorrente
e sem navegação por membro, contato, outbox, destino ou tentativa.

| Plataforma | Consequência atual | Cardinalidade | Não significa |
|---|---|---:|---|
| Instagram | Story público por padrão; Feed só por escolha explícita | 1 por anúncio | mensagem direta ou fallback de Story para Feed |
| Facebook | postagem pública na página | 1 por anúncio | mensagem por pessoa |
| Google Meu Negócio | atualização pública padrão do estabelecimento | 1 por anúncio | mensagem por pessoa |
| WhatsApp | mensagem direta | até 1 por pessoa elegível | postagem pública |

Mensagem direta no Instagram está fora do contrato. Se for aprovada no futuro, exige
fluxo de entrega, capability, consentimento, prontidão, limites e comprovante próprios.

**Vocabulário da operação:** mensagem é uma mensagem direta e possui destinatário;
publicação é uma postagem pública e não possui destinatário individual; entrega é o
termo genérico que pode se referir às duas anteriores. Identificadores técnicos podem
permanecer em inglês, mas esses termos não podem ser trocados na UI.

O gate `MKT-CAP-01` foi aprovado em 2026-09-11: a evolução adotará a identidade
`{platform, delivery_kind, format}`, um catálogo server-owned de capacidades e schemas
fechados por destino. Durante a transição, cada plataforma continua resumida a uma
única modalidade de entrega e nenhum novo efeito externo será habilitado. A auditoria
e a decisão completas estão em
[`marketing-platform-capability-audit-20260911.md`](../reports/execution/marketing-platform-capability-audit-20260911.md).

Para novas entregas, as três dimensões são obrigatórias desde o schema 4 e são
persistidas no artefato, outbox e destino. A resposta de `/marketing/options/`
projeta `delivery_capabilities` com modalidade, formatos, default, campos aceitos e
exigência de mídia; o formulário consome essa projeção. Linhas e artefatos anteriores
continuam legíveis pela compatibilidade histórica, mas não podem originar uma nova
identidade incompleta.

O formato público faz parte do artefato imutável (`publication_format`). A prévia,
aprovação e chamada do provider leem o mesmo valor. No Instagram, `story` é o default
de produto para FOMO e exige imagem pública; `feed` é secundário e precisa estar
explicitamente escolhido. Artefato histórico sem formato continua legível, mas o
adapter real o recusa antes da rede — nunca adivinha um efeito novo. A prévia de Story
mostra a imagem 9:16 e avisa que o texto do rascunho não é sobreposto automaticamente.

## Rotas Nuxt

<!-- marketing-ui-routes:start -->
- `/`
- `/announcements/:id`
- `/campaigns`
- `/history`
- `/platforms`
- `/templates`
<!-- marketing-ui-routes:end -->

Rotas de infraestrutura: `/api/v1/**` é o BFF same-origin, `/sse/notifications`
transporta apenas invalidação pessoal, `/health/live` prova o processo/BFF e
`/health/ready` inclui a prontidão do Django. O alias legado
`/campaign/announcements/:id` redireciona para `/announcements/:id`.

## Rotas Django

A lista abaixo é comparada por máquina com `shopman/backstage/api/urls.py`. `:id` e
`:ref` representam parâmetros de rota, não texto literal.

<!-- marketing-api-routes:start -->
- `/api/v1/backstage/marketing/`
- `/api/v1/backstage/marketing/announcements/:id/`
- `/api/v1/backstage/marketing/announcements/:id/approve/`
- `/api/v1/backstage/marketing/announcements/:id/cancel/`
- `/api/v1/backstage/marketing/announcements/:id/delivery-actions/`
- `/api/v1/backstage/marketing/announcements/:id/reconcile-deliveries/`
- `/api/v1/backstage/marketing/announcements/:id/reject/`
- `/api/v1/backstage/marketing/announcements/:id/reschedule/`
- `/api/v1/backstage/marketing/announcements/:id/retry-deliveries/`
- `/api/v1/backstage/marketing/announcements/:id/rewrite/`
- `/api/v1/backstage/marketing/announcements/:id/suggestions/:ref/disposition/`
- `/api/v1/backstage/marketing/audience/count/`
- `/api/v1/backstage/marketing/history/`
- `/api/v1/backstage/marketing/options/`
- `/api/v1/backstage/marketing/platforms/`
- `/api/v1/backstage/marketing/preview/`
- `/api/v1/backstage/marketing/rules/`
- `/api/v1/backstage/marketing/rules/:id/`
- `/api/v1/backstage/marketing/rules/:id/fire/`
- `/api/v1/backstage/marketing/security/dual-control/`
- `/api/v1/backstage/marketing/security/freeze/`
- `/api/v1/backstage/marketing/security/step-up/`
- `/api/v1/backstage/marketing/security/unfreeze/`
- `/api/v1/backstage/marketing/telemetry/vital/`
- `/api/v1/backstage/marketing/templates/`
- `/api/v1/backstage/marketing/templates/:id/`
- `/api/v1/backstage/marketing/v2/`
- `/api/v1/backstage/marketing/v2/announcements/:id/`
- `/api/v1/backstage/marketing/v2/history/`
- `/api/v1/backstage/marketing/whatsapp-template/`
- `/api/v1/backstage/marketing/whatsapp-template/test/`
<!-- marketing-api-routes:end -->

## Projeção e comandos

As leituras v2 são o limite gerado e versionado:

- fonte: `shopman/backstage/projections/marketing_v2.py`;
- JSON Schema: `contracts/projections/marketing_v2.schema.json`;
- OpenAPI 3.1: `contracts/openapi/marketing_v2.openapi.json`;
- cliente: `surfaces/marketing-nuxt/app/generated/marketingClient.ts`;
- verificação: `python manage.py export_marketing_client --check`.

Projection não carrega rótulo final, copy de UX, PII nem membership. A apresentação
pt-BR mora no Nuxt. Cada ação vem resolvida pelo backend com método, disponibilidade,
motivo, versão, esquema, idempotência e confirmação. O cliente não deduz autorização
nem transição a partir do status.

Comandos sensíveis usam CAS, idempotência, confirmação contextual e comprovante.
Conforme consequência e limiar, exigem nova autenticação, TOTP ou duplo controle.
Outbox, público selado, artefato imutável, destinos e tentativas formam o grafo durável.
`accepted_unconfirmed`, `confirmed`, falha final, falha repetível e `unknown` são estados
distintos. `unknown` nunca recebe repetição cega.

Dialeto de erro: comandos respondem `{code, detail, field_errors}`, o CRUD de
campanhas/modelos `{detail, field, fields}` e o 401 leva `code`; `detail` está sempre
presente. Ver [Superset do Marketing em `errors.md`](errors.md#superset-do-marketing-deliberado).

## Capacidades

| Capacidade | Autoriza |
|---|---|
| `shop.view_marketing` | leitura agregada |
| `shop.edit_marketing_campaigns` | criar/editar campanhas; editar anúncio antes de aprovar (`PATCH announcements/:id/`) |
| `shop.edit_marketing_templates` | criar/editar modelos |
| `shop.preview_marketing_audience` | contar e pré-visualizar público |
| `shop.approve_marketing_announcements` | aprovar, rejeitar e usar assistência de texto |
| `shop.publish_marketing_announcements` | publicar, agendar, cancelar e reagendar |
| `shop.fire_marketing_campaigns` | disparar campanha para revisão |
| `shop.retry_failed_marketing` | repetir somente falhas seguras |
| `shop.reconcile_unknown_marketing` | consultar resultado incerto sem reenviar |
| `shop.send_marketing_test` | um alvo de teste cadastrado e verificado |
| `shop.configure_marketing_platforms` | configurar plataformas |
| `shop.audit_marketing` | auditoria agregada no Admin |
| `shop.access_marketing_delivery_pii` | acesso excepcional a PII protegida |
| `shop.freeze_marketing` | congelar/descongelar efeitos externos |

`shop.manage_campaigns` é legado e só mantém leitura/edição/prévia durante a transição;
não concede aprovação, publicação, disparo, teste ou configuração.

## Flags e configuração segura

| Configuração | Owner | Padrão/failsafe | Expira ou é reavaliada |
|---|---|---|---|
| `SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED` | Platform/SRE | `false`; sem handoff | MKT-054 |
| `SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED` | Platform/SRE | `false`; sem tentativa | MKT-054 |
| `SHOPMAN_MARKETING_PUBLICATION_CANARY_ENABLED` | Release Manager | `false`; comando unitário não cruza a fronteira | desligar após o canário |
| `SHOPMAN_MARKETING_DELIVERY_ADAPTERS` | Platform Owner | vazio; canal indisponível | por adapter/canário |
| `SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED` | Platform Owner | `false`; adapter durável do WhatsApp nem é registrado — campanha aprovada fica na fila | por etapa, junto do modo: `canary` → `open` |
| `SHOPMAN_MARKETING_WHATSAPP_MODE` | Platform Owner | `blocked`; nenhum evento de Marketing sai por WhatsApp. `canary`/`open` sem cache compartilhado continuam bloqueados | por etapa: `canary` → `open` |
| `SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS` | Platform Owner | vazio; `canary` sem lista fica bloqueado | esvaziar ao fim do ensaio |
| `SHOPMAN_MANYCHAT_FLOW_SETTLE_SECONDS` | Platform Owner | `120`; inválido volta ao padrão | revisar com a latência observada no ensaio |
| `SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED` | Platform Owner | `false`; adapter nem é registrado | por canário público |
| `SHOPMAN_MARKETING_FACEBOOK_PUBLICATION_ENABLED` | Platform Owner | `false`; adapter nem é registrado | por canário público |
| `SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED` | Platform Owner | `false`; adapter nem é registrado | por canário público |
| `SHOPMAN_MARKETING_TIKTOK_PUBLICATION_ENABLED` | Platform Owner | `false`; adapter experimental nem é registrado | somente após OAuth, revisão e gate TikTok |
| `SHOPMAN_MARKETING_TARGET_HMAC_KEY` e versão | Segurança | vazio bloqueia materialização segura | rotação versionada |
| `SHOPMAN_MARKETING_TEST_TARGETS_JSON` | Platform Owner | `{}`; nenhum alvo de teste | remover alvo ao fim do teste |
| `SHOPMAN_MARKETING_MEDIA_HOSTS` | Segurança/Marca | vazio; mídia externa bloqueada | revisão por host |
| `SHOPMAN_MARKETING_AI_ASSIST_V2` | Produto | `false`; assistência invisível | MKT-054 |
| `SHOPMAN_MARKETING_AI_PROVIDER_POLICY_APPROVED` | Jurídico/Segurança | `false`; chave não basta | por política do fornecedor |

`SHOPMAN_MARKETING_SIMULATION_ENABLED`, o bypass local de horário e os fluxos
sintéticos pertencem exclusivamente a `config.settings_marketing_demo`. A simulação
recusa ambiente não local e qualquer flag que permita saída externa. Nenhuma flag
desliga consentimento, permissão, CSRF, redaction, unicidade ou revalidação pré-envio.

WhatsApp de Marketing (campanha e "Me avise") abre por modo, não por credencial. Cada
mensagem com flow reserva o contato no cache compartilhado durante a janela de
assentamento, antes de gravar qualquer campo; outra mensagem com flow para a mesma
pessoa volta depois (`subscriber_busy`, retentável, nunca `unknown`). Em `canary`, quem
está fora da lista é suprimido no claim (`whatsapp_canary_recipient_excluded`) e o
adapter recusa na última porta; a prontidão aparece como `degraded` com
`canary_recipients` (contagem, nunca refs). Decisão e limites em
[ADR-009](../decisions/adr-009-whatsapp-via-manychat.md).

Campanha de WhatsApp aprovada chega ao ManyChat pelo ledger durável só quando
`SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED` registra o adapter
`marketing_delivery_whatsapp` — com a flag desligada a prontidão diz
`platform_switched_off` e os destinos ficam na fila, sem envio. O adapter confere o modo na última
porta, relê consentimento, exige o flow selado na aprovação e monta as variáveis do
flow só do artefato aprovado (corpo, link, foto e fatos selados; do destino, só
telefone e primeiro nome). Aceite do ManyChat é `accepted_unconfirmed`; resposta
ambígua depois de possível escrita é `unknown`; recusa antes de chamar é falha final
com código; contato ocupado volta pela fila. A etapa que leva o destino ao provedor
roda no `maintenance-worker`, sem componente próprio — ver
[Entrega sem componente próprio](#entrega-sem-componente-próprio).

Cada mensagem com flow de Marketing grava o conjunto completo de campos declarado para o
evento (`MARKETING_FLOW_FIELDS`), com vazio para o que não tiver — nunca herda preço,
nome ou link da mensagem anterior.

Campanha geral por WhatsApp exige um **mínimo de pessoas elegíveis configurável no
Admin** (Configuração → A loja → Integrações → "Campanhas de WhatsApp"), gravado em
`Shop.defaults["marketing"]["whatsapp_minimum_audience"]`. Aumentar o número impede que
uma campanha "geral" vire mensagem mirada em uma pessoa. **Padrão 1** (chave ausente),
por decisão do dono em 2026-09-17: no início da operação um mínimo alto seguraria
campanhas boas antes de a casa sentir o impacto. O Admin aceita inteiro a partir de 1 e
recusa zero, negativo e texto com mensagem em português; quem mudou e quando fica no
histórico da página (`LogEntry`). A aprovação lê o valor na hora e, abaixo dele, recusa
com `audience_below_minimum`, `minimum_count` igual ao número configurado e o número na
mensagem. No modo `canary` o mínimo não se aplica, porque só a lista de canário
controlada pela operação recebe — a aprovação registra `canary=true` com o
`minimum_count` que não valeu, e o cockpit diz "Ensaio: o mínimo de N não vale; só a
lista de canário recebe". Em `blocked` e `open` o mínimo vale.

Instagram/Facebook usam `META_PAGE_ACCESS_TOKEN`; Instagram também exige
`META_IG_USER_ID`, conta Instagram Business ligada à página, e Facebook,
`META_PAGE_ID`. Google exige token OAuth com escopo
`business.manage`, `GOOGLE_BUSINESS_ACCOUNT_ID` e `GOOGLE_BUSINESS_LOCATION_ID`.
O token Google configurado nesta etapa é estático: serve ao canário, mas ativação
contínua exige decidir e validar seu ciclo de renovação. Credencial presente não liga
publicação: a flag da plataforma e os consumidores duráveis — ou o canário unitário
explicitamente armado — permanecem gates independentes. Em `DEBUG`, adapter externo
também exige o opt-in geral de saída externa.

TikTok ainda não integra o catálogo selecionável. O adapter Direct Post de foto é
somente uma fronteira testável e inerte: token estático serve no máximo a canário
controlado; operação contínua exige armazenamento OAuth com renovação, consulta de
`creator_info`, aprovação de `video.publish` e auditoria Direct Post. A simples
presença da flag ou da credencial não autoriza adicionar TikTok a uma campanha.

### Plataforma desligada × integração não registrada

Os adapters de Instagram, Facebook, Google e WhatsApp existem no código; a flag de
cada plataforma (tabela acima) decide se ele é registrado em
`SHOPMAN_MARKETING_DELIVERY_ADAPTERS` neste ambiente. `Shop.integrations`, quando
define `marketing_delivery`, responde antes das settings, como em `get_adapter`.
O estado de cada plataforma sai de `marketing_delivery_runtime.delivery_lanes()`,
sem chamar adapter nem provedor:

| Estado | Quando | Prontidão | Worker | Log |
|---|---|---|---|---|
| `registered` | há integração registrada | segue para simulação/credencial/probe | pede o adapter | — |
| `switched_off` | nada registrado e a flag da plataforma desligada | `blocked`, `platform_switched_off`, "desligada neste ambiente"; a ação cita a flag | não pede o adapter; destinos seguem `queued`, sem reserva | nenhum |
| `unconfigured` | nada registrado com a flag ligada | `blocked`, `publication_adapter_missing` / `whatsapp_durable_provider_missing`, "erro de configuração" | pede o adapter | WARNING do `get_adapter` a cada ciclo |

Desligada é escolha de quem opera; o aviso do `get_adapter` fica para a integração
que deveria existir e não existe. A aprovação não recusa plataforma desligada: o que
for aprovado para ela é materializado e fica `queued`. No cockpit, o resultado da
plataforma diz "aguardando a plataforma ligar", e não só "na fila"; o
`diagnose_marketing` mostra o bloco `lanes` (estado, flag e destinos na fila) e
aponta `observe:platform_switched_off_holds_queued`. Ao ligar, cada destino ainda
passa pelas conferências de prazo e consentimento antes do envio.

## Entrega sem componente próprio

A etapa final da entrega — destino `queued` → adapter → provedor
(`process_marketing_delivery`) — **não tem componente próprio** no App Platform. Ela roda
dentro do `maintenance-worker` que já existe (`python manage.py maintenance_worker`, ciclo
de 300 s), uma passada por ciclo, logo **depois** de `process_marketing_outbox`. A ordem é
proposital: a outbox publica a Directive, o dispatch por signal materializa e enfileira os
destinos no commit, e a passada de entrega os encontra no mesmo ciclo. Decisão do dono
(2026-09-17): um worker a mais custaria mais do que a entrega que ele faz.

| Opção da passada | Valor | Por quê |
|---|---|---|
| `worker_id` | `maintenance_worker:marketing-delivery` | estável: o `lease_owner` diz qual componente segura o destino |
| `limit` | `20` destinos (e 20 consultas) por passada | uma mensagem de WhatsApp com flow custa ~20 chamadas ao ManyChat; o lote cabe no ciclo |
| `lease_seconds` | `300` | cobre a passada inteira; se o processo cair, o destino volta a ser elegível em até 5 min |
| `--with-reconciliation` | ligado | só executa consultas somente-leitura já pedidas pelo operador; `unknown` nunca é reenviado |
| `--watch` / `--with-outbox` | desligados | passada única; a outbox já roda como tarefa própria do ciclo |

`SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED` continua sendo o portão: desligada, a passada
volta calada (sem aviso a cada ciclo) e nenhum destino é reservado. Exceção na entrega é
logada e **não** derruba o ciclo das demais tarefas. Ligar a consequência é ligar as flags;
não há worker para criar, escalar ou pagar. O comando avulso continua servindo ao
simulador local (`make marketing-simulator`) e a ensaio explícito.

**Latência esperada (aprovação → chamada ao provedor).** Uma campanha aprovada entra na
próxima passada, não sai no mesmo segundo. No pior caso, a aprovação chega logo depois da
outbox do ciclo corrente e espera o ciclo seguinte: **até ~300 s + a duração das tarefas
que vêm antes da outbox no ciclo + a própria passada**, na prática **até ~7 minutos** para
o último dos primeiros 20 destinos. Cada 20 destinos a mais somam um ciclo (≈300 s): 100 pessoas
elegíveis levam até ~30 minutos para esgotar a fila. Se a Directive não for processada no
commit e ficar para o `directive-worker`, soma-se mais um ciclo. Horário comercial,
contato ocupado (`subscriber_busy`) e freeze adiam por conta própria. **"Enviar agora"
significa "na próxima passada" e pode levar alguns minutos** — não é defeito.

## Operação, diagnóstico e gates

- `make marketing-diagnose`: leitura agregada sem PII ou chamada de provider;
- `make marketing-drills`: oito incidentes sintéticos e testes dos runbooks;
- `make marketing-capacity`: 200 mil candidatos e 20 mil destinos, sem provider;
- `make marketing-simulator`: outbox → ledger → comprovante local, sem rede;
- `python manage.py run_marketing_publication_canary --announcement-id ID
  --platform instagram`: preflight somente leitura a partir do número já visível na
  URL; imprime a consequência e o comando exato, sem publicar;
- `make admin`: garante o corte Nuxt operacional/Admin audit-only;
- job `Marketing — cadeia completa`: instalação, unit/component, lint, tipos, build,
  E2E, acessibilidade, visual, segurança e auditoria de dependências.

Runbooks: [`docs/runbooks/README.md`](../runbooks/README.md). Simulador:
[`docs/operations/marketing-local-simulator.md`](../operations/marketing-local-simulator.md).
Canário público:
[`docs/operations/marketing-publication-canary.md`](../operations/marketing-publication-canary.md).
Capacidade: [`docs/engineering/marketing-capacity-gate.md`](../engineering/marketing-capacity-gate.md).

## Deploy e estado de rollout

O host é `mkt.<domínio>`, com `NUXT_DJANGO_BASE_URL`/`NUXT_PUBLIC_DJANGO_BASE_URL`
apontando para `api.<domínio>` e `NUXT_PUBLIC_OPERATOR_HUB_URL` para `central.<domínio>`.
Os dois blueprints versionados usam readiness `/health/ready` e liveness
`/health/live`. Eles são referência; nunca devem sobrescrever o spec vivo sem preservar
segredos e obter autorização explícita.

Em 2026-09-11, o cockpit e o pipeline-base de `#601` estão em produção e o teste
WhatsApp unitário para contato verificado foi recebido pelo proprietário. Os adapters
de postagem pública e a escolha Story/Feed estão em branch isolada, desligados por
default e ainda sem deploy. Publicar Story, Feed, página do Facebook ou atualização do
Google continua sendo gate humano: requer peça válida, conferência da prévia, conta
correta, credenciais/escopos, autorização explícita e canário público observável. Teste
local não substitui esse gate.
