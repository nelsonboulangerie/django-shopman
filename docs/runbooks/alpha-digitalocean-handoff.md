# DigitalOcean - handoff operacional do app unico

> **Estado confirmado em 11/09/2026:** `menu.nelsonboulangerie.com.br` e o
> dominio definitivo da loja. `alpha.*` e `staging.*` foram aposentados e nao
> devem ser recriados. O app vivo se chama `shopman-nelson` e continua com
> perfil de pre-go-live (`SHOPMAN_ENVIRONMENT=staging`, Pix mock e OTP/captura
> de teste expostos). O rename foi aplicado em janela autorizada, preservando
> App ID, custo, domínios, componentes e o spec vivo; health, readiness, loja,
> páginas legais e API responderam 200 depois do deployment.

> O componente `web` e o backend Django/Daphne que atende API, Admin e
> backstage. O Storefront ja e o componente `storefront-nuxt`; esses nomes nao
> sao intercambiaveis.

Objetivo: registrar o estado aplicado do unico app na DigitalOcean e as regras
para nao aumentar custo recorrente nem perder segredos. O dominio ja e o
definitivo; a ativacao de adapters e segredos reais continua sendo um gate
separado e explicitamente autorizado.

## Decisao obrigatoria

- Nao manter `staging.*` e `alpha.*` como ambientes separados.
- Reaproveitar o App Platform atual, nomeado `shopman-nelson`.
- Manter o perfil de pre-go-live ate autorizacao especifica de producao.
- Usar `menu.nelsonboulangerie.com.br` como URL definitiva da loja.
- Nao recriar `alpha.*` ou `staging.*`.
- Nao reclassificar o banco existente sem gate de producao e plano de recuo.
- Manter API, Admin e apps de operador nos dominios tecnicos/operacionais existentes.
- Nao recriar Postgres/Valkey so para trocar nomes internos `staging` por `alpha`.

## Custo esperado

Economia financeira e requisito. Nao duplicar App Platform, Postgres, Valkey,
workers ou superficies para criar alpha. O trabalho de renomeacao e aceitavel;
o custo recorrente na DigitalOcean nao.

O spec atual roda aproximadamente:

- `web`: 1 instancia `apps-s-1vcpu-1gb`.
- Nuxt: 6 instancias `apps-s-1vcpu-0.5gb`.
- Workers: 3 instancias `apps-s-1vcpu-0.5gb`.
- PostgreSQL gerenciado: 1 cluster 1 GiB.
- Valkey gerenciado: 1 cluster 1 GiB.

Estimativa em 22/08/2026: cerca de USD 87/mes, fora trafego extra, storage,
logs e IP dedicado. A proposta lida em 11/09/2026 indicou USD 84 sem mudar
componentes. Criar outro ambiente duplica quase tudo; nao criar outro
app/banco/cache apenas por nomenclatura.

## Historico de renomeacao staging -> alpha

Estado aplicado:

- App Platform: `shopman-nelson`.
- App ID preservado: `40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`.
- Projeto DigitalOcean: `Shopman Alpha`.
- Contexto `doctl` com token nesta maquina: `shopman-alpha-deploy`.
- Contexto `shopman-alpha-write`: nao existe.
- Default ingress nao mudou com o rename:
  `https://shopman-staging-cdjpy.ondigitalocean.app`.
- CNAMEs gerenciados pelo App Platform ficaram idempotentes; rename nao gerou
  downtime nem janela de DNS.
- Spec versionado esperado: `.do/app.alpha-subdomains.yaml`.

Nao renomear se exigir fork, recriacao, migracao ou nova cobranca recorrente:

- Cluster PostgreSQL ja existente `shopman-staging-postgres`.
- Cluster Valkey ja existente `shopman-staging-cache`.
- Pool existente `shopman-staging-pool`.
- Nome do database/user `shopman`.

Justificativa: app/spec/projeto/contexto sao rotulos operacionais e viraram
alpha para reduzir confusao. Cluster de banco/cache e pool sao recursos
stateful; criar novos recursos so por cosmetica aumenta custo financeiro e
risco. `staging` no nome do banco/cache significa "nao-producao", nao URL
publica.

### Rename aplicado para shopman-nelson

A proposta gerada a partir do spec vivo mudou somente `name`, preservando App
ID, componentes, domínios, recursos e valores encrypted. O custo proposto
permaneceu USD 84. O deployment `0b7731c2-8caa-4683-bac0-3259a58ac910`
terminou `ACTIVE`; health, readiness e rotas públicas responderam 200. O spec
pós-deploy corresponde byte a byte à candidata validada. O deployment anterior
`20f67ba8-7134-4126-b3ba-099d898566d7` permanece identificado para recuo.

