# Os vocabulários fechados das superfícies

**O que é:** a tabela de palavras de cada superfície — o **objeto** que ela manipula, os
**atos** que ela oferece e as **grandezas** que ela conta. Fechar um vocabulário é a
pré-condição que a §4.2 de [`omotenashi-copy.md`](omotenashi-copy.md) exige antes da Onda 2
de qualquer varredura de copy: *"senão a varredura troca um nome errado por outro"*.

**Por que um arquivo só, e não um por contrato de superfície.** A §4.2 manda o vocabulário
morar no contrato do domínio, e três dos quatro moram — o do Marketing em
[`marketing-surface-contract.md`](marketing-surface-contract.md), e os deste arquivo estão
apontados de lá. O que não cabe em nenhum contrato é a **colisão entre eles**: "Tela do
cliente" nomeava dois objetos em dois apps, *lote* tinha três nomes com dois deles no mesmo
arquivo, e o gesto de silenciar um aviso tem duas palavras, uma por app. Colisão entre
domínios não tem dono num contrato de domínio. Tem aqui.

**O que este documento NÃO faz:** não reabre decisão tomada. A §1 lista o que já está
decidido, com data e com o lugar onde é cobrado. Se uma pergunta sua já foi respondida, a
resposta está lá — a casa tem regra escrita sobre isso, e a razão é que reabrir custa uma
rodada e não melhora nada.

**Medições:** `origin/main` em `7d0b92cfd`, 24/09/2026. Número aqui é número medido; quando
envelhecer, remeça.

---

## 0. As três leis

As duas primeiras vêm da §4.2 da régua. A terceira é o que a medição das quatro varreduras
obrigou a escrever, e ela já está aplicada na trava do `operator-kit`:

1. **Um nome por conceito, qualquer que seja a porta de entrada.** Se duas telas fazem a
   mesma pergunta, fazem com as mesmas palavras. Quem aprende o app por uma tela tem que
   reconhecer a outra.
2. **O verbo nomeia o ato real** — o que o sistema faz, não o que ele providencia.
3. **Quem lê é quem manda na palavra.** A linha não é por app, é por audiência. O Marketing
   prova isso por dentro: `placeholder="#padaria #fornada"` é sugestão de hashtag de
   Instagram, e `#lote` ali não é hashtag de padaria — é vocabulário de chão de fábrica num
   canal onde a casa fala com cliente. O rótulo do campo ao lado, que só o gestor lê, diz
   *lote*. Mesmo arquivo, duas audiências, duas palavras certas.

---

## 1. O que já está decidido — e não se reabre

