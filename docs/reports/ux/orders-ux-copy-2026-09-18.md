# Varredura de copy — Gestor de Pedidos (18/09/2026)

- **Escopo:** `surfaces/orders-nuxt/app/` — `pages/`, `components/`, `composables/`,
  `presentation/`, `utils/`. Mais o que o app consome de `surfaces/operator-kit/app/`
  **quando a string aparece na tela dele**. Lido no `origin/main` em `e5b338007`.
- **Natureza:** leitura e relatório. **Nenhuma linha de produto foi alterada.** A
  aplicação é PR seguinte.
- **Régua:** [`docs/reference/omotenashi-copy.md`](../../reference/omotenashi-copy.md) —
  a definição (§1), o teste de uma frase (§2) e os oito defeitos (§3). Os nomes D1–D8
  são de lá; não inventei critério.
- **Ordem:** [§6.3](../../reference/omotenashi-copy.md) põe o `orders-nuxt` na **Onda 3**,
  porque aqui o operador decide sobre o pedido de **outra pessoa**. Foi o que guiou o
  ordenamento: os achados da Parte A são todos casos em que a decisão errada chega a um
  cliente.
- **Modelo:** [`marketing-ux-adversarial-2026-09-18.md`](marketing-ux-adversarial-2026-09-18.md).
- **Irmãs em voo:** as varreduras do PDV (ordem 1) e de KDS/Produção (ordem 2) estavam
  sendo escritas noutras frentes enquanto esta era feita, e ainda não estavam no `main`
  no HEAD medido. Quando entrarem, vale cruzar as três: **B5, B6 e B11 deste relatório
  são dívidas compartilhadas** (vocabulário de envio, rótulo do gesto de acerto e o
  rótulo de "tenta de novo"), e consertá-las só aqui repete o padrão que a casa já
  nomeou — o remédio aplicado no site reportado, não no irmão.

## Uma nota de método, porque muda o que conta como achado

Metade da copy desta tela **não mora neste app**. Os rótulos de ação (`"Aceitar"`,
`"Marcar saída para entrega"`, `"Registrar pagamento da entrega"`), os rótulos de estado
(`status_label`, `courier_status_label`) e as razões de bloqueio chegam prontos da
projection (`shopman/backstage/projections/order_queue.py` e
`shopman/shop/services/operator_orders.py`). Julgar só o `.vue` deixaria de fora
justamente o D1, que exige saber o que o handler faz.

Por isso cada achado abaixo diz **onde a string nasce** — e vários dos consertos são no
Python, não no Nuxt. Foi assim que apareceu o padrão mais caro deste app: **o Gestor
descarta rótulos que o servidor já produziu corretamente e escreve outros por cima**
(A7, B6).

## Placar

| Defeito | Achados |
|---|---:|
| D1 — rótulo que mente | 9 |
| D4 — grandezas somadas | 4 |
| D7 — jargão e colisão de vocabulário | 11 |
| D3 — frase que obriga a completar sentido | 5 |
| D2 — verbo genérico apaga o ato | 3 |
| D5 — zero/vazio como código secreto | 2 |
| D6 — nota de rodapé do engenheiro | 5 |
| D8 — prolixo | 3 |
| **Total** | **42** |

Ordenado por dano, na régua da §6.1: **Parte A** faz decidir errado (D1, D4), **Parte B**
faz parar para pensar por vocabulário (D7), **Parte C** faz parar para pensar por frase
incompleta ou decoreba (D2, D3, D5), **Parte D** é só feio (D6, D8). **A Parte E diz o
que examinei e considerei bom** — é metade do resultado.

---

# Parte A — faz decidir errado

## A1. O botão que avisa o cliente que o pedido saiu se chama "Levou o troco"

- **Onde:** `pages/index.vue` e `pages/[ref].vue`, rodapé do diálogo de despacho:
  `{{ dispatchAsksChange ? "Levou o troco" : "Saiu para entrega" }}`, e ao lado
  `"Saiu sem troco"`.
- **Defeito:** D1 — rótulo que mente. Os **dois** botões despacham o pedido; nenhum dos
  dois diz isso quando há troco.
- **Por que dói:** o gesto que os dois botões executam é `advance` → `DISPATCHED`, e
  `shopman/shop/lifecycle.py` dispara `notification.send(order, "order_dispatched")` —
  o cliente recebe *"Pedido X saiu para entrega!"* (`adapters/notification_sms.py`). O
  operador abriu o diálogo clicando **"Marcar saída para entrega"**, leu um título sobre
  troco, e agora escolhe entre duas frases que só falam de dinheiro. Se ele ainda não
  entregou a sacola ao entregador e toca **"Levou o troco"** só para registrar a
  custódia da gaveta, o cliente já foi avisado de que o pedido está a caminho. É o
  caminho mais curto deste app entre um toque e uma promessa quebrada.
- **Substituição:** o verbo do ato volta ao botão, e o troco vira complemento:
  - com troco: `"Saiu para entrega · levou R$ 20,00"` · o secundário:
    `"Saiu para entrega · sem troco"`
  - sem troco: `"Saiu para entrega"` (já está certo)
  - e a descrição do diálogo diz o que acontece depois:
    `"Ao confirmar, o cliente é avisado de que o pedido saiu."`

## A2. O cartão mostra "Entregue" e "Saiu para entrega" ao mesmo tempo

- **Onde:** `components/OrderCard.vue`, a linha
  `· <Icon bike /> {{ card.courier_status_label }}` logo acima do selo
  `{{ card.status_label }}`; e `components/OrderCourierPanel.vue`, o selo
  `{{ courier.status_label }}` e o passo `"Entregue"` de
  `presentation/courier.ts` (`STEPS`).
- **Defeito:** D1 — rótulo que mente, pela via da colisão: `COURIER_STATUS_LABELS["F"]`
  é literalmente `"Entregue"` (`order_queue.py`), e é o estado da **corrida**, não do
  **pedido**.
- **Por que dói:** a corrida do Machine termina quando o entregador finaliza no app dele;
  o pedido só vira `delivered` quando alguém toca **"Marcar como Entregue"** no Gestor. No
  intervalo — que pode durar o turno inteiro — o mesmo cartão diz `Saiu para entrega` no
  selo de status e `🚲 Entregue` na linha de cima. Quem lê o cartão de relance lê a
  palavra mais forte. Num pedido pago na porta (COD) isso é dinheiro: o operador conclui
  que acabou e não faz o acerto, e o `"Acertar entrega"` some do campo de visão dele
  junto com o pedido.
- **Substituição:** a corrida fala da corrida, sempre com o sujeito na frente —
  `COURIER_STATUS_LABELS["F"]` vira `"Entregador finalizou"`; `STEPS` do
  `presentation/courier.ts` vira `Solicitado · Aceito · Coletado · **Finalizado**`. A
  palavra "Entregue" fica reservada ao estado do pedido, que é o que o cliente confirma.

## A3. "Cancelar" num pedido iFood não cancela — pede

- **Onde:** `components/OrderReasonDialog.vue`, `title = "Cancelar pedido"`, botão
  `"Confirmar"`; e `pages/[ref].vue`, o botão `"Cancelar"` / `"Cancelar (gerente)"`.
- **Defeito:** D1 — rótulo que mente.
- **Por que dói:** `shopman/shop/services/ifood_cancellation.py` é explícito no título do
  módulo: *"only iFood CAN closes a live order"*. O que o toque faz é gravar
  `ifood_cancellation_request` com `state: "queued"` e criar uma Directive. O pedido
  **continua vivo**, continua na coluna, e o iFood pode recusar (`record_result` grava
  `"O iFood não aceitou a solicitação."`). A casa já sabe disso em três lugares — o
  `cancel_block_label` diz `"Aguardando confirmação de cancelamento do iFood."`, o
  `AdvanceBlock.IFOOD_CANCELLATION_PENDING` existe, e o botão irmão do painel de corrida
  diz honestamente **"Solicitar cancelamento"**. Só o gesto que cancela o pedido de um
  cliente não avisa que é um pedido.
