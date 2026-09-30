# Deploy

Este guia descreve os dois caminhos suportados: o fluxo hospedado da
DigitalOcean App Platform e o compose self-hosted. Estado corrente e autorização
de corte ficam na
[matriz canônica](../plans/GO-LIVE-READINESS-PLAN.md), não neste guia.

## Contrato

- Aplicacao: imagem `Dockerfile` com Python 3.12, assets Tailwind compilados e
  ASGI via Daphne.
- Banco: PostgreSQL 16+.
- Cache/realtime: Redis 7+ ou Valkey Redis-compatible usando o backend nativo
  `django.core.cache.backends.redis.RedisCache`.
- Worker leve: `python manage.py process_directives --watch`.
- Release step: `check --deploy`, `migrate` e `collectstatic`.
- Estáticos: `collectstatic` roda no build da imagem; WhiteNoise serve
  `/static/` no runtime.

Nao ha `django-redis`, Celery ou broker adicional neste contrato.

## Arquivos

- `Dockerfile`: imagem da aplicacao.
- `docker-compose.yml`: Postgres/Redis por default; app, worker e release em
  profiles para nao alterar o fluxo de desenvolvimento.
- `.env.example`: variaveis base. Copie para `.env` e substitua os segredos.
- `Makefile`: wrappers `deploy-*`.
- `.do/app.alpha-subdomains.yaml`: referencia DigitalOcean App Platform de alpha
  (ingress por subdomínio), sem valores secretos. Produção: `.do/app.subdomains.yaml`.

## Fluxo hospedado atual

Na baseline de 2026-09-29, deployment de código não é exclusivamente manual:

1. merge em `main` dispara o workflow **Deploy Images**;
2. imagens alteradas são publicadas no DOCR e registradas em manifesto;
3. componentes com `deploy_on_push=true` iniciam o deployment na DigitalOcean,
   um por tag publicada (até quatro por run);
4. **Pre-go-live Smoke** espera o deployment correspondente ficar `ACTIVE` e
   verifica `/ready/`, menu, checkout não mutante e SSR.

O job `manifest` do Deploy Images já sabe o outro modo, que é UM deployment
por run: com `deploy_on_push` desligado em todos os componentes de imagem do
spec vivo, ele cria um deployment depois de publicar tudo
(`POST /v2/apps/{id}/deployments`), espera `ACTIVE` e grava o id no
manifesto, que o smoke então confere. O modo é lido do spec vivo a cada run.
Para ligar, nesta ordem: segredo `DIGITALOCEAN_APP_DEPLOY_TOKEN` (escopo
`app` read+update) no repositório, depois `deploy_on_push: false` nos oito
componentes de imagem do spec vivo, editado a partir do spec vivo.

`Deploy Images` verde prova publicação; só o smoke posterior prova que o
deployment correspondente chegou ao ambiente. Nenhum dos dois autoriza
lançamento comercial.

Mudanças de spec, secrets, ingress ou domínio não fazem parte desse fluxo. Use
o spec vivo como base e siga o runbook dedicado; nunca aplique um spec local que
apagaria valores secretos.

## Compose self-hosted

```bash
cp .env.example .env
# edite .env: DJANGO_DEBUG=false, segredo forte, hosts e tokens reais
make deploy-check
make deploy-up
```

`make deploy-up` executa:

1. build da imagem;
2. subida de PostgreSQL/Redis;
3. release one-shot (`check --deploy`, migrations e `collectstatic`);
4. subida do web ASGI e do directive worker.

Para acompanhar ou parar:

```bash
make deploy-logs
make deploy-ps
make deploy-down
```

## Variaveis minimas

Para qualquer ambiente publico:

```env
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<segredo forte>
DJANGO_ALLOWED_HOSTS=loja.example.com
CSRF_TRUSTED_ORIGINS=https://loja.example.com
DATABASE_URL=postgres://...
REDIS_URL=redis://... ou rediss://...
DOORMAN_ACCESS_LINK_API_KEY=<segredo>
EFI_WEBHOOK_TOKEN=<segredo>
IFOOD_WEBHOOK_TOKEN=<segredo>
MANYCHAT_API_TOKEN=<segredo>
MANYCHAT_WEBHOOK_SECRET=<segredo>
SHOPMAN_PIX_ADAPTER=shopman.shop.adapters.payment_efi
EFI_CLIENT_ID=<sandbox/producao>
EFI_CLIENT_SECRET=<sandbox/producao>
EFI_CERTIFICATE_PATH=<path existente no container>
EFI_PIX_KEY=<chave pix>
SHOPMAN_CARD_ADAPTER=shopman.shop.adapters.payment_stripe
STRIPE_SECRET_KEY=<sandbox/producao>
STRIPE_WEBHOOK_SECRET=<segredo webhook stripe>
```

`manage.py check --deploy` falha fechado quando esses itens obrigatorios nao
estao configurados para producao. Para staging tecnico sem credenciais sandbox
reais, use `payment_mock` apenas com `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true`;
o check registra `SHOPMAN_W006` e o ambiente nao deve ser promovido a go-live
nesse modo.

## Static e Media

`collectstatic` grava em `STATIC_ROOT` (`/app/staticfiles` no container) durante
o build da imagem. WhiteNoise serve `/static/` no runtime; CDN/reverse proxy
pode ser adicionado depois, mas nao é requisito para App Platform.

`MEDIA_ROOT` permanece em `/app/media` no container local. Em App Platform esse
filesystem é efêmero; piloto publico com uploads reais precisa de storage
externo persistente, como DigitalOcean Spaces/S3-compatible.

## Gates

Antes de abrir trafego:

```bash
make deploy-check
make test-runtime
make canonical-docs
```

No PR, o workflow `Runtime Gate` builda a imagem Docker e executa PostgreSQL +
Redis reais no GitHub Actions, entao esse gate nao depende de Docker instalado
na maquina local.

### Marketing permanece fechado até o canário

O componente `marketing-nuxt` usa `/health/live` no health check da plataforma;
`/health/ready` (BFF + Django) fica para smoke e diagnóstico. Antes de propor qualquer mudança
no spec vivo:

```bash
make marketing-docs
python manage.py export_marketing_client --check
make marketing-drills
make marketing-diagnose
```

`SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED` e
`SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED` ficam `false` até autorização
contextual de shadow/canário. São gates independentes e não substituem adapter,
prontidão, consentimento, capabilities, freeze ou reconciliação. Simulação local
jamais é configuração de staging/produção. O contrato de flags, smoke e rollback
está em
[`../reference/marketing-surface-contract.md`](../reference/marketing-surface-contract.md).

## Limites

Este compose e uma topologia minima. Em ambiente comercial,
manter os mesmos contratos, mas decidir provedor, TLS/reverse proxy,
backup/restore, logs, monitoramento de webhooks e estrategia de rollbacks.

Para DigitalOcean App Platform, use o guia dedicado:
[`deploy-digitalocean.md`](deploy-digitalocean.md).