| Palavra | Decisão | Quando | Onde é cobrado |
|---|---|---|---|
| **dispositivo** | o objeto que o operador segura (tablet, celular, terminal) | 17/09 | trava: `guardrails.vocabulary.test.ts` + `test_vocabulario_de_tela.py` |
| **maquininha** | a do cartão tem nome próprio; não é dispositivo | 17/09, reafirmado 24/09 | mesma trava (recusa `aparelh`, não força a troca) |
| **equipamento** | a lista genérica que o canal permite levar (`fulfillment.equipment`) — não é objeto que alguém segura | 18/09 | — |
| **aparelho** | ⛔ não se usa em superfície de operador. **Fica na loja**, por concessão do dono | 18/09 | exenção escrita da trava para `storefront-nuxt/` |
| **lote** | o objeto que a Produção planeja, abre e fecha. *Fornada* nomeia o evento do forno | 22/09 | trava (só texto de tela; comentário sobre o forno continua livre) |
| **fornada** | fica na **loja** e no texto que o **cliente** lê no Marketing | 22/09 | exenção por audiência, escrita na trava |
| **ficar pronto** | o que acontece com o lote, o produto e as unidades quando a produção termina, em todo texto que o **operador** lê (Admin, apps de operador, aviso do servidor ao operador): "Produto ficou pronto", "O preparo abre quando o lote ficar pronto.", "24 un ficaram prontas às 10h01", "Unidades que não ficaram prontas". O verbo concorda com o que ficou pronto (o lote, as unidades). ⛔ *sair do forno*, em qualquer tempo (*sai*, *saiu*, *saíram*, *saindo do forno*, *saída do forno*). O forno continua tendo nome ("Retirou do forno", "Tempo de forno", "Timer do forno"): o que não se diz é que o produto *sai* dele. **A voz do cliente não é este vocabulário**: a loja e o texto que a casa escreve PARA o cliente (corpo de anúncio, aviso ao cliente) têm a regra e a trava deles (#2791) | dono, 16/11 | trava: `guardrails.vocabulary.test.ts` (texto de tela dos apps de operador) + `test_vocabulario_de_tela.py` (texto de operador do servidor), exceções de voz do cliente declaradas nas duas |
| **Em lote** · **Na hora** | o **modo de produção** da receita (`Recipe.production_mode`). *Em lote*: planejado e estocado, sai por ordem de produção (pão, creme, recheio, molho). *Na hora*: feito quando vende, vai à estação de Preparo e baixa os insumos na venda (café, chá, croque). Revenda é o produto sem receita, não um modo. ⛔ *fornada* para o modo; ⛔ *inativa*/*Arquivada* para dizer "na hora" (Arquivada é só arquivamento) | 20/10/2026 | ADR-040, "Modo de produção" |
| **etapa** | a unidade do modo de fazer de uma receita (`Recipe.steps`, `RecipeVersion.steps`) e o avanço dela no lote (evento `step_advanced` = "Etapa avançada"). Decisão do dono: era "Etapas" no modelo e no Admin e "Passos" nas telas de receita. ⛔ **"passo" como nome da etapa de receita ou de produção** ("Passos", "Passos lidos", "Adicionar passo", "Passo 3" da receita). "Passo" continua certo para o que não é etapa: o passo do login, o passo a passo de instalação, "próximo passo" de uma instrução | 01/10 | trava: 3ª regra de `guardrails.vocabulary.test.ts` (texto do `production-nuxt`) + `test_vocabulario_etapa_da_receita.py` (literais do `craftsman` e dos arquivos `recipe`/`production` do backstage) |
| **Grupo** (de clientes) | o conjunto comercial do cliente (`guestman.PriceTier`: varejo, atacado, staff), o mesmo nome no Gestor, no Marketing, no PDV e no Admin: "Grupo" no filtro e no público, "Exclusiva do grupo" na campanha, "Grupos de clientes" no Admin. Decisão do dono: o Marketing dizia *Faixa de preço* e o Gestor dizia *Grupos* para a mesma coisa; ficou **Grupo** nos dois. ⛔ **"Faixa de preço"** em texto de tela (o `Shop.price_range`, o "$$" do Google, é outra coisa e continua). O identificador `price_tier` fica: é o nome do modelo. A *lane* de processamento continua nomeada **plataforma**, nunca *faixa* | 20/10/2026 (substitui a de ≤22/09) | trava: `surfaces/marketing-nuxt/tests/operatorLanguage.test.ts` ("grupo é o conjunto do cliente") |
| **hora: "12h45"** | toda hora que alguém LÊ, na suíte inteira (operador e cliente): "12h45", "9h05", "9h". ⛔ "12:45" em tela, aviso, alerta e comprovante. Regra completa na §2.7 | 16/11 | trava: `guardrails.clock.test.ts` (kit, loja e status) + `test_formato_de_hora.py` |
| **Tela do cliente** | o monitor do balcão do **PDV** | 22/09 | — |
| **Painel de retirada** | o painel público da **Cozinha** (rota `/pickup` não muda: URL é em inglês) | 22/09 | — |
| **RevPASH · RFM** | traduzir no texto de tela; identificador, campo e comentário continuam em inglês | 22/09 | — |
| **Validar** | fica no PDV, com precedente explícito (o Odoo usa assim) | 18/09 | — |
| **Finalizar** | o último passo da Finalização, e só ele. O caminho antes continua em *Confirmar* | 18/09 | — |
| **Saída** | a estação do **KDS** por onde o pedido pronto sai (entregar no balcão, despachar a entrega). A mesma palavra em dois apps mandava gente para a tela errada; a tela de finalização de lote da Produção se chama **Finalização**, e *Expedição* é só o posto da saída dos pedidos (`workstation_vocabulary.py`). O `type` gravado continua `expedition` (identificador), e o ref da estação do seed é `exit` (`backstage.0094`, 07/11: URL de operador é em inglês) | 26/09 | — |
| **estação** (navegação da Cozinha) | cada item da navegação da Cozinha é uma estação da casa pelo NOME do cadastro (Cafés, Lanches, Encomendas), levando à sua bancada (`/<ref>`; o ref é o caminho, então é em inglês: `/coffee`, `/snacks`, `/preorders`, sem redirect do nome antigo), com "Estação · N pendências"; a lista vem do índice do servidor. A **Saída** leva ao Gestor. O título da bancada é o nome da estação. ⛔ item ou título genérico *Preparo*: estação é um posto específico, não existe estação chamada "Preparo" | 09/10 | `kds-nuxt/tests/sections.test.ts` + `useKdsShell.test.ts` |
| **Transferir** | a AÇÃO ÚNICA de levar itens de uma comanda para outra (dono, N=1, 13/10/2026), sem modos: some "Outra comanda / Comanda nova / Juntar comandas" e nada de Juntar ou Separar como botão. O diálogo "Transferir" tem um campo, **"Para qual comanda?"**, que recebe o leitor, a digitação e a escolha na lista das comandas em uso; a ação padrão, já escolhida ao abrir, é a comanda nova pré-nomeada (`13-2`, editável ali). Vão os itens marcados, ou todos sem marca. O botão diz o RESULTADO: **"Levar 3 itens para a #12"** · **"Levar tudo para a #12 e liberar a #13"** · **"Separar 2 itens na comanda nova 13-2"** (*Separar* só nessa frase de resultado). A origem que fica vazia é liberada sozinha, com Desfazer (T2=1). A **mesa do Salão** também é destino (M=1): a ocupada leva à comanda dela (**"Levar 3 itens para a Mesa 4 (#12)"**); a livre abre a comanda nova já nela (**"Separar 2 itens na comanda nova 13-2 (Mesa 5)"**), pelas listas "Comandas em uso" e "Mesas livres". O rastro: selo **"Transf. da #13"** na comanda nova, texto inteiro **"Transferida da comanda #13"** na dica e no detalhe do pedido (T1=1). **Dividir conta** é só pagar em partes e mora SÓ no Pagamento; o ⋯ da comanda fica só com Liberar (na folha do tablet e do celular, sem o pé, Transferir segue no ⋯). ⛔ *Juntar comandas*, *Outra comanda / Comanda nova* como modos, *Separada da #13*, *Veio da #13*; ⛔ *dividir* para mover itens; *Mesclar* fora, por técnico demais | 10/10 · 13/10 | `presentation/moveLines.ts`, `tests/presentation.test.ts`, `PosMoveLinesDialog.test.ts` |
| **Envio: Auto · Manual** | o modo do envio à cozinha no cabeçalho da comanda do PDV: um controle de dois botões ("Envio" + Auto · Manual) que grava o interruptor das estações desta comanda (o mesmo de Ajustes › Envio à cozinha; vale para todas as comandas). O QUANDO do Auto (ao sair da comanda ou depois de 90 s parada) e o alcance moram na dica. ⛔ *envio automático: desligado*, *automático desligado* | 13/10 | `presentation/ticketColumn.ts`, `tests/ticketColumn.test.ts` |
| **Tudo pronto** | o selo da comanda no quadro do PDV quando a cozinha terminou TUDO o que foi disparado (todo ticket vivo no Pronto; o cancelado não conta). A comanda sobe para o topo e o balcão ouve o toque. Selo `soft` com o sino; no cartão estreito fica só o sino, com "Tudo pronto" na dica e no aria. Só vale para a comanda inteira: parte pronta não tem selo de comanda, e o "Pronto" segue sendo o de cada ticket, no cartão da cozinha da linha. ⛔ *Pronta* | 13/10 | `components/PosTabBoard.vue`, `tests/components/PosTabBoard.test.ts` |
| **item = unidade** | nunca linha, em nenhuma superfície | deliberado antes, reafirmado 18/09 | — |
| **Produção · Finalização · Qualidade** | as abas do ciclo do lote na Produção (`/`, `/close`, `/quality`), depois de Planejamento e Preparação. Status Planejada · Aberta · Fechada · Cancelada (fonte única: `WorkOrder.Status`); quantidades planejado · previsto · realizado; indicadores perda e aproveitamento. ⛔ *Produzido* como rótulo de `started` ou `finished`; ⛔ *Estornar* para o `void` (é *Cancelar*); ⛔ *Rendimento* como KPI (fica com a ficha e a massa). Rótulos de eventos: *Produção* (`started`) e *Finalização* (`finished`). Fora do app, qualificar: *Produção do lote*, *Finalização do lote*. Identificadores internos e rotas permanecem `open`/`started` e `close`/`finish`. Não mexe na abertura e no fechamento do caixa nem na Saída do KDS | 29/10 | trava: `production-nuxt/tests/lifecycleVocabulary.test.ts` + `test_vocabulario_abertura_fechamento.py` |
| **Iniciar preparo** (Cozinha e Fila do Gestor) | o MESMO ato nos dois lados, e a verdade é da Cozinha (dono, 06/11/2026: "a verdade é da cozinha, o gestor é um alias, um atalho"). O pedido aceito já está na Cozinha, com o ticket esperando "Iniciar preparo" no posto (no canal `prep_start=operator` o pedido segue Aceito até lá). O toque do posto (`kds.start_ticket`) põe o ticket e o pedido em preparo; o do Gestor é atalho para o gerente adiantar e chama o mesmo serviço (`kds.start_order_tickets`) em todos os tickets que esperam, com quem tocou como autor. O Gestor nunca cria ticket: quem cria é o aceite. Pedido sem item de cozinha segue só pela transição. ⛔ "o gesto do Gestor cria os tickets" (regra de 04/10, revogada) | 04/10 · 06/11 | `shop/tests/test_prep_start_operator.py` |
| **Pronto** (Cozinha) | o ato de terminar o ticket, em todo tamanho: "Pronto W07" no card do tablet e do desktop (`cardActionLabel`) e no polegar do celular (`thumbActionLabel`). O desfazer é **Desfazer o Pronto**, e o aviso de item cancelado manda tocar em **Recebi o cancelamento** para poder marcar Pronto. ⛔ *finalizar* em qualquer flexão (*Finalizar preparo*, *finalizado*, *finalização*) no kds-nuxt e nas mensagens de `services/kds.py`. A Produção mantém o seu *finalizar* de lote | 04/10 | trava: `kds-nuxt/tests/prontoVocabulary.test.ts` + `shop/tests/test_kds_vocabulario_pronto.py` |
| **+ na barra do celular** (Marketing) | Campanhas e Ofertas mantêm o "+" (Nova campanha, Criar oferta) na barra de 56px, como ação principal da tela. A regra do Atualizar não muda. Nada muda no código | 04/10 | — |
| **barra lateral** | a navegação do app na lateral, nos três estados (aberta, compacta, oculta): "Compactar a barra lateral", "Ocultar a barra lateral", "Mostrar a barra lateral", também no menu do operador e na ajuda de atalhos. ⛔ **"rail"** em texto de tela ou `aria-label`; no código `rail` continua sendo o nome (`SUITE_RAIL_*`, `data-suite-rail`) | 08/10 | trava: 4ª regra de `guardrails.vocabulary.test.ts` |
| **gaveta** · **barra inferior** | no celular, a **gaveta** é a barra lateral aberta pelo ☰: o menu COMPLETO do app. A **barra inferior** é o menu RÁPIDO, de 3 a 5 vagas; uma delas é **Mais** (abre a gaveta) só quando sobra seção. Regra única para todo app, exceção só declarada com motivo | 08/10 | `quickBarLayout`/`quickBarProblems` (`operator-kit/app/presentation/suiteChrome.ts`), README do kit, "Barra lateral e barra inferior" |
| **Seção · N pendências** | a descrição de contagem de uma seção, a MESMA na barra lateral, na gaveta e na barra inferior: "Saída · 2 pendências", "Pedidos · 1 pendência", ou "Seção · estado" ("Canais · 1 desligado"). ⛔ contagem por extenso própria de cada app no item de navegação ("Saída, 2 pedidos na Saída") | 08/10 | `sectionDescription` (`suiteChrome.ts`), testes do kit |
| **Screen** (código) · **tela** (categoria) | a coisa. `display` é **papel** (`Channel.CommercePolicy.DISPLAY`, `SubjectType.DISPLAY`); `painel` é dashboard; `board` sai do vocabulário de tela | 24/09 | [`WP-TELAS-DE-PAREDE.md`](../plans/WP-TELAS-DE-PAREDE.md) |
| **Painel · Fila · Tabela** (Gestor de pedidos) | os três modos de ver os pedidos, nesta ordem, só com ícone (Painel: três colunas, `columns-3`; Fila: faixas, `rows-3`; Tabela: `table-2`); o nome fica na dica e no aria. **Painel** é a casa, as três colunas Novos · Em preparo · Prontos; com uma coluna só aberta, os cartões ficam em até duas colunas. ⛔ *Quadro* (o modo), *Lista* (colide com a Fila) | 14/11 | `orders-nuxt/tests/queueV6.test.ts` |
| **Corrida A · B · C** (Entregas do Gestor) | corrida se nomeia por **letra** (A, B, C… até Z), em toda tela, aria e mensagem: "Corrida B", "Chamar a corrida A". O **número** só grava (`courier.ride_number`, 1 a 26) e escolhe a letra e a cor (a cor repete a cada 6); nunca se escreve para o operador, e a URL do detalhe leva a chave da corrida (`?ride=<chave>`), não o número. A letra vem de `courier.ride_letter` (servidor) e `rideLetter` (Gestor). O número da **parada** dentro da corrida (1, 2, 3, na ordem do percurso) continua número. O id da corrida na TaOn não é nome: aparece só como referência para achar no painel da central ("número 776753357 na TaOn"). ⛔ *Corrida 2*, *corrida nº 2* | 16/11 | `orders-nuxt/tests/deliveries.test.ts` ("nenhuma tela do Gestor escreve o número da corrida"), `shop/tests/test_courier_service.py` |

---

## 2. Os gestos compartilhados — um nome, nos nove apps

Estes três não pertencem a nenhuma superfície: pertencem ao operador, que é a mesma pessoa
em apps diferentes. O padeiro que fecha o lote às 6h e o cozinheiro que expede às 11h são,
em metade dos turnos, uma pessoa só.

### 2.1 Reconhecer um aviso → **Visto**

Medido: `"Visto"` 5 · `"Ciente"` 4.

*Eu vi, pode parar de me avisar* é um gesto único, e a casa tem duas palavras para ele —
uma por app. Fica **Visto**: é o mais curto, o mais usado, e é o que já tem o ícone de olho
na Produção.

⚠️ E o gesto do KDS que **não** é esse — destravar o pedido cancelado — sai da palavra: vira
**"Recebi o cancelamento"**. Hoje ele se chama "Ciente" ao lado de outro "Ciente" que faz
coisa diferente: duas palavras, três atos, nenhuma correspondência.

### 2.2 Repetir o que falhou → **Tentar de novo** · **Tente de novo.**

Medido: `Tente de novo.` 47 · `Tentar de novo` 23 · `Tente novamente.` 8 · `Tentar novamente` 2.

A casa já convergiu de fato; os 10 restantes são varredura a terminar, não escolha a fazer.
**Rótulo de botão** no infinitivo (`Tentar de novo`), **frase de toast** no imperativo
(`Tente de novo.`). A ocorrência mais cara é a do `operator-kit`
(`OperatorSessionUnavailable.vue`): ela sozinha corrige o rótulo nos nove apps.

E o irmão: **Atualizar** é para buscar estado novo de algo que já carregou. `Revalidar`,
`Verificar novamente`, `Contar novamente` e `Conferir de novo` não existem.

### 2.3 "O que você está vendo pode estar velho" → uma forma

Medido: **14 redações distintas** em texto de tela, com dois separadores (ponto e travessão)
e sete substantivos para a mesma coisa — *painel, leitura, lista, preparos, quadro, página,
estado*. Nenhuma está errada; juntas, ensinam ao operador que há catorze situações quando há
uma.

A forma:

```
Sem conexão. O que está na tela é de {hora}.
Sem conexão. O que está na tela pode estar velho.    (quando não há hora)
```

Duas exceções legítimas, e só duas:

- **`OfflineBanner` do kit** fica como está: ele fala da *conexão*, não do dado, e é global.
- **O Painel da TV** diz só **"sem sinal"** — a palheta é curta porque a palheta é curta. Mas
  então é só isso, sem uma segunda redação no `title`.

### 2.4 Mensagens do Gestor na voz do dono (09/10/2026)

Frases aprovadas pelo dono, no lugar das que o #1557 introduziu e ele recusou. A recusada
está na trava `surfaces/orders-nuxt/tests/vocabularioFechado.guardrails.test.ts`.

| Situação | Fica | Saiu |
|---|---|---|
| Gesto que não chegou ao servidor (sem motivo do servidor) | **"WEB-6 continua novo: o Aceitar não chegou. Tente de novo."** Forma geral: `<REF> continua <situação>: o <gesto> não chegou. Tente de novo.`, com a referência, a situação (`status_label`, inicial minúscula; "Saiu para entrega" é verbo e entra como nome do estado: `H58 continua em “Saiu para entrega”`, nunca apelido como "na rua") e o nome do botão vindos da projeção. Sem referência ou situação: `O <gesto> não chegou. Tente de novo.` | "Não deu para concluir “Aceitar”. Tente de novo." · "H58 continua na rua" |
| Lote em que alguns pedidos falharam | **"N pedidos ficaram como estavam. Cada cartão diz por quê."** · singular **"1 pedido ficou como estava. O cartão diz por quê."** | "N pedidos não foram atualizados. O motivo está em cada cartão." |
| Os que andam sem precisar do operador (fim da Fila) | **"Seguem sozinhos: 1 na cozinha, 2 na rua"** | "Sem pedir você: …" |
| Selo ao vivo sem tempo real (poll) | **"Atualiza sozinho a cada 30 s"**, e a mesma forma nos outros apps: PDV "a cada 60 s", KDS "a cada 15 s", Marketing "a cada 1 min" (trava em `surfaces/marketing-nuxt/tests/operatorLanguage.test.ts`) |  "Atualiza a cada 30 s" |

### 2.5 Jargão de sistema não é texto de tela (dono, 09/10/2026)

O dono leu *"Conectando ao Core de compras"* no Compras e a frase de vincular o posto
(*"Escolha uma vez. Depois ele abre direto no trabalho deste posto e pede só o PIN de
quem for operar."*) e recusou as duas: a primeira é jargão, a segunda é prolixa.

| Situação | Fica | Saiu |
|---|---|---|
| Compras carregando | **"Carregando as compras…"** | "Conectando ao Core de compras" |
| Compras sem dado | **"Não foi possível carregar as compras"** · "Insumos, fornecedores e custos não carregaram. Toque em Atualizar para tentar de novo." | "Compras sem conexão operacional" · "Conecte o backend para …" |
| Vincular o dispositivo ao posto | **"Escolha uma vez. Depois, o dispositivo abre direto no posto e só pede o PIN."** | a frase acima |
| Postos, no Gestor | **"Onde cada dispositivo fica. Vinculado a um posto, ele abre direto ali e só pede o PIN."** | "… abre direto no trabalho do posto e pede só o PIN de quem for operar." |
| Conflito de edição | **"Alguém mudou as coleções enquanto você editava"** (e a rotação, a configuração) · "A nota gravada é: …" / **"Usar a nota gravada"** | "… mudou no servidor" · "Usar texto do servidor" |
| Documento de impressão que não veio | **"As vias não ficaram prontas."** · "A DANFE não ficou pronta." · "A etiqueta não carregou." | "O servidor não montou …" |

A trava é `surfaces/operator-kit/tests/guardrails.jargon.test.ts`: recusa em texto de
tela (tag, atributo, literal de ligação e literal de script com espaço) *Core, backend,
API, endpoint, payload, projection, SSE, token, webhook, Django, Nuxt, BFF, JSON, HTTP,
directive, servidor* e os nomes de pacote (*offerman, stockman, craftsman, orderman,
guestman, doorman, payman, buyman, fiscalman, cashman*). "Projeção" em português fica: é
a tela de previsão do B.I.

### 2.6 Maiúscula no selo: só a primeira letra da sentença (dono, 16/11/2026)

Selo (o `NuxtBadge` da suíte) é sentença: **só a primeira letra é maiúscula**, como
qualquer frase da casa. Dono, 16/11/2026: "'Procurando Outro Entregador' ->
'Procurando outro entregador'. A regra é clara: Maiúscula para primeira letra da
sentença!", e vale para todo selo. Cada parte de um selo composto (separado por " · ")
é uma sentença. Nome próprio ("Cozinha", "Diego"), marca e sigla ("iFood", "PDV",
"NFC-e") e palavra com número ficam como são.

| Certo | Errado |
|---|---|
| **Procurando outro entregador** · **Loja online** · **A receber** · **Pagar na retirada** · **Saiu para entrega** · **Pronto pela Cozinha** · **Pix · Não pago** | ⛔ *Procurando Outro Entregador* · *Loja Online* · *A Receber* · *Saiu para Entrega* |

⛔ **Revertido em 16/11/2026**: a regra de 03/11, 04/11 e 07/11/2026 ("Maiúsculas no
selo: nome tem, frase não") dava maiúscula a cada palavra do selo curto ("Loja Online",
"A Receber", "Pagar na Retirada") e só a primeira ao selo-frase. Não volta.

Mora num ponto só: `surfaces/operator-kit/app/presentation/badgeCase.ts`, aplicado pelo
`NuxtBadge` do kit; nenhum app chama à mão. Quem escreve o texto do selo escreve em
sentença; o kit só garante a primeira maiúscula. A trava é
`surfaces/operator-kit/tests/badgeCase.test.ts`. A frase que não cabe em selo (o
detalhe, o motivo) vai fora dele, em texto.

### 2.7 Hora: "12h45" (dono, 16/11/2026)

Toda hora que o operador ou o cliente **lê** se escreve como a casa fala: **"12h45"**. Vale
para os onze apps de `surfaces/` (a loja incluída: aqui não há voz própria, a decisão foi
"na suíte inteira"), para o que o servidor escreve (notificação, alerta, projeção,
comprovante, Admin, a concierge) e para seed e copy configurável.

| Caso | Escreve-se | Não se escreve |
|---|---|---|
| hora e minuto | **12h45** · **9h05** | 12:45 · 09h05 · 9h5 |
| hora cheia | **9h** · **12h** · **0h** | 9h00 · 09h · 9:00 |
| intervalo | **das 12h às 14h30** · **12h às 14h30** | 12:00 às 14:30 |
| data e hora | **16/11, 12h45** · **16/11 às 12h45** | 16/11 12:45 |
| com segundos, só onde o segundo é a informação | **12h45min30s** | 12:45:30 |

Três escolhas de borda, todas tiradas do que a casa já escrevia antes da regra (horário de
funcionamento da loja, "Aberto até 19h"; a hora combinada na Cozinha, "17h" e "14h30"):

- **Sem zero à esquerda na hora** ("9h05"), minuto sempre com dois dígitos.
- **Hora cheia sem minuto** ("9h"). É a forma mais curta e não tem segunda leitura: "9h"
  só pode ser nove horas.
- **Duração não é hora.** "12 min", "1 h 20 min", "há 3 h" seguem como estão: são quanto
  tempo, não que horas.

**Um formatador por metade, e mais nada formata hora:**

- servidor: `shopman.utils.formatting.format_clock` (e `format_local` com a marca
  `{clock}`, para data e hora juntas);
- apps de operador: `surfaces/operator-kit/app/presentation/clock.ts` (`formatClock`,
  `formatDateClock`, `formatClockRange`, `formatClockSeconds`);
- loja e página de status: o módulo **gêmeo**, byte a byte, em `app/utils/clock.ts` de
  cada uma (não estendem o kit e buildam sozinhas).

**Fica de fora, por decisão escrita:**

- **Formato de máquina.** O `"HH:MM"` que se grava e trafega (`opens_at`, `ready_from`, o
  ref `"14:00-14:30"`, a janela de campanha), ISO, payload de terceiro, chave de cache e
  log. Quem lê é código: a tela ordena e calcula com ele, e formata só ao exibir. Cada
  linha leva o marcador `hora-ok: <motivo>`, e a trava exige o motivo.
- **Campo de formulário.** O `<input type="time">`, o `UInputTime` e os campos de hora do
  Admin mostram e aceitam a forma do campo. A mensagem de erro que ensina a digitar
  ("Use o formato HH:MM. Ex.: 12:00.") acompanha o campo.
- **Carimbo técnico com segundos.** A coluna de auditoria do Admin, o DANFE (leiaute
  legal), o backup e o log. Não é hora de relance, é registro.
- **Migração aplicada** (é história) e **exportação de dado** (CSV é dado, não leitura).

**A trava** reprova o formatador antigo, não a frase: `toLocaleTimeString(`,
`hour: "2-digit"`, `timeStyle`, `%H:%M`, `"H:i"`, `|time` e a hora montada à mão. O que
ela não vê é a hora escrita por extenso numa string ("das 20:00 às 08:00"): isso é olho
de quem escreve e de quem revisa.

---

## 3. PDV

**Objeto**

| Palavra | O que é |
|---|---|
| **comanda** | a conta aberta no balcão (`POSTab` no código) |
| **pedido** | o que foi enviado à cozinha ou ao cliente |
| **venda** | a comanda cobrada e fechada |
| **encomenda** | pedido para uma data futura — a casa dita o fluxo |

**Atos**

| Palavra | O que faz |
|---|---|
| **validar** | cobra, chuta a gaveta, manda à cozinha e emite a NFC-e (na encomenda paga antes, só o recibo: a nota sai na retirada ou na entrega). ⛔ Fica assim por decisão do dono (precedente Odoo) — e nenhuma frase da tela pode chamar isso de *finalizar* |
| **enviar à cozinha** | manda os itens para o KDS |
| **Transferir** | levar itens para outra comanda, em uso ou nova (`13-2`); a que fica vazia é liberada. Selo **Transf. da #13** na comanda nova |
| **dividir conta** | pagar em partes, só no Pagamento (nunca mover itens) |
| **Envio: Auto · Envio: Manual** | o modo do envio à cozinha da estação: vai sozinho, ou só no "Enviar à cozinha" |
| **Tudo pronto** | o selo da comanda que a cozinha terminou inteira; parte pronta não tem selo de comanda |
| **marcados** | o alvo das ações da comanda (dono, 13/10/2026): tocar um item marca só ele; a caixa soma. O título conta ITENS ("5 itens marcados"), e os botões dizem o alcance: **Enviar marcados**, **Transferir marcados**. Sem nada marcado: **Enviar à cozinha** (com a contagem) e **Transferir itens** valem para a comanda inteira. ⛔ *3 linhas marcadas* |
| **liberar** | devolve a comanda ao balcão |
| **fechar caixa** | encerra o turno de custódia |

⚠️ **Dívida com endereço:** `PosMoveLinesDialog.vue` tem `|| "Mover itens"` como rótulo de
reserva — um **quarto verbo** para os três atos acima, e ele aparece exatamente quando o modo
não resolve. O comentário do arquivo já registra que "Mover" foi retirado dos outros três
lugares; só o fallback ficou.

**Grandezas**

**item = unidade, nunca linha.** Três croissants e um café são **4 itens** onde o operador
lança, no pagamento, no quadro de comandas e na Tela do cliente. O que precisar contar linha
ganha outro nome (`line_count`), nunca *itens*. As outras grandezas: **comanda**, **pessoa**,
**cobrança** — e nenhuma delas se soma com outra num número só.

---

## 4. Produção e KDS

**Os dois apps não compartilham o objeto, e isso está certo.** A Produção faz **lotes**; o
KDS monta **pedidos**. `kds-nuxt` tem zero ocorrências de *lote* em texto de tela, e é assim
que deve ser. O que precisa de nome único é só o que os dois **fazem igual** — e é a §2.

**Produção**

| Camada | Palavras |
|---|---|
| objeto | **lote** · **receita** (a ficha) · **etapa** (do modo de fazer; ⛔ nunca "passo", 01/10) · **insumo** · **bancada** · **estação** |
| atos | **planejar** · **abrir** (o lote, na Produção) · **continuar** · **finalizar** (só o último passo da Finalização) · **cancelar** (o lote) · **visto** |
| ciclo | **Planejamento** · **Preparação** · **Produção** · **Finalização** · **Qualidade**; status **Planejada · Aberta · Fechada · Cancelada** |
| quantidades e indicadores | **planejado** · **previsto** · **realizado** · **perda** · **aproveitamento** (⛔ "rendimento" como KPI) |
| grandezas | **peça** (unidade) · **quilo** · **lote** — ⛔ nunca somadas num número só |

⚠️ A grandeza é o defeito mais caro deste par: um número que junta peça e quilo faz o padeiro
assar a quantidade errada. E `board.vue` já foi pego cravando `UN` numa quantidade que pode
ser kg.

**KDS**

| Camada | Palavras |
|---|---|
| objeto | **pedido** · **item** · **estação** · **comanda** · **Saída** (a estação por onde o pedido sai) |
| atos | **avançar** · **pronto** · **visto** · **recebi o cancelamento** |
| grandezas | **item = unidade** · **pedido** — ⛔ "volumes" não é grandeza de nada |

**Mudança no que já está na cozinha** (dono, 10/10/2026: "com alarde, a cada mudança. Jamais
silenciosamente!"). O card afetado diz, acima do código, **Mudou** (ou **Cancelado**, o pedido
inteiro) e, numa caixa vermelha, uma linha por mudança: **Cancelado: 1× Croissant** ·
**Pão de queijo: agora 1, eram 3** · **Observação nova em Tapioca: sem glúten** ·
**Tapioca: observação retirada** · **Tapioca: enviado de novo** · **Era a comanda Mesa 5**;
o pedido inteiro: **Pedido cancelado às 22:01. Não preparar.** O gesto de ciência é
**Recebi o cancelamento** quando algo saiu e **Visto** no resto (§2.1). Fonte:
`backstage/projections/kds.py` (`_item_change`) e `kds-nuxt/app/presentation/board.ts`.

---

## 5. Storefront

⚠️ **Esta superfície tem voz própria, por concessão explícita do dono.** O vocabulário de
operador não se aplica; calor é permitido. O que não é permitido é **promessa vaga** — e uma
promessa vaga não deixa de ser vaga por ser simpática.

| Camada | Palavras |
|---|---|
| objeto | **sacola** · **pedido** · **encomenda** · **fornada** · **aviso** · **oferta** · **cardápio** |
| atos | **montar** · **enviar** · **acompanhar** · **repetir** · **cancelar** · **avisar** |
| grandezas | **item = unidade** · **pedido** · **pessoa** |
| o objeto do cliente | **aparelho** — aqui, e só aqui |

⛔ **sacola, nunca carrinho.** Medido: *sacola* 97 · *carrinho* 16, e as duas convivem na
mesma linha — `useReorder.ts` diz `"Sua sacola está atualizada"` num ramo do ternário e
`"Itens adicionados ao carrinho"` no outro. Também em `useCartState.ts` (`'Carrinho vazio.'`)
e em `utils/operationalCopy.ts`.

⛔ **aparelho, nunca dispositivo** — e hoje `conta/seguranca.vue` diz as duas, no mesmo gesto:
pergunta *"Salvar este aparelho?"* e responde *"Dispositivo salvo por 30 dias."* Meia
superfície com duas palavras é pior do que qualquer uma das duas.

---

## 6. O que a trava cobra, e o que só olho pega

**Cobra hoje** (`surfaces/operator-kit/tests/guardrails.vocabulary.test.ts`, 1.073 arquivos;
irmã em Python sobre 1.951):

- `aparelh` em qualquer canal — template, string, comentário, nome de teste;
- `fornada` **só em texto de tela** nas superfícies de operador. A diferença de alcance entre
  as duas regras é deliberada e está escrita lá: *aparelho* é palavra que a casa não usa;
  *fornada* é palavra certa para o evento do forno, e bani-la do comentário obrigaria a
  mentir sobre o forno para satisfazer uma regra que é sobre o rótulo do botão.
- `sair do forno` (*sai*, *saiu*, *saíram*, *saindo*, *saída do forno*) **só em texto de tela**
  nas superfícies de operador, e nos literais de `shopman/backstage` e `shopman/shop` do lado
  do servidor. A casa diz "ficar pronto" (dono, 16/11/2026). O texto que a casa escreve PARA
  o cliente fica de fora por exceção declarada, com o motivo, nas duas travas: no kit, as
  fixtures e o mock visual do Marketing (corpo de anúncio); no servidor, a copy da loja, os
  avisos ao cliente e as frases que a IA do Marketing precisa reconhecer no anúncio.

**Pode passar a cobrar**, pelo mecanismo de baseline que só encolhe já usado em
`guardrails.identifiers.test.ts`:

- as 10 ocorrências de `Tentar/Tente novamente` (§2.2);
- as 14 redações de dado velho (§2.3);
- `Ciente` (§2.1);
- `carrinho` no Storefront (§5);
- `"Mover itens"` no PDV (§3).

**Não dá para cobrar por regex, e está dito em vez de fingir cobertura:**

- a palavra que depende da **audiência** dentro do mesmo arquivo (§0.3) — o Marketing é exento
  inteiro por isso;
- a **grandeza** de um número: `"12 entregas"` é uma frase impecável e o erro está na
  projection;
- o **rótulo que mente**: `"Disparar"` é uma palavra perfeita, e o defeito está no handler.

---

## 7. Como fechar o vocabulário da próxima superfície

Faltam **Compras**, **B.I.** e **Hub**. A receita é curta:

1. **Liste o que existe**, não o que deveria existir — por grep, em texto de tela, separando
   comentário. A primeira medição de vocabulário desta casa errou por um fator de dez
   exatamente por não separar.
2. **Três camadas: objeto, atos, grandezas.** Se um ato não tem verbo próprio, ele não está
   fechado — está esperando.
3. **Para cada palavra que sai, o de-para com endereço.** Palavra que sai sem endereço volta.
4. **Diga quem lê.** É a terceira lei, e ela decide mais casos do que as outras duas juntas.
5. **O que não couber nas três camadas é colisão entre superfícies** — sobe para a §2 deste
   arquivo, não fica no contrato do domínio.
