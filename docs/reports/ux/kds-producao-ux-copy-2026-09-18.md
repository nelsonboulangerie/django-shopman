# Varredura de copy — KDS e Produção (18/09/2026)

- **Escopo:** `surfaces/kds-nuxt/app/` e `surfaces/production-nuxt/app/` — `pages/`,
  `components/`, `composables/`, `presentation/`, `utils/`; mais o que essas telas
  consomem de `surfaces/operator-kit/app/` e das projections que servem as duas
  superfícies (`shopman/backstage/projections/kds.py`, `production.py`,
  `shopman/backstage/api/operations.py`).
- **Lido em:** `origin/main` no `e5b338007`. Número aqui é número medido; quando
  envelhecer, remeça.
- **Natureza:** leitura e relatório. **Nenhuma linha de produto foi alterada.** A
  aplicação é PR seguinte.
- **Régua:** [`docs/reference/omotenashi-copy.md`](../../reference/omotenashi-copy.md) —
  o teste de uma frase (§2), os oito defeitos D1–D8 (§3) e o critério de dano (§6.1).
  Esta é a **Onda 2** da ordem da §6.3: quiosque, mão ocupada, decisão em segundos.
- **Formato:** modelo de
  [`marketing-ux-adversarial-2026-09-18.md`](marketing-ux-adversarial-2026-09-18.md).
  Cada achado tem **Onde** (arquivo e a string — não a linha, que envelhece),
  **Defeito**, **Por que dói** e **Substituição escrita**. Achado sem substituição
  escrita não entrou.

**Por que um relatório só para os dois apps:** o padeiro anda entre as duas telas na
mesma hora. A Parte E existe por isso — é onde aparece o defeito que nenhuma das duas
varreduras isoladas encontraria: **o mesmo gesto com nomes diferentes conforme a porta
de entrada** (D7c).

---

## Placar

Contado por **ficha**, pelo defeito principal de cada uma. As fichas de vocabulário
agrupam ocorrências — E3 agrupa 11 strings, F1 agrupa 6, P1 agrupa 4 nomes
do mesmo objeto.

| Defeito | KDS | Produção | Ambos (Parte E) | Total |
|---|---:|---:|---:|---:|
| D1 — rótulo que mente | 2 | 5 | — | **7** |
| D2 — verbo genérico apaga o ato | — | 2 | — | **2** |
| D3 — frase que obriga a completar sentido | 1 | 5 | — | **6** |
| D4 — grandezas somadas | 2 | 4 | — | **6** |
| D5 — zero como código secreto | — | 1 | — | **1** |
| D6 — nota de rodapé do engenheiro | 1 | 2 | — | **3** |
| D7 — jargão e colisão de vocabulário | 4 | 14 | 3 | **21** |
| D8 — prolixo | — | 1 | — | **1** |
| **Total** | **10** | **34** | **3** | **47** |

Por nível de dano (§6.1 da régua): **13 fazem decidir errado** (D1+D4), **31 fazem parar
para pensar** (D2, D3, D5, D7), **4 são só feios** (D6, D8).

O retrato é claro e não é o do Marketing: lá o defeito dominante era D6 (11 de 38), a
frase que explica a arquitetura. Aqui é **D7 — jargão e colisão de vocabulário, 21 de
47**, e quase todo ele na Produção. Não é que se escreva mal nestes dois apps; é que a
mesma coisa recebeu nomes diferentes a cada tela que nasceu, e ninguém voltou para
unificar. O conserto é mais barato que o do Marketing e mais chato: é varredura, não
redação.

Ordenado por dano: o que faz decidir errado primeiro, o que é só feio por último.
A **Parte G** registra as dúvidas que não viraram proposta de troca, e a **Parte H**
diz o que examinei e considerei bom — é metade do resultado.

---

# Parte A — KDS: faz decidir errado (D1, D4)

## A1. "volumes" na expedição soma peça com quilo

- **Onde:** `kds-nuxt/app/components/KdsExpeditionCard.vue`, o número grande do cartão
  com `"volume"` / `"volumes"`; alimentado por `units_count` em
  `shopman/backstage/projections/kds.py`, que é
  `sum(Decimal(str(item.qty)) for item in items)` formatado por `_qty`, o qual
  quantiza em `Decimal("0.001")`.
- **Defeito:** D4 (grandezas somadas), com D1 de carona no substantivo.
- **Por que dói:** `units_count` não conta volumes — conta a soma das quantidades dos
  itens do pedido, e essas quantidades não são todas da mesma natureza.
  `Product.unit` (`packages/offerman/.../product.py`) aceita `un`, `kg`, `lt` por
  padrão, e `json_quantity` (`shopman/shop/services/order_helpers.py`) existe
  justamente para "keep integral JSON compatibility **without truncating exact
  fractional goods**". Três pães (3) mais 350 g de queijo (0,35) viram **"3,35
  volumes"**. Quem expede confere volumes: ele vai contar sacolas e não vai achar
  3,35. Pior: um pedido só de granel aparece como **"0,75 volumes"**, e a pessoa com o
  cliente na frente conclui que falta item.
- **Substituição:** o número que a expedição precisa é **linhas** (já existe:
  `line_count`) e a contagem de peças **separada** do peso. Enquanto a projection não
  separa, o rótulo honesto é o que não mente: trocar o par
  `"{units_count}" / "volumes"` por `"{line_count}" / "itens para conferir"` e mover a
  quantidade somada para dentro da lista de conferência, onde cada linha já mostra
  `qty × nome` com a unidade do próprio item.

## A2. "A fazer" soma peça com fração, e usa "×"

- **Onde:** `kds-nuxt/app/pages/[ref].vue`, a faixa `"A fazer"` com
  `{{ entry.qty }}×` — e a mesma gramática nos itens do card
  (`KdsTicketCard.vue`, `{{ item.qty }}×`) e do modal (`KdsTicketModal.vue`). A soma
  vem de `allDayCounts()` em `kds-nuxt/app/presentation/board.ts`, que faz
  `Number(item.qty)` e devolve `Number(qty.toFixed(9))`.
- **Defeito:** D4.
- **Por que dói:** o `toFixed(9)` diz em código que a fração é esperada. O agregado
  all-day é, segundo o próprio comentário, "uma das infos mais úteis da estação" — é
  com ele que a cozinha decide o lote. **"0,85× Queijo Minas"** não é uma instrução de
  preparo: o `×` promete peça e o número entrega peso. E, somando dois pedidos de
  granel, a faixa chega a **"1,35× Queijo Minas"**, que não é nem peça nem peso claro.
- **Substituição:** o agregado passa a respeitar a unidade que vem do item. Para item
  de peça, mantém `"12× Pão Francês"`. Para item fracionário, some o `×` e diga a
  unidade: `"1,35 kg Queijo Minas"`. Se a projection ainda não manda a unidade, o
  mínimo honesto é agrupar por unidade e nunca imprimir `×` sobre um número com
  vírgula.

## A3. "na fila" no seletor conta quem já está sendo feito

- **Onde:** `kds-nuxt/app/pages/index.vue`, o selo `{{ inst.pending_count }}` seguido
  de `"na fila"`. O campo se chama `pending_count`, mas
  `build_kds_index()` em `shopman/backstage/projections/kds.py` o preenche com
  `build_kds_board(inst.ref).counts.get("total", 0)` — o **total ativo**, pendentes
  mais em preparo.
- **Defeito:** D1 (rótulo que mente) e D4 (é a mesma grandeza do board com outro nome).
- **Por que dói:** "fila" é o que ainda não começou. O cozinheiro olha o seletor de
  estações de longe para escolher onde ajudar: lê **"6 na fila"** na Confeitaria, corre
  para lá e encontra 6 pedidos, cinco deles já em preparo por outra pessoa. É a decisão
  errada tomada a partir de uma palavra. Some a isso que a mesma grandeza aparece no
  board com outro nome — lá é `"ativos"`.
- **Substituição:** `"6 ativos"` no seletor, igual ao board. Um nome por conceito
  (D7c). Quando a fila de verdade importar, ela ganha o seu próprio número:
  `"6 ativos · 1 esperando"`.

## A4. "a gente avisa quando o próximo chegar" — e às vezes não avisa

- **Onde:** `kds-nuxt/app/pages/[ref].vue`, estado vazio: `"Tudo em dia"` +
  `"Nenhum pedido na fila agora. Aproveite para respirar — a gente avisa quando o
  próximo chegar."`
- **Defeito:** D1.
- **Por que dói:** o aviso é o som, e o som pode estar desligado (`soundOn` falso) ou
  bloqueado pelo autoplay (`soundBlocked`) — o próprio cabeçalho tem o botão
  `"Som bloqueado — toque para ativar"` para esse caso. A frase promete um aviso que,
  nos dois estados, não vai acontecer; o card novo entra na grade em silêncio, e a
  cozinha foi convidada a não olhar. A tela vazia é exatamente quando ninguém está
  olhando.
- **Substituição:** a frase passa a depender do estado do som.
  - Som ligado e desbloqueado: `"Nenhum pedido na fila agora. O próximo avisa com som."`
  - Som desligado ou bloqueado: `"Nenhum pedido na fila agora. O som está desligado —
    o próximo pedido aparece aqui sem avisar."`, com o mesmo botão de ligar o som ao
    lado.

---

# Parte B — KDS: faz parar para pensar (D3, D6, D7)