- **Substituição:** o app já tem `marketplace` como prop no diálogo; falta usá-la no
  título e no botão.
  - título, canal iFood: `"Solicitar cancelamento ao iFood"`
  - botão, canal iFood: `"Enviar solicitação"`
  - descrição: `"O iFood decide. Enquanto ele não responder, o pedido continua no quadro
    e não avança."`
  - nos outros canais tudo fica como está (`"Cancelar pedido"` / `"Confirmar"` são
    verdade ali).

## A4. "Informe o motivo — o cliente é avisado."

- **Onde:** `components/OrderReasonDialog.vue` e `pages/index.vue` (o diálogo de recusa do
  board repete a frase), na descrição do modo `reject`.
- **Defeito:** D1 — o presente do indicativo afirma um fato que o app não controla.
- **Por que dói:** `reject_order` chama `notification.send(order, "order_rejected", …)`,
  que é **assíncrono** e cria uma Directive (`shop/services/notification.py`, docstring:
  *"ASYNC — does not block the request"*). A entrega pode ser pulada — os mesmos motivos
  que o `payment_link_notice` já lista no Python: `customer_opt_out`,
  `expected_no_contact`. O operador recusa o pedido de alguém, lê "o cliente é avisado",
  e não liga. Numa recusa, esse telefonema é a única coisa que sobra da relação.
- **Substituição:** `"Informe o motivo. Ele vai para o aviso de recusa que o cliente
  recebe."` — e, quando o pedido não tem contato utilizável, a mesma linha do diálogo
  passa a dizer `"Este pedido não tem contato para aviso. Combine a recusa por fora."`
  (o dado existe: `customer_phone_uri` / `customer_whatsapp_url` / `customer_email` já
  chegam na projection do detalhe e alimentam o bloco de contato).

## A5. O relógio que cancela o pedido sozinho aparece como "4:32", sem uma palavra

- **Onde:** `components/OrderCard.vue`, o chip
  `<Icon hourglass /> {{ confirmationLeft }}`, cujo único texto é o próprio número; o
  que diz o que ele faz está no `title`:
  `"Cancela automaticamente ao vencer"` / `"Confirma automaticamente ao vencer"`.
- **Defeito:** D1 + D3 — o único sinal do desfecho está num tooltip, e no cartão há dois
  chips de número lado a lado.
- **Por que dói:** o cartão mostra `🕐 12m` (tempo decorrido) e `⏳ 4:32` (contagem
  regressiva) grudados, com gramática visual quase igual. Os dois desfechos possíveis
  são **opostos** — um confirma o pedido, o outro cancela — e a diferença não está
  escrita em lugar nenhum visível. O Gestor roda em tablet de balcão: `title` não existe
  ali. O operador vê um número descendo e não sabe se precisa correr.
- **Substituição:** a palavra entra no chip, e o `title` deixa de ser o único portador:
  - `confirmation_action === "cancel"` → `"cancela em 4:32"`
  - senão → `"confirma em 4:32"`
  - o ícone acompanha (`lucide:x-circle` para cancelar, `lucide:check-circle` para
    confirmar) para os dois não se parecerem.

## A6. O som que toca por quatro motivos diferentes se chama "som de pedido novo"

- **Onde:** `pages/index.vue`, o botão de som —
  `aria-label` `"Som de pedido novo ativo"` / `"Som de pedido novo desativado"` /
  `"Som bloqueado — toque para ativar"`, `title` `"Som de pedido novo"`; e o botão
  vizinho, `aria-label="Reconhecer aviso de pedido novo"`, rótulo visível `"Ciente"`.
- **Defeito:** D1 — o controle nomeia um gatilho que ele não tem.
- **Por que dói:** quem decide tocar é `treatableOrderRefs` (`presentation/board.ts`), e
  o predicado é `can_confirm || can_advance || can_settle_delivery_cash ||
  equipment_back_pending`. O sino toca para **pedido novo**, **pedido pronto para
  avançar**, **acerto de dinheiro pendente** e **maquininha que voltou** — três deles em
  pedidos velhos. O operador que desliga o som porque "hoje não entra pedido novo" desliga
  também o aviso de que há dinheiro para acertar. E o próprio app já tem o nome certo, a
  dois arquivos de distância: a notificação do `utils/treatableNotification.ts` se chama
  **"Pedido para tratar"**, e o título piscante também.
- **Substituição:** um nome só, o que já existe:
  - `title`: `"Som de pedido para tratar"`
  - `aria-label`: `"Som de pedido para tratar ativo"` / `"…desativado"`
  - `"Reconhecer aviso de pedido para tratar"`
  - e o rótulo visível `"Ciente"` ganha o que se está dando por ciente:
    `"Vi os pedidos"`.

## A7. No quadro, o botão morto continua dizendo o verbo — e o rótulo certo existe e é jogado fora

- **Onde:** `presentation/board.ts`, `cardAffordances()`: quando `a.enabled` é falso, o
  código troca o ícone e a prioridade mas **mantém `label: a.label`**, pondo o motivo só
  em `reason` → `title` do botão. E `types/orders.ts` recebe `advance_block_label`, que
  **nenhum arquivo do app consome** (medido: zero ocorrências em `app/`).
- **Defeito:** D1 — o rótulo promete um ato que o servidor já recusou.
- **Por que dói:** um pedido com pagamento não capturado mostra um botão escrito
  **"Marcar pronto"**, apagado, sem razão visível em tablet. O operador toca, não
  acontece nada, e conclui que a tela travou. O servidor produziu de propósito o rótulo
  curto para esse lugar — `_ADVANCE_BLOCK_LABELS` tem `"Aguardando pagamento…"`,
  `"Esperando a fornada…"`, `"Aguardando entregador iFood…"` — com uma docstring
  explicando que existe exatamente para o botão desabilitado. O Gestor não lê o campo.
  A regra da casa sobre botão morto já foi aprendida no Marketing (a razão vai **por
  extenso, abaixo da linha**, porque tooltip em botão desabilitado não aparece); aqui ela
  não chegou.
- **Substituição:** no `cardAffordances`, o botão desabilitado passa a usar
  `card.advance_block_label` como rótulo quando ele existe, e o `reason` inteiro sai
  **como texto abaixo do botão**, não como `title`:
  ```
  [ ⏳ Aguardando pagamento… ]
  Pagamento ainda não foi confirmado. O pedido só avança depois que o dinheiro entra.
  ```
  Nos casos sem `advance_block_label` (bloqueio definitivo), o botão não aparece — é o que
  a própria docstring do Python manda.

## A8. "Encomenda do dia…" no pedido que **não** é do dia

- **Onde:** `shopman/backstage/projections/order_queue.py`, `_ADVANCE_BLOCK_LABELS[PREORDER_NOT_DUE] = "Encomenda do dia…"`.
- **Defeito:** D1 — o rótulo afirma o contrário do que bloqueia.
- **Por que dói:** o bloqueio é `PREORDER_NOT_DUE`: *encomenda para data futura, o preparo
  abre no dia combinado*. O rótulo curto diz "Encomenda do dia", que é a leitura oposta —
  e é a que faz o operador pôr na fila de hoje um pedido de sábado. Ele hoje só aparece
  no Admin (A7 explica por que o Gestor nem o lê), mas o conserto pertence a este PR,
  porque é o mesmo campo que A7 manda passar a usar.
- **Substituição:** `"Encomenda de outro dia…"`, com o motivo por extenso já pronto
  (`"Encomenda para uma data futura. O preparo abre no dia combinado."`).

## A9. "Em trânsito: 1" enquanto três maquininhas estão na rua

