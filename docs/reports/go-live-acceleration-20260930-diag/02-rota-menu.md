# 02 — A rota `/menu`: página real do cardápio ou resquício de teste?

**Pergunta do dono:** *"a url `/menu` foi usada para testar algo, confere? Ela ainda é necessária?"*

**Árvore:** `.dsh-worktrees/go-live-acceleration` (branch `dsh/handoff-onda1-e-p7-20260930`, 3 commits à frente de `origin/main`).
**Método:** leitura estática + `git log`/`grep` + sondagens HTTP **de leitura** (`curl -o /dev/null`) contra o host público, em 01/10/2026 ~00:04 UTC. Nada foi editado além deste arquivo.
**Legenda:** [FATO] verificado no código/saída de comando · [INFERÊNCIA] dedução minha · [NÃO VERIFICADO] não consegui confirmar.

---

## 0. Resposta curta

**Não, `/menu` não é resquício de teste. É a página real do cardápio, e removê-la quebra o site.**

1. **É uma das quatro páginas fundadoras do storefront Nuxt.** [FATO] O commit `3c3cdddbd` (*"feat: add Nuxt storefront surface"*, 2026-05-07) criou exatamente `index.vue`, `menu.vue`, `cart.vue` e `produto/[sku].vue`. `menu.vue` não veio depois: nasceu com a superfície.
2. **O dono já decidiu mantê-la, com o nome atual.** [FATO] `docs/plans/completed/URL-STANDARDIZATION-PLAN.md:3`: *"✅ EXECUTADO (2026-06-20, commit `fb82dfb3`). **Decisões do Pablo: `/menu` mantido**; `/cart`→`/sacola` e `/checkout`→`/finalizar`."* A alternativa (`/cardapio`) foi descartada — e de fato `/cardapio` **dá 404** hoje.
3. **Ela está no ar e é indexada.** [FATO] `GET https://www.nelsonboulangerie.com.br/menu` → `HTTP/2 200`, `x-powered-by: Nuxt`. O `sitemap.xml` público lista `/menu` com `priority 0.9` (só a home tem 1.0).
4. **Onde o dono provavelmente viu "usada para testar":** o **piloto do Continuum** foi ligado 100 % em cima de `/menu` (`02b4f1487`, 28/09) — o relatório irmão se chama *"03 — Continuum no `/menu`"*. E o endpoint `/api/v1/storefront/menu/` é o que aparece em **toda** medição de performance do `GO-LIVE-ACCELERATION-PLAN`. Nenhum dos dois faz de `/menu` uma página de teste.

**A confusão que precisa ser desfeita — são TRÊS coisas chamadas "menu":**

| # | O que é | Endereço | Natureza | Destino |
|---|---|---|---|---|
| **1** | **Página do cardápio da loja** (Nuxt/SSR) | `/menu` no site | Pública, indexada, com preço | **Fica. É o cardápio.** |
| **2** | **Endpoint Django privado** (catálogo + sacola) | `/api/v1/storefront/menu/` | API JSON, `cache-control: private` | **Fica.** ~2,6–3,3 s, é o alvo da Onda 1 |
| **3** | **Host legado** `menu.nelsonboulangerie.com.br` | subdomínio | App `nb-catalog-app` (fora deste repo) | Já decidido: vai para o site após o go-live |

A nº 3 é a mais traiçoeira: [FATO] `curl -L https://menu.nelsonboulangerie.com.br/menu` devolve `200` mas a URL efetiva é `https://menu.nelsonboulangerie.com.br/` — é o **cardápio antigo**, não a nossa página. Confirmado em `.do/app.alpha-subdomains.yaml:8-11`: *"O `menu.` voltou para o cardápio antigo (app `nb-catalog-app`), porque é para lá que os links divulgados apontam; depois do go-live ele também vem para o site."*

---

## 1. O que a rota `/menu` faz hoje

**Arquivo:** `surfaces/storefront-nuxt/app/pages/menu.vue` — **650 linhas**, 27.665 bytes. [FATO] `wc -l`.

Não é casca. O que ela faz:

