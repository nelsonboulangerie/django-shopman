# Varredura de copy — Storefront, a loja do cliente (18/09/2026)

- **Escopo:** `surfaces/storefront-nuxt/app/` — `pages/`, `components/`, `presentation/`,
  `composables/`, `utils/`; mais a copy que vem do servidor e chega à tela do cliente:
  `shopman/shop/omotenashi/copy.py`, `shopman/storefront/presentation/` e as mensagens de
  erro de `shopman/storefront/api/`. Lido no HEAD `76935e597`.
- **Natureza:** leitura e relatório. **Nenhuma linha de produto foi alterada.**
- **Régua:** [`docs/reference/omotenashi-copy.md`](../../reference/omotenashi-copy.md) — o
  teste de uma frase (§2) e os oito defeitos (§3). Os nomes D1–D8 são de lá.
- **Ordem:** a §6.3 põe o Storefront em **7º, e com régua própria**. O dono pediu esta
  superfície primeiro. A régua própria vale: **o vocabulário fechado de operador não se
  aplica aqui**, e calor é permitido. O teste de uma frase vale inteiro.

## A régua própria, dita antes de qualquer achado

Nenhum achado deste relatório pede que a loja fale como um app de operador. Onde a voz da
casa e o vocabulário de backstage discordam, a voz da casa ganha — e onde eu tive de
escolher, está dito na seção **"Onde a régua de operador e a voz da loja se chocaram"**,
no fim.

O que a concessão do dono **não** dispensa é a primeira lei da §4.2: **um nome por
conceito, qualquer que seja a porta de entrada.** Ter voz própria autoriza a loja a dizer
*aparelho* onde o operador diz *dispositivo*; não a dizer os dois na mesma frase. Boa
parte dos achados de D7 aqui é exatamente isso: não é a palavra escolhida que está errada,
é o fato de haver duas.

E um critério de dano traduzido para uma loja: **o que faz o cliente desistir, ou concluir
errado sobre o pedido dele**, antes do que é só feio. Por isso **recusa sem saída** —
principalmente a recusa que não chega a aparecer — está na Parte A junto com D1.

Onde há número, ele foi medido neste HEAD. Quando envelhecer, remeça.

## Placar

**37 fichas** nas partes A, B e C, contadas pelo defeito **principal** de cada uma (quase
todas carregam um segundo, dito na ficha), mais **45 miudezas** com endereço e substituição
na Parte D. Total: **82 achados**.

| Defeito | Fichas A+B+C |
|---|---:|
| D7 jargão e colisão de vocabulário | 15 |
| D3 frase que obriga a completar sentido | 11 |
| D1 rótulo que mente | 10 |
| D2 verbo genérico apaga o ato | 1 |
| D6 nota de rodapé do engenheiro | 1 |
| D4 grandezas somadas | 0 — ver E8 |
| D8 prolixo | 0 |
| D5 zero como código secreto | **0** — ver E9 |

Dois números explicam esta superfície melhor do que a tabela.

**D7 é o defeito dominante, e quase sempre na forma (c): o mesmo conceito com nomes
diferentes conforme a porta de entrada.** Aparelho × dispositivo, sacola × carrinho,
finalizar × revisar × enviar × seguir × confirmar, tentar de novo × tente novamente, e dez
redações de "fale conosco". Não é jargão vazando — é a loja tendo aprendido a falar duas
vezes. Faz sentido: nove telas escritas por frentes diferentes, sem um vocabulário fechado
(ver "Onde eu procuraria o resto", item 1).

**Sete achados são recusas que NÃO APARECEM.** A tela recusa, grava a mensagem numa
variável, e não mostra nada — ou a mensagem é gravada num ramo do template que aquele estado
não renderiza. É a forma mais cara do D1 numa loja, porque o cliente não tem como saber que
precisa tentar outra coisa: ele toca, nada acontece, e vai embora. Estão em A2, A11, B11 e
no item 2 de "Onde eu procuraria o resto".

## Onda 1 — aplicada em 18/09/2026

**Escopo da onda:** D1 (rótulo que mente), D3 (frase que obriga a completar sentido) e as
**sete recusas que não aparecem** — que entram aqui mesmo quando a ficha as classificou
noutro defeito, porque numa loja essa é a classe mais cara. Mais a uniformização de
**aparelho** (B3), que é a dívida que a §5.5 da régua nomeia como desta frente.

**Aplicado:** A1 · A2 · A3 (com a correção do dono, abaixo) · A4 (com ressalva de
contrato) · A5 · A6 · A9 · A11 · B5 · B8 · B9 · B10 · B11 · B14 · B15 · B16 · B17 · C2 ·
C5 · C6 · B3 · e as recusas silenciosas de `AddressLabelSheet.choose`,
`enderecos.setDefaultAddress` e `WhatsappVerifyPanel.copyMessage`.

**Fica para as ondas seguintes**, com motivo:

- **A7, A8, A10, A12, B1, B2, B4, B6, B7, B13, B18, B19, C1, C3, C4** — D7/D2/D6, que são
  a Onda 2 e a 3. A §4.2 manda **fechar o vocabulário do Storefront antes**, e sete destes
  dependem dele ("Onde eu procuraria o resto", item 1); aplicá-los agora trocaria um nome
  errado por outro.
- **As 45 miudezas da Parte D** — a maioria é D1 ou D3 e entra na Onda 1b. Ficaram fora
  desta por volume: são 45 endereços em mais de 20 arquivos, e misturá-las com as fichas
  faria um diff que ninguém revisa de verdade.
- **A6, a metade de produto** — ligar `usePasskey().signIn()` em `/entrar` é outra frente.
  Aqui a tela só parou de prometer a porta que não existe.
- **A8, a decisão de esconder o ambiente de teste de cliente real** — é decisão de produto,
  não de redação, e está dita na própria ficha.

**Três lugares onde este relatório estava errado, e foram corrigidos junto:**

1. **A3 descrevia o defeito errado.** Ver a ficha: não há promessa quebrada, e a pergunta
   de produto do fim não existia.
2. **A1 dizia que a porta da recompra tem "aceite explícito".** Ela tem as chaves
   (`REORDER_CONFLICT_REPLACE_HELP` e `_ACK_LABEL`) **no registro e não na tela**: nenhum
   dos três diálogos de conflito (`pedido/[ref]`, `conta/index`, `conta/pedidos`) as
   renderizava. A onda fez as duas portas dizerem a consequência e pedirem o aceite — a da
   oferta, que não tinha nada, e a da recompra, que tinha a frase escrita e invisível.
3. **A substituição escrita para A4 colidia com um contrato P1.** O
   `COPY-WAITLIST-001` ([storefront-surface-parity-contract](../../reference/storefront-surface-parity-contract.md))
   proíbe transformar a data do lote em disponibilidade, e a varredura de
   `test_remote_multisurface_contract.py` bloqueia justamente a expressão que o relatório
   propunha. O achado continua válido — a data existe, escolhe o ramo e era descartada —,
   então a frase entrou dizendo a data como **previsão** e mantendo "fila de espera" como
   termo canônico: `"Sua reserva está na fila de espera da fornada prevista para {when}.
   Avisamos quando sair."`

**E uma que já estava resolvida antes da varredura:** **B12** pede que o bloqueio de pedido
mínimo diga quanto falta. `shopman/storefront/presentation/cart.py` já montava
`f"Faltam {…} para o pedido mínimo."` no HEAD `76935e597` — o mesmo que o relatório mediu.
A chave `CART_CHECKOUT_BLOCK_MIN_ORDER` é o fallback de quando **não há** número a dizer, e
aí a frase genérica é honesta. Nada a fazer.

A ordem é a do dano (§6.1): **Parte A** faz o cliente desistir ou concluir errado sobre o
pedido; **Parte B** faz parar para pensar; **Parte C** é só feio; **Parte D** são miudezas
com endereço. A **Parte E** diz o que examinei e considerei bom — é metade do resultado.

---

# Parte A — faz o cliente desistir, ou concluir errado sobre o pedido

## A1. "Começar uma sacola nova" apaga a sacola — e a mesma casa já escreveu a versão certa

- **Onde:** `pages/oferta/[ref].vue`, bloco `v-else-if="conflict"`:
  `"Você já tem itens na sacola"` · `"Podemos somar a oferta ao que já está lá, ou começar
  uma sacola nova conosco."` · botões `"Somar à minha sacola"` e `"Começar uma sacola
  nova"`. O segundo chama `claim('replace')`.
