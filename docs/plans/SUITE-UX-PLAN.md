# SUITE-UX-PLAN — a suíte tem que parecer uma suíte

**Medido em 22/09/2026** sobre os nove apps de `surfaces/` + a layer `operator-kit`.
Três varreduras independentes (navegação e cabeçalhos · primitivas de UI · fronteira
entre apps e copy). Tudo abaixo com arquivo e linha na origem; aqui fica o número e a
consequência.

O pedido do dono, na íntegra: *"Trata-se de uma suíte, os apps funcionam em conjunto,
isso precisa refletir"* — e *"descubra maneiras de garantir o Omotenashi genuíno aos
operadores que ainda não enxergamos, visando o excelente funcionamento não somente de um
app isolado, mas também do todo."*

---

## 0. O diagnóstico em uma frase

Nenhum app está mal desenhado. **O que não existe é o entre.** Cada app resolveu bem o
seu problema, sozinho, e oito soluções boas e diferentes para o mesmo problema somam uma
suíte que o operador tem que reaprender a cada porta.

A prova mais barata: o token `--spacing-control: 2.75rem` (44px) existe desde sempre em
`operator-kit/app/assets/css/operator-theme.css:19`. Ele é respeitado 214 vezes no
Gestor, 10 no kit, 1 na Cozinha, 1 no Marketing e **zero** nos outros cinco. Não é
desleixo: é que ninguém tinha como saber que ele existia sem ler o CSS da layer.

**Corolário, e é a regra deste plano:** o que não tem peça compartilhada e trava
volta a divergir. Documentação aqui vale como raciocínio, não como mecanismo.

---

## 1. O que foi medido

### 1.1 Cabeçalho e navegação

Nenhum dos nove apps usa `app/layouts/` — **não existe um único arquivo de layout no
repositório**; todo o chrome é montado em `app/app.vue` ou, no PDV e na Cozinha, por
página.

Sete cabeçalhos escritos à mão, com quatro padronagens diferentes: `px-4 py-2.5` no
Gestor/B.I./Compras, `px-4 py-2` no PDV, `px-4 py-3` no Hub, `px-3 py-2 sm:px-4` no
Marketing. Cinco cópias do mesmo *segmented control*, com alturas de aba de `h-8` (32px,
B.I. e Compras), `h-11` e `min-h-control` (44px). `chipClass(active)` duplicado byte a
byte entre B.I. e Compras.

Declaração da navegação em quatro formas diferentes (array no componente de barra, array
no `app.vue` + `v-for`, `RailItem` escritos um a um, e nenhum arquivo de rotas
declarativo).

Busca em quatro implementações: a primitiva do kit (`UiSearchInput`, usada por 3 apps),
duas reimplementações quase idênticas na Produção, três campos crus no Compras (`h-10`,
abaixo do token) e uma no Marketing. **O Hub — launcher de oito apps — e o B.I. — oito
páginas de análise — não têm busca nenhuma.**

Preferência de visualização persistida de quatro maneiras: cookie, `localStorage`, query
na URL e `useState` sem persistir. Só o Gestor trata query/filtro/ordenação/scroll/foco
como contexto restaurável e endereçável por URL (`useOrdersContext.ts`).

### 1.2 Primitivas

| primitiva | cópias no repo | versões distintas |
|---|---|---|
| Botão (`Ui/Button.vue`) | 7 arquivos | 2 (tamanhos divergem: `h-9/h-11/h-14` no operador, `h-8/h-9/h-10` na loja) |
| Botão escrito à mão | — | **~86 strings de classe distintas** (36 só no Compras) |
| Input | 7 | 2 (`h-11 bg-background` × `h-9 bg-white`) |
| Rótulo de campo | **0 componentes compartilhados** | **8 dialetos** |
| Mensagem de erro de campo | **0** | **20+ strings** |
| Estado obrigatório | **0** | — |
| Badge | 6 | 2 |
| Chip/pílula | 2 componentes + markup | 2 + **127 strings distintas** em 148 usos |
| Mapa de cor de status | 6 módulos | **3 vocabulários incompatíveis** (Tailwind cru × tokens × sem cor) |
| Dialog | 6 conjuntos | 4 (o botão Fechar diz **"Close"** em inglês no PDV, Cozinha e Produção) |
| Overlay à mão (`fixed inset-0`) | **13 call sites** | 11 deles **sem trap de foco nem scroll-lock** |
| Alerta inline | 6 | 4 (dois usam cor crua onde há token) |
| Sino de notificação | 4 | 4 — inclusive **dois arquivos `AlertsBell.vue` diferentes com o mesmo nome** |
| Skeleton / estado vazio | 1 (só storefront) | **inexistente nos 8 apps de operador** |
| Tipografia semântica | 12 classes `.shop-*` na loja | **2.287 combos utilitários à mão** no operador |

