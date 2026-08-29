# WP-01-agente-c — Hub / Central de Apps

**Status:** pronto para implementação · **Autor:** Agente C (terceira leitura, 2026-08-29)
**Superfície:** `surfaces/hub-nuxt` + `shopman/backstage/projections/hub.py` + `shopman/backstage/api/hub.py`
**Objetivo:** a Central mostra exatamente os apps que o operador pode abrir, e quando não mostra nada, diz por quê — em vez de pedir a senha dele.

## Diferenças vs. WP-01 (Agente G) e WP-01-agente-d

**Mantidos, verificados:** o tile de Produção usa o predicado errado; a Central colapsa
todo modo de falha num formulário de login; mock e spec e2e congelados no contrato
pré-cutover; `SHOPMAN_PURCHASE_BASE_URL` fora do check de domínio operacional.

**Agravado:** o Agente D acertou a direção do bug do tile de Produção e subestimou o
efeito. Não é "o tile some": um usuário com **só** `backstage.operate_production` — a
permissão que o próprio app de Produção exige — recebe `tiles == []` e a mensagem
"Nenhum app liberado, fale com o gerente", enquanto consegue abrir `prod.` digitando a
URL. Provado com teste executável contra o código de hoje.

**Refutados (não entram):**
- **"Validar `javascript:` nas URLs de tile" (G, P1).** As URLs vêm de
  `settings.SHOPMAN_SURFACE_URLS` (`hub.py:94-96`), nunca de entrada de usuário. Não há
  superfície de ataque.
- **"Validar `SHOPMAN_SURFACE_URLS` inteiro contra o cookie domain" (D, P2).** Como
  escrito, **reprovaria todo deploy correto**: a chave `loja` é o apex do storefront
  (`settings.py:1304`), deliberadamente fora da zona de operador — é o ponto inteiro do
  `OperatorSessionDomainMiddleware`. Sobra uma linha: só a chave do Purchase.
