# Auditoria adversarial de UX de operador — superfícies Nuxt

> ⚠️ **SEVERIDADE REVISADA — leia [`verify-04-05-ux.md`](verify-04-05-ux.md) antes de agir por este laudo.**
> 
> Um passe de refutação em 01/09 atacou cada P0 deste arquivo com uma régua única
> (P0 = perde dinheiro, corrompe dado, viola segurança, ou impede tarefa central sem
> contorno). **12 P0 alegados → 0 sobreviveram como P0.** A entrada de compras "sem idempotência" foi REFUTADA por inteiro: `confirm_receipt` usa `run_idempotent_mutation`. Este laudo é o que mais sofreu com calibragem de severidade.
> 
> As contagens NO CORPO deste arquivo são as originais e estão infladas. O fato de
> cada achado quase sempre se sustenta; a **severidade** não.

Escopo: `surfaces/pos-nuxt`, `kds-nuxt`, `orders-nuxt`, `production-nuxt`, `hub-nuxt`,
`marketing-nuxt`, `bi-nuxt`, `purchase-nuxt` e a layer compartilhada `operator-kit`.
Leitura estática (read-only). Nenhum teste executado, nenhum arquivo alterado.

Personas usadas em cada tela: **dono** (todas as permissões) · **atendente júnior**
(limitada) · **padeiro** (só produção) · **novato no dia um** · **quem chega numa tela
que outro operador deixou aberta**.

Nota de contexto: este código é, no geral, de qualidade muito acima da média. O padrão
de idempotência do caixa (`usePosCashSession`), a captura unificada de crachá/PIN, o
`boardDisplay/isStale` da produção e a classificação de falha da Central são
exemplares. **Quase todos os achados abaixo são pontos onde um padrão que a casa já
domina não foi aplicado de forma consistente** — a mesma superfície resolve o problema
numa tela e o deixa aberto na vizinha.

## Sumário

| | P0 | P1 | P2 |
|---|---|---|---|
| pos-nuxt | 1 | 13 | 5 |
| kds-nuxt | — | 7 | 4 |
| production-nuxt | 6 | 16 | 9 |
| orders-nuxt | 1 | 16 | 10 |
| hub-nuxt | — | — | 5 |
| marketing-nuxt | 2 | — | 1 |
| purchase-nuxt | 1 | 1 | — |
| bi-nuxt | — | 1 | 1 |
| operator-kit (cross-cutting) | 1 | 8 | 2 |
| **total** | **12** | **62** | **37** |

Três padrões atravessam quase tudo e valem ser corrigidos como **regra**, não caso a caso:

1. **Falhar aberto no canal errado.** `error` do `useFetch` é descartado e o estado
   vazio assume o lugar: "Nenhum alerta agora", "Nenhuma estação configurada",
   "Nenhum feed", "Nenhum operador habilitado", tela em branco. Em alerta, permissão e
   identidade, omissão tem que ser restritiva.
2. **A tela não diz se está atual.** Três composables calculam `realtime` honestamente
   (`usePosEvents`, `useOrderEvents`, `useKdsBoard`) e as telas de operador **jogam o
   valor fora**. Só o painel do cliente (`/pickup`) e o board do Gestor o mostram.
3. **Mutação sem trava e sem eco.** Botão que não desabilita durante o envio, mensagem
   de timeout que afirma "não aconteceu", e retentativa sem chave de idempotência.

---

## pos-nuxt

### Autorização do gerente (`PosManagerAuthDialog` / `presentation/managerAuth`)

**[P0] O gerente assina a sangria sem ver o valor.**
`surfaces/pos-nuxt/app/presentation/managerAuth.ts:46-49` +
`surfaces/pos-nuxt/app/components/PosManagerAuthDialog.vue:103-104`

O diálogo mostra só `title` + `reason`: para `cash_out` isso é "Autorizar retirada da
gaveta" / "Sai dinheiro da gaveta." — **nunca o valor nem o motivo**. O gerente digita o
PIN (ou passa o crachá) numa tela que não diz se são R$ 200 ou R$ 2.000, e o servidor
grava a assinatura dele em `Entry.approved_by` contra um número que ele não leu. O
propósito inteiro da segunda assinatura é que alguém confira; hoje é um carimbo cego.
Idem `refund_cash` ("Sai dinheiro da gaveta.", sem pedido nem valor) e `serve_change`.

Comparar com o cuidado da própria casa em `pages/session/index.vue:548-555` (*Fechar
caixa*, que ecoa o valor contado). O ato mais auditado do PDV tem a confirmação mais fraca.

**Correção:** prop `detail?: string` no `PosManagerAuthDialog`, em destaque abaixo do
`reason`, preenchida nos três pontos de chamada.

**[P1] Cancelar venda não mostra o valor nem o que acontece com o dinheiro.**
`surfaces/pos-nuxt/app/components/PosCancelSaleDialog.vue:59-64`

Não diz **quanto**, não diz que a NFC-e emitida é cancelada junto, e não diz que numa
venda em dinheiro a devolução fica **pendente na sessão de caixa** até alguém entregar
as notas (`composables/usePosCashSession.ts:316-336`). O operador cancela achando que acabou.

**[P1] `cancelarComAprovacao` não manda chave de idempotência.**
`surfaces/pos-nuxt/app/composables/usePosSale.ts:1787-1826` — diferente de `close_sale`
(que reusa `cart.clientRequestId`, `:1433`) e de todo o caixa (`chaveDoGesto`). Na queda
de 4G o operador lê "Falha ao cancelar venda." sem saber se cancelou.

### Sessão de caixa (`pages/session/index.vue`)

**[P1] Sangria e suprimento não têm confirmação com eco do valor.**
`surfaces/pos-nuxt/app/pages/session/index.vue:261-276`

*Fechar caixa* confirma em dois passos com eco. O **movimento de caixa** — que escreve
linha no livro imutável e abre a gaveta — dispara direto. Na sangria o PIN do gerente
serve de confirmação de fato, mas ele não vê o valor (P0 acima); e o **suprimento não
pede PIN nenhum**: um dígito a mais entra no livro sem nenhuma pergunta.

**[P1] A chave de replay do caixa tem um só slot — outro gesto no meio a perde.**
`surfaces/pos-nuxt/app/composables/usePosCashSession.ts:86-99`

`ultimaTentativa` guarda **uma** assinatura. Cenário real: sangria de R$ 200 dá timeout
(chave guardada) → o operador abre a gaveta para conferir (`drawer_open` passa pelo mesmo
`run()` e **sobrescreve o slot**) → volta e refaz a sangria → **chave nova → duas linhas
de R$ 200 no livro imutável**. É exatamente o modo de falha que o comentário das linhas
70-85 diz estar prevenindo.

**Correção:** `Map<assinatura, chave>` com poda por idade (ex. 10 min).

**[P1] Mensagem de timeout de dinheiro não diz o que fazer.**
`usePosCashSession.ts:117` — com status 0 o operador lê "Falha ao registrar movimento."
e não sabe se o dinheiro entrou no livro.

### Fechamento do dia (`pages/session/closing.vue`)

**[P1] Sem estado de erro: a tela fica em branco.**
`closing.vue:123` e `:366-368` — o template cobre `accessDenied`, `closing` e `pending`.
Com `error` preenchido e `closing` null, **nada é renderizado**: cabeçalho e área vazia,
sem mensagem e sem retry. `useDayClosing` já expõe `error` (`useDayClosing.ts:50`) e
ninguém consome.

**[P1] "snapshot" e "estorne" na tela do operador.** `closing.vue:185`, `:163`.

**[P1] "SKU" como cabeçalho de coluna, três vezes, na contagem cega.**
`closing.vue:192`, `:227`, `:283`, e `:317`. Quem faz o fechamento conta pão, não SKU.

**[P2] A confirmação do fechamento não diz que é irreversível.** `closing.vue:347-349`.

### Tela de venda (`pages/index.vue`)

**[P1] O operador nunca sabe se as comandas na tela estão atuais.**
`surfaces/pos-nuxt/app/app.vue:49-51` + `composables/usePosEvents.ts:104`

`usePosEvents` calcula honestamente `realtime` (`live`/`connecting`/`polling`) e o
`app.vue` **descarta o retorno**. Quando o SSE cai, o PDV volta ao poll de 60 s e o
quadro segue com cara de tempo real. O KDS (`/pickup`) e o Gestor fazem isso certo com
`realtimeIndicator`; o PDV joga o dado fora.

**[P1] Erro de leitura das comandas é um beco sem saída.**
`pages/index.vue:926-931` — "Não foi possível ler as comandas agora.", sem botão. O
único caminho é o *Atualizar* do rail colapsável, que um novato não vê.

**[P1] Auto-lock derruba o operador com carrinho aberto.**
`composables/usePosAutoLock.ts:39-50` + `pages/index.vue:174-176`

`holdWhen` só segura o relógio durante **checkout ou PIX**. Venda de balcão com 6 itens,
operador conversando com o cliente sem tocar na tela (tablet, sem mouse, então nem
`pointermove` salva) → 60 s → tela de PIN por cima da venda. Pior: se **outra pessoa**
destravar, ela herda o carrinho em silêncio e a venda sai no nome dela.

**Correção:** incluir `cart.items.length > 0` no `paymentHold`; ao destravar com carrinho
de outro operador, perguntar "Venda começada por Fulano. Continuar ou limpar?".

**[P1] Travar o terminal pode falhar em silêncio.** — ver *Cross-cutting*, mesmo defeito.

