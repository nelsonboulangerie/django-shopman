# Verificação WP-01 — Hub

Método: cada linha citada por G e por D foi aberta e lida por inteiro (função/bloco, não a
linha). Três afirmações de comportamento foram provadas com teste executável descartável
(`scratchpad/test_probe_hub.py`, 3 passaram contra o código de hoje) — os resultados estão
marcados com **[provado]**. `git log` foi consultado em todos os arquivos citados.

---

## A. Superfície real (o que existe hoje)

**Backend (Django)**

| Arquivo | O que é |
|---|---|
| `shopman/backstage/api/hub.py` | `HubView` — `GET /api/v1/backstage/hub/`, `permission_classes = [IsBackstageOperator]` (linha 19). Devolve `{"hub": {...}}`. |
| `shopman/backstage/projections/hub.py` | Registry declarativo `_REGISTRY` (8 tiles, linhas 81-90), `HubTileProjection` (51-60), `OperatorHubProjection` (63-66), `_surface_urls()` (93-96), `build_operator_hub()` (104-119). |
| `shopman/backstage/permissions.py` | Predicados canônicos. `can_access_production` (32-41), `can_operate_production` (93-102) — os dois existem. |
| `shopman/backstage/api/permissions.py` | `IsBackstageOperator` (87-103) — staff OU conta de estação autônoma; levanta `station_locked` quando estação confiável sem operador. |
| `shopman/shop/api_errors.py` | `exception_handler` (47-61) + `_attach_permission_code` (64-80) — publica `error.code` **só** para `PermissionDenied`. |
| `config/settings.py:1294-1306` | `SHOPMAN_SURFACE_URLS` — derivado dos mesmos `SHOPMAN_*_BASE_URL` do nav do Admin. Inclui `purchase` (1303) e `loja` (1304). |
| `shopman/shop/checks.py:395-459` | `check_operator_cookie_domain` — dict em 401-408 com 6 chaves. |
| `shopman/backstage/tests/test_api_hub_surface.py` | 6 testes, verdes hoje. |
| **`shopman/backstage/admin/navigation.py:95-105`** | **Não mencionado por G nem por D:** o nav do Admin é um SEGUNDO launcher para as mesmas superfícies, e gateia "Produção ao vivo" com `_can_operate_production` (linha 102) — o predicado *certo*. |
| **`shopman/shop/services/operator_links.py`** | Não mencionado: terceiro consumidor das mesmas base URLs. Não há drift (mesma fonte). |
| **`shopman/shop/tests/test_group_permission_parity.py`** | Não mencionado: teste de paridade perm↔grupo. `GATE_FILES` (33-46) **não inclui** `projections/hub.py`. |

**Superfície (Nuxt)**

| Arquivo | O que é |
|---|---|
| `surfaces/hub-nuxt/app/app.vue` | Shell inteira (149 linhas): form de login (16-31, 50-95), `needsLogin` (41), rail, grade de tiles (127-143), empty state (117-125). |
| `surfaces/hub-nuxt/app/composables/useOperatorHub.ts` | `useFetch` da projection; expõe `error`. |
| `surfaces/hub-nuxt/app/presentation/hub.ts` | `tileIcon`, `tileTarget`, `hubIsEmpty`, `hubGreeting` — puras, testadas. |
| `surfaces/hub-nuxt/app/types/hub.ts:13` | `kind: "launch" \| "external"`. |
| `surfaces/hub-nuxt/server/api/v1/[...path].ts` | BFF: `proxyDjangoApi` da layer. |
| `surfaces/hub-nuxt/tests/{hub.test.ts, composables/useOperatorHub.test.ts}` | Vitest — rodam no CI (`surfaces-gate.yml`). |
| `surfaces/hub-nuxt/tests/e2e/{mockBackend.mjs,hub.spec.ts,resilience.spec.ts}` | Playwright — **não roda em CI nem no Makefile** (verificado: `surfaces-gate.yml` só faz `npm test` + `typecheck`; `Makefile` só tem `storefront-e2e`). |
| **`surfaces/operator-kit/nuxt.config.ts:26`** | Não mencionado: `operatorHubUrl` ← `NUXT_PUBLIC_OPERATOR_HUB_URL`, fallback `http://127.0.0.1:3001/`. O host da Central **já existe** — do lado Nuxt. |
| **`surfaces/operator-kit/app/components/OperatorRail.vue:51-74`** | Não mencionado: o botão "Central" de volta, em 7 apps. |

---

## B. Evidências dos WPs, veredito uma a uma