- **"Leve-me ao gargalo" (G, UX #1).** Fura a fronteira que o próprio G declarou: exigiria
  o Hub ler orderman, cashman, craftsman e buyman. O Hub lista o que recebe; não agrega.
- **"401 → sessão expirada" (G e D).** Não existe 401 nesta zona. Ver WP-00 Bloco E; a
  receita é substituída por `error.code === "not_authenticated"`.
- **`tile.forbidden` / `tile.blocked_reason` (G, P2).** Contradizem o contrato documentado
  ("o app que o operador não pode acessar nem aparece", `hub.py` docstring) e vazariam o
  nome de superfícies que ele não pode abrir. D estava certo — mas jogou fora o
  `missing_url` junto, e esse não vaza nada: volta como `empty_reason` escalar (P2-3).

**Novos (verificados nesta leitura):** o backstage nunca devolve 401 (promovido ao
WP-00, porque atinge as sete superfícies); o caminho de **volta** para a Central não tem
a guarda de "nunca link morto" que o Hub tem na ida; `projections/hub.py` está fora do
inventário de gates da paridade RBAC — que é o buraco pelo qual o bug do tile entrou.

**Correções de citação:** o Agente G errou 3 das 7 linhas que citou (`app.vue:40`→41,
`hub.ts:12`→13, `settings:1256`→1258). O Agente D acertou todas. Nada foi corrigido no
main desde então.

## Pré-requisitos

- **WP-00 Bloco E** (`api_errors.py`, uma linha): sem ele, os aceites P1-2 e P1-3 deste WP
  são inverificáveis, porque o front não tem como distinguir as causas do 403.
- Nada mais. Este WP não cria permissão, não cria modelo e não gera migração.

## Fronteira natural

A Central lista superfícies e leva a elas. Não agrega estado operacional de outro app —
cada app expõe o próprio resumo se quiser um. Não decide permissão: lê o mesmo predicado
que a superfície de destino usa para deixar entrar. Não é tela de configuração.

## Evidências (verificadas nesta leitura)

- Predicado errado do tile: `shopman/backstage/projections/hub.py:85` usa
  `can_access_production`; a API de Produção exige `operate_production`
  (`shopman/backstage/api/operations.py:714`).
- O nav do Admin — o **outro** launcher para o mesmo destino — já usa o predicado certo:
  `shopman/backstage/admin/navigation.py:102` → `_can_operate_production`. O Hub é o
  outlier, não a regra.
- Predicados: `shopman/backstage/api/permissions.py:32-41` (`can_access_production`) e
  `:94-101` (`can_operate_production`).
- Filtro que colapsa as duas causas de grade vazia:
  `shopman/backstage/projections/hub.py:117` (`spec.can_access(user) and urls.get(spec.ref)`).
- Erro vira login: `surfaces/hub-nuxt/app/composables/useOperatorHub.ts:12-15` +
  `surfaces/hub-nuxt/app/app.vue:41` (`needsLogin = Boolean(error.value) || …`) e `:50`.
- Ramo de sessão expirada morto: `app.vue:57,60`; único chamador de
  `flagIfUnauthenticated` em todo o `surfaces/` é
  `pos-nuxt/app/composables/usePosAction.ts:43`.
- Check de domínio sem a chave do Purchase: `shopman/shop/checks.py:401-408`.
- Fallback de link morto no caminho de volta:
  `surfaces/operator-kit/nuxt.config.ts:26` (`|| "http://127.0.0.1:3001/"`);
  `surfaces/operator-kit/app/components/OperatorRail.vue:49-54` já degrada para `<div>`
  sem link quando a URL é vazia — o comportamento seguro existe, só é inalcançável.
- Mock/spec stale desde `0ac1872c1`: `surfaces/hub-nuxt/tests/e2e/mockBackend.mjs:15`,
  `tests/e2e/hub.spec.ts:22-23`.
- `shopman/backstage/projections/hub.py` ausente do `GATE_FILES` de
  `tests/test_group_permission_parity.py:33-46`.

## Achados priorizados

### P1-1 — Quem opera a Produção vê a Central vazia

**Mecanismo, do clique ao efeito.** O gerente cria um usuário e concede
`backstage.operate_production`, que é o gate do app de Produção. O padeiro abre
`central.` → `GET /api/v1/backstage/hub/` → `build_operator_hub` percorre o registro; o
spec de `production` chama `can_access_production`, que exige `shop.manage_production`
**ou** alguma permissão de coluna fina. O grant não é nenhuma das duas → o tile cai fora.
Como ele não tem outra permissão, a grade inteira fica vazia e a tela diz "Nenhum app
liberado — fale com o gerente". O gerente confere, e o grant está lá. A porta certa
(`prod.boulangerie.com.br`) abre normalmente — só a Central não a mostra.

A direção inversa também está errada: quem tem `shop.view_production_planned` e não tem
`operate_production` **vê** o tile e leva 403 ao clicar.

**Fix mínimo — uma palavra**, em `shopman/backstage/projections/hub.py:85` (mais o import
na linha 26):

```python
_AppSpec("production", "Produção", "Produção e fornadas", "croissant", "launch", can_operate_production),
```

**Risco×esforço:** uma palavra, sem migração, sem permissão nova. Não é P0 porque os dois
grupos seedados (Cozinha e Gerente) têm as duas permissões, então ninguém no ar hoje é
afetado — mas qualquer grant customizado, que é o caso normal quando entra gente nova,
cai nele na hora.

### P1-2 — Erro de fetch vira formulário de senha

**Mecanismo.** `useOperatorHub` usa `useFetch`; qualquer não-2xx popula `error`, e
`app.vue:41` reduz cinco causas distintas a um booleano que sobe o formulário de login.
Hoje, no balcão: API fora do ar → formulário de senha; deploy em andamento → formulário
de senha; **403 `station_locked`** → formulário de **senha**, num balcão onde a
credencial é PIN ou crachá. O código da recusa existe e chega no payload; a Central
simplesmente não o lê.

**Fix.** Classificar com os utilitários que a layer já tem (`httpError.ts`), numa função
pura em `presentation/hub.ts` para poder testar sem montar componente:

| Sinal | Tela |
|---|---|
| `error.code === "not_authenticated"` | formulário de usuário/senha |
| `isStationLockedError` (403 + `station_locked`) | identificação por PIN/crachá |
| 403 sem código | "sem permissão" + caminho de volta |
| `isTransientError` (0/502/503/504) ou 5xx | "Central indisponível" + botão Tentar de novo |

⚠️ **Não** afrouxar `isUnauthenticatedError` para aceitar 403. Isso transformaria toda
negativa de permissão em "sessão expirada" e mandaria o operador digitar senha para um
problema que senha não resolve. A correção é no servidor (WP-00 Bloco E).

### P2-3 — A projection não distingue "sem permissão" de "sem configuração"

**Mecanismo.** O filtro `spec.can_access(user) and urls.get(spec.ref)` colapsa as duas
causas no mesmo `tiles == []`, e a tela sempre acusa permissão. Se o deploy subiu sem
`SHOPMAN_*_BASE_URL`, o gerente vai procurar uma permissão que já está lá — foi
exatamente o bug do tile de Marketing no staging, registrado em
`test_api_hub_surface.py:116-117`.

**Fix.** Um campo escalar **na projection**, não por tile:
`empty_reason: "" | "no_permission" | "not_configured"`, computado dentro de
`build_operator_hub` comparando os specs que passaram no predicado com os que tinham URL.
Não vaza nome de superfície e não quebra o contrato do tile — o assert de
`test_api_hub_surface.py:92` é sobre as chaves do tile, que não mudam.

### P2-4 — O caminho de volta não tem a guarda de "nunca link morto"

**Mecanismo.** O Hub tem a regra explícita "superfície sem URL não vira tile", nascida do
bug do tile de Marketing. O caminho inverso — o botão "Central" no rail dos sete apps de
operador — não tem guarda: o `nuxt.config.ts` da layer cai em `http://127.0.0.1:3001/`
quando a env falta. Se a variável não estiver no spec **vivo** (o `.do/` do repositório
não deploya), o padeiro clica em "Voltar à Central" no meio do turno e o navegador tenta
o localhost do laptop de alguém. Sem erro, sem mensagem: página em branco. É o mesmo
defeito de 28/08, no espelho.

**Fix mínimo**, `surfaces/operator-kit/nuxt.config.ts:26`:

```ts
operatorHubUrl: process.env.NUXT_PUBLIC_OPERATOR_HUB_URL || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:3001/" : ""),
```

O `OperatorRail` já degrada para identidade sem link quando a URL é vazia. O
comportamento seguro está implementado; falta poder alcançá-lo.

⚠️ **Colisão alta:** este arquivo é herdado pelos sete apps. Ver WP-00 Bloco D.

### P2-5 — `SHOPMAN_PURCHASE_BASE_URL` fora do check de domínio operacional

`compras.` é superfície de operador e usa o mesmo cookie `.boulangerie`. Publicada fora
do domínio-pai, o login não a alcança e o operador cai numa tela que pede senha a cada
carregamento — e o deploy passa. **Fix:** uma linha no dict de `shopman/shop/checks.py`
(após 407). **Só** essa chave.

### P3-6 — Mock e spec e2e congelados

O commit `0ac1872c1` mudou o tile da Loja de `kind:"config"` para `external`. Mock e spec
ficaram no contrato antigo, e como o Playwright do Hub **não roda em lugar nenhum**
(nem `surfaces-gate.yml`, nem `Makefile`), ninguém percebeu. Corrigir os dois juntos —
mas ver a pergunta 3 abaixo: consertar sem wirar no CI é consertar algo que apodrece de novo.

## Verificado sem achado

Não há vazamento de PII nem de segredo nesta superfície. O payload devolve o nome do
próprio usuário e metadados públicos de tile; o login tem rate-limit por username (5/min)
e por IP (30/min), mensagem genérica e exigência de `is_staff`; o tratamento de erro
nunca devolve a string técnica do ofetch. O Hub não tem SSE. `target="_blank"` sem
`rel="noopener"` é inócuo em navegador moderno e não vale um item de trabalho.

## RBAC / `setup_groups`

**Nenhuma permissão nova. Nenhuma migração.** `backstage.operate_production` já existe,
já é concedida a Cozinha e a Gerente, e já está travada na tabela de paridade. Como os
dois grupos seedados têm as duas permissões, a troca de predicado do P1-1 **não altera o
acesso de ninguém que esteja no ar hoje** — muda o comportamento para grants
customizados, que é o ponto.

Nota de dívida, para WP próprio: `backstage.view_production_reports` existe e **nenhum
grupo a concede**, deliberadamente e com justificativa escrita no teste de paridade. Se
alguém quiser o tile "Produção — relatórios" que o Agente G sugeriu, começa por aí.

## Testes

| # | Aceite | Prova |
|---|---|---|
| 1 | Staff com **só** `backstage.operate_production` vê o tile `production`. | Backend, `test_api_hub_surface.py`. **Hoje falha** (`tiles == []`). |
| 2 | Todo tile `kind="launch"` declara a mesma permissão que a superfície de destino exige. | Contrato: tabela `{ref: perm}` no teste; para cada spec, conceder só aquela permissão e assertar que o tile aparece; conceder tudo menos ela e assertar que não. Cobre os sete tiles e é a rede que faltava. |
| 3 | Anônimo recebe 403 **com** `error.code == "not_authenticated"`. | Assert de payload. **Hoje falha.** Depende do WP-00 Bloco E. |
| 4 | 403 `station_locked` não renderiza o formulário de senha. | Vitest sobre a função pura de classificação; assert-negativo no campo de senha. |
| 5 | 500 e erro de rede renderizam "indisponível" com retry, nunca o formulário de senha. | Idem, com `{status:500}` e `{status:0}`. |
| 6 | `check --deploy` reprova `SHOPMAN_PURCHASE_BASE_URL` fora do cookie domain. | Backend, no molde dos testes de `SHOPMAN_E014`. |
| 7 | O mesmo check **não** reprova por causa do apex do storefront. | Assert-negativo. Guarda contra a regressão que a proposta do Agente D teria introduzido. |
| 8 | Grade vazia por permissão e por configuração produzem `empty_reason` distintos. | Dois testes backend. |
| 9 | O contrato do tile não ganhou campos. | `test_api_hub_surface.py:92` continua verde. |

## Arquivos tocados (para a matriz de colisão)

| Arquivo | Dono | Colide com |
|---|---|---|
| `shopman/backstage/projections/hub.py` | backstage | — |
| `shopman/backstage/tests/test_api_hub_surface.py` | backstage | — |
| `shopman/shop/api_errors.py` (1 linha) | **shop** | **WP-00 Bloco E — fazer lá, não aqui** |
| `shopman/shop/checks.py` (1 linha) | shop | WP-06 (mesmo dict) |
| `surfaces/hub-nuxt/app/app.vue`, `presentation/hub.ts`, `tests/` | hub-nuxt | — |
| `surfaces/hub-nuxt/tests/e2e/{mockBackend.mjs,hub.spec.ts}` | hub-nuxt | — |
| `surfaces/operator-kit/nuxt.config.ts` (1 linha) | **operator-kit** | **WP-02 a WP-08 (herdam a layer)** |

⚠️ **Não tocar** `surfaces/operator-kit/app/utils/httpError.ts`: as funções necessárias já
existem e estão corretas.

## Fora de escopo

Agregação de estado de outros apps (gargalo, contagens, badges), configuração no Hub,
qualquer permissão nova, atalho de teclado e "recentes por estação" (backlog de UX, não
defeito), e wirar o Playwright no CI (decisão de plataforma — ver pergunta 3).

## Perguntas para o dono do produto

1. **O host da Central deve virar setting do Django?** Hoje ele existe só como
   `NUXT_PUBLIC_OPERATOR_HUB_URL`. Criar `SHOPMAN_HUB_BASE_URL` permitiria incluir a
   Central no check de domínio, mas cria uma segunda fonte para o mesmo fato — contra a
   regra "uma fonte por superfície" que o próprio `settings.py` declara. Vale a duplicação?
2. **O tile "Loja online" continua exclusivo de superusuário?** O Gerente não vê o atalho
   para a loja do cliente, embora a loja seja pública e ele administre o catálogo dela.
   Está travado por teste, então parece deliberado, mas não há ADR nem comentário
   justificando. É decisão ou herança?
3. **O e2e do Hub entra no CI ou é apagado?** Ele não roda em lugar nenhum hoje, e foi por
   isso que o mock ficou totalmente stale sem ninguém notar. Consertar sem wirar é
   consertar algo que apodrece de novo.

## Prompt para agente executor

~~~text
Execute WP-01-agente-c (Hub / Central de Apps).

Pre-requisito: WP-00 Bloco E (shopman/shop/api_errors.py, uma linha) precisa estar no
main antes dos aceites 3, 4 e 5. Sem ele o front nao distingue as causas do 403.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-01-agente-c-hub.md
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-00-agente-c-transversal.md (Bloco E)
- shopman/backstage/projections/hub.py
- shopman/backstage/api/permissions.py (can_access_production x can_operate_production)
- shopman/backstage/admin/navigation.py:102 (o predicado certo, ja em uso no outro launcher)
- shopman/backstage/tests/test_api_hub_surface.py
- surfaces/hub-nuxt/app/app.vue + app/composables/useOperatorHub.ts
- surfaces/operator-kit/app/utils/httpError.ts (LER, nao alterar)
- surfaces/operator-kit/nuxt.config.ts:26
- shopman/shop/checks.py:401-408

Fases:
1. P1-1: trocar can_access_production por can_operate_production (linha 85 + import 26).
   Escrever o teste 1 ANTES; ele deve falhar contra o codigo atual.
2. Teste 2 (paridade tile-permissao dos 7 tiles launch) — a rede que faltava.
3. P1-2: funcao pura de classificacao de erro em presentation/hub.ts + vitest (4, 5).
4. P2-3: empty_reason escalar na projection (8).
5. P2-5: uma linha em checks.py + testes 6 e 7. So a chave do Purchase.
6. P2-4: nuxt.config.ts da operator-kit. ⚠️ arquivo herdado por 7 apps — confirmar que
   nenhum outro WP esta com ele aberto antes de tocar.
7. P3-6: mock + spec e2e juntos.

NAO adicione campo por tile na projection. NAO afrouxe isUnauthenticatedError.
NAO estenda o check de dominio ao SHOPMAN_SURFACE_URLS inteiro (reprova deploy correto).
NAO faca o Hub agregar estado de outro app.
~~~
