# EXCELÊNCIA-STOREFRONT: laudo e plano da loja

Compromisso: DEV-2026-028. Brief: `docs/coordination/ROUNDS/EXCELENCIA-STOREFRONT.md`, sobre a
base `docs/coordination/ROUNDS/EXCELENCIA-base.md`. Medido em 16/11/2026 contra o `main`
`6a1398bba` e reconferido contra `95e37402d` (nenhum dos achados mudou entre os dois). Nenhum
código de produção foi escrito.

Foco do brief: nada que o cliente lê fica velho, a encomenda é a joia, confiança no pagamento.

## Sumário

- **Nenhum P0, 11 P1 e 14 P2** no perímetro da loja, mais 12 itens de fronteira.
- **A causa que mais se repete é de contrato, não de tela.** Três fatos não existem como fato
  na projeção que a loja lê, e cada tela inventa o seu: *quando o produto fica pronto*, *o que
  mudou depois que a página carregou* e *o que aconteceu com o dinheiro*. Oito dos onze P1
  saem daí (seção 4.1).
- **O que já é bom, e não se mexe:** o passo "Quando" (motivo com o produto e a hora, horários
  riscados), a recusa "Ficou indisponível enquanto você escolhia" com alternativas, o Pix com
  prazo e contagem, o cancelamento por prazo dizendo que o dinheiro voltou, o mínimo de entrega
  com saída em um toque, o acompanhamento que muda sozinho quando a loja aceita.
- **O salto que mais impressiona:** "A promessa de quando". Toda tela, do cardápio ao
  acompanhamento, diz a mesma frase calculada pelo servidor a partir da produção: "Fica pronto
  amanhã, terça, a partir das 15h". O botão do pão de amanhã passa a ser "Encomendar para
  amanhã". Nenhum dos seis benchmarks liga a promessa à produção real.
- **11 WPs em 4 ondas**, mais um sem data (a agenda das fornadas). O primeiro a delegar é o
  **WP-L01** (a promessa de quando, um fato só), junto com o **WP-L00** (harness da cliente de
  verdade).
- **As 4 decisões do dono foram respondidas em 16/11/2026** (seção 10): nenhum WP das ondas
  espera decisão.