**[P1] Mensagem de falha no fechamento de venda afirma um fato que pode ser falso.**
`composables/usePosSale.ts:1573` — "O pedido **não foi fechado**". Num timeout o servidor
pode ter fechado e a resposta ter se perdido. A retentativa em si é segura (o
`clientRequestId` é reusado e o backend deduplica —
`shopman/backstage/tests/test_pos_commercial_completion.py:84`), mas a copy mente sobre o estado.

**[P1] `close_sale` que volta `ok: false` não produz reação nenhuma.**
`usePosSale.ts:1497` — `if (response.ok && response.order_ref)` sem `else`. Se o servidor
responder 200 com `ok: false`, o `busy` volta a false e **o botão "Finalizar"
simplesmente não faz nada**, com o cliente na frente.

**[P2] `sensorLost` é prop morta no diálogo da gaveta.** `PosDrawerLockDialog.vue:33`
declara, o template nunca usa; em `useDrawerLock.ts:159-161` é ligada e imediatamente
zerada pelo `release()` (`:341`).

**[P2] "reenfileirada" na tela.** `components/PosRecentSales.vue:173`.

**[P2] "vírgula p/ centavos".** `components/PosCartPanel.vue:629`.

### Tela do cliente (`pages/display.vue`)

**[P2] O display fica congelado sem avisar ninguém.** Consumo só por `BroadcastChannel`.
Se a aba do PDV recarregar ou travar, o segundo monitor mostra o último snapshot
indefinidamente e **o operador não tem como saber** que o cliente lê um total velho.

---

## kds-nuxt

### `/` — seletor de estações

**[P1] Erro e 403 viram "Nenhuma estação configurada".**
`surfaces/kds-nuxt/app/pages/index.vue:6` desestrutura só `{ data, pending }`; `error` é
descartado. `KDSIndexView` exige `backstage.operate_kds`
(`shopman/backstage/api/kds.py:48-49`), então um atendente júnior sem a perm — ou um 500
— cai no ramo `!instances.length` (`:36-39`) e lê **"Nenhuma estação configurada."** O
funcionário do dia um conclui que o sistema não está montado.

**[P2] "Kitchen Display" em inglês na tela do operador.** `pages/index.vue:27`.

### `/[ref]` — board da estação

**[P1] Fila serial de escritas sem timeout: um POST pendurado engole os toques
seguintes, em silêncio.** `composables/useKdsBoard.ts:96-100`

`enqueue` encadeia em `chain` e o `$fetch` **não tem `timeout`**. Em 4G ruim um
`finalize` pode pendurar minutos; toda finalização/marcação posterior fica presa na
fila. A UI é otimista (`removeFrom`, `:125-138`), então **os cards somem do board e
nada chega ao servidor enquanto isso**. O operador vê "Tudo em dia" com pedidos vivos.
A reversão em erro está correta e bem feita (`:133-137`) — o buraco é que um *hang* não
é um erro: ele nunca chega ao catch.

**Correção:** `timeout: 8000` no `$fetch` do proxy, e indicador visível de "N ações
aguardando envio" quando a fila tiver pendência acima de ~3 s.

**[P1] O board do operador não diz se está recebendo push; o painel do CLIENTE diz.**
`presentation/board.ts:210` (`realtimeIndicator`) só é usado em `pages/pickup.vue:13`.
`useKdsBoard.ts:51` engole o `onerror` do EventSource e não expõe estado. Enquanto isso o
relógio do cabeçalho (`pages/[ref].vue:46-48`) **pisca os segundos** — o sinal de
vivacidade mais forte da tela — alimentado por `setInterval` do cliente e totalmente
desacoplado do dado.

**[P1] 403 por falta de permissão é diagnosticado como problema de rede, para sempre.**
`pages/[ref].vue:328-338` mostra "Falha ao carregar o board. Reconectando…" para
qualquer `error`. Pior: `utils/operatorSession.ts:5` dispara
`refreshNuxtData("operator-session")` em todo 401/403 — inclusive no 403 de permissão,
que login nenhum resolve. Loop de re-fetch a cada 15 s e um "Reconectando…" eterno.

**[P1] `station_locked` não levanta a bandeira aqui.**
`flagIfStationLocked` é chamado em `pos-nuxt/app/composables/usePosTerminal.ts:29`,
`usePosAction.ts:44`, `orders-nuxt/.../useOrdersBoard.ts:34` e `useOrderDetail.ts:19` —
e **em nenhum lugar de kds-nuxt nem production-nuxt**. O docstring de
`operator-kit/app/composables/useStationLock.ts:8-11` descreve o sintoma exato.

**[P1] Alvos de toque abaixo de 44 px na tela que mais recebe toque com farinha na mão.**
Cabeçalho `size-9` = 36 px (`pages/[ref].vue:229, 244, 277, 290`), busca `h-9` (`:214`),
e o pior: itens do card `py-1.5` sobre `text-base` ≈ 34 px
(`components/KdsTicketCard.vue:189`) — conferir item é o gesto de maior frequência da estação.

**[P2] Board não re-assina ao trocar de estação por back/forward.**
`pages/[ref].vue:30` chama `useKdsBoard(stationRef.value)` (string congelada, key do
`useFetch` também) enquanto o `<h1>` usa `stationRef` reativo (`:166`). Sem
`definePageMeta({ key })` em nenhuma página. `/molde` → voltar → `/forno` com o
componente reaproveitado: título de uma estação, cards de outra.

**[P2] `aria-label` expõe a chave interna.** `pages/[ref].vue:230` anuncia "cozy"/"roomy".

**[P2] O timer do card não anda entre atualizações.** `KdsTicketCard.vue:149` renderiza
`elapsed_seconds` do servidor: pula de 15 em 15 s enquanto o relógio do cabeçalho corre
em segundos — lê-se como "o board está congelado".

### `/pickup` — painel público de retirada

**[P1] Erro na busca não aparece; o painel mente para o cliente.**
`pages/pickup.vue:8` desestrutura só `{ status, realtime }`. Se o REST falha mas o
EventSource segue conectado, `realtime` fica `"live"` (`useKdsCustomerBoard.ts:39-41`) e
o painel mostra **bolinha verde "Ao vivo" sobre dados velhos**. No primeiro load,
`status` nulo → "Nenhum pedido em preparo agora." — um estado vazio **falso** na parede
da loja.

---

## production-nuxt

### `/plan` e `/` — grade por etapa (`components/ProductionStageGrid.vue`)

**[P0] Falha de insumo ao INICIAR não mostra absolutamente nada.**
`ProductionStageGrid.vue:273-285`

`confirmStart` trata só `res.ok`. `useProductionBoard.ts:53-55` devolve
`{ok:false, shortage}` **antes** do `useSonner.error` — ou seja, no caso de escassez não
há nem toast. E o `ShortageDialog` só é aberto por `confirmPlan` (`:262-265`), que faz
exatamente o `else if (res.shortage)` que falta aqui. O padeiro toca "Iniciar", o
servidor recusa com 409 `material_shortage`, **a tela não faz nada**: sem toast, sem
modal, o diálogo continua aberto. Ele toca de novo. Mesmo defeito em `advanceStep()`
(`:313-318`), que descarta o resultado inteiro.

**[P0] O quiosque não vira o dia.** `ProductionStageGrid.vue:72-73`
`const todayISO = isoForOffset(0)` — constante, avaliada uma vez. `pages/mise-en-place.vue:15-19`
tem o mesmo problema (`dateChips` é array literal). O helper certo existe e é usado só
pelo Solari (`presentation/production.ts:116` ← `pages/board.vue:43`). A padaria abre às
4h com a tela ligada desde a véspera: **o chip "Hoje" aponta para ontem e o padeiro
planeja o dia errado**.

**[P1] "Concluir mesmo assim" do `ShortageDialog` é botão morto no Planejamento.**
`ProductionStageGrid.vue:1056-1063` monta o `<ShortageDialog>` **sem** `@confirm`; o
componente emite `confirm` (`ShortageDialog.vue:54`) e ninguém escuta. Em `/expedite` o
mesmo componente tem o listener (`expedite.vue:459`).

**[P1] Nenhuma mutação dá sinal de "enviando".** `confirmPlan` (`:240`), `confirmStart`
(`:273`), `confirmVoid` (`:296`) e "Confirmar estorno" (`:918-925`) não desabilitam nem
mostram spinner. O guard é o `busy` do composable (`useProductionBoard.ts:45`), que
devolve `{ok:false}` **em silêncio** no segundo toque.

**[P1] Estorno não diz que é irreversível nem usa a palavra do padeiro.**
`ProductionStageGrid.vue:891-925` — "A ordem sai do processo e o vínculo com pedidos é
desfeito." ("ordem" é `WorkOrder`; falta "isso não pode ser desfeito"; "Estornar…" é
vocabulário contábil).

**[P1] A identidade do produto na grade é o SKU.** `ProductionStageGrid.vue:564`
(`{{ row.output_sku }}` em `font-bold`) sob o cabeçalho "Produto" (`:542`), com
`recipe_name` em `text-xs text-muted-foreground` (`:568`). O padeiro lê o código, não o pão.

**[P2] Célula desabilitada não explica por quê.** `actionEnabled` (`:338-342`).

**[P2] Falta a antecipação de gestor na grade** — o que está atrasado, o que vai faltar
de insumo, o que passou da hora, só existe no sino, e o sino é uma gaveta fechada.

### `/board` — Solari "Fornadas"

**[P1] O aviso "sem sinal" da TV é cinza e minúsculo.** `pages/board.vue:126-135`: o
`<span>` recebe `tone-amber`, mas a regra é `.tone-amber :deep(.flap-cell)` (`:426-428`)
e o conteúdo é `<Icon>` + texto puro — **nenhum `.flap-cell`**. O âmbar nunca se aplica;
o badge herda `--board-dim: #82868d` a `0.78rem`. Na TV, a 3 metros, o único indicador
de dado velho é invisível.