| # | Afirmação (G/D) | Arquivo:linha ATUAL | Veredito | Nota |
|---|---|---|---|---|
| 1 | Projection estreita (só `operator_name` + `tiles`) — G `hub.py:51,:63`; D `51-66` | `projections/hub.py:51-66` | CONFIRMADO | Li as duas dataclasses: 6 campos no tile, 2 na projection. Nada mais. |
| 2 | Hub API usa `IsBackstageOperator` — G `api/hub.py:18` | `api/hub.py:19` | CONFIRMADO | Linha 18 é o `class`; o `permission_classes` está em 19. |
| 3 | Tela trata qualquer erro como login — G `app.vue:40`; D `:41` | `app.vue:41` | CONFIRMADO | D acertou a linha. `needsLogin = Boolean(error.value) \|\| sessionExpired.value`. |
| 4 | Tipo de tile aceita `launch\|external` — G `hub.ts:12`; D `:13` | `types/hub.ts:13` | CONFIRMADO | 12 é o comentário, 13 é o campo. D acertou. |
| 5 | Mock e2e usa `kind:"config"` — G/D `mockBackend.mjs:15` | `mockBackend.mjs:15` | CONFIRMADO | Intocado desde `dd43ec382`; `0ac1872c1` mudou o contrato e deixou o mock. |
| 6 | Spec e2e também stale (`href=/admin/shop/shop/`, `target=_blank`) — D, novo | `tests/e2e/hub.spec.ts:22-23` | CONFIRMADO | Com `kind:"config"`, `tileTarget` devolve `_self`; a asserção de 23 falharia. **Mas** o Playwright não roda em CI nem no `make` — é rot dormente, não check vermelho. |
| 7 | `SHOPMAN_PURCHASE_BASE_URL` nas URLs — G `settings.py:1256,:1303`; D `1258,1303` | `settings.py:1258-1260` e `:1303` | CONFIRMADO | D acertou; G errou por 2 linhas. |
| 8 | Check de domínio omite Purchase (D: **e Hub**) — G `checks.py:401`; D `401-408` | `shop/checks.py:401-408` | CONFIRMADO | Dict com 6 chaves: POS, KDS, ORDERS, PRODUCTION, MARKETING, BI. Sem Purchase, sem Hub. |
| 9 | G: "tile Produção → usuário abre e dá 403" | — | PARCIAL | Acontece, mas só para quem tem coluna fina sem `operate_production`. **[provado]** usuário com `shop.view_production_planned` vê o tile e `can_operate_production` é `False`. |
| 10 | D: a direção é o **inverso** — quem tem `operate_production` não vê o tile | `projections/hub.py:85` | CONFIRMADO, e **pior do que D escreveu** | **[provado]** usuário com só `backstage.operate_production` recebe `tiles == []` — grade **inteira** vazia, não só "sem tile de Produção". Ele vê "Nenhum app liberado. Fale com o gerente." (`app.vue:120-123`) e ao mesmo tempo consegue abrir `prod.` direto. |
| 11 | D: `can_operate_production` já existe — a correção é trocar o predicado | `permissions.py:93-102` | CONFIRMADO | Docstring diz explicitamente "Sibling of `operate_pos`/`operate_kds`: a single surface-entry grant". |
| 12 | D: nos grupos seedados as duas perms coexistem, o bug fica mascarado | `setup_groups.py:110-119` (Cozinha), `:158,180-189` (Gerente) | CONFIRMADO | Cozinha tem `operate_production` + `manage_production`; Gerente tem `operate_production` + as 10 colunas finas. Nenhum grupo isola uma perm da outra. |
| 13 | D: zero cobertura de teste do grant customizado de Produção | `test_api_hub_surface.py` (6 testes) | CONFIRMADO | Só superuser, `manage_orders` e filtro de URL. Nada de Produção. |
| 14 | G: URLs de tiles repassadas sem validação → risco de `javascript:` | `projections/hub.py:93-96,113` | REFUTADO como risco de segurança | `_surface_urls()` lê `settings`, nunca payload de cliente. Escrever `javascript:` ali exige acesso ao spec de deploy — quem tem isso já tem o servidor. É config-drift. D acertou ao rebaixar. |
| 15 | D: rebaixar para P2 config-drift | — | CONFIRMADO | Concordo. Ver §E para a falha da proposta de D. |
| 16 | G: "incluir Hub no check de dominio" | — | PARCIAL | Como aceite é impossível hoje (não existe `SHOPMAN_HUB_BASE_URL`) — D pegou. Mas D perdeu que o valor **já existe** como `NUXT_PUBLIC_OPERATOR_HUB_URL` (`.do/app.alpha-subdomains.yaml:492`, `operator-kit/nuxt.config.ts:26`). Criar o setting Django duplica a fonte. |
| 17 | G: P2 projection com `tile.status/blocked_reason/forbidden` | `types/hub.ts:2-3` | PARCIAL | D está certo que `forbidden` contradiz "tiles já vêm FILTRADOS" e vaza nome de superfície. Mas `missing_url` **não** vaza nada (a superfície existe e o operador pode) — D jogou fora junto. |
| 18 | G: "Leve-me ao gargalo" (CTA calculado no backend) | — | REFUTADO como escopo deste WP | O próprio §Fronteira de G declara orderman/cashman/craftsman como donos externos. D acertou ao rebaixar para backlog. |
| 19 | D: "401 → re-gate de sessão (manter `useOperatorSession`)" | `config/settings.py:826-828`; `useOperatorSession.ts:23-29` | **REFUTADO** | **[provado]** o backstage **nunca** devolve 401. Ver §D-1. A receita de erro de *ambos* os agentes está errada nesse ponto. |
| 20 | D: "sem ação em `setup_groups.py`" | `setup_groups.py` inteiro | CONFIRMADO | A troca de predicado usa perm existente, já concedida a Cozinha e Gerente, já na `PARITY_TABLE:71`. |
| 21 | Ambos: main já corrigiu algo? | `git log` em hub.py / app.vue / mockBackend.mjs / checks.py | NÃO — nada corrigido | Último toque em `hub.py` foi `d7584e46c` (tile Compras); `mockBackend.mjs` intocado desde a criação. |