A escala tipográfica do operador (`display · figure · title · body · label · micro`)
está escrita — **como comentário** em `operator-base.css:163-215`. Nenhuma linha dela
existe como CSS. É a definição de regra sem trava.

Cópias mortas: `orders-nuxt` carrega `Ui/Button.vue`, `Ui/Input.vue`, `Ui/Textarea.vue`,
`Ui/Badge.vue` e `Ui/Alert/*` no repositório e usa **zero** vezes — 125 `<button>`, 54
`<input>` e 10 `<textarea>` escritos à mão ao lado deles.

### 1.3 A fronteira entre os apps

**Não existe app switcher.** Existe uma porta, e ela é de volta: o ícone do app no topo
do `OperatorRail` vira seta e leva ao Shopman Apps. Os sete apps não-hub a passam.

**Quatro links de app para app em todo o repositório, e só UM carrega contexto:**

| de → para | carrega contexto? |
|---|---|
| PDV → Gestor (`PosSaleResult.vue`, "Abrir no gestor") | **sim** (`${ordersUrl}/${orderRef}`) |
| PDV → Produção (`closing.vue`, ×2, "Resolver na produção") | não — aponta para a raiz, e a tabela logo acima lista o `ref` de cada ordem |
| qualquer → Hub (rail) | n/a |

**Travessias que o texto manda fazer e a tela não oferece**: "confira no Gestor"
(`closeGuard.ts:83`), "Registre o recebimento no Gestor" (`PosPaymentWorkspace.vue:987`
e `:996`), "o consumo é registrado quando uma fornada é finalizada na Produção"
(`purchase.ts:952`), "Configure os canais no Admin" (`feeds.vue:293`). Quatro frases que
mandam o operador atravessar, e nenhuma delas é um link.

**Travessias inexistentes**: PDV→Cozinha, Cozinha→Gestor, Gestor→PDV, B.I.→Compras,
Produção→Gestor. O kit só publica três URLs de destino (`ordersUrl`, `posUrl`,
`productionUrl`) — **Cozinha, B.I., Compras e Marketing não são endereçáveis a partir de
nenhum app.**

**O Hub não mostra estado.** O launcher desenha oito tiles com rótulo e descrição e nada
mais: não diz se o caixa está aberto, quantos pedidos esperam, se há alerta. O operador
precisa entrar para descobrir se precisava entrar.

**Reimplementações do que o kit já tem**: `resilientEventSource` (3 apps usam, 4 abrem
`EventSource` cru), `useUserNotifications` (1 app usa, o Marketing lê o MESMO canal com
código próprio), `OperatorSessionUnavailable` (6 usam, Marketing e Hub reimplementam
cada um o seu), `MoreBelow` (**0 apps de operador usam** a peça que o kit tem com teste).

### 1.4 Copy

Onde a copy mora hoje, em ordem de grandeza:

- **18** chaves de operador no registro central do Omotenashi (e são só duas famílias:
  `ORDER_STATUS_*` e `PAYMENT_METHOD_*`) — contra 349 chaves da loja;
- **~546** interpolações vindas de *projections* Python (`*_label`, `*_display`);
- **~3.800** literais nos `.vue`/`.ts` dos apps.

Nenhum arquivo de `surfaces/` lê o Omotenashi. E a maior fatia da copy de operador não
está em nenhum dos dois lugares que a régua de `docs/reference/omotenashi-copy.md`
varre: está em `app/presentation/*.ts` — que é exatamente onde D6, D7 e D8 se concentram.

