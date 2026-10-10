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
| **etapa** | a unidade do modo de fazer de uma receita (`Recipe.steps`, `RecipeVersion.steps`) e o avanço dela no lote (evento `step_advanced` = "Etapa avançada"). Decisão do dono: era "Etapas" no modelo e no Admin e "Passos" nas telas de receita. ⛔ **"passo" como nome da etapa de receita ou de produção** ("Passos", "Passos lidos", "Adicionar passo", "Passo 3" da receita). "Passo" continua certo para o que não é etapa: o passo do login, o passo a passo de instalação, "próximo passo" de uma instrução | 01/10 | trava: 3ª regra de `guardrails.vocabulary.test.ts` (texto do `production-nuxt`) + `test_vocabulario_etapa_da_receita.py` (literais do `craftsman` e dos arquivos `recipe`/`production` do backstage) |
| **Faixa de preço** | fica (conceito de negócio). A *lane* de processamento passa a ser nomeada **plataforma** | ≤22/09 | [`omotenashi-copy.md`](omotenashi-copy.md) §D7b(b) |
| **Tela do cliente** | o monitor do balcão do **PDV** | 22/09 | — |
| **Painel de retirada** | o painel público da **Cozinha** (rota `/pickup` não muda: URL é em inglês) | 22/09 | — |
| **RevPASH · RFM** | traduzir no texto de tela; identificador, campo e comentário continuam em inglês | 22/09 | — |
| **Validar** | fica no PDV, com precedente explícito (o Odoo usa assim) | 18/09 | — |
| **Finalizar** | o último passo do Fechamento, e só ele. O caminho antes continua em *Confirmar* | 18/09 | — |
| **Saída** | a estação do **KDS** por onde o pedido pronto sai (entregar no balcão, despachar a entrega). A mesma palavra em dois apps mandava gente para a tela errada; desde 03/10 a tela de fechamento de lote da Produção se chama **Fechamento**, e *Expedição* é só o posto da saída dos pedidos (`workstation_vocabulary.py`). O `type` gravado continua `expedition` (identificador), e a estação do seed passou de `expedicao` para `saida` por migração (`backstage.0076`), com redirect do endereço antigo no kds-nuxt | 26/09 | — |
| **estação** (navegação da Cozinha) | cada item da navegação da Cozinha é uma estação da casa pelo NOME do cadastro (Cafés, Lanches, Encomendas), levando à sua bancada (`/<ref>`), com "Estação · N pendências"; a lista vem do índice do servidor. A **Saída** leva ao Gestor. O título da bancada é o nome da estação. ⛔ item ou título genérico *Preparo*: estação é um posto específico, não existe estação chamada "Preparo" | 09/10 | `kds-nuxt/tests/sections.test.ts` + `useKdsShell.test.ts` |
| **transferir · juntar** | os atos da comanda (dono, 10/10/2026). *Transferir* embute a comanda nova (o que se chamava *dividir* ou *separar*) e o diálogo se chama "Transferir itens", com o destino nos botões (Outra comanda · Comanda nova · Juntar comandas). **Dividir conta** é só pagar em partes, no Pagamento; ícones distintos (`arrow-right-left` × `split`). ⛔ *Separar*; ⛔ *dividir* para mover itens. *Mesclar* fora, por técnico demais | 10/10 | `presentation/moveLines.ts`, `tests/ticketColumn.test.ts` |
| **item = unidade** | nunca linha, em nenhuma superfície | deliberado antes, reafirmado 18/09 | — |
| **Abertura · Fechamento · Qualidade** | as abas do ciclo do lote na Produção (`/`, `/close`, `/quality`), depois de Planejamento e Preparação. Status Planejada · Aberta · Fechada · Cancelada (fonte única: `WorkOrder.Status`); quantidades planejado · previsto · realizado; indicadores perda e aproveitamento. ⛔ *Produzido* como rótulo de `started` ou `finished`; ⛔ *Estornar* para o `void` (é *Cancelar*); ⛔ *Rendimento* como KPI (fica com a ficha e a massa). Fora da Produção, qualificar: *abertura de lote*, *fechamento de lote*. Não mexe na abertura e no fechamento do caixa nem na Saída do KDS | 03/10 | trava: `production-nuxt/tests/lifecycleVocabulary.test.ts` + `test_vocabulario_abertura_fechamento.py` |
| **Iniciar preparo** (Fila do Gestor) | fica para o pedido sem estação: é esse gesto que cria os tickets do KDS. Nada muda no código | 04/10 | — |
| **Pronto** (Cozinha) | o ato de terminar o ticket, em todo tamanho: "Pronto W07" no card do tablet e do desktop (`cardActionLabel`) e no polegar do celular (`thumbActionLabel`). O desfazer é **Desfazer o Pronto**, e o aviso de item cancelado manda tocar em **Recebi o cancelamento** para poder marcar Pronto. ⛔ *finalizar* em qualquer flexão (*Finalizar preparo*, *finalizado*, *finalização*) no kds-nuxt e nas mensagens de `services/kds.py`. A Produção mantém o seu *finalizar* de lote | 04/10 | trava: `kds-nuxt/tests/prontoVocabulary.test.ts` + `shop/tests/test_kds_vocabulario_pronto.py` |
| **+ na barra do celular** (Marketing) | Campanhas e Ofertas mantêm o "+" (Nova campanha, Criar oferta) na barra de 56px, como ação principal da tela. A regra do Atualizar não muda. Nada muda no código | 04/10 | — |
| **barra lateral** | a navegação do app na lateral, nos três estados (aberta, compacta, oculta): "Compactar a barra lateral", "Ocultar a barra lateral", "Mostrar a barra lateral", também no menu do operador e na ajuda de atalhos. ⛔ **"rail"** em texto de tela ou `aria-label`; no código `rail` continua sendo o nome (`SUITE_RAIL_*`, `data-suite-rail`) | 08/10 | trava: 4ª regra de `guardrails.vocabulary.test.ts` |
| **gaveta** · **barra inferior** | no celular, a **gaveta** é a barra lateral aberta pelo ☰: o menu COMPLETO do app. A **barra inferior** é o menu RÁPIDO, de 3 a 5 vagas; uma delas é **Mais** (abre a gaveta) só quando sobra seção. Regra única para todo app, exceção só declarada com motivo | 08/10 | `quickBarLayout`/`quickBarProblems` (`operator-kit/app/presentation/suiteChrome.ts`), README do kit, "Barra lateral e barra inferior" |
| **Seção · N pendências** | a descrição de contagem de uma seção, a MESMA na barra lateral, na gaveta e na barra inferior: "Saída · 2 pendências", "Pedidos · 1 pendência", ou "Seção · estado" ("Canais · 1 desligado"). ⛔ contagem por extenso própria de cada app no item de navegação ("Saída, 2 pedidos na Saída") | 08/10 | `sectionDescription` (`suiteChrome.ts`), testes do kit |
| **Screen** (código) · **tela** (categoria) | a coisa. `display` é **papel** (`Channel.CommercePolicy.DISPLAY`, `SubjectType.DISPLAY`); `painel` é dashboard; `board` sai do vocabulário de tela | 24/09 | [`WP-TELAS-DE-PAREDE.md`](../plans/WP-TELAS-DE-PAREDE.md) |

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
| **transferir · juntar** | os atos da comanda (transferir para outra comanda ou para uma nova; juntar leva tudo e libera esta) |
| **dividir conta** | pagar em partes, no Pagamento (nunca mover itens) |
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
| atos | **planejar** · **abrir** (o lote, na Abertura) · **continuar** · **finalizar** (só o último passo do Fechamento) · **cancelar** (o lote) · **visto** |
| ciclo | **Planejamento** · **Preparação** · **Abertura** · **Fechamento** · **Qualidade**; status **Planejada · Aberta · Fechada · Cancelada** |
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