---

## C. Achados confirmados, com gravidade recalibrada

### C-1 — Quem opera a Produção vê a Central **vazia**. P1.

**Risco × esforço:** o padeiro é a persona de chão que mais usa o kiosk; o fix é uma
palavra numa linha. Não é P0 só porque os grupos seedados mascaram o defeito hoje — mas
qualquer grant customizado (o cenário normal quando entra gente nova) o expõe na hora.

**Mecanismo, do clique ao efeito:** o gerente cria um usuário e concede a perm que a
documentação chama de "gate do app de Produção" (`backstage.operate_production`,
`permissions.py:94-101`). O padeiro entra em `central.` → `GET /api/v1/backstage/hub/` →
`build_operator_hub` percorre `_REGISTRY`; o spec de `production` (`hub.py:85`) chama
`can_access_production`, que exige `shop.manage_production` **ou** alguma coluna fina
(`permissions.py:32-41` → `resolve_production_access(...).can_access_board`,
`projections/production.py:2358-2381`, `:330-343`). Nenhuma das duas existe → o tile cai
fora. Como ele não tem mais nenhuma perm, **a grade inteira fica vazia** e `app.vue:117`
renderiza "Nenhum app liberado — fale com o gerente". O gerente confere e o grant está lá.
A porta certa (`prod.boulangerie.com.br`, `production-nuxt/app/app.vue:10`) abre normal —
só que a Central não a mostra.

**[provado]** `tiles == []` para usuário com só `backstage.operate_production`.

**Direção inversa, mesma causa:** um usuário com `shop.view_production_planned` e sem
`operate_production` **vê** o tile e leva 403 na API (`api/operations.py:714`). **[provado]**

**Corroboração forte:** o nav do Admin — o outro launcher para o mesmo destino — já usa o
predicado certo: `navigation.py:102` → `permission=_can_operate_production`. O Hub é o
outlier, não a regra.

**Fix mínimo (uma palavra), `shopman/backstage/projections/hub.py:85`:**

```python
_AppSpec("production", "Produção", "Produção e fornadas", "croissant", "launch", can_operate_production),
```
(+ trocar o import na linha 26.) Sem migração, sem `setup_groups`, sem perm nova.

---

### C-2 — Erro de fetch vira formulário de senha. P1.

**Risco × esforço:** todo modo de falha do Hub — API caída, deploy no ar, permissão
negada, estação travada — chega ao operador como a mesma tela pedindo usuário e senha.
Ele digita, falha, digita de novo. Não há retry, não há mensagem, não há sinal de que o
problema não é ele.

**Mecanismo:** `useOperatorHub` (`useOperatorHub.ts:12-15`) usa `useFetch`; qualquer
não-2xx popula `error`. `app.vue:41` faz `needsLogin = Boolean(error.value) || …` — um
booleano para cinco causas distintas. O `v-if="needsLogin"` (`:50`) sobe o form de login.
O ramo `sessionExpired` do título (`:57`) nunca dispara (§D-1).

