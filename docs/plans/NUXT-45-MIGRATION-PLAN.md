# Migração Nuxt 4.5 — como subir sem quebrar

> **Estado:** plano aberto. Medições de 2026-08-19 contra `nuxt@4.5.2` e
> `4.4.8` (as superfícies rodam `4.4.5`).
> **Revisão 3:** a bissecção encontrou a causa da Categoria B — **duplicata de
> `vue`** na árvore, conserto de uma linha (`vue: ^3.5.41`). Não era bug do Nuxt
> nem havia o que esperar do upstream. Com isso a migração deixa de ter parte
> bloqueada. Ver §3.
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
| `pos-nuxt` | 276/276 testes ✓, 0 erros TS | 6 falhas, 10 erros TS |

Verificado contra baseline limpo e re-rodado com `.nuxt` apagado — não é tipo
gerado velho, não é flake.

> ⚠️ Correção de medição: uma versão anterior registrou o baseline do PDV como
> `248/248` em 19 arquivos. O número certo é **276/276 em 20 arquivos** — a
> primeira medição rodou antes do `nuxt prepare` regenerar os tipos. A contagem
> de falhas (6) estava correta.

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

A quebra parece grande e não é: são 4 causas, **todas com causa conhecida e
caminho definido**. Nada depende de terceiros.

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
**✅ CAUSA ENCONTRADA: duplicata de `vue` na árvore. Conserto de uma linha.**

Símbolos usados em `<template>` deixam de existir no tipo da instância:

| Símbolo | Onde vive | Ocorrências |
|---|---|---|
| `formatCount` | `app/utils/display.ts` | 9 (storefront) |
| `compactUnitWeightLabel` | `app/utils/display.ts` | 3 (storefront) |
| `orderTrackingRoute` | `app/utils/routes.ts` | 2 (storefront) |
| `navigateTo` | do próprio Nuxt | 2 storefront + 9 PDV |

#### A causa, e o conserto

O Nuxt 4.5 exige `vue` ≥ 3.5.41. O nosso `package.json` declara `^3.5.34`, e o
npm resolveu a raiz para **3.5.34**, aninhando **3.5.41** dentro do `nuxt` e do
`@nuxt/nitro-server`:

```
3.5.34  <- node_modules/vue                              ← nossos componentes
3.5.41  <- node_modules/nuxt/node_modules/vue            ← o Nuxt
3.5.41  <- node_modules/@nuxt/nitro-server/node_modules/vue
```

`.nuxt/types/imports.d.ts` faz `declare module 'vue' { interface
ComponentCustomProperties { … } }`. Com duas cópias de `vue`, a augmentação dos
nossos auto-imports e a do Nuxt caem em **módulos diferentes** e não fundem. É
exatamente o que o erro dizia, e que passou despercebido: `$nuxt` aparece no tipo
da instância (augmentação do Nuxt aplicada) e `formatCount` não (a nossa, não).

**O conserto:**

```jsonc
// package.json de cada superfície
"vue": "^3.5.41"   // era ^3.5.34
```

Medido no `storefront-nuxt`, em 4.5.2:

| | erros de tipo |
|---|---|
| com `vue` duplicado | 21 |
| com `vue` deduplicado | **2** |

Os 2 que sobram são os da Categoria C — reais e nossos. No `pos-nuxt` o mesmo
conserto leva a **0 erros de tipo**.

#### Como isso foi encontrado (e o que foi descartado no caminho)

A bissecção descartou, em ordem: **módulos** (com `modules: []` os erros-assinatura
continuam), **o override `typescript.tsConfig`** (removê-lo piora — ele sustenta
os tipos do `google.maps`), e uma **referência quebrada** em `.nuxt/nuxt.d.ts`
(`./eslint-typegen.d.ts` não existe — é um defeito real, mas criar o arquivo não
muda nada).

O que virou a chave foi parar de mexer na config e **ler os tipos gerados**:
`formatCount` estava lá, correto, em `.nuxt/types/imports.d.ts:704`. Se o tipo é
gerado e não é visto, o problema não é geração — é identidade de módulo.

> 📌 Lição para a próxima: `$nuxt` presente e o resto ausente no mesmo tipo é
> assinatura de augmentação que não fundiu, ou seja, de pacote duplicado. Não é
> bug de framework.

#### Histórico: a atribuição ao upstream estava errada