## B1. "Ciente" nomeia dois gestos diferentes na mesma tela

- **Onde:** `kds-nuxt/app/pages/[ref].vue`. Botão `"Ciente"` no cabeçalho, com
  `aria-label` `"Reconhecer aviso de ticket novo"` (silencia a fanfarra). Botão
  `"Ciente"` no cartão vermelho de cancelado, com `aria-label`
  `"Dar baixa no cancelado"` (libera o finalizar do pedido). E o aviso que aparece ao
  tocar num pedido travado: `"Há item cancelado neste pedido. Toque em Ciente no alerta
  vermelho antes de finalizar."`
- **Defeito:** D7b (colisão de vocabulário dentro do mesmo app).
- **Por que dói:** o próprio aviso precisa de seis palavras de desambiguação — *"no
  alerta vermelho"* — porque a casa já sabe que há dois "Ciente" na tela ao mesmo
  tempo. Um silencia um som; o outro destrava um pedido. Numa manhã cheia, com os dois
  visíveis, o cozinheiro toca no que está mais perto da mão e o pedido continua travado,
  sem que nada na tela explique por quê. Ninguém desconfia de uma palavra que acabou de
  aprender no app.
- **Substituição:** um nome por gesto.
  - silenciar o som: `"Silenciar"` · `aria-label` `"Silenciar o aviso de pedido novo"`;
  - liberar o cancelado: `"Recebi o cancelamento"` · `aria-label`
    `"Confirmar que a cozinha viu o cancelamento do pedido {código}"`;
  - e o aviso vira `"Este pedido tem item cancelado. Confirme o cancelamento no cartão
    vermelho para poder finalizar."`
- ⚠️ Ver também **E1**: a Produção chama esse mesmo gesto de `"Visto"`.

## B2. O cartão de expedição diz "Delivery", "Despacho" e "Despachar" ao mesmo tempo

- **Onde:** `kds-nuxt/app/components/KdsExpeditionCard.vue`. Sobrancelha:
  `{{ card.fulfillment_label }}`, que vem de
  `fulfillment_label="Delivery" if is_delivery else "Retirada"`
  (`shopman/backstage/projections/kds.py`). Selo ao lado: `"Despacho"` / `"Balcão"`.
  Botão: `"Despachar pedido"` / `"Entregar pedido"`.
- **Defeito:** D7c (o mesmo conceito com três nomes) e D7a (`"Delivery"` em inglês na
  tela).
- **Por que dói:** três palavras para um fato, dentro de um cartão que cabe na palma
  da mão: *Delivery* em cima, *Despacho* ao lado, *Despachar* embaixo. E do outro lado
  do par, *Retirada* em cima, *Balcão* ao lado, *Entregar* embaixo — outras três. Quem
  aprende o app pelo selo não reconhece a sobrancelha, e conclui que são coisas
  diferentes, o que é pior do que não entender. O `"Delivery"` ainda quebra a regra de
  português na tela, e sai da projection, então contamina qualquer outra superfície que
  a consuma.
- **Substituição:** dois nomes, um por caso, repetidos nos três lugares.
  - entrega: sobrancelha `"Entrega"` · selo `"Entrega"` · botão `"Despachar pedido"`
    (só o botão diz o verbo — regra de caminho da §3/D1 da régua);
  - balcão: sobrancelha `"Retirada"` · selo `"Retirada"` · botão `"Entregar pedido"`.
  - e `fulfillment_label` na projection passa a `"Entrega"` / `"Retirada"`.

## B3. "Prévia · libera na data" não diz qual data

- **Onde:** `kds-nuxt/app/components/KdsTicketCard.vue`, faixa de estado
  `"Prévia · libera na data"`; e `KdsExpeditionCard.vue`, botão desabilitado com o
  mesmo texto.
- **Defeito:** D3 (frase que obriga a completar sentido).
- **Por que dói:** o card só aparece quando o operador escolheu uma data futura no
  seletor — mas o seletor está no topo do cabeçalho, o card está no meio da grade, e
  entre um e outro pode ter passado um minuto e um cliente. "Na data" pede um
  complemento que o próprio card não dá. O selo do relógio ao lado diz só
  `"Agendado"`, que também não tem data.
- **Substituição:** a data no card, que é onde o olho está:
  `"Prévia · começa em 19/09"`. E o selo do relógio troca `"Agendado"` por
  `"19/09"` — o ícone de calendário já diz que é agendamento.

## B4. O leitor de tela ouve "Densidade: cozy"

- **Onde:** `kds-nuxt/app/pages/[ref].vue`, o botão de densidade da grade:
  `:aria-label="`Densidade: ${density}`"`. A constante `DENSITIES` declara
  `label: "Compacta"` / `"Padrão"` / `"Ampla"` — e **nenhum dos três é usado em lugar
  nenhum do template.**
- **Defeito:** D7a (código interno na tela — a categoria mais segura da varredura V4 da
  régua).
- **Por que dói:** o nome acessível do botão é o valor bruto da chave em inglês:
  *"Densidade: cozy"*. Os três rótulos em português já foram escritos e estão a
  quarenta linhas de distância, mortos. Não é uma decisão a tomar; é um fio solto.
- **Substituição:** usar o que já existe, e dizer o que o toque faz —
  `:aria-label="`Densidade da grade: ${DENSITIES.find(d => d.key === density)?.label}.
  Tocar troca para a próxima.`"`, e o `title` visível igual ao rótulo:
  `"Densidade: Padrão"`.

## B5. "board" e "ticket" vazam para a tela

- **Onde:** `kds-nuxt/app/pages/[ref].vue` — `"Falha ao carregar o board.
  Reconectando…"` e `aria-label="Reconhecer aviso de ticket novo"`.
  `kds-nuxt/app/pages/index.vue` — a sobrancelha `"Kitchen Display"`.
- **Defeito:** D7a (termo interno e estrangeirismo em texto de tela).
- **Por que dói:** em todo o resto do app o objeto se chama **pedido** e a tela se
  chama **estação**. Três strings falam a língua do repositório: *board*, *ticket*,
  *Kitchen Display*. A do erro é a pior das três, porque é a única que a pessoa lê num
  momento em que já está sem informação: ela não sabe o que é um board e agora também
  não sabe o que falhou.
- **Substituição:**
  - `"Falha ao carregar o board. Reconectando…"` → `"Não deu para carregar os pedidos
    desta estação. Tentando de novo."`
  - `aria-label="Reconhecer aviso de ticket novo"` → `"Silenciar o aviso de pedido
    novo"` (ver B1).
  - `"Kitchen Display"` → `"Cozinha"`.

## B6. "sem ações e sem som" explica o sistema no lugar do estado

- **Onde:** `kds-nuxt/app/pages/[ref].vue`, a linha acima da grade quando a data não é
  hoje: `` `Prévia de ${view.serviceDateDisplay.toLowerCase()} — sem ações e sem som` ``.
- **Defeito:** D6 (nota de rodapé do engenheiro) com D3 embutido.
- **Por que dói:** "sem ações" é a descrição de uma decisão de arquitetura
  (`readOnly`), não de uma situação da cozinha. O cozinheiro não estava pensando em
  ações; ele quer saber se pode adiantar alguma coisa. A frase responde a uma pergunta
  que ninguém fez e deixa a dele em aberto.
- **Substituição:** `"Amanhã, 19/09 — só para consultar. Nada aqui pode ser iniciado
  ou finalizado hoje."`

---

# Parte C — Produção: faz decidir errado (D1, D4)

> C8 é D2 e C10 é D3, defeitos de nível 2 no catálogo. Estão nesta parte porque o dano
> é de nível 1: um é o botão irreversível que não diz o ato, o outro é a guarda que
> existe para matar um erro de digitação no fechamento da fornada.

## C1. O Painel diz "UN" para tudo, e o "UN" é inventado pela tela

- **Onde:** `production-nuxt/app/pages/board.vue`, a palheta de quantidade
  `` :value="`${row.qty} UN`" `` e o `aria-label` da linha,
  `` `${row.recipe_name}: ${row.qty} unidades às ${row.eta_display}, ${row.status_label}` ``.
  O `qty` vem de `ForecastRowProjection` em
  `shopman/backstage/projections/production.py`, formatado por `_qty`, que quantiza em
  `Decimal("0.001")`. **A projection não manda unidade nenhuma.**
- **Defeito:** D4 (grandezas somadas) e D1 (o rótulo afirma um fato que a tela não tem).
- **Por que dói:** o "UN" não vem do dado — está cravado no template, com um comentário
  que se explica sozinho: *"quantidade com UN embutido ('12 UN' — doze o quê?
  unidades)"*. A pergunta estava certa e a resposta foi chutada. `WorkOrder.quantity` é
  `DecimalField` sem unidade, e a unidade real mora no produto
  (`Product.unit`, que aceita `kg` e `lt`). O Painel é a TV que **o salão inteiro** lê
  para responder ao cliente: *"sai às 10h"*. Uma fornada de massa medida em quilo
  aparece na TV como **"3 UN"**, e o atendente promete três pães.
  A prova de que a casa sabe fazer o certo está no app ao lado: a Preparação
  (`mise-en-place.vue` via `presentation/weighing.ts`) mostra
  `"1,250 kg"` porque o servidor manda a unidade junto. Uma tela sabe; a outra inventa.
