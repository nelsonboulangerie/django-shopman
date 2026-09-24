# Varredura de copy — app do PDV (18/09/2026)

- **Escopo:** `surfaces/pos-nuxt/app/` — `pages/`, `components/`, `composables/`,
  `presentation/`, `utils/`; mais o que o PDV consome de `surfaces/operator-kit/app/`
  quando a string aparece na tela dele. Lido no HEAD `21adc94c8`.
- **Natureza:** leitura e relatório. **Nenhuma linha de produto foi alterada.**
- **Régua:** [`docs/reference/omotenashi-copy.md`](../../reference/omotenashi-copy.md) —
  o teste de uma frase (§2) e os oito defeitos (§3). Os nomes D1–D8 são de lá; este
  relatório não inventa critério.
- **Ordem:** Onda 1 da §6.3. O PDV vem primeiro porque o operador decide com cliente na
  frente, dinheiro na gaveta e nota fiscal em jogo.

Onde há número, ele foi medido neste HEAD. Quando envelhecer, remeça.

## Placar

| Defeito | Achados |
|---|---:|
| D1 rótulo que mente | 10 |
| D4 grandezas somadas | 4 |
| D7 jargão e colisão de vocabulário | 7 |
| D2 verbo genérico apaga o ato | 4 |
| D3 frase que obriga a completar sentido | 4 |
| D8 prolixo | 3 |
| D6 nota de rodapé do engenheiro | 2 |
| D5 zero como código secreto | **0** — ver E7 |
| **Total** | **34** (30 fichas abaixo; alguns achados carregam dois defeitos) |

A ordem é a do dano (§6.1): **Parte A** faz o operador concluir errado, **Parte B** faz
parar para pensar, **Parte C** é só feio, **Parte D** são miudezas com endereço. A
**Parte E** diz o que examinei e considerei bom — é metade do resultado.

---

# Parte A — faz o operador concluir errado

## A1. O selo verde e "Venda concluída" aparecem com o Pix ainda não pago

- **Onde:** `presentation/saleResult.ts`, `saleResultTitle()` → `"Venda concluída"` /
  `"Venda concluída. Obrigado, {nome}!"`; e `components/PosSaleResult.vue`, o círculo
  verde com o ícone `lucide:check`, logo acima. No mesmo ecrã, mais abaixo:
  `"Aguardando confirmação do PIX…"`.
