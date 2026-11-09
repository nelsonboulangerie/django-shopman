# Promover um release para produção

> WP-RELEASE-01 R2. Contrato: [release-contract.md](../reference/release-contract.md);
> decisão de fundo: [ADR-043](../decisions/adr-043-build-once-promote-e-convivencia-v1-v2.md).
> Rollback por release set é a R3 e ainda não existe: até lá, vale o
> [rollback de deploy](rollback-de-deploy.md).

## O caminho

```text
push no main ──→ Deploy Images ──→ candidato imutável (<tag>-<sha>) + release-manifest
                       │
                       └──→ alpha (tags móveis) ──→ Pre-go-live Smoke verde
                                                          │
Promote Release (dispatch manual, environment production) ←┘
   1. valida ancestralidade, alpha verde e digests
   2. retag dos MESMOS manifests para <tag>-prod
   3. GitHub Deployment
   4. deployment no app de produção, ACTIVE, /health/release = commit promovido
   5. smoke de produção
```

Push no `main` nunca chega na produção: o Deploy Images só escreve a tag móvel do
alpha e a imutável, nunca `-prod`; e se o app para onde ele implanta já estiver nas
tags `-prod`, ele não cria deployment (`deploy_mode: production_pinned`).

## Promover

1. Escolha o Release ID. Está no topo do run do Deploy Images (passo `Release ID`),
   no `/health/release` do alpha e na linha "Versão do serviço" dos apps.
2. Actions → **Promote Release** → *Run workflow*, branch `main`:
   - `mode: dry-run` primeiro. Só valida e mostra, no resumo do run, a tabela
     componente → digest → tag de produção → ação. Não escreve nada.
   - `mode: promote` para valer. O job `promote` fica esperando a aprovação do
     revisor do environment `production`.
3. O run fica verde só depois do smoke de produção. Vermelho em qualquer passo para
   ali, e o GitHub Deployment fica `failure`.

O que recusa, antes de escrever qualquer coisa:

| Recusa | Por quê |
| --- | --- |
| Release ID que o git não recalcula igual, ou commit fora do `main` | só release do `main` é promovível |
| Sem `release-manifest` no run do Deploy Images | release anterior à R2, ou run que não terminou: o release set nunca foi registrado |
| Manifesto sem um dos quatro componentes, digest ilegível, `release_set_error` | o conjunto não está provado |
| `deploy_mode` fora de `single_deployment`, `deploy_on_push`, `nothing_published` | o alpha não rodou esse conjunto |
| Componente construído num commit que não é ancestral do release | mistura de linhas |
| Smoke do alpha vermelho, ou ausente depois daquele deploy | não esteve verde no alpha |
| Tag imutável que não aponta mais para o digest, manifest que não é imagem | candidato adulterado |
| Environment `production` sem revisor obrigatório ou aberto a qualquer branch | promoção sem trava (só no `dry-run` vira aviso) |

## Prova de que não há rebuild

O job que escreve faz checkout **esparso** só dos scripts da promoção (nenhum
Dockerfile chega ao runner), não tem passo de build, buildx ou docker, e o cliente de
registry (`scripts/release_manifest.py`) só lê e escreve **manifest**: lê os bytes
pelo digest, confere o sha256 e escreve os mesmos bytes sob `<tag>-prod`; depois relê
a tag e cobra o mesmo digest. Não existe caminho de upload de camada no código.
`shopman/shop/tests/test_release_promotion.py` cobra tudo isso.

## O que falta para ligar (ação do dono)

Hoje o app vivo `shopman-nelson` é o alpha e, pela D-029, será a produção. A R2
deixa a promoção pronta, mas ela só tem onde chegar depois destes passos, nesta
ordem. Nenhum agente aplica spec vivo (D-009).

### 1. Environment `production` no GitHub

Settings → Environments → **New environment** `production`:

- **Required reviewers:** você (e quem mais puder aprovar uma ida à produção);
- **Deployment branches and tags:** *Selected branches* → `main`;
- **Variables** do environment:

| Variável | Valor (D-029: o app vivo) |
| --- | --- |
| `PRODUCTION_DO_APP_NAME` | `shopman-nelson` |
| `PRODUCTION_API_URL` | `https://api.boulangerie.com.br` |
| `PRODUCTION_STOREFRONT_URL` | `https://www.nelsonboulangerie.com.br` |
| `PRODUCTION_RELEASE_URL_WEB` | `https://api.boulangerie.com.br/health/release/` |
| `PRODUCTION_RELEASE_URL_STOREFRONT` | `https://www.nelsonboulangerie.com.br/health/release` |
| `PRODUCTION_RELEASE_URL_OPERATOR_FLOOR` | `https://pdv.boulangerie.com.br/health/release` |
| `PRODUCTION_RELEASE_URL_OPERATOR_OFFICE` | `https://mkt.boulangerie.com.br/health/release` |

Sem revisor e sem a trava de branch, o `plan` recusa os modos que escrevem.

### 2. Criar as tags de produção

Promote Release com `mode: retag-only` no último release verde. Cria `web-prod`,
`storefront-prod`, `operator-floor-prod` e `operator-office-prod` apontando para os
digests do alpha, e registra o GitHub Deployment como `inactive`. Não mexe em app
nenhum. As tags precisam existir **antes** do passo 3, senão o deployment não acha a
imagem.

### 3. Proposta de spec: o app de produção nas tags `-prod`

No painel da DigitalOcean: app `shopman-nelson` → **Settings** → **App Spec** →
**Edit**. Editar o spec vivo no próprio painel preserva os segredos `EV[...]`. Trocar
**só** a `tag` dos nove componentes de imagem, nada mais:

```diff
 services:
 - name: web-operator
   image:
-    tag: web
+    tag: web-prod
 - name: web-storefront
   image:
-    tag: web
+    tag: web-prod
 - name: storefront-nuxt
   image:
-    tag: storefront
+    tag: storefront-prod
 - name: operator-floor
   image:
-    tag: operator-floor
+    tag: operator-floor-prod
 - name: operator-office
   image:
-    tag: operator-office
+    tag: operator-office-prod
 workers:
 - name: directive-worker
   image:
-    tag: web
+    tag: web-prod
 - name: maintenance-worker
   image:
-    tag: web
+    tag: web-prod
 - name: ifood-poll-worker
   image:
-    tag: web
+    tag: web-prod
 jobs:
 - name: release
   image:
-    tag: web
+    tag: web-prod
```

`deploy_on_push` fica desligado em todos (como já está). Salvar cria um deployment;
ele sobe as mesmas imagens que já estavam no ar, porque o passo 2 apontou as tags
`-prod` para os digests do alpha. Conferir `/health/release` nos quatro endereços.

No mesmo dia, um PR troca as nove tags também em `.do/app.alpha-subdomains.yaml`
(senão o `make deploy-spec-drift` acusa o vivo) e ajusta os testes que hoje cobram
o app nas tags móveis (`test_nuxt_deploy_config.py` e
`test_spec_versionado_do_app_vivo_e_alpha_hoje`).

### ⚠️ Antes do passo 3: onde fica o alpha depois

Com o passo 3 aplicado no app vivo, o push no `main` deixa de implantar nele
(`production_pinned`): o candidato continua sendo construído, mas **não há mais
alpha**, e a promoção recusa todo release que não esteve num alpha verde. Isto é
decisão sua, não mecânica:

1. **Um app alpha separado** (recomendado): um app pequeno da DO nas tags móveis,
   recebendo o push como hoje. É componente novo e tem custo mensal; precisa da sua
   palavra e de um banco próprio (alpha não escreve no banco da loja).
2. **Sem alpha**: produção recebe o candidato só com a CI. Viola a invariante 2 do
   WP-RELEASE-01 ("produção só recebe digest que esteve ativo e verde no alpha") e
   exige mudar a ADR-043.

Até essa decisão, não aplique o passo 3: o app vivo segue como alpha contínuo, e a
promoção fica pronta para o dia em que houver dois ambientes.