- **Renderiza o cardápio completo**, agrupado por seção/coleção, com rail de pills sticky, contagem por seção, scroll ancorado e rótulo de foco para leitor de tela (`menu.vue:96-140`).
- **Filtro dietético (WP-5)**: `dietaryFilterOn` esconde itens com aviso dietético quando o cliente logado tem preferências, com contador de ocultos — transparente e reversível (`menu.vue:68-95`).
- **Busca por overlay** (a página não tem campo de texto; `menu.vue:210`).
- **É o consumidor do piloto Continuum** (`menu.vue:23-37`) — ver §4.
- **Duas fontes de catálogo com fallback**: snapshot estrutural + catálogo canônico (`menu.vue:38-51`).

**Sinais de que é página de produto, não de teste:**

| Sinal | Evidência |
|---|---|
| Está no `sitemap.xml` com prioridade 0.9 | `server/utils/sitemap.ts:35`; `curl .../sitemap.xml` → `<loc>.../menu</loc><priority>0.9</priority>` |
| Declara `canonical` próprio (anti-duplicate) | `menu.vue:423`; `curl .../menu \| grep canonical` → `<link rel="canonical" href="https://www.nelsonboulangerie.com.br/menu">` |
| É o alvo de `hasMenu` no JSON-LD do site | `app/presentation/seo.ts:429`: `ld.hasMenu = absoluteUrl(origin, '/menu')` |
| É atalho do PWA instalado | `server/utils/pwaManifest.ts:62`: `{ name: 'Cardápio', short_name: 'Cardápio', url: '/menu' }` |
| É a tela de recuperação de erro | `app/error.vue:58`: `clearError({ redirect: '/menu' })` |
| É para onde o checkout manda depois de fechar o pedido | `app/pages/finalizar.vue:1158`: `await navigateTo('/menu')` |
| O Django inteiro aponta para ela | §2 |

[FATO] O oposto de um resquício: **60 ocorrências** do literal `/menu` em **32 arquivos** de `app/` + `server/` do storefront-nuxt (`grep -ro "/menu" app server | wc -l`).

---

## 2. Quem depende de `/menu` (a página)

### 2.1 Navegação da loja — 4 pontos de entrada diretos

| Onde | Linha | Conteúdo |
|---|---|---|
| Cabeçalho (desktop + mobile) | `app/components/ShopHeader.vue:29` e `:38` | `{ to: '/menu', label: 'Cardápio', icon: 'lucide:utensils' }` |
| Barra inferior (mobile/PWA) | `app/components/AppBottomNav.vue:14` | `{ to: '/menu', label: 'Cardápio', ..., showsCartBadge: false }` |
| Rodapé | `app/components/ShopFooter.vue:40` | `<NuxtLink to="/menu">` |
| Destaque de navegação | `app/components/NavigationFeedback.vue:30` | `if (path.startsWith('/menu') \|\| path.startsWith('/colecao'))` |

[FATO] `tests/surfaceGuardrails.test.ts:513` **trava** o item da barra inferior: `expect(bottomNav).toContain("to: '/menu'")`.

### 2.2 Links de conteúdo — 17 páginas apontam para ela

```
app/pages/index.vue:346,384        (home, dois CTAs)
app/pages/faq.vue:127
app/pages/a.vue:144
app/pages/sacola.vue:114,165,298,314
app/pages/busca.vue:51             ("ver tudo no cardápio")
app/pages/encerrar-acesso.vue:52
app/pages/gerenciar-aviso.vue:196
app/pages/oferta/[ref].vue:155
app/pages/conta/favoritos.vue:58   (fallback do CTA de vazio)
app/pages/conta/pedidos.vue:111
app/pages/pedido/[ref]/index.vue:509
app/pages/colecao/[ref].vue:117,163,182  (+ breadcrumb JSON-LD :103)
app/pages/produto/[sku].vue:87,185 (+ breadcrumb JSON-LD :157)
app/components/SubstituteSheet.vue:113
app/components/HomeHeroThing.vue:48 (fallback do CTA do hero)
app/components/SearchOverlay.vue:81
app/composables/useCartState.ts:101 (CTA de "continuar comprando")
```