### Publicação W00–W10 do Storefront

A promoção autorizada do PR #612 entrou em `main` como
`cc135f47c5bcabe62ff43eab1e9bb819f191f92c`. O workflow por imagens publicou
`web`, `storefront`, `production` e `purchase`; o deployment final
`0f6dda3d-6bef-43c3-a458-945d9fc1d52f` terminou `ACTIVE` em 11/09/2026 às
21:39:47Z, com 47/47 etapas e todos os serviços, workers e o job `release` em
`SUCCESS`. O release aplicou `backstage.0062`, `craftsman.0011`,
`orderman.0005`–`0006` e `storefront.0004`–`0007` com `OK`.

O smoke correlacionado por digest passou readiness, cardápio, checkout e SSR.
Como âncoras de recuo, as imagens anteriores continuam disponíveis nas tags
imutáveis `web-1de5f3496a2b4fe4f3c8f1862f316301cc70540e`,
`storefront-587392a49280fadf6740ede27a8dfe67a5c34676`,
`production-c14cdb64781b82a7ed70453a8fc75aaf9e426465` e
`purchase-587392a49280fadf6740ede27a8dfe67a5c34676`.

Os merges posteriores #611 e #615 preservaram esta implementação. O deployment
`239c5fd5-846f-4983-be70-9fb660654c73` publicou `web` no descendente
`29e0737e99a806975df8810b5b03393af83e9f02`, reutilizou a imagem Storefront e
terminou `ACTIVE` com 47/47 etapas; o smoke correlacionado passou. O merge
documental #617 não publicou imagem nem iniciou novo deployment.

## Dominio da loja

Configurar a loja em seu dominio definitivo:

```text
menu.nelsonboulangerie.com.br -> storefront-nuxt
```

Manter API, Admin e backstage nos dominios operacionais existentes:

```text
api.boulangerie.com.br      -> web para API/backstage/webhooks
admin.boulangerie.com.br    -> web para Admin tecnico
gestor.boulangerie.com.br   -> orders-nuxt
kds.boulangerie.com.br      -> kds-nuxt
pdv.boulangerie.com.br      -> pos-nuxt
prod.boulangerie.com.br     -> production-nuxt
central.boulangerie.com.br  -> hub-nuxt
mkt.boulangerie.com.br      -> marketing-nuxt
bi.boulangerie.com.br       -> bi-nuxt
```

Essa escolha e aceitavel porque apenas o storefront e divulgado a testadores.
Nao criar aliases `api.alpha.*`, `admin.alpha.*`, `gestor.alpha.*`,
`pdv.alpha.*`, `kds.alpha.*`, `prod.alpha.*` ou `central.alpha.*` sem decisao
nova.

## App Platform

App vivo:

```text
app name: shopman-nelson
app id: 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f
spec versionado: .do/app.alpha-subdomains.yaml
```

Para subir codigo novo:

```bash
doctl --context shopman-alpha-deploy apps create-deployment \
  40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f --wait
```

Para inspecionar ou preparar mudanca futura de dominios/topologia, primeiro
salvar o spec vivo:

```bash
doctl --context shopman-alpha-deploy apps spec get \
  40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f --format yaml \
  > /tmp/shopman-alpha-live-spec.yaml
```

Nao aplicar `.do/app.alpha-subdomains.yaml` diretamente com
`doctl apps update --spec`. Esse comando faz replace do spec inteiro e pode
apagar variaveis encrypted que existem so no app vivo. Mudanca futura de config
deve partir do spec vivo capturado por `apps spec get`, preservando secrets.

Validacao correta:

```bash
# Template versionado do repo, sem EV[...].
doctl apps spec validate .do/app.alpha-subdomains.yaml

# Spec vivo capturado do app existente, com SECRET/EV[...] preservados.
doctl apps propose --spec /tmp/shopman-alpha-live-spec.yaml \
  --app 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f
```

Nao use `doctl apps spec validate /tmp/shopman-alpha-live-spec.yaml` para spec
vivo: esse comando valida como app novo e rejeita os `EV[...]` encrypted que
precisam ser preservados no app existente. `apps propose --app` valida contra o
app alvo e mostra custo/diff antes de qualquer update.

## Estado atual de variaveis do app

