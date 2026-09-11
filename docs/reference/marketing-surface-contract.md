# Contrato da superfície Marketing

- **Proprietário:** Produto/Marketing (operação), Platform/SRE (entrega) e DPO
  (consentimento/auditoria)
- **Última verificação:** 2026-09-11
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
| Facebook | publicação pública na página | 1 por anúncio | mensagem por pessoa |
| Google Meu Negócio | atualização pública padrão do estabelecimento | 1 por anúncio | mensagem por pessoa |
| WhatsApp | mensagem direta | até 1 por pessoa elegível | publicação pública |

Mensagem direta no Instagram está fora do contrato. Se for aprovada no futuro, exige
fluxo de entrega, capability, consentimento, prontidão, limites e comprovante próprios.

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

## Capacidades

| Capacidade | Autoriza |
|---|---|
| `shop.view_marketing` | leitura agregada |
| `shop.edit_marketing_campaigns` | criar/editar campanhas |
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
| `SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED` | Platform Owner | `false`; adapter nem é registrado | por canário público |
| `SHOPMAN_MARKETING_FACEBOOK_PUBLICATION_ENABLED` | Platform Owner | `false`; adapter nem é registrado | por canário público |
| `SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED` | Platform Owner | `false`; adapter nem é registrado | por canário público |
| `SHOPMAN_MARKETING_TARGET_HMAC_KEY` e versão | Segurança | vazio bloqueia materialização segura | rotação versionada |
| `SHOPMAN_MARKETING_TEST_TARGETS_JSON` | Platform Owner | `{}`; nenhum alvo de teste | remover alvo ao fim do teste |
| `SHOPMAN_MARKETING_MEDIA_HOSTS` | Segurança/Marca | vazio; mídia externa bloqueada | revisão por host |
| `SHOPMAN_MARKETING_AI_ASSIST_V2` | Produto | `false`; assistência invisível | MKT-054 |
| `SHOPMAN_MARKETING_AI_PROVIDER_POLICY_APPROVED` | Jurídico/Segurança | `false`; chave não basta | por política do fornecedor |

`SHOPMAN_MARKETING_SIMULATION_ENABLED`, o bypass local de horário e os fluxos
sintéticos pertencem exclusivamente a `config.settings_marketing_demo`. A simulação
recusa ambiente não local e qualquer flag que permita saída externa. Nenhuma flag
desliga consentimento, permissão, CSRF, redaction, unicidade ou revalidação pré-envio.

Instagram/Facebook usam `META_PAGE_ACCESS_TOKEN`; Instagram também exige
`META_IG_USER_ID`, conta Instagram Business ligada à página, e Facebook,
`META_PAGE_ID`. Google exige token OAuth com escopo
`business.manage`, `GOOGLE_BUSINESS_ACCOUNT_ID` e `GOOGLE_BUSINESS_LOCATION_ID`.
O token Google configurado nesta etapa é estático: serve ao canário, mas ativação
contínua exige decidir e validar seu ciclo de renovação. Credencial presente não liga
publicação: a flag da plataforma e os consumidores duráveis — ou o canário unitário
explicitamente armado — permanecem gates independentes. Em `DEBUG`, adapter externo
também exige o opt-in geral de saída externa.

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
de publicação pública e a escolha Story/Feed estão em branch isolada, desligados por
default e ainda sem deploy. Publicar Story, Feed, página do Facebook ou atualização do
Google continua sendo gate humano: requer peça válida, conferência da prévia, conta
correta, credenciais/escopos, autorização explícita e canário público observável. Teste
local não substitui esse gate.