- **Substituição:** a `ForecastRowProjection` ganha `qty_display` já com a unidade do
  produto (`"12 un"`, `"3,000 kg"`), e o Painel imprime esse campo direto, sem sufixo.
  O `aria-label` vira `` `${row.recipe_name}: ${row.qty_display} às ${row.eta_display},
  ${row.status_label}` ``. Enquanto a projection não manda, o honesto na TV é **não
  afirmar a unidade**: só o número, com o nome do produto ao lado.

## C2. O Painel mostra três quantidades diferentes na mesma coluna

- **Onde:** a mesma palheta de C1. O comentário do campo em
  `shopman/backstage/projections/production.py` diz o que ele é:
  `qty: str  # a quantidade RELEVANTE do momento (planejada→iniciada→real)`. O código
  confirma: `arrived` → `wo.finished`; `STARTED` → `_wo_started_qty(wo) or
  wo.quantity`; planejada → `wo.quantity`.
- **Defeito:** D4.
- **Por que dói:** três grandezas do dia entram na mesma coluna, e nada na linha diz
  qual delas é. Duas linhas lado a lado — `"40 UN · PLANEJADO"` e `"36 UN ·
  CONFIRMADO"` — parecem comparáveis e não são: a primeira é uma intenção, a segunda é
  um fato. Quem lê a TV para decidir se sobra pão soma as duas.
- **Substituição:** a coluna de status já distingue os três momentos; a de quantidade
  passa a dizer o seu sufixo quando não é fato consumado —
  `"40 previstas"` / `"36 no forno"` / `"36"` (sem sufixo quando confirmado, porque aí
  o número é o que saiu). Se a largura da palheta não permitir, o mínimo é o sufixo de
  uma letra que o Solari comporta: `"40 p"` / `"36 f"` / `"36"`, com a legenda fixa no
  rodapé do Painel.

## C3. "PREVISTO" é o status da fornada que já está no forno

- **Onde:** `_FORECAST_STATUS_LABELS` em
  `shopman/backstage/projections/production.py`:
  `scheduled → "Planejado"`, `in_progress → "Previsto"`, `delayed → "Atrasado"`,
  `arrived → "Confirmado"`. Renderizado em `production-nuxt/app/pages/board.vue`.
- **Defeito:** D1 (rótulo que mente) e D2 (a palavra não nomeia o estado).
- **Por que dói:** três dos quatro rótulos falam do **estado da fornada** (planejada,
  atrasada, confirmada). O quarto fala da **natureza do horário** (previsto). O
  resultado é que a fornada que está assando neste momento aparece na TV como
  *PREVISTO* — uma palavra que soa **menos** concreta que *PLANEJADO*, o rótulo de quem
  nem começou. O atendente que olha a TV para responder ao cliente conclui, pela
  palavra, que ainda não começou nada. É exatamente a informação que a TV existe para
  dar.
- **Substituição:** a coluna passa a falar só do estado da fornada, na ordem em que o
  forno acontece:
  - `scheduled → "PLANEJADO"` (fica)
  - `in_progress → "NO FORNO"`
  - `delayed → "ATRASADO"` (fica)
  - `arrived → "PRONTO"`
  `"NO FORNO"` cabe nos 10 caracteres de `STATUS_CHARS`; `"PRONTO"` também.

## C4. O quadrado de fechar a fornada mostra dois números com um rótulo só

- **Onde:** `production-nuxt/app/pages/expedite.vue`, o ladrilho de 80 px:
  `{{ cardAnchor(order) }} un.` A função é
  `cardAnchor(order) => order.started_qty || order.planned_qty`.
- **Defeito:** D4.
- **Por que dói:** o número é o que entrou no forno **ou** o que foi planejado — os dois
  com a mesma tipografia, o mesmo `un.` e nenhuma marca que os distinga. Eles só
  divergem quando importa: o comentário do próprio arquivo diz *"A fornada real que
  entrou no forno (started): quando diverge do previsto, é ELA que ancora o
  fechamento"*. O padeiro toca no ladrilho achando que confirma 40 (o que planejou) e
  está confirmando 36 (o que enfornou) — ou o contrário, e não tem como saber qual.
- **Substituição:** duas linhas no ladrilho, o rótulo acima do número:
  - com `started_qty`: `"NO FORNO"` / `"36 un."`
  - sem: `"PREVISTO"` / `"40 un."`
  A palavra `"Confirmar"` embaixo continua onde está (ver C8).

## C5. "40 produzidos" no cabeçalho de uma fornada que não foi produzida

- **Onde:** `production-nuxt/app/components/QcCloseScreen.vue`, o selo do cabeçalho:
  `{{ anchor.anchor }} produzidos` / `"Sem quantidade produzida"`. A âncora vem de
  `ovenAnchor(planned, started)` em `production-nuxt/app/presentation/qc.ts`, que
  devolve `started !== null ? started : planned`.
- **Defeito:** D1.
- **Por que dói:** este é o único número da tela de fechamento, e é dele que saem todos
  os padrões (`initialState` preenche `fullQty` com ele). Quando a fornada foi
  confirmada na Produção, "produzidos" é a palavra certa — é o vocabulário da casa
  (`stage=produce` rotula a coluna de ação como **Produzido**). Mas a Expedição também
  fecha fornada **planejada e nunca produzida** (`can_close` aceita
  `status == PLANNED`), e aí o selo afirma que 40 foram produzidos quando nada foi.
  O padeiro confirma o padrão e grava 40 produzidos que não existiram.
- **Substituição:** o rótulo segue a âncora usada.
  - âncora = `started_qty`: `"40 produzidos"` (fica)
  - âncora = `planned_qty`: `"40 previstos · nada produzido ainda"`
  - sem âncora (fornada avulsa): `"Fornada avulsa — conte quanto saiu"` no lugar de
    `"Sem quantidade produzida"`, que hoje soa como erro.

## C6. "12 planejados" com uma barra que mede outra coisa

- **Onde:** `production-nuxt/app/components/ProductionStageGrid.vue`, `headerCount`:
  `{ count: counts.planned, label: "planejados" }` no Planejamento e
  `{ count: counts.started, label: "produzidos" }` na Produção; renderizados por
  `ProductionHeader.vue` com a barra de `dayProgress` logo abaixo. `counts.planned` é
  `len(by_status[WorkOrder.Status.PLANNED])` — **contagem de fornadas**. `dayProgress`
  é `finished_qty / (planned_qty + started_qty + finished_qty)` — **razão de
  quantidades**.
- **Defeito:** D4, e o comentário do template torna o defeito explícito: *"O percentual
  mora COM o número que ele resume — nunca longe dele."* Ele não resume aquele número.
- **Por que dói:** é o primeiro número que o padeiro lê ao abrir a tela de manhã, e a
  leitura natural de `"12 PLANEJADOS"` numa padaria é *doze pães*. São doze **fornadas**
  — que podem somar quatrocentas peças. Embaixo, colada, uma barra de 30% que fala de
  peças, não de fornadas. Quem lê o bloco inteiro como uma frase — e ele foi desenhado
  para ser lido assim — conclui que 30% de doze coisas já saiu.
- **Substituição:** o substantivo entra, e a barra ganha o seu próprio número.
  - Planejamento: `"12 fornadas planejadas"`, e sob a barra
    `"0 de 400 un. concluídas"`.
  - Produção: `"8 fornadas produzidas"`, mesma barra.
  Se não couber na horizontal, o número da barra vai para o `aria-label` e para o
  `title`, mas o substantivo **fornadas** não sai do número de cima.

## C7. "Quantidade concluída." — a fornada é que foi concluída

- **Onde:** `production-nuxt/app/pages/expedite.vue`, `onConfirm`:
  `useSonner.success(correcting ? "Qualidade corrigida." : "Quantidade concluída.")`.
- **Defeito:** D1 e D2 — o aviso nomeia o objeto errado e usa um verbo que não é o do
  ato.
- **Por que dói:** é a confirmação do gesto mais caro do app: fechar a fornada, gravar
  a partição de qualidade, dar baixa na perda e liberar os avisos de disponibilidade.
  O que aparece é uma frase sobre uma *quantidade*, que não foi concluída nem é o
  objeto. O padeiro não recebe a confirmação do que acabou de fazer, e — pior — não
  recebe o número. Se ele digitou 222 no lugar de 22 e passou pela guarda de
  plausibilidade, esta era a última chance de ver o erro.
- **Substituição:** `` `Fornada de ${order.recipe_name} fechada · ${total} un.` `` e, na
  correção, `` `Qualidade da fornada de ${order.recipe_name} corrigida.` ``

## C8. O botão que fecha a fornada só diz "Confirmar"

- **Onde:** `production-nuxt/app/components/QcCloseScreen.vue`, o botão grande do
  rodapé: `"Confirmar"` — e, enquanto envia, `"Fechando a fornada…"`.
- **Defeito:** D2 (verbo genérico apaga o ato).
- **Por que dói:** a régua diz, na regra de caminho de D1, que **só o último passo diz o
  verbo do ato**. Este é o último passo — e é o único do caminho que não diz o verbo.
  O ato real só aparece no estado ocupado, isto é, **depois** que a pessoa já não pode
  escolher. E `"Confirmar"` é justamente a palavra que ela já tocou duas vezes para
  chegar aqui (na célula da grade e no ladrilho do painel), sem que nada tivesse
  acontecido; a terceira é irreversível e se parece com as outras duas.