Casos concretos hoje:
- **500 / 502 / rede** → form de senha. O operador não sabe que a API caiu.
- **403 `station_locked`** (`api/permissions.py:87-103`) → form de **senha** num balcão
  onde a credencial é PIN/crachá. O código existe e chega no payload
  (`api_errors.py:77-79`), o Hub simplesmente não o lê.
- **anônimo / sessão expirada** → form de senha. Correto, mas por acidente.

**Fix mínimo:** classificar com os utilitários que a layer já tem
(`operator-kit/app/utils/httpError.ts:33,70,81`) — ver §D-1, que é o pré-requisito
backend de uma linha para essa classificação ser possível sem casar string em português.

---

### C-3 — `SHOPMAN_PURCHASE_BASE_URL` fora do check de domínio operacional. P2.

**Mecanismo:** `compras.` é superfície de operador e usa o mesmo cookie de sessão
`.boulangerie`. Se alguém publicá-la fora do domínio-pai, o login não a alcança e o
operador cai numa tela que pede senha a cada carregamento. `check_operator_cookie_domain`
(`checks.py:401-408`) hoje não olha para ela — o deploy passa e o defeito só aparece no
balcão.

**Fix mínimo (uma linha), em `shopman/shop/checks.py`, dentro do dict (após 407):**

```python
        "SHOPMAN_PURCHASE_BASE_URL": getattr(settings, "SHOPMAN_PURCHASE_BASE_URL", ""),
```

⚠️ **Não** estender o check para `SHOPMAN_SURFACE_URLS` inteiro, como D propôs — a chave
`loja` aponta para o apex do storefront (`settings.py:1304`), que é **deliberadamente**
fora da zona de operador. Isso reprovaria todo deploy correto. Ver §E-3.

---

### C-4 — Mock e spec e2e congelados no contrato pré-cutover. P3.

**Mecanismo:** `0ac1872c1` mudou o tile Loja de `kind:"config"`/`/admin/shop/shop/` para
`external`/storefront. `mockBackend.mjs:15` e `hub.spec.ts:22-23` ficaram no contrato
antigo. Como o Playwright do hub não roda em CI (`surfaces-gate.yml` faz só `npm test` +
`typecheck`) nem no `Makefile`, ninguém percebeu — e o dia em que alguém rodar, a suíte
recebe uma falha que não é do código.

**Gravidade P3, não P1:** não afeta operador nenhum. É higiene, e o custo é de minutos.
Corrigir mock **e** spec juntos (`kind:"external"`, `url` do storefront, `target=_blank`).

---

### C-5 — A projection não distingue "sem permissão" de "sem configuração". P2.

**Mecanismo:** `build_operator_hub` filtra por `spec.can_access(user) and urls.get(spec.ref)`
(`hub.py:117`) — as duas causas colapsam no mesmo `tiles == []`. `app.vue:120-123` chuta
sempre a mesma frase: "Sua conta ainda não tem acesso a nenhuma superfície. Fale com o
gerente." Se o deploy subiu sem `SHOPMAN_*_BASE_URL`, o gerente vai procurar permissão
que já está lá (foi exatamente esse o bug do tile Marketing no staging, citado em
`test_api_hub_surface.py:116-117`).

**Fix mínimo:** um campo escalar na projection — `empty_reason: "" | "no_permission" |
"not_configured"` — computado dentro de `build_operator_hub` comparando os specs que
passaram no predicado com os que tinham URL. **Não** adicionar estado por tile
(§E-2 explica por quê D está certo sobre isso, e onde exagerou).

⚠️ Isso quebra o contrato travado em `test_api_hub_surface.py:92`
(`set(tile) == {...}`)? Não — esse assert é sobre as chaves do **tile**; o campo novo é da
projection. O teste continua verde.

---

## D. Achados NOVOS (que G e D perderam)

### D-1 — O backstage **nunca** devolve 401; a receita de erro dos dois WPs não funciona. P1.

**[provado]** `GET /api/v1/backstage/hub/` anônimo → **403**, corpo
`{"detail": "As credenciais de autenticação não foram fornecidas."}`, **sem** `error.code`.

**Mecanismo:** `REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]` tem só
`SessionAuthentication` (`config/settings.py:826-828`). O DRF levanta `NotAuthenticated`
(status 401 na classe), e `APIView.handle_exception` rebaixa para 403 quando
`get_authenticate_header` devolve `None` — `SessionAuthentication` não sobrescreve
`authenticate_header` (verificado no pacote instalado). Resultado: **nenhum** endpoint de
operador emite 401.