- **Onde:** `pages/index.vue`, a linha `data-equipment-available`:
  `"Maquininhas disponíveis: {{ n }} … · Em trânsito: {{ equipmentOut.filter(item => item.identified).length }}"`,
  seguida de `"Registros antigos sem maquininha identificada: {{ … !item.identified … }}"`.
- **Defeito:** D4 — um número que conta parte de uma grandeza e se apresenta como o
  total dela.
- **Por que dói:** `equipmentOut` é a lista do que saiu e não voltou. A tela quebra essa
  lista por um atributo de **qualidade do dado** (`identified`) e chama só metade de "Em
  trânsito". A pergunta que o operador faz a essa linha é uma só — *quantas maquininhas
  estão fora?* — e a resposta é `equipmentOut.length`. Quem lê "Em trânsito: 1" e
  precisa despachar uma entrega conclui que há folga; o bloqueio `DEVICE_UNAVAILABLE` vai
  discordar dele depois, no meio do despacho.
- **Substituição:** um número por grandeza, e a dívida de dado como ressalva, não como
  segunda contagem:
  - `"Maquininhas: 2 na loja · 4 na rua"`
  - e, quando houver não identificadas: `"(3 das que estão na rua são registros antigos,
    sem saber qual maquininha é)"`.

## A10. "12 selecionados" e "Revise 37 células antes de confirmar"

- **Onde:** `pages/catalog.vue`, a barra flutuante
  (`{{ selected.size }} selecionado{{ … }}`) e, dentro do popover de preço,
  `"Revise {{ pricePreview.cells.length }} células antes de confirmar"`; o mesmo par
  aparece na prévia de publicação: `"Confira {{ publicationDraft.preview.cells.length }}
  células em {{ surfaceLabel(…) }}"`.
- **Defeito:** D4 — produto × canal × faixa de preço, três grandezas, dois números sem
  unidade que não fecham entre si.
