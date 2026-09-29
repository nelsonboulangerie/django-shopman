# 04 — Bug do "segundo clique" (add-to-cart)

**Árvore analisada:** `.dsh-worktrees/go-live-acceleration` @ `f0ffd02fd` (origin/main, 2026-09-29).
Leitura estática; nenhum arquivo do produto foi alterado. Único arquivo escrito: este relatório.

Legenda: **[FATO]** verificado no código/saída de comando · **[INFERÊNCIA]** dedução minha · **[NÃO VERIFICADO]** não consegui confirmar.

---

## 1. Resumo executivo

1. **[FATO] A string exata "Não foi possível adicionar" NÃO EXISTE no repositório.** Procurei em `surfaces/storefront-nuxt`, em `shopman/` e na worktree inteira, em `.ts`, `.vue`, `.py`, `.md`. O dono está parafraseando. A mensagem real que o add-to-cart da loja pode mostrar é **"Não foi possível atualizar o carrinho."** (`surfaces/storefront-nuxt/app/composables/useCartState.ts:342-343`) — o único toast genérico do caminho de carrinho.
2. **[FATO] O primeiro clique custa 2 a 3 idas ao Django; o segundo custa 1.** O cliente faz um GET semente de CSRF quando não tem o cookie (`useShopmanCsrfHeaders.ts:17-20`) e o BFF faz **outro** GET semente quando o PUT chega sem token (`djangoProxy.ts:191-196` → `ensureDjangoCsrfCookie`, `djangoProxy.ts:58-82`). É uma assimetria estrutural e mensurável entre clique 1 e clique 2 — o candidato nº 1 a "só funciona no segundo clique".
3. **[FATO] O erro da semente do cliente é engolido em silêncio** (`.catch(() => null)`, `useShopmanCsrfHeaders.ts:18`): se aquele GET falhar, nada é dito ao usuário, o PUT segue sem `x-csrftoken`, e o que sobra é o toast genérico do item 1. Falha na primeira perna vira "Não foi possível…" na última.
4. **[FATO] A medição já existe e ninguém está olhando:** o BFF carimba `Server-Timing: bff;dur=<ms>` em toda resposta (`djangoProxy.ts:214-220`) e o cronômetro começa **antes** da semente de CSRF (`djangoProxy.ts:121` vs `:192`). Logo o `bff;dur` do **primeiro** PUT inclui a semente e o do segundo não. É o experimento decisivo, de graça.
5. **[FATO] O add button é `disabled` até a hidratação** (`CartQuantityAction.vue:24,33,74,83`; o próprio teste documenta "só age depois de hidratado", `tests/components/cartQuantityAction.test.ts:1`). Um toque antes da hidratação é um **no-op silencioso**, sem requisição e sem alerta. Isto explica (b) "algumas coisas só funcionam no segundo clique" **sem** explicar o alerta — é um **bug distinto**.
6. **[FATO] Não existe retry de UI para o clique 1 e o retry que existe é curto.** `retryWithBackoff` só reage a `status === null | 502 | 503 | 504` (`httpError.ts:24-27`) e espera 200 ms/400 ms (`retryBackoff.ts:21-23`) — curto para cold start, e um 500 é terminal.
7. **[FATO] Não existe chave de idempotência no carrinho — e não precisa.** O PUT é `qty` absoluto, `@transaction.atomic` (`cart_mutations.py:57`), então o clique 2 é idempotente por construção. O que **não** é idempotente é o *efeito de tela*: `useCartState` pode ter revertido o otimista e o segundo clique apenas reconcilia.
8. **[FATO] Há uma corrida de *lost update* no cliente** que faz o item adicionado sumir da tela: `refreshCart()` grava a projeção sempre que `queueDepth === 0` (`useCartState.ts:272`), inclusive se a resposta for **anterior** à mutação que acabou de drenar. Isso não gera alerta, mas gera "sumiu, cliquei de novo e apareceu".
9. **[INFERÊNCIA] Hipótese principal:** o primeiro clique é o único que paga sessão + CSRF + projeção de carrinho completa com backend frio; qualquer falha em qualquer elo dessa cadeia longa cai no toast genérico, e o clique 2 **nunca repete a cadeia** (o cookie já está no navegador). Mecanismo passo a passo na §2.
10. **[FATO] O time já sabia que o primeiro clique é especial:** `app/middleware/cart-settle.global.ts:7-9` diz literalmente que a navegação "não pode abortar a requisição que torna o clique durável (**e que carrega o primeiro cookie de sessão**)". O comentário é de um bug passado com o mesmo cheiro.