[FATO] `app/presentation/menu.ts:200,211` monta `/menu?secao=<slug>` — é o destino das seções dinâmicas ("Destaques"). Travado em `tests/menuPresentation.test.ts:192-204`.

### 2.3 O Django depende dela — 8 pontos de emissão

[FATO] O backend **headless** não serve HTML, mas *gera links de cliente*, e o caminho canônico do cardápio é `/menu`:

| Arquivo:linha | O que emite |
|---|---|
| `shopman/shop/services/storefront_links.py:39` | `path_menu()` → `return "/menu"` — a fonte única declarada |
| `shopman/storefront/presentation/home.py:471` | `href="/menu"` — ação `view_menu` do hero da home |
| `shopman/storefront/presentation/cart.py:578` | `href="/menu"` — ação "Continuar comprando" da sacola |
| `shopman/storefront/presentation/catalog.py:211` | `cta_href="/menu"` (empty state) |
| `shopman/storefront/presentation/catalog.py:886` | `f"/menu#{ref}" if ref else "/menu"` |
| `shopman/storefront/presentation/product_detail.py:733` | `url=f"/menu#{col.ref}"` |
| `shopman/storefront/api/account.py:332` | `"cta_href": "/menu"` (conta vazia) |
| `shopman/storefront/api/surface.py:103` | `href="/menu"` — ação "Ver cardápio" no erro de estoque |

Mais dois consumidores de caminho:

- `shopman/storefront/concierge/tools.py:53` — `WEB_DESTINATIONS = {"menu": "/menu", ...}`. O **concierge** (WhatsApp/chat) manda o cliente para cá.
- `shopman/backstage/services/omotenashi_qa.py:145` — a verificação de QA `mobile.catalog.browse` tem `url=storefront_links.storefront_url(storefront_links.path_menu())`. [FATO] É o **único** consumidor de `path_menu()` fora do próprio módulo (`grep -rn path_menu`).
- `shopman/shop/models/shop.py:267` — campo de SEO com `help_text="Aparece no Google para a página /menu."`

### 2.4 Testes

[FATO] **29 arquivos de teste, 99 ocorrências** de `/menu` em `surfaces/storefront-nuxt/tests/`. Inclui os **e2e que usam `/menu` como ponto de entrada canônico** do fluxo de compra: `tests/e2e/criticalFlow.spec.ts:15`, `tests/e2e/alpha/specs/01-smoke.spec.ts:19`, `tests/e2e/alpha/helpers.ts:89`, `tests/e2e/pwa.spec.ts:31,53,85`, `tests/e2e/resilience.spec.ts:43`, `tests/e2e/guards.spec.ts:18`, `scripts/ux-smoke.mjs:327`.

[INFERÊNCIA] Isto, somado ao uso dela como página-base de smoke test, é candidato forte a ser a origem do *"foi usada para testar algo"*. Mas a causalidade é a inversa: é usada nos testes **porque** é a página principal, não é principal porque é testada.

---

## 3. `/api/v1/storefront/menu/` — o endpoint Django privado (o OUTRO "menu")

**Isto é o que o dono vê em todo relatório de performance.** [FATO] Medido agora:

```
$ curl -sS -o /dev/null -w 'status=%{http_code} ttfb=%{time_starttransfer}s' \
    https://api.boulangerie.com.br/api/v1/storefront/menu/
status=200 ttfb=2.636758s size=136681

$ curl -sS -D - -o /dev/null https://api.boulangerie.com.br/api/v1/storefront/menu/ \
    | grep -i 'server-timing|cache-control|vary'
server-timing: projection;dur=3193.80, availability;dur=2407.56, personalization;dur=57.30, shadow;dur=0.00, db;dur=1079.02
vary: Accept, Cookie
cache-control: private
cf-cache-status: BYPASS
```

**O que é:** [FATO] `shopman/storefront/api/urls.py:107-108` → `StorefrontMenuView` (`shopman/storefront/api/surface.py:451`). Docstring: *"GET /api/v1/storefront/menu/"*. Diferença para o irmão `StorefrontCatalogView` (`surface.py:523`): `include_cart = True` — este endpoint **inclui a projeção da sacola**, o outro não.