Uma versão anterior deste documento dizia que isto era o
[nuxt#34562](https://github.com/nuxt/nuxt/issues/34562) e que bastava esperar o
upstream. Errado nas duas pontas: o issue está **fechado como `completed` desde
2026-04-02**, e não havia issue aberto com o sintoma. Foi casamento por
semelhança, não por evidência — e a causa real nem era do Nuxt.

O sinal que deveria ter contado desde o início: **não reproduzia em app mínimo**
(três tentativas, todas limpas). App mínimo tem uma cópia só do `vue`.

### Categoria C — deriva de tipo de módulo/lib

**Impacto:** 5 erros no storefront, 1 no PDV.

- **`$colorMode` (3 storefront + 1 PDV)** — era a mesma duplicata de `vue` da
  Categoria B. **Some com o `vue: ^3.5.41`.**
- **`useShopTheme.ts` — `useHead`.** Este é real e declarado: as notas do 4.5
  dizem que o **unhead v3 introduz type-narrowing no `useHead`, "which can be a
  breaking type change"**. Ajuste nosso, pequeno e legítimo. Específico do 4.5 —
  não aparece no 4.4.8.
- **`Ui/Nav/Item.vue` — props do `NuxtLink`.** Também só no 4.5; origem não
  confirmada. Sobrevive à deduplicação, então é trabalho nosso.

Dos 31 erros entre as duas superfícies, **29 somem com o `vue: ^3.5.41`** e
sobram **2**, ambos no storefront: o `useHead` (quebra declarada pelo unhead v3)
e o `NuxtLink`. O `pos-nuxt` fica em **zero**.

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

### Fase 1 — bissecção da Categoria B ✅ CONCLUÍDA

Era o gate do plano e está fechada: a causa é a **duplicata de `vue`** (§3,
Categoria B). Não havia decisão de política a tomar, nem espera pelo upstream —
havia um bug nosso de resolução de dependência, de uma linha.

Com isso o quadro do 4.5.2 muda por completo:

| | advisories abertas | `test` | `typecheck` | `build` |
|---|---|---|---|---|
| **4.4.5** (hoje) | **16** | ✓ | ✓ 0 | ✓ |
| **4.4.8** | **7** | ✓ | ✗ 19 | ✓ |
| **4.5.2** cru | **0** | ✗ 16 falhas | ✗ 21 | ✓ |
| **4.5.2 + `vue ^3.5.41`** | **0** | ✗ 16 falhas (Cat. A) | **✓ 2** | ✓ |

O 4.4.8 deixa de interessar: fecha só 7 das 16 e ainda paga 19 erros de tipo. E
o 4.5.2 deixa de ser uma escolha entre males — com o `vue` deduplicado ele fecha
**todas as 16 advisories** com **2 erros de tipo** e o único trabalho restante
sendo a migração de mock, já provada.

**Não há mais decisão pendente do dono.** O que existe é execução (Fase 2).

### Fase 2 — o bump, por superfície, **atômico**

Descoberta que reorganizou este plano: a correção do mock **não roda em 4.4.5**
(`Cannot find import "$fetch" to mock`). Logo não existe fase de preparação — em
cada superfície, num único commit, entram juntos:

1. `npx nuxt upgrade --dedupe` (o caminho oficial; ver §"caminho de upgrade")
2. **`vue: ^3.5.41` no `package.json`** — sem isto, 19 erros de tipo fantasma
   (§3, Categoria B). Conferir depois com
   `node -e "…"` ou `npm ls vue`: tem de haver **uma** cópia só.
3. a conversão dos testes da Categoria A para `mockNuxtImport` + `vi.hoisted`
4. o ajuste do `useHead` (unhead v3) e do `NuxtLink`, se a superfície tiver

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
- [x] Gatilho da Categoria B isolado: duplicata de `vue`.
- [ ] `npm ls vue` mostra **uma** versão em cada uma das 9 superfícies.

## 6. O que **não** fazer

- **`npm audit fix --force`.** Cruza majors sem cerimônia; o build morre no
  minuto 25 do deploy, na superfície que serve a loja.
- **Subir as 9 superfícies num PR só.** O gate perde a capacidade de dizer *qual*
  quebrou.
- **Subir `nuxt` junto com feature.** Foi por isso que o `dependabot.yml` colocou
  o framework em grupo próprio.
- **Tratar `npm run build` verde como prova de que funciona.** Ele prova que
  compila. Tela é tela.
- **Abrir issue upstream sem reprodução.** Tentado e recuado: não reproduz em app
  mínimo, então o relatório seria fechado — com razão.
- **Casar sintoma com issue fechado e chamar de causa.** Foi o erro da primeira
  versão deste documento; custou uma recomendação errada ("esperar o upstream").
  A causa real era duplicata de `vue` — nossa, e de uma linha.
- **Deixar `vue` frouxo em relação ao que o Nuxt exige.** Um range nosso mais
  velho que o do framework produz duas cópias, e augmentação de tipo que não
  funde não dá erro de instalação: dá 19 erros de tipo que parecem bug de
  terceiro.

## 7. Referências

**Upstream (o que sustenta o diagnóstico):**

- [Nuxt 4.5 — notas de release](https://nuxt.com/blog/v4-5) — Vite 8, Rspack 2,
  unhead v3 ("type-narrowing for `useHead`, which can be a breaking type change")
- [nuxt#35581](https://github.com/nuxt/nuxt/pull/35581) — "Auto-import `$fetch`
  where possible": a causa da Categoria A
- [nuxt#34562](https://github.com/nuxt/nuxt/issues/34562) — sintoma idêntico ao
  da Categoria B, mas **fechado como `completed` em 2026-04-02**. Fica como
  referência histórica, NÃO como a causa (ver a correção em §3)
- [Guia oficial de upgrade](https://nuxt.com/docs/getting-started/upgrade)

**Interno:**

- PR #225 — triagem dos 284 alertas, `constraints.txt`, `dependabot.yml`
- `.github/dependabot.yml` — o grupo `nuxt-framework` e o porquê dele
- `@nuxt/nitro-server@4.4.5/dist/index.mjs:213-219` — o guard que faz
  `/__nuxt_island/**` compilar para stub em produção
- [ADR-016](../decisions/adr-016-sse-first-realtime.md) — SSE, que também vive
  sobre o Nitro e merece atenção na Fase 2
