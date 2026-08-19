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
> renderizam. A prova de tela é a Fase 4 (staging), não este parágrafo.

## 3. As quatro categorias de quebra

A quebra parece grande e não é: são 4 causas, e duas delas são de uma linha.

### Categoria A — `vi.stubGlobal('$fetch', …)` não intercepta mais

**Impacto:** storefront 5 arquivos / 16 testes · PDV 2 arquivos / 6 testes.

Os testes mockam a global e o código de app chama `$fetch` auto-importado. No
4.4.5 isso resolvia para `globalThis.$fetch` e o mock pegava. No 4.5 não pega
mais: a chamada escapa para o `ofetch` real e bate no servidor nitro de teste.

```
FetchError: [PUT] "/api/v1/cart/skus/CROISSANT/": 404
  Cannot find any path matching /api/v1/cart/skus/CROISSANT/.
```

O sintoma é sempre o mesmo — ou `expected "vi.fn()" to be called once, but got 0
times`, ou um 404 do roteador. Subir `@nuxt/test-utils` para 4.1.0 **não**
resolve (testado).

Arquivos: `tests/components/{cartQuantityAction,stockNotifyButton}.test.ts`,
`tests/composables/{useCartState,useFavoritesState,useReorder}.test.ts` (storefront);
`tests/composables/{usePosAction,usePosSale.sale}.test.ts` (PDV).

### Categoria B — auto-import some do **tipo** do template

**Impacto:** storefront 16 erros · PDV 9 erros. Só tipo — o build passa.

Símbolos usados em `<template>` deixam de existir no tipo da instância:

| Símbolo | Onde vive | Ocorrências |
|---|---|---|
| `formatCount` | `app/utils/display.ts` | 9 (storefront) |
| `compactUnitWeightLabel` | `app/utils/display.ts` | 3 (storefront) |
| `orderTrackingRoute` | `app/utils/routes.ts` | 2 (storefront) |
| `navigateTo` | do próprio Nuxt | 2 storefront + 9 PDV |

Que `navigateTo` — auto-import do Nuxt, não nosso — apareça na lista é o que
sugere mudança no emissor de tipos do 4.5, não dívida nossa.

### Categoria C — deriva de tipo de módulo/lib

**Impacto:** 5 erros no storefront, 1 no PDV. Pontuais, cada um com dono próprio.

- `$colorMode` não existe no tipo (3 storefront + 1 PDV) — `@nuxtjs/color-mode`
  em `Ui/{Calendar,Datepicker,Sonner}.vue`.
- `Ui/Nav/Item.vue` — props do `NuxtLink` incompatíveis.
- `useShopTheme.ts` — `useHead` não aceita mais a forma passada (`UseHeadInput`).

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

O princípio: **nenhuma fase sobe `nuxt` antes das anteriores estarem verdes.** A
ordem existe para que, quando o bump entrar, ele seja a única variável.

### Fase 0 — a dívida que não depende do Nuxt ✅ (feita neste commit)

Remover o import duplicado em `tests/checkoutFlow.test.ts`. Vale por si: é um
identificador redeclarado que hoje só não explode por tolerância do bundler.
Zero risco, zero relação com o bump.

### Fase 1 — spike no `bi-nuxt` (a superfície que já está lá)

`bi-nuxt` **já roda `nuxt@4.5.2` limpo**, com 1 alerta low. É o laboratório
natural: nenhuma migração para fazer, e o padrão certo já vive lá.

Entregar deste spike, como documento curto ou ADR:

1. **O substituto do `vi.stubGlobal('$fetch')`.** Candidatos a avaliar, não
   escolha feita: `registerEndpoint` do `@nuxt/test-utils` (mocka no servidor, e
   é o caminho que a doc empurra), `mockNuxtImport`, ou injeção explícita de
   `$fetch` nos composables. ⚠️ **Ainda não determinei qual é o correto** — esta
   é a pergunta central do spike, e chutar aqui seria inventar.
2. **Se a Categoria B é bug do Nuxt ou mudança intencional.** Ler o changelog do
   4.5.0/4.5.1 e os issues, e decidir entre esperar correção upstream, declarar
   os utils explicitamente, ou ajustar o `imports` do `nuxt.config`. ⚠️ Também
   não determinado.
3. Confirmar que `bi-nuxt` não tem os sintomas por sorte (pode simplesmente não
   exercitar os caminhos), rodando os mesmos padrões lá.

Sem a Fase 1 respondida, as fases seguintes são chute. **Ela é o gate do plano.**

### Fase 2 — Categoria A, ainda em 4.4.5

Migrar os 7 arquivos de teste para o padrão escolhido na Fase 1, **sem subir o
Nuxt**. Se o padrão novo é correto, ele passa nas duas versões — e é exatamente
isso que torna o bump reversível depois.

Critério: `npm run test` verde em storefront e PDV, ainda em 4.4.5.

### Fase 3 — Categorias B e C, ainda em 4.4.5 no que der

O que for corrigível sem o bump (Categoria C provavelmente é: atualizar
`@nuxtjs/color-mode`, ajustar `useHead`, tipar o `NuxtLink`) entra aqui. A
Categoria B pode depender do bump para ser verificável — nesse caso ela migra
junto com a Fase 4, e o plano assume isso explicitamente.

### Fase 4 — o bump, uma superfície por vez

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

### Fase 5 — fechar a porta

Com a frota em 4.5.x, os grupos do `.github/dependabot.yml` fazem o resto: o
grupo `nuxt-framework` passa a trazer os minors sozinho, num PR isolado, e o
gate das superfícies decide. Major segue fora do automático.

## 5. Critérios de pronto

- [ ] Os 9 lockfiles em `nuxt` ≥ 4.5.1.
- [ ] `npm run test`, `npm run typecheck` e `npm run build` verdes nas 9.
- [ ] Storefront e PDV conferidos em tela no staging.
- [ ] Os alertas de `nuxt`/`@nuxt/nitro-server` fechados no Dependabot.
- [ ] Padrão de mock de `$fetch` documentado, para o próximo teste nascer certo.

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

- PR #225 — triagem dos 284 alertas, `constraints.txt`, `dependabot.yml`
- `.github/dependabot.yml` — o grupo `nuxt-framework` e o porquê dele
- `@nuxt/nitro-server@4.4.5/dist/index.mjs:213-219` — o guard que faz
  `/__nuxt_island/**` compilar para stub em produção
- [ADR-016](../decisions/adr-016-sse-first-realtime.md) — SSE, que também vive
  sobre o Nitro e merece atenção na Fase 4