**Por que é lento e não é cacheável:** [FATO] `vary: Accept, Cookie` + `cache-control: private` → `cf-cache-status: BYPASS`. É a rota que `docs/coordination/DECISIONS.md:260` descreve: *"a rota **privada** `/api/v1/storefront/menu/` continua ~3,3 s (`projection;dur=2718, availability;dur=1679, db;dur=613`). Ela não é cacheável por desenho (estado de sessão). É a **Onda 1** do `GO-LIVE-ACCELERATION-PLAN`."* O `GO-LIVE-ACCELERATION-PLAN-2026-09-29.md:24` a mede em **2,6–4,4 s** e a aponta como a queixa nº 1 de lentidão.

### Quem depende do endpoint (≠ da página)

| Consumidor | Evidência | Natureza |
|---|---|---|
| **`sitemap.xml` do site** | `surfaces/storefront-nuxt/server/routes/sitemap.xml.ts:18`: `$fetch<MenuResponse>(`${djangoBaseUrl}/api/v1/storefront/menu/`)` | [FATO] **único consumidor de produção dentro deste repo** |
| BFF do storefront (allowlist) | `server/utils/storefrontApiAllowlist.ts` (prefixo `storefront/`); `tests/securityBoundaries.test.ts:14` | [FATO] permitido, mas **nenhum código chama** |
| Testes de contrato do BFF | `tests/djangoProxyBehavior.test.ts:110,120,136,143,199` | [FATO] |
| Suíte Django + carga | `shopman/shop/tests/load/locustfile.py:114,144`; `shopman/shop/tests/test_health.py:244`; `storefront/tests/e2e/*`, `tests/api/test_server_timing.py:38`, `test_public_edge_cache.py:173`, `test_continuum_catalog.py` | [FATO] |

**Achado relevante para o dono:** [FATO] a página `/menu` **não chama mais** `/api/v1/storefront/menu/`. Ela chama `apiPath('/api/v1/storefront/catalog/')` (`menu.vue:47`), e existe teste que **proíbe** a regressão:

```
tests/performanceGuardrails.test.ts:21-22
  expect(menu).toContain("apiPath('/api/v1/storefront/catalog/')")
  expect(menu).not.toContain("apiPath('/api/v1/storefront/menu/')")
```

[INFERÊNCIA] Ou seja: o endpoint de 2,6–4,4 s que aparece em todo relatório de performance hoje **serve, dentro do repo, apenas o `sitemap.xml`** (mais a suíte de testes). O sitemap só precisa de `sku` e `ref` de coleção estática — o que a gêmea pública e cacheável (`storefront/public/catalog/`, `shopman/storefront/api/public_cache.py`) já entrega. **Isto é uma alavanca da Onda 1 que não está no plano** e vale medir. [NÃO VERIFICADO] Não consigo garantir que não há consumidor **externo** ao repo (o `nb-catalog-app` legado, integrações, iFood); o endpoint é público em `api.boulangerie.com.br` e eu não tenho tráfego.

---

## 4. O Continuum depende de `/menu`? É o contrário.

**Resposta curta: o Continuum não depende de `/menu`; `/menu` é o único consumidor do Continuum.**

[FATO] No storefront inteiro, `continuumCatalog` e `useContinuousProjection` aparecem em **exatamente dois lugares**:

```
$ grep -rn 'continuumCatalog|useContinuousProjection|continuumCatalogEnabled' surfaces/storefront-nuxt/app
app/pages/menu.vue:16,27,29        ← o único consumidor
app/composables/useContinuousProjection.ts:19  ← a definição
```