**Consequências em cadeia, todas verificadas:**
1. `isUnauthenticatedError` (`httpError.ts:44-46`, `status === 401`) é **inalcançável** no
   zona de operador. `useOperatorSession.expired` nunca vira `true` por essa via.
2. No Hub, ninguém sequer chama `flagIfUnauthenticated` — grep em `surfaces/` mostra
   **um único** chamador em todo o repositório: `pos-nuxt/app/composables/usePosAction.ts:43`.
   Logo, em `hub-nuxt` `sessionExpired` é constante `false`: o ramo `"Sua sessão expirou"`
   (`app.vue:57,60`) é **código morto**, e `resetSession()` (`:25`) é no-op.
3. Portanto `needsLogin` (`:41`) reduz-se a `Boolean(error.value)` — e o comentário da
   linha 39 ("re-gate de 401") descreve algo que não acontece.
4. **A receita que G (§P1 "401: sessão expirada") e D (§P1 "401 → re-gate") prescrevem não
   tem como funcionar.** Implementar o WP como está escrito produz um `if` que nunca entra,
   e o 403 continua caindo no `else`.

**Fix mínimo, e é de uma linha — `shopman/shop/api_errors.py:59`:**

```python
    elif isinstance(exc, (exceptions.PermissionDenied, exceptions.NotAuthenticated)):
```

`_attach_permission_code` (`:64-80`) já filtra `code == "permission_denied"`;
`NotAuthenticated().detail.code` é `"not_authenticated"` (verificado), então passa e o
payload ganha `{"error": {"code": "not_authenticated"}}`. Com isso o Hub classifica sem
casar mensagem em português — que é exatamente o motivo pelo qual `STATION_LOCKED_CODE`
existe (`api/permissions.py:36-41`).

Classificação resultante no `app.vue`:
| Sinal | Tela |
|---|---|
| `error.code === "not_authenticated"` | form de usuário/senha |
| `isStationLockedError` (403 + `station_locked`) | identificação por PIN/crachá |
| 403 outro | "sem permissão" + link de voltar |
| `isTransientError` (0/502/503/504) ou 5xx | "Central indisponível" + botão Tentar de novo (`refresh()`) |

**Dono:** o fix do `api_errors.py` é do `shop` e beneficia as 7 superfícies. Vale declarar
como pré-requisito do WP-01 e avisar os WPs 02-08 (todos herdam o mesmo defeito).

---

### D-2 — O caminho de VOLTA para a Central não tem a guarda de "nunca link morto". P2.

**Mecanismo:** o Hub tem a regra explícita "superfície sem URL não vira tile"
(`hub.py:10-13`, `:117`), nascida do bug do tile Marketing (`b978bbd38`). O caminho
inverso — o botão "Central" no rail de todos os 7 apps de operador — não tem guarda
nenhuma: `operator-kit/nuxt.config.ts:26` faz
`operatorHubUrl: process.env.NUXT_PUBLIC_OPERATOR_HUB_URL || "http://127.0.0.1:3001/"`, e
`OperatorRail.vue:51-54` renderiza o `<a href>` sempre que `centralUrl` for truthy — e o
fallback garante que **sempre** é.

Se a env não estiver no spec **vivo** do app (o `.do/` do repo não deploya — memória
`reference_nuxt_public_fallback_e_assado_no_build`), o padeiro clica em "Voltar à Central
de Apps" no meio do turno e o navegador tenta `http://127.0.0.1:3001/`. Sem erro, sem
mensagem: página em branco. É o mesmo defeito de 28/08, no espelho.

**Não consegui confirmar** se a env está no spec vivo — só que ela existe no espelho
(`.do/app.alpha-subdomains.yaml:492` = `https://central.boulangerie.com.br`) e que o nome
da chave bate com `operatorHubUrl` (a regra da memória `reference_nuxt_public_env_name…`).
O defeito estrutural — fallback 127.0.0.1 que nunca vira "esconde o botão" — está provado
lendo as duas linhas.

**Fix mínimo, `surfaces/operator-kit/nuxt.config.ts:26`:**

```ts
      operatorHubUrl: process.env.NUXT_PUBLIC_OPERATOR_HUB_URL || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:3001/" : ""),
```
`OperatorRail` já degrada para `<div>` sem link quando `centralUrl` é vazio
(`OperatorRail.vue:49-51` — "sem centralUrl é identidade pura, sem atalho"). O
comportamento seguro já está implementado; só falta poder alcançá-lo.

