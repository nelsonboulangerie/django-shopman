# Migração Nuxt 4.5 — como subir sem quebrar

> **Estado:** plano aberto, aguardando execução. Medições de 2026-08-19 contra
> `nuxt@4.5.2` (as superfícies rodam `4.4.5`).
> **Origem:** triagem dos 284 alertas do Dependabot (PR #225). A conclusão de lá:
> nenhum alerta alcança produção, mas seis advisories de SSR do Nuxt só estão
> inertes por causa de config que um commit futuro pode virar sem querer.

## 1. Por que subir, já que nada é explorável hoje

As seis advisories de SSR do Nuxt (`4.4.5` → corrigidas em `4.5.1`) são todas
condicionais, e hoje **nenhuma condição existe** no repo — sem `.server.vue`, sem
`vue.runtimeCompiler`, sem `cache`/`swr`/`isr` em `routeRules`, e o handler
`/__nuxt_island/**` compila para stub vazio em build de produção.

O problema é a distância entre "inerte" e "seguro". Duas linhas de config
separam uma da outra:

- **Um `swr: true`** adicionado em `routeRules` por performance liga a extração de
  payload — e com ela o `GHSA-wm8w-6qjm-cv43`, que serve o payload SSR de um
  cliente autenticado para o próximo que pedir `/<page>/_payload.json`. Numa loja,
  esse payload é sacola, conta e pedido.
- **O primeiro `.server.vue`** monta o handler real de island no lugar do stub, e
  com ele os dois DoS não autenticados.

Nenhuma dessas mudanças dispararia alerta. O alerta já está aberto **hoje** e
seria fechado por qualquer um dos dois commits sem ninguém perceber. É por isso
que a migração vale ser agendada — não porque há fogo.

## 2. O que o gate mediu (2026-08-19)

`npm update nuxt` (4.4.5 → 4.5.2, um **minor** dentro do `^4.4.5` já declarado)
a partir de suítes 100% verdes:

| Superfície | Baseline | Com 4.5.2 |
|---|---|---|
| `storefront-nuxt` | 381/381 testes ✓, 0 erros TS | 16 falhas + 1 suíte sem coletar, 21 erros TS |
| `pos-nuxt` | 248/248 testes ✓, 0 erros TS | 6 falhas, 10 erros TS |

Verificado contra baseline limpo e re-rodado com `.nuxt` apagado — não é tipo
gerado velho, não é flake.

### ✅ O achado que barateia tudo: `npm run build` **passa**

```
BUILD_EXIT=0
.output/server/index.mjs gerado — Σ 124 MB (32,2 MB gzip)
```

O bundle de produção do `storefront-nuxt` sai inteiro no 4.5.2. **A quebra é de
typecheck e de teste, não de runtime.** Isso reclassifica a migração: não é
"reescrever o app", é "consertar o contrato de tipos e a estratégia de mock".

> ⚠️ O build passar prova que compila e empacota — **não** prova que as telas
> renderizam. A prova de tela é a Fase 2 (staging), não este parágrafo.

## 3. As quatro categorias de quebra

A quebra parece grande e não é: são 4 causas, e duas delas são de uma linha.

### Categoria A — `vi.stubGlobal('$fetch', …)` não intercepta mais

**Impacto:** storefront 5 arquivos / 16 testes · PDV 2 arquivos / 6 testes.
**Causa confirmada na fonte primária. Correção provada.**

O changelog do 4.5.0 diz, em uma linha:

> **Auto-import `$fetch` where possible** ([nuxt#35581](https://github.com/nuxt/nuxt/pull/35581))
> — corrige casos de `$fetch.create` no topo do arquivo sob o formato de saída do Rolldown.

É isso. `$fetch` deixou de ser lido da global e passou a ser **auto-import**. Os
testes mockam `globalThis.$fetch`; o código de app resolve o binding
auto-importado. O mock passa ao lado e a chamada vai para o `ofetch` de verdade:

```
FetchError: [PUT] "/api/v1/cart/skus/CROISSANT/": 404
  Cannot find any path matching /api/v1/cart/skus/CROISSANT/.
```

Subir `@nuxt/test-utils` para 4.1.0 **não** resolve (testado) — não é bug da
lib, é mudança de onde o símbolo vem.

**A correção é o `mockNuxtImport`**, que é justamente a ferramenta para
auto-import. Como o valor precisa variar por teste, o espião nasce em
`vi.hoisted`:

```ts
// Nuxt 4.5 passou a AUTO-IMPORTAR `$fetch` (nuxt#35581), então `vi.stubGlobal`
// não intercepta mais.
const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)

beforeEach(() => { fetchMock.mockReset() })

it('…', async () => {
  const $fetch = fetchMock.mockResolvedValue({})   // no lugar do vi.stubGlobal
  // resto do teste intacto
})
```

Aplicado em `tests/composables/useFavoritesState.test.ts` como piloto:
**4/4 passando em `nuxt@4.5.2`**, com 12 linhas adicionadas e 9 removidas. O
corpo das asserções não muda — só a origem do espião.

#### ⛔ A restrição que define o plano: o padrão **não** é retrocompatível

O mesmo arquivo corrigido, rodado em `4.4.5`:

```
Error: Cannot find import "$fetch" to mock
  Plugin: nuxt:vitest:mock-transform
```

Em 4.4.5 `$fetch` não é auto-import, então não há o que mockar. **Não dá para
migrar os mocks antes do bump.** Mock e bump têm de entrar juntos, atomicamente,
por superfície. Isso invalida qualquer plano em que os testes são preparados
primeiro — inclusive a primeira versão deste documento.

Arquivos: `tests/components/{cartQuantityAction,stockNotifyButton}.test.ts`,
`tests/composables/{useCartState,useFavoritesState,useReorder}.test.ts` (storefront);
`tests/composables/{usePosAction,usePosSale.sale}.test.ts` (PDV).

### Categoria B — auto-import some do **tipo** do template

**Impacto:** storefront 16 erros · PDV 9 erros. Só tipo — o build passa.
**Não é dívida nossa: é regressão conhecida do `nuxt typecheck`, upstream.**

Símbolos usados em `<template>` deixam de existir no tipo da instância:

| Símbolo | Onde vive | Ocorrências |
|---|---|---|
| `formatCount` | `app/utils/display.ts` | 9 (storefront) |
| `compactUnitWeightLabel` | `app/utils/display.ts` | 3 (storefront) |
| `orderTrackingRoute` | `app/utils/routes.ts` | 2 (storefront) |
| `navigateTo` | do próprio Nuxt | 2 storefront + 9 PDV |

O [nuxt#34562](https://github.com/nuxt/nuxt/issues/34562) descreve exatamente
isto — inclusive o `colorMode` da Categoria C, no mesmo issue. A causa: o Nuxt 4
adotou **project references** do TypeScript, e o `nuxt typecheck` roda
`vue-tsc -b --noEmit` (modo build); em modo build o TS não resolve as declarações
globais de `.nuxt/types/imports.d.ts` através da fronteira de projeto.

É regressão que vai e volta entre patches (relatada em 4.3.0, 4.3.1 e 4.4.2; o
nosso 4.4.5 está limpo; o 4.5.2 volta a falhar). **Consequência prática: não
gastar esforço "consertando" isto no nosso código.** O caminho é acompanhar o
upstream e, se preciso, um ajuste de `tsconfig`/flag de typecheck — nunca
espalhar import explícito por 25 sítios para contornar bug de terceiro.

### Categoria C — deriva de tipo de módulo/lib

**Impacto:** 5 erros no storefront, 1 no PDV.

- **`$colorMode` (3 storefront + 1 PDV)** — mesmo issue #34562 da Categoria B.
  Não é problema do `@nuxtjs/color-mode`. Some junto quando o upstream resolver.
- **`useShopTheme.ts` — `useHead`.** Este é real e declarado: as notas do 4.5
  dizem que o **unhead v3 introduz type-narrowing no `useHead`, "which can be a
  breaking type change"**. Ajuste nosso, pequeno e legítimo.
- **`Ui/Nav/Item.vue` — props do `NuxtLink`.** Único erro sem origem confirmada;
  investigar na Fase 2.

Ou seja: dos 31 erros de tipo entre as duas superfícies, **28 são o issue
upstream** e **2 são trabalho nosso de verdade**.

### Categoria D — bug nosso, que o vite 7 engolia

**Impacto:** 1 arquivo, mas derruba 17 testes de uma vez.

`tests/checkoutFlow.test.ts` importa `isCheckoutDateUnavailable` **duas vezes no
mesmo import** (linhas 8 e 11). O esbuild (vite 7) tolerava; o oxc (vite 8, que
entra de carona com o nuxt 4.5) rejeita:

```
[PARSE_ERROR] Identifier `isCheckoutDateUnavailable` has already been declared
```

Isto **não** é problema do Nuxt. É dívida latente que só ficou visível agora, e
está corrigida neste mesmo commit — ver Fase 0.

## 4. O plano

O princípio: **uma superfície por vez, e dentro dela tudo junto.** Como a
correção do mock não roda em 4.4.5 (§3, Categoria A), não existe fase de
preparação — o bump e seus consertos são um commit só, por superfície. A
granularidade que protege é a superfície, não o tipo de mudança.

### Fase 0 — a dívida que não depende do Nuxt ✅ (feita neste commit)

Remover o import duplicado em `tests/checkoutFlow.test.ts`. Vale por si: é um
identificador redeclarado que hoje só não explode por tolerância do bundler.
Zero risco, zero relação com o bump.

### Fase 1 — decidir o que fazer com a Categoria B (o gate do plano)

As duas perguntas que estavam em aberto **já foram respondidas** (§3): a causa da
Categoria A é o nuxt#35581 e a correção está provada; a Categoria B é o
nuxt#34562, upstream. Sobra uma decisão, e ela é de política, não de técnica:

**Aceitamos subir com o `typecheck` vermelho por causa de bug de terceiro, ou
seguramos a frota em 4.4.5 até o upstream resolver?**

Três saídas, em ordem de preferência:

1. **Esperar o upstream.** Zero trabalho nosso, zero gambiarra. Custo: a frota
   fica em 4.4.5 por tempo indeterminado — aceitável, já que a alcançabilidade
   hoje é nula (§1). Recomendada **se** houver correção à vista no issue.
2. **Ajustar o typecheck.** O issue aponta o modo build (`vue-tsc -b`) com
   project references como a causa. Se houver flag ou `tsconfig` que restaure a
   resolução dos tipos globais sem desligar a checagem, é a saída limpa.
   **Investigar antes de escolher a 3.**
3. **Último recurso: import explícito nos 25 sítios.** Espalha ruído pelo código
   para contornar bug de terceiro, e deixa resíduo quando o upstream consertar.
   Só com decisão consciente e um `# DEPRECATED` apontando para o issue.

⚠️ **Nunca** desligar o `typecheck` no gate das superfícies para fazer passar.

### Fase 2 — o bump, por superfície, **atômico**

Descoberta que reorganizou este plano: a correção do mock **não roda em 4.4.5**
(`Cannot find import "$fetch" to mock`). Logo não existe fase de preparação — em
cada superfície, num único commit, entram juntos:

1. `npx nuxt upgrade --dedupe` (o caminho oficial; ver §"caminho de upgrade")
2. a conversão dos testes da Categoria A para `mockNuxtImport` + `vi.hoisted`
3. o ajuste do `useHead` (unhead v3) e do `NuxtLink`, se a superfície tiver
4. o que a Fase 1 decidiu sobre a Categoria B

Ordem deliberada, da menor consequência para a maior:

```
bi-nuxt (já lá) → operator-kit → hub → marketing → kds → orders → production → pos → storefront
```

Ordem deliberada, da menor consequência para a maior:

```
bi-nuxt (já lá) → operator-kit → hub → marketing → kds → orders → production → pos → storefront
```

`pos` e `storefront` por último: são as duas únicas no spec de **produção**
(`.do/app.subdomains.yaml`). As demais são staging, onde um erro custa um
redeploy, não uma venda.

Gate por superfície, **os três, sem pular**:

```bash
npm run test && npm run typecheck && npm run build
```

E, para `pos` e `storefront`, uma passada de tela em staging antes do merge —
porque o build passar não prova que renderiza (ver §2).

#### O caminho de upgrade

Use **`npx nuxt upgrade --dedupe`**, não `npm update nuxt`. É o caminho oficial e
ele limpa `.nuxt` e deduplica a árvore.

Dito isso, medimos os dois: **dão os mesmos 21 erros de tipo no storefront**.
Então o `--dedupe` não é uma saída mágica — é higiene. Vale saber também que,
mesmo depois dele, sobra `@nuxt/kit@3.21.8` aninhado sob `@nuxt/test-utils`
(além do `4.5.2` da raiz). É dependência de ferramenta de teste, não do app, mas
é o primeiro lugar para olhar se algo estranho aparecer só nos testes.

### Fase 3 — fechar a porta

Com a frota em 4.5.x, os grupos do `.github/dependabot.yml` fazem o resto: o
grupo `nuxt-framework` passa a trazer os minors sozinho, num PR isolado, e o
gate das superfícies decide. Major segue fora do automático.

## 5. Critérios de pronto

- [ ] Os 9 lockfiles em `nuxt` ≥ 4.5.1.
- [ ] `npm run test`, `npm run typecheck` e `npm run build` verdes nas 9.
- [ ] Storefront e PDV conferidos em tela no staging.
- [ ] Os alertas de `nuxt`/`@nuxt/nitro-server` fechados no Dependabot.
- [ ] Padrão de mock de `$fetch` documentado, para o próximo teste nascer certo.
- [ ] Decisão da Fase 1 registrada — inclusive se a escolha foi *esperar*.

## 6. O que **não** fazer

- **`npm audit fix --force`.** Cruza majors sem cerimônia; o build morre no
  minuto 25 do deploy, na superfície que serve a loja.
- **Subir as 9 superfícies num PR só.** O gate perde a capacidade de dizer *qual*
  quebrou.
- **Subir `nuxt` junto com feature.** Foi por isso que o `dependabot.yml` colocou
  o framework em grupo próprio.
- **Tratar `npm run build` verde como prova de que funciona.** Ele prova que
  compila. Tela é tela.

## 7. Referências

**Upstream (o que sustenta o diagnóstico):**

- [Nuxt 4.5 — notas de release](https://nuxt.com/blog/v4-5) — Vite 8, Rspack 2,
  unhead v3 ("type-narrowing for `useHead`, which can be a breaking type change")
- [nuxt#35581](https://github.com/nuxt/nuxt/pull/35581) — "Auto-import `$fetch`
  where possible": a causa da Categoria A
- [nuxt#34562](https://github.com/nuxt/nuxt/issues/34562) — `$route`,
  `navigateTo` e `colorMode` fora do tipo da instância no typecheck: Categorias
  B e C
- [Guia oficial de upgrade](https://nuxt.com/docs/getting-started/upgrade)

**Interno:**

- PR #225 — triagem dos 284 alertas, `constraints.txt`, `dependabot.yml`
- `.github/dependabot.yml` — o grupo `nuxt-framework` e o porquê dele
- `@nuxt/nitro-server@4.4.5/dist/index.mjs:213-219` — o guard que faz
  `/__nuxt_island/**` compilar para stub em produção
- [ADR-016](../decisions/adr-016-sse-first-realtime.md) — SSE, que também vive
  sobre o Nitro e merece atenção na Fase 2