- **Substituição:** `"Fechar a fornada"`, com o ocupado
  `"Fechando a fornada…"` (que já existe) e, no modo correção, `"Salvar correção"` /
  `"Salvando correção…"` (que já existem e estão certos). Nada muda no caminho antes
  dele — ver a dúvida registrada em **G1**.

## C9. "Nenhuma fornada planejada para hoje" numa tela que não é de hoje

- **Onde:** `production-nuxt/app/pages/expedite.vue`, o vazio do painel:
  `"Nenhuma fornada planejada para hoje."` O `v-else-if` não olha a data selecionada,
  e a própria tela existe para poder voltar a dias anteriores — o aviso acima diz
  `"N fornadas abertas de dias anteriores. Toque para ver."`
- **Defeito:** D1.
- **Por que dói:** o caminho é exatamente este: o padeiro toca no aviso âmbar para
  fechar a fornada esquecida de ontem, a data muda para ontem, a lista vem vazia (por
  filtro, por busca ainda preenchida, por qualquer motivo) e a tela responde **"para
  hoje"**. Ele conclui que voltou para hoje e que a fornada de ontem sumiu.
- **Substituição:** `` `Nenhuma fornada para ${kiosk.selected_date_display}.` ``, usando
  o campo que a projection já manda e que o chip de data já exibe.

## C10. "Foram contabilizadas 222 de 22 unidades?"

- **Onde:** `production-nuxt/app/components/QcCloseScreen.vue`, `sheetTitle` do caso
  `overshoot`: `` `Foram contabilizadas ${total} de ${anchor.anchor} unidades?` ``. A
  pergunta só aparece quando `overshootQty(state) > 0`, isto é, quando o total é
  **maior** que a âncora.
- **Defeito:** D3, e é o pior lugar possível para ele.
- **Por que dói:** "X de Y" é a gramática de uma fração, e por construção aqui X é
  sempre maior que Y. A frase se lê como um erro de digitação **da própria tela**. E
  este sheet existe, segundo o comentário do arquivo, para matar exatamente o typo de
  *222 no lugar de 22* — é a guarda de plausibilidade do fechamento. Uma guarda que se
  expressa numa frase malformada é lida como bug e dispensada com um toque.
- **Substituição:** duas frases curtas, o fato antes da pergunta:
  `` `Você contou ${total}. Para o forno foram ${anchor.anchor}.` `` como título, e
  `"Confere?"` como subtítulo. Os dois botões continuam `"Corrigir"` (ver P5) e
  `` `Confirmar ${total} unidades` ``.

## C11. "Atualizar ao reconectar" atualiza agora

- **Onde:** `production-nuxt/app/composables/useProductionMutationGuard.ts`. No bloco
  `offline`, a recuperação é
  `{ action: "refresh", label: "Atualizar ao reconectar" }`, e `notify()` monta o toast
  com `action: { label, onClick: () => void refreshSafely() }` — que atualiza **na
  hora**.
- **Defeito:** D1.
- **Por que dói:** o rótulo promete um comportamento automático futuro; o botão executa
  uma ação imediata que, estando offline, falha e emite um **segundo** toast de erro
  (`"Não foi possível atualizar os dados. Tente novamente."`). O padeiro toca num botão
  que diz que vai esperar a conexão voltar e recebe um erro novo por cima do primeiro.
- **Substituição:** `"Tentar de novo"` (o rótulo da casa — ver E2), que é o que o botão
  de fato faz. Se a casa quiser mesmo a espera automática, aí o rótulo fica e o
  `onClick` passa a agendar o refresh no evento `online`.

---

# Parte D — Produção: faz parar para pensar (D2, D3, D5, D7)

> As fichas desta parte são numeradas **P1–P20** de propósito: numerá-las "D1, D2…"
> colidiria com os nomes dos defeitos da régua, que é exatamente o erro que esta parte
> cataloga.

## P1. Uma fornada tem quatro nomes, conforme a tela

- **Onde:** medido em `production-nuxt/app/` (só `.vue`), sobre o mesmo objeto
  `WorkOrder`:
  - **fornada** — 58 ocorrências (`expedite.vue`, `board.vue`, `QcCloseScreen.vue`,
    `ProductionStageGrid.vue`);
  - **lote** — `ProductionStageGrid.vue`: `"Planejar novo lote"`, `"Novo lote"`,
    `"Novo lote planejado"`, `"Confirmar novo lote"`;
  - **OP** — `reports.vue`: `"OPs concluídas"`, `"OPs planejadas"`, cabeçalho de coluna
    `"OP"`;
  - **Ordens** — `reports.vue`, dois títulos de seção.
- **Defeito:** D7c — o mesmo conceito com nomes diferentes conforme a porta de entrada.
- **Por que dói:** é o subtipo que a régua chama de pior do que não entender: *"quem
  aprende o app por uma tela não reconhece a outra — e conclui que são coisas
  diferentes"*. O padeiro fecha **fornadas** a manhã inteira e, ao abrir Relatórios,
  lê `"OPs concluídas: 8"` — uma sigla que não existe em nenhuma outra tela — e não
  sabe se aquilo conta o mesmo que ele fez. No Planejamento, ele planeja um **lote** que
  no dia seguinte chega à Expedição como **fornada**.
- **Substituição:** **fornada**, em todas as quatro portas. É o nome do negócio, é o
  majoritário por larga margem, e é o que o padeiro fala.
  - `"Planejar novo lote"` → `"Planejar outra fornada"`
  - `"Novo lote"` (verbo da célula) → `"Outra fornada"`
  - `"Novo lote planejado"` (toast) → `"Outra fornada planejada"`
  - `"Confirmar novo lote"` → `"Confirmar a fornada"`
  - `"OPs concluídas"` → `"Fornadas concluídas"` · `"OPs planejadas"` →
    `"Fornadas planejadas"` · coluna `"OP"` → `"Fornada"` · seções `"Ordens"` →
    `"Fornadas"`.

## P2. "estação" é três coisas diferentes

- **Onde:** três sentidos vivos ao mesmo tempo, dois deles dentro da Produção:
  - **posto do operador** — `mise-en-place.vue`:
    `"Checklist local desta estação"` (vem do `stationRef` do `useOperatorLock`);
  - **agente de impressão** — `useProductionLabelPrinting.ts`:
    `"Aguardando estação"`, `"Verifique a estação"`, `"Estação da Preparação"`;
    `ProductionLabelPrintDialog.vue`: `"A estação de impressão não está disponível."`;
  - **tela da cozinha** — `kds-nuxt/app/pages/index.vue`: `"Escolha uma estação"`,
    `"Nenhuma estação configurada."`; `[ref].vue`: `"Estação KDS"`.
- **Defeito:** D7b (colisão dentro do mesmo app) e D7c (entre os dois apps).
- **Por que dói:** "estação" é português comum — nenhuma lista de palavras proibidas
  pega uma palavra legítima. É por isso que ela derivou. O efeito prático: a mesma
  pessoa lê `"Verifique a estação"` na Preparação (quer dizer: a impressora não
  respondeu) e `"Escolha uma estação"` no KDS (quer dizer: escolha uma tela). Se a
  impressora não sai, ela vai procurar o problema no lugar errado.
- **Substituição:** um nome por conceito, e o nome mais concreto ganha.
  - impressão → **impressora**: `"Aguardando a impressora"`, `"Confira a impressora"`,
    `"Impressora da Preparação"`, `"A impressora não está disponível."`
  - posto do operador → **bancada**: `"Marcações desta bancada"` (ver P8).
  - tela da cozinha → **estação** fica com o KDS, sozinha.

## P3. "saldo" é o que falta contar e também o que tem no estoque

- **Onde:**
  - `QcCloseScreen.vue`: `"Dois toques usam o saldo"`, `"Escolha um grau ou Perda;
    dois toques usam o saldo disponível."`, e o rótulo `"Saldo automático"` sob o grau
    padrão;
  - `mise-en-place.vue`: a coluna **`"Saldo"`** da tabela de insumos, que mostra
    `line.available_display` — o estoque físico disponível, com `"Falta"` embaixo
    quando `is_short`.
- **Defeito:** D7b.
- **Por que dói:** o padeiro acabou de separar insumo olhando a coluna *Saldo* (quanto
  tem). Meia hora depois, no fechamento da fornada, lê *"dois toques usam o saldo"* e
  entende "o que tem". O saldo ali é outra coisa: o que ainda não foi contado nesta
  fornada. Ele toca duas vezes num grau menor e vê o número saltar para a fornada
  inteira, sem entender por quê.
- **Substituição:** a palavra sai do fechamento e fica com o estoque.
  - `"Dois toques usam o saldo"` → `"Dois toques preenchem o que falta contar"`
  - `"Escolha um grau ou Perda; dois toques usam o saldo disponível."` →
    `"Escolha um grau ou Perda. Dois toques preenchem com o que ainda não foi contado."`
  - `"Saldo automático"` → `"Recebe o que sobrar"`

## P4. O mesmo campo se chama "iniciada" na tela e "produzida" no leitor de tela

- **Onde:** `production-nuxt/app/components/QcCloseScreen.vue`, sheet do overshoot. O
  rótulo visível é `"Por que a contagem ficou acima da fornada iniciada?"`; o
  `aria-label` do `UiTextarea` logo abaixo é
  `"Motivo da quantidade acima da fornada produzida"`.
- **Defeito:** D7c, no caso mais curto possível: duas palavras para o mesmo fato, no
  mesmo controle.