```env
DJANGO_DEBUG=false
SHOPMAN_ENVIRONMENT=staging
SHOPMAN_PREPROD_URL=https://menu.nelsonboulangerie.com.br

DJANGO_ALLOWED_HOSTS=api.boulangerie.com.br,admin.boulangerie.com.br
CSRF_TRUSTED_ORIGINS=https://menu.nelsonboulangerie.com.br,https://api.boulangerie.com.br,https://admin.boulangerie.com.br,https://gestor.boulangerie.com.br,https://kds.boulangerie.com.br,https://pdv.boulangerie.com.br,https://prod.boulangerie.com.br,https://mkt.boulangerie.com.br,https://central.boulangerie.com.br,https://bi.boulangerie.com.br

SHOPMAN_STOREFRONT_BASE_URL=https://menu.nelsonboulangerie.com.br
SHOPMAN_DOMAIN=https://menu.nelsonboulangerie.com.br
AUTH_DEFAULT_DOMAIN=menu.nelsonboulangerie.com.br
WHATSAPP_STOREFRONT_URL=https://menu.nelsonboulangerie.com.br

SHOPMAN_OPERATOR_API_HOST=api.boulangerie.com.br
SHOPMAN_OPERATOR_COOKIE_DOMAIN=.boulangerie.com.br
SHOPMAN_ADMIN_HOST=admin.boulangerie.com.br
SHOPMAN_ORDERS_BASE_URL=https://gestor.boulangerie.com.br
SHOPMAN_KDS_BASE_URL=https://kds.boulangerie.com.br
SHOPMAN_POS_BASE_URL=https://pdv.boulangerie.com.br
SHOPMAN_PRODUCTION_BASE_URL=https://prod.boulangerie.com.br

SHOPMAN_PIX_ADAPTER=shopman.shop.adapters.payment_mock
SHOPMAN_CARD_ADAPTER=shopman.shop.adapters.payment_stripe
SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true
SHOPMAN_EXPOSE_MOCK_CAPTURE=true
SHOPMAN_MOCK_PIX_AUTO_CONFIRM=false
SHOPMAN_EXPOSE_DEBUG_OTP=true
SHOPMAN_STAGING_AUTOPILOT=false
```

Segredos continuam como `SECRET`/encrypted no painel, nunca em YAML versionado.

## Integracoes

Google:

- Verificar `nelsonboulangerie.com.br` como dominio autorizado.
- Usar um OAuth client identificado para o app Shopman/Nelson.
- Cadastrar origem exata `https://menu.nelsonboulangerie.com.br`.
- Cadastrar callback exato usado pelo app em `https://menu.nelsonboulangerie.com.br/...`.
- Trocar credenciais de teste somente no gate autorizado de producao.

Fiscal:

- Pendente do Pablo: `SHOPMAN_FISCAL_ADAPTER` e `FOCUS_NFE_TOKEN` nao existem
  no app vivo.
- Criterio de aceite fiscal esta reprovado ate Focus NFe homologacao estar
  configurado.
- Validar emissao, consulta, erro reprocessavel e cancelamento.

iFood:

- OAuth esta configurado.
- Pendente do Pablo: `IFOOD_MERCHANT_ID=2512433` e recusado pelo iFood com HTTP
  400 em `x-polling-merchants`.
- Confirmar que `ifood-poll-worker` esta rodando.
- Testar evento repetido, falha antes do ack, confirmacao, pronto, despacho e cancelamento.

Pagamentos:

- Pix pode ficar mock durante o pre-go-live por limite de sandbox Pix.
- O botao de simular pagamento pode ficar exposto somente durante o pre-go-live.
- Producao deve falhar se `SHOPMAN_EXPOSE_MOCK_CAPTURE=true`.

## Criterio de aceite

Antes de liberar testadores:

```bash
make alpha-readiness preprod_url=https://menu.nelsonboulangerie.com.br
make smoke-gateways
make omotenashi-qa strict=1
```

Aceitar apenas warnings documentados de pre-go-live: pagamento mock, botao de
simulacao, OTP debug e autopilot. Focus NFe ausente e merchant iFood invalido
sao pendencias externas do Pablo.

Antes de producao:

```bash
make production-readiness \
  manual_qa=docs/reports/manual-qa.md \
  preprod_url=https://menu.nelsonboulangerie.com.br
```

Esse comando ainda e insatisfazivel com um unico app porque os hosts de operador
rodam no mesmo App Platform, com mock e OTP debug ligados.
Isso e bloqueio de go-live/pre-producao real, nao regressao do handoff.

## Proibido

- Criar um segundo App Platform apenas por nomenclatura.
- Criar banco/cache novos so para trocar nome `staging` por `alpha`.
- Recriar `alpha.nelsonboulangerie.com.br` ou `staging.nelsonboulangerie.com.br`.
- Usar banco alpha em producao.
- Usar secrets de alpha em producao.
- Divulgar URLs de backstage para testadores finais.
- Criar aliases `api.alpha.*`, `admin.alpha.*` ou `*.alpha.*` para backstage sem necessidade.
- Rodar `apps update --spec` sem backup do spec vivo.
- Recriar aliases `*.staging.nelsonboulangerie.com.br` — removidos em 2026-09-01, sem legado.