- **Defeito:** D1.
- **Por que dói:** `mode == "replace"` executa `CartService.clear_items(request)`
  (`shopman/storefront/api/surface.py`). "Começar uma sacola nova" admite as duas leituras
  do §2: *abre uma segunda sacola e a minha continua lá* × *apaga a minha*. O sistema faz a
  segunda, e não se desfaz. Quem chega aqui veio de um link de campanha no WhatsApp, com uma
  sacola que montou à mão. O comentário do próprio arquivo sabe do risco (*"Trocar sem
  perguntar apagaria uma sacola que o cliente montou, e isso não se desfaz"*) — a pergunta
  foi criada, e o rótulo escondeu a resposta.
  **O agravante é a comparação interna.** O mesmo `clear_items`, alcançado pela outra porta
  (repetir pedido), tem copy exemplar no registro: `REORDER_CONFLICT_REPLACE_LABEL`
  (`"Substituir sacola"`), `REORDER_CONFLICT_REPLACE_HELP` (`"Os itens atuais serão
  removidos antes de recriar o pedido anterior."`), um **aceite explícito**
  (`REORDER_CONFLICT_REPLACE_ACK_LABEL`: `"Entendo que os itens atuais serão removidos."`)
  e um cancelar que diz o estado (`"Manter minha sacola"`).
  ⛔ **Correção de 18/09 (Onda 1): a porta da recompra tinha essas duas frases no registro
  e NÃO as renderizava.** Os três diálogos de conflito (`pedido/[ref]/index.vue`,
  `conta/index.vue`, `conta/pedidos.vue`) mostravam só título, mensagem, cancelar e os
  rótulos das ações — `replace_help` e `replace_ack_label` eram chaves mortas na tela. O
  ato destrutivo, portanto, não avisava por porta nenhuma; a comparação continua sendo o
  argumento, mas ela era entre uma porta muda e um registro mudo.
- **Substituição:** as duas portas passam a dizer a mesma coisa.
  - descrição → `"Somar mantém o que você já escolheu. Trocar apaga os itens de agora e
    deixa só os da oferta."`
  - botão 2 → `"Trocar: deixar só a oferta"`
  - aceite explícito, com a frase do `REORDER_CONFLICT_REPLACE_ACK_LABEL`, travando o botão
    até ser marcado — nas duas portas.
- **Aplicado:** sim (Onda 1), nos quatro arquivos: `pages/oferta/[ref].vue`,
  `pages/pedido/[ref]/index.vue`, `pages/conta/index.vue` e `pages/conta/pedidos.vue`.

## A2. O endereço que a busca não achou responde com silêncio

- **Onde:** `components/AddressPicker.vue`. Três caminhos:
  1. `runSearch` → `suggestions.value = results` / `searchOpen.value = results.length > 0`.
     Com `results` vazio, **nenhuma string**.
  2. `acceptSuggestion`, `catch` → `saveIssue.value = 'Não foi possível carregar este
     endereço. Tente outra busca.'`
  3. `locateMe`, `catch` → `geoIssue.value = errorDetail(e, 'Não foi possível resolver sua
     localização.')`.
- **Defeito:** D1 (o caso 2, na forma que a régua chama de pior: a pessoa acaba de agir
  achando que agiu) e D2 (o caso 3).
- **Por que dói:** no **caso 1**, o cliente digita os 8 dígitos do CEP, o Places não devolve
  nada e o ViaCEP responde `{"erro": true}`: a lista fecha e a tela fica idêntica. Ele
  conclui que a loja não atende o CEP dele — que é a conclusão mais cara possível — e vai
  embora. No **caso 2**, a mensagem existe e **nunca é renderizada**: o único
  `<UiAlert v-if="saveIssue">` vive no ramo `<template v-else>` (modo `form`), e como
  `applyPartial` não chegou a rodar, `mode` continua `'search'`. Frase escrita, gravada,
  invisível. No **caso 3**, uma frase serve para permissão negada, timeout e GPS ausente —
  três causas com três gestos diferentes —, e *"resolver sua localização"* não é ato nenhum:
  resolver o quê, e quem resolve?
- **Substituição:**
  - busca vazia por CEP → `"Não achamos esse CEP. Confira os números — ou toque em
    'Preencher manualmente' e escreva o endereço."`
  - busca vazia por texto → `"Nenhum endereço com esse nome. Tente a rua com o número, ou o
    CEP. Se preferir, preencha manualmente."`
  - falha ao abrir a sugestão → renderizar no card de busca, ao lado do `geoIssue` que já
    aparece ali: `"Não deu para abrir este endereço. Escolha outro resultado da lista, ou
    toque em 'Preencher manualmente'."`
  - localização, ramificando por `error.code`:
    `PERMISSION_DENIED` → `"Você não liberou a localização para a loja. Dá para liberar nas
    configurações do navegador — ou buscar pela rua ou pelo CEP aqui em cima."` ·
    `TIMEOUT` → `"Demorou demais para achar você. Tente de novo, ou busque pela rua ou pelo
    CEP aqui em cima."` · resto → `"Não conseguimos achar onde você está. Busque pela rua ou
    pelo CEP aqui em cima."`
  - ⚠️ o mesmo desenho se repete em `'Geolocalização não está disponível neste aparelho.'`
    (D7a: `Geolocalização` é o nome da API) — e a frase acusa o telefone quando o culpado é
    o navegador ou o contexto inseguro: `"Este navegador não informa sua localização. Busque
    pela rua ou pelo CEP aqui em cima."`

## A3. O interruptor do checkout não diz o que governa

> ⛔ **Corrigido em 18/09/2026, na aplicação da Onda 1.** A versão original desta ficha
> descrevia o defeito como promessa quebrada — "desligar não impede o endereço de ser
> salvo" — e propunha dar ao endereço uma recusa própria. **O dono refutou:** não há
> promessa quebrada. O endereço novo sempre vai para a agenda do cliente, e **tem que
> ir** — ninguém redigita CEP a cada pedido. O interruptor governa os **padrões**: qual
> endereço vem escolhido, a forma de pagamento e o horário. São coisas distintas, e o
> defeito é só de texto. A pergunta de produto que o relatório fazia no fim **não existe**;
> ela foi respondida e está riscada lá embaixo.

- **Onde:** `pages/finalizar.vue`, o toggle `data-checkout-save-default`:
  `"Salvar para a próxima vez"` · `"Guardamos suas escolhas para agilizar seu próximo
  pedido."`
- **Defeito:** D1.
- **Por que dói:** o título fica logo abaixo do campo de endereço e se lê como "salvar
  **este endereço**" — que não é o que a chave faz. "Suas escolhas" não nomeia nenhuma
  das três coisas que ela de fato governa, então quem desliga não sabe o que desligou.
- **Substituição** (decidida pelo dono, e é só isto — sem frase de reforço):
  - título → `"Lembrar destas escolhas"`
  - linha de apoio → `"Endereço, pagamento e horário."`
- **Aplicado:** sim (Onda 1). O comentário do `save_as_default` em
  `shopman/storefront/api/serializers.py` e o de `utils/checkoutPayload.ts` foram
  reescritos junto — citavam o rótulo antigo e descreviam mal o que a chave cobre.

## A4. A espera pela fornada joga fora a data que o sistema tem na mão

- **Onde:** `shopman/storefront/presentation/order_tracking.py`, `_waitlist_message()`:
  o ramo `if wait_display:` resolve `TRACKING_PROMISE_WAITLIST_MESSAGE` e faz
  `.replace("{when}", wait_display)` sobre a string
  `"Sua reserva está na fila de espera. Avisamos quando estiver pronto."` — **que não tem
  `{when}`**. O mesmo em `_paid_fulfillment_wait_message()` com
  `TRACKING_PROMISE_WAITLIST_MESSAGE_PAID`. Os pares `_NO_DATE` são byte a byte idênticos
  aos com data.
- **Defeito:** D3 (terceira forma: lembrar de algo que a tela não mostra).
- **Por que dói:** o cliente comprou um item que espera a fornada de um dia conhecido. Na
  **sacola**, minutos antes, a loja disse a data: `CART_WAITLIST_PLANNED_DATE`
  (`"Previsto para {date}"`) com `{date}` virando "hoje"/"amanhã"/"sábado, 19/07". Depois
  que ele paga, a mesma loja passa a dizer `"Avisamos quando estiver pronto."` e para de
  dizer quando. O dado existe, o ramo do código **só é escolhido porque ele existe**, e a
  frase o descarta. A pessoa que pagou sabe menos do que a que só olhou.
  A prova de que a casa já concorda comigo está no mecanismo irmão: o bloco WP-P2E
  (`waitlist_state === 'fermata'`) mostra `"Fornada prevista para {display}."` na mesma tela.
  São dois caminhos (`fulfillment_wait_kind == "planned_batch"` × `waitlist_state`), e só um
  deles fala a data.
- **Substituição:** a mensagem com data carrega a data, e a sem data diz o que sabe.
  ⛔ **Correção de 18/09 (Onda 1):** a frase escrita aqui na primeira versão —
  *"na fila da fornada de {when}"* — colide com o **COPY-WAITLIST-001**
  ([storefront-surface-parity-contract](../../reference/storefront-surface-parity-contract.md)),
  um contrato P1 que proíbe transformar a data do lote em disponibilidade (o hold planejado
  não está materializado) e cuja varredura em `test_remote_multisurface_contract.py` bloqueia
  exatamente aquela expressão. O achado continua de pé; a frase mudou para dizer a data como
  **previsão**, mantendo "fila de espera" como termo canônico.
  - `TRACKING_PROMISE_WAITLIST_MESSAGE` → `"Sua reserva está na fila de espera da fornada
    prevista para {when}. Avisamos quando sair."`
  - `TRACKING_PROMISE_WAITLIST_MESSAGE_PAID` → `"Pagamento confirmado. Sua reserva está na
    fila de espera da fornada prevista para {when}. Avisamos quando sair."`
  - os dois `_NO_DATE` ficam como estão — aí a frase é verdadeira.
  - ⚠️ enquanto a substituição não entra, o `.replace("{when}", …)` nas duas funções é
    código morto que **parece** cobertura. Vale apagá-lo junto, ou alguém vai ler o
    `replace` e concluir que a data já aparece.

## A5. A loja fechada convida a montar o pedido sem dizer que está fechada

- **Onde:** `pages/index.vue`, prop `closed-cta-label="Montar pedido"`, consumida em
  `components/HomeHeroThing.vue`, computed `slides`:
  `const menuLabel = (!props.statusOpen && props.closedCtaLabel) || titleOf(copy.menu_cta, 'Ver cardápio')`.
- **Defeito:** D1 e a terceira falha do §2.
- **Por que dói:** este rótulo **só existe no estado fechado** — e nada no hero diz que a
  loja está fechada. O `statusLabel` está na sessão e é renderizado, mas lá embaixo, como
  badge ao lado de `how_store_heading`, dentro do card "visite a loja". O topo da página, que
  é o que a pessoa lê, convida a montar pedido. Ela monta a sacola inteira e descobre no
  checkout — que é onde o investimento dela já está feito e o abandono custa mais.
  ⚠️ Há gêmeo no cabeçalho: `components/ShopHeader.vue`, `{{ statusLabel || 'Confira nossos
  horários' }}` — no fallback, a única faixa da loja que diz se está aberto vira uma
  instrução sem destino (o texto não é link; o horário está a três toques). E
  `components/ShopFooter.vue` repete: `"Consulte os horários de atendimento."` no lugar
  exato onde o horário deveria estar.
- **Substituição:**
  - rótulo → `"Montar pedido para depois"`
  - eyebrow no slide quando `!statusOpen` → `"{statusLabel}. Você monta agora e finaliza
    quando abrirmos."`
  - a faixa do header vira botão que abre a gaveta rolada até os horários, com o texto
    `"Ver horários"`.
  - rodapé sem horários → `"Horário não informado. Pergunte no WhatsApp."`, com o link ao
    lado.

## A6. A loja promete entrar com a chave do aparelho, e a porta não existe

- **Onde:** `pages/conta/seguranca.vue`, `UiEmpty` do Acesso rápido: `"Ativando, na próxima
  visita você entra num toque — e continua podendo entrar pelo WhatsApp quando quiser."`;
  cabeçalho da seção: `"Entrar com uma chave deste aparelho, sem código e sem esperar
  mensagem."`
- **Defeito:** D1, no grau máximo.
- **Por que dói:** `usePasskey().signIn()` **não é chamado em lugar nenhum**. Medido: o
  composable só é consumido em `seguranca.vue`, e só por `enroll`, `passkeyIsQuick` e
  `passkeyBlockedReason`. `pages/entrar.vue` oferece WhatsApp e SMS, nunca a chave. A frase
  `'Não reconhecemos esta chave neste aparelho.'`, dentro de `signIn`, é copy que nunca foi
  lida por ninguém. O cliente ativa uma credencial que vale para sempre, fecha o app, volta,
  e não encontra o botão que a tela prometeu. É nível 1 da §6.1 — ele decidiu com base numa
  frase falsa.
- **Substituição:** duas saídas, e a escolha é de produto, não de redação.
  - **se a porta vai existir:** `pages/entrar.vue` ganha `"Entrar com a chave deste
    aparelho"`, e a copy atual passa a ser verdade.
  - **enquanto não existir:** `"Ativando, esta loja passa a reconhecer a chave deste
    aparelho."` — e o cabeçalho perde a promessa de entrada:
    `"Guardar uma chave deste aparelho para entrar sem código."`
  - Isto é dívida com endereço, não opinião: ou o botão nasce, ou a frase encolhe.

## A7. "Pedido incompleto." — numa loja onde pedido é a compra

- **Onde:** `shopman/storefront/api/auth.py`, duas ocorrências no fluxo de passkey:
  `Response({"detail": "Pedido incompleto.", "field": "credential"}, status=400)`.
- **Defeito:** D7b (colisão de vocabulário dentro do mesmo app).
- **Por que dói:** aqui "pedido" é a *requisição HTTP*. Na loja, **pedido é o objeto central
  do negócio** — tem página, tem acompanhamento, tem número. O cliente que está ativando o
  acesso rápido lê "Pedido incompleto." e vai conferir o pedido de pão. É exatamente o caso
  da `"faixa"` que a régua usa como exemplo: uma palavra legítima em todo o resto do app,
  que ninguém desconfia porque acabou de aprendê-la ali. É a única colisão desse tipo em
  código de produção do Storefront — as outras ocorrências estão em teste.
- **Substituição:** `"Faltou a credencial do aparelho. Toque de novo em Ativar."`
  ⚠️ Gêmea de arquitetura na mesma vizinhança: `"Recurso indisponível."` (503, duas
  ocorrências) — `Recurso` é nome de sistema e a frase não oferece gesto. Vira
  `"O acesso rápido está fora do ar agora. Você continua entrando pelo WhatsApp."`

## A8. O ambiente de teste conversa com o cliente, e diz "gateway", "Efí" e "captura simulada"

- **Onde:** quatro lugares.
  - `pages/finalizar.vue`, `pixProviderTestMessage`: `'Ambiente de testes: a Efí simula a
    confirmação de Pix de até R$ 10,00. Para continuar, troque a forma de pagamento ou
    ajuste os itens do pedido.'`, sob o título `'Pix indisponível para este total'` /
    `'Pix em período de testes'`, com a linha `'Este pedido está dentro do limite
    temporário.'`
  - `pages/finalizar.vue`, bloco dos cartões de teste: `'Nenhuma cobrança real acontece
    aqui. Use um destes números no {{ checkout.card_provider || 'gateway' }}.'`
  - `components/PaymentBlock.vue`: `'Neste ambiente o cartão não abre a página do gateway.
    Use a captura simulada abaixo.'` e `'Pagamento de teste'` / `'Use este botão para
    confirmar o pagamento neste ambiente de teste.'`
  - `shop/omotenashi/copy.py`, `TRACKING_MOCK_PAYMENT_SUCCESS_MESSAGE`: `"Atualizamos o
    pedido com o estado financeiro simulado."`, e `TRACKING_ACTION_MOCK_CONFIRM_PAYMENT`:
    `"Capturar pagamento teste"`.
- **Defeito:** D7a, e D1 na segunda forma (`"a captura simulada abaixo"` nomeia um controle
  cujo rótulo é `"Simular pagamento"`).
- **Por que dói:** **isto está no ar no alpha** — os fallbacks Tier 1 estão ligados, com Pix
  mock. O cliente que compra pão lê o nome do provedor de pagamento, a palavra `gateway`, a
  expressão `estado financeiro simulado` e uma instrução que aponta para um botão com outro
  nome. `"Pix em período de testes"` ainda admite duas leituras, e a errada é a que fica: *a
  loja está experimentando Pix* — quem lê isso não volta a escolher Pix. Os dois blocos
  também podem coexistir (`abreCheckout && checkout_url` ao lado de `podeSimular`), e aí a
  mesma tela diz `"Pagamento seguro"` em cima e `"Pagamento de teste"` embaixo.
- **Substituição:** o limite vira um fato da loja, sem o nome do provedor nem a palavra
  "teste" como qualidade do Pix.
  - título excedido → `"Pix não cobre este valor agora"`; dentro do limite → **sem faixa
    nenhuma** (dizer que está tudo certo é ruído).
  - mensagem → `"Por enquanto o Pix desta loja vai até R$ 10,00. Escolha outra forma de
    pagamento, ou ajuste os itens."` (os dois botões que já existem ficam)
  - cartões de teste → `"Nenhuma cobrança real acontece aqui."` e a lista, sem a frase que
    cita o provedor; se o provedor precisar aparecer, `checkout.card_provider` sem fallback
    (o bloco só existe com chave de teste, então ele sempre existe).
  - `PaymentBlock` → `"Neste ambiente o cartão não abre a página do banco. Use o botão
    Simular pagamento, abaixo."`
  - `TRACKING_MOCK_PAYMENT_SUCCESS_MESSAGE` → `"Marcamos o pedido como pago. Nenhum dinheiro
    saiu da sua conta."`
  - ⚠️ o conserto de redação **não substitui** a decisão de esconder isso de clientes reais.
    Enquanto o alpha atender gente de verdade, a melhor copy do mundo continua dizendo a
    quem comprou pão que a padaria está em teste.

## A9. "Confirmação em consulta. Mantenha esta tentativa." — não há tentativa na tela

- **Onde:** `pages/finalizar.vue`, `submitCheckout`, ramo de 5xx/rede:
  `serverError.value = 'A confirmação ainda está em consulta. Mantenha esta tentativa.'`,
  sob o título `'Confirmação em consulta'`.
- **Defeito:** D1 na segunda forma (a instrução nomeia um controle que não existe) e D7a.
- **Por que dói:** é o pior instante possível do fluxo — a pessoa apertou o botão que fecha
  o pedido e não sabe se o pedido existe. E a única instrução que a loja dá é sobre um
  objeto (`tentativa` = `attemptKey`, a chave de idempotência) que ela nunca viu e não pode
  manter nem largar. `"em consulta"` é vocabulário de conciliação, não de padaria. O cliente
  faz a única coisa que consegue: aperta de novo, ou vai embora achando que perdeu o
  dinheiro.
- **Substituição:** o que aconteceu, o que **não** aconteceu, e o gesto.
  `"Não sabemos ainda se o pedido entrou."` ·
  `"Estamos conferindo com o sistema. Não envie de novo: se o pedido entrou, você seria
  cobrado duas vezes. Esta tela se resolve sozinha em instantes."` ·
  e o botão que hoje não existe: `"Ver meus pedidos"` (para `/conta/pedidos`).
  ⚠️ Gêmea, no mesmo arquivo: `useSonner.info('Pedido confirmado. Estamos tentando salvar
  suas escolhas para a próxima vez.')`, repetida no acompanhamento como faixa **warning**:
  `"Pedido confirmado. Estamos tentando salvar suas escolhas para a próxima vez. Você não
  precisa repetir o pedido."` É D6 puro — um aviso amarelo, em cima do pedido que deu certo,
  sobre uma retentativa interna que o cliente não pode influenciar, começando pela defesa
  contra um risco que ele não sabia que existia. **Corte inteiro.** Se o produto insiste em
  dizer algo, é uma linha discreta e sem alarme: `"Suas escolhas serão guardadas em
  instantes."`

## A10. A tela de erro do checkout não diz nada, e diz numa palavra que a loja não usa

- **Onde:** `pages/finalizar.vue`, `<UiAlert v-else-if="error">`:
  `<UiAlertTitle>Checkout indisponível</UiAlertTitle>` e, dentro da
  `<UiAlertDescription>`, **só um botão** `"Atualizar"`. E, do lado do servidor,
  `CART_CHECKOUT_BLOCK_CHANNEL`: `"Checkout indisponível para este canal."`
- **Defeito:** D7a e D3.
- **Por que dói:** duas coisas, e a segunda é pior. (a) **`Checkout` e `canal` não são
  palavras da loja.** Na mesma página, o `<h1>` diz `"Finalize seu pedido"` e a migalha diz
  `"Finalizar pedido"`; `canal` é o `ChannelConfig`, um objeto da arquitetura que o cliente
  não tem como conhecer. (b) **a descrição não tem frase.** Só um botão. O cliente não sabe
  se a sacola sobreviveu, se o problema é dele, ou se vale a pena voltar. Compare com a
  irmã, na `pages/sacola.vue`, que acerta tudo: `"Sua sacola não quis carregar agora"` /
  `"Seus itens estão guardados. Tente de novo em instantes."` / `"Tentar de novo"`. Duas
  telas consecutivas, o mesmo evento, e só uma trata o cliente como gente.
- **Substituição:**
  - título → `"Não conseguimos abrir o seu pedido agora"`
  - descrição → `"Seus itens estão guardados na sacola. Tente de novo em instantes."`
  - botão → `"Tentar de novo"` (ver B1)
  - `CART_CHECKOUT_BLOCK_CHANNEL` → `"Não dá para finalizar por aqui agora. Fale no WhatsApp
    que a gente fecha o pedido com você."`

## A11. Esgotado sem substituto: "Veja boas alternativas" e não há nenhuma

- **Onde:** `components/SubstituteSheet.vue`, computeds `title` e `description`:
  `"Ficou indisponível enquanto você escolhia."` · `"{itemName} está indisponível agora. Veja
  boas alternativas."`; e o único botão do estado, `"Tentar de novo"`.
- **Defeito:** D1 e recusa sem saída.
- **Por que dói:** com `hasAvailable === false`, `substitutes.length === 0` e
  `isNotifiable === false`, o `v-if="substitutes.length"` não renderiza nada — a frase manda
  ver um bloco que a tela não tem. O único gesto oferecido, `retryLastMutation()`, refaz a
  mesma mutação no mesmo item esgotado: ele vai falhar de novo, pelo mesmo motivo. É o beco
  fechado com uma placa apontando para a parede.
  Mesmo desenho na página do produto: `pages/produto/[sku].vue`,
  `:add-label="product.can_add_to_cart ? 'Adicionar' : 'Indisponível'"` mais a badge
  `"Indisponível"` sobre a foto mais `"Este item não está disponível agora."` — a mesma
  palavra três vezes e zero gestos (repetido em `components/ProductTile.vue`).
- **Substituição:** a descrição segue o que a tela de fato tem, e o botão vira saída.
  - sem substituto e sem aviso → `"{itemName} acabou agora, e não temos substituto para
    oferecer hoje."` + botão `"Ver o cardápio de hoje"` (para `/menu`).
  - na PDP, quando não dá comprar nem avisar: o botão morto sai e entra um link real
    `"Ver itens parecidos"` (`/menu?secao={breadcrumb_category}`); a linha vira `"Não está no
    cardápio de hoje."`; a badge da foto diz o estado uma vez, e basta.

## A12. O aviso de reposição tem quatro nomes, e nenhum diz por onde o aviso chega

- **Onde:** `components/StockNotifyButton.vue`, quatro rótulos para **um** gesto:
  `"Me avise"` (variante `pill` — é o que aparece no cardápio, via `ProductListItem.vue`),
  `"Me avise sempre"` (variante larga — PDP e tiles da home), `"Ativar aviso"` (submit do
  sheet), `"Tentar ativar aviso"` / `"Tentar de novo"` (retomada). Contra
  `SOLDOUT_NOTIFY_CTA` no registro: `"Me avise quando disponível"` — o quinto.
- **Defeito:** D7c e D3.
- **Por que dói:** quem aprendeu `"Me avise"` no cardápio encontra `"Me avise sempre"` na
  página do produto e conclui, corretamente pela leitura, que são coisas diferentes. E
  `sempre` é o único lugar onde a recorrência aparece — sem dizer *sempre o quê*. Pior:
  **nenhum dos cinco diz que o aviso chega por WhatsApp.** Essa informação existe só no
  `aria-label` (`"Ativar avisos recorrentes quando {name} voltar"`) e na descrição do sheet;
  quem enxerga não lê o `aria-label`. O cliente assina um canal que não escolheu.
- **Substituição:** um rótulo em todas as portas, e o canal na linha visível.
  - rótulo, nas cinco → `"Avisar quando voltar"`
  - linha sob o botão / descrição do sheet → `"Avisamos no WhatsApp toda vez que voltar, até
    você cancelar."`
  - ⚠️ isto é a primeira linha de um **vocabulário fechado do Storefront**, que a §4.2 manda
    escrever antes da Onda 2. Ver "Onde eu procuraria o resto".

---

# Parte B — faz o cliente parar para pensar

## B1. "Tentar de novo" (12) × "Tente novamente" (7) × "Tentar novamente" (1) × "Verificar novamente" (1)

- **Onde:** contagem medida neste HEAD **em `surfaces/storefront-nuxt/app/`**: `"Tentar de
  novo"` 12 · `"Tente novamente"` 7 · `"Tentar novamente"` 1 · `"Verificar novamente"` 1.
  Os fora-da-curva com endereço: `pages/index.vue` (`"Tentar novamente"` — o único **rótulo
  de botão** divergente da loja inteira), `utils/operationalCopy.ts` (`'Tente novamente'` e
  `'Use Verificar novamente antes de enviar outra vez.'`),
  `components/WhatsappVerifyPanel.vue` (`"Tente novamente ou use o SMS."` **imediatamente
  acima** do botão `"Tentar de novo"`), e `pages/conta/seguranca.vue` (três frases).
  Some-se o lado do servidor, fora dessa contagem: `TRACKING_RETRY_CTA` e
  `TRACKING_PROMISE_RETRY_ACTION`, os dois `"Tentar novamente"`.
- **Defeito:** D7c.
- **Por que dói:** é o caso que a própria régua já mediu e mandou terminar (§3, D7:
  *"Não é uma escolha a fazer; é uma varredura a terminar"*). A casa convergiu em `"Tentar
  de novo"`; o Storefront tem **9 resíduos no app e 2 no registro**, e um deles está a três
  centímetros do rótulo certo.
- **Substituição:** `"Tentar de novo"` no rótulo, `"Tente de novo"` na frase, nos onze.
  `"Verificar novamente"` some junto com o dicionário que o abriga (B2).

## B2. `utils/operationalCopy.ts` — 30 strings de tela, zero consumidores, e o vocabulário errado

- **Onde:** `utils/operationalCopy.ts`. Medido: `grep -rn "operationalCopy\|OPERATIONAL_COPY"
  surfaces/` **não devolve nenhum consumidor** fora do próprio arquivo.
- **Defeito:** D7a e D7c concentrados, mais D6.
- **Por que dói:** o arquivo não está na tela hoje — está esperando. Ele se declara contrato
  (`OPERATIONAL_COPY_SOURCE`, `contractIds: ['COPY-SOURCE-001','COPY-FACT-001']`, com
  referência a um documento), o que faz dele o primeiro lugar onde um agente futuro vai
  buscar a frase pronta. E o que ele entrega é: `'Não foi possível carregar o checkout'` e
  `'Não foi possível carregar o carrinho'` (**carrinho**, numa loja cuja rota é `/sacola`,
  cujo `<h1>` é `"Sua sacola"` e cuja migalha diz "Sacola"); `'Estoque, pedido mínimo,
  agenda, pagamento e dados do cliente serão validados no envio.'` (D6 exemplar — a loja
  falando do próprio cliente em terceira pessoa, e listando as validações internas antes de
  ele apertar o botão); `'Se precisarmos ajustar algo, mostramos a próxima ação antes de
  continuar.'` (D6 + `próxima ação` é jargão de UX); `'Seu pedido já está em processamento.
  Use Verificar novamente antes de enviar outra vez.'` e `'O pedido continua preservado. Use
  Atualizar status ou acompanhe pela página do pedido.'` — **dois controles nomeados que não
  existem em tela nenhuma** (D1, segunda forma). A auditoria adversarial de 01/09 já o tinha
  marcado como dicionário morto; ele continua aqui, intacto, e agora com um rótulo de
  contrato em cima.
- **Substituição:** **apagar o arquivo.** O que dele é bom já existe vivo e melhor:
  `presentation/orderAccess.ts` para as falhas de acesso, `pages/sacola.vue` para a falha de
  carregamento, `CART_CHECKOUT_BLOCK_*` no registro para os bloqueios. Se alguma frase
  precisar sobreviver, ela nasce no registro omotenashi, que é onde o operador reescreve — e
  não num `const` de TypeScript que ninguém importa.
  ⚠️ `'carrinho'` também vive fora dele, e pior, no par
  `composables/useReorder.ts`: `'Esta tentativa já foi processada. Sua sacola está
  atualizada.'` × `'Itens adicionados ao carrinho.'` — **duas palavras para o mesmo objeto
  em duas linhas do mesmo arquivo**. E `composables/useCartState.ts`: `'Não foi possível
  atualizar o carrinho.'` Nas três, `sacola`.

## B3. "Salvar este aparelho?" → "Dispositivo salvo por 30 dias."

- **Onde:** um gesto, dois substantivos, três segundos de distância. No registro:
  `DEVICE_TRUST_PROMPT` (`"Salvar este aparelho?"` / `"Use só em um aparelho seu. Por 30
  dias, você entra sem código."`) → `DEVICE_TRUST_CTA` (`"Salvar por 30 dias"`) →
  `DEVICE_TRUST_SAVED` (`"Dispositivo salvo por 30 dias."`). Na tela, o mesmo:
  `pages/conta/seguranca.vue` diz `"Ativar neste aparelho"`, `"Não disponível neste
  aparelho"`, `"Entrar com uma chave deste aparelho…"` — e, **na mesma página**,
  `"Dispositivos confiáveis"`, `"dispositivo autorizado"`, `"Este dispositivo"`,
  `"Dispositivo removido."` A frase que fecha o argumento sozinha, no `passkeyBlocked` do
  mesmo arquivo: `'Este aparelho não oferece acesso rápido pela chave do próprio
  dispositivo.'` — **os dois nomes, para o mesmo objeto, dentro de uma frase.**
- **Defeito:** D7c.
- **Por que dói:** a concessão do dono isenta o Storefront de ser **obrigado** a dizer
  "dispositivo"; ela não autoriza dizer os dois. Quem aprendeu "aparelho" no login não
  reconhece "Dispositivos confiáveis" na conta e conclui que são duas listas diferentes — o
  que é pior do que não entender, porque ele para de procurar. E é a tela onde a pessoa
  decide o que confia com a própria conta.
- **Substituição:** **`aparelho`**, em toda a superfície do cliente — é a palavra que a voz
  da casa já escolheu no texto em segunda pessoa, e a que o dono isentou. Varrer as
  ocorrências de `dispositivo` em `presentation/account.ts`, `conta/seguranca.vue`,
  `conta/index.vue` e nas chaves `DEVICE_*` / `ACCOUNT_TRUSTED_DEVICES_MESSAGE` /
  `ACCOUNT_DELETE_WARNING` do registro.
  - `"Dispositivos confiáveis"` → `"Aparelhos confiáveis"`
  - `"Dispositivo salvo por 30 dias."` → `"Aparelho salvo por 30 dias."`
  - `'Este aparelho não oferece acesso rápido pela chave do próprio dispositivo.'` →
    `"Este aparelho não guarda chave de acesso rápido."`
  - ⚠️ `usePasskey.deviceLabel()` devolve `'Este aparelho'` como **nome salvo** da linha.
    Visto de outro celular, ele mente. Derivar do `userAgent`: `"Celular"` / `"Computador"`.
  - ⚠️ Esta é a escolha que colide com a régua de operador. Está justificada na seção do fim.

## B4. Cinco maneiras de dizer que algo não carregou, e uma palavra que só existe uma vez na loja

- **Onde:** `pages/index.vue` (`"Não foi possível carregar a loja"`), `pages/produto/[sku].vue`
  (`"Não foi possível abrir este produto"` + `"Tivemos um percalço ao carregar. Tente de
  novo em instantes."`), `pages/menu.vue` (`"Não conseguimos abrir o cardápio agora"`),
  `pages/colecao/[ref].vue` (`"Não conseguimos abrir a coleção agora"`), `pages/busca.vue` e
  `components/SearchOverlay.vue` (`"Não conseguimos buscar agora"`).
- **Defeito:** D7c, e D2 em `"percalço"`.
- **Por que dói:** é o mesmo evento — um fetch falhou — com cinco redações e três linhas de
  apoio divergentes. Nada disso confunde sozinho; junto, ensina o cliente que a loja tem
  cinco humores. `"percalço"` é a única ocorrência da palavra em todo o app e não nomeia
  nada: percalço de quem, de quê?
- **Substituição:** uma família, com o objeto trocando e a linha de apoio única.
  `"Não conseguimos abrir {o cardápio | este produto | a loja | a coleção} agora"` +
  `"Foi uma falha nossa. Tente de novo em instantes."`

## B5. O cardápio filtrado que zera manda "tentar outro termo" — e a tela não tem busca

- **Onde:** `pages/menu.vue`, o segundo `<UiEmpty>` (quando `activeSections` está vazio mas
  `catalog.has_items` é verdadeiro): `"Nada por aqui"` · `"Não encontramos esse item. Tente
  outro termo ou veja o cardápio completo."`
- **Defeito:** D1, segunda forma, e D3.
- **Por que dói:** não houve busca nenhuma nesta tela — o `/menu` não tem campo de texto (a
  busca é overlay). O cliente chegou por `?filtro=…` ou ligou a chave de preferências
  alimentares. A instrução nomeia um controle que não existe, e o controle que **existe**
  (`"Limpar filtro"`, na barra de pílulas lá em cima) não é nomeado. E `"Nada por aqui"` é
  falso: o cardápio tem itens; o filtro é que não casou.
- **Substituição:** `"Nenhum item com esses filtros"` · `"Limpe os filtros para ver o
  cardápio inteiro."` + botão `"Limpar filtros"` dentro do próprio vazio, chamando
  `clearMenuFilters()`. Quando a causa é a chave de preferências: `"Todos os itens desta
  seção conflitam com suas preferências. Desligue o filtro para vê-los."`

## B6. Consentimento de maioridade em três formulações

- **Onde:** `presentation/auth.ts` carrega a regra da casa **em comentário** (*"Nunca '18',
  'anos' nem 'adulto' — é 'maior de idade'"*) e a string
  `"Ao continuar, você confirma que é maior de idade e aceita os"`. Contra
  `pages/conta/preferencias.vue`: `"Declaro ter 18 anos ou mais e quero continuar recebendo
  este aviso."`, erro `"Confirme que você tem 18 anos ou mais."`, `aria-label` `"Confirmar
  maioridade para este aviso"`, descrição `"Confirme sua maioridade novamente…"`. E
  `components/StockNotifyButton.vue`: `"Declaro ter 18 anos ou mais e quero receber estes
  avisos."`
- **Defeito:** D7c, agravado por ser declaração jurídica.
- **Por que dói:** a casa escreveu a regra, num comentário, e três telas a ignoram. Numa
  declaração que existe para servir de prova, ter três redações é um problema antes de ser
  um problema de leitura. E `"estes avisos"` (no plural, sem antecedente) é D3: quais? deste
  produto? de todos? quantas vezes?
- **Substituição:** a frase carimbada, em todas as portas.
  `"Declaro que sou maior de idade e quero receber o aviso de volta deste produto no
  WhatsApp."` · erro `"Confirme que você é maior de idade."` · `aria-label` `"Confirmar que é
  maior de idade"`.

## B7. "Seus dados não são compartilhados." — no fluxo que manda o número por WhatsApp

- **Onde:** `pages/entrar.vue`, via `LOGIN_TERMS_NOTE`: `"Usamos seu telefone para autenticar
  a entrada. Seus dados não são compartilhados."`, visível em todo passo que não seja
  `welcome`.
- **Defeito:** D6, D7a (`autenticar`), e ambiguidade numa declaração de privacidade.
- **Por que dói:** a frase começa afirmando o que o sistema não faz — assinatura do D6 — e o
  faz numa tela cujo **caminho principal** entrega o número e o contexto da sacola ao
  WhatsApp/ManyChat, que são terceiros. "Não são compartilhados" é lido como "nada sai desta
  loja", e isso não é verdade nesse caminho. Numa frase de privacidade, a leitura errada é a
  que gera a reclamação.
- **Substituição:** `"Usamos seu telefone para confirmar que é você e falar sobre seus
  pedidos. Não vendemos seus dados nem mandamos propaganda sem você pedir."`

## B8. O horário do slot recusado só existe para quem usa leitor de tela

- **Onde:** `pages/finalizar.vue`, lista de horários de retirada:
  `:aria-label="slot.enabled ? slot.label : `${slot.label}: ${slot.reason}`"`. Na tela, o
  slot desabilitado é só um `<span class="line-through">`.
- **Defeito:** D3, e recusa sem causa.
- **Por que dói:** o `reason` existe, vem do servidor, e a loja o entrega **apenas** na
  camada de acessibilidade. Quem enxerga vê um horário riscado, sem saber se lotou, se
  passou, ou se aquele dia não tem aquele turno — e a diferença decide se ele muda de
  horário ou de dia. É a mesma falha do calendário, abaixo.
- **Substituição:** o `reason` vira linha visível sob o slot desabilitado, no mesmo texto do
  `aria-label`. Sem `reason`, `"Esgotado para este horário."`

## B9. Dia fechado no calendário: riscado, mudo e intocável

- **Onde:** `components/Ui/Datepicker.vue` e `components/Ui/Calendar.vue`, regra
  `.vc-disabled { pointer-events: none; text-decoration-line: line-through; }`. Nenhuma
  string, em nenhum dos dois, nem no popover `"Outra data"` de `pages/finalizar.vue`.
- **Defeito:** D3, terceira forma.
- **Por que dói:** este é o caminho de *"não tem entrega nesse dia"*, e ele não fala. O
  cliente toca três vezes no sábado (o `pointer-events: none` garante que nada aconteça) e
  conclui que o calendário travou. Pior: `isCheckoutDateUnavailable` mistura três causas
  distintas — feriado, dia da semana fechado, e fora do prazo de encomenda — num risco só.
- **Substituição:** legenda fixa sob o calendário: `"Dias riscados: a loja não abre. Escolha
  outro dia."`; e, para o dia além do limite de encomenda, uma segunda legenda: `"Fora do
  prazo de encomenda."`
  ⚠️ No mesmo par de arquivos, nenhum passa `locale` ao `VDatePicker`/`VCalendar`, e o
  `nuxt.config.ts` registra o módulo sem locale: num aparelho configurado em inglês, o
  cliente escolhe a data lendo `October 2026` / `Sun Mon Tue`, ao lado do
  `Intl.DateTimeFormat('pt-BR', …)` que formata a mesma data em português três centímetros
  acima. Fixar `locale="pt-BR"` nos dois wrappers.

## B10. "Entregamos no seu endereço · a 3,2 km" — a distância no lugar da taxa

- **Onde:** `pages/finalizar.vue`, bloco `data-checkout-zone-ok`: `"Entregamos no seu
  endereço"` + `· a {{ cart.delivery_distance_display }}`. E, um passo antes,
  `{{ checkout.delivery_hint || 'Taxa conforme a região' }}`.
- **Defeito:** D3, terceira forma.
- **Por que dói:** essa linha só existe quando `cart.delivery_fee_q !== null` — ou seja, **a
  taxa acabou de ser calculada, e a tela escolhe mostrar a distância**. A única pergunta que
  o cliente tem ao informar o endereço é quanto custa a entrega; ele escolheu "Entrega" sem
  número (`"Taxa conforme a região"`) e continua sem número depois de confirmar o endereço.
  Ele só descobre no rodapé — que é declaradamente mínimo (Total + um botão) — ou abrindo o
  resumo.
- **Substituição:** `"Entregamos no seu endereço · taxa de R$ 8,00"`, com a distância como
  complemento discreto ou fora.

## B11. Fora da área numa loja sem retirada: nem o bloqueio aparece

- **Onde:** `pages/finalizar.vue`, `applyDeliveryDraft`:
  `pickupSwapOffer.value = covered ? false : availableFulfillment.value.includes('pickup')`.
- **Defeito:** D1 e recusa que não chega à tela.
- **Por que dói:** se a loja **não** oferece retirada, `pickupSwapOffer` fica `false`, e o
  `v-else-if` da confirmação de cobertura também é falso (`delivery_zone_error === true`).
  **Nenhuma linha é renderizada** ao lado do endereço, e o botão principal continua
  habilitado (`disabled: draftSyncing || !addressSelection` — e há seleção). O cliente
  atravessa o resto do checkout e toma o erro no commit. O alerta que existe para esse caso
  (`"Ainda não entregamos nesse endereço"` + `"Mudar para retirada"`, que é o modelo de
  recusa desta superfície, ver E1) só cobre a loja **com** retirada.
- **Substituição:** terceiro ramo, colado ao picker: `"Ainda não entregamos nesse endereço.
  Escolha outro endereço aqui em cima, ou fale com a gente no WhatsApp."` — e o Continuar
  desabilitado com esse mesmo `reason`.

## B12. "Pedido mínimo não atingido." — sem o número que a tela tem ao lado

- **Onde:** `CART_CHECKOUT_BLOCK_MIN_ORDER` no registro: `"Pedido mínimo não atingido."`,
  que vira `action.reason` e aparece sob o botão principal. Contra o bloco
  `data-checkout-delivery-minimum` da mesma página, que diz
  `"Faltam {remaining_display} para o mínimo de entrega"` com barra de progresso, botão
  `"Adicionar mais itens"` e a saída `"Prefere retirar? Sem mínimo."`
- **Defeito:** D3.
- **Por que dói:** a razão do botão desabilitado é o texto que a pessoa lê quando o botão
  não responde — e é o único dos dois que não diz **quanto falta** nem oferece gesto. O dado
  está na mesma projection.
- **Substituição:** `"Faltam {remaining_display} para o pedido mínimo."`
  ⛔ **Correção de 18/09 (Onda 1): isto já era verdade no HEAD medido.**
  `shopman/storefront/presentation/cart.py` monta exatamente essa frase quando há
  `minimum_order_progress`; a chave `CART_CHECKOUT_BLOCK_MIN_ORDER` é só o fallback de
  quando **não há** número a dizer — e aí a frase genérica é honesta. O achado é falso e
  nada foi alterado.
  ⚠️ Irmãs no mesmo registro: `CART_CHECKOUT_BLOCK_UNAVAILABLE` (`"Revise itens
  indisponíveis antes de finalizar."`) e `CHECKOUT_WHEN_REQUIRED` (`"Escolha data e horário
  para seguir."`) usam **finalizar** e **seguir** para o gesto cujo botão na mesma tela diz
  `"Revisar pedido"` e, no sheet, `"Enviar pedido"` (com fallback local `'Confirmar
  pedido'`). Na `sacola.vue` o botão diz `"Finalizar pedido"`. A sequência
  **Finalizar → Revisar → Enviar** está *certa* pela regra de caminho da §D1 (só o último
  passo diz o verbo do ato); o que está errado são as frases que mandam "finalizar" e
  "seguir" numa tela onde nenhum controle tem esse nome, e o fallback `'Confirmar pedido'`,
  que é um quinto verbo. Ver o vocabulário fechado, no fim.

## B13. "Happy hour ativo" — em inglês, e sem dizer até quando

- **Onde:** `pages/menu.vue`, `<UiAlert v-if="catalog.happy_hour?.active">`: `"Happy hour
  ativo"` · `"{discount_percent}% de desconto aplicado no cardápio."` (o registro traz
  `CART_DISCOUNT_LABEL_TIME_WINDOW` = `"Happy Hour"`, com a nota de que o deployment
  reescreve).
- **Defeito:** D7a e D3.
- **Por que dói:** termo de bar, em inglês, numa padaria — e `ativo` é vocabulário de
  sistema. Mas o que custa dinheiro é o D3: **aplicado até quando?** É exatamente o dado que
  decide se a pessoa compra agora. E `"aplicado no cardápio"` admite duas leituras: tudo, ou
  os itens participantes.
- **Substituição:** `"Desconto do dia"` · `"{x}% em todo o cardápio até {hora}."` — e, sem o
  horário no payload, `"{x}% em todo o cardápio, enquanto durar."`, que é honesto em vez de
  vago por preguiça.

## B14. "Só compatível com minhas preferências" diz "0 itens ocultos" quando funciona

- **Onde:** `pages/menu.vue`, bloco `data-menu-dietary-filter`: `"Só compatível com minhas
  preferências"` · `"Esconder itens que conflitam com o que você marcou."` ·
  `` `${hiddenByDietaryCount} ${hiddenByDietaryCount === 1 ? 'item oculto' : 'itens ocultos'} pelas suas preferências` ``
- **Defeito:** D3, duas vezes.
- **Por que dói:** (a) *"o que você marcou"* — marcado onde? A tela não mostra a lista
  (lactose? glúten? nada?), que é a terceira falha do §2 em estado puro. (b) No estado mais
  pobre (§2, passo 2), `hiddenByDietaryCount === 0` e a linha diz **"0 itens ocultos pelas
  suas preferências"**: o controle parece quebrado no instante em que está funcionando.
- **Substituição:** desligado → `"Esconder itens que conflitam com suas restrições. Ver
  quais em Conta › Preferências."` · ligado com n>0 → `"{n} itens escondidos por conflitarem
  com suas restrições."` · ligado com n=0 → `"Nenhum item do cardápio conflita com suas
  restrições."`

## B15. "Quer repetir seu último pedido?" com o botão "Ver histórico"

- **Onde:** `pages/index.vue`, `quickReorderTitle` (`"Quer repetir seu último pedido{, nome}?"`)
  e o botão `{{ reorderAction?.label || 'Ver histórico' }}`, que sem ação chama
  `navigateTo('/conta')`. A linha de apoio: `"Seu pedido anterior volta à sacola para
  revisão."`
- **Defeito:** D1 e D7c.
- **Por que dói:** pergunta e resposta não batem — a loja pergunta se quer repetir e o botão
  responde "ver histórico". E o mesmo gesto aparece três vezes na mesma home com três nomes:
  `"Repetir pedido"` no slide do hero, `reorderAction.label` no card, `"Ver histórico"` no
  fallback.
- **Substituição:** sem ação disponível, o card muda de título: `"Seus pedidos anteriores"`,
  botão `"Ver meus pedidos"`. Com ação, um rótulo só em toda a home: `"Repetir pedido"`. E a
  linha de apoio → `"Os itens voltam para a sacola; você confere antes de finalizar."`

## B16. Preço e peso colados admitem "R$ 18,00 por 500 g"

- **Onde:** `pages/produto/[sku].vue` (bloco de preço e `shop-action-dock`), e igual em
  `components/ProductTile.vue` / `components/ProductListItem.vue`:
  `{{ product.price_display }}` seguido de `{{ product.unit_weight_label }}`, com
  `{{ product.original_price_display }}` riscado acima.
- **Defeito:** D3.
- **Por que dói:** dois números adjacentes sem conector — `R$ 18,00` `500 g`. Preço **por**
  500 g, ou preço da peça **que pesa** 500 g? Numa padaria, onde granel e peça convivem, a
  leitura errada é cara e só se descobre no balcão. O preço riscado tem o mesmo problema:
  nada diz que o desconto já está no valor grande, nem até quando vale.
- **Substituição:** conector explícito — `"R$ 18,00 · peça de 500 g"` — e, na linha do preço
  antigo, `"antes R$ 22,00"` em vez do risco mudo.

## B17. "Economize até" — até quanto, e por quê "até"?

- **Onde:** `pages/finalizar.vue`, toggle de fidelidade:
  `{{ checkout.copy.loyalty_savings_prefix || 'Economize até' }} {{ checkout.loyalty_value_display }}`
  (`CHECKOUT_LOYALTY_SAVINGS_PREFIX` no registro).
- **Defeito:** D3.
- **Por que dói:** `"Economize até R$ 12,00"` deixa o cliente sem saber se vai economizar 12
  ou menos, e por qual regra. Ele liga a chave para descobrir — que é justamente "parar para
  pensar" num campo que mexe no total.
- **Substituição:** se o valor é o desconto efetivo, `"Usar {valor} em pontos neste pedido"`.
  Se ele é um teto (o desconto depende do total), o teto tem que ser dito:
  `"Seus pontos cobrem até {valor} deste pedido."`

## B18. Confirmar o cancelamento sem falar do dinheiro

- **Onde:** no registro: `TRACKING_CANCEL_WARNING_MESSAGE` (`"O cancelamento só é permitido
  enquanto o pagamento não foi capturado e a loja ainda permite reversão."`),
  `TRACKING_CANCEL_ACK_LABEL` (`"Entendo que o pedido será cancelado e deixará de ser
  preparado."`), `TRACKING_CANCEL_SUCCESS_TITLE` (`"Pedido cancelado"`) com
  `TRACKING_CANCEL_SUCCESS_MESSAGE` (`"Recebemos o cancelamento. Acompanhe o status nesta
  página."`).
- **Defeito:** D7a, D6 e D1.
- **Por que dói:** três coisas. (a) `capturado` e `reversão` são vocabulário de adquirente;
  a frase explica a **política** em vez de dizer se **este** pedido pode ser cancelado — e o
  cliente está lendo isso com o dedo sobre o botão. (b) O aceite fala do preparo e **não
  fala do dinheiro**: quem já pagou não descobre ali se será estornado, nem quando. O
  registro tem `TRACKING_REFUND_STATUS_PROCESSING` (`"Reembolso em processamento"`) — sem
  prazo — mas ele só aparece *depois*. (c) O título diz `"Pedido cancelado"` e a linha de
  baixo diz que o cancelamento foi *recebido*: o título afirma o fim, a mensagem admite que
  é começo. É a mesma forma do `"Enviado"` sobre mensagens na fila que o Marketing tinha.
- **Substituição:**
  - aviso → `"Dá para cancelar enquanto a loja não começa a preparar."` (e, quando não dá, a
    frase é a recusa concreta, não a política)
  - aceite, com pagamento confirmado → `"Entendo que o pedido será cancelado e que o
    reembolso de {valor} cai na mesma forma de pagamento em até {n} dias."`
  - título/mensagem de sucesso → `"Cancelamento recebido"` / `"A loja confirma em instantes.
    Você acompanha por aqui."`, e o título troca para `"Pedido cancelado"` quando de fato
    cancelar.
  - `TRACKING_REFUND_STATUS_PROCESSING` → `"Reembolso a caminho — costuma levar até {n}
    dias."`

## B19. "Pagamento expirado. O prazo acabou e cancelamos o pedido." — e o SMS conta outra história

- **Onde:** `TRACKING_PAYMENT_EXPIRED` (`"Pagamento expirado"` / `"O prazo acabou e
  cancelamos o pedido."`), com `TRACKING_PROMISE_EXPIRED_FOOTNOTE` (`"Você pode pedir de novo
  quando quiser."`). Contra `TRACKING_PROMISE_LINK_FOOTNOTE`: `"Se o prazo passar, liberamos
  a reserva e avisamos você."`
- **Defeito:** D2 e D7c.
- **Por que dói:** *"liberamos a reserva"* descreve o que a **loja** faz com o próprio
  estoque; do lado do cliente, o que acontece é que o pedido dele morre. O mesmo evento tem
  dois verbos nas duas notas de rodapé da mesma tela. E a nota de saída (`"Você pode pedir de
  novo quando quiser"`) é uma frase, não um gesto: não há botão. ⚠️ Fora da tela, o gêmeo
  agrava: `shop/adapters/notification_sms.py` manda `"Nao recebemos o pagamento do pedido
  {order_ref} no prazo e liberamos a reserva. Se ainda quiser, fale com a gente que
  refazemos o pedido."` — o cliente lê "cancelamos o pedido" na tela e "liberamos a reserva"
  no celular, com minutos de diferença.
- **Substituição:** um verbo, em todos os canais — **o pedido é cancelado**; a reserva é
  assunto da loja.
  - `TRACKING_PROMISE_LINK_FOOTNOTE` → `"Se o prazo passar, o pedido é cancelado e a gente
    avisa você."`
  - `TRACKING_PROMISE_EXPIRED_FOOTNOTE` → mantém a frase e **ganha o botão**: `"Montar o
    pedido de novo"` (o `reorder` já existe como ação e já é injetado no painel quando o tom
    é `danger`; basta o estado expirado entrar nessa regra).

---

# Parte C — é só feio

## C1. "Erro 404" na tela de uma padaria

`error.vue`, computed `kicker` → `"Erro 404"`, com o `<h1>` logo abaixo já dizendo `"Não
encontramos esta página"`. D7a — é o V4 da régua, código de protocolo na tela do cliente.
**Substituição:** apagar o kicker. E, no mesmo arquivo, `"O item pode ter saído do cardápio
ou o endereço está incorreto. Vamos levar você de volta ao cardápio."` promete um
redirecionamento automático que não acontece (D1 leve; o que existe são dois botões):
`"O item pode ter saído do cardápio, ou o endereço está errado. O cardápio de hoje está
aqui:"` E `"Prefere falar conosco? WhatsApp"` é pergunta e resposta grudadas num rótulo de
botão (D8): `"Falar conosco no WhatsApp"`.

## C2. "Nutricional" e "% VD"

`pages/produto/[sku].vue`, `<UiAccordionItem value="nutrition">`: o título `"Nutricional"` é
adjetivo sem substantivo (D3), e `{{ row.pdv }}% VD` é sigla que o cliente tem de decorar
(D7a). **Substituição:** `"Informação nutricional"`, e `"% VD"` com a legenda `"VD: valor
diário de referência"` sob a tabela. No mesmo acordeão, `"Conservação"` guarda `"Peso: …"` e
`"Dimensões: …"` — grandezas de naturezas diferentes sob um rótulo só (parente do D4):
`"Conservação e medidas"`, ou dois itens.

## C3. Quatro formas de dizer "ir para o cardápio"

`"Ver cardápio completo"` (`index.vue`, `colecao/[ref].vue`), `"Ver cardápio"` (`index.vue`,
`TRACKING_MENU_CTA`), `"Ver o cardápio"` (`faq.vue`, `oferta/[ref].vue`), `"Voltar ao
cardápio"` (`error.vue`, `gerenciar-aviso.vue`). D7c. **Substituição:** `"Ver o cardápio"`
como padrão; `"Voltar ao cardápio"` só quando a pessoa de fato veio de lá. (`"Buscar no
cardápio"` já está consistente nas quatro portas — ver E7.)

## C4. "Mensagem" × "Falar no WhatsApp"

`components/ShopHeader.vue`, link `v-else-if="!statusOpen && whatsappUrl"` → `"Mensagem"`,
contra `"Falar no WhatsApp"` na gaveta do mesmo componente, no `ShopFooter.vue`, no CTA da
`index.vue` e no `error.vue`. D7c e D2 — `"Mensagem"` é substantivo solto, não diz o ato nem
o canal, e aparece exatamente quando a loja está fechada, que é quando mais importa.
**Substituição:** `"WhatsApp"` no espaço curto da barra (o `aria-label` já diz `"Enviar
mensagem para {marca}"`), `"Falar no WhatsApp"` nos botões largos. Dois tamanhos do mesmo
nome, não dois nomes.

## C5. "Um cuidado especial hoje, {nome}!" — qual cuidado?

`components/HomeHeroThing.vue`, `slides`, ramo `omo.is_birthday`, fallback de
`copy.birthday_heading`. D3: a tela diz que há um cuidado especial e não diz qual; o botão
abaixo leva ao cardápio normal. **Substituição:** sem benefício concreto no payload, `"Feliz
aniversário, {nome}!"` — calor sem promessa vazia é permitido nesta superfície; promessa
vazia não é. No mesmo componente, `"Com um toque, seu favorito volta à sacola."` colide com
o conceito de **favorito** que a loja tem de verdade (`FavoriteHeart`, seção "Seus
favoritos") — D7b: `"Os itens do seu último pedido voltam para a sacola."`

## C6. A descrição do produto que vira o nome da seção

`components/ProductTile.vue`: `{{ item.short_description || sectionLabel }}`. D3, e só
visível no estado pobre (§2, passo 2): sem descrição, o card mostra `"Rústicos"` com a
tipografia de descrição, e o cliente lê isso como o que o produto **é**. **Substituição:**
deixar a linha vazia (o `sm:min-h-10` já reserva o espaço), ou marcar a diferença:
`"Em Rústicos"`.

---

# Parte D — miudezas com endereço

Cada uma é uma linha, e todas têm substituição escrita. Agrupadas por onde vivem.

**No checkout (`pages/finalizar.vue`, `utils/checkoutFlow.ts`, `components/CheckoutProgressSection.vue`)**

- `{{ phoneDisplay || 'Entre por telefone para continuar' }}` ocupa a linha do **número**, com
  o botão `"Trocar"` ao lado: a frase manda entrar e o controle oferece trocar (D1, segunda
  forma). → `"Telefone não confirmado"` + botão `"Confirmar telefone"`.
- `"Esta é a opção disponível para este pedido."` não diz por que a outra sumiu (D3). →
  `"Hoje este pedido só pode ser retirado na loja."` / `"…só sai por entrega."`
- `'Complete esta etapa para continuar'` (`CheckoutProgressSection.vue`, fallback de
  `summary`) aparece sob uma seção **fechada**, sem controles e sem "Editar" — instrução para
  um gesto indisponível (D1) + verbo genérico (D2). → em `upcoming`, `"Você preenche esta
  etapa daqui a pouco."`
- `'Escolha data e horário'` (`checkoutStepSummary`, passo `when` não ativo) num pedido de
  **entrega**, que não tem seletor de horário (D1). O irmão ativo já bifurca corretamente. →
  entrega: `'Escolha a data'`.
- `'Bloqueado'` (`stateLabel`, dentro de um `sr-only`): quem enxerga lê `action.reason`; quem
  usa leitor de tela ouve a parede antes da causa (D2, fraco — registro por honestidade). →
  `'Falta algo nesta etapa'`.
- `'Pedido não pode ser confirmado agora.'` (fallback de `openConfirmSheet`) sem causa e sem
  gesto. → `"Algo mudou na sua sacola. Volte um passo e confira os itens."`
- `"Precisa de troco?"` / placeholder `"Troco para quanto?"` / `"Informe o valor da nota para
  o entregador levar o troco certinho."` — três formas de dizer a mesma coisa num campo só
  (D8). → manter o rótulo e a descrição; o placeholder vira `"Ex: 50"`.

**No acompanhamento (`pages/pedido/[ref]/index.vue` e o registro)**

- `'Solicitação registrada. Guarde o protocolo.'` (`successMessage`, ramo
  `request_cancellation`): **não há protocolo em lugar nenhum da tela** (D1, segunda forma;
  terceira falha do §2). → `"Pedido de cancelamento enviado. A loja responde por aqui."`
- `useSonner.info('Ação confirmada. A atualização do acompanhamento está pendente.')`: `Ação`
  e `pendente` são vocabulário de sistema, e não há gesto (D7a + D3). → `"Recebemos. Esta
  tela atualiza sozinha em instantes."`
- `'Não foi possível concluir. Tente de novo ou fale conosco.'` — concluir **o quê**? (D3) e
  `"fale conosco"` sem link (ver D-final). → `"Não conseguimos {ação} agora. Tente de novo,
  ou fale no WhatsApp."`, com o botão de suporte que a página já tem.
- `TRACKING_PAYMENT_CARD_INTRO` (`"Conclua o pagamento no nosso ambiente seguro."`) manda o
  cliente para um domínio de terceiro, enquanto `TRACKING_PAYMENT_CARD_SECURITY_NOTE` diz
  `"Pagamento processado por provedor seguro."` — `nosso` e `provedor` na mesma caixa (D3). →
  `"Conclua o pagamento na página segura do {provedor}. Assim que a confirmação chegar,
  atualizamos esta tela."` O mesmo vale para os quatro `"Finalize no ambiente seguro…"` de
  `order_tracking.py`.
- `TRACKING_POLLING_BADGE` (`"Atualização periódica"`) ao lado de `TRACKING_LIVE_BADGE`
  (`"Ao vivo"`): o cliente não tem o que fazer com a distinção (D7a). → `"Atualizando"`, ou
  nenhum selo (o painel já pulsa quando está fresco).
- `TRACKING_RATE_LIMIT_TITLE` (`"Atualização pausada por um instante"`) sem gesto. →
  `"Atualizando com menos frequência por um instante. Nada mudou no seu pedido."`
- `TRACKING_NOT_FOUND_MESSAGE` (`"Confira o link do pedido ou fale com a equipe."`) sem link
  nem botão. Compare com `presentation/orderAccess.ts`, que trata o mesmo 404 com título,
  causa e **botão de entrar** — a versão boa existe e é do lado do cliente. → alinhar a do
  servidor à do cliente, ou deixar só a do cliente.
- `URGENCY_BANNER_MESSAGE` (`"Últimos pedidos. Fechamos em breve"`) contra
  `SHOP_STATUS_OPEN_CLOSING_SOON` (`"Últimos pedidos até"` + hora): o mesmo momento, um com
  hora e outro com "em breve" (D3). → `"Últimos pedidos até {hora}."`

**Nos avisos de reposição (`components/StockNotifyButton.vue`, `presentation/stockNotify.ts`, `pages/gerenciar-aviso.vue`)**

- `"Anotado"` como rótulo de um botão desabilitado cujo `title` promete `"Gerenciar aviso"`
  (D1 + D2). → `"Aviso ativo"`, com o destino visível: `"Para pausar ou cancelar, abra Conta
  › Preferências."`
- `"Aviso pausado agora. Na próxima atualização, Me avise ficará disponível."` — `"próxima
  atualização"` é a projeção do servidor (D6) e `"Me avise"` nomeia um botão que saiu da tela
  (D1). → `"Aviso cancelado. Recarregue a página para ativá-lo de novo."`
- `"Aviso recorrente ativo. Você pode gerenciá-lo nas preferências."` — `recorrente` é palavra
  de contrato (D7a), `"nas preferências"` não é lugar (D3), e o canal não aparece. →
  `"Pronto. Avisamos no WhatsApp toda vez que voltar. Para pausar, abra Conta › Preferências."`
- `"Este aviso não está ativo. Você pode ativá-lo novamente quando quiser."` logo depois de o
  cliente tocar em ativar: duas leituras, falhou × já existia (D3 + D6). → `"Seu aviso para
  {nome} estava pausado. Toque de novo em Avisar quando voltar para retomá-lo."`
- `"Seu aviso fica guardado para a volta."` — num fluxo cujo verbo central é *voltar*, "a
  volta" é a do cliente ou a do pão? (D3) → `"Guardamos seu pedido de aviso até você
  terminar."`
- `"ocorrências"` em cinco strings (`"para ocorrências futuras"`, `"Retomar para próximas
  ocorrências"`, …): palavra de sistema de eventos; na padaria o que ocorre é o pão voltar
  (D7a). → `"Aviso ligado: avisamos toda vez que este produto voltar."` / botão `"Retomar
  aviso"`.
- `"Este link de gestão não é válido."` — `link de gestão` é nome interno, e a pessoa veio
  **cancelar** um aviso e sai sem cancelar (D7a + recusa sem saída). → `"Este link não vale
  mais — eles expiram depois de um tempo. Seus avisos ficam em Conta › Preferências."` +
  botão `"Ver meus avisos"`.
- `"Mensagens já aceitas pelo provedor não podem ser retiradas."` (duplicada em
  `preferencias.vue` e `gerenciar-aviso.vue`) — D6 exemplar mais `provedor` (D7a). →
  `"Cancelar vale a partir de agora. Se uma mensagem já estiver a caminho, ela ainda pode
  chegar."`
- `"Há {n} envio com resultado ainda não confirmado pelo provedor."` — erro de concordância
  garantido com n≥2, mais D6, mais três palavras de sistema numa frase, mais nada para o
  cliente fazer. → some, ou vira `"Uma mensagem pode estar a caminho. Se ela chegar depois de
  você cancelar, é só ignorar."`

**Na entrada e na conta**

- `"Enviamos um código por SMS para este número."` **antes** de enviar (o formulário ainda
  está vazio) — D1 clássico. → `"O código vai por SMS para este número."`
- `ERROR_TITLES.invalid_code = 'Código não confere'` disparado quando o cliente enviou
  **menos de 6 dígitos**: o título acusa de errado um código que não foi comparado (D1 + D3).
  → título `"Faltam dígitos"`, corpo `"O código tem 6 números. Complete e a confirmação é
  automática."`
- `'Código inválido ou expirado.'` — duas causas com remédios opostos numa frase (D3). →
  `"Este código não abriu sua conta. Ele pode ter sido digitado errado ou já ter vencido —
  confira os 6 dígitos ou toque em Reenviar código."` (o botão existe, com esse nome).
- `"Enviamos um código para o seu telefone. Digite-o para continuar com esta ação."` no
  diálogo de step-up, que **cobre** a tela e apagou o contexto: *esta ação* pode ser apagar a
  conta (D3 triplo — a ação, o número e o canal). → `"Enviamos um código por SMS para
  {número}. Digite para excluir sua conta."` / `"…para baixar seus dados."`
- O último botão da exclusão diz `"Confirmar"` — e é o único passo que não diz o ato; o mesmo
  rótulo também serve para baixar um arquivo (D1). → `"Excluir minha conta"` / `"Baixar meus
  dados"`.
- `"Remover"` age na hora na lista de passkeys e **abre confirmação** na lista de aparelhos,
  na mesma página (D1 + D7c). → confirmar também a chave: `"Remover esta chave?"` / `"Você vai
  precisar ativar de novo neste aparelho."`
- `'Não foi possível remover agora.'` de uma **passkey** é renderizado dentro da seção de
  aparelhos, sob `"Não foi possível atualizar"` — longe do botão tocado e apontando para o
  objeto errado (D1). → `passkeyIssue` próprio: `"Não foi possível remover esta chave agora.
  Tente de novo."`
- `"Baixe uma cópia dos seus dados ou encerre sua conta."` contra o botão `"Excluir minha
  conta"` e o diálogo `"Excluir sua conta?"` — dois verbos para um ato irreversível (D7c). →
  `"Baixe uma cópia dos seus dados ou exclua sua conta."`
- `"Telefone: Telefone confirmado"` — `phoneDisplayLabel` cai em `'Telefone confirmado'` como
  **valor** da linha rotulada `"Telefone"`, e aparece duas vezes (D3 + D1). → usar
  `profileCopy.missing_value` (`"Não informado"`).
- `"Número não informado"` na seção `"Seu número"`, logo abaixo de `"É por ele que você
  entra…"` — a tela se contradiz na mesma caixa (D3). → `"Não conseguimos mostrar seu número
  agora"`, com o botão `"Mudar número"` ativo.
- O badge de **Pedidos** (`presentation/account.ts`, `accountNavCards`) mostra
  `active_order_count || total_order_count`: com pedido ativo é "ativos", sem nenhum vira "o
  total da vida", e nada marca a virada (**D4**). → badge só para o que pede atenção agora;
  sem ativos, sem badge. Se o total precisa aparecer, é texto rotulado: `"12 no total"`.
- `"Cartela completa! Sua recompensa está pronta."` numa vitrine que **não tem botão de
  resgate** (D3). → `"Cartela completa. Peça sua recompensa no balcão ou no próximo pedido."`
- `'UF.'` como mensagem de erro, abaixo de um campo já rotulado "UF", ao lado das irmãs
  `'Informe a rua.'` / `'Informe o bairro.'` / `'Informe a cidade.'` (D3). → `'Escolha o
  estado.'`
- `'CEP com 8 dígitos.'` cobre **campo vazio** e **CEP incompleto** com uma frase (D3). →
  vazio: `'Informe o CEP.'`; incompleto: `'O CEP tem 8 dígitos. Confira os números.'`
- `'E-mail inválido.'` (`conta/perfil.vue`) não diz o que consertar (D3). → `"Esse e-mail
  parece incompleto. Exemplo: nome@email.com"`
- `"Agora não"` significa **"não é este endereço"** no card de geolocalização do
  `AddressPicker` e **"depois eu escolho"** no `AddressLabelSheet` — duas telas em sequência
  (D7c). → no card, `"Não é aqui"`; `"Agora não"` fica só para o adiamento.
- `"Definir padrão"` (`conta/enderecos.vue`) × `"Usar como padrão"` (`AddressPicker.vue`), e
  só o segundo explica o que é (`"Este endereço aparece primeiro na próxima compra."`) — D7c
  + D3. → unificar em `"Usar como padrão"` e repetir a explicação sob a badge.
- `"Endereço não encontrado."` (404 do servidor) dentro do diálogo que está **mostrando** o
  endereço (D3). → tratar o 404 como sucesso na tela: fechar, `refreshAddresses()`, e dizer
  `"Este endereço já não estava mais na sua conta. Atualizamos a lista."`
- `"Use ?action=default."` (`shopman/storefront/api/account.py`, 400) — query string na tela
  do cliente (D7a / V4 da régua). Só alcançável fora do app hoje, mas o `errorDetail` joga
  qualquer `detail` direto na tela. → `"Não foi possível concluir esta alteração."`
- `"Muitas tentativas. Aguarde alguns minutos."` × `"Muitas tentativas. Aguarde um
  instante."` × `"Aguarde {retry_after_seconds} segundos antes de tentar novamente."` — três
  esperas para a mesma situação, duas vagas e uma exata (D7c + D3). → uma só, com o número
  que o servidor já tem: `"Muitas tentativas. Tente de novo em {n} minutos."`
- `"Próximo"` no passo 0 do guia iOS (`PwaInstallInvite.vue`), que tem dois passos e cujo
  botão de volta já sabe disso (D3 leve). → `"Continuar (1 de 2)"`.

**Uma que atravessa a loja inteira: `"fale conosco"` em dez redações e quase nunca com link**

Medido no HEAD, em `shopman/` e `surfaces/storefront-nuxt/`: `fale com a equipe` (8) ·
`fale conosco` (8, contando maiúscula) · `falar com a gente` (3) · `Falar com a loja` (3) ·
`Falar com a equipe` (2) · `Conversar com a loja` (1) · `A gente resolve com você pelo
WhatsApp` (1). D7c, e o agravante é que na maioria delas **não há link ao lado** — a saída
que a loja oferece para o cliente travado é uma frase. **Substituição:** um rótulo,
`"Falar no WhatsApp"`, e a regra: toda recusa que diz isso ganha o botão, com a
`publicConfig.whatsapp_url` que já está na sessão.

---

# Parte E — o que examinei e considerei bom

## E1. O alerta de fora-de-área é o modelo de recusa desta superfície

`pages/finalizar.vue`, `data-checkout-pickup-swap`: `"Ainda não entregamos nesse endereço"` /
`"Mas você pode retirar na loja quando quiser."` / botão `"Mudar para retirada"`. Diz o
limite, oferece o gesto, e o gesto é um clique — `switchToPickup()` troca o tipo, limpa o
erro, refaz o rascunho e avança a etapa. É a resposta exata ao "bloqueio sem saída é o pior
defeito numa loja", e é o padrão que a Parte A inteira pede que se copie. O único buraco é a
loja sem retirada (B11).

## E2. O bloco do mínimo de entrega faz tudo o que uma recusa precisa fazer

`data-checkout-delivery-minimum`: `"Faltam {x} para o mínimo de entrega"` + barra de
progresso + `"Adicionar mais itens"` (que volta ao cardápio, com o rascunho preservado) +
`"Prefere retirar? Sem mínimo."` Quatro elementos, quatro funções: quanto falta, quão perto
está, o gesto que resolve, e a saída alternativa. E ele acusa **cedo** — no momento em que
"Entrega" é escolhida, não no commit — porque o valor é flat e já se sabe sem endereço. O
comentário registra a decisão. É a melhor recusa do app, e é a referência do B12.

## E3. A sacola vazia vira caminho, não botão morto

`pages/finalizar.vue`, `primaryAction`: com `bagIsEmpty`, o botão principal deixa de ser um
`"Revisar pedido"` apagado e vira `"Adicionar itens"` **ativo**, com `reason` `"Sacola
vazia."` e destino `/menu`. O comentário diz por quê, e a regra vale para o resto:
`reason` nunca é decorativo num botão desabilitado no lugar mais nobre da tela.

## E4. A copy da fila de espera do WP-P2E

No registro: `"Você está na fila"` / `"Assim que a fornada sair, a gente te avisa para
confirmar. **Nada foi cobrado ainda.**"` → `"Sua fornada saiu!"` / `"Confirme para garantir o
seu. Se não der, a vaga vai para a próxima pessoa da fila."` → `"A vaga passou a vez"` / `"O
prazo de confirmação passou e liberamos a sua vaga. Nada foi cobrado, e você pode entrar na
fila da próxima fornada."` Cada fase diz o que aconteceu, o que fazer, o que acontece se não
fizer, **e o que não aconteceu com o dinheiro** — que é a pergunta silenciosa de quem espera.
A saída é dita sem culpa e com a porta aberta. É a melhor sequência de copy do sistema
inteiro, e é exatamente por isso que o A4 dói: a outra fila de espera, a do
`fulfillment_wait_kind`, não tem nada disso.

## E5. `presentation/orderAccess.ts` — o 404 tratado como gente

Distingue 404/403 (`"Não encontramos este pedido"` / `"Ele pode estar em outra conta ou em
outro aparelho. Entre com seu telefone para ver seus pedidos."` + botão **Entrar**) de 429
(`"Muitas atualizações em pouco tempo"` / `"Espere um instante e tente de novo. Está tudo
bem."`) de instabilidade (`"Pode ter sido uma instabilidade rápida."`). Três causas, três
frases, três gestos — e o comentário explica por que a copy é do cliente e não do servidor
(um 404 não traz corpo). É a estrutura que o `TRACKING_NOT_FOUND_MESSAGE` deveria herdar.

## E6. As páginas de termos e privacidade

`pages/terms.vue` e `pages/privacy.vue`: `"Quem vende"`, `"Preço e disponibilidade"`, `"Como
o pedido é confirmado"`, `"O que a gente guarda"`, `"Por que a gente pode guardar"`, `"Os
seus direitos, e onde eles ficam"`. São a pergunta do cliente virada rótulo, sem uma palavra
de jurídico. É a melhor copy do app, e é a prova de que esta superfície sabe escrever.
⚠️ Duas ressalvas de fato, não de redação: `terms.vue` carrega em comentário o aviso `⚠️
ESTE TEXTO PRECISA DO AVAL DO DONO antes do go-live`, com três pontos em aberto (troca e
devolução de perecível, prazo de estorno, razão social); e `updatedAt = '20 de agosto de
2026'` está fixo no código — qualquer edição de copy nessa página deixa a data mentindo.

## E7. Onde o vocabulário JÁ fechou

- **`"Buscar no cardápio"`** — idêntico no atalho da home, no ícone do `/menu`, no
  placeholder da `/busca` e no do `SearchOverlay`. Quatro portas, um nome. É a prova de que
  dá para fechar um rótulo nesta superfície.
- **`"Agora não"`** como saída dos bottom sheets de aviso e de substituto — recusa sem carga,
  e o comentário do `MarketingPromptSheet` registra que "agora não" **não** é gravado como
  opt-out. Copy e comportamento concordam. (A colisão do mesmo rótulo no `AddressPicker` está
  na Parte D; o uso aqui é o certo.)
- **`"Entre na sua conta para continuar."`** — 30 ocorrências no servidor, todas idênticas. É
  a mensagem de auth mais repetida do sistema e nunca divergiu.

## E8. Peças que li inteiras e não têm achado

- **`pages/sacola.vue`, o erro de carregamento:** `"Sua sacola não quis carregar agora"` /
  `"Seus itens estão guardados. Tente de novo em instantes."` / `"Tentar de novo"`. Título com
  a voz da casa, a garantia que o cliente quer (o que aconteceu com o meu trabalho), e o
  gesto. Três linhas, nada sobrando. É a versão certa do A10.
- **`pages/sacola.vue`, o teto de estoque:** `"Por hoje, temos {n} unidades deste item."`
  ao lado do `+` desabilitado, e o botão `"Usar {n} disponíve{is/l}"` quando sobra alguma
  coisa. O "+" não morre em silêncio, e a alternativa é um toque. O comentário registra a
  decisão. Note a grandeza: **unidade**, nunca linha — e `items_count` na projection é
  `sum of units across lines`, consistente em `sacola.vue`, `finalizar.vue` e
  `confirmSheetDescription`. D4 passa limpo no carrinho, que é onde o PDV tropeçou.
- **`AddressPicker.vue`, `'Informe o número (ou "s/n").'`** — nomeia o campo, dá a saída para
  quem não tem número, e cabe numa linha. É o padrão que `'UF.'` e `'CEP com 8 dígitos.'`
  deveriam seguir.
- **`AddressPicker.vue`, o card de geolocalização:** `"Você está aqui?"` + `"Usar este
  endereço"`. A localização nunca é aplicada em silêncio; a pergunta é literal e a
  confirmação é explícita.
- **`AddressPicker.vue`, três rótulos de salvar:** `"Salvar alterações"` (PATCH) ×
  `"Salvar endereço"` (POST) × `"Usar este endereço"` (seleção em memória). Parece
  inconsistência e é o contrário: três atos diferentes, três nomes. `"Usar este endereço"`
  passa no D1 justamente porque **não** promete salvar — quem conta o resto é a linha vizinha
  no checkout.
- **`AddressLabelSheet.vue`:** `"Endereço salvo"` × `"Vamos guardar este endereço"`, com
  `"Como você quer chamar este endereço?"` e `"Ele fica salvo na sua conta quando o pedido
  fechar."` A folha distingue o endereço que já é do que ainda vai ser, e diz o que aconteceu
  antes de pedir algo.
- **`utils/checkoutFlow.ts`, `paymentMethodHint`:** `"Pague com Pix no app do banco"` /
  `"Pagamento seguro via {provedor}"` / `"Pague ao receber"`. O comentário registra que isso
  substituiu um `"Padrão da loja"` que não significava nada, e que nomear o provedor reduz a
  hesitação de digitar cartão. Decisão certa e escrita.
- **`pages/conta/seguranca.vue`, a seção "Seu número":** `"É por ele que você entra e recebe o
  aviso de que o pão saiu do forno."` · `"Mudou de número? A conta vem junto — seus pedidos,
  endereços e pontos ficam."` · `"O número antigo deixa de abrir esta conta assim que você
  confirmar."` · `"Mandamos um código para {número}. Digite-o para concluir a mudança."`
  Responde à pergunta real (perco meu histórico?) antes de ela ser feita, e diz a consequência
  no momento da decisão, com o prazo exato. É o modelo que falta ao step-up.
- **`devicesCopy.delete_warning`:** `"Apagamos seu nome, telefone, e-mail e endereços,
  inclusive dos pedidos antigos, e você sai da loja neste dispositivo."` Enumera o concreto em
  vez de dizer "seus dados", e o `"inclusive dos pedidos antigos"` é a palavra que evita a
  surpresa. (Só o substantivo final entra no B3.)
- **O diálogo de sair (`conta/index.vue`):** `"Você precisará entrar de novo para ver seus
  pedidos e fidelidade. Seus dados ficam guardados."` com o cancelar chamado `"Ficar
  conectado"`. Os dois botões dizem o **estado resultante**, não sim/não.
- **`presentation/account.ts`, `ordersEmptyCopy` e `ordersCountLabel`:** vazios acolhedores por
  filtro, e `"2 pedidos em andamento (8 pedidos no total)"` — duas grandezas, dois números,
  nunca somados. D4 passa limpo.
- **`presentation/orderTracking.ts`, `timelineStepStateLabel`:** `concluído` / `em andamento` /
  `cancelado` / `ainda não`, num `sr-only`. O ✓ e o X são sinal visual; quem ouve a tela ouve a
  diferença. E o passo cancelado tem indicador próprio (X destrutivo), nunca um check verde —
  a timeline não pode contradizer o painel.
- **`components/PaymentBlock.vue`, `"Não abriu? Toque no botão novamente."`** — só aparece
  depois de o cliente tocar (`tentouAbrirCheckout`), que é quando a frase faz sentido.
- **`pages/index.vue`, o banner de pedido ativo** (`data-home-active-order`): estado
  (`status_label`), identidade (`"Pedido {ref}"`) e gesto (`"Acompanhar"`) na mesma faixa.
- **`pages/menu.vue`, `menuFocusLabel`:** `"{n} itens no cardápio."` em vez de "disponíveis" —
  o comentário ao lado documenta a recusa de afirmar o que não foi medido. D4 evitado de
  propósito.
- **`pages/faq.vue`, o vazio:** `"Ainda não publicamos as perguntas frequentes."` + `"Se ficou
  alguma dúvida, fale com a gente por um dos canais abaixo."`, com os canais renderizados
  logo abaixo. Estado vazio que entrega o gesto **e** o controle dele na mesma tela.
- **`pages/oferta/[ref].vue`, a linha do item que ficou de fora:** `"Um item não estava
  disponível agora e ficou de fora:"` — nomeia a causa, o número e aponta para a lista, que
  traz o botão de aviso item a item. É o oposto exato do A11.
- **`TRACKING_PROMISE_DISPATCHED_MESSAGE`:** `"Está a caminho. Confirme aqui quando receber."`
  — e o comentário explica: courier terceirizado, sem rastreio de chegada, então a loja **não
  promete** aviso de entrega e devolve o fecho ao cliente. É a promessa calibrada pelo que o
  sistema sabe.
- **`TRACKING_PROMISE_STALE`** (`"Atualizar"`) e o carimbo de frescor: enquanto o dado está
  fresco o ícone pulsa e não há texto; quando um poll falha, vira informação com o botão de
  recuperar. O comentário registra que isso substituiu um "reconectando…" técnico.
- **`"Sem conexão no momento. Reconectamos e atualizamos assim que a internet voltar."`** e
  **`"O prazo terminou. Estamos atualizando seu pedido…"`** — dois estados de transição que
  dizem o que a tela está fazendo, sem explicar o mecanismo.
- **`TRACKING_PAYMENT_CARD_SECURITY_NOTE`** (`"Nós não recebemos os dados do seu cartão."`) —
  **não** é D6, embora comece negando. A régua prevê isso: *"algumas negações são a
  informação"*. É a reafirmação que o cliente quer antes de digitar cartão. Refutado de
  propósito.
- **`_privacy_receipt_unavailable_response`** (`f"Não é possível {action} agora."`) — o
  `{action}` **não** é um ref interno; é `"exportar seus dados"` / `"excluir sua conta"`,
  escolhido logo acima. Levantei como suspeita de D7a e refuto: está certo.

## E9. D5 é zero, e o que isso significa

**Nenhum caso de "zero como código secreto"** em texto de tela do Storefront — nem em `.vue`,
nem nas chaves do registro que a loja consome. Os 12 casos de D5 que a régua mediu vivem em
`help_text` do Admin. A loja do cliente entra com dívida zero nesse defeito, como o PDV.

---

# Onde a régua de operador e a voz da loja se chocaram

Três vezes. Nas três eu escolhi a loja, e nas três a escolha tem um motivo que não é gosto.

**1. `aparelho` × `dispositivo` (B3).** O `CLAUDE.md` manda dizer **dispositivo, nunca
aparelho**, com uma trava de AST em Python — e isenta `shopman/storefront/` e
`shopman/shop/omotenashi/` explicitamente, *"por concessão do dono"*. A régua repete a
isenção na §4.1 e a §5.5 manda o `WP-COPY-VUE-SWEEP` isentar `surfaces/storefront-nuxt/`
também. Então o Storefront **pode** dizer "aparelho". O que ele não pode é dizer os dois, e
diz: 9 ocorrências de cada em `conta/seguranca.vue`, uma frase com os dois juntos, e o par
`"Salvar este aparelho?"` → `"Dispositivo salvo por 30 dias."` no mesmo gesto. **Escolhi
`aparelho`** porque é a palavra que a voz da casa já usa no texto em segunda pessoa e a que
a concessão protege; adotar "dispositivo" seria importar o vocabulário de operador para
dentro da isenção que existe justamente para impedir isso. A regra que aplico aqui não é a
do `CLAUDE.md` — é a primeira lei da §4.2, **um nome por conceito**, que vale em toda
superfície, com ou sem isenção.

⚠️ Consequência assumida: quando o `WP-COPY-VUE-SWEEP` nascer, a varredura de `aparelh` vai
ter que **continuar isentando** `surfaces/storefront-nuxt/`, e essa isenção passa a ser
deliberada em vez de herdada. Se um dia o dono mudar de ideia, a troca é mecânica e vale a
superfície inteira de uma vez — que é exatamente a diferença entre ter um nome e ter dois.

**2. O vocabulário fechado, que a §4.2 manda escrever antes da Onda 2, aqui não pode ser o
do operador.** O modelo é o contrato do Marketing, mas o conteúdo não: a loja não tem
"disparar", não tem "destino", não tem "anúncio". O que ela tem é **sacola · pedido ·
fornada · encomenda · aviso**, e os atos **montar · enviar · acompanhar · repetir ·
cancelar**. Fechar isso é a pré-condição de metade da Parte B, e é decisão de dicionário,
não de PR avulso. Ver abaixo.

**3. Calor.** A régua proíbe calor (§1: *"'querido', 'juntos', emoji"*) e a concessão do
dono libera aqui. Eu **não** listei como achado nenhuma frase apenas por ser calorosa:
`"Bom apetite!"`, `"Que bom que chegou."`, `"Vamos montar seu café da manhã?"`, `"Acordou
cedo?"`, `"Está esperando por você no balcão."` ficam, e ficam certas. O que listei foi o
calor que **compra ambiguidade** — `"Saber das fornadas antes de todo mundo?"` promete
prioridade e entrega mensagem; `"Um cuidado especial hoje"` não diz qual; `"Seu aviso fica
guardado para a volta"` tem duas voltas na frase. Essa é a fronteira que usei: calor é
permitido, **promessa vaga não é**, e uma promessa vaga não deixa de ser vaga por ser
simpática.

---

# Onde eu procuraria o resto

1. **O vocabulário fechado do Storefront não existe, e sete achados dependem dele.** A §4.2
   manda fechá-lo no contrato da superfície *antes* da Onda 2, "senão a varredura troca um
   nome errado por outro". As camadas a fechar: **objeto** (sacola · pedido · encomenda ·
   fornada · aviso · oferta · cardápio), **atos** (montar · enviar · acompanhar · repetir ·
   cancelar · avisar), **grandezas** (item = unidade, pedido, pessoa) e **o aparelho**. Os
   dependentes: A12 (o aviso), B1 (tentar de novo), B2 (sacola × carrinho), B3 (aparelho ×
   dispositivo), B12 (finalizar × revisar × enviar × seguir × confirmar), C3 (ver o cardápio)
   e C4 (WhatsApp). O molde é
   [`docs/reference/marketing-surface-contract.md`](../../reference/marketing-surface-contract.md).
2. **Sete recusas silenciosas em um relatório não é coincidência — é um padrão de
   arquitetura.** `catch { }` vazio, ou `catch` que grava numa variável que aquele ramo do
   template não renderiza, aparece em `AddressPicker.acceptSuggestion`,
   `AddressLabelSheet.choose`, `enderecos.setDefaultAddress`, `WhatsappVerifyPanel.copyMessage`
   e `useWhatsAppConfirm` (cujo `failed` **nenhum dos dois consumidores destrutura**). Vale
   uma varredura própria, e ela é mecânica: todo `catch` de um handler de clique ou tem um
   destino de tela, ou tem um comentário dizendo por que o silêncio é a decisão certa. Hoje há
   comentários defendendo o silêncio (`"Etiqueta é açúcar"`) que estão certos sobre o fluxo e
   errados sobre a tela.
3. **`concierge/tools.py` conta `items_count` como LINHAS** (`order.items.count()`), enquanto
   a projection da loja conta **unidades**. Mesmo nome, duas grandezas — e uma delas alimenta
   o que o concierge do WhatsApp diz ao cliente. É o gêmeo exato do `tab_cleared` que o
   relatório do PDV achou, um andar abaixo da copy.
4. **A promessa dos termos não tem lastro na vitrine.** `terms.vue` diz `"Se acabar, a gente
   avisa e você decide se troca ou cancela, sem custo."` — mas na página do produto o aviso só
   existe quando `is_notifiable` é verdadeiro, e o canal nunca é nomeado. Fechar A11, A12 e o
   aviso de reposição fecha isso junto.
5. **A declaração de maioridade da ponte (`pages/a.vue`) aparece durante o spinner e some.**
   `exchangeToken()` roda no `onMounted` e navega embora assim que responde; o servidor
   carimba `adult_declaration` de qualquer jeito. Não é defeito de palavra — é de lugar, e é o
   que decide se a prova vale. **Escalar ao dono**, não corrigir por redação.
6. **A Onda 2 do Storefront (D2, D3, D5, D7 tela a tela) não foi feita.** Esta varredura entrou
   fundo em D1 e na recusa sem saída, como o dano manda numa loja, e colheu o que estava à
   vista dos outros. Sobraram sem leitura fina: `pages/busca.vue` e `SearchOverlay.vue` além
   dos chips, o `BottomSheet` do storefront (que a régua já registra como tendo a versão antiga
   de "tem mais abaixo" inline), e a copy de notificação
   (`shop/adapters/notification_*.py`), que é a mesma loja falando com a mesma pessoa por
   outro canal — e onde o B19 já mostrou que ela conta outra história.

---

## ~~Uma pergunta para o Pablo, e ela é de produto~~ — respondida em 18/09/2026

**Era:** "o endereço deve seguir o interruptor?" (achado A3.)

**Resposta do dono:** a pergunta partia de uma leitura errada. O endereço novo vai para a
agenda do cliente sempre, e tem que ir — ninguém redigita CEP a cada pedido. O interruptor
governa os **padrões** (qual endereço vem escolhido, pagamento, horário), não o
armazenamento. Não há promessa quebrada, e nada muda no Core: o conserto é de texto, e
está na ficha A3.