- O **read model** do Continuum (`shopman/storefront/continuum.py`, endpoint `/api/v1/storefront/continuum/v0.2/catalog-structure/`) é construído a partir de escritas de catálogo e **não sabe que `/menu` existe**.
- A **dependência real é no sentido oposto**: apagar `/menu` **orfana o piloto Continuum inteiro** — e, com ele, as recomendações 1–5 do relatório `03-continuum-impacto.md` (matar o poll canônico de 30 s, encurtar o poll do snapshot, serializar a reconstrução).
- E o Continuum **não gateia** a página: sem snapshot, o SSR volta ao catálogo canônico — `menu.vue:41`: `canonicalOnServer = import.meta.server && (!continuumEnabled || !structureCatalog.value)`. [FATO] Confirmado no `03-continuum-impacto.md:309`: *"Fallback monolítico real — nenhum caminho do Continuum pode impedir a compra."*

**Sobre o "usada para testar algo":** [FATO] `docs/reports/go-live-acceleration-20260929/03-continuum-impacto.md:4` diz literalmente: *"**Escopo:** piloto Continuum 0.2 do snapshot estrutural do cardápio (**`/menu` do storefront**)"*, e `:298`: *"**Rollout: 100 % do `/menu` do site público**"*, ligado em 28/09/2026 13:25 (`02b4f1487`). É [FATO] que `/menu` **foi a superfície do piloto** — mas o piloto chegou 4 meses e meio depois da página (07/05/2026 vs 28/09/2026). A página não nasceu para testar o Continuum; o Continuum é que foi testado *nela*.

---

## 5. Se remover `/menu`, o que quebra

**Quase tudo na jornada de compra.** Lista concreta:

1. **Navegação principal some.** Cabeçalho (`ShopHeader.vue:29,38`), barra inferior (`AppBottomNav.vue:14`) e rodapé (`ShopFooter.vue:40`) levam a 404. [FATO] `tests/surfaceGuardrails.test.ts:513` reprova a CI imediatamente.
2. **~30 pontos de link interno apontam para 404** (§2.2): home, sacola, busca, FAQ, favoritos, pedidos, coleção, produto, oferta, erro global, pós-checkout.
3. **O Django continua emitindo `/menu`** (§2.3) — home, sacola, conta, erro de estoque, PDP, concierge, QA de omotenashi. [FATO] São 8 pontos de emissão mais `path_menu()`; renomear/remover sem tocar neles produz 404 **em produção**, servido pelo backend.
4. **SEO quebra.** `/menu` sai do sitemap (`server/utils/sitemap.ts:35`), o `hasMenu` do JSON-LD some (`app/presentation/seo.ts:429`) e a URL indexada (priority 0.9) passa a 404 — perda de equity, sem 301 (não existe redirect declarado para ela, ver §6).
5. **O PWA instalado perde o atalho** (`server/utils/pwaManifest.ts:62`).
6. **A recuperação de erro aponta para 404** (`app/error.vue:58`), e o cliente que pagou e fechou o pedido é jogado num 404 (`finalizar.vue:1158`).
7. **`/menu?secao=<slug>` (seções dinâmicas) e `/menu?filtro=` (busca) deixam de existir** — `app/presentation/menu.ts:200,211`, `SearchOverlay.vue:81`, `busca.vue:51`.
8. **O Continuum fica órfão** (§4) — o piloto ligado em 28/09 passa a não ter consumidor nenhum.
9. **29 arquivos de teste, 99 referências** deixam de compilar/passar, incluindo todos os e2e que usam `/menu` como porta de entrada (`criticalFlow`, `alpha/01-smoke`, `alpha/helpers`, `pwa`, `resilience`, `guards`, `ux-smoke.mjs`). Eles precisariam de uma nova página-âncora.

---

## 6. Se ainda assim quisesse remover: qual o custo?

**Não existe "remover `/menu`" barato, porque não há para onde apontar.** [FATO] Não há rota substituta:

| Caminho testado ao vivo | Resultado |
|---|---|
| `/cardapio` | `404` — o nome alternativo **nunca existiu** (descartado em 20/06/2026) |
| `/menu/paes/` (variante legada de categoria) | `404` — o shim já foi removido |

O custo real de remover seria o custo de **substituir**, e ele tem 4 frentes:

1. **Uma página nova em `app/pages/`** que absorva as 650 linhas de `menu.vue` (seções, pills, filtro dietético, busca por overlay, fallback canônico/snapshot).
2. **301 permanente** da URL antiga para a nova. [INFERÊNCIA] Isto tem custo de SEO real: `/menu` está no sitemap com priority 0.9 e é a URL que o Google conhece; e, conforme `shopman/shop/services/storefront_links.py:20-27`, **301 em link de cliente é problema** — *"alguns clientes de mensagem pré-visualizam o destino, e o redirect atrapalha"*. O repo tem uma decisão explícita e documentada contra deixar link de cliente passar por redirect.
3. **Trocar o caminho em 8 pontos do Django + `path_menu()` + o campo de SEO do `Shop`** (`shop/models/shop.py:267` tem o `help_text` com a URL escrita à mão e a migração `0059_shop_search_presence.py` carrega a string).
4. **Renomear em 32 arquivos do storefront + 29 arquivos de teste** — e reescrever os guardrails que **travam** `/menu`: `surfaceGuardrails.test.ts:513` (`to: '/menu'` na bottom nav), `performanceGuardrails.test.ts:21`, `indexingPolicy.test.ts:39`, `sitemap.test.ts:9`.

**Custo/benefício:** [INFERÊNCIA] o ganho é **zero** (nenhuma performance, nenhuma correção; `/menu` responde `200` em `cache-control: private` com SSR normal). O gasto é uma migração de URL em produção com perda de SEO e risco de quebrar link já divulgado — às vésperas do go-live. **Não se paga.**

---

## 7. Veredito

| Pergunta do dono | Resposta |
|---|---|
| "A url `/menu` foi usada para testar algo?" | **Parcialmente, e no sentido inverso.** [FATO] `/menu` **é** a superfície onde o piloto Continuum foi ligado (100 %, 28/09) e **é** a página usada como porta de entrada nos smokes e2e. Mas ela é uma das 4 páginas fundadoras do storefront (07/05/2026), anterior ao piloto em 4 meses e meio. **Ela não é uma página de teste.** O que o dono provavelmente viu é o **endpoint** `/api/v1/storefront/menu/` aparecendo em todo relatório de performance — e esse é outro objeto. |
| "Ela ainda é necessária?" | **Sim, é o cardápio.** [FATO] Página Nuxt SSR, pública, no ar (`200`), no sitemap (0.9), no cabeçalho, na barra inferior, no rodapé, no JSON-LD, no atalho do PWA, na tela de erro, no pós-checkout, e no destino de 8 links gerados pelo próprio Django. |
| "Confere que foi usada para testar algo?" | **Não no sentido que a pergunta sugere.** [FATO] O dono **já decidiu mantê-la** em 20/06/2026 (`URL-STANDARDIZATION-PLAN.md:3`, commit `fb82dfb3`), escolhendo `/menu` em vez de `/cardapio`. `/cardapio` dá `404` hoje. |
| "Se remover, quebra algo?" | **Sim, extensamente** — §5: navegação, ~30 links internos, 8 emissores no Django, sitemap, JSON-LD, PWA, tela de erro, `/menu?secao=`, o Continuum, e 29 arquivos de teste. |
| "Qual o custo de remover?" | **Alto e sem contrapartida** — §6: renomear URL em produção, 301 que o próprio repo evita para links de cliente, 32+29 arquivos, e perda de SEO. Ganho: zero. |

**Recomendação:** [INFERÊNCIA] **não mexer em `/menu`.** A pergunta útil que está escondida atrás dela é sobre **`/api/v1/storefront/menu/`** — o endpoint de 2,6–3,3 s que, dentro deste repo, só o `sitemap.xml` consome desde que a página migrou para `/api/v1/storefront/catalog/` (§3). Se o objetivo é cortar peso do go-live, **é ali**, e não na página.

---

## 8. Onde procurei e não achei

