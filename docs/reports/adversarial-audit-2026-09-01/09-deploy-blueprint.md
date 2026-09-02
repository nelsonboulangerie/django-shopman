# 09 — Production deployment blueprint (audited by lead)

The thesis: **`.do/app.subdomains.yaml` no longer describes the product it is supposed to
deploy.** It is the only committed artifact that says what production *is*, and it has drifted
from reality on four independent axes. None of this is caught by any test — infrastructure
blueprints are not in the suite.

## P1

### D-1. The production blueprint clones from the wrong GitHub organisation
- `.do/app.subdomains.yaml:211,248,281,315,330,349,366` — all seven components declare
  `repo_clone_url: https://github.com/pablondrina/django-shopman.git`
- Actual origin: `git@github.com:nelsonboulangerie/django-shopman.git`

An app created from this template builds from a personal account's copy, not the house repo —
either failing to clone, or (worse) succeeding against a stale mirror and shipping code nobody
reviewed. The alpha spec has no clone URLs at all (it deploys DOCR images), so this error
exists only on the production path and has therefore never been exercised.

### D-2. The production blueprint is missing 7 of the 10 surfaces
- prod declares: `web`, `storefront-nuxt`, `pos-nuxt` (+3 workers, +release)
  — `.do/app.subdomains.yaml:209,246,279,313,328,347,363`
- alpha declares: `web`, `storefront-nuxt`, `pos-nuxt`, `kds-nuxt`, `orders-nuxt`,
  `production-nuxt`, `purchase-nuxt`, `hub-nuxt`, `marketing-nuxt`, `bi-nuxt`
  — `.do/app.alpha-subdomains.yaml:408-778`

Deploying production from this blueprint yields a bakery with **no kitchen display, no order
manager, no production kiosk, no purchasing, no operator hub, no marketing, and no B.I.** The
header comment still describes the old four-host topology (`STORE_DOMAIN`, `api.`, `admin.`,
`pdv.`), which is the system as it was, not as it is.

### D-3. Production observability is roughly a third of the alpha's
- health_check blocks: prod 4 vs alpha 11 · alerts blocks: prod 7 vs alpha 14

Partly a consequence of D-2, but not entirely: the alpha carries CPU/memory/restart alerts and
both `/ready/` and `/health/` probes per service. Production is the environment where nobody is
watching the logs, so it is the one that most needs the alerts — and it has fewer.

## Retirado — D-4 era leitura minha, não defeito

Eu havia registrado como P2 que o blueprint de produção "não passa no próprio gate":
`SHOPMAN_ENVIRONMENT=production` + `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=false` +
`SHOPMAN_PIX_ADAPTER/SHOPMAN_CARD_ADAPTER=payment_mock` faz o `check --deploy` do job
`PRE_DEPLOY` reprovar, e o deploy não sobe.

Isso é **deliberado**, e está escrito no próprio arquivo
(`.do/app.subdomains.yaml:281-283`): *"o deploy-check SHOPMAN_E003 FALHA o PRE_DEPLOY de
propósito — forçando a troca por adapters reais antes de subir"*. É a filosofia fail-closed da
casa aplicada ao blueprint: o template **recusa-se a subir** até alguém escolher
conscientemente o gateway. A trava seguinte (`SHOPMAN_MOCK_PIX_AUTO_CONFIRM=false`) é descrita
como pré-armada para o dia em que alguém desligar a primeira sob pressão — o que é justamente
o raciocínio certo.

Registrado aqui em vez de apagado porque a lição é minha: li o valor antes de ler o comentário
ao lado dele. Nenhuma alteração foi feita no bloco de pagamentos.

## Verified-safe
- `manage.py check --deploy` really is wired as a `PRE_DEPLOY` job in both specs, so the
  deploy-time checks are not decorative — they gate the release. This is the mechanism that
  turns D-4 from a money bug into a deploy failure.
- Production spec correctly sets `SHOPMAN_ENVIRONMENT=production`,
  `SHOPMAN_EXPOSE_DEBUG_OTP=false`, `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=false`,
  `SHOPMAN_MOCK_PIX_AUTO_CONFIRM=false` — the four flags that matter most are right.
- Secrets are correctly absent from both committed specs (they belong in the DO panel); the
  106-vs-29 key gap is mostly this, by design, not an omission.