**[P1] Nome de produto acima de 22 caracteres é cortado sem aviso.**
`pages/board.vue:116` (`NAME_CHARS = 22`, comentário "maior nome atual") +
`components/SplitFlap.vue:43` (`raw.slice(0, width)`, sem reticências).

**[P2] Pontinhos de página com 7 px.** `.board-pagedot { width: .45rem }` (`:397-400`) —
são botões com `aria-pressed`.

### `/menuboard` — cardápio Solari público

**[P0] O cardápio da parede NUNCA se atualiza.** `pages/menuboard.vue:27-30` é um
`useFetch` sem `useAdaptivePoll`, sem SSE, sem `refresh`. Todas as outras telas polleiam
(`useProductionForecast.ts:20`, `useQcKiosk.ts:33`, `useAlerts.ts:16`). A TV carrega uma
vez e mostra **preço e "ESGOTADO" congelados** até alguém recarregar a página à mão. É
preço errado exibido ao cliente.

**[P0] Um blip na rede mata o cardápio de forma permanente.** `menuboard.vue:143`:
`v-else-if="error"` sem `&& !pages.length` (diferente de `board.vue:226`) troca o
cardápio inteiro por **"Sinal perdido — reconectando…"** — e como não há poll nem retry,
**nada está reconectando**. A frase é falsa e o estado é terminal.

### `/mise-en-place` — Preparação

**[P1] O gesto principal da tela tem 20 px.** `pages/mise-en-place.vue:310-316` — o
checkbox "separado" é `size-5` e a `<tr>` não é clicável. É o toque que o auxiliar dá
dezenas de vezes com a mão suja de farinha. O checkbox "Explodir até matéria-prima"
(`:202-206`) é `size-4` = 16 px.

**[P1] "Explodir até matéria-prima".** `mise-en-place.vue:207` — vocabulário de BOM.

**[P1] Etiqueta impressa de alimento com abreviações de uma letra.**
`components/WeighingLabels.vue:63`: `F {{ made_display }} · V {{ expiry_display }}`. Numa
etiqueta na geladeira, "F"/"V" para fabricação/validade é adivinhação — e é rotulagem de
alimento.

**[P2] Não há confirmação de volume de impressão.** `printLabels` (`:105-109`) dispara
`window.print()` direto; `labels` (`:93-103`) é o produto cartesiano preparo × ingrediente
e pode passar de 50 etiquetas.

**[P2] Coluna "Saldo" some sem explicação** quando `has_stock_readings` é falso
(`:289`, `:351`) — não se distingue "não faltou nada" de "não sei".

### `/expedite` — fechamento de fornada

**[P1] Erro na primeira carga deixa a tela em branco.** `pages/expedite.vue:350-353` tem
ramo para `pending && !kiosk` e para `kiosk && !kiosk.orders.length`, e **nenhum** para
`error && !kiosk`.

**[P1] "Nenhuma fornada planejada para hoje." aparece em qualquer data.**
`expedite.vue:352`, com o seletor "Outra data" logo acima.

**[P1] Um leitor de crachá pode fechar a fornada com o número errado.**
`components/QcCloseScreen.vue:203-224` registra `keydown` em `window`: dígitos alteram a
quantidade e **Enter chama `onConfirm()`**. O guard cobre só `<input>`/`<textarea>`. O
ecossistema tem leitores HID que "digitam" e terminam com Enter
(`operator-kit/app/presentation/operatorLock.ts:37-46`). Um crachá passado perto do
quiosque de QC digita dígitos na quantidade e submete o fechamento imutável.

**Correção:** escopar o listener ao elemento da tela com foco, e nunca mapear Enter para
o submit destrutivo (o PDV já resolve isso com `globalKeysBlocked()`,
`pos-nuxt/app/utils/keyboardGuard.ts`).

**[P1] Fechar fornada não avisa que é definitivo.** `QcCloseScreen.vue:347-354` —
"Confirmar", sem número e sem consequência. O fechamento é imutável e consome insumos.

**[P2] `concludeOven()` pode limpar o timer e não abrir nada.** `expedite.vue:229-236`
limpa o timer e chama `openOrder(order)`, que faz `return` mudo se `!order.can_close`
(`:74`). Hoje inalcançável, mas é acoplamento silencioso.

**[P2] `role="button"` sem Space.** `expedite.vue:362-372` — só `@keydown.enter`.

### Timer do forno (`composables/useOvenTimers.ts`)

**[P0] Depois de qualquer recarga da página, o timer do forno NÃO toca.**
`useOvenTimers.ts:88-89` (`chime()` faz `if (!audio) return`) e `audio` só é criado em
`unlockAudio()`, chamado exclusivamente por `arm()` (`:119`). `load()` (`:33-50`)
restaura os timers do localStorage mas **não** destrava o áudio. Um deploy, um F5 do
quiosque, um crash do tab: **os timers voltam contando na tela e expiram em silêncio
absoluto**. Pão queimado.

Compare com `operator-kit/app/composables/useAlertSound.ts:74-92`, que arma listeners de
gesto e expõe `soundBlocked` — o kit resolveu exatamente isso e o timer do forno não usa.

**[P0] O alarme depende de a aba estar em primeiro plano.** O `chime` é disparado pelo
`setInterval` de 1 s (`ensureTicker`, `:61-75`), throttlado ou parado com a aba oculta ou
o tablet dormindo — e não há wakeLock em lugar nenhum. O countdown está correto
(`endsAt` é tempo absoluto, sobrevive a suspend), mas **o alarme não toca na hora**:
toca quando alguém volta à tela.

**[P1] O alarme desiste depois de 4 toques.** `MAX_CHIMES = 4` a cada `RECHIME_MS = 45s`
(`:23-24`): ~3 minutos, e depois só o card oscilando (`expedite.vue:612-614`). Numa
padaria com masseira e exaustor ligados, 3 minutos de aviso é pouco.

**[P2] Timer é do aparelho, não da casa.** Documentado (`useOvenTimers.ts:3-4`) e dito ao
operador (`expedite.vue:479`, "Toca neste aparelho.") — honesto. Mas o forneiro que troca
de tablet perde o alarme; vale um badge "armado em outro aparelho" (`useOvenFacts` já
declara `armed`).

### Alertas (`components/AlertsBell.vue`, `composables/useAlerts.ts`)

**[P1] 403 e 500 no canal de alertas viram "Nenhum alerta agora."**
`useAlerts.ts:7-14` ignora `error`; `AlertsBell.vue:58-61` renderiza o estado vazio. É o
canal que carrega "fornada esquecida" e "atrasado" — um falso "está tudo bem" aqui é o
pior falso-negativo do app. (O mesmo defeito existe em `orders-nuxt`.)

**[P1] Botão de reconhecer com 28 px.** `AlertsBell.vue:79-87` (`size-7`); sino `size-9` (`:31`).

**[P2] Dropdown sem Escape nem trap de foco.** `AlertsBell.vue:45-50`.

### `/reports`

**[P2] "OP" como cabeçalho de coluna** (`reports.vue` +78, +244) — abreviação de "Ordem
de Produção" que só o autor conhece. (O tratamento de 403 desta tela é o melhor das duas
superfícies — ver *Verified-safe*.)

---

## orders-nuxt

### Board (`pages/index.vue`)

**[P0] Pedido aceito perde a cor de status — resíduo do rename `confirmed`→`accepted`.**
`surfaces/orders-nuxt/app/presentation/board.ts:18`

`STATUS_TONE` mapeia `confirmed: "info"` e **não tem `accepted`**. O status canônico é
`accepted` (`packages/orderman/shopman/orderman/models/order.py:37`) e a projection manda
`status` cru (`shopman/backstage/projections/order_queue.py:438`). Resultado: **toda a
coluna Preparo desenha o pill em cinza neutro** — o mesmo tom de `returned` e de status
desconhecido. O operador perde o eixo de cor na coluna mais cheia. A fixture do próprio
teste já usa `status: "accepted"` (`tests/board.test.ts:39`) sem nunca assertar o tom
(`:86-92`).

**Correção:** trocar a chave `confirmed` por `accepted` (zerar o nome antigo, não
empilhar os dois — convenção da casa) e assertar `statusTone("accepted") === "info"`.

**[P1] Um blip de rede apaga o quadro inteiro.** `pages/index.vue:453-455` —
`v-else-if="error && !stationLocked"` substitui **todo** o board por "Falha ao carregar a
fila. Reconectando…". O poll é de 30 s (`useOrdersBoard.ts:150`); um 500 num tick e o
atendente fica sem fila nenhuma na mão. Não há last-known dimmed nem "última atualização
às HH:MM". Compare com o padrão certo da produção (`presentation/production.ts:245-261`).

**[P1] Sessão expirada / estação travada não re-portoa fora da fila.**
`useOrderDetail.ts:14-17` — `operatorSessionOnError` está ligado **só** no fetch da fila
(`useOrdersBoard.ts:31`). Não está em `useOrderDetail`, `useCatalogMatrix`, `useFeedBoard`
nem `useAlerts`. Com a sessão expirada, a tela de detalhe diz **"Pedido não encontrado ou
falha ao carregar."** (`pages/[ref].vue:152`) para sempre, e o overlay nunca sobe.