- **Por que dói:** além da divergência em si, `"iniciada"` é a palavra que a casa
  **retirou de propósito** da Produção — a decisão de 16/09 está escrita no cabeçalho
  de `ProductionStageGrid.vue`: *"Sem 'iniciar', sem subetapas, sem máquina de
  estados"*, e a coluna de ação passou a se chamar **Produzido**. O rótulo visível é o
  resíduo que a varredura daquela decisão não pegou.
- **Substituição:** as duas viram a mesma frase, no vocabulário que ficou:
  - visível: `"Por que a contagem ficou acima do que foi produzido?"`
  - `aria-label`: `"Motivo da contagem acima do que foi produzido"`

## P5. "Corrigir" é dois atos diferentes na mesma tela

- **Onde:** `QcCloseScreen.vue`, sheet do overshoot: botão `"Corrigir"` (volta ao
  numpad para o operador refazer o número). `expedite.vue`, cartão de fornada fechada:
  botão `"Corrigir qualidade"` + `screenMode === "correct"` com o cabeçalho
  `"Correção de qualidade · "` e o botão `"Salvar correção"`.
- **Defeito:** D7b.
- **Por que dói:** um *Corrigir* desfaz uma digitação e não sai da tela; o outro abre um
  registro auditado de correção de qualidade, que conta em `correction_count` e aparece
  no cartão como `"3 correções"`. O primeiro é grátis; o segundo fica na ficha. Estão a
  dois toques um do outro.
- **Substituição:** o barato perde a palavra cara.
  - botão do overshoot: `"Voltar e recontar"`
  - `"Corrigir qualidade"` e `"Salvar correção"` ficam como estão.

## P6. "Confirmar qualidade" produz o estado "Qualidade revisada"

- **Onde:** `production-nuxt/app/pages/expedite.vue`. Botão: `"Confirmar qualidade"`
  (ocupado: `"Confirmando…"`). Confirmação: `"Confirmar a qualidade da fornada de X?
  Isso libera os avisos de disponibilidade autorizados pelos clientes."` Toast:
  `"Qualidade confirmada."` Estado resultante no cartão:
  `"Qualidade revisada"` / `"Aguardando revisão"`. A função se chama `reviewQuality`.
- **Defeito:** D7c.
- **Por que dói:** o operador toca em **confirmar**, lê **confirmada** no toast e,
  no mesmo cartão, um segundo depois, vê **revisada**. Três palavras, um ato. Quem
  chega pelo cartão (`"Aguardando revisão"`) procura um botão de revisar e não encontra
  nenhum.
- **Substituição:** **confirmar** ganha, porque é o que o botão diz e o que o operador
  faz.
  - `"Qualidade revisada"` → `"Qualidade confirmada"`
  - `"Aguardando revisão"` → `"Falta confirmar a qualidade"`
  - o resto fica.

## P7. "libera os avisos de disponibilidade autorizados pelos clientes"

- **Onde:** `production-nuxt/app/pages/expedite.vue`, o `window.confirm` de
  `confirmQuality`: `` `Confirmar a qualidade da fornada de ${order.recipe_name}? Isso
  libera os avisos de disponibilidade autorizados pelos clientes.` ``
- **Defeito:** D7a (jargão) sobre a única frase que diz a **consequência externa** do
  gesto.
- **Por que dói:** "avisos de disponibilidade autorizados pelos clientes" é o nome
  interno do Avise-me (`StockAlertSubscription` + consentimento). O padeiro lê uma
  oração de sete palavras técnicas e não descobre o que ele vai disparar: mensagens
  para pessoas de verdade, agora, que não dá para desdizer. É a informação mais
  importante do diálogo, escondida atrás do vocabulário do repositório.
- **Substituição:** `` `Confirmar a qualidade da fornada de ${order.recipe_name}?\n\nQuem
  pediu para ser avisado quando este produto voltasse recebe a mensagem agora. Não dá
  para desfazer.` ``

## P8. "Checklist local desta estação · não é registro de auditoria"

- **Onde:** `production-nuxt/app/pages/mise-en-place.vue`:
  `Checklist local {{ stationRef ? "desta estação" : "deste dispositivo" }} · não é
  registro de auditoria`.
- **Defeito:** D7a (`checklist`) + D6 (a frase termina dizendo o que o sistema **não**
  é) + D2 (o que a pessoa precisa saber é quem mais enxerga aquelas marcações).
- **Por que dói:** o padeiro não sabia que havia um registro de auditoria em jogo, e
  agora tem que ler a defesa contra uma preocupação que não era dele. A pergunta real
  que a marcação levanta — *se eu marcar, o outro turno vê?* — fica sem resposta.
- **Substituição:** `"As marcações ficam nesta bancada. Ninguém mais vê, e elas somem
  quando o planejamento muda."` (a segunda metade é verdade: o próprio arquivo já avisa
  `"O planejamento mudou. Confira esta revisão; as marcações da lista anterior foram
  limpas."`)

## P9. "Explodir até matéria-prima"

- **Onde:** `production-nuxt/app/pages/mise-en-place.vue`, o rótulo do checkbox
  `"Explodir até matéria-prima"`.
- **Defeito:** D7a.
- **Por que dói:** *explodir* é o verbo de BOM explosion, vindo inteiro do vocabulário
  de engenharia de manufatura. Na boca do forno, "explodir" tem outro significado, e o
  que a caixinha faz é o oposto de uma explosão: ela abre o pré-preparo para mostrar o
  que tem dentro.
- **Substituição:** `"Abrir os pré-preparos"`, com o `title`
  `"Mostra a farinha, a água e o sal que estão dentro de cada pré-preparo, em vez do
  pré-preparo pronto."`

## P10. "Não foi possível confirmar o fato do forno."

- **Onde:** `production-nuxt/app/composables/useOvenFacts.ts`:
  `"Não foi possível confirmar o fato do forno. Tente novamente."`
- **Defeito:** D7a.
- **Por que dói:** "o fato do forno" é o nome que o código dá ao evento declarado ao
  servidor (`ovenFacts.armed` / `ovenFacts.concluded`). É uma abstração que não existe
  para quem está com a pá na mão: o padeiro acabou de tocar em **Iniciar** ou em
  **Confirmar** e recebe uma frase sobre um *fato*. Ele não sabe o que falhou, nem se o
  timer está valendo — e o próprio diálogo emenda `"O timer local não foi alterado."`,
  que só faz sentido se você já sabia que havia dois registros.
- **Substituição:** duas mensagens, uma por ato, dizendo o que continua valendo:
  - ao armar: `"Não deu para registrar que a fornada entrou no forno. O timer desta
    tela continua contando. Tente de novo."`
  - ao concluir: `"Não deu para registrar que a fornada saiu do forno. Tente de novo
    antes de fechar a fornada."`

## P11. "Reconciliar relatório"

- **Onde:** `production-nuxt/app/pages/reports.vue`:
  `"O relatório mudou enquanto você navegava."` + botão `"Reconciliar relatório"`. O
  `@click` é `applyFilters()`.
- **Defeito:** D7a e D2 — o verbo é de contabilidade de sistema e não nomeia o que
  acontece (recarregar a consulta desde a primeira página).
- **Substituição:** `"Recarregar do começo"`. E o aviso ganha a consequência:
  `"Os dados mudaram enquanto você navegava. Recarregar volta para a primeira página."`

## P12. "Enviado à impressora configurada neste PC."

- **Onde:** `production-nuxt/app/components/ProductionLabelPrintDialog.vue`:
  `localPrintNote.value = "Enviado à impressora configurada neste PC."` — e, no mesmo
  fluxo, `useProductionLabelPrinting.ts` diz
  `"A impressão deste dispositivo não respondeu."`
- **Defeito:** D7a e D7c — **e é a única string de tela destes dois apps que contraria
  uma regra escrita do `CLAUDE.md`**: *"'dispositivo', nunca 'aparelho'"*, para toda
  superfície de operador. "PC" é um terceiro nome, a duas telas de distância de
  "dispositivo".
- **Por que dói:** a trava que existe (`test_vocabulario_de_tela.py`) varre **só
  Python** — é o buraco nomeado na §5.2 da régua. Esta string é a prova do buraco na
  Onda 2: uma regra da casa, com teste, sendo quebrada num `.vue` sem que nada acuse.
  E na bancada o efeito é concreto: em tablet, a impressão local não existe, e "PC"
  faz o padeiro procurar um computador.
- **Substituição:** `"Enviado à impressora deste dispositivo."` E, de passagem, este
  achado é o caso de uso mais barato do `WP-COPY-VUE-SWEEP` (§5.5 da régua): a
  varredura de `aparelh` estendida a `.vue`/`.ts` teria pego, se a lista incluísse
  `\bPC\b` e `computador`.

## P13. "A prova para imprimir não veio nesta tela" e a impressão "indisponível neste contexto"

- **Onde:** `production-nuxt/app/composables/useProductionLabelPrinting.ts`:
  `"A autorização para imprimir não veio nesta tela. Atualize os dados."`,
  `"A prova para imprimir não veio nesta tela. Atualize os dados."`,
  `"A impressão está indisponível neste contexto."`
- **Defeito:** D7a (`prova` é o `override_proof` do contrato; `contexto` é a palavra do
  programador) e D3 (a pessoa não descobre o que fazer além de "atualizar").