**Dono:** `operator-kit`, não `backstage`. Colide com WP-02..WP-08 se algum deles mexer no
`nuxt.config.ts` da layer.

---

### D-3 — `projections/hub.py` está fora do inventário de gates da paridade RBAC. P3.

`test_group_permission_parity.py:33-46` lista os módulos que contêm gate de RBAC e varre
literais de permissão. `shopman/backstage/projections/hub.py` — que decide quem vê qual
app — **não está na lista**. Hoje isso é inócuo (o Hub usa predicados de
`permissions.py`, que está na lista), mas é exatamente o buraco pelo qual C-1 entrou: um
segundo lugar que decide acesso e que a rede de segurança não enxerga.

**Fix mínimo:** o teste de paridade tile↔`OPERATOR_PERM` proposto em §F-2 cobre isso
melhor do que adicionar o arquivo ao `GATE_FILES` (que só varre literais, e o Hub não tem
nenhum). Registrar como nota, não como item de trabalho separado.

---

### D-4 — Nada de PII/segredo vazando. Verificado, sem achado.

Auditei o payload (`build_operator_hub` devolve `operator_name` = nome próprio do próprio
usuário + label/description/icon/url públicos), o login (`OperatorLoginView`,
`api/operations.py:432-481` — rate-limit por username 5/min e por IP 30/min, mensagem
genérica em usuário-ou-senha inválidos, `is_staff` exigido), e o tratamento de erro
(`httpErrorMessage`, `httpError.ts:55-62`, nunca devolve a string técnica do ofetch). O
Hub não tem SSE. **Não há vazamento a reportar.** `target="_blank"` sem
`rel="noopener"` (`app.vue:130-131`) é inócuo em navegador moderno (noopener implícito) —
não vale um item.

---

## E. Achados a DESCARTAR

**E-1 — "Validar URLs de tile contra `javascript:` / XSS" (G, P1).** Refutado: as URLs vêm
de `settings.SHOPMAN_SURFACE_URLS` (`hub.py:94-96`), nunca de entrada de usuário. Não há
superfície de ataque. D já havia rebaixado; concordo com o rebaixamento e vou além — o
`javascript:` some do aceite, sobra só o check de host (C-3).