**[P1] "Acerto de dinheiro" não mostra quanto era para receber.**
`pages/index.vue:736-746` (gêmeo em `pages/[ref].vue:380-390`) — pede "Valor recebido na
entrega" e diz *"Em branco usa o total do pedido"* sem nunca mostrar o total. O dado está
à mão (`settleCard.total_display`). O entregador volta, o atendente digita de cabeça, e o
livro-caixa fecha em cima de um chute.

**[P1] Diálogos de dinheiro/recusa do board não travam durante o envio.**
`pages/index.vue:675-682`, `:723-727`, `:764-767` — nenhum dos três botões tem
`:disabled`. A tela de detalhe faz certo (`[ref].vue:410`, `:449`, `:453`). O POST
duplicado é barrado pelo `busy` (`useOrdersBoard.ts:191`), mas em 4G ruim o operador toca
"Levou o troco" três vezes e não sabe se saiu. Pior: em falha o diálogo continua aberto e
a razão do backend vai para o `actionError` do card **atrás do modal** (`:210`).

**[P1] Contagem regressiva da confirmação nasce com o relógio do boot do servidor.**
`composables/useNowTick.ts:5` — `const nowMs = ref(Date.now())` é estado de **módulo**,
compartilhado entre requests no SSR, e o `setInterval` só liga no `onMounted`. No servidor
o valor congela na hora em que o processo subiu; o primeiro paint calcula
`confirmationRemainingLabel(deadline, nowMs)` (`OrderCard.vue:54`) contra um relógio de
horas atrás.

**[P2] "Aceitar 12" em lote, sem confirmação e com falha parcial escondida.**
`pages/index.vue:424-439`, `useOrdersBoard.ts:264-286` — `actMany` dispara N POSTs em
paralelo e a falha vira um toast agregado ("3 pedido(s) não puderam ser atualizados.")
sem dizer *quais*, com a seleção já limpa (`index.vue:102`).

**[P2] Nada na tela diz o que está atrasado.** `pages/index.vue:302-331` — os chips
filtram canal e entrega/retirada; a urgência só existe como ordenação escondida no menu ⋯
(`:372-385`) e como cor do relógio por card. O `timer_class` já vem resolvido do servidor:
um chip **"Atrasados · 3"** ao lado de Entrega/Retirada resolveria.

**[P2] Alvos de toque pequenos.** `OrderCard.vue:81` (checkbox `size-4` = 16 px), `:96-106`
(botão Atender ~20 px), `index.vue:571`/`584` (`size-7` = 28 px) — num board declaradamente
usado em tablet (`index.vue:5`).

**[P2] `triaged(zone)` re-filtra e re-ordena a lista inteira 3× por zona a cada render.**
`pages/index.vue:470`, `:474`, `:480` — método, não computed, dentro do `v-for`. Marcar um
checkbox re-executa nove passadas de filtro+sort. Com 200 pedidos num tablet velho isso
aparece. O `tableRows` (`:61-63`) já faz do jeito certo.

**[P2] Botão de recusa com a cor de "confirmar".** `OrderReasonDialog.vue:122` usa
`bg-primary` para "Recusar pedido"; o do board usa `bg-destructive` para o mesmo gesto
(`index.vue:678`). E nenhum dos dois diz que não dá para desfazer.

### Detalhe do pedido (`pages/[ref].vue`)

**[P1] Status de pagamento em inglês, na linha do dinheiro.** `pages/[ref].vue:182` —
`payment_status` é o status cru do intent do Payman
(`shopman/shop/services/payment.py:894-919`): `pending`, `authorized`, `captured`,
`failed`, `cancelled` e o deliberado **`unknown`** (o fail-closed de quando o Payman não
responde). O atendente lê "Pix · captured", ou pior, "Cartão · unknown" — que é
justamente o caso em que ele **não pode** entregar.

**[P1] A tela onde o operador mais fica parado não diz se está atualizada.**
`pages/[ref].vue:24` — o `realtime` de `useOrderEvents` (`:48`) é **descartado**. O board
tem o indicador (`index.vue:336-339`); o detalhe não.

**[P1] Canal cru na tela.** `pages/[ref].vue:166` renderiza `ifood`, `web`, `pdv`. O board
traduz pelo `channelLabel()` (`board.ts:278`), já importado no arquivo vizinho.

**[P2] Sem relógio de espera.** `pages/[ref].vue:132-145` — o card tem `elapsed_seconds`
bem visível; ao abrir o pedido, some. Quem abre para decidir se cancela perde a
informação que motivou a decisão.

**[P2] Cancelar sai com "Cancelado pelo operador" para o cliente.** `pages/[ref].vue:104`
+ `OrderReasonDialog.vue:41` — no modo `cancel` o motivo é opcional, e a descrição do
próprio diálogo diz *"O motivo é enviado ao cliente na notificação de cancelamento."*
(`:65`).

**[P2] Painel de entregador: "1ª corrida não concluída".** `OrderCourierPanel.vue:44-46`
— com `attempts_count = 1` é ambíguo (a atual? a anterior?).

### Catálogo (`pages/catalog.vue`)

**[P1] Preço com ponto vira 100× o valor.** `pages/catalog.vue:175` (`parsedPriceValue`) e
`:227` (`parseBrl`) — ambos fazem `.replace(/\./g, "")`, tratando o ponto como separador
de milhar. Num teclado numérico de tablet o operador digita `15.50` → limpa para `1550` →
`Math.round(1550*100)` = **R$ 1.550,00**. Sem confirmação (achado abaixo) e sem desfazer,
esse pão vai para a loja a mil e quinhentos reais.

