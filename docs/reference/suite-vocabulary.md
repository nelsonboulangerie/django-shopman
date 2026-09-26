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
| **lote** | o objeto que a Produção planeja, inicia e fecha. *Fornada* nomeia o evento do forno | 22/09 | trava (só texto de tela; comentário sobre o forno continua livre) |
| **fornada** | fica na **loja** e no texto que o **cliente** lê no Marketing | 22/09 | exenção por audiência, escrita na trava |
| **Faixa de preço** | fica (conceito de negócio). A *lane* de processamento passa a ser nomeada **plataforma** | ≤22/09 | [`omotenashi-copy.md`](omotenashi-copy.md) §D7b(b) |
| **Tela do cliente** | o monitor do balcão do **PDV** | 22/09 | — |
| **Painel de retirada** | o painel público da **Cozinha** (rota `/pickup` não muda: URL é em inglês) | 22/09 | — |
| **RevPASH · RFM** | traduzir no texto de tela; identificador, campo e comentário continuam em inglês | 22/09 | — |
| **Validar** | fica no PDV, com precedente explícito (o Odoo usa assim) | 18/09 | — |
| **Finalizar** | o último passo da Expedição — e só ele. O caminho antes continua em *Confirmar* | 18/09 | — |
| **dividir · transferir · juntar** | os três atos da comanda. *Mesclar* fora, por técnico demais | 18/09 | `presentation/moveLines.ts` |
| **item = unidade** | nunca linha, em nenhuma superfície | deliberado antes, reafirmado 18/09 | — |
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
Sem conexão — o que está na tela é de {hora}.
Sem conexão — o que está na tela pode estar velho.    (quando não há hora)
```

Duas exceções legítimas, e só duas:

- **`OfflineBanner` do kit** fica como está: ele fala da *conexão*, não do dado, e é global.
- **O Painel da TV** diz só **"sem sinal"** — a palheta é curta porque a palheta é curta. Mas
  então é só isso, sem uma segunda redação no `title`.

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
| **transferir · dividir · juntar** | os três atos da comanda |
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
| objeto | **lote** · **receita** (a ficha) · **insumo** · **bancada** · **estação** |
| atos | **planejar** · **iniciar** · **continuar** · **finalizar** (só o último passo) · **visto** |
| grandezas | **peça** (unidade) · **quilo** · **lote** — ⛔ nunca somadas num número só |

⚠️ A grandeza é o defeito mais caro deste par: um número que junta peça e quilo faz o padeiro
assar a quantidade errada. E `board.vue` já foi pego cravando `UN` numa quantidade que pode
ser kg.

**KDS**

| Camada | Palavras |
|---|---|
| objeto | **pedido** · **item** · **estação** · **comanda** |
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