- **301/redirect declarado para `/menu`:** procurei em `surfaces/storefront-nuxt/nuxt.config.ts` (`routeRules`, linha 58 — só headers de `/`, `/img/products/**` e `/sw.js`, **nenhum redirect**) e em `server/middleware/` (`indexing-policy.ts`, `sku-redirects.ts`, `storefront-security.ts` — os 301 de URL pt-BR que o `URL-STANDARDIZATION-PLAN` menciona **não estão mais lá**; o único redirect de servidor é de SKU aposentado, `server/utils/skuRedirects.ts`). Não achei nenhum redirect que envolva `/menu`.
- **Rota `/cardapio`:** não existe. `glob`/`ls` em `surfaces/storefront-nuxt/app/pages/` não tem o arquivo, e a URL dá `404` ao vivo.
- **Subpágina `/menu/[category]`:** não existe mais (`find app/pages` lista só `menu.vue`); `/menu/paes/` dá `404` ao vivo. O shim foi removido — era pendência do `STOREFRONT-NUXT-PARITY-ACTION-PLAN`.
- **`robots.txt` estático:** não existe em `public/`; é rota Nitro (`server/routes/robots.txt.ts`). `/menu` **não** está em `CRAWL_DISALLOWED_PREFIXES` nem em `PRIVATE_ROUTE_PREFIXES` (`server/utils/indexingPolicy.ts:22,25`) — logo é lida e indexável. `tests/indexingPolicy.test.ts:39` confirma que `/menu` não é rota privada.
- **Consumidor externo do endpoint `/api/v1/storefront/menu/`:** [NÃO VERIFICADO] Não tenho tráfego nem acesso a `doctl apps logs`. Dentro do repo, o único consumidor de produção é `sitemap.xml.ts:18`. Não dá para descartar o `nb-catalog-app` legado (repo externo) nem integrações.
- **Compatibilidade do `menu.\` host com esta página:** não é esta página. `curl -L` mostra que `https://menu.nelsonboulangerie.com.br/menu` resolve para a **raiz** do app antigo.

---

## 9. Comandos executados (reproduzíveis)

```bash
cd /Users/pablovalentini/Dev/Claude/django-shopman/.dsh-worktrees/go-live-acceleration

# 1. A página nasceu com a superfície Nuxt
git log --diff-filter=A --format='%h %ad %s' --date=short -- surfaces/storefront-nuxt/app/pages/menu.vue
#   → 3c3cdddbd 2026-05-07 feat: add Nuxt storefront surface
git show --stat 3c3cdddbd -- surfaces/storefront-nuxt/app/pages/
#   → menu.vue | 74 ++++  (junto com index.vue, cart.vue, produto/[sku].vue)

# 2. Densidade de dependência interna
cd surfaces/storefront-nuxt
grep -ro "/menu" app server | wc -l          # → 60
grep -rl "/menu" app server | wc -l          # → 32
grep -rl "/menu" tests | wc -l               # → 29
grep -ro "/menu" tests | wc -l               # → 99

# 3. Quem no Django emite o caminho
grep -rn --include=*.py -E "["']/menu["']|href="/menu"" shopman/ config/ | grep -v /tests/ | grep -v menuboard

# 4. Único consumidor do Continuum
grep -rn 'continuumCatalog|useContinuousProjection' surfaces/storefront-nuxt/app

# 5. Prova ao vivo (somente leitura)
curl -sS -o /dev/null -D - --max-time 20 https://www.nelsonboulangerie.com.br/menu     # HTTP/2 200, x-powered-by: Nuxt
curl -sS --max-time 20 https://www.nelsonboulangerie.com.br/sitemap.xml | head          # /menu priority 0.9
curl -sS -o /dev/null -w '%{http_code}\n' https://www.nelsonboulangerie.com.br/cardapio  # 404
curl -sS -o /dev/null -w '%{http_code}\n' https://www.nelsonboulangerie.com.br/menu/paes/  # 404
curl -sS -o /dev/null -w 'status=%{http_code} ttfb=%{time_starttransfer}s\n' \
     https://api.boulangerie.com.br/api/v1/storefront/menu/                             # 200 / 2,64 s
curl -sS -o /dev/null -w '%{http_code} %{url_effective}\n' -L https://menu.nelsonboulangerie.com.br/menu
#   → 200 https://menu.nelsonboulangerie.com.br/   (cardápio ANTIGO, app nb-catalog-app)
```