**E-2 — `tile.status` / `tile.blocked_reason` / `tile.forbidden` na projection (G, P2).**
Descartar `forbidden` e `blocked_reason`: contradizem o contrato documentado
(`types/hub.ts:2-3`, `hub.py` docstring linha 4-5: "o app que o operador não pode acessar
nem aparece") e vazariam o nome de superfícies que o operador não pode abrir. D está certo.
**Mas** D jogou fora `missing_url` junto, e esse não vaza nada — substituído pelo
`empty_reason` escalar de C-5, que resolve o problema real (o gerente não saber se é
permissão ou config) sem inventar estado por app.

**E-3 — "Validar `SHOPMAN_SURFACE_URLS` inteiro no `check --deploy`, host sob
`SHOPMAN_OPERATOR_COOKIE_DOMAIN`" (D, P2).** Descartar como escrito: a chave `loja`
(`settings.py:1304` = `SHOPMAN_STOREFRONT_BASE_URL`) é o apex da loja do cliente, que por
desenho **não** está sob o domínio de operador (é o ponto inteiro do
`OperatorSessionDomainMiddleware`, `shop/middleware.py:84-126`). Aplicar a regra ao dict
inteiro reprovaria todo deploy correto. O que sobra é C-3: uma linha, só a chave do
Purchase.

**E-4 — "Criar `SHOPMAN_HUB_BASE_URL`" (D).** Não descartar, mas **não** fazer sem decisão
do dono: o host da Central já tem uma fonte (`NUXT_PUBLIC_OPERATOR_HUB_URL`,
`operator-kit/nuxt.config.ts:26`, `.do/…:492`). Criar um setting Django paralelo é uma
segunda fonte para o mesmo fato — o oposto do "UMA fonte por superfície" que
`settings.py:1290-1293` declara. Vira pergunta em §H.

**E-5 — "Leve-me ao gargalo" (G, UX #1).** Fora de escopo por fronteira declarada pelo
próprio G. Exigiria o Hub ler orderman/cashman/craftsman/buyman.

**E-6 — "401: sessão expirada" (G §P1 e D §P1).** Descartar a formulação: não existe 401
(§D-1). Substituir por `error.code === "not_authenticated"`.

**E-7 — Teclado `1-9`, recentes por estação, handoff contextual.** Backlog de UX. Nenhum
dos dois é defeito; ambos exigem dado novo (uso por estação) ou desenho novo.

---

## F. Aceites verificáveis

| # | Aceite | Como se prova |
|---|---|---|
| F-1 | Usuário staff com **só** `backstage.operate_production` vê o tile `production` na grade. | Teste backend em `test_api_hub_surface.py`, no molde do probe já escrito: conceder a perm via `Permission.objects.get(content_type=for_model(DayClosing), codename="operate_production")`, `client.force_login`, assert `"production" in refs`. Hoje **falha** (`tiles == []`, provado). |
| F-2 | Todo tile `kind="launch"` declara a mesma permissão que o `OPERATOR_PERM` da superfície destino. | Teste de contrato Python: tabela `{ref: perm}` no teste, para cada spec do `_REGISTRY` conceder **só** aquela perm a um staff novo e assertar que o tile aparece; e conceder tudo **menos** ela e assertar que não aparece. Cobre os 7 tiles `launch` de uma vez e é a rede que faltava (§D-3). |
| F-3 | Requisição anônima a `/api/v1/backstage/hub/` devolve 403 **com** `error.code == "not_authenticated"`. | Assert-negativo de payload: `assert r.json()["error"]["code"] == "not_authenticated"`. Hoje **falha** (`error` ausente, provado). |
| F-4 | 403 `station_locked` no Hub não renderiza o form de usuário/senha. | Teste Vue (vitest, roda no `surfaces-gate`): montar a shell com `error` = `{status:403, data:{error:{code:"station_locked"}}}` e assertar que o input `[aria-label="Senha"]` **não** existe. |
| F-5 | 500 e erro de rede renderizam estado "indisponível" com ação de retry, nunca o form de senha. | Mesmo teste Vue, `{status:500}` e `{status:0}`; assert-negativo em `[aria-label="Senha"]` + assert positivo no botão de retry. |
| F-6 | `manage.py check --deploy` reprova quando `SHOPMAN_PURCHASE_BASE_URL` está fora de `SHOPMAN_OPERATOR_COOKIE_DOMAIN`. | Teste backend com `override_settings` no molde dos testes existentes de `SHOPMAN_E014`; assert `"SHOPMAN_PURCHASE_BASE_URL" in str(errors)`. |
| F-7 | O mesmo check **não** reprova por causa do storefront apex. | Assert-negativo: com `SHOPMAN_STOREFRONT_BASE_URL="https://nelsonboulangerie.com.br"` e cookie domain `.boulangerie.com.br`, `check --deploy` volta sem erro. Guarda contra a regressão de E-3. |
| F-8 | Grade vazia por falta de permissão e grade vazia por falta de URL produzem `empty_reason` distintos. | Dois testes backend com `override_settings(SHOPMAN_SURFACE_URLS={})` vs. staff sem perms; assert nos dois valores. |
| F-9 | O contrato do tile não ganhou campos. | `test_api_hub_surface.py:92` já existe e deve continuar verde: `set(tile) == {"ref","label","description","icon","url","kind"}`. |
| F-10 | Mock e spec e2e concordam com o contrato atual. | `npx playwright test` em `surfaces/hub-nuxt` passa. ⚠️ **Não roda em CI hoje** — o aceite exige rodar à mão, ou wirar o e2e no `surfaces-gate.yml` (decisão de escopo, ver §H-3). |

Aceites deliberadamente **fora** da lista por dependerem de infra que não existe:
"Hub entra na matriz de host/cookie" (sem `SHOPMAN_HUB_BASE_URL` não há o que checar) e
qualquer coisa sobre gargalo cross-app.

---

## G. Fronteiras e colisões

### Arquivos que este WP toca (lista exata)

**Backend — `backstage`:**
- `shopman/backstage/projections/hub.py` — linha 26 (import) e 85 (predicado); `build_operator_hub` + `OperatorHubProjection` para o `empty_reason` (C-5).
- `shopman/backstage/tests/test_api_hub_surface.py` — testes F-1, F-2, F-3, F-8.

**Backend — `shop` (fora do `backstage`; risco de colisão real):**
- `shopman/shop/api_errors.py` — **linha 59** (D-1). Arquivo compartilhado por storefront + backstage; qualquer WP que mexa em dialeto de erro colide aqui.
- `shopman/shop/checks.py` — dentro do dict em 401-408 (C-3). O `WP-06 Compras` provavelmente quer tocar o mesmo dict.
- Teste de check (F-6, F-7) — localizar o arquivo existente de `SHOPMAN_E014` antes de criar um novo.

**Superfície — `hub-nuxt`:**
- `surfaces/hub-nuxt/app/app.vue` — bloco 33-41 e o `v-if` de 50; blocos novos de estado de erro.
- `surfaces/hub-nuxt/app/presentation/hub.ts` — função pura de classificação (para testar sem montar componente).
- `surfaces/hub-nuxt/tests/hub.test.ts` — F-4, F-5.
- `surfaces/hub-nuxt/tests/e2e/mockBackend.mjs` + `tests/e2e/hub.spec.ts` — C-4, **juntos**.

**Superfície — `operator-kit` (colisão alta: 7 apps herdam):**
- `surfaces/operator-kit/nuxt.config.ts` — linha 26 (D-2). **Todo** WP de superfície pode querer esse arquivo.
- ⚠️ **Não tocar** `surfaces/operator-kit/app/utils/httpError.ts`: as funções necessárias
  (`isTransientError`, `httpErrorCode`, `isStationLockedError`) já existem e estão corretas.
  Se algum WP quiser "consertar" `isUnauthenticatedError` para aceitar 403, **recusar** — a
  correção é no backend (D-1), não em afrouxar o narrowing do front.

### Permissões novas e impacto em `setup_groups.py`

**Nenhuma.** Li `shopman/shop/management/commands/setup_groups.py` inteiro:
`backstage.operate_production` já existe (`models/closing.py:34`, migração
`0005_alter_dayclosing_options.py`), já é concedida a **Cozinha** (`:114`) e **Gerente**
(`:158`), e já está travada na `PARITY_TABLE` (`test_group_permission_parity.py:71`).
A troca de predicado de C-1 **reduz** o conjunto de quem vê o tile em produção? Não: nos
dois grupos seedados as duas perms coexistem, então nada muda para quem está no ar hoje —
o que muda é o comportamento para grants customizados. **Sem migração, sem `setup_groups`,
sem risco de regressão de acesso no alpha.**

Se algum dia entrar o tile "Produção — relatórios" que G sugeriu, aí sim:
`backstage.view_production_reports` existe mas **nenhum grupo a concede** —
deliberadamente, com justificativa escrita em `test_group_permission_parity.py:105-114`.
Isso é WP próprio.

### O que pertence a outro app/dono

| Item | Dono |
|---|---|
| D-1 (`api_errors.py`) | `shop`. Beneficia 7 superfícies; se este WP não fizer, WP-02..WP-08 herdam o mesmo defeito. Coordenar. |
| D-2 (`operator-kit/nuxt.config.ts`) | `operator-kit`. |
| C-3 e o eventual `SHOPMAN_HUB_BASE_URL` | `config/settings.py` + `shop/checks.py` — infra/deploy, não backstage. |
| Qualquer resumo operacional por app (gargalo, badge, contagem) | O app dono. O Hub lista o que recebe; não agrega. D está certo e G está errado aqui. |
| Wirar o Playwright do hub no CI | Dono do `surfaces-gate.yml` — decisão de plataforma, não do WP. |

---

## H. Perguntas abertas para o dono do produto

1. **O host da Central deve virar setting do Django?** Hoje ele existe só como
   `NUXT_PUBLIC_OPERATOR_HUB_URL` (`operator-kit/nuxt.config.ts:26`). Criar
   `SHOPMAN_HUB_BASE_URL` permite incluir a Central no `check_operator_cookie_domain`, mas
   cria uma segunda fonte para o mesmo fato — contra a regra "UMA fonte por superfície"
   que o próprio `settings.py:1290-1293` declara. Vale a duplicação pelo check, ou o check
   da Central fica de fora?

2. **O tile "Loja online" deve continuar exclusivo de superusuário?** `hub.py:89` usa
   `is_superuser`, então o **Gerente** não vê o atalho para a loja do cliente na Central —
   embora a loja seja pública e ele administre o catálogo dela. Está travado por teste
   (`test_api_hub_surface.py:108`: "loja só p/ superuser"), então parece deliberado, mas
   não achei ADR nem comentário justificando. É decisão ou herança?

3. **O e2e do Hub deve entrar no CI?** Hoje o Playwright de `hub-nuxt` não roda em lugar
   nenhum (`surfaces-gate.yml` só faz `npm test` + `typecheck`; `Makefile` só tem
   `storefront-e2e`). Consertar mock+spec (C-4) sem wirar no CI é consertar algo que vai
   apodrecer de novo — o mock ficou 100% stale desde `0ac1872c1` sem ninguém notar. Vale o
   custo de runner, ou apagamos o e2e do Hub e assumimos vitest + revisão local?