Os oito defeitos nomeados, hoje, nos apps de operador: **os oito estão presentes.** O
mais volumoso é a mensagem de erro que não diz o que fazer — **63 mensagens "Falha …",
12 com saída**; no PDV, onde tem cliente esperando no balcão, são **33 com 1**.

O jargão que mais alcança gente: `capacity.ts:70` e `:72` dizem *"Medido pelo sistema do
contêiner"* / *"Estimado pelos processos do serviço"* — **no rail dos oito apps**, ao
lado do nome do operador.

Vocabulário do mesmo conceito com nomes diferentes: *lote*/*fornada*/*ordem de produção*
(três nomes, dois deles no MESMO arquivo), *faixa* de preço × *faixa* de processamento
no Marketing, *Tela do cliente* nomeando dois objetos diferentes em dois apps, o Gestor
com três grafias, "Tentar de novo" (30) × "Tentar novamente" (5), e a descrição de cada
app diferente entre o tile do launcher e o manifesto — **nos sete**.

---

## 2. O sistema proposto

Um princípio ordena o resto: **o operador aprende a suíte uma vez.** Toda peça abaixo
existe para que a segunda tela não exija reaprender a primeira.

### 2.1 Anatomia única de tela

```
┌─ OperatorRail ─┬──────────────────────────────────────────────┐
│ identidade +   │  OperatorAppBar   seções · atenção · atalho  │  ← quem sou, onde estou
│ volta ao Hub   ├──────────────────────────────────────────────┤
│ operador       │  UiToolbar        busca · filtros · visão    │  ← o que estou olhando
│ capacidade     ├──────────────────────────────────────────────┤
│ tema · girar   │  conteúdo                                    │  ← o trabalho
│                ├──────────────────────────────────────────────┤
│                │  MoreBelow / ação primária fixa              │  ← tem mais / o próximo passo
└────────────────┴──────────────────────────────────────────────┘
```

Quatro faixas, sempre na mesma ordem, sempre com o mesmo significado. Um app pode não
ter uma delas; **nenhum app inventa uma quinta.**

- **Rail** (existe): identidade, volta ao Hub, operador, capacidade, tema, giro.
- **Barra de seções** (`OperatorAppBar` — **entregue**, §3.1): onde estou dentro do app.
- **Barra de trabalho** (`UiToolbar` — existe, 1 app usa): o que estou olhando — busca,
  filtros, visão, ações da lista.
- **Rodapé de conteúdo**: `<MoreBelow />` e, onde houver, a ação primária que não some.

### 2.2 Régua de controle

Um número: **44px** (`--spacing-control`) para tudo que se toca. `h-8` e `h-10` em
controle são defeito, não escolha — a mão do operador está ocupada, molhada ou com luva.
Chip informativo (`<span>`, não clicável) fica livre.

### 2.3 Tipografia com nome

Os seis papéis já escritos em `operator-base.css:163-215` viram CSS de verdade
(`op-display`, `op-figure`, `op-title`, `op-body`, `op-label`, `op-micro`), como as 12
classes `.shop-*` da loja já são. Enquanto forem comentário, os 2.287 combos à mão
continuam sendo a única verdade.

### 2.4 Status: um vocabulário, não seis

Um módulo `operator-kit/app/presentation/status.ts` com o mapa único
`estado → {tom, rótulo, ponto}`, em **tokens** (`success`/`warning`/`danger`/`info`),
nunca em paleta crua do Tailwind. Hoje são seis mapas e três vocabulários; o mesmo
"atrasado" é `red-500` na Cozinha, `destructive` no Compras e nada no PDV.

### 2.5 Campo de formulário com contrato

`UiField` (rótulo + obrigatório + dica + erro + `aria-describedby`), porque hoje são 8
dialetos de rótulo, 20+ strings de erro, zero marcação de obrigatório e três apps sem
nenhum `role="alert"`. Erro de campo sem `aria-live` é erro que o operador não vê quando
está olhando para o produto, não para a tela.

### 2.6 Overlay com uma porta

