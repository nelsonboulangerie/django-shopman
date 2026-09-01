# Alpha DigitalOcean - handoff operacional

Objetivo: registrar o estado aplicado do alpha tecnico na DigitalOcean e as
regras para nao aumentar custo recorrente nem perder segredos. O alpha deve
ficar pronto para testadores; na producao final entram outro dominio, segredos
reais e adapters reais.

## Decisao obrigatoria

- Nao manter `staging.*` e `alpha.*` como ambientes separados.
- Reaproveitar o App Platform atual, ja renomeado para `shopman-alpha`.
- Manter `SHOPMAN_ENVIRONMENT=staging` no alpha.
- Usar `alpha.nelsonboulangerie.com.br` como unica URL divulgada aos testadores.
- Reservar `menu.nelsonboulangerie.com.br` para producao final.
- Nao apontar `menu.*` para o Shopman enquanto o cardapio antigo ainda estiver em uso.
- Nao transformar o banco alpha em banco de producao.
- Manter API, Admin e apps de operador nos dominios tecnicos/operacionais existentes.
- Nao recriar Postgres/Valkey so para trocar nomes internos `staging` por `alpha`.
- `staging.*` continua como ALIAS de rollback; nao divulgar.

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
logs e IP dedicado. Criar staging e alpha separados dobra quase tudo. Nao criar
outro app/banco/cache.

## Renomeacao staging -> alpha

Estado aplicado:

- App Platform: `shopman-alpha`.
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

## Dominios do alpha

Configurar somente a loja publica de teste em `alpha.nelsonboulangerie.com.br`:

```text
alpha.nelsonboulangerie.com.br -> storefront-nuxt
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
app name: shopman-alpha
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

## Estado atual de variaveis do alpha

```env
DJANGO_DEBUG=false
SHOPMAN_ENVIRONMENT=staging
SHOPMAN_PREPROD_URL=https://alpha.nelsonboulangerie.com.br

DJANGO_ALLOWED_HOSTS=api.boulangerie.com.br,admin.boulangerie.com.br
CSRF_TRUSTED_ORIGINS=https://alpha.nelsonboulangerie.com.br,https://api.boulangerie.com.br,https://admin.boulangerie.com.br,https://gestor.boulangerie.com.br,https://kds.boulangerie.com.br,https://pdv.boulangerie.com.br,https://prod.boulangerie.com.br,https://mkt.boulangerie.com.br,https://central.boulangerie.com.br,https://bi.boulangerie.com.br

SHOPMAN_STOREFRONT_BASE_URL=https://alpha.nelsonboulangerie.com.br
SHOPMAN_DOMAIN=https://alpha.nelsonboulangerie.com.br
AUTH_DEFAULT_DOMAIN=alpha.nelsonboulangerie.com.br
WHATSAPP_STOREFRONT_URL=https://alpha.nelsonboulangerie.com.br

SHOPMAN_OPERATOR_API_HOST=api.boulangerie.com.br
SHOPMAN_OPERATOR_COOKIE_DOMAIN=.boulangerie.com.br
SHOPMAN_ADMIN_HOST=admin.boulangerie.com.br
SHOPMAN_ORDERS_BASE_URL=https://gestor.boulangerie.com.br
SHOPMAN_KDS_BASE_URL=https://kds.boulangerie.com.br
SHOPMAN_POS_BASE_URL=https://pdv.boulangerie.com.br
SHOPMAN_PRODUCTION_BASE_URL=https://prod.boulangerie.com.br

SHOPMAN_PIX_ADAPTER=shopman.shop.adapters.payment_mock
SHOPMAN_CARD_ADAPTER=shopman.shop.adapters.payment_mock
SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true
SHOPMAN_EXPOSE_MOCK_CAPTURE=true
SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true
SHOPMAN_EXPOSE_DEBUG_OTP=true
SHOPMAN_STAGING_AUTOPILOT=true
```

Segredos continuam como `SECRET`/encrypted no painel, nunca em YAML versionado.

## Integracoes

Google:

- Verificar `nelsonboulangerie.com.br` como dominio autorizado.
- Criar OAuth client separado: `Shopman Alpha`.
- Cadastrar origem exata `https://alpha.nelsonboulangerie.com.br`.
- Cadastrar callback exato usado pelo app em `https://alpha.nelsonboulangerie.com.br/...`.
- Nao reutilizar secret do alpha em producao.

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

- Pix/cartao podem ficar mock no alpha por limite de sandbox Pix.
- O botao de simular pagamento pode ficar exposto somente no alpha.
- Producao deve falhar se `SHOPMAN_EXPOSE_MOCK_CAPTURE=true`.

## Criterio de aceite

Antes de liberar testadores:

```bash
make alpha-readiness preprod_url=https://alpha.nelsonboulangerie.com.br
make smoke-gateways
make omotenashi-qa strict=1
```

Aceitar apenas warnings documentados de alpha: pagamento mock, botao de
simulacao, OTP debug e autopilot. Focus NFe ausente e merchant iFood invalido
sao pendencias externas do Pablo.

Antes de producao:

```bash
make production-readiness \
  manual_qa=docs/reports/manual-qa.md \
  preprod_url=https://alpha.nelsonboulangerie.com.br
```

Esse comando ainda e insatisfazivel com um unico app porque os hosts de operador
rodam no mesmo App Platform do alpha, com mock, OTP debug e autopilot ligados.
Isso e bloqueio de go-live/pre-producao real, nao regressao do handoff.

## Proibido

- Criar um segundo App Platform `shopman-alpha`.
- Criar banco/cache novos so para trocar nome `staging` por `alpha`.
- Apontar `menu.nelsonboulangerie.com.br` antes do go-live.
- Usar banco alpha em producao.
- Usar secrets de alpha em producao.
- Divulgar URLs de backstage para testadores finais.
- Criar aliases `api.alpha.*`, `admin.alpha.*` ou `*.alpha.*` para backstage sem necessidade.
- Rodar `apps update --spec` sem backup do spec vivo.
- Recriar aliases `*.staging.nelsonboulangerie.com.br` — removidos em 2026-09-01, sem legado.