**[P1] Reprecificação em lote entra no ar sem confirmação e sem resumo.**
`pages/catalog.vue:739` — "Aplicar" grava direto. Muda o preço de N produtos num canal de
venda ativo, é permanente (a própria dica admite: *"Permanente — para promo, use as
regras."*, `:735`) e não há desfazer nem no cliente nem no servidor.

**[P1] `set` aceita R$ 0,00.** `pages/catalog.vue:182` — `priceOp !== "set" || v >= 0`
deixa passar zero. "Definir 0" em lote publica os produtos de graça.

**[P1] 403 de permissão e 403 de estação travada viram "erro de rede".**
`pages/catalog.vue:350-352` — `useCatalogMatrix` não chama `flagIfStationLocked` nem
classifica o status. As abas Catálogo e Feeds aparecem para **qualquer** operador que
passe no gate do shell (`app/app.vue:7`, `shop.manage_orders`), mas as APIs exigem
`shop.manage_catalog` (`shopman/backstage/api/catalog.py:35`,
`shopman/backstage/api/feeds.py:21`). O atendente júnior toca "Catálogo", recebe *"Não foi
possível carregar o catálogo. Tentar de novo"* — e vai ficar tentando de novo.

**[P1] Erro e vazio aparecem juntos, dizendo coisas opostas.** `pages/catalog.vue:350` +
`:667-673` — a tarja de erro não é `v-else` do bloco da matriz. Com a matriz falhando a
tela mostra *"Não foi possível carregar o catálogo"* **e**, abaixo, *"Nenhum produto no
catálogo."*

**[P1] O painel de produto joga fora o rascunho sem perguntar.** `pages/catalog.vue:762` +
`CatalogProductPanel.vue:702` — o rodapé literalmente conta as alterações (*"{{ patchSize }}
campo(s) alterado(s)"*, `:698`) e mesmo assim "Cancelar", Esc e clique no overlay fecham
direto. São 5 abas, incluindo tabela nutricional inteira digitada à mão.

**[P2] Reordenar não tem trava de envio nem caminho por teclado.**
`useCatalogMatrix.ts:300-331`, `pages/catalog.vue:438-448` — `reorderCollections`/
`reorderItems` são os únicos escritores sem guarda de `busy` (dois arrastes rápidos =
dois POSTs concorrentes, o último vence); e o handle é `role="button" tabindex="0"` com
**só** `@pointerdown` (`useDragReorder.ts:76`): recebe foco e não faz nada com Enter/setas.
É a curadoria da vitrine — precisa existir sem mouse.

**[P2] Alvo de 16 px de altura para pausar um produto num canal ao vivo.**
`pages/catalog.vue:578-588` — toggle `h-4 w-7` numa grade densa, sem confirmação e sem
desfazer. Errar a linha tira o pão da loja.

**[P2] Três significados no mesmo glifo, separados só pela cor.**
`presentation/catalog.ts:180-181` + `:200` — `retracted` ("Retirado"), `skipped`
("Ignorado") e "Nunca sincronizado" usam todos `○`, distinguidos apenas por tonalidade de
cinza, num `size-4`.

### Feeds (`pages/feeds.vue`)

**[P1] Backend caído aparece como "você não tem nenhum feed".** `pages/feeds.vue:10` e
`:215-218` — `useFeedBoard` devolve `error` (`useFeedBoard.ts:6`) e a página **não o
desestrutura**. Falhou o fetch → `board` nulo → `pending` falso → o `v-else` afirma
**"Nenhum feed. Crie um no Admin (menuboard, Google ou Meta)."** O gerente vai ao Admin
criar um menuboard que já existe. É o mesmo 403 de `shop.manage_catalog`, com a mesma mentira.

**[P2] Nada diz se a TV está mesmo recebendo.** `pages/feeds.vue:93-119` — o card mostra
ligado/pausado (a intenção da loja) e nunca a saúde da saída. Uma TV desplugada há três
horas segue "Ativo", verde. (Pede dado novo no backend.)

**[P2] "Feeds" é nome de model, não de coisa da padaria.** `GestorTopBar.vue:16`,
`pages/feeds.vue:66`. O comentário do próprio arquivo entrega a origem: *"No backend o
model do feed chama-se `Feed` — daí os nomes internos aqui"* (`catalog.vue:30-32`).
Sugestão: **Vitrines** — decisão de nomenclatura, vale registrar no glossário ao lado do
par Ocultar/Exibir.

### Sino de alertas

**[P1] O sino falha aberto: fetch quebrado = "Nenhum alerta agora".**
`composables/useAlerts.ts:14-16` + `components/AlertsBell.vue:47-50` — `error` não é lido;
`activeCount` cai para `0` e o painel afirma, **com um check verde**, que está tudo bem.
(Mesmo defeito em `production-nuxt`.)

**[P2] Alerta cita o pedido e não leva até ele.** `AlertsBell.vue:59` — `a.order_ref` é
texto morto.

**[P2] Painel sem Esc nem foco preso.** `AlertsBell.vue:36-45` — `div` + backdrop de
clique, fora do padrão `UiDialog` (reka-ui) que o resto do app usa e que já entrega trap
de foco e Esc. Mesmo problema no menu de ordenação do board (`index.vue:371-385`).

**[P2] "Reconhecer" sem trava.** `useAlerts.ts:44-51` — dois toques = dois POSTs.

---

## hub-nuxt

A classificação de falha (`presentation/hub.ts:47-93`) é o melhor trecho de tratamento de
erro de todas as superfícies: cinco causas, cinco saídas, "tentar de novo" só onde tentar
de novo resolve, e `station_locked` checado antes do 403 genérico. **É o padrão que
Catálogo, Feeds, KDS e o sino de alertas deveriam copiar.** Nada a corrigir ali.

**[P2] "Tentar de novo" não dá sinal de vida.** `app/app.vue:129-136` — `@click="refresh()"`
sem `:disabled` e sem spinner; `pending` é devolvido (`useOperatorHub.ts:21`) e não é
consumido. Numa rede ruim o gerente toca cinco vezes e a tela fica idêntica.

**[P2] Uma falha depois de carregado apaga a Central inteira.** `app/app.vue:117` + `:38`
— se o refresh de reconexão falhar, `hasBlockingFailure` troca a grade já conhecida por
"Central indisponível". Os tiles são links estáticos; podiam continuar clicáveis com uma
tarja discreta.

**[P2] O launcher não antecipa nada.** `app/app.vue:170-186` — seis ícones iguais, sem
sinal. Quem chega às 6h não sabe se há 12 pedidos na fila, 3 alertas críticos ou o caixa
aberto de ontem. Um badge de contagem por tile (a projection já monta cada `_AppSpec` com
o predicado de permissão — `shopman/backstage/projections/hub.py:84`) transformaria a
Central de menu em painel. **Maior valor por linha de código de toda a auditoria.**

**[P2] Descrição do tile sem limite.** `app/app.vue:182` — `<span class="block text-xs">`
sem `line-clamp`; descrição longa desalinha a grade de `min-h-28`.

**[P2] Foco não vai para o campo de usuário.** `app/app.vue:81` e
`orders-nuxt/app/components/OperatorLogin.vue:49` — falta `autofocus` nos dois formulários
de senha. (O PDV faz certo: `pos-nuxt/app/app.vue:91-95`.)

---

## marketing-nuxt

**[P0] Disparar campanha não tem confirmação — um clique manda WhatsApp de verdade.**
`components/FireCampaignPanel.vue:376-384`

O botão **"Disparar agora"** submete o form direto. É a ação mais irreversível do sistema
inteiro: manda mensagem paga para N clientes reais, sem desfazer. O painel mostra o número
de pessoas (`:311-361`, muito bem feito), mas o número é informação passiva — não há um
passo em que o gestor **afirme** que quer mandar para aquelas 143 pessoas.

Comparar: fechar o caixa do PDV, que afeta um turno, exige dois passos com eco do valor
(`pos-nuxt/app/pages/session/index.vue:548-555`).

**[P0] Retentativa após timeout duplica o disparo.**
`composables/useCampaigns.ts:56-96` + `shopman/backstage/api/marketing.py:441`

O POST vai **sem `client_request_id`**, e o servidor não deduplica (nenhuma ocorrência de
idempotência em `marketing.py`). Numa queda de rede o gestor lê *"Não foi possível
disparar a campanha."* (`:94`) — uma afirmação de fracasso que a tela não pode garantir —
clica de novo, e os mesmos clientes recebem **duas** mensagens, com custo dobrado. É
exatamente o modo de falha que `usePosCashSession.ts:70-99` descreve e resolve para o
dinheiro da gaveta; aqui está aberto.

**[P2] "Anúncio publicado" quando o servidor disse `publishing`.**
`useCampaigns.ts:74-84` — `wentOut` inclui `"publishing"` e `"approved"`. Publicando ≠
publicado; numa fila lenta o gestor acha que saiu e não volta a olhar.

---

## purchase-nuxt

**[P0] Confirmar entrada sem idempotência: retentativa duplica estoque e custo.**
`composables/usePurchaseDesk.ts:962-979` + `shopman/backstage/api/purchase.py:72`

`api.confirmReceipt` (`composables/usePurchaseApi.ts:55-60`) manda `mode`, `supplierRef`,
`invoiceAccessKey`, `note`, `lines` — **sem chave de requisição** — e a view não
deduplica. O recebimento acontece na doca, no tablet, com o entregador esperando: o pior
lugar de rede da loja. Timeout → toast de erro → o operador toca "Confirmar entrada" de
novo → **25 kg de farinha entram duas vezes no estoque e o custo médio é contaminado**. O
erro só aparece na próxima contagem.

**Correção:** `client_request_id` no payload + dedupe na view. A `invoiceAccessKey` já é
candidata natural a chave no modo nota fiscal.

**[P1] Confirmar entrada é um clique só, sem eco do que está sendo lançado.**
`pages/index.vue:1144-1147` — o botão escreve estoque e custo direto. O `receiptSnapshot`
(`usePurchaseDesk.ts:955-960`) já monta exatamente o resumo que falta (fornecedor, nº de
linhas, total) — só que **depois** do commit, para a tela de resultado.

---

## bi-nuxt

**[P1] Só a home foi verificada com ramo de erro completo.**
`pages/index.vue:91-97` faz o certo (carregando / erro com *Tentar de novo* / dados /
vazio por gráfico). Vale conferir se `sales`, `cash`, `customers`, `explore`, `forecast`,
`profiles` e `scenarios` repetem os quatro ramos — uma tela de B.I. sem ramo de erro
mostra área vazia, e o dono lê "não vendemos nada" onde a verdade é "o servidor não
respondeu". É o mesmo defeito de `feeds.vue` e do sino de alertas, num lugar onde o
resultado é uma decisão de produção errada.

**[P2] Nenhuma tela diz *quando* os números foram lidos.** O período está resolvido muito
bem (`components/BiTopBar.vue:95-99`), mas não há "lido às 14:32".

---

## Cross-cutting (operator-kit)

**[P0] Nenhuma superfície pede `wakeLock`.**
Verificado em todo `surfaces/`: zero ocorrências de `wakeLock`/`NoSleep`.

O KDS é tela de parede, o `production-nuxt` é kiosk Solari, o `/pickup` fica na loja e o
PDV é tablet de balcão. Todos apagam pela política do sistema. Uma cozinha com o KDS
apagado é serviço parado até alguém com farinha na mão tocar no vidro, e o operador não
distingue "tela apagada" de "app caiu". **Combina com o P0 do timer do forno**: o alarme
depende do `setInterval` da aba, e a aba dorme junto com a tela — pão queimado com o
alarme mudo.

**Correção:** `useScreenWake()` no kit, com re-aquisição em `visibilitychange` (o lock
morre quando a aba sai de foco), adotado por `kds-nuxt` (`[ref]`, `pickup`),
`production-nuxt` (`board`, `menuboard`, `expedite`) e `pos-nuxt`.

**[P1] Travar a estação pode falhar em silêncio.**
`surfaces/operator-kit/app/composables/useOperatorLock.ts:101-111`

```ts
async function lock(): Promise<void> {
  try { await $fetch(".../lock/", …); await refresh(); }
  catch { /* best-effort: a failed lock leaves the operator active */ }
}
```

O operador toca "Travar" no rail no fim do turno, **nada muda na tela**, e ele vai embora
achando que travou. A estação fica aberta sob a identidade dele num balcão compartilhado.
O comentário admite o problema e não o resolve. Vale para os quatro apps
(`pos-nuxt/app/pages/index.vue:681`, `pages/session/index.vue:399`,
`orders-nuxt/app/app.vue:28`) e para o auto-lock do PDV — uma rede caída desliga a única
proteção de kiosk sem avisar. Autenticação é o eixo em que a omissão precisa ser restritiva.

**[P1] `navigator.onLine` não vê a falha real de uma padaria.**
`composables/useConnectivity.ts:15` + `components/OfflineBanner.vue:15`

`onLine` é true sempre que a placa está associada ao roteador — inclusive quando o
roteador perdeu a internet, que é *o* modo de falha do wi-fi de loja. O banner "Sem
conexão — tentando reconectar…" nunca aparece nesse caso, e as telas seguem mostrando
dados velhos com cara de atuais. Além disso o banner **promete uma reconexão que ele
próprio não executa** — não há heartbeat, só o listener de evento.

**Correção:** derivar o sinal do **último fetch bem-sucedido** (nada há > 90 s com poll
ativo ⇒ degradado), não do `navigator.onLine`.

**[P1] Falha de rede na lista de operadores vira "ninguém pode trabalhar aqui".**
`composables/useOperatorLock.ts:63-75` + `components/OperatorLock.vue:178-184`

```ts
} catch { eligible.value = []; }
```

Qualquer erro (500, timeout, wi-fi caindo às 6h) zera a lista e a tela de bloqueio afirma
**"Nenhum operador habilitado para esta tela."** Sem retry, sem caminho alternativo
visível — a padaria abre e o balcão diz que ninguém tem permissão de operar. É a mesma
afirmação categórica sobre pergunta não respondida que `pos-nuxt/app/pages/index.vue:918-925`
tem o cuidado de evitar no quadro de comandas.

**[P1] Blip no `/operator/session/` manda o balcão para a tela de SENHA.**
`useOperatorLock.ts:23-46` (`canIdentify = session !== null`) + `pos-nuxt/app/app.vue:80`

Se a leitura da sessão falhar por 500 ou rede, `data` fica null, `canIdentify` vira false
e sobe **"Entre para operar o caixa"**, que pede usuário e senha de gestor. Ninguém no
balcão às 6h tem essa senha; a estação está provisionada e o caminho certo era o PIN. O
comentário em `useOperatorLock.ts:37-45` descreve a intenção (403 = não é estação), mas o
código não distingue 403 de 500/rede.

**[P1] Não existe auto-trava por inatividade fora do PDV.**
Nenhuma ocorrência de idle/inactivity/autoLock em `operator-kit`, `kds-nuxt` ou
`production-nuxt` (verificado). A tela que o padeiro deixa aberta continua com a
identidade dele até alguém tocar "Travar". Quem chegar depois fecha fornadas e finaliza
pedidos no nome do anterior. É decisão de produto legítima (`usePosAutoLock` documenta o
porquê em `:7-9`), mas vale revisitar para o quiosque de QC, que faz escrita imutável.

**[P1] Travar o terminal é item de rail sem rótulo de ação e sem confirmação.**
`components/OperatorRail.vue:91-97` — o item mostra **o nome do operador** e ao ser tocado
faz logout de verdade. No estado compacto é um ícone de pessoa. Um toque errado no PDV com
venda aberta põe a tela de PIN por cima do atendimento.

**[P1] Botão "Cancelar" inerte na troca forçada de PIN.**
`components/OperatorLock.vue:166` (`@cancel="() => {}"`) + `components/OperatorPinChange.vue:119`
— no fluxo forçado o `OperatorPinChange` desenha um botão que diz **"Cancelar"** e emite
`cancel`, que o `OperatorLock` liga a uma função vazia. Num kiosk, botão que não responde
é lido como "travou".

**[P1] `<span class="sr-only">Close</span>` em inglês em todos os diálogos, com X de 16 px.**
`kds-nuxt/app/components/Ui/Dialog/Content.vue` e
`production-nuxt/app/components/Ui/Dialog/Content.vue:32` (e o irmão de `orders-nuxt:34`).
O X é `size-4` sem padding — a única saída sem ação de cada modal. A equipe já sabe:
`production-nuxt/app/pages/expedite.vue:469-476` sobrescreve com `size-11` e o comentário
"X maior, pensando em touch". Todos os outros modais (planejar, iniciar, estorno,
encomendas, escassez, recall do KDS, detalhe do ticket) ficaram com 16 px.

**[P2] O som de alerta pode estar mudo sem que ninguém saiba, justo no KDS.**
`composables/useAlertSound.ts:76-92` — o `AudioContext` só sai de `suspended` com um gesto
do usuário. Numa tela de parede **ninguém toca**. O composable expõe `soundBlocked`
corretamente e o KDS o exibe (`kds-nuxt/app/pages/[ref].vue:268-272`) — está resolvido
ali; o que falta é o timer do forno usar o mesmo mecanismo (ver P0 de `useOvenTimers`).

**[P2] `retryWithBackoff` do kit retenta `status === 0`.**
`utils/retryBackoff.ts:35` (`isTransientError`) — status 0 significa "não sabemos se o
servidor recebeu". Para GET é correto; para POST não-idempotente é duplicação silenciosa.
O único consumidor de operador é `production-nuxt/app/composables/useOvenFacts.ts:13`, que
**retenta um POST**. Documentar na assinatura que mutação exige chave de idempotência, e
conferir se `oven-facts` tem uma.

---

## Copy rewrite table

| file:LINE | current | proposed pt-BR |
|---|---|---|
| `pos-nuxt/app/presentation/managerAuth.ts:48` | `Sai dinheiro da gaveta.` | `Sai dinheiro da gaveta. Você assina: {{ detail }}.` — `detail` = `Sangria de R$ 200,00 · Cofre` |
| `pos-nuxt/app/presentation/managerAuth.ts:56` | `Sai dinheiro da gaveta.` (devolução) | `Devolver R$ 45,00 do pedido NB-1234, em dinheiro.` |
| `pos-nuxt/app/presentation/managerAuth.ts:52` | `Atender abre a gaveta.` | `Atender o pedido de R$ 100,00 em notas de 10. A gaveta abre.` |
| `pos-nuxt/app/components/PosCancelSaleDialog.vue:60` | `O pedido {{ orderRef }} será cancelado. Esta operação exige a autorização de um gerente.` | `Cancelar o pedido {{ orderRef }} — {{ totalDisplay }}. A nota fiscal, se já saiu, é cancelada junto. Se o cliente pagou em dinheiro, a devolução fica pendente na sessão de caixa. Não dá para desfazer.` |
| `pos-nuxt/app/composables/usePosSale.ts:1573` | `Não foi possível finalizar a venda. O pedido não foi fechado; revise o pagamento e valide de novo.` | (timeout/5xx) `Não tivemos resposta do servidor. Valide de novo — se o pedido já tiver fechado, ele não duplica.` |
| `pos-nuxt/app/composables/usePosCashSession.ts:117` | `Falha ao registrar movimento.` | `Não tivemos resposta do servidor. Confira o livro do turno antes de lançar de novo.` |
| `pos-nuxt/app/composables/usePosSale.ts:1825` | `Falha ao cancelar venda.` | `Não conseguimos cancelar. Confira nas Últimas vendas se o pedido ainda está aberto.` |
| `pos-nuxt/app/pages/index.vue:929` | `Não foi possível ler as comandas agora.` | `Não conseguimos ler as comandas agora. Confira a internet do balcão.` + botão `Tentar de novo` |
| `pos-nuxt/app/pages/session/closing.vue:163` | `Conclua ou estorne antes de encerrar o dia.` | `Conclua ou cancele essas ordens antes de encerrar o dia.` |
| `pos-nuxt/app/pages/session/closing.vue:185` | `Ficaram registradas no snapshot; resolva na produção.` | `Ficaram registradas no fechamento do dia; resolva na produção.` |
| `pos-nuxt/app/pages/session/closing.vue:192,227,283` | `SKU` (cabeçalho) | `Produto` (mostrar o nome; código como linha secundária) |
| `pos-nuxt/app/pages/session/closing.vue:348` | `Sobras viram "Ontem" ou perda e a contagem é registrada.` | `…e a contagem é registrada. O dia fecha uma vez só — não dá para refazer hoje.` |
| `pos-nuxt/app/components/PosRecentSales.vue:173` | `Emissão de {{ ref }} reenfileirada.` | `A nota de {{ ref }} foi mandada de novo para emissão. Acompanhe aqui.` |
| `pos-nuxt/app/components/PosCartPanel.vue:629` | `Preço unitário — vírgula p/ centavos · gerente aprova` | `Preço unitário — vírgula para os centavos · precisa de gerente` |
| `kds-nuxt/app/pages/index.vue:27` | `Kitchen Display` | `Cozinha` |
| `kds-nuxt/app/pages/index.vue:38` | `Nenhuma estação configurada.` | (ramo de erro novo) `Não foi possível carregar as estações.` / 403: `Seu acesso não inclui a cozinha. Peça a liberação a quem administra a loja.` |
| `kds-nuxt/app/pages/[ref].vue:163` | `Estação KDS` | `Estação de preparo` |
| `kds-nuxt/app/pages/[ref].vue:230` | `Densidade: ${density}` (→ "cozy") | `Tamanho dos cards: Padrão` |
| `kds-nuxt/app/pages/[ref].vue:332` | `Falha ao carregar o board. Reconectando…` | `Não foi possível carregar a fila. Tentando de novo.` + ramo 403: `Você não tem acesso a esta estação.` |
| `kds-nuxt/app/pages/[ref].vue:377` | `Ciente` | `Dar baixa` |
| `kds-nuxt/app/components/KdsTicketCard.vue:270` | `Detalhes...` | `Detalhes` |
| `kds-nuxt/app/components/KdsExpeditionCard.vue:97` | `volume` / `volumes` (é a soma das qtds — `projections/kds.py:511`) | `item` / `itens` |
| `production-nuxt/app/components/ProductionHeader.vue:119` | `Buscar por código, SKU ou receita` | `Buscar por produto, ficha ou código da fornada` |
| `production-nuxt/app/components/ProductionStageGrid.vue:186` | `Planejar novo lote` | `Planejar nova fornada` |
| `production-nuxt/app/components/ProductionStageGrid.vue:751` | `Salvar novo lote` | `Salvar nova fornada` |
| `production-nuxt/app/components/ProductionStageGrid.vue:772` | `…registra o início e materializa o lote.` | `…registra o início e cria a fornada.` |
| `production-nuxt/app/components/ProductionStageGrid.vue:885` | `Iniciar próximo lote (N un.)` | `Iniciar próxima fornada (N un.)` |
| `production-nuxt/app/components/ProductionStageGrid.vue:897` | `A ordem sai do processo e o vínculo com pedidos é desfeito.` | `A fornada sai da produção e os pedidos ligados a ela ficam descobertos. Isso não pode ser desfeito.` |
| `production-nuxt/app/components/ProductionStageGrid.vue:916` | `Estornar…` | `Cancelar fornada…` |
| `production-nuxt/app/components/ProductionStageGrid.vue:924` | `Confirmar estorno` | `Sim, cancelar a fornada` |
| `production-nuxt/app/components/QcCloseScreen.vue:138` | `O que houve com as N do sublote?` | `O que houve com as N que saíram diferentes?` |
| `production-nuxt/app/components/QcCloseScreen.vue:183` | `A fornada não tem grupo vendável. Perda total se registra como estorno, com o gestor.` | `Nenhuma unidade boa nesta fornada. Perda total não fecha por aqui — chame o gestor para cancelar a fornada.` |
| `production-nuxt/app/components/QcCloseScreen.vue:276` | `Quantas divergentes` | `Quantas saíram diferentes` |
| `production-nuxt/app/components/QcCloseScreen.vue:335` | `Sublote: N` | `Diferentes: N` |
| `production-nuxt/app/components/QcCloseScreen.vue:353` | `Confirmar` | `Fechar fornada · {{ total }} un.` + linha fixa: `Depois de fechada, só o gestor corrige.` |
| `production-nuxt/app/components/WeighingLabels.vue:63` | `F {{ made }} · V {{ expiry }}` | `FAB {{ made }} · VAL {{ expiry }}` |
| `production-nuxt/app/components/ShortageDialog.vue:23` | `Faltam insumos para concluir {{ work_order_ref }}` | `Falta insumo para esta fornada ({{ work_order_ref }}). Dá para seguir assim mesmo — fica registrado um alerta.` |
| `production-nuxt/app/components/ShortageDialog.vue:31` | `{{ item.sku }}` (código cru) | nome do insumo, SKU em segundo plano |
| `production-nuxt/app/pages/mise-en-place.vue:207` | `Explodir até matéria-prima` | `Mostrar até a matéria-prima` |
| `production-nuxt/app/pages/expedite.vue:352` | `Nenhuma fornada planejada para hoje.` | `Nenhuma fornada planejada para {{ kiosk.selected_date_display }}.` |
| `production-nuxt/app/pages/expedite.vue:429` | `{{ full_price_qty }} OK` | `{{ full_price_qty }} boas` |
| `production-nuxt/app/pages/menuboard.vue:143` | `Sinal perdido — reconectando…` (nada reconecta) | `Sem conexão com o cardápio.` — e só quando não há dado |
| `orders-nuxt/app/pages/[ref].vue:182` | `{{ payment_method_label }} · {{ payment_status }}` → "Pix · captured", "Cartão · unknown" | mapear em `presentation/board.ts`: `captured`→`pago`, `authorized`→`autorizado, ainda não cobrado`, `pending`→`aguardando pagamento`, `failed`→`pagamento recusado`, `cancelled`→`pagamento cancelado`, `unknown`→**`não consegui confirmar o pagamento — não entregue sem checar`** |
| `orders-nuxt/app/pages/[ref].vue:166` | `{{ order.channel_ref }}` → "ifood" | `{{ channelLabel(order.channel_ref) }}` → "iFood" |
| `orders-nuxt/app/pages/index.vue:454` | `Falha ao carregar a fila. Reconectando…` | `Sem atualizar desde {hora}. O que está na tela pode ter mudado — tentando reconectar.` |
| `orders-nuxt/app/pages/feeds.vue:217` | `Nenhum feed. Crie um no Admin (menuboard, Google ou Meta).` | vazio real: `Nenhuma vitrine configurada. Crie uma no Admin (TV do balcão, Google ou Meta).` · erro: `Não consegui carregar as vitrines. Tente de novo.` |
| `orders-nuxt/app/components/AlertsBell.vue:49` | `Nenhum alerta agora.` | só com fetch bem-sucedido. Em erro: `Não consegui carregar os alertas — toque para tentar de novo.` |
| `orders-nuxt/app/pages/index.vue:681` / `OrderReasonDialog.vue:125` | `Recusar pedido` | `Recusar — o cliente é avisado e isso não pode ser desfeito` |
| `orders-nuxt/app/components/OrderReasonDialog.vue:125` (modo cancel) | `Confirmar` | `Cancelar o pedido` |
| `orders-nuxt/app/pages/[ref].vue:104` | fallback `Cancelado pelo operador` (vai para o cliente) | `Não conseguimos preparar seu pedido hoje. Desculpe.` |
| `orders-nuxt/app/pages/index.vue:737` / `[ref].vue:381` | `Valor recebido na entrega. Em branco usa o total do pedido.` | `Quanto o entregador trouxe. Total do pedido: R$ 42,00. Em branco, usamos o total.` |
| `orders-nuxt/app/pages/catalog.vue:739` | `Aplicar` | `Alterar 24 preços` + confirmação: `Vale já na loja e não dá para desfazer.` |
| `orders-nuxt/app/pages/catalog.vue:351` | `Não foi possível carregar o catálogo.` | 403 → `Você não tem acesso ao catálogo. Fale com o gerente.` · rede → `Não consegui carregar o catálogo. Tente de novo.` |
| `orders-nuxt/app/components/GestorTopBar.vue:16` | `Feeds` | `Vitrines` (registrar no glossário) |
| `orders-nuxt/app/presentation/catalogFilters.ts:96` | `Canal ou feed` | `Canal ou vitrine` |
| `orders-nuxt/app/presentation/catalogFilters.ts:107` | `À venda` | `Ativo` — par canônico do glossário (`docs/reference/glossary.md:18`) |
| `orders-nuxt/app/components/OrderCourierPanel.vue:45` | `1ª corrida não concluída` | `1 tentativa anterior não concluída` |
| `orders-nuxt/app/composables/useOrdersBoard.ts:284` | `3 pedido(s) não puderam ser atualizados.` | `3 de 12 não avançaram — continuam marcados.` |
| `Ui/Dialog/Content.vue:32-34` (kds, production, orders) | `<span class="sr-only">Close</span>` | `Fechar` |
| `operator-kit/app/components/OperatorLock.vue:183` | `Nenhum operador habilitado para esta tela.` | (quando a causa é erro) `Não conseguimos ler quem pode operar. Confira a internet do balcão.` + `Tentar de novo` |
| `operator-kit/app/components/OperatorPinChange.vue:119` | `Cancelar` no fluxo forçado | esconder quando `forced`, ou `Não consigo agora — chamar o gerente` |
| `operator-kit/app/components/OperatorRail.vue:94` | `:label="operatorName"` | `:label="\`Travar · ${operatorName}\`"` |
| `operator-kit/app/components/OfflineBanner.vue:30` | `Sem conexão — tentando reconectar…` | (derivado do último fetch) `Sem resposta do servidor há {{ n }} min — o que você vê pode estar desatualizado.` |
| `operator-kit/app/composables/useOperatorLock.ts:109` (hoje silêncio) | — | `Não consegui travar a estação — ela continua aberta no seu nome. Tente de novo.` |
| `marketing-nuxt/app/components/FireCampaignPanel.vue:382` | `Disparar agora` (sem confirmação) | passo de confirmação: `Enviar para {{ n }} pessoas agora? A mensagem sai no WhatsApp de cada uma e não dá para desfazer.` |
| `marketing-nuxt/app/composables/useCampaigns.ts:94` | `Não foi possível disparar a campanha.` | `Não tivemos resposta do servidor. Confira no histórico se a campanha saiu antes de disparar de novo.` |
| `marketing-nuxt/app/composables/useCampaigns.ts:78` | `Anúncio publicado para {{ people }}.` (inclui `publishing`) | `publishing` → `Anúncio a caminho de {{ people }}. Acompanhe no histórico.` |
| `purchase-nuxt/app/pages/index.vue:1146` | `Confirmar entrada` (direto) | confirmação: `Dar entrada em {{ n }} itens de {{ fornecedor }} — {{ total }}? Isso entra no estoque e no custo.` |

### Vocabulário cruzado a decidir de uma vez

- **lote × fornada** — o operador vê "lote" em Planejamento/Produção
  (`ProductionStageGrid.vue:186`, `:751`, `:885`) e "fornada" na Expedição, no Solari e
  nos alertas, para a mesma `WorkOrder`. O glossário (seção Craftsman) só define
  `WorkOrder`. **"Fornada" é a palavra da casa** — a grade deveria seguir.
- **feed × vitrine** — `Feed` é nome de model; a aba de navegação é a última fronteira
  antes do operador.
- **SKU** — vaza em `closing.vue` (3×), `ProductionStageGrid.vue:564`,
  `ShortageDialog.vue:31` e `ProductionHeader.vue:119`. Regra: o nome do produto é a
  identidade; o código é linha secundária.
- **estorno** — contábil; em produção o gesto é "cancelar a fornada".

---

## Verified-safe

Verificado contra os eixos da auditoria e genuinamente bem resolvido — não mexer sem motivo.

**Dinheiro e idempotência (pos)**
- `close_sale` reusa o `clientRequestId` gravado pelo `reviewSale`
  (`usePosSale.ts:1433` → `:1094`) e o backend deduplica de fato
  (`shopman/backstage/tests/test_pos_commercial_completion.py:84`). Retentar não duplica venda.
- `usePosCashSession.chaveDoGesto` (`:94-99`): a chave volta enquanto o gesto idêntico
  falha e é descartada no sucesso — duas sangrias iguais de propósito viram duas linhas.
  (A ressalva do slot único está acima.)
- Guarda de reentrância em toda mutação de venda (`usePosSale.ts:1482`, `:1467`,
  `usePosCashSession.ts:102`).
- Gaveta só abre **depois** do `ok` do servidor (`usePosCashSession.ts:163`, `:304`, `:331`).
- Troco/pedido de troco explicitamente **fora** de `cash/movement/` (`:266-269`) — net
  zero não cria falta fantasma no fechamento.
- Recibo de movimento sai sozinho e a falha de papel **não desfaz o movimento**: vira
  registro + toast com "Tentar de novo" (`:184-225`).
- Contagem cega de verdade: campos vazios, CTA só arma com todos preenchidos, e a dica
  aponta **o item** que falta (`closing.vue:53-61`, `:340-344`).
- O PDV nunca mostra o esperado da gaveta (`pages/session/report.vue:5-7`).

**Destrutivo com confirmação proporcional**
- Remover item do carrinho pergunta sempre, e a pergunta muda quando a linha já foi para a
  cozinha (`PosCartPanel.vue:204-253`, `:728-747`); remoção em lote diz quantos.
- Fechar caixa: dois passos com eco do valor contado (`session/index.vue:548-555`).
- Cancelar pedido de troco confirma **por pedido**, não em bloco (`session/index.vue:321-323`).
- Cancelar corrida do entregador com two-tap que reseta no blur (`OrderCourierPanel.vue:19-26`).
- `presentation/qc.ts:149-157` (`pendingQuestions`): guard anti-typo de overshoot + motivo
  obrigatório para perda e para o grupo com desconto, perguntados um de cada vez, sem
  custar toque na fornada limpa.

**Trava de gaveta (pos)**
- `readState()` **nunca lança** (`useCounterAgent.ts:204-224`); o sensor morto derruba a
  trava marcando o episódio (`useDrawerLock.ts:155-163`); a desistência vira desfecho
  auditado (`:322-333`); a saída normal é fechar a gaveta — não existe "Já fechei". A porta
  de emergência é discreta no desenho mas com alvo de 44 px (`PosDrawerLockDialog.vue:97-106`).
- `messageOf` traduz `TypeError` de porta fechada em "O agente da estação não está rodando"
  (`useCounterAgent.ts:229-237`); `AgentTooOldError` (`:65-73`) diz "reinstale pelo gestor".

**Impressão (pos)**
- Fallback nunca silencioso (`pages/index.vue:225-227`).
- Auto-impressão da DANFE espera a SEFAZ com fim (~90 s) e ao desistir cai no mesmo aviso
  com o próximo passo (`:246-281`, `:315-326`).
- Recibo é snapshot congelado no fechamento, não estado vivo (`usePosSale.ts:1503-1517`).

**Teclado / balcão com scanner**
- `PosShortcutsHelp` existe e abre com `?` (`pages/index.vue:652-657`).
- Atalhos globais desligam sob overlay/diálogo (`utils/keyboardGuard.ts`,
  `pages/index.vue:508-514`) — PIN de gerente e token de crachá não alimentam o numpad de
  tender por baixo. **É exatamente a proteção que falta no `QcCloseScreen`.**
- Enter só finaliza com review fresca e total coberto (`pages/index.vue:643-651`).
- Escolha de operador por número de teclado (`OperatorIdentify.vue:97-108`) — identificação
  inteira sem mouse.

**Honestidade de dado velho**
- `production-nuxt/app/presentation/production.ts:245-261` (`boardDisplay`/`isStale`) e sua
  aplicação em `ProductionStageGrid`, `mise-en-place`, `expedite`, `board`, `reports`: dado
  velho visível > quadro vazio, com chip honesto de degradação. **Padrão exemplar — é o que
  falta no board do Gestor e no KDS.**
- `presentation/board.ts:328-336` + `orders-nuxt/pages/index.vue:336-339`: verde só com SSE
  aberto, poll de 30 s como rede, `visibilitychange`/`online` forçando refetch.
- `useKdsCustomerBoard.ts:20-49` + `kds-nuxt/presentation/board.ts:210`: "Ao vivo" só acende
  com `onopen` do EventSource.
- `useKdsBoard.ts:65-71` e `useAdaptivePoll.ts`: refetch imediato ao voltar à aba, cadência
  que aperta sob pressão (`useProductionKds.ts:29`: 30 s → 10 s com atraso no chão).

**Escrita sem otimismo (orders)**
- Toda mutação marca ocupado por ref, faz POST e re-busca a verdade do servidor; nada de
  mover card local (`useOrdersBoard.ts:165-221`). O 409 tem mensagem própria e honesta.
- Erro de ação persiste inline no card/linha até ser dispensado, em vez de toast fugaz
  (`OrderCard.vue:245-255`, `index.vue:596-606`).
- Botão bloqueado ocupa o lugar e diz o motivo em vez de sumir (`board.ts:231-243`,
  `[ref].vue:222-224`); `can_cancel`/`cancel_block_label` vêm resolvidos do servidor.
- `useProductionBoard.ts:63-79`: `expected_rev` no ajuste — duas bancadas não se
  sobrescrevem em silêncio.

**Permissões (só oferece o que existe)**
- `hub-nuxt/app/presentation/hub.ts:47-93` — classificação de falha em cinco causas com
  teste próprio. O padrão a copiar.
- Tiles do hub filtrados por permissão no servidor (`shopman/backstage/projections/hub.py:84`).
- `production-nuxt/app/pages/reports.vue:96-114`: 403 tratado como estado legítimo,
  explicado, com saída.
- `pos`: `danfe_screen_allowed` (`pages/index.vue:494-498`), `can_audit_cash`
  (`session/index.vue:74`), `canReprint` (`report.vue:27-29`), `accessDenied` no fechamento
  (`closing.vue:112-121`), `useStationProvision.allowed` vindo da resposta do servidor.

**Estado da estação**
- 403 `station_locked` levanta bandeira na leitura E na escrita (`useStationLock.ts`,
  `usePosTerminal.ts:22-29`, `usePosAction.ts:11`) — o quadro de comandas nunca desenha
  vazio fingindo que sumiram. O aviso de leitura falha se cala enquanto `locked`
  (`pages/index.vue:918-925`).
- Chip "Não salvo" com retry automático a cada 5 s no autosave da comanda
  (`usePosSale.ts:1358-1370`, chip em `pages/index.vue:701-708`) — a promessa do tooltip é
  cumprida pelo código.

**Som e antecipação**
- `useAlertSound.ts:37-47`: `soundBlocked` transforma a política de autoplay num aviso
  visível em vez de falha muda — e o KDS o exibe (`kds-nuxt/pages/[ref].vue:268-272`).
  Permissão de notificação pedida dentro do gesto (`useOrdersBoard.ts:56-68`); o beep só
  dispara em `kind === "created"` (`board.ts:345-355`) — mudança de status não grita.
- `expedite.vue:336-348`: banner de fornadas abertas de dias anteriores com toque que leva
  ao dia pendente. Antecipação real de gestor.
- `useQcKiosk.ts:48-50`: `state_conflict` força refresh imediato em vez de esperar o poll.
- `board.vue:42-48` + `presentation/production.ts:116`: virada de dia à meia-noite na TV,
  testável e pura. **É o helper que `ProductionStageGrid` e `mise-en-place` deveriam usar.**
- `useOvenFacts.ts`: o fato (enfornou/retirou) é carimbado no servidor com
  `retryWithBackoff`, e falha terminal vira relato de erro, não toast às 5h.
- `useOvenTimers.ts:121`: `endsAt` absoluto + persistência — o countdown está correto após
  suspend/resume (o problema é o alarme, não a conta).

**Captura de identidade (kit)**
- `composables/useIdentityCapture.ts` + `presentation/operatorLock.ts`: buffer único,
  decisão no Enter pela mediana de cadência, nenhuma tecla perdida por digitação rápida,
  `stopPropagation` para o PIN não vazar para os atalhos por baixo, token nunca logado.
- `touch-manipulation` no pad (`OperatorIdentify.vue:214`); digitar nunca desabilita, só o
  confirmar (`:237`); alvos de 44 px (`OperatorNumpad.vue:24-29`).
- `httpErrorMessage` nunca devolve string técnica do ofetch (`utils/httpError.ts:69-76`);
  `isUnauthenticatedError` por código, não por status (`:56-60`).
- Telemetria de erro com dedupe e teto (`plugins/errorReporter.client.ts:6-25`), inerte em dev.
- `OfflineBanner` só depois da hidratação (`:11-15`), montado em todas as superfícies.

**B.I.**
- `delta()` não depende de cor (`presentation/bi.ts:104-107`): "▲ 12% vs Período anterior".
- Denominador sempre à vista (`:111-114`): "18 de 24 fornadas medidas".
- Estado vazio por gráfico com a causa (`pages/index.vue:145`).
- Um período para o app inteiro (`BiTopBar.vue:3-6`).
- `board.ts:518-536` (`changeBackSuggestionQ`) e o comentário que documenta a sobra
  fantasma de R$ 24 por entrega.

**Marketing / Purchase**
- Contagem de público ao vivo com as parcelas por regra (`FireCampaignPanel.vue:130-139`,
  `:336-349`); alcance zero nunca passa calado com o motivo certo (`useCampaigns.ts:83-88`);
  reabrir o painel zera tudo (`:57-71`).
- `ReceiptConversion.vue:35-48` mostra **a conta pronta** ("4 × saco 25 kg = 100 kg") em vez
  do fator; `:50-55` traduz a procedência ("É a própria nota que diz.") em vez de "unidade
  tributável".
- `purchase-nuxt/app/pages/index.vue:1141-1152`: o botão **nunca fica mudo** — quando falta
  algo ele diz o quê e leva ao campo (`focusReceiptLine`).