- **Por que dói:** três mensagens para o mesmo bloqueio, duas delas com palavras que
  não existem na padaria, e a terceira sem nenhuma pista. Se atualizar não resolver —
  e não vai resolver quando for falta de permissão — o padeiro fica no laço.
- **Substituição:** duas mensagens, separadas pela causa real.
  - tela velha: `"Esta tela está velha demais para imprimir. Atualize e tente de
    novo."` (as duas primeiras viram esta)
  - sem permissão: `"Imprimir etiquetas pede uma permissão que este operador não tem.
    Peça a liberação a quem administra a loja."` — a mesma frase que `reports.vue` já
    usa para o seu bloqueio, e que está certa.

## P14. Os nove estados da impressão trocam de sujeito a cada linha

- **Onde:** `production-nuxt/app/composables/useProductionLabelPrinting.ts`:
  `"Pronta para enviar"` · `"Aguardando estação"` · `"Enviado à fila"` ·
  `"Pronta para abrir a impressão"` · `"Aguardando confirmação"` ·
  `"Saída confirmada"` · `"Falha confirmada"` · `"Envio sem confirmação"` ·
  `"Cancelada"`.
- **Defeito:** D3 — o leitor tem que descobrir, a cada linha, de quem se fala.
- **Por que dói:** o gênero pula entre *Pronta* (etiqueta?), *Enviado* (envio?) e
  *Cancelada* (impressão?), e o sujeito muda junto. Pior é **`"Falha confirmada"`**:
  duas das nove linhas terminam em *confirmada* e significam o oposto uma da outra
  (`"Saída confirmada"` = saiu; `"Falha confirmada"` = não saiu). Num relance, com a
  bandeja na mão, a palavra que fica é *confirmada*.
- **Substituição:** um sujeito só — **as etiquetas** — e o resultado dito sem rodeio:
  `"Prontas para enviar"` · `"Esperando a impressora"` · `"Na fila da impressora"` ·
  `"Prontas para abrir a impressão"` · `"Esperando você confirmar"` · `"Saíram"` ·
  `"Não saíram"` · `"Enviadas, sem confirmação"` · `"Canceladas"`.

## P15. "Substitui #WO-2026-00042 (40) — 0 remove."

- **Onde:** `production-nuxt/app/components/ProductionStageGrid.vue`, diálogo de plano
  no modo `adjust`: `Substitui #{{ selectedPlannedOrder.ref }} ({{ planned_qty }}) — 0
  remove.`
- **Defeito:** D5 (zero como código secreto) — o caso exato do catálogo, e o único dos
  dois apps.
- **Por que dói:** a tela ensina o operador a decorar que digitar zero **apaga a
  fornada planejada**. Apagar é um ato; ele merece um controle, não uma decoreba. E o
  numpad tem um botão `"C"` (limpar) a poucos centímetros, que zera o campo por outro
  motivo — o caminho para apagar sem querer está pronto.
- **Substituição:** o interruptor que o D5 pede.
  - a frase vira `"Substitui a fornada #WO-2026-00042, que hoje tem 40."`;
  - e um botão separado no rodapé do diálogo: `"Remover do plano"`, com confirmação
    `"Remover a fornada de {nome} do plano de {data}?"`.
  Enquanto o botão não existir, o mínimo é dizer o efeito por extenso, não o código:
  `"Substitui a fornada #WO-2026-00042, que hoje tem 40. Digitar 0 apaga o
  planejamento dela."`

## P16. Três frases que dizem o fato e param antes do que fazer

- **Onde:** `production-nuxt/app/components/ProductionStageGrid.vue` e
  `pages/expedite.vue`:
  - `Soma ao dia · {{ started_qty }} produzidas · {{ finished_qty }} concluídas.`
  - `Diferente do planejado ({{ planned_qty }}).`
  - `· {{ order.committed_qty }} comprometidas`
- **Defeito:** D3 (frase que obriga a completar sentido), três vezes.
- **Por que dói:**
  - *"Soma ao dia"* — soma **o quê** ao dia? A frase abre num verbo sem sujeito, e os
    dois números que a seguem são de outra coisa (o que já saiu), o que faz parecer que
    eles é que serão somados.
  - *"Diferente do planejado (40)."* — diz um desvio e para. O comentário do código diz
    o que faltava: *"é rendimento, não perda"*. Sem isso, o padeiro hesita: precisa
    justificar? Vai gerar perda? Ele confere duas vezes, que é o custo que esta onda
    existe para evitar.
  - *"12 comprometidas"* — comprometidas o quê. Unidades. E comprometidas com quem:
    com pedidos já vendidos. A palavra sozinha, em roxo, ao lado de um SKU, não fecha.
- **Substituição:**
  - `"Cria outra fornada, que soma ao total do dia. Hoje já saíram {started} produzidas
    e {finished} concluídas."`
  - `"Diferente do planejado ({planned}). É rendimento da massa — não precisa
    justificar."`
  - `"{committed} un. já têm dono (pedidos de clientes)"`

## P17. "38 OK · 4 com desconto · 2 de perda"

- **Onde:** `production-nuxt/app/pages/expedite.vue`, no cartão de fornada fechada:
  `{{ order.full_price_qty || "0" }} OK`, `· {{ order.discounted_qty }} com desconto`,
  `· {{ order.loss_qty }} de perda`.
- **Defeito:** D3 e D7a (`"OK"`).
- **Por que dói:** os três números não têm unidade e o primeiro tem um rótulo que não
  é do domínio: *OK* não é um grau de qualidade — os graus vêm de `kiosk.grades` e têm
  nome próprio (é o que a tela de fechamento mostra). É a linha que o padeiro consulta
  para decidir se corrige a qualidade da fornada, e ela apaga a informação que decide.
- **Substituição:** `"38 un. a preço cheio · 4 com desconto · 2 de perda"`. E, se o
  espaço permitir, o nome do grau no lugar de "a preço cheio", que é o que a tela de
  correção vai mostrar.

## P18. "Sem insumo (casar no editor)"

- **Onde:** `production-nuxt/app/pages/recipes/` — `"Sem insumo (casar no editor)"`;
  e, ao lado, `"Todos os ingredientes têm insumo."`
- **Defeito:** D7a.
- **Por que dói:** *casar* é o verbo de quem escreve o mapeamento; na ficha, o que se
  faz é ligar o ingrediente escrito a um insumo cadastrado. A frase pede uma ação com
  um verbo que a tela não oferece em lugar nenhum (não há nenhum botão "Casar").
- **Substituição:** `"Sem insumo — ligue a um insumo no editor"`.

## P19. "Do planejado sobre a capacidade diária"

- **Onde:** `production-nuxt/app/pages/reports.vue`, o `title` do cartão
  `"Capacidade"`.
- **Defeito:** D3.
- **Por que dói:** é uma razão descrita pelos seus operandos, sem dizer o que ela
  significa nem o que um número alto quer dizer. O gestor lê `"Capacidade 140%"` e não
  sabe se isso é bom (dia cheio) ou alarme (planejou além do que o forno faz).
- **Substituição:** `"Quanto do dia já está planejado, em relação à capacidade que as
  fichas declaram. Acima de 100% o plano passa do que cabe."`

## P20. "Identificação interna" é um botão que imprime

- **Onde:** `production-nuxt/app/pages/mise-en-place.vue`, lado a lado:
  `"Etiquetas de pesagem"` e `"Identificação interna"` (com `title`
  `"Identificação interna: nome, data prevista e validade configurada"`); o diálogo que
  o segundo abre se chama `"Identificação interna do preparo"`.
- **Defeito:** D2 — um rótulo nomeia a coisa (etiqueta), o irmão nomeia uma abstração.
- **Por que dói:** os dois botões fazem a mesma coisa (imprimir etiquetas), e só um diz
  isso. Quem precisa de etiqueta lê o primeiro e para ali, sem descobrir que o segundo
  também é etiqueta — de outro tipo.
- **Substituição:** `"Etiquetas de pesagem"` e `"Etiquetas de identificação"`, com o
  `title` do segundo mantido. O diálogo acompanha:
  `"Etiquetas de identificação do preparo"`.

---

# Parte E — os dois juntos: o vocabulário que muda na porta de entrada

Esta é a parte que só existe porque os dois apps foram lidos no mesmo relatório. O
padeiro que confirma a fornada às 6h e o cozinheiro que finaliza o pedido às 11h são,
em metade dos turnos, a mesma pessoa.

## E1. "Ciente" (KDS) e "Visto" (Produção) são o mesmo gesto

- **Onde:**
  - KDS — `pages/[ref].vue`: `"Ciente"` no cartão de cancelado
    (`aria-label="Dar baixa no cancelado"`) e `"Ciente"` no cabeçalho
    (`aria-label="Reconhecer aviso de ticket novo"`);
  - Produção — `components/AlertsBell.vue`: `aria-label="Marcar alerta como visto"`,
    `title="Visto"`; `components/FloorTimersPanel.vue` e `pages/expedite.vue`:
    `"Visto"` para silenciar o alarme do timer.
- **Defeito:** D7c.
- **Por que dói:** *eu vi, pode parar de me avisar* é um único gesto, e a casa tem duas
  palavras para ele — uma por app. Some a isso o problema interno do KDS (B1) e o
  resultado é: **duas palavras, três atos**, sem nenhuma correspondência entre elas.
  Quem aprende "Visto" na Produção procura "Visto" no KDS e encontra "Ciente" em dois
  botões que fazem coisas diferentes.