- **Defeito:** D1.
- **Por que dói:** o único caso que derruba o selo verde é `paymentFailed()`, que só é
  verdadeiro com `status === "error"` ou `"unavailable"`. O Pix **pendente** — QR na tela,
  polling vivo, dinheiro nenhum na conta — passa como sucesso: check verde, título em
  corpo 3xl dizendo que a venda está concluída, e o nome do cliente no vocativo. O
  comentário do próprio componente declara a regra certa (*"O selo verde é uma AFIRMAÇÃO
  sobre o dinheiro: só aparece quando houve cobrança"*) e a implementação lê "cobrança
  criada" onde a frase diz "cobrança recebida". É a mesma forma do `"Enviado"` sobre
  mensagens na fila que o Marketing tinha (A2 de lá), e aqui vale o valor da venda: o
  operador entrega o pão, fecha a tela e vai atender o próximo. A tela já sabe que a
  espera existe — o CTA dela troca para `"Nova venda mesmo assim"` — e o título continua
  afirmando o contrário do CTA.
- **Substituição:** o título segue o estado do dinheiro, e o selo segue o título.
  - Pix/link com prova e sem confirmação → `"Venda registrada. Falta o pagamento"`, selo
    neutro (não verde), e o detalhe já existente logo abaixo:
    `"Aguardando confirmação do PIX…"`.
  - Confirmação chega (`pixStatus === "paid"`) → a **mesma** tela troca para
    `"Venda concluída"` e o selo acende verde. Aí é verdade.
  - Dinheiro/cartão/Pix confirmado → como está hoje.
  - O vocativo (`"Obrigado, Maria!"`) só entra no estado concluído: agradecer por um
    pagamento que não chegou é a parte que mais convence o operador de que chegou.

## A2. "itens" conta linha no carrinho e unidade em todo o resto do PDV

- **Onde:** `components/PosCartPanel.vue`, no cabeçalho da comanda:
  `{{ items.length }} {{ items.length === 1 ? "item" : "itens" }}`.
  Contra: `components/PosPaymentWorkspace.vue`, `summaryUnits` (`Σ item.qty`) com o mesmo
  `"item"/"itens"`; `pages/display.vue` (a tela virada para o cliente), `itemCountLabel`,
  também `Σ qty`; `presentation/tabBoard.ts`, `summary` (`item_count` da projection, que é
  `sum(_qty_int(...))`); `presentation/kitchen.ts`, `kitchenHandoffNote` e o badge de
  `"Enviar"`, ambos em unidades.
- **Defeito:** D4.
- **Por que dói:** três croissants numa linha e um café noutra são **"2 itens"** no painel
  onde o operador lança, e **"4 itens"** no resumo do pagamento, no quadro de comandas e
  **na tela que o cliente está lendo**, ao lado. Quem confere em voz alta ("são dois itens,
  certo?") confere pelo número errado, com o cliente olhando o número certo. O resto do app
  já decidiu, e decidiu por escrito: o cabeçalho de `kitchen.ts` registra que a frase da
  cozinha foi migrada de linha para unidade justamente porque *"'1 item já está na cozinha'
  quando o que estava lá eram três chás"* era o número errado, e conclui que **"linha"
  virou artefato interno, que ninguém fala em voz alta**. O cabeçalho do carrinho é o
  último lugar que ainda fala linha — e é o mais lido.
- **Substituição:** uma grandeza só, a unidade, em toda a superfície.
  - cabeçalho da comanda → contar `Σ item.qty`, mantendo o texto `"{n} itens"`.
  - contador da seleção múltipla → `"{n} itens selecionados"` também em unidades (marcar
    a linha dos três croissants seleciona três itens).
  - confirmação de remoção → `"Remover 3 itens selecionados?"` em unidades, pelo mesmo
    motivo: o que sai do pedido são três.
  - **Nunca** trocar para a palavra "linha" na tela para resolver a diferença: é o nome
    interno, e o `kitchen.ts` já documentou por que ele não sobe.
  - ⚠️ Há um gêmeo do outro lado: no evento de auditoria `tab_cleared`
    (`shopman/shop/services/pos.py`), `item_count` é `len(discarded)` — **linhas** —
    enquanto o `item_count` da `POSTabProjection` é unidades. Mesmo nome, duas grandezas,
    e uma delas alimenta tela. Não é copy, mas é a mesma armadilha um andar abaixo.

## A3. "Validar" — o botão que cobra a venda não diz o que faz, e as frases ao redor o chamam de outra coisa

- **Onde:** `components/PosPaymentWorkspace.vue`, `ctaLabel` → `"Validar"` /
  `"Autorizar e validar"`. E, na mesma tela ou a um passo dela:
  `presentation/kitchen.ts` → `"Ao finalizar, os 3 itens vão para a cozinha."`;
  `composables/usePosSale.ts` → `"Escolha Entrega ou Retirada antes de finalizar."` e
  `"Identifique o cliente para finalizar a venda."`;
  `components/PosPaymentWorkspace.vue`, `ctaBlock` → `"Faltam R$ 12,00 para validar."`;
  `components/PosShortcutsHelp.vue` → `"Validar a venda (com o total coberto)"`.
- **Defeito:** D2 (o verbo não nomeia o ato) somado a D1 na sua segunda forma (a
  instrução nomeia um controle que não existe) e a D7c (dois nomes para o mesmo gesto).
- **Por que dói:** é o botão mais apertado do sistema, e é o que fecha o pedido, cobra,
  chuta a gaveta, manda o que falta para a cozinha e dispara a NFC-e. "Validar" não nomeia
  nada disso — é o *Validate* do Odoo traduzido ao pé da letra, e o comentário do arquivo
  admite a origem. Em português, validar é o que se faz com um formulário: conferir se está
  certo. O operador novo lê "Validar" e procura o botão de cobrar. Pior: **toda frase que
  fala desse botão o chama de "finalizar"** — inclusive o aviso que diz o que vai acontecer
  com a comida (*"Ao finalizar, os 3 itens vão para a cozinha"*) e as duas recusas do
  servidor. A tela manda finalizar e não tem nenhum controle com esse nome.
- **Substituição:** o rótulo nasce do ato real, como o `deliveryActionLabel` do Marketing
  já faz, e as frases ao redor usam o mesmo verbo.

  | situação | rótulo |
  |---|---|
  | cobrança no caixa (o caso comum do balcão) | **"Cobrar"** |
  | cobrança na entrega/retirada (`on_delivery`) | **"Fechar pedido"** — nada é cobrado agora, e o guia ao lado já diz `"Sem cobrança agora: …"` |
  | falta autorização do gerente | **"Pedir autorização"** (ver A4) |
  | revisão falhou | `"Tentar de novo"` — já está certo, não mexer |

  E as frases vizinhas passam a dizer o mesmo verbo:
  `"Ao cobrar, os 3 itens vão para a cozinha."` ·
  `"Escolha Entrega ou Retirada antes de cobrar."` ·
  `"Identifique o cliente para cobrar."` · `"Faltam R$ 12,00 para cobrar."` ·
  no dicionário de atalhos, `"Cobrar a venda (com o total coberto)"`.

  ⚠️ Isto é a primeira linha de um **vocabulário fechado do PDV**, que a §4.2 da régua
  manda escrever no contrato da superfície antes da Onda 2. Ver "Onde eu procuraria o
  resto".

## A4. "Autorizar e validar" não autoriza nem valida — abre o teclado do gerente

- **Onde:** `components/PosPaymentWorkspace.vue`, `ctaLabel` quando `needsAuth`:
  `"Autorizar e validar"`. O `onCta()` correspondente faz
  `managerAuthOpen.value = true; return;`.
- **Defeito:** D1.
- **Por que dói:** é a regra de caminho da §D1 da régua — num fluxo de várias etapas, **só
  o último passo diz o verbo do ato**. Aqui o operador aperta um botão que promete as duas
  coisas e recebe uma terceira: um diálogo pedindo o gerente. O dano é menor que o de A1
  porque o diálogo aparece na hora, mas é o mesmo defeito de A3 do Marketing
  (`"Disparar"` abrindo um painel), e num botão que o operador aperta com fila na frente.
- **Substituição:** `"Pedir autorização"`. O diálogo que abre já diz o ato certo
  (`"Autorizar a venda"`, de `operator-kit/app/presentation/managerAuth.ts`), e quem
  conclui é o gerente digitando o PIN — que é, corretamente, o último passo.

## A5. "Cadastrar cliente novo com este CPF" não cadastra ninguém

- **Onde:** `presentation/customerSearch.ts` — `"Cadastrar cliente novo com este CPF"`,
  `"Cadastrar cliente novo com o {telefone}"`, `"Cadastrar «{nome}» só com o nome"`.
  Os três handlers (`onResolveCpf`, `onTransfer`, `onCreateNameOnly` em
  `components/PosCustomerModal.vue`) **apenas preenchem um campo do formulário e movem o
  foco**. No rodapé do mesmo modal, `"Cadastrar cliente"` faz o POST em
  `/pos/customer/resolve/` e cria o cadastro de verdade.
- **Defeito:** D1, na forma mais cara: **o mesmo verbo, no mesmo modal, mentindo numa
  metade e dizendo a verdade na outra.**
- **Por que dói:** o operador busca o CPF, não acha, toca em "Cadastrar cliente novo com
  este CPF", vê o CPF aparecer no formulário e conclui que cadastrou. Fecha o modal — e
  nada foi salvo. O caso é pior no balcão cheio, que é exatamente quando ele não relê a
  tela. E o defeito é invisível para quem lê só o código do botão: o rótulo é impecável, e
  o erro está a dois arquivos de distância.
- **Substituição:** o botão diz o gesto que ele faz — preencher —, e o cadastro continua
  sendo o rodapé:
  - `"Usar este CPF no cadastro novo"`
  - `"Usar o {telefone} no cadastro novo"`
  - `"Começar um cadastro com «{nome}»"`

  Os três levam o foco ao próximo campo, como já levam, e o rodapé `"Cadastrar cliente"`
  segue sendo o único lugar da tela que diz "cadastrar" como ato.

**Irmã, no mesmo defeito e noutra tela:** `components/PosRecentSales.vue`, botões
`"Enviar e-mail"` / `"Reenviar e-mail"` — **só abrem o campo de e-mail**; quem envia é o
`"Enviar"` ao lado. **Substituição:** o botão diz o que abre —
`"E-mail da nota"` / `"E-mail da nota (já enviada)"` — e o `"Enviar"` ao lado continua
sendo o único que diz o ato.

## A6. "Concluir entrega" e "Concluir retirada" só fecham um diálogo

- **Onde:** `components/PosFulfillmentModal.vue`, rodapé:
  `"Concluir entrega"` / `"Concluir retirada"`. O handler é `isOpen = false`.
- **Defeito:** D1.
- **Por que dói:** "concluir a entrega" é um ato real desta casa — é o que o Gestor de
  Pedidos faz quando o pedido chegou na mão de alguém. Aqui o operador está apenas
  escolhendo **como** o pedido será recebido, antes de qualquer coisa acontecer, e o botão
  anuncia o fim do caminho. Numa encomenda para sábado, o rótulo afirma que a entrega
  terminou no momento em que ela foi combinada.
- **Substituição:** o rodapé confirma a escolha, não o desfecho:
  `"Entrega neste endereço"` / `"Retirada no balcão"`. Quando ainda falta escolher, o
  rótulo desabilitado atual (`"Escolha o recebimento"`) está certo e fica.

## A7. "Fechar caixa" aparece duas vezes no caminho, e nenhuma das duas fecha

- **Onde:** `pages/session/index.vue` — o tile `"Fechar caixa"` (que abre o diálogo) e o
  botão de submissão **dentro** do diálogo, também `"Fechar caixa"` (que só arma
  `confirmingClose`). Quem encerra o turno é `"Confirmar"`, no terceiro passo.
- **Defeito:** D1.
- **Por que dói:** encerrar o turno é irreversível e mexe no livro-caixa. A tela repete
  duas vezes o verbo do ato em controles que não o praticam, e o controle que pratica diz
  a palavra mais vaga da sequência: `"Confirmar"`. Quem já usou o app duas vezes aprende a
  apertar "Fechar caixa" no automático — e a única barreira contra isso é uma confirmação
  cujo rótulo não diz o que confirma.
- **Substituição:** um verbo por degrau, e o último degrau carrega o ato.
  - tile → `"Fechar caixa"` (correto: é uma porta com nome do destino, como
    `"Pedir troco"`, e a descrição `"Contagem cega · encerra o turno"` já avisa).
  - botão do diálogo → `"Conferir e fechar"`.
  - confirmação → `"Fechar o caixa"` (hoje `"Confirmar"`), mantendo o eco do valor contado
    que a frase acima já traz.

## A8. "Testar gaveta" abre a gaveta de verdade e deixa registro no turno

- **Onde:** `pages/session/index.vue`, botão `"Testar gaveta"`. O `probeDrawer()` sonda
  o agente e, quando a sonda responde, **registra uma abertura** (`drawer_open` com motivo
  `"Teste de gaveta"`) e chuta a gaveta. A frase de resultado confirma:
  `"{mensagem} A gaveta abriu? Se não abriu, confira o cabo dela na impressora."`
- **Defeito:** D1.
- **Por que dói:** "testar" promete um ato sem consequência. O que acontece é uma abertura
  de gaveta fora de venda — o gesto que a casa audita de propósito, com motivo, autor e
  hora gravados no turno. O operador que testa três vezes deixa três aberturas no
  relatório do dia, e não sabia que estava produzindo registro nenhum.
- **Substituição:** `"Abrir para testar"`, com a descrição de uma linha que a tela já
  tem espaço para carregar: `"Abre a gaveta e fica registrado no turno, como qualquer
  abertura sem venda."` É o mesmo contrato que o diálogo `"Abrir gaveta"` já enuncia
  (`"Abrir sem venda fica registrado no turno: quem abriu, quando e por quê."`) — falta só
  o botão de teste concordar com ele.

## A9. "Vendas hoje", dentro do cartão do turno aberto, não é do turno

- **Onde:** `pages/session/index.vue`, a caixa de duas colunas do turno aberto:
  `"Aberto em"` ao lado de `"Vendas hoje"`. O número é `shift.count`, de
  `build_pos_shift_summary` (`shopman/backstage/projections/pos.py`):
  `Order.objects.filter(channel_ref=POS, created_at__date=hoje).exclude(status="cancelled").count()`.
- **Defeito:** D4.
- **Por que dói:** a coluna da esquerda é do turno (`"Aberto em 08:02"`); a da direita é do
  **dia inteiro do canal PDV**, somando os dois balcões, os turnos anteriores já fechados e
  o que o colega vendeu antes de você assumir. É o número que o operador lê quando quer
  saber como está indo *o seu* turno, num cartão intitulado pelo turno. Numa loja de duas
  gavetas, ele nunca fecha com a contagem dele.
- **Substituição:** o rótulo diz de quem é o número —
  `"Vendas hoje na loja"` — e, se a intenção era mesmo o turno, o par honesto é
  `"Aberto em"` / `"Vendas neste turno"`, alimentado pelo `sales_count` da leitura X, que
  já existe em `cash_session.py` e já conta as vendas do turno aberto. **Enquanto a
  segunda não existir, o rótulo honesto é o primeiro** — feio, mas não mente.

## A10. O crachá "Precisa de você" soma devolução, pedido de troco e cliente com saldo

- **Onde:** `presentation/cash.ts`, `attentionCount()` —
  `pendingCashRefunds.length + pendingChangeRequests.length + accountBalances.length`.
  Renderizado em `pages/session/index.vue` como o número ao lado de `"Precisa de você"`,
  com o leitor de tela dizendo `"pendência"` / `"pendências"`.
- **Defeito:** D4.
- **Por que dói:** são três naturezas com três donos e três urgências: **devolução** é um
  pedido cancelado esperando dinheiro sair da gaveta (com PIN de gerente); **pedido de
  troco** é alguém que precisa que tragam cédulas até o balcão; **conta na casa** é um
  cliente com saldo em aberto, que pode esperar a semana inteira. "4 pendências" pode ser
  quatro devoluções (dinheiro parado, cliente reclamando) ou quatro contas de fiado (nada
  a fazer agora). O operador decide se larga o balcão com base nesse número.
- **Substituição:** o crachá some e as três seções — que já existem logo abaixo, com
  título próprio — carregam cada uma o seu número:
  `"Devoluções em dinheiro pendentes · 2"` · `"Pedidos de troco pendentes · 1"` ·
  `"Contas na casa · 1"`. Se um número único no cabeçalho for necessário para chamar a
  atenção de longe, ele conta **só o que exige gesto agora**: devoluções + pedidos de
  troco, e o rótulo diz isso — `"Esperando você · 3"`, com as contas na casa fora da conta
  e visíveis na sua seção.

## A11. "Liberar comanda" cancela a comida que já está no fogão, e o aviso não diz

- **Onde:** `components/PosTabHeader.vue`, diálogo de confirmação: título
  `"Liberar comanda?"`, corpo `"Isso descarta este atendimento e libera a comanda. A ação
  não pode ser desfeita."`, botão destrutivo `"Liberar comanda"`. O `clearCurrentTab()`
  faz DELETE em `clear_tab`; no servidor (`shopman/shop/services/pos.py`,
  `clear_pos_tab`), se a comanda tinha linhas disparadas, ele **cancela os tickets da
  cozinha** (`kds.cancel_tickets_for_session`).
- **Defeito:** D1 pela ausência — o aviso lista a consequência barata (o atendimento some,
  a comanda libera) e cala a cara (o que já estava sendo preparado é cancelado).
- **Por que dói:** é a decisão que a casa já nomeou: *o dado que falta tem que fechar a
  promessa*. Quem lê "descarta este atendimento" pensa em apagar itens de uma tela. O que
  acontece é um ticket sumindo do KDS enquanto alguém está com a mão na massa — e a tela do
  quadro de comandas **já sabia** que havia comida lá, porque ela carimba o selo
  `"Não pago"` com o `title` `"Disparado para a cozinha e ainda não pago"`.
- **Substituição:** a frase muda conforme a comanda tenha ou não itens na cozinha.
  - sem itens disparados: como está.
  - com itens disparados: `"Isso descarta este atendimento e libera a comanda. O que já
    foi enviado à cozinha é cancelado — avise quem está lá dentro. Não dá para desfazer."`

## A12. "1 venda em aberto" nas contas na casa conta pagamentos, não vendas

- **Onde:** `pages/session/index.vue`, na lista de `"Contas na casa"`:
  `"{n} venda"` / `"{n} vendas em aberto"`. A fonte é `account.intents` →
  `PaymentService.account_balances()` → `Count("id")` de `PaymentIntent` com
  `method=ACCOUNT` e `status=AUTHORIZED`.
- **Defeito:** D4.
- **Por que dói:** um pedido pago metade em dinheiro e metade "em conta" gera um intent;
  dois pedidos podem gerar três intents se algum foi lançado em duas partes. O número que
  o operador diz em voz alta ao cliente ("você tem três vendas em aberto") é a contagem de
  cobranças, não de idas à padaria. E na mesma casa, duas telas adiante
  (`pages/session/report.vue`), `"Vendas"` conta `order_ref` distintos e `"Pagamentos"`
  conta intents — ou seja, a palavra certa para este número já existe no app, e não é a
  que está aqui.
- **Substituição:** `"{n} cobranças em aberto"`, alinhando com o `"Pagamentos"` do
  relatório. Se o que se quer mesmo é o número de compras, ele se busca por `order_ref`
  distinto, como o relatório já faz — e aí o rótulo `"vendas"` passa a ser verdade.

## A13. O aviso manda escolher "Receber no caixa" num controle que se chama "No balcão"

- **Onde:** `components/PosPaymentWorkspace.vue`, `ctaBlock`:
  `"Troque a linha por dinheiro ou cartão na maquininha, ou escolha Receber no caixa."`
  O rótulo do controle vem de `presentation/payment.ts`, `paymentCollectionLabel()`, que
  devolve `"No balcão"` quando `salesMode === "order"` (e o `collection.label` do servidor,
  `"Receber no caixa"`, no balcão).
- **Defeito:** D1, segunda forma — a instrução nomeia um controle que a tela não tem.
- **Por que dói:** este aviso aparece justamente no modo encomenda, que é onde o rótulo é
  `"No balcão"`. O operador procura "Receber no caixa" no seletor e não acha; o que está
  ali são dois botões dizendo "No balcão" e "Na entrega".
- **Substituição:** a frase cita o rótulo que a própria tela está mostrando —
  `` `… ou escolha ${paymentCollectionLabel(terminalCollection, salesMode, fulfillmentType)}.` `` —
  ou, mais simples e sem interpolação, descreve o efeito em vez do controle:
  `"Troque a linha por dinheiro ou cartão na maquininha, ou cobre agora, antes de o pedido
  sair."`

---

# Parte B — faz parar para pensar

## B1. "agente", "estação", "sonda" — o encanamento na tela do balcão, e com quatro nomes

- **Onde:** `presentation/terminalHealth.ts` (`"Agente do balcão"`, `"sondando a
  estação"`, `"agente respondendo"`, `AGENT_OFFLINE_MESSAGE` =
  `"Agente offline. Recibos sairão pelo diálogo do navegador."`,
  `"sem caminho até a estação (agente offline)"`); `composables/useCounterAgent.ts`
  (`"O agente recusou o comando."`, `"O agente não sabe o estado da gaveta."`,
  `"Este balcão não tem agente para ler a gaveta."`, e o normalizador que já converte
  `"O agente local não respondeu."` → `"O agente não respondeu."` e
  `"O agente local desta estação não está rodando."` → `"O agente da estação não está
  rodando."`); `components/PosTerminalHealth.vue` (`"Reinicie o agente na estação do
  balcão. Depois de qualquer mudança na configuração do terminal, o agente precisa ser
  reiniciado de novo."`); `composables/usePosOrderTickets.ts`
  (`"o agente do balcão não respondeu"`).
- **Defeito:** D7a (termo interno vazado) e D7c (o mesmo objeto com quatro nomes:
  *o agente*, *o agente local*, *o agente da estação*, *o agente do balcão*).
- **Por que dói:** o "agente" é o programinha que roda na máquina do balcão e fala com a
  impressora e a gaveta. A padaria não tem esse conceito, e o operador que lê "Agente
  offline" não sabe se o recibo saiu, se a venda valeu, ou o que ele deve fazer. A prova de
  que o app sabe disso está no próprio arquivo: `AGENT_OFFLINE_MESSAGE` foi escrito com o
  comentário *"O estado honesto quando o agente caiu: diz O QUE acontece com os recibos"* —
  a segunda metade da frase está certíssima, e a primeira ainda é o nome de um processo.
  Existe ainda a normalização de quatro variantes para duas, o que mostra que o problema já
  foi visto e resolvido pela metade.
- **Substituição:** o agente se chama pelo que ele é para quem está no balcão — a **ligação
  com a impressora e a gaveta**:
  - linha do card: `"Impressora e gaveta"` (hoje `"Agente do balcão"`), com estado
    `"conferindo…"` (hoje `"sondando a estação"`) e `"respondendo"`.
  - `AGENT_OFFLINE_MESSAGE` → `"Sem ligação com a impressora deste balcão. O recibo vai
    sair pela janela de impressão do navegador."`
  - `"O agente não respondeu."` → `"A impressora deste balcão não respondeu."`
  - `"O agente não sabe o estado da gaveta."` → `"Não dá para saber se a gaveta está
    aberta neste balcão."`
  - `"Este balcão não tem agente para ler a gaveta."` → `"Este balcão não lê o estado da
    gaveta."`
  - `"O agente recusou o comando."` → `"A impressora recusou o comando."`
  - a instrução de reinício é a única que fala com quem conserta, e pode manter o nome
    técnico **se** disser para quem é: `"Peça para reiniciar o programa do balcão (e sempre
    que a configuração do terminal mudar)."`

## B2. "Balcão" quer dizer duas coisas no mesmo app

- **Onde:** `components/PosTabHeader.vue`, o seletor de **modo de atendimento**:
  `"Balcão"` × `"Encomendas"`. Contra: `components/PosRecentSales.vue`, sobretítulo do
  painel — `"Balcão"` como o **lugar**; e `"o agente do balcão"`, `"As fichas saem no
  balcão que tem impressora."`, `"Este balcão não tem agente…"`, `"Cobra agora, no
  balcão."`, `"Nome no balcão"`, `"Observações do balcão"`.
- **Defeito:** D7b — colisão de vocabulário dentro do mesmo app. É a "faixa" do Marketing.
- **Por que dói:** o operador acabou de aprender, no cabeçalho, que "Balcão" é o modo de
  venda (o oposto de Encomendas). Meia tela adiante, `"Últimas vendas"` traz o sobretítulo
  `"Balcão"`, e ele lê "vendas do modo balcão" — que não é o que a lista mostra. Ninguém
  desconfia de uma palavra que acabou de aprender no app.
- **Substituição:** o **modo** fica com "Balcão" (é o nome do negócio e não tem substituto)
  e o **lugar** passa a ser dito pelo nome que o app já usa em toda a seção de saúde:
  **este terminal**.
  - sobretítulo de `"Últimas vendas"` → `"Neste terminal"` (ou some: o título já basta).
  - `"As fichas saem no balcão que tem impressora."` → `"As fichas saem no terminal que
    tem impressora."`
  - `"Nome no balcão"` e `"Observações do balcão"` ficam: ali "balcão" é o atendimento
    presencial, e é isso que significam.

## B3. Transferir, Mover, Dividir, Juntar — quatro verbos para um gesto, e "Dividir" para dois

- **Onde:** `components/PosMoveLinesDialog.vue` — título `"Transferir · #1007"`, um dos
  três modos também chamado `"Transferir"`, os outros dois `"Dividir"` e `"Juntar"`, e o
  botão que executa qualquer um dos três chamado `"Mover"`. Em
  `components/PosShortcutsHelp.vue`, o mesmo F10 é descrito como `"Transferir itens para
  outra comanda"`. A Action do servidor chama-se `move_tab_lines`, com label `"Transferir"`.
  E, no pagamento, o mesmo F10 é `"Dividir a conta"` — outro "dividir" completamente.
- **Defeito:** D7b + D7c.
- **Por que dói:** para fazer uma coisa só, o operador lê quatro palavras. Pior: "Transferir"
  é ao mesmo tempo o nome da caixa inteira e o nome de um dos três botões dentro dela, e
  quem escolhe "Dividir" confirma apertando "Mover". E "Dividir", na tecla F10 de uma tela,
  reparte **itens entre comandas**; na F10 da tela ao lado, reparte **a conta entre pessoas**.
- **Substituição:** um nome para a caixa, um verbo por modo, e o botão repete o modo
  escolhido.
  - título → `"Mover itens · #1007"`.
  - modos → `"Para outra comanda"` (hoje *Transferir*) · `"Separar numa comanda nova"`
    (hoje *Dividir*) · `"Juntar nesta outra comanda"` (hoje *Juntar*).
  - botão → `"Mover itens"` nos três casos.
  - dicionário de atalhos → `"Mover itens para outra comanda"`, e no pagamento
    `"Dividir a conta entre pessoas"`, para que as duas F10 não se confundam de memória.

## B4. Trinta e uma mensagens "Falha ao X." que não dizem o que sobrou nem o que fazer

- **Onde:** 31 strings distintas, em 7 arquivos. Uma amostra:
  `"Falha ao fechar caixa."` · `"Falha ao devolver o dinheiro."` ·
  `"Falha ao registrar movimento."` · `"Falha ao enviar à cozinha."` ·
  `"Falha ao mover itens."` · `"Falha ao salvar o cliente."` · `"Falha ao cancelar venda."` ·
  `"Falha ao revisar checkout."` · `"Falha ao revisar venda."` · `"Falha na ação."`
- **Defeito:** D3 (obriga o leitor a completar sentido: *o dinheiro saiu? a comida foi?
  posso tentar de novo?*), com D7a de brinde em `"checkout"` e D7c em revisar
  *checkout* × revisar *venda*, que são a mesma operação.
- **Por que dói:** o mesmo app tem a frase certa escrita, e mais de uma vez:
  `"Não foi possível salvar a comanda. Os itens seguem na tela; confira a conexão e tente
  de novo."` Ela diz três coisas que "Falha ao salvar a comanda." não diz — o que
  sobreviveu, o que verificar e que pode repetir. Com dinheiro em jogo a lacuna é pior:
  depois de `"Falha ao devolver o dinheiro."`, o operador não sabe se a gaveta chegou a
  abrir. (Neste caso o código é categórico — a gaveta só é chutada depois do sucesso —, o
  que significa que **a informação existe e só não foi escrita**.)
- **Substituição:** o padrão é *o que aconteceu · o que não aconteceu · o que fazer*, e ele
  já está na casa. Os três de dinheiro, escritos:
  - `"Não foi possível fechar o caixa. O turno continua aberto e a contagem está na tela;
    confira a conexão e tente de novo."`
  - `"A devolução não foi registrada. Nada saiu da gaveta; tente de novo."`
  - `"O movimento não foi registrado. A gaveta não abriu e nada foi lançado no livro-caixa;
    tente de novo."`
  - e `"Falha na ação."` deixa de existir: toda ação tem nome.
  ⚠️ São **fallbacks** — o servidor manda a mensagem quando tem uma. Consertar os 31 sem
  olhar o `detail` do Django conserta metade da frase, como já aconteceu no Marketing.

## B5. "PIX Efí exige confirmação automática" na hora de cobrar na entrega

- **Onde:** `composables/usePosSale.ts`, `addTender()`:
  `` `Na ${handoff}, use dinheiro ou cartão na maquininha. PIX Efí exige confirmação
  automática.` ``
- **Defeito:** D6 (a frase explica a restrição de arquitetura) e D7a ("Efí" é o nome do
  provedor, que não existe no vocabulário da padaria).
- **Por que dói:** a primeira metade está certa e é a única coisa acionável. A segunda
  conta ao padeiro por que o time escolheu o que escolheu, com o nome de uma empresa que
  ele não conhece — e ainda por cima "exige confirmação automática" soa como uma coisa boa,
  o que deixa a proibição sem motivo.
- **Substituição:** `"Na entrega, só dinheiro ou cartão na maquininha. O Pix não dá para
  conferir fora do balcão."`

## B6. Cliente, cadastro, contato — e quatro verbos para dizer de quem é o pedido

- **Onde:** `components/PosCustomerModal.vue` e `presentation/customerDecision.ts`.
  No mesmo selo convivem `"Cliente novo"` e `"Cadastro existente · {Nome}"`; o rodapé é
  `"Salvar cadastro"` / `"Cadastrar cliente"`; a busca vazia diz `"Nenhum cadastro
  encontrado."` e o botão `"Remover cliente"`. Para o mesmo gesto — fixar de quem é o
  pedido — os painéis de decisão oferecem `"Associar cliente"`, `"Vincular {Nome}"`,
  `"Atender {Nome}"`, `"Atender este"`, `"Usar cadastro de {Nome}"` e `"Seguir neste
  cadastro"`; três deles caem literalmente na mesma função (`attendCustomer`).
- **Defeito:** D7c — o mesmo conceito com nome diferente conforme a porta de entrada.
- **Por que dói:** é o subtipo que a régua chama de pior do que não entender: quem aprende
  o app por uma tela não reconhece a outra e conclui que são coisas diferentes. "Vincular"
  e "Atender" parecem dois gestos, e são um. E a distinção pessoa × ficha — que o app tenta
  fazer com *cliente* × *cadastro* — se desfaz na frase `"Cadastrar cliente"`, que usa as
  duas.
- **Substituição:** duas decisões, e o resto segue.
  1. **A pessoa é "cliente"; a ficha é "cadastro".** O rodapé passa a
     `"Criar cadastro"` / `"Salvar cadastro"`; o selo, a `"Sem cadastro"` ×
     `"Cadastro de {Nome}"`; `"Remover cliente"` vira `"Tirar o cliente do pedido"` (que é
     o que ele faz: não apaga cadastro nenhum).
  2. **Um verbo para dizer de quem é o pedido: "atender".** `"Atender {Nome}"` em todos os
     seis lugares; `"Associar cliente"` e `"Vincular {Nome}"` somem; `"Seguir neste
     cadastro"` vira `"Atender com este cadastro"`.

  ⚠️ Isto é conteúdo do vocabulário fechado do PDV (ver "Onde eu procuraria o resto"), não
  de um PR avulso: trocar seis rótulos sem fechar o dicionário troca um nome errado por
  outro.

## B7. O botão que chama o gerente é três pontinhos chamados "Mais opções"

- **Onde:** `components/PosDrawerLockDialog.vue`, `aria-label="Mais opções"` no botão de
  reticências — sem rótulo visível. O handler é `drawerLock.askManager()`, que abre o
  teclado do gerente **e já registra a tentativa** (`drawer_unlock_attempt`, outcome
  `"opened"`).
- **Defeito:** D2.
- **Por que dói:** a gaveta está aberta, a venda está parada, e a única saída que não é
  "fechar a gaveta" está escondida atrás do rótulo mais genérico que existe. Quem não
  conhece o app fica preso olhando `"Aguardando a gaveta fechar"`. E o toque, que parece
  inofensivo, escreve uma linha de auditoria.
- **Substituição:** `"Chamar o gerente"` (`aria-label` e, de preferência, texto visível —
  cabe). O X ao lado, `"Desistir desta venda"`, já está certo e é o modelo.

---

# Parte C — é só feio

## C1. O subtítulo das Fichas de pedido explica o que o papel não é, e depois diz que o papel diz isso

- **Onde:** `pages/tickets.vue`: `"Comprovante do pedido remoto — entrega, retirada ou
  encomenda — para pendurar no painel. Não é nota fiscal e não comprova pagamento; o papel
  diz isso."`
- **Defeito:** D6 + D8. Trinta palavras, com um travessão duplo, um ponto e vírgula, e uma
  oração final que existe para tranquilizar quem escreveu o código.
- **Por que dói:** é a assinatura literal do D6 — a frase gasta a metade final defendendo
  a decisão ("o papel diz isso") contra um risco que o operador não sabia que existia. E o
  aposto entre travessões repete a lista de recebimentos que a própria tela já filtra.
- **Substituição (11 palavras):** `"O papel do pedido, para pendurar no painel. Não é nota
  fiscal."`

## C2. "Esta forma exige pagamento antecipado."

- **Onde:** `components/PosPaymentWorkspace.vue`, `ctaBlock`.
- **Defeito:** D3 — antecipado em relação a quê? A tela está cobrando agora; o que o
  operador escolheu foi receber depois.
- **Substituição:** `"Pix e link só dão para cobrar agora, no balcão."`

## C3. "Tipo, valor e motivo. A loja confere e aplica."

- **Onde:** `components/PosPaymentWorkspace.vue`, descrição do diálogo de desconto.
- **Defeito:** D2 — "a loja confere e aplica" não nomeia ato nem ator: quem é a loja,
  confere quando, e o desconto vale antes ou depois disso? A frase é lida por quem está
  prestes a prometer um desconto em voz alta.
- **Substituição:** `"O desconto entra no total assim que você fechar esta caixa. Acima do
  limite, um gerente assina."`

---

# Parte D — miudezas com endereço

1. **`"{n} item(ns) a enviar"`** — `components/PosCartPanel.vue`, `aria-label` do badge de
   envio. O parêntese-plural é lido em voz alta pelo leitor de tela como "item parênteses
   ene esse". D3/D8. → `` `${n} ${n === 1 ? "item" : "itens"} a enviar` ``.
2. **`"Concluir"` como rodapé de quatro caixas diferentes** — `PosScheduleModal`,
   `PosCustomerModal`, o diálogo de desconto e o de divisão. D2: não nomeia ato nenhum, e
   em duas delas nada acontece além de fechar. → o rodapé repete a escolha:
   `"Usar este horário"`, `"Usar este cliente"`, `"Aplicar o desconto"`, `"Dividir"`.
3. **`"nenhuma ficha para {intervalo}."`** — `presentation/orderTickets.ts`, estado vazio
   que começa em minúscula e termina em ponto. → `"Nenhuma ficha para hoje."`
4. **`"{item_count} · {total_display}"`** — `components/PosTabPickerDialog.vue`, o número
   aparece **sem substantivo** ("12 · R$ 84,00"). D3. → `"12 itens · R$ 84,00"`.
5. **O item `"Tela do cliente"` do rail não faz nada em `pages/tickets.vue`** — ele emite
   `display`, e essa página não escuta o evento. Não é copy: é um rótulo que promete um ato
   que o código não liga. Vale um PR de uma linha (`@display` na página, ou o item some
   dali).
6. **`"Falha ao revisar checkout."` × `"Falha ao revisar venda."`** — a mesma operação,
   dois nomes, e um deles em inglês na tela. Entra no conserto de B4.
7. **"Encomenda" em dois eixos** — em `PosTabHeader` é o **modo** de atendimento (o oposto
   de Balcão); no subtítulo de `pages/tickets.vue` aparece como um **tipo de recebimento**,
   ao lado de entrega e retirada. D7b menor, que o vocabulário fechado resolve.

---

# Parte E — o que examinei e considerei BOM

Metade do valor está aqui: estas peças são o padrão, e várias delas são a resposta que os
achados acima pedem emprestada. **Não mexer.**

## E1. `ctaBlock` — toda recusa do servidor tem gêmea na tela, com o toque que resolve

`components/PosPaymentWorkspace.vue`. Onze portões, cada um com **frase curta**
(o que trava), **porquê miúdo** (o que se diz ao cliente) e **caminho de um toque**
(`"Escolher entrega ou retirada"`, `"Identificar cliente"`, `"Preencher"`,
`"Trocar forma de pagamento"`). Nenhum deles explica arquitetura; todos dizem o gesto.
`"O link precisa de um contato."` / `"Telefone ou e-mail — é por onde ele vai."` é a frase
mais bem escrita do app: doze palavras, uma causa, um destino. É o modelo que a Parte B4
manda copiar para as mensagens de falha.

## E2. `presentation/payment.ts` — o troco que só sai do dinheiro

`paymentChangeQ()` limita o troco à soma das linhas **em espécie**, e `nonCashExcessQ()`
existe para dizer que o excedente de cartão é erro de digitação, não troco. O comentário
carrega o caso real (uma venda de R$ 42,00 que mandava devolver R$ 4.958,00 da gaveta). O
aviso correspondente na tela — `"Cartão ou Pix R$ 30,00 acima do total."` /
`"Não há troco para forma digital; ajuste a linha."` — nomeia a forma, o valor e o gesto,
sem explicar o mecanismo. Modelo.

## E3. `presentation/kitchen.ts` — a única camada do app que já decidiu a grandeza

Conta **unidades**, e diz por escrito por quê. `kitchenHandoffNote()` distingue o que já
está na cozinha do que vai ao fechar; `kitchenBadge()` inventou o rótulo
`"{fired_qty} na cozinha · {qty} na conta"` para o caso em que o fogão faz mais do que a
conta cobra — um número honesto sobre comida saindo sem cobrança, que ninguém pediu e que
salva dinheiro. O achado A2 é um pedido para que o carrinho copie esta decisão.

## E4. `operator-kit/app/presentation/managerAuth.ts` — o ato assinado, em uma linha

Todo o texto da autorização mora num lugar só, com o par perigoso nomeado no cabeçalho
(destrave = *você assume o balcão*; autorização = *você continua quem era*). Os títulos são
o ato (`"Autorizar retirada da gaveta"`, `"Autorizar troco"`, `"Autorizar cancelamento"`) e
o motivo é uma frase de quatro palavras (`"Sai dinheiro da gaveta."`). O comentário registra
que a versão anterior explicava a política e foi cortada por prolixa — é o D8 aplicado com
a mão certa, cortando a explicação e mantendo o que decide. E o motivo do desconto vem do
servidor (`approval_reasons`), não de um chute da tela.

## E5. `presentation/saleResult.ts` — quando a tela **não** pode sumir sozinha

`autoAdvanceSeconds()` e `enterAdvances()` listam quatro situações em que o auto-avanço é
zero e o Enter não vale: troco a conferir, Pix aguardando, cobrança falhada e link de
pagamento na tela. Cada uma com a razão escrita em linguagem de balcão ("a tela não some
sozinha em cima do dinheiro"; "recuperar a URL exige ir ao gestor"). E o CTA muda de nome
conforme o estado: `"Nova venda mesmo assim"` quando há Pix pendente. O título (A1) é o
único elo que ainda discorda deste desenho — todo o resto dele está certo.

## E6. O diálogo da gaveta aberta — e o único rótulo destrutivo honesto do app

`components/PosDrawerLockDialog.vue`: `"Gaveta aberta"` / `"Feche a gaveta para
continuar."` / `"Aguardando a gaveta fechar"`. Três frases, nenhuma palavra sobrando, e
**não existe botão "Já fechei"** — a única saída normal é o sensor, o que é a decisão certa
e é dita pela ausência. O X do canto se chama `"Desistir desta venda"`, que é exatamente o
que ele faz. Só o botão de reticências destoa (B7).

## E7. D5 é zero, e o `"Tentar de novo"` já convergiu

- **Nenhum caso de "zero como código secreto"** em texto de tela. As duas ocorrências de
  `(0 = …)` no app (`types/pos.ts`, `components/PosPaymentWorkspace.vue`) são **docstring
  de prop** — prosa, que a regra manda deixar em paz. O PDV está limpo num defeito em que o
  Admin tem doze casos e o Marketing tem três.
- **Seis ocorrências de `"Tentar de novo"` e nenhuma de `"Tentar novamente"` nem de
  `"Verificar novamente"`.** A varredura de D7c que a régua pede (§3, D7) já está terminada
  nesta superfície. Se alguém escrever a trava V6, o PDV entra com dívida zero nesse item.

## E8. Peças que li inteiras e não têm achado

- **`presentation/terminalHealth.ts`, a linha da trava da gaveta:** `"armada — a próxima
  venda não começa com a gaveta aberta"` × `"sem medição: a trava não age neste balcão.
  Meça em Terminais do PDV, no gestor."` Distinguir "protegido" de "sem medição" é
  precisamente o dado que fecha a promessa, e o endereço do conserto vem junto. Só o
  substantivo "agente", nas linhas vizinhas, precisa cair (B1).
- **`presentation/customerDecision.ts`, os textos de conflito:** dizem o que foi alterado
  (`"Nenhum cadastro foi alterado."`), o que a escolha faz (`"O cadastro passa a usar o
  novo em tudo — mensagem, acompanhamento, próxima venda."`) e por quanto tempo dá para
  desfazer, com o endereço (`"Dá para desfazer até amanhã às 09:05 — com o gerente, em
  Clientes → Unificações de cadastro."`). É a camada mais bem escrita do PDV; o problema
  dela é o vocabulário (B6), não a redação.
- **`presentation/payment.ts`, `orderPaymentGuidance()`:** `"Sem cobrança agora: o
  entregador recebe e o Gestor registra."` / `"Cobra agora. Pix e link ficam pendentes até
  o provedor confirmar."` O comentário registra que a versão anterior explicava o mecanismo
  e o dono não entendeu. A correção pegou.
- **`presentation/payment.ts`, `splitHint()`:** `"Peça R$ 21,00 · pessoa 3 de 3"` — o
  comentário explica que o verbo entrou porque a frase virou a instrução lida de longe e
  dita em voz alta. `"R$ 21,00 · pessoa 3 de 3"` era etiqueta; `"Peça"` é o que fazer agora.
  É o D2 resolvido na direção certa.
- **`presentation/payment.ts`, `cashNoteLabel()` e `paymentDeadlineLabel()`:** `"R$ 50"`
  em vez de `"R$ 50,00"` porque não existe cédula quebrada; `"amanhã às 9h"` em vez de um
  carimbo ISO, porque é o que o operador fala ao telefone. Duas decisões pequenas e certas.
- **`pages/index.vue`, o bloqueio de cobrança incerta:** `"Resultado da cobrança não
  confirmado"` · `"Antes de cobrar novamente, confira em Últimas vendas ou no Gestor se o
  pedido e o pagamento foram criados."` · `"Já conferi · liberar tentativa"` · e a
  reconfirmação `"Conferi o pedido e o pagamento e sei se esta venda precisa ser tentada
  novamente."` É atrito desenhado no lugar certo, com o rótulo dizendo o que foi conferido
  em vez de "Confirmar".
- **`components/PosShortcutsHelp.vue`:** o dicionário inteiro descreve **efeitos**, não
  teclas (`"Mover o foco entre itens, sem mudar as marcações"`, `"Pedir remoção do item,
  com confirmação"`, `"Exato: a forma selecionada assume o restante"`). As duas divergências
  que ele expõe (F9 `"Enviar à cozinha"` × botão `"Enviar"`; F10 `"Transferir"` × botão
  `"Mover"`) são achados dos outros arquivos, não dele — a lista está certa e é o melhor
  inventário de vocabulário que o app tem.

---

## Onde eu procuraria o resto

1. **O vocabulário fechado do PDV não existe, e três achados dependem dele.** A §4.2 da
   régua manda fechá-lo no contrato da superfície *antes* da Onda 2, "senão a varredura
   troca um nome errado por outro". A3 (o verbo do ato), B3 (mover/transferir/dividir) e B6
   (cliente/cadastro, atender/vincular/associar) são decisões de dicionário, não de PR
   avulso. O molde é
   [`docs/reference/marketing-surface-contract.md`](../../reference/marketing-surface-contract.md);
   as camadas a fechar aqui são **objeto** (comanda · pedido · venda · encomenda),
   **atos** (cobrar · enviar · mover · liberar · fechar) e **grandezas** (item = unidade,
   comanda, pessoa, cobrança).
2. **As mensagens `detail` do Django.** Os 31 `"Falha ao …"` são *fallbacks*: o que a tela
   mostra na maioria das vezes é o `detail` do servidor
   (`shopman/shop/api_errors.py` e os comandos do PDV em `shopman/backstage/api/pos.py`).
   Reescrever só o lado Nuxt conserta metade da frase — foi o que aconteceu no Marketing
   com o `platformReadinessNote`.
3. **`components/PosCustomerModal.vue` (899 linhas) merece uma segunda leitura com a régua
   na mão.** Cobri os rótulos e os handlers, mas ele tem nove títulos condicionais e onze
   rótulos de ação gerados por composição (`receiptTitle`, `receiptActions`), e uma
   combinação rara pode produzir uma frase que nenhuma das minhas leituras montou.
4. **`components/PosReceiptSaveOffer.vue` não está montado em tela nenhuma.** As funções que
   ele consome (`receiptSaveOffers`, `receiptContactArmed`) são usadas direto pelo
   `PosPaymentWorkspace`. Ou o componente é dívida morta, ou uma oferta de salvar contato
   deixou de aparecer em algum caminho — vale descobrir qual antes de auditar a copy dele.
5. **A Onda 2 do PDV (D2, D3, D5, D7 tela a tela)** ainda não foi feita: esta varredura
   entrou fundo em D1 e D4, como a §6.2 manda, e colheu o que estava à vista dos outros.