**Confiança:** alta de que existem **dois bugs distintos** (§2.1 e §2.2) e alta sobre os mecanismos de código; **média** sobre qual deles produziu a queixa (a) — depende de qual mensagem o dono viu, e isso só o Network/console do navegador dele resolve.

---

## 2. Achados

### 2.1 Achado A — a cadeia do primeiro clique (hipótese principal do alerta)

**O que é.** A primeira mutação de carrinho de um navegador é a única que faz *handshake*. Todo o resto do ciclo de vida do visitante navega com o token já em cookie.

**Evidência (tudo [FATO]):**

| # | Fato | path:line |
|---|---|---|
| A1 | Cliente lê `csrftoken`; se não existe, faz um GET semente ao BFF e **engole o erro** | `surfaces/storefront-nuxt/app/composables/useShopmanCsrfHeaders.ts:16-21` |
| A2 | Se após isso o token continuar vazio, devolve `{}` e o PUT sai sem `x-csrftoken` | `…/useShopmanCsrfHeaders.ts:21` |
| A3 | O PUT do carrinho usa esse header e passa por `retryWithBackoff` (o header é reavaliado a cada tentativa) | `…/useCartState.ts:296-301` |
| A4 | O BFF, sem token, dispara **outro** GET semente direto ao Django | `surfaces/storefront-nuxt/server/utils/djangoProxy.ts:191-196` |
| A5 | `ensureDjangoCsrfCookie` = `$fetch.raw(`${djangoBaseUrl}/api/v1/storefront/cart/`)` | `…/djangoProxy.ts:58-82` |
| A6 | O GET `storefront/cart/` é decorado com `ensure_csrf_cookie`, então **de fato** emite `Set-Cookie: csrftoken` | `shopman/storefront/api/surface.py:568-576` + Django 6.1.1 `django/middleware/csrf.py:96-114` (`get_token`) e `:472-482` (`process_response`) |
| A7 | A resposta do PUT monta a projeção **completa** do carrinho (a leitura mais cara da loja), além da escrita | `shopman/storefront/api/surface.py:1070-1076` → `_cart_payload` (`:69-71`) |
| A8 | `Server-Timing: bff;dur=` é carimbado pelo BFF, e o cronômetro começa **antes** da semente | `djangoProxy.ts:121` (`bffStarted`), `:214-220` (header), `:192` (semente no meio) |
| A9 | O teste do BFF **espera** que a semente aconteça no 1º método unsafe sem cookie | `tests/djangoProxyBehavior.test.ts:154-175` |
| A10 | O mock de e2e precisa devolver `csrftoken` em **toda** resposta "p/ o handshake do BFF não precisar semear em loop" | `tests/e2e/mockBackend.mjs:11-13` |
| A11 | O time já registrou que o primeiro clique é o que carrega o primeiro cookie de sessão | `app/middleware/cart-settle.global.ts:7-9` |

**Mecanismo, passo a passo (clique 1, navegador sem `csrftoken`):**