Toda camada por cima passa por `UiDialog`/`UiSheet` (trap de foco, scroll-lock e a
correção de teclado virtual do `operator-base.css` já vêm juntos). Os 13 `fixed inset-0`
à mão — 11 sem trap nem lock — viram uma lista fechada que não cresce.

### 2.7 Vazio, carregando e erro como peça

`UiEmpty` e `UiSkeleton` existem na loja (56 e 33 usos) e **não existem no operador**.
Estado vazio é onde a tela mais fala com quem não sabe o que fazer: ele nomeia o espaço,
diz por que está vazio e oferece o gesto. "Nada por aqui agora." não faz nenhum dos três.

### 2.8 A fronteira: o Hub deixa de ser lista e vira painel

O launcher mostra estado — caixa aberto, pedidos esperando, alerta de canal, fornada em
curso —, e cada tile leva ao lugar exato. Hoje o operador entra em cada app para
descobrir se precisava entrar. Isto exige publicar as URLs das quatro superfícies que
ainda não são endereçáveis (Cozinha, B.I., Compras, Marketing) e completar os atalhos do
manifesto, que hoje conhecem 3 de 7 destinos.

E **toda frase que manda atravessar vira link com contexto**. "Resolver na produção" leva
à ordem, não à raiz. É o padrão que o PDV→Gestor já acerta sozinho.

### 2.9 Omotenashi que ainda não enxergávamos

Quatro coisas que a medição revelou e que não estavam em nenhuma lista:

1. **O erro que não diz o que fazer é o defeito mais caro da casa** — 63 mensagens, 12
   com saída, e a pior concentração está no balcão. Não é copy: é o operador parado com
   cliente na frente.
2. **A palavra do engenheiro chega ao operador pelo rail**, o lugar que aparece em todas
   as telas dos oito apps. "Contêiner" e "processos do serviço" não são coisas da
   padaria.
3. **O atalho só é ensinado onde alguém pensou em ensinar.** A Produção imprime a tecla
   na própria aba e no campo de busca; os outros sete têm atalhos que ninguém descobre.
   Atalho não descoberto é atalho que não existe.
4. **O app não sabe dizer que está velho.** Só 2 dos 8 apps reconciliam ao reconectar
   (`onReconnect`); os outros seis montam o banner de offline e ignoram o gancho — a tela
   volta do offline mostrando o que estava lá antes, sem dizer que é passado.

---

## 3. Os work packages, em ordem de dívida paga por linha mexida

### 3.1 `WP-UX-1` — barra de seções canônica ✅ ENTREGUE

`OperatorAppBar` + `activeSectionKey()` puro, adotado por Gestor, B.I., Marketing e
Compras. Corrige os alvos de toque de 32px do B.I. e do Compras, espalha a revelação da
aba ativa (que só o Marketing tinha) e o `aria-current`, e ensina a tecla na própria aba
(que só a Produção tinha). Trava: `tests/guardrails.appBar.test.ts`, com a lista fechada
dos cabeçalhos ricos ainda não convertidos.

### 3.2 `WP-UX-2` — barra de trabalho canônica

`UiToolbar` + `UiSearchInput` + `UiFilterChip` + visão persistida por URL em todos os
apps de lista. Mata as quatro implementações de busca e os três campos `h-10` do
Compras; leva busca ao Hub e ao B.I., que não têm. Trava: varredura que recusa
`<input type="search">` cru fora da primitiva.

### 3.3 `WP-UX-3` — erro que diz o que fazer

As 63 mensagens "Falha …", começando pelas 33 do PDV. Formato: **o que aconteceu + o que
sobrevive + o que fazer agora**, e nunca "tente de novo" onde repetir pode duplicar
pagamento ou movimento de caixa. Trava: varredura que cobra um gesto em toda mensagem de
falha, com exceções declaradas.
*(Em execução — ver §5.)*

### 3.4 `WP-UX-4` — jargão fora da tela

Começando pelo rail dos oito apps. Trava: a varredura de vocabulário que hoje recusa uma
palavra (`aparelh`) passa a recusar a lista de termos de engenharia com tradução
declarada. *(Em execução — ver §5.)*

### 3.5 `WP-UX-5` — tipografia e status com nome