- **O que este PR deixou de fora tem issue**: a execução do plano (#2567), as fronteiras
  (#2568) e as jornadas que não foram percorridas pela UI (#2569).

## 1. Como foi medido, e o que a medição não cobre

**Pilha isolada** (portas e banco do brief): Django `:8070` com o settings do harness de E2E,
banco `shopman_exc_loja`, loja `:3170`, Gestor `:3174`, worker de directives, Pix simulado.
`migrate` e `seed --flush --profile qa` rodaram até o fim (4.097 pedidos de histórico; a
vitrine do perfil `qa` deixa um produto esgotado, um nas últimas unidades, um com fornada só
amanhã e um pausado). A loja rodou com o Continuum ligado, como no app vivo
(`.do/app.alpha-subdomains.yaml:1090-1092`).

**Papéis**: cliente nova por código (o código chegou pelo sender de arquivo do harness, sem
SMS real), a mesma cliente voltando, uma segunda cliente em outro navegador lógico, e a
Gerente no Gestor. Nunca o superusuário.

**Leitura de código**: mapa de frescor da loja inteira (o que assina push, o que consulta, o
que fica parado), e a causa de cada achado com `caminho:linha`. As provas de maior peso foram
reconferidas linha a linha no `main` de hoje.

**Limites, ditos com nome:**

| O que | Por quê | Como ficou provado |
|---|---|---|
| Uma porta a mais que o brief: Stripe falso em `:8071` | o cartão não se exercita sem ele; a porta fica na dezena da loja e não colidiu com as revisões irmãs | - |
| Hosts `*.excloja.localhost` em vez de `127.0.0.1` | o navegador das revisões irmãs compartilha os cookies de `127.0.0.1` entre portas: a sessão de uma pilha apagava a da outra | - |
| Desempenho | a máquina tem 8 GB e rodou três revisões e vários agentes ao mesmo tempo (carga entre 12 e 34, swap quase cheio); cada chamada levou de 6 a 40 s, e o BFF desiste aos 25 s. Nenhum tempo de resposta medido aqui vale como achado | fora do laudo |
| Capturas da segunda metade | o painel do navegador ficou oculto e não compõe imagem; a partir das 19h a prova é o texto lido da página | texto citado no laudo |
| 1366 px | medido por script (largura, colunas, rolagem lateral) no cardápio, no acompanhamento e na lista de pedidos, sem captura | seção 3 |
| Preparo, pronto e entrega; cancelar depois do preparo | o pedido de teste era para amanhã (a casa fechou às 18h durante a medição), e a Cozinha só recebe no dia | leitura de código; roteiro na issue #2569 |
| Cobrança do cartão no aceite e anulação | o Stripe falso do repositório não implementa captura nem anulação (`shopman/shop/tests/e2e/fake_stripe.py`: "ROTA NÃO IMPLEMENTADA") | o aceite caiu no estado de falha de cobrança, que é o desenho para esse caso (`shopman/shop/services/payment.py:786-832`) |
| Endereço fora da área e taxa por distância | sem chave de mapas na pilha local | leitura de código; laudo de 06/11 |
| Virada do dia | não há relógio de teste no servidor | leitura de código |
| Cupom, favoritos, preferências, segurança da conta, busca | a janela de UI foi consumida pela máquina saturada | fora deste laudo; roteiro na issue #2569 |
| Entrar pelo WhatsApp | depende do provedor real | fora por limite do brief |

## 2. Histórico: o que já está no `main` (não reauditar)

Conferido contra o `main` de hoje, sem relistar:

- Laudo de 06/11 (P1 em #2188 a #2198, P2 em oito frentes) e laudo de encomendas de 09/11
  (#2253, #2254, #2257, #2289 a #2297). Os limites de envio de código por telefone, que o
  laudo de 06/11 apontava, já têm teto por hora e por dia
  (`shopman/shop/policies/login_code_ceiling.py:22-23`).
- Em voo e fora deste laudo: #2296 (o acompanhamento conta o desconto uma vez) e #2292 (fechar
  o dia avisa os pedidos, no Admin).
- Decisões que este plano respeita: pagar ao pedir (ADR-036); aceite em 5 min para o pedido do
  dia e 60 min para a encomenda ou para o pedido feito com a casa fechada; a cliente cancela
  sozinha antes do preparo e o valor volta inteiro; janela de 30 dias; a fornada da sacola não
  é piso absoluto; para a cliente só existe "Indisponível".
- Plano irmão do Gestor (#2545): o P0 de lá (lote cancelado solta a reserva da encomenda paga
  em silêncio, #2547) tem um lado da loja, registrado aqui como fronteira F-6.

## 3. Roteiro percorrido pela UI

Em 375 px, salvo onde dito. Horário da medição entre 13:20 e 19:35, com a casa aberta até
as 18h e fechada depois.

| # | Papel | Passos | Resultado |
|---|---|---|---|
| R1 | visitante | início, cardápio, produto com fornada só amanhã (Tabatière), adicionar, sacola | P1-01, P1-05, P2-01 |
| R2 | cliente nova | entrar por código, dar o nome, voltar ao checkout | passou; P2-03 |
| R3 | cliente nova | checkout: retirada, Quando (amanhã, 15h; calendário; data além das fornadas planejadas), Pix, revisão, enviar | passou; P1-06 |
| R4 | cliente nova | pagar o Pix simulado; ler o acompanhamento; abas Histórico, Resumo e Retirada | P1-07, P1-09 |
| R5 | ninguém aceita | 60 minutos sem aceite | cancelou sozinho e disse que o dinheiro voltou; P1-10 |
| R6 | cliente que volta, casa fechada | produto pronto (Croissant), sacola, checkout com entrega abaixo do mínimo, troca por retirada | passou; P1-02, P2-05, P2-12 |
| R7 | duas clientes | A abre o Melonpan (últimas unidades); B leva as últimas; A toca em Adicionar 14 min depois | P1-03, P1-04, P2-06 |
| R8 | cliente que volta | cartão: revisão, enviar, pagar no ambiente falso, voltar | passou; P2-09 |
| R9 | Gerente no Gestor | entrar, ver o pedido novo com "Cancela sozinho em 14h27", aceitar | o acompanhamento da cliente mudou sozinho; P1-07, P1-08 |
| R10 | cliente que volta | cancelar antes do preparo | cancelou na hora; P2-11 |
| R11 | cliente que volta | Conta, Pedidos | P1-10, P2-03 |
| R12 | 1366 px | cardápio (3 colunas, navegação de desktop), acompanhamento (duas colunas, 704 e 360 px), lista de pedidos: sem rolagem lateral | sem achado |

## 4. Laudo

Lentes: UX (UX/UI) · COPY · CONTR (contrato) · PERM (segurança e permissão) · OMO
(omotenashi-first) · MOB (mobile-first) · FLUXO (continuidade do fluxo) · PROM (a promessa de
produção).

Caminhos abreviados: `FE` = `surfaces/storefront-nuxt/app` · `BFF` =
`surfaces/storefront-nuxt/server` · `SP` = `shopman/storefront/presentation` · `SA` =
`shopman/storefront/api` · `PT` = `shopman/shop/projections/order_tracking.py` (fronteira) ·
`IMG` = `docs/plans/img/excelencia-storefront`.

### 4.1 A causa de desenho

A loja lê projeções que não carregam três fatos. Cada tela então monta o seu, com fonte e
frescor próprios, e as telas discordam entre si.

| Fato que falta como fato da projeção | Onde ele já existe no servidor | O que cada tela faz hoje | Achados |
|---|---|---|---|
| **Quando fica pronto** (dia, hora e de onde vem: pronto, fornada, encomenda) | `waitlist.next_batch_availability` (dia da fornada), `product_readiness` e `fulfillment_window` (hora) | cardápio e produto: só o selo "Lista de espera" (`SP/catalog.py:71-138`, `SP/product_detail.py:125-211`; a data é calculada e descartada em `shopman/shop/projections/catalog_context.py:681-687`). Produto: frase montada no cliente com o estado da loja em cache (`FE/presentation/product.ts:22-35`). Sacola: "Previsto para amanhã" (`SP/cart.py:458-478`). Checkout: "sai amanhã" calculado no cliente (`FE/presentation/cart.ts:186-212`) e "sai às 15:00" vindo de outro serviço (`SP/checkout.py:595-626`). Acompanhamento: mais uma (`SP/order_tracking.py`). São cinco fontes | P1-01, P1-02, P1-08, P2-02, P2-12 |
| **O que mudou depois que a página carregou** | o servidor já publica o canal público `stock-web` a cada mudança de disponibilidade (`shopman/shop/handlers/_sse_emitters.py:101-134`; permissão em `shopman/shop/eventstream.py:165`) | só o acompanhamento assina push (`FE/composables/useOrderTrackingStream.ts:83`). Produto, busca, coleção e início não consultam nem ouvem; o cardápio consulta a cada 30 s. A recusa do servidor não corrige a página | P1-03, P1-04, P2-08 |
| **O que aconteceu com o dinheiro** (cobrado quando, a loja responde até quando, voltou quando) | o prazo de aceite é um directive `confirmation.timeout`; pagamento e estorno são eventos do pedido | a revisão não fala de dinheiro; o prazo de aceite só chega à projeção no modo antigo de confirmação; o histórico perde o "Pago" depois do estorno e não tem "Devolvido" | P1-06, P1-07, P1-10, P2-11 |

Corrigir tela por tela não fecha. O conserto é publicar cada fato uma vez, no servidor, e
deixar cardápio, produto, sacola, checkout, acompanhamento e conta lerem dali.

### 4.2 P0

Nenhum provado no perímetro. O mais próximo é o P0-1 do plano do Gestor (lote cancelado depois
do aceite): do lado da loja a cliente também não fica sabendo. Está em F-6.

### 4.3 P1 no perímetro

| # | Achado | Lente | Prova | Causa |
|---|---|---|---|---|
| **P1-01** | **A página do pão de amanhã não diz que é para amanhã.** O produto com fornada só no dia seguinte mostra o selo "Lista de espera" e o botão "Adicionar". Não diz o dia, a hora, nem o que a expressão quer dizer. Ao adicionar, nada avisa. O dia aparece só na sacola e a hora só no terceiro passo do checkout. | PROM, COPY | `IMG/01`, `IMG/04`, `IMG/08`. A resposta de `/api/v1/storefront/products/TABAT/` traz `availability: "planned_ok"`, `availability_label: "Lista de espera"`, `available_qty: 7` e nenhum campo de data ou hora | contrato sem o fato (4.1); rótulo em `shopman/shop/omotenashi/copy.py:1895`, repassado por `FE/presentation/menu.ts:237-242` |
| **P1-02** | **"Disponível hoje na loja, com retirada grátis" com a casa fechada.** Às 18:38, com a loja fechada desde as 18h, a cliente A leu "Disponível hoje"; no mesmo minuto a cliente B leu "Retirada grátis na loja quando abrirmos, amanhã às 9h". A diferença: na A o estado da loja não tinha carregado. | PROM, CONTR | `IMG/13` | `FE/presentation/product.ts:28-34`: sem estado da loja, a frase afirma "hoje" (falha aberta). O estado vem do shell em cache (`FE/composables/useStorefrontShell.ts:6-13,30`) e a frase não usa a grade de retirada que o checkout usa: perto do fechamento, com a casa aberta, ela também diz "hoje" quando já não há horário de retirada |
| **P1-03** | **O produto fica velho na tela.** A página aberta continuou "Últimas unidades · Adicionar" 14 minutos depois de o item esgotar, inclusive ao voltar para a aba. O mesmo vale para busca, coleção e início, e a home promete "Disponibilidade em tempo real" em três lugares. | PROM, CONTR | `IMG/13` e `IMG/15` (mesma página, 18:38 e 18:52) | sem consulta nem push em `FE/pages/produto/[sku].vue:25-28`, `FE/pages/busca.vue:17`, `FE/pages/colecao/[ref].vue:37`; a home reaproveita a primeira carga (`FE/composables/useStorefrontHome.ts:6-13`). O canal `stock-web` existe e ninguém assina; `SA/urls.py:186-203` só expõe os eventos de pedido. A promessa de tempo real está em `shopman/shop/omotenashi/copy.py:306`, `:315`, `:324`, `:379` |
| **P1-04** | **Depois de o servidor dizer que acabou, a página continua vendendo.** O aviso "Ficou indisponível enquanto você escolhia" é bom. Ao fechá-lo, a página segue "Últimas unidades · Disponível hoje · Adicionar", e o toque seguinte repete o ciclo. | CONTR | `IMG/14`, `IMG/15` (depois do 409) | `FE/composables/useCartState.ts:380-398` só recarrega a sacola; o produto só é rebuscado pelo botão de erro (`FE/pages/produto/[sku].vue:193`); os cards leem `can_add_to_cart` parado (`FE/components/ProductTile.vue:122`, `ProductListItem.vue:129`) |
| **P1-05** | **A linha com promoção mostra dois valores que não fecham.** "1 × R$ 6,00 (riscado) R$ 5,10 cada" e, na mesma linha, o total "R$ 6,00". A revisão do pedido repete o "R$ 6,00". O plano do Gestor viu o mesmo de fora (F-18 de lá). | CONTR | `IMG/03`, `IMG/05` | duas correções de beta que se cruzaram: a linha fala o preço cheio para as linhas somarem o Subtotal (`SP/cart.py:66`, `:387-392`, de 05/11) e a linha repete o par do cardápio (`SP/cart.py:369-378`, de 06/11). Tela: `FE/pages/sacola.vue:229-231` e `:298`; `FE/pages/finalizar.vue:2431`. Decidido em 16/11: a linha mostra o preço com desconto, com o cheio riscado (decisão 1) |
| **P1-06** | **A revisão não diz o que acontece com o dinheiro.** Antes de "Enviar pedido" a cliente não lê que paga agora, que a loja confere em seguida, nem que o valor volta se a loja não confirmar. A descrição do sheet é "1 item · R$ 5,10". | OMO, CONTR | `IMG/05`; no cartão o sheet é igual (lido em 16/11, 19:26) | `FE/pages/finalizar.vue:2405-2516` não tem nenhuma frase sobre dinheiro; `FE/utils/checkoutFlow.ts:538-540` |
| **P1-07** | **Quem pagou não sabe até quando a loja responde.** A cliente lê "Pagamento recebido. A loja confirma sua encomenda para amanhã · A partir das 15h e avisa por aqui." O Gestor lê, no mesmo pedido, "Cancela sozinho em 14h27". Nesta frase também falta o "Se não puder, devolvemos o valor" que a frase irmã tem. | CONTR, OMO | `IMG/11`; texto do Gestor lido em 16/11, 19:32 | o prazo só entra na projeção com `cfg.mode == "auto_confirm"` (`PT:1841-1862`), e a loja opera em `auto_cancel` desde a ADR-036 (`config/instances/nelson.json`, canal `web`). No perímetro: o ramo `payment_confirmed` usa a frase sem devolução (`SP/order_tracking.py:1288-1293`) e o ramo `store_checking` usa a frase com devolução (`:1239-1250`, `:1509-1537`) |
| **P1-08** | **Retirada "a partir das 09h" para um pedido que a loja pode aceitar até as 10h.** Pedido feito com a casa fechada: o checkout oferece o primeiro horário da abertura, e o prazo de aceite começa a contar na abertura. No cartão, a tela não diz sequer que a casa está fechada. | PROM | checkout às 19:25 ("Hoje já encerramos as retiradas", "A partir das 09h · Mais cedo"); acompanhamento às 19:28 ("O valor está reservado no seu cartão e só é cobrado quando a loja aceitar seu pedido para amanhã · A partir das 09h"); Gestor: "Cancela sozinho em 14h27" | a grade de retirada não conhece o prazo de aceite (fronteira F-12); o ramo do cartão autorizado volta antes do estado "loja fechada" (`PT:1262` antes de `:1273`) |
| **P1-09** | **No celular, o Pix mostra primeiro o QR Code, que não serve no próprio aparelho.** O botão "Copiar código" fica na segunda dobra, e o prazo é de 10 minutos. | MOB | `IMG/07` | `FE/components/PaymentBlock.vue:125-155`: QR, instrução, código e botão nessa ordem em qualquer largura |
| **P1-10** | **O dinheiro some do histórico.** Com o pedido pago, o histórico tinha "Recebido" e "Pago". Depois do cancelamento por prazo ficou "Recebido" e "Cancelado": o "Pago" sumiu e não entrou "Devolvido". O resumo do pedido pago dizia só "Pagamento recebido", sem valor, meio nem hora. Em Conta, o card diz "Cancelado · R$ 5,10". | CONTR | `IMG/10`, `IMG/12`; lista de pedidos lida em 16/11, 19:10 | a aba mostra `progress_steps` (`FE/pages/pedido/[ref]/index.vue:857-859`); o passo de pagamento depende do saldo capturado, que zera com o estorno (`PT:1479`, `:1628-1634`). Os eventos de estorno têm rótulo (`SP/order_tracking.py:66`, `:68`) mas alimentam um campo que a tela não mostra |
| **P1-11** | **Faltou estoque no último passo: a saída é um aviso que manda "ajustar o carrinho".** Na sacola, o mesmo fato tem sheet com o item e alternativas. No envio do pedido, vira toast, sem o item, sem atualizar a tela e sem levar a lugar nenhum. Outras recusas do envio chegam com texto de sistema ("Reserva expirada para este check."). | FLUXO, COPY | leitura de código (não reproduzido pela UI) | a recusa nasce com o item no contexto (`shopman/shop/services/stock.py:960-980`), o mapeamento para a tela descarta código e contexto (`shopman/shop/services/checkout.py:207-233`), e a tela cai no ramo genérico (`FE/pages/finalizar.vue:1450-1518`). Jargão em `packages/orderman/shopman/orderman/services/commit.py:388-431` |

### 4.4 P2 no perímetro

| # | Achado | Lente | Prova | Causa |
|---|---|---|---|---|
| P2-01 | O cardápio salta: abre por "Rústicos" e, um instante depois, entram "Destaques" e a chave "Mostrar só disponíveis" no topo | UX | `IMG/02` | o esqueleto do Continuum não traz a seção de destaques nem o filtro (`FE/pages/menu.vue:36-62`) |
| P2-02 | "Tabatière sai amanhã", "sai às 15:00", "Avisamos quando sair", "Assim que a fornada sair": verbo genérico, e a regra de 16/11 é "fica pronto" | COPY | `IMG/08` | `FE/presentation/cart.ts:211`; `SP/order_tracking.py:1454`, `:1530`, `:1837`; fora do perímetro: `shopman/shop/services/fulfillment_window.py:433`, `:532`, `:538` (F-4) |
| P2-03 | Termos: o título da aba é "Checkout"; a legenda do calendário diz "Agendamentos até"; "Enviamos um código por SMS para este número" aparece antes de enviar; no pedido cancelado o botão é "Acompanhar"; "Refazer" na lista e "Repetir pedido" no acompanhamento; "amanhã" minúsculo como valor isolado | COPY | R2, R3, R11 | `FE/pages/finalizar.vue:1543-1545`, `:1970`; `FE/pages/entrar.vue:775`; `FE/pages/conta/pedidos.vue:141`, `:149` |
| P2-04 | O cabeçalho corta "Fechado agora. Abrimos amanhã às 9h" em 375 px: some justamente a hora (213 px disponíveis para 247 px de texto) | MOB | medido em R6 | `FE/components/ShopHeader.vue:114-138` |
| P2-05 | Dois convites no caminho da compra: instalar o app sobre o produto e "Saber das fornadas antes de todo mundo?" sobre a sacola, cobrindo o botão de finalizar | OMO, FLUXO | `IMG/16`, `IMG/17` | a lista de rotas vetadas não inclui produto (`FE/composables/usePwaInstall.ts:22-26`) nem produto e sacola (`FE/presentation/auth.ts:149-154`); a coordenação é por página, não por visita (`FE/composables/useShopInvite.ts:27-50`). Decidido em 16/11: convite só depois do pedido enviado (decisão 3) |
| P2-06 | A primeira adição de quem nunca entrou pode criar uma reserva fantasma: o BFF desiste aos 25 s, o Django já reservou numa sessão que se perde, e a nova tentativa abre outra. Um toque, duas reservas; a fantasma segura o item por 30 min (ou sem prazo, numa fornada futura) | CONTR, PROM | R7: duas reservas de Melonpan com 3 s de diferença para um toque; com duas unidades vendáveis, a fantasma levou uma | `BFF/utils/djangoProxy.ts:31`, `:88-126`, `:289`: a semente cria o `csrftoken`, não a sessão; a sessão nasce na primeira escrita (`shopman/storefront/cart.py:153`) |
| P2-07 | A reserva da sacola dura 30 minutos e a cliente não sabe; a contagem da vaga na fila usa o relógio do aparelho, sem a correção que o acompanhamento faz | PROM | leitura de código | `FE/pages/sacola.vue:37-45`; correção existente em `FE/presentation/deadline.ts:8-12`. Decidido em 16/11: a sacola mostra até quando guarda (decisão 4) |
| P2-08 | O checkout não se atualiza ao voltar para a aba, e "hoje", "amanhã" e os limites do calendário vêm do relógio do aparelho. Corte e virada do dia só aparecem no envio | PROM | leitura de código | `FE/pages/finalizar.vue:346`, `:557`; `FE/utils/checkoutFlow.ts:107-140`; `FE/presentation/cart.ts:117`, `:154`, `:174`, `:187`, `:205` |
| P2-09 | Cartão pede dois toques: "Enviar pedido" leva ao acompanhamento, e só lá aparece "Pagar com cartão" | FLUXO | R8 | o envio sempre navega para o acompanhamento (`FE/pages/finalizar.vue:1425`) |
| P2-10 | "Enviar resumo" leva "Retirada: amanhã · A partir das 09h": data relativa num texto que vai ser lido depois, por outra pessoa | COPY | link lido em R10 | `share_text` da projeção (`FE/pages/pedido/[ref]/index.vue:543`) |
| P2-11 | Cancelado pela cliente com cartão: o diálogo promete "A reserva no seu cartão será desfeita, e nada será cobrado"; a tela seguinte diz só "Conforme sua solicitação". A confirmar com o Stripe falso completo | CONTR | R10 (inconclusivo: a anulação falhou no ambiente falso) | `SP/order_tracking.py:621-669` |
| P2-12 | Com a casa fechada, a sacola não diz que o pedido fica para amanhã; a cliente descobre no checkout | PROM | R6 | a linha da sacola só fala de data quando há fornada futura (`SP/cart.py:458-478`) |
| P2-13 | Nenhuma jornada com dados roda em Playwright dentro do app da loja: as duas que existem (retirada com Pix, entrega com cartão) vivem no pytest do Django e param antes do aceite | CONTR | `surfaces/storefront-nuxt/tests/e2e/README.md`; `shopman/shop/tests/e2e/test_storefront_e2e.py:569`, `:787` | o `playwright.config.ts` da loja sobe um backend vazio |
| P2-14 | `docs/reference/qa-seed-scenarios.md` cita três SKUs que saíram do catálogo em 23/09 (PURIN, TEA-JELLY, MELON-PAN) | CONTR | `config/management/commands/seed.py:747-760` | documento não acompanhou o seed |

### 4.5 Reclassificados (não são defeito)

- **Sacola vazia logo depois de adicionar**: foi a minha navegação (recarga antes de a resposta
  voltar) somada aos cookies compartilhados de `127.0.0.1`. O que sobra de real é o P2-06.
- **"Não conseguimos cobrar o cartão" depois do aceite**: o Stripe falso não captura. O estado
  mostrado é o desenho para falha de cobrança sem anulação possível.
- **Acompanhamento sem push para quem não entrou**: intencional (`SA/tracking.py:342-366`).
- **Limite de envio de código**: já tem teto por hora e por dia.
- **Adição que estoura o tempo e é repetida**: a repetição é idempotente (quantidade absoluta).

## 5. Fronteiras (registrar, não mexer)

As projeções que a loja lê moram em `shopman/shop/projections/` e são lidas também pelo
WhatsApp (`shopman/shop/services/conversation.py`), pelos avisos
(`shopman/shop/services/notification.py`) e pelo PDV. Por isso ficam fora dos WPs. Todas vão na
issue #2568, menos a F-6, que já tem a #2547.

| # | O que é | Por que afeta a loja | De quem é | Quem mais sente |
|---|---|---|---|---|
| F-1 | A data da próxima fornada é calculada e descartada na montagem do catálogo (`shopman/shop/projections/catalog_context.py:681-687`, `:865`, `:874-876`) | P1-01. O WP-L01 contorna lendo o mesmo serviço; o certo é o contexto carregar a data | shop (projeções) | WhatsApp, PDV |
| F-2 | O prazo de aceite só entra na projeção do acompanhamento no modo `auto_confirm` (`PT:1841-1862`, `:1878-1891`) | P1-07 e P1-08: sem isso a loja não tem como mostrar "a loja responde até" | shop (projeções) | WhatsApp |
| F-3 | O histórico do pedido perde o pagamento depois do estorno e não tem passo de devolução (`PT:1479`, `:1628-1634`) | P1-10 | shop (projeções) | WhatsApp |
| F-4 | Frases que a loja mostra e que são escritas fora dela: "Ajuste o carrinho" (`shopman/shop/services/stock.py:960-980`), "sai às" (`shopman/shop/services/fulfillment_window.py:433`, `:532`, `:538`), o texto de sistema das recusas do commit (`packages/orderman/shopman/orderman/services/commit.py:388-431`), "Disponibilidade em tempo real" e "Lista de espera" (`shopman/shop/omotenashi/copy.py:306-385`, `:1895`); e o mapeamento que descarta código e item da recusa (`shopman/shop/services/checkout.py:207-233`) | P1-01, P1-03, P1-11, P2-02 | shop e Core | PDV, WhatsApp |
| F-5 | A reserva de sacola numa fornada futura não tem prazo, e a sessão abandonada só é limpa em 48 h (`shopman/shop/management/commands/cleanup_stale_sessions.py`). Na medição, três sessões abandonadas seguravam 3 das 10 Tabatières de amanhã | não trava a venda (o pedido tem prioridade sobre a sacola), mas conta como comprometido na sugestão de produção | shop (estoque) e Produção | Produção |
| F-6 | Lote cancelado, atrasado ou que rende menos não vira fato do pedido (P0-1 e F-6 do plano do Gestor, #2547) | a cliente com encomenda paga não é avisada. Quando o fato existir, o WP-L06 mostra | shop (estoque) e Produção | Gestor, PDV |
| F-7 | O Stripe falso do harness não implementa captura, anulação nem estorno (`shopman/shop/tests/e2e/fake_stripe.py`) | nenhuma jornada automatizada de cartão passa do aceite; J6 e J8 dependem disso | harness de E2E do shop | Gestor, PDV |
| F-8 | Duas estimativas de "fica pronto às": tempo fixo na loja (`PT:1896-1912`), mediana no Gestor (F-4 do plano do Gestor) | a operadora diz uma hora e a cliente lê outra | shop (projeções) | Gestor |
| F-9 | Pedido de hoje com hora combinada vai à Cozinha no aceite (F-5 do plano do Gestor, #2548) | a promessa "a partir das 17h" feita na loja é atendida cedo demais | lifecycle e Core | Cozinha, Gestor |
| F-10 | A Concierge | frente própria (CONCIERGE-R3) | Concierge | - |
| F-11 | `docs/reference/qa-seed-scenarios.md` desatualizado (P2-14) | o roteiro de QA manda testar SKUs que não existem | docs | todos |
| F-12 | A grade de retirada não conhece o prazo de aceite: oferece o primeiro horário da abertura a um pedido que a loja pode aceitar até uma hora depois (`shopman/shop/services/fulfillment_window.py`) | P1-08 | shop (janela de atendimento) | PDV, WhatsApp |

## 6. O salto

| # | Ideia | Ganho para a cliente | Custo | Benchmark |
|---|---|---|---|---|
| S1 | **A promessa de quando.** Cardápio, produto, sacola, checkout e acompanhamento dizem a mesma frase, calculada no servidor a partir da produção: "Pronto agora", "Fica pronto hoje às 15h", "Fica pronto amanhã, terça, a partir das 15h". O botão do pão de amanhã é "Encomendar para amanhã". O que a tela promete é o que o envio do pedido confere. | Ela decide na primeira tela, sem montar a sacola para descobrir o dia. Fecha P1-01, P1-02, P1-08. | WP-L01, L02, L03 e L05. Leitura de serviços que já existem. | Nenhum faz: todos vendem contra um número digitado. A Starbucks e a Toast prometem hora por capacidade, não por produção. |
| S2 | **Loja viva.** A disponibilidade chega por push ao cardápio, ao produto, à busca e à sacola. O item que acaba se transforma na frente da cliente, já com a saída ao lado: a próxima fornada para encomendar, ou a alternativa. O que fica pronto acende. | Acaba o toque em botão morto e a promessa de "tempo real" passa a ser verdade. Fecha P1-03 e P1-04. | WP-L04. O servidor já publica o canal; falta a rota e quem assine. | A Toast marca "Out of Stock" na hora mas admite a corrida da última unidade; a Shopify só revalida no pagamento; o Hotplate reserva, mas não avisa quem está olhando. |
| S3 | **A linha do tempo do dinheiro.** Antes de pagar: "Você paga agora. A loja confirma em até 1 hora. Se não confirmar, o valor volta na hora para a mesma conta." Depois: "Pix de R$ 5,10 pago às 13:34 · A loja responde até 14:34", e no fim "Devolvido às 14:34". | Nunca fica dúvida sobre o que foi cobrado. Fecha P1-06, P1-07 e P1-10. | WP-L05 e WP-L06, com F-2 e F-3. | Nenhum mostra dinheiro e pedido na mesma linha do tempo. A reclamação mais repetida do iFood e do Rappi é justamente estorno que ninguém vê. |
| S4 | **A agenda das fornadas.** Uma página "Fornadas da semana": o que fica pronto em cada dia, a que horas, e se ainda dá para encomendar. Reservar o pão de sexta em dois toques, da própria agenda. | Encomendar fica melhor que ir à padaria: ela vê a semana e garante o pão antes de a fila existir. | WP-L10. **Não agora** (decisão 2): fica como direção, fora das ondas. Lê a produção planejada, sem escrever nela. | O Hotplate tem o "drop" com contagem regressiva, alimentado à mão; ninguém publica a produção planejada. |
| S5 | **Reserva com prazo à vista.** A sacola diz até quando guarda os itens ("Guardamos seus itens até 19:18") e renova a cada gesto, sem cronômetro ansioso. Quando vence, diz o que ainda está lá. | Ela sabe o que é dela e por quanto tempo. | WP-L11, depois do L03. Aprovado (decisão 4). | Só o Hotplate mostra o prazo da reserva, com cronômetro obrigatório de 5 minutos. |

## 7. WPs

Regras comuns a todos:

- A sessão segue a seção **"Teste como um operador de verdade"** de
  `docs/coordination/ROUNDS/EXCELENCIA-base.md`: pela UI, como cliente nova por código ou
  cliente que volta, e a operadora do Gestor só para aceitar ou recusar. Nunca como
  superusuário, sem atalho de API, Admin ou banco, em 375 px e depois em 1366 px.
- WP que muda tela mostra **prévia local ao dono antes de enfileirar**.
- WP que muda contrato regenera `contracts/projections/*.json` e commita os dois lados juntos.
- Voz da loja: português, "aparelho", voz feminina da Concierge, "Indisponível" como único
  estado de falta, "fica pronto" e nunca "sai". Regras em `docs/reference/omotenashi-copy.md`
  e `docs/reference/suite-vocabulary.md` (seção 5).
- Fora de todos: `shopman/storefront/concierge/`, `shopman/shop/` (services, projeções,
  `lifecycle.py`, copy), `packages/`, o Gestor e o PDV. O que um WP precisar dali está na
  seção 5 e na issue #2568; o WP entrega o lado da loja e para na fronteira.
- A pilha de teste: a seção 1 deste plano, com hosts próprios (`*.localhost`) para não dividir
  cookies com outra pilha.

Tamanhos: P (até meio dia) · M (um dia) · G (uma sessão cheia).

---

### WP-L00 · Harness da cliente de verdade

- **Objetivo:** a loja ganha uma suíte Playwright que roda contra o Django da pilha, com
  entrada por código de verdade, e a jornada J1 nasce nela.
- **Achados que fecha:** P2-13.
- **Dependências:** nenhuma. (J6 e J8 dependem da F-7.)
- **Arquivos:** `surfaces/storefront-nuxt/playwright.journeys.config.ts` (novo),
  `surfaces/storefront-nuxt/tests/journeys/**` (novo), `surfaces/storefront-nuxt/package.json`
  (script `test:journeys`), `surfaces/storefront-nuxt/tests/e2e/README.md`.
- **Fora do escopo:** o CI; o pytest de E2E do Django, que continua; o Stripe falso (F-7).
- **Pronto quando:**
  - roteiro: cliente nova abre o cardápio, adiciona um item pronto, entra por código, escolhe
    retirada para hoje, paga o Pix simulado e vê o pedido no acompanhamento; a operadora
    aceita no Gestor e a tela da cliente muda sozinha. Capturas em 375 e 1366.
  - testes: `npm run test:journeys` verde, com a J1 escrita com os mesmos papéis e passos.
- **Muda tela:** não. **Tamanho:** M.
- **Brief:** leia `docs/coordination/ROUNDS/EXCELENCIA-base.md` ("Teste como um operador de
  verdade"), a seção 1 deste plano, `surfaces/storefront-nuxt/tests/e2e/README.md` e
  `scripts/run_storefront_e2e.sh` (de lá saem o sender de código por arquivo e o settings do
  harness). Monte a suíte em `tests/journeys/`, contra uma loja compilada e um Django já de pé
  (URLs por variável de ambiente; a suíte recusa rodar sem elas). O código de acesso é lido do
  arquivo do sender, como a cliente leria o SMS. O aceite é feito pela tela do Gestor. Escreva
  a J1 e um README de como subir a pilha.

### WP-L01 · A promessa de quando, um fato só

- **Objetivo:** cada produto e cada linha da sacola carregam, vindos do servidor, quando ficam
  prontos e de onde vem essa resposta.
- **Achados que fecha:** a base de P1-01, P1-02 e P2-12; a parte de contrato de P1-05.
- **Dependências:** nenhuma (a decisão 1 está tomada).
- **Arquivos:** `shopman/storefront/presentation/promise.py` (novo),
  `shopman/storefront/presentation/catalog.py`, `product_detail.py`, `cart.py`,
  `shopman/storefront/api/serializers.py`, `contracts/projections/*.json`,
  `surfaces/storefront-nuxt/app/types/shopman.ts`, testes de projeção.
- **Fora do escopo:** qualquer tela (L02, L03, L05); o acompanhamento (L06); mexer em
  `catalog_context.py` (F-1).
- **Pronto quando:**
  - roteiro: pela API da pilha, o produto pronto, o das últimas unidades, o de fornada só
    amanhã e o indisponível devolvem a promessa certa às 10h, depois do fechamento e num
    domingo; a linha da sacola devolve a mesma. Como a tela ainda não muda, a prova deste WP é
    a resposta da API lida ao lado da tela atual.
  - testes: projeção com os quatro estados de vitrine do perfil `qa`, casa aberta e fechada,
    e contrato gerado.
- **Muda tela:** não. **Tamanho:** G.
- **Brief:** leia a seção 4.1 e os achados P1-01 e P1-02. Publique um objeto de promessa
  (`kind`: pronto, fornada ou encomenda; dia; hora de pronto; frase curta já escrita) no card
  do cardápio, no detalhe do produto e na linha da sacola. A frase nasce no servidor, de uma
  função só, lendo `waitlist.next_batch_availability`, `product_readiness` e a mesma grade de
  retirada que o checkout usa (`fulfillment_window`), sem alterá-los. Casa fechada, corte do
  dia e ausência de dado devolvem a promessa mais conservadora, nunca "hoje". Verbo: "fica
  pronto". Pela decisão 1, publique também, já formatados, o total da linha com desconto e o
  total cheio para riscar.

### WP-L02 · O produto e o cardápio dizem quando

- **Objetivo:** a página do produto e o card do cardápio mostram a promessa do servidor, e o
  pão de amanhã se oferece como encomenda.
- **Achados que fecha:** P1-01, P1-02.
- **Dependências:** WP-L01.
- **Arquivos:** `surfaces/storefront-nuxt/app/pages/produto/[sku].vue`,
  `app/presentation/product.ts`, `app/presentation/menu.ts`, `app/components/ProductTile.vue`,
  `app/components/ProductListItem.vue`, testes.
- **Fora do escopo:** push (L04); sacola (L03).
- **Pronto quando:**
  - roteiro: cliente nova abre o produto de fornada só amanhã e lê o dia e a hora antes de
    tocar em qualquer coisa; o botão diz "Encomendar para amanhã"; ao tocar, a confirmação
    repete o dia. Com a casa fechada, o produto pronto diz quando dá para retirar. Capturas em
    375 e 1366. Esta é a J2.
  - testes: apresentação do produto e do card para os quatro estados; a J2 em Playwright.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia os achados P1-01 e P1-02 e as capturas `IMG/01` e `IMG/13`. Troque a frase
  montada no cliente (`inStorePickupLine`) pela promessa do WP-L01, na página e nos cards. O
  selo "Lista de espera" dá lugar à promessa com dia e hora. Não escreva regra de horário no
  cliente: se a promessa não veio, a tela não promete.

### WP-L03 · A sacola fala a mesma promessa, e o preço fecha

- **Objetivo:** a linha da sacola mostra a promessa do servidor e um preço que não se
  contradiz.
- **Achados que fecha:** P1-05 (sacola e checkout: o total da linha e o resumo da revisão),
  P2-02 (sacola), P2-12.
- **Dependências:** WP-L01.
- **Arquivos:** `surfaces/storefront-nuxt/app/pages/sacola.vue`, `app/presentation/cart.ts`,
  `app/components/CartSummaryBreakdown.vue`, `app/components/CartLineTotal.vue`, as linhas e
  o resumo de `app/pages/finalizar.vue`, `shopman/storefront/presentation/cart.py`, testes.
- **Fora do escopo:** o restante do checkout e da revisão (L05); prazo da reserva (L11).
- **Executado no #2673.** O preço da revisão entrou aqui, e não no L05: a sacola e o checkout
  mostram a linha e o resumo pelo mesmo componente, e migrar só a sacola deixaria o checkout
  com linha cheia sob um Subtotal com desconto.
- **Pronto quando:**
  - roteiro: cliente adiciona um item em promoção e um de fornada futura; cada linha mostra um
    preço só e a promessa; o resumo fecha com as linhas. Com a casa fechada, a sacola diz para
    quando fica o pedido. Capturas em 375 e 1366.
  - testes: apresentação da sacola (linha com promoção, com cupom, sem desconto).
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia o achado P1-05, a captura `IMG/03` e os comentários de
  `shopman/storefront/presentation/cart.py:369-392`, que explicam por que a linha ficou com
  dois valores. Aplique a decisão 1: unitário e total da linha com desconto, cada um com o
  cheio riscado ao lado; o Subtotal é a soma das linhas com desconto; o resumo diz quanto a
  promoção economizou e só subtrai cupom e pontos. Troque "Previsto para" e "sai" pela
  promessa do WP-L01.

### WP-L04 · Loja viva

- **Objetivo:** o que a cliente lê sobre disponibilidade e sobre a casa estar aberta muda
  sozinho, por push, e a recusa do servidor corrige a tela.
- **Achados que fecha:** P1-03, P1-04, P2-01.
- **Dependências:** WP-L02 (divide a página do produto).
- **Arquivos:** `shopman/storefront/api/urls.py` (rota de eventos do canal de estoque da
  loja), `surfaces/storefront-nuxt/server/routes/sse/loja.ts` (novo),
  `server/utils/eventStream.ts`, `app/composables/useLiveStore.ts` (novo),
  `app/composables/useCartState.ts`, `useStorefrontHome.ts`, `useStorefrontShell.ts`,
  `app/pages/produto/[sku].vue`, `menu.vue`, `busca.vue`, `colecao/[ref].vue`, `index.vue`,
  testes.
- **Fora do escopo:** o emissor (`_sse_emitters.py`), que já publica; o acompanhamento.
- **Pronto quando:**
  - roteiro: duas clientes. A abre o produto das últimas unidades; B leva as últimas. Sem
    recarregar, a tela de A passa a "Indisponível" com a saída ao lado em poucos segundos. Com
    o push derrubado, a consulta de reserva faz o mesmo em até um minuto. Se A tocar antes,
    o aviso aparece e, ao fechá-lo, a página já está certa. Capturas em 375 e 1366. É a J3.
  - testes: composable (evento, reconexão, consulta de reserva), e a J3 com dois contextos.
- **Muda tela:** sim (prévia). **Tamanho:** G.
- **Brief:** leia a ADR-016, os achados P1-03 e P1-04 e
  `shopman/shop/handlers/_sse_emitters.py:1-60`. O evento só avisa; a tela refaz a consulta
  canônica. Assine o canal de estoque da loja pelo BFF, no molde de
  `server/routes/sse/pedido/[ref].ts`. Um composable só serve produto, cards, busca, coleção e
  início; a consulta periódica fica como reserva, em cadência calma. Trate o 409 como
  verdade: atualize o produto e os cards. Revalide o estado da casa (aberta, fechada) do mesmo
  jeito. O esqueleto do cardápio reserva o espaço de "Destaques" e do filtro para não saltar.

### WP-L05 · O checkout que não envelhece e diz do dinheiro

- **Objetivo:** o checkout se mantém verdadeiro enquanto está aberto, e a revisão diz o que
  vai acontecer com o dinheiro.
- **Achados que fecha:** P1-06, P1-11 (lado da loja), P2-03 (título e calendário), P2-08,
  P2-09. O preço da revisão (P1-05) já foi fechado pelo WP-L03 (#2673).
- **Dependências:** WP-L01 (promessa e total da linha).
- **Arquivos:** `surfaces/storefront-nuxt/app/pages/finalizar.vue`,
  `app/utils/checkoutFlow.ts`, `shopman/storefront/presentation/checkout.py`,
  `shopman/storefront/api/views.py`, testes.
- **Fora do escopo:** a grade de retirada (F-12); as frases escritas no shop (F-4).
- **Pronto quando:**
  - roteiro: cliente deixa o checkout aberto, volta depois do fechamento e a tela já mostra
    "Hoje já encerramos as retiradas" sem ela tocar em nada. A revisão diz, em uma frase, que
    paga agora, até quando a loja confirma e que o valor volta se não confirmar. No cartão, um
    toque leva ao pagamento. Com o item esgotado entre a revisão e o envio, a tela fecha a
    revisão, diz qual item e oferece as alternativas. Capturas em 375 e 1366. É a J5.
  - testes: fluxo do checkout (retorno à aba, erros de envio com item), e a J5 e a J8.
- **Muda tela:** sim (prévia). **Tamanho:** G.
- **Brief:** leia os achados P1-06, P1-11, P2-08 e P2-09. "Hoje" e os limites do calendário
  vêm do servidor (publique a data e a hora do servidor na projeção do checkout), não do
  relógio do aparelho. Refaça a consulta ao voltar o foco. Na view, deixe passar código e item
  das recusas de estoque, como já se faz com `total_changed`, e trate cada código com destino
  (fechar a revisão, mostrar o item, oferecer a alternativa); nenhuma recusa termina em toast
  sozinho. A frase do dinheiro usa o prazo de 5 ou 60 minutos da política do canal. Título da
  aba: "Finalizar pedido". Legenda: "Encomendas até". Vocabulário: sacola, nunca carrinho. O
  total da linha e o resumo da revisão já seguem a decisão 1 (WP-L03): não refaça. Na revisão
  falta trocar o selo "Lista de espera" e o "Previsto para" pela promessa do WP-L01, como a
  sacola já faz.

### WP-L06 · O dinheiro às claras no acompanhamento

- **Objetivo:** o acompanhamento e a conta dizem sempre o que foi cobrado, até quando a loja
  responde e o que voltou.
- **Achados que fecha:** P1-07, P1-08 (lado da loja), P1-10, P2-03 (Acompanhar, Refazer,
  maiúscula), P2-10, P2-11.
- **Dependências:** F-2 e F-3 para o prazo e para o passo de devolução. O que não depende
  delas (frase com devolução, eventos de dinheiro no histórico, lista de pedidos, resumo com
  valor e hora) sai neste WP.
- **Arquivos:** `shopman/storefront/presentation/order_tracking.py`,
  `surfaces/storefront-nuxt/app/pages/pedido/[ref]/index.vue`,
  `app/presentation/orderTracking.ts`, `app/pages/conta/pedidos.vue`, testes.
- **Fora do escopo:** `shopman/shop/projections/order_tracking.py` (F-2, F-3, F-8); o preço da linha no resumo do pedido, que é do #2296 e segue a decisão 1.
- **Pronto quando:**
  - roteiro: cliente paga uma encomenda e lê o valor, o meio, a hora e a frase da devolução;
    a operadora recusa no Gestor; a cliente lê "Devolvido" com valor e hora no histórico, e a
    lista de pedidos diz que o valor voltou. Cancelar antes do preparo, com cartão, diz o que
    aconteceu com a reserva. Capturas em 375 e 1366. São a J4 e a J6.
  - testes: apresentação do acompanhamento (pago aguardando, cancelado com estorno, cartão
    com a casa fechada), e a J4 em Playwright.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia os achados P1-07, P1-08 e P1-10 e as capturas `IMG/10` a `IMG/12`. No ramo
  `payment_confirmed`, use a frase que promete a devolução, como no ramo vizinho. Mostre no
  histórico os eventos de dinheiro que a projeção já entrega no campo `timeline`. O resumo diz
  "Pix de R$ 5,10, pago às 13:34". Na lista, pedido cancelado diz "Ver pedido" e o destino do
  dinheiro; o gesto de repetir chama "Repetir pedido" em toda tela. O texto de "Enviar
  resumo" leva a data por extenso. Quando a F-2 existir, mostre "A loja responde até 14:34".

### WP-L07 · Pix no celular

- **Objetivo:** no celular, copiar o código é o primeiro gesto do pagamento.
- **Achados que fecha:** P1-09.
- **Dependências:** nenhuma.
- **Arquivos:** `surfaces/storefront-nuxt/app/components/PaymentBlock.vue`, teste do
  componente.
- **Fora do escopo:** cartão; o prazo do Pix.
- **Pronto quando:**
  - roteiro: cliente chega ao Pix em 375 px e vê, sem rolar, o prazo, o valor e "Copiar
    código"; o QR fica um toque abaixo. Em 1366 px o QR segue à vista. Capturas nas duas.
  - testes: componente nas duas larguras.
- **Muda tela:** sim (prévia). **Tamanho:** P.
- **Brief:** leia o achado P1-09 e a captura `IMG/07`. Em tela estreita, a ordem é prazo,
  valor, botão de copiar e, recolhido, o QR ("Mostrar QR Code"). Em tela larga, o QR primeiro.

### WP-L08 · A primeira adição não cria fantasma

- **Objetivo:** um toque de quem nunca entrou gera uma reserva só, mesmo com a rede lenta.
- **Achados que fecha:** P2-06.
- **Dependências:** nenhuma.
- **Arquivos:** `surfaces/storefront-nuxt/server/utils/djangoProxy.ts`,
  `shopman/storefront/api/surface.py`, testes do BFF e da view.
- **Fora do escopo:** o prazo das reservas (F-5).
- **Pronto quando:**
  - roteiro: cliente nova, com a rede estrangulada até estourar o tempo do BFF, toca uma vez
    em Adicionar; a sacola acaba com uma unidade e o estoque com uma reserva. É a J9.
  - testes: BFF (a semente garante a sessão antes da primeira escrita) e a J9.
- **Muda tela:** não. **Tamanho:** P.
- **Brief:** leia o achado P2-06. A semente que hoje garante o `csrftoken` passa a garantir
  também a sessão do Django antes da primeira escrita, para a nova tentativa cair na mesma
  sessão. Não crie sessão em leitura pública com cache de borda.

### WP-L09 · Miudezas que a cliente lê

- **Objetivo:** cabeçalho, entrada e convites deixam de atrapalhar.
- **Achados que fecha:** P2-03 (entrada), P2-04, P2-05.
- **Dependências:** nenhuma (a decisão 3 está tomada).
- **Arquivos:** `surfaces/storefront-nuxt/app/components/ShopHeader.vue`,
  `app/pages/entrar.vue`, `app/composables/usePwaInstall.ts`, `app/presentation/auth.ts`,
  `app/composables/useShopInvite.ts`, testes.
- **Fora do escopo:** o texto dos convites; a instalação em si.
- **Pronto quando:**
  - roteiro: com a casa fechada, em 375 px, o cabeçalho mostra a hora de abertura inteira. Na
    entrada, a frase do SMS fala no futuro antes do envio. Cliente que volta percorre produto,
    sacola e checkout sem nenhum convite; o convite aparece depois do pedido enviado.
    Capturas em 375 e 1366.
  - testes: apresentação do cabeçalho e as regras dos convites.
- **Muda tela:** sim (prévia). **Tamanho:** P.
- **Brief:** leia os achados P2-04 e P2-05. O estado da casa não trunca: a hora de abertura é
  a parte que fica. Aplique a decisão 3 nas duas listas de rotas e na coordenação entre
  convites: nenhum convite em produto, sacola ou checkout; o primeiro lugar possível é depois
  do pedido enviado, e um convite por visita.

### WP-L10 · A agenda das fornadas (sem data, fora das ondas)

> Decisão 2, de 16/11/2026: **não agora**. O dono não tinha este plano e pediu para ser
> convencido antes. A recomendação desta revisão passou a ser esperar: a agenda publica a
> produção planejada, e hoje um lote cancelado ou atrasado ainda não vira aviso para quem
> encomendou (F-6). Volta à mesa depois de a promessa de quando (L01 e L02) estar no ar e de a
> F-6 ter dono. O texto abaixo fica como registro da ideia.

- **Objetivo:** a cliente vê a semana de fornadas e encomenda dali.
- **Achados que fecha:** nenhum; é o salto S4.
- **Dependências:** WP-L01, WP-L04 (divide `api/urls.py`); F-6; nova palavra do dono.
- **Arquivos:** `shopman/storefront/presentation/batches.py` (novo), view e rota em
  `shopman/storefront/api/`, `surfaces/storefront-nuxt/app/pages/fornadas.vue` (novo),
  entrada na navegação, testes e contrato.
- **Fora do escopo:** escrever na produção; mostrar quantidade, salvo decisão.
- **Pronto quando:**
  - roteiro: cliente abre "Fornadas da semana", vê o que fica pronto em cada dia e a que
    horas, e encomenda o pão de sexta em dois toques. Capturas em 375 e 1366.
  - testes: projeção (dias fechados, fornada esgotada) e a jornada em Playwright.
- **Muda tela:** sim (prévia). **Tamanho:** G.
- **Brief:** leia a ideia S4 e o WP-L01. A agenda lê a produção planejada pelos mesmos
  serviços da promessa, nunca escreve. Cada item leva à encomenda com o dia já escolhido.

### WP-L11 · Reserva com prazo à vista

- **Objetivo:** a sacola diz até quando guarda os itens.
- **Achados que fecha:** P2-07.
- **Dependências:** WP-L03.
- **Arquivos:** `shopman/storefront/presentation/cart.py`,
  `surfaces/storefront-nuxt/app/pages/sacola.vue`, `app/presentation/cart.ts`, testes.
- **Fora do escopo:** mudar o prazo (F-5).
- **Pronto quando:**
  - roteiro: cliente monta a sacola e lê "Guardamos seus itens até 19:18"; cada gesto renova;
    vencido o prazo, a sacola diz o que ainda está disponível. Capturas em 375 e 1366.
  - testes: apresentação da sacola com o prazo, usando a hora do servidor.
- **Muda tela:** sim (prévia). **Tamanho:** M.
- **Brief:** leia a ideia S5 e o achado P2-07. O prazo vem do servidor e a contagem usa a
  correção de relógio que o acompanhamento já tem (`app/presentation/deadline.ts`). Sem
  cronômetro em destaque: uma linha calma, com a hora.

## 8. Jornadas a canonizar

Todas em `surfaces/storefront-nuxt/tests/journeys/`, contra o Django da pilha.

| # | Jornada | Papel | Passos | WP |
|---|---|---|---|---|
| J1 | Retirada para hoje com Pix | cliente nova; operadora | cardápio, produto, sacola, entrar por código, retirada hoje, Pix, acompanhamento; aceite no Gestor; a tela muda sozinha | L00 |
| J2 | A encomenda da fornada de amanhã | cliente nova | produto diz dia e hora, "Encomendar para amanhã", sacola, Quando já no dia, Pix, acompanhamento | L02 |
| J3 | Acabou enquanto eu olhava | duas clientes | A abre o produto; B leva as últimas; a tela de A muda sem recarregar | L04 |
| J4 | Paguei e a loja não aceitou | cliente que volta; operadora | pagar, ler valor e frase da devolução, recusa no Gestor, "Devolvido" no histórico e na conta | L06 |
| J5 | Casa fechada | cliente que volta | pedir à noite para a abertura; a revisão diz quando a loja confirma; o checkout aberto atravessa o fechamento | L05 |
| J6 | Cancelar antes do preparo, com cartão | cliente que volta; operadora | cartão, aceite, cancelar, ler o destino da reserva | L06 (depende da F-7) |
| J7 | Repetir o pedido | cliente que volta | "Repetir pedido" do acompanhamento, sacola, checkout com as escolhas lembradas | L03 |
| J8 | Entrega com cartão | cliente que volta | entrega, abaixo do mínimo, trocar por retirada, voltar à entrega com o mínimo, cartão em um toque | L05 (depende da F-7) |
| J9 | Um toque, uma reserva | cliente nova | rede lenta, um toque em Adicionar, uma unidade na sacola | L08 |

## 9. Ondas

Dois WPs da mesma onda nunca tocam o mesmo arquivo.

| Onda | WPs | Observação |
|---|---|---|
| 1 | L00, L01, L07, L08, L09 | L01 é o único que toca `app/types/shopman.ts` e os contratos |
| 2 | L02, L03, L05, L06 | todos leem o que o L01 publicou; cada um tem as suas páginas |
| 3 | L04 | toca a página do produto e o cardápio depois do L02 |
| 4 | L11 | toca a sacola depois do L03 |
| sem data | L10 | fora das ondas pela decisão 2 |

## 10. Decisões do dono

Respondidas pelo dono no chat, em 16/11/2026.

| # | Pergunta | Resposta | Efeito |
|---|---|---|---|
| 1 | Linha com promoção: qual preço a linha mostra? | **Com desconto, e com o valor cheio riscado ao lado, para ficar claro.** | A promoção do produto abate na linha (unitário e total), o Subtotal é a soma das linhas com desconto, e o resumo só subtrai cupom e pontos. Vale para sacola, revisão, recibo e acompanhamento. Destrava L01, L03 e L05. O #2296, ainda aberto, adota a régua antiga (linha cheia) no acompanhamento e precisa seguir esta |
| 2 | Agenda das fornadas: fazer? | **Não agora.** "Não tinha esse plano. Se achar que deve mesmo, me convença primeiro." | O WP-L10 sai das ondas e fica sem data. A recomendação desta revisão passou a ser esperar a promessa de quando (L01, L02) e a F-6 |
| 3 | Convites só depois de o pedido ser enviado? | **Sim.** | Destrava o L09 |
| 4 | A sacola mostra até quando guarda os itens? | **Sim.** | Destrava o L11 |

## 11. Benchmarks

Pesquisa de 16/11/2026. A documentação de desenvolvedor do iFood, a página oficial da
Starbucks e a da Toast bloquearam a leitura direta; o que dependia delas está marcado.

| Quem | O que faz melhor | Onde falha | Fonte |
|---|---|---|---|
| Hotplate | reserva real na sacola com cronômetro obrigatório (padrão 5 min); venda por "drop" com SMS antes de abrir; limites por item, por pedido e por janela de retirada | a fila de espera só coleta telefone (pedido de funcionalidade com 43 votos); a cliente não cancela sozinha; ganha quem clica primeiro | [prazo do checkout](https://help.hotplate.com/en/articles/13730228-how-do-i-change-the-checkout-time-limit) · [limites](https://help.hotplate.com/en/articles/13720613-how-to-set-inventory-and-order-limits) · [fila](https://hotplate.canny.io/feature-requests/p/waitlist-1) |
| Toast | capacidade da cozinha por janela (a cliente só vê o horário mais tarde); item esgotado na hora, sem republicar | não reserva na sacola e admite a corrida da última unidade; a cliente não cancela sozinha; pedidos chegando com a loja fechada | [capacidade](https://support.toasttab.com/en/article/Managing-Online-Order-Volume-Throttling-Orders-1492627940253) · [estoque](https://support.toasttab.com/en/article/Setting-the-Stock-Status-and-Count-for-Menu-Items) |
| Shopify | reserva curta no passo de pagamento; pré-venda com cobrança posterior; "Buy again" nativo | o carrinho não reserva; lojistas pedem cronômetro "que reserve de verdade" | [reservas](https://shopify.engineering/scaling-inventory-reservations) · [cronômetro](https://community.shopify.com/t/checkout-timer-thats-actually-reserves-items/422063) |
| iFood | agendar com a loja fechada; Pix com prazo curto; cancelar antes do aceite é imediato e integral; prazos de estorno por meio de pagamento | agendado cancelado sem aviso; cobrança depois do estorno (reclamações públicas) | [agendar](https://tecnoblog.net/responde/como-agendar-um-pedido-no-ifood/) · [cancelar](https://idec.org.br/dicas-e-direitos/cancelar-pedido-ifood) · [estorno](https://tecnoblog.net/responde/como-pedir-reembolso-no-ifood/) |
| Rappi | pouco confirmável para o Brasil | estorno em créditos em vez do meio original (relatos do Chile) | [cancelar](https://tecnoblog.net/responde/como-cancelar-pedido-no-rappi/) |
| Starbucks | retirada em janela de 5 minutos conforme a capacidade da loja; margem de segurança nas últimas unidades (via trecho de busca) | não cancela pelo app; "pronto" que não bate; aceita item que acabou | [cancelar](https://thetakeout.com/cancel-starbucks-mobile-order-1847900234) · [pronto](https://www.leanblog.org/2024/09/starbucks-mobile-ordering-process-problems/) |

**O que nenhum deles faz** (inferência: nenhuma fonte descreve o recurso, e ausência de
documentação não prova ausência): promessa calculada da produção real; encomenda para trinta
dias com vaga em fornada e prazo de aceite à vista; dinheiro e pedido na mesma linha do
tempo; fila de espera com prioridade para quem já pagou; a agenda da produção aberta à
cliente. A loja já tem a base de todos: o trabalho deste plano é pôr isso na tela, uma vez
só, e manter verdadeiro.

## 12. Capturas

Todas em 375 px, de 16/11/2026. `IMG/NN` no laudo aponta para estes arquivos.

| # | O que mostra | Arquivo |
|---|---|---|
| 01 | produto com fornada só amanhã: "Lista de espera" e "Adicionar", sem dia nem hora | [01](img/excelencia-storefront/01-pdp-tabat-lista-de-espera-375.jpg) |
| 02 | cardápio abrindo em esqueleto, antes de "Destaques" entrar | [02](img/excelencia-storefront/02-menu-esqueleto-continuum-375.jpg) |
| 03 | linha da sacola: "R$ 5,10 cada" e total "R$ 6,00" | [03](img/excelencia-storefront/03-sacola-linha-5-10-cada-total-6-00.png) |
| 04 | sacola: "Previsto para amanhã" | [04](img/excelencia-storefront/04-sacola-tabat-previsto-amanha-375.jpg) |
| 05 | revisão do pedido, sem frase sobre o dinheiro | [05](img/excelencia-storefront/05-revisao-pedido-sem-dizer-cobranca.png) |
| 07 | Pix: QR Code na primeira dobra, "Copiar código" abaixo | [07](img/excelencia-storefront/07-pix-qr-antes-do-copiar-375.jpg) |
| 08 | passo Quando: "Tabatière sai amanhã, 17/11" e horários riscados | [08](img/excelencia-storefront/08-quando-tabat-sai-amanha-375.jpg) |
| 10 | cancelado por prazo: "Devolvemos os R$ 5,10 do seu Pix"; histórico sem "Pago" | [10](img/excelencia-storefront/10-cancelado-por-prazo-devolvemos-375.jpg) |
| 11 | pedido pago: "A loja confirma sua encomenda", sem prazo | [11](img/excelencia-storefront/11-pagamento-recebido-sem-prazo-de-aceite-375.jpg) |
| 12 | resumo do pedido pago: "Pagamento recebido" | [12](img/excelencia-storefront/12-resumo-pedido-pago-375.jpg) |
| 13 | "Disponível hoje na loja" às 18:38, com a casa fechada | [13](img/excelencia-storefront/13-pdp-melon-disponivel-hoje-com-loja-fechada-375.jpg) |
| 14 | "Ficou indisponível enquanto você escolhia", com alternativas | [14](img/excelencia-storefront/14-ficou-indisponivel-enquanto-escolhia-375.jpg) |
| 15 | a mesma página depois da recusa: segue "Últimas unidades · Adicionar" | [15](img/excelencia-storefront/15-pdp-segue-disponivel-depois-do-409-375.jpg) |
| 16 | convite de instalar o app sobre o produto | [16](img/excelencia-storefront/16-convite-instalar-sobre-o-produto-375.jpg) |
| 17 | convite de avisos sobre a sacola | [17](img/excelencia-storefront/17-convite-avisos-sobre-a-sacola-375.jpg) |
| 18 | mínimo de entrega com as duas saídas | [18](img/excelencia-storefront/18-minimo-de-entrega-no-checkout-375.jpg) |