- **Substituição:** **`"Visto"`** nos dois apps, para o gesto de *silenciar/reconhecer
  um aviso* — é o mais curto, o mais usado e o que já tem o ícone de olho na Produção.
  E o gesto do KDS que **não** é esse (destravar o pedido cancelado) sai da palavra e
  vira `"Recebi o cancelamento"`, como em B1. Fica: um nome por gesto, o mesmo nos dois
  apps.

## E2. "Tentar de novo" (8) contra "Tentar novamente" (5)

- **Onde:** medido nos dois apps mais o kit que eles montam:
  - `"Tentar de novo"` — 8 ocorrências (`mise-en-place.vue` ×2, `reports.vue`,
    `recipes/`, e as variantes `"Tente de novo."` nos toasts do KDS e da Produção);
  - `"Tentar novamente"` / `"Tente novamente."` — 5:
    `operator-kit/app/components/OperatorSessionUnavailable.vue` (que **as duas
    superfícies montam**), `production-nuxt/.../ProductionLabelPrintDialog.vue`,
    `useProductionMutationGuard.ts`, `useOvenFacts.ts`,
    `useProductionLabelPrinting.ts`.
- **Defeito:** D7c. A régua já nomeou esta dívida (§3/D7c: *"Não é uma escolha a fazer;
  é uma varredura a terminar"*) e mediu 4 stragglers no HEAD de 18/09. Nestes dois apps
  mais o kit, são **5** — e a mais cara é a do kit, porque ela aparece em toda
  superfície de operador.
- **Substituição:** `"Tentar de novo"` em todas, e `"Tente de novo."` nos toasts. A do
  `operator-kit` primeiro: ela sozinha corrige o rótulo nos nove apps.

## E3. Onze redações para "o que você está vendo pode estar velho"

- **Onde:** medido nos dois apps, todas em texto de tela:

  | Redação | Arquivo |
  |---|---|
  | `"Sem atualizar. Mostrando o último painel carregado."` | `production/pages/expedite.vue` |
  | `"Sem atualizar. Mostrando a última leitura."` | `production/pages/recipes/` |
  | `"Sem atualizar — mostrando a última lista carregada."` | `production/pages/mise-en-place.vue` |
  | `"Sem atualizar. Mostrando a última lista carregada."` | `production/pages/recipes/` |
  | `"Sem atualizar — mostrando os últimos preparos carregados."` | `production/pages/mise-en-place.vue` |
  | `"Sem atualizar — mostrando o último quadro carregado."` | `production/components/ProductionStageGrid.vue` |
  | `"Sem atualizar — mostrando a última página aplicada."` | `production/pages/reports.vue` |
  | `"Sem sinal — mostrando o último quadro"` (+ o selo `"sem sinal"`) | `production/pages/board.vue` |
  | `"Sinal perdido — reconectando…"` | `production/pages/board.vue` |
  | `"Sem conexão — mostrando o último estado. Reconectando…"` | `kds/pages/[ref].vue` |
  | `"Sem conexão — tentando reconectar…"` | `operator-kit/.../OfflineBanner.vue` |

- **Defeito:** D7c (N redações para o mesmo estado) e D8 (sete delas dizem em nove
  palavras o que cabe em quatro).
- **Por que dói:** onze frases, dois separadores diferentes (ponto e travessão) e sete
  substantivos diferentes para a mesma coisa na tela (*painel, leitura, lista, preparos,
  quadro, página, estado*). Nenhuma delas está errada; juntas, elas ensinam ao operador
  que há onze situações diferentes quando há uma. E a §5.3 da régua já aponta o
  mecanismo certo para este caso: **V6, baseline que só encolhe**.
- **Substituição:** uma frase, com o substantivo trocado por variável e o resto fixo:
  `` `Sem conexão — o que está na tela é de ${quando}.` ``, e onde o `quando` não
  existir, `"Sem conexão — o que está na tela pode estar velho."` O `OfflineBanner` do
  kit fica como está (ele fala da conexão, não do dado, e é global). O Painel da TV é a
  única exceção legítima: `"sem sinal"` é curto porque a palheta é curta — mas então é
  **só** `"sem sinal"`, sem a segunda redação no `title`.

## E4. O contrário de tudo isso: "fornada" não existe no KDS, e está certo

- **Onde:** `kds-nuxt/app/` — zero ocorrências de *fornada*, *lote* ou *batch* em texto
  de tela. O KDS fala de **pedido**, **item**, **estação**, **comanda**; a Produção fala
  de **fornada**, **receita/ficha**, **insumo**, **bancada**.
- **Por que registro:** porque a Parte E podia ter encontrado a fronteira errada e não
  encontrou. Os dois apps **não** compartilham o objeto — o KDS monta pedidos, a
  Produção faz fornadas — e a separação de vocabulário está limpa. O que precisa de
  nome único é só o que os dois **fazem igual**: reconhecer um aviso (E1), tentar de
  novo (E2), dizer que o dado está velho (E3), e a palavra *estação* (P2).
  Não há nada aqui pedindo que a Expedição do KDS e a Expedição da Produção usem o
  mesmo vocabulário — são atos diferentes com o mesmo nome de aba, e isso é tratado em
  **G3**.

---

# Parte F — é só feio (D6, D8)

## F1. Seis frases que começam dizendo o que o sistema não faz

- **Onde:**
  - `ShortageDialog.vue`: `"Registre o motivo real da autorização; a identidade do
    operador e um alerta serão preservados."`
  - `ShortageDialog.vue`: `"Esta operação não está autorizada a ignorar a falta."`
  - `FloorTimersPanel.vue`: `"Lembretes deste dispositivo — fermentação, descanso, o
    que for. Não travam nada."`
  - `useProductionMutationGuard.ts`: `"Sem conexão. A ação não foi enviada e seus dados
    foram preservados."`
  - `useProductionLabelPrinting.ts`: `"Não foi possível atualizar o estado agora. A
    estação pode continuar trabalhando."`
  - `useProductionLabelPrinting.ts`: `"Não recebemos resposta. O trabalho pode ter sido
    criado; verifique o envio antes de tentar de novo."`
- **Defeito:** D6. Assinatura literal: *preservados*, *não travam*, *pode continuar
  trabalhando*, *o trabalho pode ter sido criado*.
- **Por que dói:** é orgulho de engenharia lido pelo padeiro. Ele não sabia que havia o
  risco de perder o que digitou, nem que um timer pudesse travar uma fornada, nem que
  existisse um "trabalho" a ser criado. Agora tem que ler a defesa contra riscos que
  não eram dele. E a frase da falta de insumo é a pior: `"Esta operação não está
  autorizada"` põe a culpa numa *operação*, deixa a pessoa sem saber que é permissão, e
  não diz o que fazer.
- **Substituição:** apagar a oração que defende a decisão de arquitetura; se o que
  sobra não diz o que fazer, era o gesto que faltava.
  - `"Diga quem autorizou e por quê. Fica registrado no seu nome."`
  - `"Você não pode seguir sem os insumos. Peça a liberação a quem administra a loja,
    ou reduza a quantidade."`
  - `"Lembretes deste dispositivo — fermentação, descanso, o que for. Eles só tocam; a
    fornada segue por conta dela."`
  - `"Sem conexão. Nada foi enviado. O que você digitou continua na tela — confirme de
    novo quando voltar."`
  - `"Não deu para atualizar o estado agora. A impressora pode ter continuado."`
  - `"Não tivemos resposta. As etiquetas podem já estar na fila — confira antes de
    mandar de novo."`

## F2. "permanece aberto até resolução"

- **Onde:** `production-nuxt/app/components/AlertsBell.vue`, o selo do alerta já visto:
  `aria-label="Alerta visto; permanece aberto até resolução"`, `title="Visto; aguardando
  resolução"`.
- **Defeito:** D6 com D3 — *resolução* por quem, de quê, quando.
- **Substituição:** `aria-label="Você já viu este alerta. Ele some quando o problema
  for resolvido."` · `title="Visto — some quando resolver"`.

## F3. "mas a cozinha não carregou"

- **Onde:** `operator-kit/app/components/OperatorSessionUnavailable.vue`:
  `` Você continua conectado{{ scope ? `, mas ${scope} não carregou` : '' }}. `` — com
  `scope="a cozinha"` no `kds-nuxt/app/app.vue` e `scope="a produção"` no
  `production-nuxt/app/app.vue`.
- **Defeito:** D3 (o sujeito não combina com o verbo) e D8 (a segunda frase da tela,
  `"Isso costuma ser uma instabilidade de rede ou uma atualização no ar."`, é explicação
  de causa que não muda o que a pessoa faz).
- **Por que dói:** uma cozinha não carrega. A frase soa como erro de montagem, e é
  exatamente o que alguém lê quando já está desconfiando de que o sistema quebrou.
- **Substituição:** o `scope` passa a nomear a tela, não o lugar —
  `scope="o painel da cozinha"` no KDS e `scope="as telas da Produção"` na Produção
  (com o verbo concordando: o template vira
  `` `, mas não conseguimos carregar ${scope}` ``). E a segunda frase encolhe para
  `"Costuma ser a rede."`

---

# Parte G — dúvidas registradas, não propostas de troca

A régua manda registrar a dúvida quando não dá para distinguir defeito de decisão de
produto. Estas quatro não viraram achado.

## G1. "Confirmar" é o verbo de sete atos — e três deles são decisão do dono

`"Confirmar"` aparece como rótulo de ação em: a célula do Planejamento, o diálogo do
Planejamento, a célula da Produção, o diálogo da Produção, o ladrilho da Expedição, o
botão do fechamento de fornada, o sheet do overshoot (`"Confirmar N unidades"`) e o
botão de qualidade (`"Confirmar qualidade"`). Pela régua, isso é D2 puro: o verbo serve
para qualquer coisa, logo não informa nenhuma.

**Mas o cabeçalho de `ProductionStageGrid.vue` registra a decisão em contrário**, com
data: *"Na Produção a ação é UMA só — 'Confirmar' (o mesmo verbo do Planejamento) diz
quanto segue para a Expedição, já preenchido com o planejado (decisão Pablo
2026-09-16)"*. A uniformidade do verbo **é** o desenho, e a informação de qual ato está
em jogo foi deliberadamente deslocada para a coluna e para o título do diálogo.

Por isso só **C8** entrou como achado: o botão de **fechar a fornada**, que é o último
passo de um caminho e o único irreversível, e para o qual a regra de caminho do D1 é
explícita — *só o último passo diz o verbo do ato*. A decisão de 16/09 é sobre
Planejamento e Produção; a Expedição não estava nela. **Se o dono quiser o "Confirmar"
uniforme também no fechamento, C8 cai** e o resto do relatório não muda.

## G2. "Timers" em inglês, no plural do português

`FloorTimersPanel.vue` e `expedite.vue` dizem `"Timers"`, `"Timer do forno"`. É
estrangeirismo em texto de tela (D7a por leitura estrita), mas *timer* é a palavra que
se usa numa cozinha profissional brasileira — o mesmo caso de *maquininha* ser nome
próprio. Não proponho troca; registro para quem fechar o vocabulário do domínio decidir
de uma vez, e pergunto: `"Timer"` ou `"Cronômetro"`?

## G3. "Expedição" nomeia dois atos diferentes, um em cada app

No KDS, **Expedição** é a estação onde o pedido é despachado ou entregue ao cliente
(`view.isExpedition`). Na Produção, **Expedição** é o fechamento de fornada com
classificação de qualidade (`/expedite`, ADR-017 §9). São atos distintos, em momentos
distintos do dia, com o mesmo nome de aba — e, ao contrário de "estação" (P2), os dois são defensáveis no português do ofício.

Não proponho troca porque escolher aqui é decisão de domínio, não de redação, e porque
o risco prático é baixo: as duas telas moram em apps diferentes, com cabeçalhos
diferentes. Registro porque, no dia em que o Hub listar as duas lado a lado, elas vão
aparecer como dois itens com o mesmo nome.

## G4. O painel do cliente tem voz própria (e um emoji)

`kds-nuxt/app/pages/pickup.vue` é a **única tela de cliente** dentro destes dois apps —
público, sem auth, na parede do balcão. Três coisas nela são, pela régua de operador,
defeito; pela concessão de voz da casa ao Storefront, talvez não:

1. `"Seu número aparece aqui assim que o pedido ficar pronto. ✨"` — emoji, proibido
   pela regra de tom.
2. `"Ao vivo"` / `"Atualiza sozinho"` / `"Conectando…"` com a bolinha, e o `title`
   `"O painel atualiza sozinho a cada poucos segundos"` — honestidade de tempo-real
   **mostrada ao cliente**, que não tem o que fazer com a informação (D6 pela régua de
   operador; provavelmente ruído para quem espera um pão).
3. `{{ splitRef(order.ref).prefix || "Pedido" }}` — quando o ref tem hífen, o cliente
   lê o prefixo cru acima do número: **`"BAL-20260918-"`**. Este terceiro eu considero
   defeito em qualquer régua (D7a — código interno na tela, a varredura V4), e a
   substituição é simples: imprimir sempre a palavra `"Pedido"`, e nunca o prefixo.

Os dois primeiros ficam como pergunta ao dono: **o painel de retirada segue a régua de
operador ou a concessão do Storefront?**

---

# Parte H — o que examinei e considerei bom

Metade do valor de uma auditoria é saber onde não mexer.

**KDS**

- **A faixa de estado do card de preparo** (`KdsTicketCard.vue`):
  `"Toque para iniciar"` → `"Em preparo"` → `"Em preparo · toque para finalizar"`. Ela
  diz, na mesma linha, **o que o card é** e **o que o próximo toque faz**, e muda com o
  estado de armação. É o oposto exato do D2: o verbo nomeia o ato, e o ato é o próximo.
  Não mexer.
- **`"Item cancelado · dê Ciente"`** acerta o mecanismo (a recusa aparece **antes** do
  toque, não depois) — só erra a palavra, que B1 troca.
- **O bloqueio de expedição** (`KdsExpeditionCard.vue`): `advance_block_label` +
  `advance_block_reason` aparecem **no lugar** do botão de ação, com o motivo por
  extenso embaixo. É a gêmea na tela da recusa do servidor, e o comentário registra por
  quê: *"recusa seca com o cliente esperando é o pior dos dois mundos"*. Exemplar.
- **`"Mais urgente primeiro — o destacado é o próximo"`** — uma frase que explica a
  ordenação e aponta o card, sem jargão e sem defender a implementação.
- **`"Concluídos recentes"` / `"Reabrir"`** — o verbo nomeia o ato, e o diálogo diz a
  janela: `"Nada concluído nos últimos 30 minutos."`
- **`"Comanda 47"` riscada + `"já liberada após o pagamento"`** — um fato que muda a
  decisão da cozinha, dito em seis palavras.
- **O toast de finalizar com `"Desfazer"` de 5 s**, e o POST que só sai quando a janela
  fecha. A copy acompanha o mecanismo em vez de explicá-lo.

**Produção**

- **O par `"NO FORNO"` implícito no cartão da Expedição**: `"Tempo esgotado"` /
  `"Visto"` / contagem regressiva / `"Iniciar"` — quatro estados, quatro palavras, zero
  ambiguidade (salvo o `"Iniciar"`, que é dúvida registrada, não erro).
- **`"Toca neste dispositivo."`** como descrição do diálogo do timer do forno: quatro
  palavras, a única informação que importa (o alarme não segue a pessoa), e no
  vocabulário certo da casa.
- **Os avisos de margem de rendimento** (`mise-en-place.vue`): `line.margin_display`
  com o `line.margin_reason` no `title`, e a linha em itálico no detalhe explicando por
  que a quebra por receita não fecha com o total. É precisão semântica: um número que
  cresceu ganha o motivo ao lado em vez de virar conta que não bate.
- **`"O planejamento mudou. Confira esta revisão; as marcações da lista anterior foram
  limpas."`** — diz o que mudou, o que fazer e o que se perdeu, em ordem.
- **O bloqueio de gestor** (`reports.vue`): `"Área do gestor"` + `"Os relatórios de
  produção pedem uma permissão de gestão que este operador não tem. Peça a liberação a
  quem administra a loja."` + `"Voltar para a produção"`. Título, motivo, caminho e
  saída. É o modelo para P13.
- **`"N fornadas abertas de dias anteriores. Toque para ver."`** — o aviso inteiro é o
  alvo, o número é o fato e a última frase é o gesto. Sem CTA solto.
- **`"Estes dados estão desatualizados. Atualize antes de confirmar."`** + botão
  `"Atualizar dados"` (`useProductionMutationGuard.ts`) — o irmão certo do rótulo
  errado de C11.
- **`"Diferente do planejado"` aparecer sem pedir justificativa** — a decisão de não
  perguntar é boa; só falta a frase dizer isso (P16).
- **Os rótulos das lentes** — `Sugerido | Planejado` e `Planejado | Produzido` — e a
  regra que os governa: cada tela tem **uma** coluna de leitura e **uma** de ação, e a
  coluna de ação de uma é a de leitura da seguinte. É um vocabulário fechado
  funcionando, no sentido da §4.2 da régua.

**operator-kit, na parte que estes dois apps montam**

- `OperatorNumpad` (`aria-label` `"Dígito 7"`, `` `Limpar ${subject}` ``,
  `"Apagar último dígito"`) e `OfflineBanner` (`"Sem conexão — tentando reconectar…"`)
  estão corretos e curtos. O problema do kit nestes dois apps é um só: o
  `"Tentar novamente"` do `OperatorSessionUnavailable` (E2) e o `scope` que não
  concorda com o verbo (F3).

---

## O que este relatório não faz

- **Não altera nenhuma linha de produto.** A aplicação é PR seguinte, e cabe em pelo
  menos três: (1) os níveis 1 do KDS e da Produção, (2) o vocabulário da Parte E, que
  toca o `operator-kit` e portanto as nove superfícies, (3) o nível 3.
- **Não fecha o vocabulário de nenhum dos dois domínios.** A régua diz que isso mora no
  contrato da superfície, não num relatório. O que está aqui é a matéria-prima: P1
  (fornada), E1 (Visto), E2 (Tentar de novo), E3 (sem conexão) e P2 (estação) são as
  cinco decisões que um contrato de superfície da Produção e do KDS
  precisaria registrar.
- **Não reabre a decisão de 16/09 sobre o "Confirmar"** — ver G1.
- **Não mede as outras superfícies.** A ordem da §6.3 da régua continua: `pos-nuxt` é a
  Onda 1 e não foi lido aqui; `orders-nuxt` é a 3.