1. O SSR entrega a página. O `GET /api/v1/storefront/shell/` roda **no servidor** (`useStorefrontShell.ts:18` só encaminha `cookie`, `:22-25`), e o Nuxt **não repassa o `Set-Cookie` de um `$fetch` interno ao navegador**. [INFERÊNCIA — não verifiquei empiricamente; ver §6]
2. O visitante toca "Adicionar". `CartQuantityAction.addOne` → `setSkuQty` (`CartQuantityAction.vue:32-36`).
3. A UI já mostra o item (otimista, `useCartState.ts:291`).
4. `csrfHeaders()` não acha cookie → **GET #1** (cliente → BFF → Django). Se ele falhar, `.catch(() => null)` esconde (`A1`).
5. Se o GET #1 não semeou o cookie, o PUT chega ao BFF sem token → **GET #2** (BFF → Django), `A4`.
6. O **PUT** roda, e sua resposta carrega `_cart_payload` — a projeção completa (`A7`).
7. Qualquer falha em 4/5/6 — e o clique 1 é o único momento em que as três existem, com o backend mais frio que estará no dia — cai em `useCartState.ts:340-344` e mostra **"Não foi possível atualizar o carrinho."** (ou o `detail` do erro, se houver).
8. O visitante toca de novo: agora o `csrftoken` **está** no navegador (o GET #1 ou #2 plantou), então **não há GET #1 nem #2** — uma requisição só, backend já quente. Funciona.

**Custo quantificado [FATO, por leitura de código]:** clique 1 = 2 chamadas HTTP ao Django no caminho feliz (semente + PUT) e **até 6 no caminho de retry** (3 tentativas × semente do BFF, mais a semente do cliente). Clique 2 = 1 chamada. O `bff;dur` do primeiro PUT deve ser visivelmente maior que o do segundo — é literalmente a soma da semente (`A8`).

**Impacto.** Explica (a) e (b) simultaneamente, e é pior justamente no pior momento: primeiro acesso de um visitante novo, tráfego de pico, logo após deploy (processos/pools frios). Também transforma o primeiro clique numa **amplificação de carga** (N sementes por clique), o que realimenta a lentidão.

**Confiança.** Mecanismo de código: **alta** (tudo `path:line`). Causalidade sobre a queixa do dono: **média** — não consigo provar que houve falha no elo 4/5/6 sem o log/Network da sessão dele.

---

### 2.2 Achado B — o primeiro toque antes da hidratação é um no-op silencioso

**O que é.** Bug **distinto** do Achado A. Não gera alerta: não gera nada.

**Evidência [FATO]:**
- `CartQuantityAction.vue:24` `const hydrated = ref(false)`; `:28-30` `onMounted(() => hydrated.value = true)`.
- `:33` `if (!hydrated.value || props.disabled || pending.value) return`.
- `:74`/`:83` `:disabled="!hydrated || disabled || pending"` — o HTML do SSR nasce **desabilitado**.
- `tests/components/cartQuantityAction.test.ts:1` documenta o contrato: "o botão de adicionar só age depois de hidratado"; `:43` `await nextTick() // onMounted → hydrated`.

**Mecanismo.** Em 4G/iPhone, o HTML pintado chega antes do bundle hidratar. O botão está visível, parece ativo (a cor vem do CSS, não do estado Vue), e o primeiro toque cai num `<button disabled>`: o browser não dispara `click`, nada acontece, nenhum spinner. Segundos depois o app hidrata e o segundo toque funciona.

**Impacto.** É exatamente a queixa (b) — e é a explicação mais provável para "algumas coisas" (todos os controles com guarda de hidratação, não só o carrinho) **quando não há alerta**. O dono relatou alerta em (a), mas as duas queixas foram dadas juntas e podem ter origens diferentes.

**Confiança.** Alta no código; média em ser *a* causa da queixa (b), porque depende do timing do aparelho dele.

---

### 2.3 Achado C — *lost update* no cliente: o item adicionado some da tela

**O que é.** `refreshCart()` e `setFromServer()` protegem-se com `queueDepth`, mas a proteção é avaliada **na chegada da resposta**, não no disparo da requisição.

**Evidência [FATO]:**
- `useCartState.ts:266-274` — `refreshCart()`: `if (queueDepth === 0) setCartProjection(response.cart)`.
- `useCartState.ts:238-248` — `setFromServer()`: `if (queueDepth > 0) return`.
- `useCartState.ts:291-310` — o otimista é aplicado e a verdade do servidor chega no drain.

**Mecanismo.** Um GET de carrinho disparado em t0 (queueDepth 0) resolve em t3, **depois** de a mutação do usuário ter nascido (t1) e drenado (t2). Em t3 `queueDepth === 0`, então o snapshot **anterior ao add** sobrescreve a verdade nova. O item pisca e desaparece; o badge volta; o cliente toca de novo.

**Impacto.** Produz "o item não entrou" **sem** erro e **sem** toast — e o clique 2 conserta porque aí o GET não está mais em voo. Forte candidato para (b) sem alerta.

**Confiança.** Alta de que a janela existe no código; média de que o dono a atingiu (depende de qual fetch passivo estava em voo). Não medi.

---

### 2.4 Achado D — `queueDepth` pode derivar para negativo (defeito latente)

**Evidência [FATO]** — `useCartState.ts:295-346`:

```js
try {
  const response = await enqueueMutation(...)
  queueDepth -= 1          // :302
  ...
  applyServerCart(response.cart)   // :306  ← se ISTO lançar…
  return response
} catch (error) {
  queueDepth -= 1          // :313  ← …decrementa de novo
```

Não há `finally`. Qualquer exceção entre `:302` e o fim do `try` decrementa duas vezes; `queueDepth` fica negativo e `queueDepth === 0` (que governa `applyServerCart`, `:304-306`) **nunca mais** é verdadeiro para as próximas mutações. O mesmo padrão em `mutateCoupon` (`:349-365`).

**Impacto.** Se acontecer, o carrinho para de reconciliar com a verdade do servidor e a tela vive de estado otimista — "só o segundo clique parece valer". É **latente** (não achei no código um caminho que faça `applyServerCart` lançar: `setCartProjection` é um spread, `useCartState.ts:225-227`).

**Confiança.** Alta no defeito; baixa na ocorrência em produção hoje. **Mesmo assim vale corrigir: é barato (um `finally`) e o sintoma que ele produz é indistinguível da queixa.**

---

### 2.5 Achado E — o retry existente não cobre o caso que provavelmente ocorre

**Evidência [FATO]:**
- `app/utils/httpError.ts:24-27`: `isTransientError` = `status === null || 502 || 503 || 504`. **500 não é retentado.**
- `app/utils/retryBackoff.ts:21-23`: `retries = 2`, `baseMs = 200`, `maxMs = 2000` → 3 execuções em ~600 ms no máximo.
- `useCartState.ts:296`: é o único retry do caminho do carrinho.
- Não há timeout explícito no `$fetch` do BFF (`djangoProxy.ts:202-207` não passa `timeout`) nem no cliente. O único `timeout_seconds` do spec de deploy é de **health check** (`.do/app.subdomains.yaml:656,663` → `5`), não de requisição. O timeout BFF→Django é da plataforma. **[NÃO VERIFICADO]** qual é.

**Impacto.** Um cold start de 2–3 s ou um 500 transitório do Django consomem as 3 tentativas em <1 s e o usuário vê o toast. Retry não é a causa — é a ausência de rede de proteção.

### 2.6 Hipóteses testadas e **refutadas** (para não voltar nelas)

| Hipótese | Veredito | Evidência |
|---|---|---|
| `NavigationFeedback` engole o primeiro clique | **REFUTADA** | o scrim é `pointer-events-none` — `NavigationFeedback.vue:205`; e o próprio código comenta "nunca cancela nem engole o clique" (`:163-166`) |
| O overlay de navegação fica preso 15 s | **REFUTADA como causa de clique engolido** | watchdog `WATCHDOG_MS = 15_000` (`:4`, `:104`) + `forceFinish` em `page:finish`/`app:error`/`router.afterEach` (`:169-177`); visual apenas |
| CSRF quebra o add-to-cart **anônimo** | **REFUTADA** | DRF `APIView.as_view()` aplica `csrf_exempt` (`rest_framework/views.py:149`) e `SessionAuthentication` só valida CSRF com usuário autenticado (`rest_framework/authentication.py:126-130`). Anônimo **não** precisa de token |
| O GET semente não devolve `csrftoken` (handshake morto) | **REFUTADA** | `surface.py:568` usa `ensure_csrf_cookie`; Django 6.1.1 `csrf.py:96-114` + `:472-482` emitem o cookie. O handshake funciona |
| Rate limit (429) no primeiro clique | **POUCO PROVÁVEL** | limite é `120/m` por `user_or_ip` (`surface.py:1038-1047`); e o 429 tem UI própria (banner com contagem, `useCartState.ts:332-339`), não o toast genérico |
| Duplo submit duplica item no servidor | **REFUTADA** | PUT de `qty` absoluto, `@transaction.atomic` (`cart_mutations.py:57-127`) — idempotente por construção |
| O `Domain` do cookie cross-subdomínio só resolve no 2º request | **REFUTADA** | `storefrontSetCookieHeader` **remove** `Domain` de propósito e os cookies da loja são host-only (`djangoProxy.ts:46-56`; settings `:2050-2052`) |
| O BFF devolve 403 por `Sec-Fetch-Site: same-site` | **NÃO VERIFICADO / improvável** | o teste existe (`djangoProxy.ts:176-184`) mas um fetch same-origin manda `same-origin`. Se o 403 ocorresse, ocorreria em **todo** clique, não só no primeiro — não casa com o sintoma |

---

## 3. O que já existe e funciona (não reinventar)

- **Fila serial de mutações** (`useCartState.ts:178-194`) — rajadas de toque não se perdem nem chegam fora de ordem; sobrevive a erro.
- **Otimista + rollback** com `rollbackCart` (`useCartState.ts:205, 289, 321-324`) e reconciliação no drain (`:304-310`).
- **Três ramos de erro com UI dedicada**: 409 → `SubstituteSheet` global (sem toast sobreposto, `:327-331`); 429 → banner com countdown (`:332-339`); genérico → toast (`:340-344`).
- **`cart-settle` global** já protege a navegação de abortar a mutação durável (`middleware/cart-settle.global.ts`).
- **Handshake de CSRF no BFF** implementado e testado (`djangoProxy.ts:58-82`; `tests/djangoProxyBehavior.test.ts:154-175`).
- **Idempotência do carrinho por construção** (qty absoluto + `atomic`).
- **`Server-Timing` instrumentado** com `bff;dur` (`djangoProxy.ts:214-220`) — telemetria pronta para medir exatamente o que falta medir.
- **Trava anti path-traversal** na allowlist do BFF (`djangoProxy.ts:84-124`) — não mexer.
- **Histórico de fixes no transporte do BFF** (`git log`: `22c2aea2c` allowlist/CSRF, `defab7430` IP do cliente, `87dfdd088` cookie com `=`). **O BFF já foi a fonte de vários bugs reais** — reforça a hipótese principal.

---

## 4. Lacunas e riscos

1. **Nenhuma telemetria de "primeiro clique".** Não existe contador de semente de CSRF, nem histograma do `bff;dur` do primeiro PUT vs os seguintes, nem evento de "mutação de carrinho falhou no clique 1". Sem isso a hipótese principal fica em "média" para sempre. [FATO — não encontrei nenhum `capture*`/`log*` para isso em `storefront/observability.py` nem no app Nuxt]
2. **`.catch(() => null)` na semente (`useShopmanCsrfHeaders.ts:18`)**: falha de rede vira silêncio, e o sintoma aparece longe da causa.
3. **`bff;dur` mistura semente e mutação** (`djangoProxy.ts:121` + `:192`): a métrica que temos não separa as duas pernas. Custa uma linha separar.
4. **`queueDepth`/`mutationChain` são estado de módulo** (`useCartState.ts:180-181`), não por requisição. Em Nuxt SSR o módulo é compartilhado por todas as requisições do mesmo processo. Não achei chamada server-side de `setSkuQty` (o `cart-settle` global sai em `import.meta.server`, `cart-settle.global.ts:2`), então hoje é latente — mas é o tipo de coisa que vaza no dia em que alguém chamar isso do SSR. [INFERÊNCIA]
5. **Sem timeout explícito** em nenhuma das duas pernas (cliente e BFF). O comportamento de timeout é 100% da plataforma. [NÃO VERIFICADO]
6. **Os testes assumem o cookie semeado**: `document.cookie = 'csrftoken=testtoken'` em `useCartState.test.ts:50`, `cartQuantityAction.test.ts:25` e mais 8 arquivos. **Nenhum teste cobre o clique 1 de um navegador sem cookie** — a assimetria que estou apontando é, por construção, invisível para a suíte. [FATO]

---

## 5. Recomendações, por impacto/esforço

### P0 — barato e decide a causa (fazer primeiro)

1. **Medir o clique 1.** Separar `bff;dur` em `csrf;dur` e `upstream;dur` (`djangoProxy.ts:121, 192, 214-220`) e logar um evento estruturado quando `ensureDjangoCsrfCookie` roda (`djangoProxy.ts:191`). Passa a existir a série "quantas sementes por mutação" e "quanto custa a semente". ~10 linhas.
2. **Eliminar a semente dupla.** O cliente não deve fazer o GET semente (`useShopmanCsrfHeaders.ts:17-20`): o BFF **já** resolve o token sozinho (`djangoProxy.ts:187-196`) e devolve o `Set-Cookie` ao navegador (`:222-227`). Remover as linhas 17-20 encurta o primeiro clique em 1 ida ao Django e apaga o `.catch(() => null)` silencioso. **Verificar antes** que todos os endpoints unsafe que o cliente chama passam pelo BFF (todos passam — `storefrontApiAllowlist.ts:1-16` cobre todos os prefixos usados).
3. **Instrumentar o clique 1 no cliente:** um `useSonner`/`telemetria` que registre `{status, detail, tentativa}` das falhas genéricas (`useCartState.ts:340-344`) com um marcador de "primeira mutação desta sessão". Sem isso, o dono vai relatar de novo e continuaremos sem saber qual elo caiu.

### P1 — corrige defeitos provados

4. **`finally` no lugar do decremento duplo** (`useCartState.ts:295-346` e `:349-365`): um `finally { queueDepth -= 1; dropPending(meta.sku) }`. Fecha o Achado D.
5. **Guardar a corrida do Achado C**: carimbar `refreshCart()`/`setFromServer()` com um `mutationEpoch` e descartar respostas iniciadas antes da última mutação (`useCartState.ts:238-248, 266-274`).
6. **Botão de adicionar não deve parecer ativo antes da hidratação** (`CartQuantityAction.vue:74,83`): ou o estado desabilitado é visível (opacidade/spinner no SSR), ou o `onMounted` deixa de ser pré-requisito e o handler passa a confiar só no `pending`/`disabled`. Hoje o usuário recebe um botão que mente. Fecha o Achado B.
7. **`e2e` do clique 1 com navegador limpo**: Playwright com `storageState` vazio → tocar "Adicionar" → exigir 200 e o item na sacola. É o teste que falta e que teria pego isto (`tests/e2e/` já existe; `tests/e2e/mockBackend.mjs:11-13` hoje **esconde** o problema semeando o cookie em toda resposta).

### P2 — robustez

8. **Retry do 500** ou, melhor, só depois de confirmar que o 500 existe no caminho (`httpError.ts:26`). **Não aumentar o backoff às cegas** — 200/400 ms pode ser curto para cold start, mas mascarar 500 é pior que mostrar.
9. **Timeout explícito e nomeado** no proxy (`djangoProxy.ts:202-207`) e no cliente, alinhado ao da plataforma. Hoje o comportamento depende do ingress.
10. **Tirar `queueDepth`/`mutationChain` do escopo de módulo** (`useCartState.ts:180-181`): mover para dentro de `useCartState()` via `useState`, ou blindar com `import.meta.client`.

---

## 6. Perguntas abertas / o que NÃO consegui verificar

1. **Qual mensagem o dono viu, exatamente?** A string "Não foi possível adicionar" **não existe** no código. Preciso de print, ou do `detail` do toast, ou do Network da aba. Sem isso, a queixa (a) pode ser: o toast genérico ("Não foi possível atualizar o carrinho."), o banner de rate-limit ("Muitas alterações na sacola…"), o `SubstituteSheet` (título "Revise este item"/"Ficou indisponível enquanto você escolhia.") ou um 403 `CSRF Failed` (que sairia **em inglês** para um cliente logado — se aparecer isso, é bug próprio e vale abrir tarefa separada).
2. **O Nuxt repassa o `Set-Cookie` de um `$fetch` interno do SSR?** Base do passo 1 do mecanismo. Não testei em runtime. Como verificar: subir a loja, abrir sem cookies, e ver no Network se o documento inicial traz `Set-Cookie` (hoje o SSR só encaminha `cookie`, `useStorefrontShell.ts:18`).
3. **Qual o timeout real da borda DO → BFF → `api.`?** O `timeout_seconds: 5` do spec é de **health check** (`.do/app.subdomains.yaml:656,663`), não de requisição. [NÃO VERIFICADO]
4. **O dono estava logado?** Muda tudo: para cliente autenticado, `SessionAuthentication.enforce_csrf` **passa a valer** (`authentication.py:126-130`; o login do cliente usa `django.contrib.auth.login`, `shop/services/auth.py:439` e `:560`) e um token rotacionado por login vira 403. Não consegui determinar em que estado de sessão ele estava.
5. **`RATELIMIT_IP_META_KEY` resolve o IP do cliente também na perna da semente?** `ensureDjangoCsrfCookie` (`djangoProxy.ts:62-69`) **não** encaminha `x-forwarded-for` nem `x-shopman-proxy-secret`, ao contrário do PUT (`:164-174`). O GET `storefront/cart/` não é rate-limited (`_request_is_rate_limited` só aparece em `surface.py:629, 734, 1038`), então **acho** que é inócuo hoje — mas é uma inconsistência entre as duas pernas do mesmo clique que merece olhar. [INFERÊNCIA]
6. **Não executei nada em runtime.** Tudo aqui é leitura estática + leitura do fonte do Django 6.1.1 e do DRF instalados no `.venv` da raiz. Não rodei a suíte de testes do storefront nem subi o app. **Nenhum comando git mutante foi usado.**

---

## Anexo — comandos de verificação usados (todos somente leitura)

```
grep -rn "Não foi possível adicionar" <worktree>            # 0 resultados
grep -rn "não foi possível" surfaces/storefront-nuxt shopman # 60+ hits, nenhum de "adicionar"
sed -n '1,80p' .venv/.../rest_framework/authentication.py   # :112-148 SessionAuthentication
grep -n "csrf_exempt" .venv/.../rest_framework/views.py     # :149
grep -n "def process_request|process_view|process_response|NEEDS_UPDATE" .venv/.../django/middleware/csrf.py
git log --oneline -40 -- surfaces/storefront-nuxt/{app/composables/useCartState.ts,server/utils/djangoProxy.ts,app/composables/useShopmanCsrfHeaders.ts}
git status --porcelain                                      # limpo (só este relatório é novo)
```