- **Por que dói:** é o caso que a §3 do documento-régua já previa para este app ("peça ×
  quilo × fornada na Produção; pedido × item × pessoa no Gestor"). O operador selecionou
  12 **produtos**, escolheu "Todos os canais", e a confirmação fala em 37 — que são
  linhas de `sku × surface × tier`. Ele não tem como saber se 37 é muito ou pouco, nem se
  o número inclui um canal que ele não queria tocar. É a última tela antes de uma
  repreficação **permanente**.
- **Substituição:** a frase declara as três grandezas, na ordem em que ele pensa:
  - `"12 produtos · 4 canais · 37 preços vão mudar"`
  - e a lista abaixo mantém `SKU · canal · mínimo N` como já está (ela está certa).
  - o mesmo para a publicação: `"12 produtos em 1 canal — 37 ofertas mudam de estado"`.

## A11. "Permanente — para promo, use as regras."

- **Onde:** `pages/catalog.vue`, sob o campo de reprecificação em lote.
- **Defeito:** D1, na segunda forma — a instrução nomeia um controle que a tela não tem.
- **Por que dói:** "as regras" não é nada que exista no Gestor. `RuleConfig` mora no
  Admin, noutro host (`adminBaseUrl`). O operador acabou de ser avisado de que a mudança
  é permanente, foi mandado usar outra coisa, e essa outra coisa não tem nome nem
  endereço. O resultado previsível é ele aplicar a permanente mesmo assim.
- **Substituição:** `"Este preço vale até alguém trocar de novo. Desconto por tempo se
  faz em Promoções, no Admin."` — com o mesmo link externo que a página de Canais já usa
  para o Admin (`adminBase`), para a frase ter para onde levar.

## A12. "Verifique esta intenção antes de uma nova ação."

- **Onde:** `composables/useOrderIntention.ts`, a mensagem de `finish()` quando o
  resultado não volta `applied`.
- **Defeito:** D1 (controle inexistente) + D7a (`intenção` é termo interno; a régua o
  lista nominalmente).
- **Por que dói:** esta é a frase que aparece quando uma gravação de pedido ficou sem
  recibo — o estado mais delicado do app, porque ninguém sabe se o pedido mudou. Ela
  manda o operador fazer uma coisa que, no quadro de pedidos, não existe: o botão
  `checkPath` só tem superfície no Catálogo (`"Verificar esta gravação"`) e na negociação
  iFood (`"Verificar mesmo envio"`). No board e no detalhe, não há nenhum. O operador
  lê uma ordem, não encontra o controle, e faz a única coisa que sobra: tenta de novo.
- **Substituição:** enquanto o gesto não existir nas telas de pedido, a frase diz o que
  de fato há a fazer: `"Não sabemos se esta gravação foi aplicada. Atualize o pedido e
  confira o histórico antes de repetir a ação."` — e o conserto estrutural (um
  "Conferir" ao lado do aviso, ligado a `checkPath`) é WP próprio.

---

# Parte B — jargão e colisão de vocabulário

## B1. "Recusar" quer dizer duas coisas opostas no mesmo pedido

- **Onde:** `pages/[ref].vue`, botão `"Recusar"` (`data-action="reject"`) na barra de
  ações; e `components/OrderIFoodNegotiations.vue`, opção `"Recusar solicitação"` no
  seletor de decisão, dentro da mesma página.
- **Defeito:** D7b — a mesma palavra com dois sentidos no mesmo app, e os sentidos são
  **contrários**.
- **Por que dói:** `"Recusar"` na barra de ações **cancela o pedido** (`reject_order` →
  `cancel`). `"Recusar solicitação"` na negociação **mantém o pedido de pé**, recusando o
  cancelamento que o cliente pediu. As duas podem estar na mesma tela: um pedido iFood
  `new` com uma negociação de cancelamento aberta tem as duas. O operador que aprendeu
  "Recusar = matar o pedido" na barra lê a mesma palavra no seletor e conclui o mesmo.
- **Substituição:** a negociação já qualifica; quem não qualifica é a barra de ações.
  - barra: `"Recusar"` → **`"Recusar o pedido"`** (é a resposta ao pedido que acabou de
    chegar; o comentário no código já diz isso e o rótulo não).
  - negociação: `"Recusar solicitação"` → **`"Manter o pedido"`**, com o subtítulo
    existente explicando que a decisão vai ao iFood. Esta é a que fecha o buraco: ela diz
    o **resultado**, não o gesto, e resultado não colide.

## B2. Dois sinos idênticos, lado a lado: "Alertas" e "Avisos"

- **Onde:** `pages/index.vue`, `<AlertsBell />` seguido de `<NotificationBell />`. Ambos
  usam `lucide:bell`, ambos têm selo numérico. `components/AlertsBell.vue`:
  `aria-label="Alertas (N)"`, `title="Alertas"`, painel `<h2>Alertas</h2>`.
  `operator-kit/app/components/NotificationBell.vue`: `aria-label="Avisos (N não lidos)"`.
- **Defeito:** D7c — dois conceitos diferentes com dois nomes que não os diferenciam.
- **Por que dói:** "alerta" e "aviso" são sinônimos em português de balcão. O operador vê
  dois sinos com dois números e não tem como saber qual olhar; e um deles (Alertas) é
  operacional e urgente — pedido preso, estoque — enquanto o outro é a caixa de entrada
  pessoal dele. Quando dois controles vizinhos não se distinguem pelo nome, o mais barato
  é ignorar os dois.
- **Substituição:** nomear pelo **dono**, não pela natureza:
  - o do app: `"Alertas da loja"` (ícone `lucide:triangle-alert`, que já é o vocabulário
    de severidade que o próprio painel usa)
  - o do kit: `"Minhas mensagens"` (mantém o sino — é a caixa pessoal, e o painel dele já
    tem "Meus acessos")
  - a decisão de qual palavra fica para quem é do contrato da superfície; o que não pode
    é continuar empatado.

## B3. "aguardando a central" — a central é outra coisa nesta casa

- **Onde:** `composables/useOrderDetail.ts`, toast
  `"Solicitação de cancelamento enfileirada; aguardando a central."`
- **Defeito:** D7b — colisão com um nome próprio do sistema.
- **Por que dói:** **Central** é o nome da Central de Apps, o hub, e ela está desenhada
  na tela: o rail do kit tem o item `"Central"` e o `aria-label`
  `"Voltar à Central de Apps"`, a três centímetros deste toast. "Aguardando a central"
  faz o operador olhar para o hub. O que a frase quer dizer é "aguardando a central de
  despacho do entregador", que nesta casa não se chama central — se chama Machine
  internamente e **entregador** na tela.
- **Substituição:** `"Cancelamento da corrida pedido. O entregador ainda pode chegar até
  a resposta vir."` — e, de quebra, some o `"enfileirada"`, que é fila de Directive, não
  de padaria (ver B8).

## B4. "célula" na tela do padeiro

- **Onde:** `pages/catalog.vue`: `"Confira N células em {canal}"`, `"Revise N células
  antes de confirmar"`, `publicationState()` → `"Habilitado nesta célula"` /
  `"Pausado nesta célula"`; e os `aria-label` de cada célula da matriz.
- **Defeito:** D7a — termo de implementação (é o nome da estrutura de dados,
  `SurfaceCellProjection`) vazado para a tela.
- **Por que dói:** "célula" só quer dizer alguma coisa para quem está vendo a matriz como
  tabela. O operador está vendo **um produto num canal**. "Pausado nesta célula" é a
  frase que aparece na prévia de uma ação em lote — o momento em que ele mais precisa
  entender o que vai mudar.
- **Substituição:** o objeto tem nome de negócio: é a **oferta** do produto naquele canal.
  - `"Habilitado nesta célula"` → `"À venda no {canal}"`
  - `"Pausado nesta célula"` → `"Pausado no {canal}"`
  - `"Revise 37 células antes de confirmar"` → ver A10.

## B5. Cinco estados de envio, quatro vocabulários

- **Onde:** quatro arquivos, o mesmo conjunto de estados:

  | estado | `presentation/catalog.ts` `syncBadge` | `presentation/catalog.ts` `cellSyncView` | `presentation/catalogFilters.ts` | `pages/feeds.vue` |
  |---|---|---|---|---|
  | synced | `"Em dia"` | `"Sincronizado"` | `"Sincronizado"` | `"sincronizados"` |
  | pending | — | `"Sincronizando"` | `"Sincronizando"` | `"pendentes"` |
  | error | `"Erro"` | `"Erro de sync"` | `"Com erro"` | `"com erro"` |
  | never | `"Nunca"` | `"Nunca sincronizado"` | `"Nunca enviado"` | — |
  | retracted | — | `"Retirado"` | — | `"retirados"` |
  | skipped | — | `"Ignorado"` | — | `"não enviados"` |

- **Defeito:** D7c — N rótulos para o mesmo conceito, conforme a porta de entrada.
- **Por que dói:** o par mais perigoso está na última coluna: `"não enviados"` (o estado
  **skipped**, que o sistema decidiu pular) e `"Nunca enviado"` (o estado **never**, que
  nunca teve uma tentativa) são estados diferentes com rótulos praticamente iguais, em
  duas telas que o operador usa em sequência — ele filtra por "Nunca enviado" no Catálogo
  e vai conferir o número "não enviados" em Canais, e os dois não batem. Ele vai concluir
  que um dos dois está errado.
- **Substituição:** um vocabulário, escrito no contrato da superfície e reusado nos
  quatro pontos. Proposta, em português de operador e sem `sync`:

  | estado | rótulo único |
  |---|---|
  | synced | `"Enviado"` |
  | pending | `"Enviando"` |
  | error | `"Falhou"` |
  | never | `"Nunca enviado"` |
  | retracted | `"Retirado do canal"` |
  | skipped | `"Não se aplica"` |

  O rótulo curto do cabeçalho de coluna (`"Em dia"`/`"Erro"`/`"Nunca"`) deixa de existir:
  a coluna é estreita, mas três palavras diferentes para economizar seis caracteres é o
  negócio errado.

## B6. O mesmo gesto de acerto tem quatro nomes, e o do servidor é descartado

- **Onde:** quatro camadas, um gesto (`settle-delivery-cash`):
  - projection (`order_queue.py`): `"Registrar pagamento da entrega"` / `"Registrar
    pagamento na retirada"`
  - `presentation/board.ts`, `cardAffordances()`: **sobrescreve** com `"Acertar entrega"`
    / `"Receber na retirada"`
  - diálogo (`index.vue` e `[ref].vue`): título `"Acerto da entrega"` / `"Pagamento na
    retirada"`
  - botão de confirmação: `"Confirmar acerto"` (board) e `"Confirmar"` (detalhe)
- **Defeito:** D7c.
- **Por que dói:** o operador aprende "Acertar entrega" no cartão, abre um diálogo
  chamado "Acerto da entrega" e confirma com um botão que, dependendo de onde clicou,
  diz duas coisas. E o mesmo gesto, visto no Admin, chama-se "Registrar pagamento da
  entrega". Nenhum dos quatro está errado sozinho; juntos ensinam que são coisas
  diferentes. O `cardAffordances` **joga fora** o `label` que a projection mandou —
  fonte única virou fonte ignorada.
- **Substituição:** o nome do servidor vence, porque é o que diz o ato (registrar um
  pagamento) e é o que o Admin já usa:
  - cartão e detalhe param de sobrescrever e usam `action.label`
  - título do diálogo: o mesmo `"Registrar pagamento da entrega"` / `"…na retirada"`
  - botão: `"Registrar pagamento"` nos dois lugares
  - o mesmo vale para `equipment_back`, que o board sobrescreve para `"Maquininha
    voltou"` enquanto a projection manda `"Registrar devolução da maquininha"`. Aqui eu
    inverteria: **`"Maquininha voltou"` é o melhor dos dois** (é o que o operador diz), e
    o conserto é mudar o Python, não continuar sobrescrevendo.

## B7. "Canais" é a aba que não lista os canais do quadro

- **Onde:** `components/GestorTopBar.vue`, aba `"Canais"` → `/feeds`;
  `pages/feeds.vue`, `useHead({ title: "Canais" })`, `<h1>Canais</h1>`, e dentro dela as
  seções `"Feeds e telas"` e `"Canais de venda"`; e `pages/index.vue`, os chips de filtro
  por `"Canal"` (Loja online · WhatsApp · iFood · PDV).
- **Defeito:** D7b/D7c — a palavra "canal" nomeia dois recortes diferentes, e a aba
  promete o que a página não tem.
- **Por que dói:** o operador filtra o quadro por **WhatsApp**, quer mexer em alguma coisa
  do WhatsApp, clica em **Canais** e encontra telas de TV e um cartão de iFood. A página
  também não se decide: a aba diz "Canais", o `h1` diz "Canais", a primeira seção diz
  "Feeds e telas" e o botão diz "Ver feed". Três nomes para o conteúdo de uma tela só.
- **Substituição:** nomear a página pelo que ela faz — **publicar catálogo para fora**:
  - aba e `h1`: `"Publicação"` (ou `"Vitrines"`, se o dono preferir; a decisão é do
    contrato)
  - seções: `"Telas e feeds"` e `"Canais de venda"` ficam como estão — sob um título que
    não promete ser a lista dos canais do quadro
  - o filtro do quadro continua `"Canal"`, que ali é a **origem do pedido** e está certo.

## B8. Códigos internos e voz de engenheiro nos rótulos

- **Onde e substituição**, um a um:

  | Onde | String | Substituição |
  |---|---|---|
  | `useOrderDetail.ts` | `"Solicitação de entregador enfileirada."` | `"Entregador solicitado. A resposta aparece aqui."` |
  | `useOrderDetail.ts` | `"Solicitação de cancelamento enfileirada; aguardando a central."` | ver B3 |
  | `useOrderIntention.ts` | `"…esta intenção…"` | ver A12 |
  | `presentation/catalog.ts` | `"Erro de sync"` | `"Falhou"` (B5) |
  | `catalog.vue` | `` `Erro de sync em ${n} plataforma(s) — reenviar tudo` `` | `"O envio falhou em N canais. Reenviar todos."` |
  | kit `ReadFreshness.vue` | `"Última leitura útil: 14:32:05 · há 3 s"` | `"Atualizado às 14:32"` — e, quando `failed`, `"Atualizado às 14:32. A última tentativa falhou."` |
  | `OrderIFoodNegotiations.vue` | `"Confirmo esta consequência."` | `"Entendi o que vai acontecer."` (a régua já matou "consequência" no Marketing) |
  | `useCatalogMatrix.ts` | `"Resultado ainda desconhecido. O arraste foi mantido; consulte novamente."` | `"Não sabemos se a nova ordem foi gravada. Sua ordem continua na tela; confira antes de arrastar de novo."` |

- **Defeito:** D7a.
- **Por que dói:** `enfileirada`, `intenção`, `sync`, `leitura útil`, `consequência` são
  as palavras com que o sistema pensa. O padeiro não tem fila de Directive nem cache de
  leitura; ele tem um pedido, um entregador e um relógio.

## B9. "Disponível", "Disponível para venda" e "Disponibilidade" são três coisas

- **Onde:** `presentation/catalog.ts`, `CELL_LABELS.available = "Disponível"`;
  `CatalogProductPanel.vue`, `is_sellable: "Disponível para venda"` e o campo
  `availability_policy: "Disponibilidade"`; `catalogFilters.ts`, `"À venda"`;
  `catalog.vue`, botões `"Pausar"` / `"Ativar"`; `presentation/catalog.ts`,
  `rowStatus` → `"Pausado"` e `"Indisponível"`.
- **Defeito:** D7c — **seis** nomes para dois interruptores (`is_published`,
  `is_sellable`) mais um terceiro conceito (`availability_policy`) que empresta a mesma
  raiz.
- **Por que dói:** "Pausado" aparece na linha do produto (`is_sellable` do produto) **e**
  na célula (`is_sellable` da oferta). São dois interruptores diferentes, com o mesmo
  rótulo, na mesma tela, a poucos pixels um do outro. O operador pausa o errado e o
  produto continua vendendo — ou some de todos os canais quando ele queria tirar de um.
- **Substituição:** o escopo entra no rótulo, sempre:
  - linha: `"Pausado em todo lugar"` · célula: `"Pausado no {canal}"`
  - linha: `"Oculto do cardápio"` · célula: `"Fora deste canal"` (hoje `"Não ofertado"`)
  - filtros: `"Exibido"` → `"No cardápio"`, `"À venda"` → `"Vendendo"`
  - o campo `availability_policy` para de se chamar "Disponibilidade" — ver B10.

## B10. "Aceita planejado" / "Aceita demanda"

- **Onde:** `components/CatalogProductPanel.vue`, as opções de `availability_policy`:
  `{ stock_only: "Somente estoque", planned_ok: "Aceita planejado", demand_ok: "Aceita
  demanda" }`.
- **Defeito:** D7a — os rótulos são a transliteração dos valores do enum. "Aceita
  demanda" não é português; é `demand_ok` com as palavras trocadas.
- **Por que dói:** esta é a chave que decide se a loja vende o que ainda não existe. A
  memória da casa já registra que `demand_ok` **é política de disponibilidade, não
  natureza do produto** — e a tela não ajuda ninguém a entender qual política está
  escolhendo. Escolher errado aqui é prometer ao cliente pão que não vai ter.
- **Substituição:** cada opção diz a promessa que a loja está fazendo:
  - `stock_only` → `"Só vende o que já está pronto"`
  - `planned_ok` → `"Vende o que está planejado para a fornada"`
  - `demand_ok` → `"Vende sob encomenda, mesmo sem fornada planejada"`
  - e o rótulo do campo deixa de ser `"Disponibilidade"` (B9): vira `"O que pode ser
    vendido"`.

## B11. Seis maneiras de pedir a mesma coisa ao servidor

- **Onde e medição** (no HEAD deste worktree, só o que a tela do Gestor mostra):

  | Rótulo | Ocorrências | Arquivos |
  |---|---:|---|
  | `"Tentar de novo"` / `"Tente de novo."` | 6 | `catalog.vue`, `useCatalogMatrix.ts` (×4), `useOrdersBoard.ts` |
  | `"Tentar novamente"` | 3 | `feeds.vue`, `channels/[ref]/catalog.vue`, kit `OperatorSessionUnavailable.vue` |
  | `"Consultar novamente"` | 2 | `OrderReasonDialog.vue`, `index.vue` |
  | `"consulte novamente"` | 1 | `useCatalogMatrix.ts` |
  | `"Verificar esta gravação"` | 1 | `catalog.vue` |
  | `"Verificar mesmo envio"` | 1 | `OrderIFoodNegotiations.vue` |

- **Defeito:** D7c.
- **Por que dói:** não é uma escolha a fazer, é uma varredura a terminar — a régua já
  mediu que a casa convergiu em **"Tentar de novo"** (16 ocorrências contra 4). As três
  de `"Tentar novamente"` são as que a régua contou para este app **mais** a do kit, que
  aparece na tela do Gestor todo redeploy do alpha. As duas últimas linhas da tabela são
  outro gesto (conferir um recibo, não repetir a chamada) e por isso ficam — mas com um
  nome só.
- **Substituição:**
  - repetir a leitura: **`"Tentar de novo"`**, nos três pontos de `"Tentar novamente"` e
    nos dois de `"Consultar novamente"` que são retentativa de fetch
  - conferir se uma gravação pegou: **`"Conferir o resultado"`**, em
    `"Verificar esta gravação"` e `"Verificar mesmo envio"`
  - ⚠️ a do kit (`OperatorSessionUnavailable.vue`) é compartilhada com os outros oito
    apps: trocar ali muda todo mundo, e é o que se quer.

## B12. "aparelho" — medido, e **não** é violação

- **Onde:** quatro ocorrências em `orders-nuxt/app/`: `OrderCard.vue`
  (`<!-- aparelho que saiu com o entregador (maquininha) -->`), `index.vue` (idem),
  `presentation/board.ts` (docstring de `dispatchAsks`), `[ref].vue` (comentário de
  `dispatchAsks`).
- **Veredito:** **todas as quatro são prosa** — comentário e docstring. **Zero strings de
  tela.** A regra da casa vale para o que chega a alguém, e nada aqui chega. Não há
  conserto a fazer neste app.
- **Duas observações que valem o registro:**
  1. Em todos os quatro pontos o objeto é a **maquininha**, e os próprios comentários
     dizem isso entre parênteses ("aparelho … (maquininha)"). A palavra da casa para esse
     objeto é nome próprio; se algum dia esses comentários virarem string, a substituição
     já está escrita ao lado deles.
  2. O que **é** texto de tela e carrega a palavra proibida está no kit, não aqui:
     `operator-kit/app/composables/useWebPush.ts`, `navigator.platform || "Aparelho"` —
     o rótulo que vira o nome do dispositivo na lista de assinaturas. Já está nomeado na
     §5.2 do documento-régua e não é deste PR, mas o Gestor renderiza o
     `NotificationBell` do kit, então a string pode aparecer na tela dele.

---

# Parte C — faz parar para pensar

## C1. "Zere os dois para mostrar tudo numa tela só, sem rotação."

- **Onde:** `pages/feeds.vue`, sob os campos "Trocar a cada (s)" e "Itens por tela".
- **Defeito:** D5 — zero como código secreto, na forma em prosa.
- **Por que dói:** é exatamente o padrão que a régua descreve: **dois campos numéricos que
  são um interruptor disfarçado**. A frase ensina uma decoreba ("zero quer dizer
  desligado") e ainda pede que ela seja aplicada a dois campos ao mesmo tempo. O
  operador que zera só um fica num estado que a tela não descreve.
- **Substituição:** o interruptor aparece, e os números só existem ligados:
  ```
  [x] Trocar de página automaticamente
      Trocar a cada [20] s · [6] itens por tela
  ```
  Desligado, a dica some e o `title` do botão passa a dizer `"Mostra tudo numa tela só"` —
  que é o que já está escrito hoje, no lugar certo.

## C2. "Você continua conectado, mas os pedidos não carregou"

- **Onde:** `pages/index.vue` passa `scope="os pedidos"` para
  `operator-kit/app/components/OperatorSessionUnavailable.vue`, cujo template é
  `` `Você continua conectado{{ scope ? `, mas ${scope} não carregou` : '' }}` ``.
- **Defeito:** D3 — a frase foi escrita para um `scope` singular e quebra no plural.
- **Por que dói:** o kit nasceu no Marketing, que passa `"o painel de Marketing"` —
  singular, concorda. O Gestor passa `"os pedidos"` e a tela mostra uma frase agramatical
  na abertura de turno e a cada redeploy do alpha (é o cenário que a própria docstring do
  componente descreve como frequente). É o padrão que a casa já nomeou: **o remédio foi
  aplicado no site reportado, não no irmão.** Uma frase quebrada nesse momento é a tela
  dizendo "eu não sei o que estou falando" no exato instante em que ela precisa ser
  acreditada.
- **Substituição:** o verbo sai da interpolação e vai para a `prop`, que passa a ser a
  frase inteira:
  - kit: `` `Você continua identificado. {{ scope }}` `` com
    `scope` documentado como oração completa
  - Gestor: `scope="Os pedidos não carregaram."`
  - Marketing: `scope="O painel de Marketing não carregou."`
  - **de quebra:** `"Você continua conectado"` afirma o que o app acabou de dizer que não
    conseguiu conferir. O honesto é `"Você continua identificado — quem não respondeu foi
    o servidor."`, que é exatamente o que `sessionUnavailable` distingue.

## C3. "Ação confirmada."

- **Onde:** seis ocorrências da mesma família: `useOrdersBoard.ts` (×2),
  `useOrderDetail.ts` (×2), `useCatalogMatrix.ts` (×2, como `"Alteração confirmada."`),
  `useFeedBoard.ts` (×2) — todas na forma
  `"Ação confirmada. A leitura atualizada falhou; atualize antes da próxima ação."`
- **Defeito:** D2 — verbo genérico apaga o ato.
- **Por que dói:** esta frase aparece no melhor momento possível para informar e no pior
  para ser vaga: a gravação **funcionou** e a releitura falhou, então a tela está
  mostrando o estado velho. O operador acabou de recusar um pedido, ou de marcar saída
  para entrega, e recebe "Ação confirmada" — sem saber qual, sobre qual pedido, e olhando
  para um cartão que ainda diz o contrário.
- **Substituição:** o ato tem nome, e o app o tem à mão (`action.label` / `a.label`):
  - `` `"${label}" foi aplicado ao pedido ${code}. O quadro ainda mostra o estado
    anterior — atualize."` `` → *"'Marcar saída para entrega' foi aplicado ao pedido 0421.
    O quadro ainda mostra o estado anterior — atualize."*
  - no Catálogo, o mesmo com o produto: `"O preço foi gravado. A lista ainda mostra o
    valor anterior — atualize."`

## C4. "3 pedido(s) não puderam ser atualizados."

- **Onde:** `composables/useOrdersBoard.ts`, `actMany()`:
  `` useSonner.error(`${failures} pedido(s) não puderam ser atualizados.`) ``
- **Defeito:** D2 (o verbo não diz o ato) + D3 (o `(s)` obriga o leitor a montar a frase).
- **Por que dói:** o lote só tem dois gestos, e os dois têm nome na tela: **"Aceitar N"** e
  **"Avançar N"**. Depois de tocar "Aceitar 8", ler "3 pedido(s) não puderam ser
  atualizados" não diz quais, nem que os outros 5 foram aceitos. O operador precisa varrer
  o quadro procurando as tarjas vermelhas — que existem, por pedido, e funcionam bem: o
  toast é que não aponta para elas.
- **Substituição:** o verbo do lote e o destino:
  - `"5 aceitos. 3 não deram — o motivo está em cada cartão."`
  - `"6 avançados. 1 não deu — o motivo está no cartão."`
  - (e o singular/plural se resolve com duas frases, não com parênteses).

## C5. "Pedido para tratar" / "Há um pedido que já pode ser tratado no quadro."

- **Onde:** `utils/treatableNotification.ts`, título e corpo da notificação local; e
  `useOrdersBoard.ts`, `startTitleAlert` → `"● Pedido para tratar 0421"`.
- **Defeito:** D2 — "tratar" serve para qualquer coisa, logo não informa nenhuma.
- **Por que dói:** esta é a **única** mensagem que alcança o operador com a aba escondida
  ou o tablet em outra tela. É o momento de maior valor por palavra do app inteiro, e ela
  gasta as palavras dizendo que existe trabalho, sem dizer qual — quando `treatableOrderRefs`
  sabe exatamente qual dos quatro é (`can_confirm`, `can_advance`,
  `can_settle_delivery_cash`, `equipment_back_pending`). "Tratar" também não é o verbo de
  ninguém: ninguém na padaria trata um pedido.
- **Substituição:** o mesmo predicado que decide tocar decide a frase:
  - `can_confirm` → `"Pedido novo 0421"` · `"Aceitar ou recusar."`
  - `can_advance` → `"Pedido 0421 esperando você"` · `"O próximo passo já está liberado."`
  - `can_settle_delivery_cash` → `"Acerto pendente no pedido 0421"` · `"Dinheiro da
    entrega ainda não entrou no caixa."`
  - `equipment_back_pending` → `"Maquininha do pedido 0421"` · `"Registre a devolução."`
  - com mais de um pendente, o título soma **por natureza**, nunca num número só:
    `"2 pedidos novos · 1 acerto"`.

## C6. "Em branco usa o total de R$ 48,00" — e só numa das duas telas

- **Onde:** `pages/index.vue`, descrição do diálogo de acerto:
  `"… ({{ settleRef }}). Em branco usa o total de {{ settleCard?.total_display }}."`;
  a mesma caixa em `pages/[ref].vue` **não** tem essa frase (diz `"Confirme após conferir
  o dinheiro e os comprovantes da maquininha."`).
- **Defeito:** D5 — vazio como código secreto; e o irmão que não recebeu o remédio.
- **Por que dói:** o campo de valor recebido tem um comportamento oculto (vazio = total),
  e ele existe nas duas telas. Num campo de dinheiro, deixar em branco por distração e
  registrar o total do pedido é uma diferença de caixa com origem invisível. Quem abre
  pelo detalhe não é avisado de nada.
- **Substituição:** o vazio para de ter significado — o campo nasce preenchido com o total
  (que é o caso esmagador), e a frase explica a exceção, não a regra:
  - campo: `value = total_display`, `aria-label="Valor recebido"`
  - abaixo: `"Já vem com o total do pedido. Mude se o cliente pagou outro valor."`
  - e a mesma frase nas duas telas.

## C7. "Maquininha 1. Voltou junto" como rótulo de caixa de seleção

- **Onde:** `pages/index.vue` e `pages/[ref].vue`:
  `<span>{{ equipment_label }}. Voltou junto</span>` numa `<label>` de checkbox. Com
  `equipment_back_pending`, `equipment_label` é `"Entregador levou maquininha 1"` — o
  texto renderizado é *"Entregador levou maquininha 1. Voltou junto"*.
- **Defeito:** D3 — a frase é uma afirmação onde deveria haver uma pergunta, e o leitor
  tem que decidir se marcar concorda ou contradiz.
- **Por que dói:** duas orações no passado, uma dizendo que saiu e outra que voltou,
  coladas num rótulo de caixa **desmarcada**. Marcar afirma o quê? O operador hesita num
  campo que fecha custódia de equipamento.
- **Substituição:** `"A maquininha voltou com o entregador"` (uma oração, no rótulo), e a
  frase de contexto (`"Entregador levou maquininha 1"`) sobe como linha acima da caixa,
  onde já está o `change_label` — exatamente o desenho que o troco usa e que funciona.

---

# Parte D — nota de rodapé do engenheiro, e prolixo

## D1. Três variações de "o sistema não vai fazer nada escondido"

- **Onde:**
  - `pages/feeds.vue`: `"Últimos registros locais de envio. Não representam o estado
    atual da loja na plataforma."`
  - `pages/channels/[ref]/catalog.vue`: `"Os dados locais ainda precisam de revisão. Este
    fluxo não envia alterações à plataforma."` e `"O arquivo será guardado no sistema;
    nenhum produto será alterado ou vinculado automaticamente."`
  - `components/CatalogBindingReview.vue`: `"Confirma apenas a identidade. Não copia
    fotos, preços ou descrições e não envia alterações à plataforma."`
  - `composables/useCatalogBindings.ts`: `"Gravação local confirmada. Nenhuma alteração
    enviada à plataforma."`
- **Defeito:** D6 — a frase começa (ou termina) defendendo a decisão de arquitetura.
- **Por que dói:** cinco frases, todas dizendo a mesma coisa: *não mandamos nada para o
  iFood*. O operador não sabia que havia esse risco e agora precisa ler a defesa contra
  ele cinco vezes, no lugar de ler o que fazer. A garantia importa **uma vez**, na entrada
  do fluxo.
- **Substituição:** uma linha, no topo da tela de revisão, e nenhuma nas outras quatro:
  > `"Nada aqui muda o iFood. Você está organizando o que já está no seu cadastro."`
  E os textos que sobram dizem o gesto: `"Escolha o arquivo do coletor iFood."`,
  `"Associar {anúncio} a {produto}."`, `"Vínculo gravado."`

## D2. O botão desabilitado do detalhe é uma frase de treze palavras

- **Onde:** `pages/[ref].vue`, `data-action="advance-blocked"`:
  `{{ projectedAction('advance')?.reason }}` **como rótulo do botão** — e o `reason` é o
  `_ADVANCE_BLOCK_MESSAGES` inteiro, por exemplo *"Pagamento ainda não foi confirmado. O
  pedido só avança depois que o dinheiro entra."*
- **Defeito:** D8 — e, de quebra, a incoerência com o board, que faz o contrário (A7).
- **Por que dói:** um botão com duas orações e um ponto final parece um parágrafo com
  borda. E as duas telas do mesmo pedido tratam o mesmo estado de forma oposta: no
  cartão o rótulo é o verbo e a razão está escondida; no detalhe a razão é o rótulo e o
  verbo sumiu.
- **Substituição:** o desenho que A7 propõe, nas duas telas: rótulo curto no botão
  (`advance_block_label`), razão inteira em texto abaixo dele.

## D3. "Esta prévia mostra o escopo da decisão."

- **Onde:** `pages/catalog.vue`, sob o título da prévia de publicação:
  `"Esta prévia mostra o escopo da decisão. Após confirmar, acompanhe a sincronização das
  plataformas separadamente nas células."`
- **Defeito:** D8 + D7a (`escopo da decisão`, `sincronização`, `células`).
- **Por que dói:** vinte palavras para dizer duas coisas, e as duas em vocabulário de
  projeto. "Acompanhe a sincronização separadamente" é uma tarefa sem endereço.
- **Substituição:** `"Isto é tudo o que muda. O envio para cada canal aparece depois, na
  coluna dele."`

## D4. "Sair e descartar os rascunhos não desfaz gravações já aplicadas."

- **Onde:** `pages/catalog.vue`, `onBeforeRouteLeave`: `"Há alterações sem confirmação no
  catálogo. Sair e descartar os rascunhos não desfaz gravações já aplicadas. Deseja
  sair?"`
- **Defeito:** D6 + D8 — a oração do meio é a defesa de uma decisão de arquitetura, num
  `window.confirm()`, onde o operador tem dois botões e três segundos.
- **Por que dói:** é a frase mais longa deste app num diálogo modal do navegador, e a
  informação que ela carrega (o que já gravou, gravou) não muda o que ele vai fazer agora.
- **Substituição:** `"Há alterações que ainda não foram gravadas. Sair e perdê-las?"`

## D5. Miudezas com endereço

| Onde | String | Substituição |
|---|---|---|
| `index.vue`, rodapé dos três diálogos | `"Cancelar"` como botão de **fechar** o diálogo, ao lado de `"Recusar pedido"` | `"Voltar"` — que é o que `[ref].vue` e `OrderReasonDialog.vue` já usam. "Cancelar" é ato de negócio neste app (D7b) |
| `useOrderDetail.ts` | `"Notas salvas."` | `"Nota salva."` — a seção e o botão dizem "Nota da cozinha" / "Salvar nota", no singular |
| `OrderCourierPanel.vue` | `` `{{ attempts_count }}ª corrida não concluída` `` | ver abaixo |
| `catalog.vue` | `"Verificar esta gravação"`, `"Aplicar meu arraste à ordem atual"`, `"Descartar o rascunho de ordem"` | `"Conferir o resultado"` (B11), `"Usar a minha ordem"`, `"Descartar"` |
| `catalog.vue` | `` `{{ sku }} · {{ canal }} · mínimo {{ cell.tier }}` `` | `"a partir de {N} unidades"` — "mínimo 6" sozinho não diz mínimo de quê |
| `feeds.vue` | `"{{ synced }} sincronizados · {{ pending }} pendentes · …"` (cinco números sem substantivo) | `"De 84 produtos: 71 enviados · 5 enviando · 2 falharam · 4 retirados · 2 não se aplicam"` (vocabulário de B5) |
| `index.vue` | `"Negociações iFood pendentes"` / `"Confira solicitações e prazos, inclusive de pedidos já encerrados."` | `"O iFood pediu uma resposta"` / `"Cada um tem prazo. Alguns são de pedidos já encerrados."` |

**Sobre a "3ª corrida":** `attempts_count` é `len(block["attempts"])`, e `attempts` é a
lista de corridas **já arquivadas** (`_archive_current_ride`, em `shop/services/courier.py`).
Com três corridas fracassadas, a tela escreve *"3ª corrida não concluída"* — um ordinal
sobre um cardinal. O operador lê "a terceira corrida não deu certo" e conclui que está na
terceira; ele está na quarta, e três já morreram. É **D4** com cara de detalhe
tipográfico. **Substituição:** `"3 corridas não deram certo antes desta"`.

---

# Parte E — o que examinei e considerei BOM

Isto não é cortesia: metade do valor de uma varredura é saber onde **não** mexer. E cinco
dos itens abaixo são o padrão que os achados da Parte A deveriam copiar — em vários
casos, o conserto que eu proponho é *"faça como esta peça aqui do lado já faz"*.

## E1. A frase do troco conta a história na ordem em que ela acontece

`_change_label` (`order_queue.py`) é a melhor peça de copy deste domínio. Uma função,
três momentos, sem condicional na tela:

- antes do despacho: `"Cliente paga com R$ 50,00 · levar R$ 24,00 de troco"`
- na rua: `"Entregador levou R$ 24,00 de troco"`
- depois do acerto: `"Voltou R$ 50,00 de troco"`

A docstring diz o critério (*"a frase do troco, na ordem em que a história acontece"*), o
cartão a imprime inteira e o diálogo a reusa como contexto (`"{change_label}. Quanto
voltou?"`). Nenhuma das três admite duas leituras, nenhuma explica o mecanismo, e a
grandeza é sempre a mesma: dinheiro, com o sujeito na frente. **Não mexer.** O C7 é só o
pedido de que a caixa da maquininha ao lado copie este desenho.

## E2. O comentário de `changeBackSuggestionQ` é uma aula de por que a copy importa

Não é copy de tela, mas merece o registro: o comentário em `presentation/board.ts` explica
que a sugestão anterior (`change_out_q − change_out_suggested_q`) produzia **R$ 24 de
sobra fantasma por entrega**, e que sobra fantasma é o esconderijo perfeito de uma falta
real. É o tipo de raciocínio — *que número esta tela está realmente dizendo?* — que, se
tivesse sido aplicado à linha das maquininhas (A9) e à prévia do lote (A10), teria
evitado os dois.

## E3. `treatableOrderRefs` já decidiu, com argumento, o que NÃO faz o sino tocar

A encomenda futura fica de fora do conjunto tratável, e o comentário diz por quê: *"não é
trabalho do turno de agora. Incluí-la aqui fazia o sino do Gestor tocar no instante da
venda, embora o próprio board a colocasse corretamente em 'Agendados'."* A lógica está
certa e é generosa com o operador. O problema (C5, A6) é só que **os rótulos não herdaram
essa precisão**: a função sabe distinguir quatro naturezas de trabalho e a tela chama as
quatro de "pedido novo".

## E4. As razões de bloqueio, no Python, estão escritas para gente

`_ADVANCE_BLOCK_MESSAGES` é copy de operador de verdade, sem jargão e sem defesa de
arquitetura:

- `"Pagamento ainda não foi confirmado. O pedido só avança depois que o dinheiro entra."`
- `"Encomenda para uma data futura. O preparo abre no dia combinado."`
- `"Reserva na fila da fornada. O preparo abre quando o lote sair."`
- `"Nenhuma maquininha está disponível. Aguarde a devolução para despachar esta entrega."`

Duas orações: o fato e a condição de destravar. Há inclusive um comentário explicando por
que a frase de pagamento **não** fala em "preparo" (porque o mesmo bloqueio vale nos três
degraus). Isso é o padrão da casa. O A7 é o pedido para que a tela finalmente as mostre, e
o A8 é o único rótulo desta família que erra.

## E5. O quadro é honesto sobre o que é tempo real e o que não é

`realtimeIndicator` (`presentation/board.ts`) só acende a bolinha verde com o SSE
genuinamente aberto; sem ele, o rótulo é `"Atualização automática"` e o `title` diz
`"Sem tempo real; o board atualiza sozinho a cada 30s"`. O comentário nomeia o critério —
*"a bolinha verde não mente"*. É a mesma disciplina que falta em A1 e A2, aplicada aqui
com nome e tudo.

## E6. As duas telas que se recusam a vestir erro de identificação de erro de rede

`index.vue` e `[ref].vue` têm a guarda `!stationLocked`, com comentários que registram o
sintoma que ela matou: *"este parágrafo dizia 'Falha ao carregar a fila. Reconectando…' —
erro de identificação vestido de erro de rede, na abertura de todo turno"*. E o texto que
ficou no lugar do erro genérico é exato:
`"Falha ao atualizar a fila. Mantivemos a última leitura; atualize antes de confirmar
ações."` — diz o que falhou, o que a tela está mostrando, e o que fazer antes de agir.
Copiar essa frase resolveria metade da Parte C.

## E7. O bloco do cliente só diz o que sabe

`joinFacts` + `profileHistory`/`profileHabits` (`[ref].vue`) montam as linhas do cliente
**deixando de fora o que faltou**, com o comentário certo: *"nunca 'R$ 0,00' ou '0 pedidos'
no lugar de 'ainda não sabemos'"*. E as escolhas de destaque são de quem conhece o balcão:
selo só nos segmentos que mudam o atendimento (`"badge que aparece sempre deixa de ser
lido"`), restrição alimentar em âmbar porque é a única linha que vira incidente,
aniversário em negrito só no dia. Nada a fazer.

## E8. A negociação do iFood qualifica o verbo — é o modelo do B1

`"Aceitar solicitação"` / `"Recusar solicitação"`, a caixa `"Confirmo esta consequência"`
(cuja única falha é a palavra "consequência", B8), o prazo com a consequência do
vencimento dita por extenso (`"O iFood informa que aceitará o cancelamento ao vencer o
prazo."`) e o aviso honesto de que a resposta ainda vai ser confirmada pela plataforma.
É a peça deste app que mais leva a sério "o operador decide sobre o pedido de outra
pessoa". O B1 é só o pedido de que a barra de ações, a dois blocos de distância, pare de
usar a mesma palavra sem qualificar.

## E9. Miudezas que estão certas e que eu conferi de propósito

- `elapsedLabel` capa em dias: o comentário explica que é para evitar `"119h"`, que
  *"grita sem informar"*. Certo.
- `channelLabel` capitaliza um canal desconhecido em vez de renderizar vazio — canal novo
  nunca nasce mudo.
- `"Sem cliente"` em vez de campo vazio no cartão e no detalhe.
- `paymentPillIcon`: interrogação para "sem meio de pagamento" e ampulheta para
  "aguardando", com o comentário dizendo por que não são o mesmo ícone. É precisão
  semântica em 12 pixels.
- `"Nada por aqui agora."` e `"Nenhum alerta agora."` nos estados vazios: curtos, sem
  falsa animação, sem emoji.
- `"Abrir cadastro"` / `"Clientes"` levando ao Admin, com o comentário registrando que a
  saída existe porque o Gestor ainda não tem tela de clientes. Honesto.
- `CatalogAiSuggest`: `"Aceitar"` / `"Descartar"` sobre um rascunho, com o comentário
  deixando claro que nada é gravado ali. O verbo está certo porque o ato é esse mesmo.

---

## Onde eu procuraria o resto

1. **As duas tabelas de rótulo de avanço.** `NEXT_ACTION_LABELS` (chaveada pelo status
   **atual**) e o dicionário `labels` de `operational_actions` (chaveado pelo status
   **alvo**) produzem hoje exatamente as mesmas frases — conferi os seis caminhos, um a
   um, e batem. Mas são duas listas mantidas à mão, em dois arquivos, com chaves de
   naturezas diferentes; a primeira divergência não vai fazer barulho nenhum: o board vai
   dizer uma coisa e o detalhe outra, sobre o mesmo pedido.
2. **O `detail` das APIs do Django.** Boa parte do vermelho desta tela é `httpErrorMessage`
   sobre o `detail` do servidor (`shopman/shop/api_errors.py` e as views de
   `backstage/api/operations.py`), não copy do Nuxt. Trocar só o fallback do Nuxt conserta
   metade da frase — é o mesmo alerta que o relatório do Marketing deixou, e aqui vale
   mais, porque o `reason` do servidor vira **rótulo de botão** (D2).
3. **`components/CatalogProductPanel.vue` (784 linhas).** Varri os rótulos de campo e as
   listas de opção (B10 saiu daí), mas os `hint` e as mensagens de validação do bloco
   fiscal e de rotulagem merecem uma leitura própria: é o único lugar do app onde o texto
   carrega obrigação legal (ANVISA, NCM, CEST), e ali a régua da §2 tem um quarto modo de
   falhar que este documento não cobre — a frase que está certa e incompleta perante a
   norma.