As seis classes de papel viram CSS; o mapa de status vira módulo único em tokens. Trava:
recusar `text-(red|amber|green|blue)-\d00` em `app/presentation/**` e em template.

### 3.6 `WP-UX-6` — campo, vazio, carregando

`UiField`, `UiEmpty`, `UiSkeleton` no kit, adotados app a app. Trava: recusar `<label>`
com classe de tipografia solta e `animate-pulse` fora da primitiva.

### 3.7 `WP-UX-7` — a fronteira

Publicar as quatro URLs que faltam, completar os atalhos do manifesto, transformar as
quatro frases-que-mandam-atravessar em links com contexto, e o Hub com estado.
*(A primeira metade está em execução — ver §5.)*

### 3.8 `WP-UX-8` — overlays e cópias mortas

Os 13 `fixed inset-0` para as primitivas; apagar os `Ui/*` que existem com zero uso
(Gestor, B.I., Cozinha); uma versão só de `Dialog/Content.vue` — e o botão "Close" em
inglês some junto.

### 3.9 `WP-UX-9` — os cabeçalhos ricos

PDV, Cozinha e Produção sobre o `OperatorAppBar`, com os slots que cada um precisa
(comanda editável, relógio e dia operacional, progresso e timers). É o WP com mais risco
de regressão visual e o único que precisa de retrato antes/depois.

---

## 4. O que era decisão do dono — **respondido em 22/09/2026**

As cinco foram decididas de uma vez. Ficam aqui com a resposta em vez de sumirem, porque
esta seção é o que a próxima leitura procura. **Nenhuma se reabre** — o de-para completo, com
o lugar onde cada uma é cobrada, está em
[`docs/reference/suite-vocabulary.md`](../reference/suite-vocabulary.md) §1.

1. **"lote" × "fornada" × "ordem de produção"** → **lote**, *"genérico mesmo"*: fornada só
   serve para o que vai ao forno, e a casa produz coisa que não vai. Nas superfícies de
   **operador**; a **loja fica com fornada**, e o texto que o **cliente** lê no Marketing
   também. Cobrado pela trava `guardrails.vocabulary.test.ts`, que varre só texto de tela —
   comentário sobre o forno continua dizendo a verdade.
2. **"faixa"** no Marketing → a decisão **já existia** e a pergunta era retrabalho:
   **"Faixa de preço" fica** (conceito de negócio) e a *lane* de processamento passa a ser
   nomeada **plataforma**. Está em [`omotenashi-copy.md`](../reference/omotenashi-copy.md)
   §D7b(b).
3. **"Tela do cliente"** → fica com o monitor do balcão do **PDV**; o painel público da
   **Cozinha** vira **"Painel de retirada"**. A rota `/pickup` não muda: URL é em inglês, e
   isto é sobre o texto da tela.
4. **`RevPASH` e `RFM`** → **traduzir**, *"jargão a traduzir, com toda certeza"*. Identificador,
   campo e comentário continuam em inglês, para quem mantém achar a literatura.
5. **O Hub vira painel com estado** → **sim**, aprovado como útil. Fica como WP neste plano, e
   depois da varredura de vocabulário, que mexe nos mesmos tiles e nas mesmas projections.

---

## 5. Estado da esteira

| WP | estado |
|---|---|
| WP-UX-1 barra de seções | PR aberta (esta) — Gestor, B.I., Marketing e Compras |
| WP-UX-3 erro com saída (PDV) | **PR #977**, na fila — 38 mensagens reescritas |
| WP-UX-4 jargão e rótulos | **PR #978** — 31 frases; aguarda baseline visual do Marketing |
| WP-UX-7 (1ª metade) deep links com contexto | **PR #976**, na fila — o link do fechamento carrega `?date=&q=<ref>` |
| WP-UX-2, 5, 6, 8, 9 | não iniciados |

---

## Referências

- `surfaces/operator-kit/README.md` — contrato das peças da layer
- `docs/reference/omotenashi-copy.md` — os oito defeitos de copy com nome
- `docs/reference/marketing-surface-contract.md` — contrato factual do Marketing
- `docs/decisions/adr-026-operator-surface-security-envelope.md` — envelope de segurança
