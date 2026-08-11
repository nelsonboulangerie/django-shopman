# Marketing — revisão de UI/UX com olhos novos

**Status:** Proposta (nada implementado)
**Data:** 2026-08-11
**Pedido do dono:** *"um botão 'WhatsApp' ali? Parece uma UI remendada... COMO seria uma
UI/UX ideal para o app de Marketing/Broadcasting?"*
**Superfície:** `surfaces/marketing-nuxt` (`mkt.boulangerie.com.br`)

---

## 0. O diagnóstico, sem eufemismo

O botão "WhatsApp" no cabeçalho do Painel é remendo, e o dono viu certo. Mas ele é
**sintoma**, não a doença. A doença é que **o estado das plataformas não tem casa**, então ele
vaza para onde dá: primeiro como ação dentro de um alerta, depois como botão no cabeçalho
de uma tela cuja função é outra.

Hoje o Painel carrega sete coisas:

1. cabeçalho com "WhatsApp" e "Atualizar";
2. avisos de alcance por plataforma;
3. o seletor do template aprovado (num painel lateral);
4. **o teste de envio** (dentro do mesmo painel lateral);
5. o placar do dia (quatro números);
6. a fila de anúncios aguardando decisão;
7. o que saiu nas últimas 24h.

Os itens 1, 3 e 4 não são "painel". São **conexão de plataforma**. Estão ali porque não havia
outro lugar — e cada vez que faltou lugar, eu pendurei no que estava por perto. Foi assim
que o seletor nasceu dentro de um alerta (e desapareceu quando o alerta parou de aparecer),
e foi assim que o botão nasceu no cabeçalho.

Um segundo problema, mais silencioso: **`Regras` e `Modelos` são duas telas para um
pensamento só.** O gestor pensa *"quando sair fornada boa, quero dizer isso, para essas
pessoas, nessas plataformas"*. Nós o obrigamos a montar isso em duas telas, com o texto de um
lado e a regra do outro — e a tela de regra chega a mandá-lo embora quando não há modelo.

E o terceiro, o mais caro de todos: **não existe prévia.** O gestor escreve
`{{product_name}}` e só descobre como a mensagem fica quando ela chega no celular de um
cliente. Toda a conversa desta sessão sobre variável vazia, foto que não carrega e botão que
não abre janela existiu porque **ninguém consegue ver o resultado antes**.

---

## 1. Plataforma, não canal — a palavra importa aqui

A primeira versão desta proposta chamava a seção de **Canais**, e o dono barrou na hora:
`Channel` já é **canal de VENDA** no Core (web, PDV, iFood, menuboard), com `ChannelConfig`,
`channel_ref` espalhado e a ADR-018 tendo feito "superfície = Channel".

E o projeto já havia decidido isto: a [ADR-020 §10](../decisions/adr-020-campaign-announces-it-does-not-sell.md)
mantém `platforms` **sem rename** exatamente porque a ADR-018 tirou a palavra "platform" de
todos os outros lugares (`CatalogSyncState.platform`, `?platform=`) — sobrou um uso só, e ele
é o certo: `instagram`, `facebook`, `google_business`, `whatsapp` **são** plataformas. A frase
seguinte da mesma ADR usa "canal" para o de venda, no mesmo parágrafo.

Chamar a tela de "Canais" recolidiria a palavra que uma ADR inteira gastou esforço para
descolar. Fica **Plataformas** — que é, aliás, o que a UI já diz ("Publicar em", com os
rótulos de plataforma) e o que a projection já devolve (`platform`, `platform_label`).

**Canal = por onde se vende. Plataforma = por onde o anúncio sai.**

---

## 2. A pergunta que cada tela responde

Uma tela por pergunta. Se duas telas respondem a mesma, uma delas é ruído; se uma tela
responde três, ela é um depósito.

| Seção | A pergunta | Quando o gestor abre |
|---|---|---|
| **Hoje** | "o que pede a minha decisão agora?" | fica aberta o dia todo |
| **Campanhas** | "o que a padaria diz, e quando?" | ao mudar a estratégia |
| **Plataformas** | "por onde eu consigo falar, e o que falta?" | ao ligar algo, ou quando falha |
| **Histórico** | "o que saiu, para quantos, com que resultado?" | ao conferir |

O botão "WhatsApp" morre. O aviso de alcance para de carregar configuração e passa a ser
**um resumo do que Plataformas sabe**, com um caminho para lá.

---

## 3. Hoje (era "Painel")

Só decisão. Nada de configuração.

· **A fila** de anúncios aguardando revisão, cada um com prévia, público alcançado, prazo
  para caducar e as três ações: publicar, agendar, recusar.
· **O que saiu hoje**, com o resultado por plataforma.
· **Um cinto de avisos** no topo, curto, quando alguma plataforma está bloqueada ou limitada —
  frase + "ver em Plataformas". Sem botão de configuração aqui.

O placar de quatro números fica, e continua sem virar dashboard: pendentes, publicados hoje,
pessoas alcançadas, falhas. A ADR-020 §11 fecha a porta para o quinto, e ela está certa —
contagem sem decisão atrelada é enfeite.

**O que muda de verdade:** o card ganha **prévia por plataforma**. Ver a bolha do WhatsApp com a
foto, o nome resolvido e o botão é a diferença entre aprovar no escuro e aprovar sabendo.

---

## 4. Campanhas (absorve Regras e Modelos)

Uma campanha passa a ser **um objeto só**, editado numa tela só, na ordem em que o gestor
pensa:

1. **Quando** — o gatilho (fornada pronta, estoque baixo, produto novo, agendado, manual);
2. **O que dizer** — o texto, com as variáveis clicáveis e **prévia ao lado**;
3. **Para quem** — o público, em frases;
4. **Onde** — as plataformas, com o estado de cada uma vindo de Plataformas (marcar Instagram
   quando ele não publica hoje é escolha informada, não surpresa depois);
5. **A oferta** (opcional) — e aí o link vira sacola montada.

**Modelos deixam de ser uma tela irmã.** Eles continuam existindo como entidade — o reuso é
real, "Saiu do forno" serve várias regras — mas o acesso natural é de dentro da campanha:
*"escrever agora"* ou *"usar um salvo"*. A biblioteca fica como uma vista secundária dentro
de Campanhas, não como aba competindo no mesmo nível.

Isso resolve o beco que existia: com zero modelos, era impossível criar campanha, e a tela
mandava o gestor para o Admin.

---

## 5. Plataformas (a casa que faltava)

A tela que o app não tem, e que explica todos os remendos.

Um cartão por plataforma, e o conteúdo do cartão é exatamente o que
`services/delivery_readiness.py` já calcula — ele foi escrito para isto:

· **WhatsApp** — transporte, template aprovado (escolher aqui), alcance que o template
  permite, e **"testar no meu número"**;
· **Instagram** e **Facebook** — credencial, permissões, e "testar" (com o rascunho
  descrito na F13b do plano de campanha);
· **Google Meu Negócio** — "sem integração", honestamente, enquanto for verdade.

Três coisas ficam bem aqui e em nenhum outro lugar:

1. **o teste**, que hoje está dentro de um painel de configuração dentro de um painel de
   revisão;
2. **a distinção entre bloqueio e limitação** — "nada sai por aqui" e "sai, mas não para
   todo mundo" são fatos diferentes, e o cartão tem espaço para os dois;
3. **o que fazer**, com o botão ao lado da frase que explica.

---

## 6. Histórico

O que já existe, mais o que hoje falta: **por que uma entrega falhou**, por plataforma, e
**quanto alcançou**. O `platform_results` já guarda isso; a tela mostra pouco.

Sem gráfico. A pergunta do gestor de padaria é "saiu? para quantos? deu problema?", e três
respostas em texto valem mais que uma curva.

---

## 7. Prévia: a peça que muda mais

Uma prévia fiel, por plataforma, alimentada por **dados reais de um produto escolhido**:

· **WhatsApp** — bolha com cabeçalho de imagem, corpo com as variáveis resolvidas e o botão
  como ele vai aparecer;
· **Instagram/Facebook** — a imagem com a legenda e as hashtags.

Isso não é enfeite: é o único jeito de o gestor ver **variável vazia antes do cliente ver**.
Toda a dor desta sessão — `{{customer_name}}` em branco, foto relativa que não carrega,
`product_ref` que virou `product_sku` — teria aparecido numa prévia em dois segundos.

E ela é barata: o backend já resolve tudo (`resolve_content`, `test_fields`,
`product_image_url`). Falta um endpoint de prévia e um componente.

---

## 8. O que eu NÃO faria

· **Dashboard de engajamento.** ADR-020 §11, e a razão é boa: número sem decisão atrelada
  treina o gestor a olhar em vez de agir.
· **Construtor de público com AND/OR.** O vocabulário é fechado e plano de propósito
  (ADR-020 §7). Árvore booleana é CDP, e a resposta é não.
· **Editor visual de flow.** Isso é o ManyChat, e duplicar seria disputar com uma
  ferramenta que faz melhor.
· **Aba de "Modelos" no primeiro nível.** É o que temos hoje, e é o que separa o texto da
  intenção.

---

## 9. Perguntas do dono, respondidas na revisão de 2026-08-11

**A sequência da nav está adequada?** Não, e é transitória. "Regras, Modelos, Plataformas" é
uma lista de OBJETOS, não um percurso. Quando Campanhas absorver Modelos (§4), fica
**Painel · Campanhas · Plataformas · Histórico** — decidir → o que dizemos → por onde sai →
o que aconteceu. E há uma divergência de nome a resolver junto: a entidade é `Campaign`, este
plano diz "Campanhas", e a aba diz "Regras".

**Histórico continua existindo**, como última aba. Cinco abas é o próprio sintoma acima.

**Aprovação em Modelos: não existe, e a tela precisa dizer.** São dois objetos distintos, e a
confusão entre eles é previsível:

| | Modelo (nosso) | Template aprovado (Meta) |
|---|---|---|
| onde vive | `/modelos` | `/plataformas` (escolhido) |
| quem aprova | ninguém | a Meta |
| texto | livre, com `{{variáveis}}` | fixo na aprovação |

⚠️ **E o que morde:** com template escolhido, `notification_manychat` manda `sendFlow` — o
`body` do Modelo **não é enviado**, só os campos discretos. O texto que o cliente lê é o da
Meta. O Modelo continua valendo para a legenda de Instagram/Facebook e para o card de
revisão. Isso agora está dito no painel do WhatsApp, ao lado da escolha; a tela de Modelos
merece a mesma frase.

**Detalhe de plataforma em overlay.** Feito: a lista virou quatro linhas escaneáveis (nome,
estado, "sem uso", resumo) e o detalhe abre em painel. Com o WhatsApp expandido o tempo todo
a lista já era estranha; com as quatro expandindo, viraria depósito.

---

## 10. Feito em 2026-08-11

**Plataformas** (passo 1) e **Campanhas absorve Modelos** (passo 3) estão no `main`.

A nav virou **Painel · Campanhas · Plataformas · Histórico**, e três nomes para `Campaign`
viraram um: a aba dizia "Regras", a entidade é `Campaign`, e agora tudo diz **Campanhas**. A
biblioteca de modelos saiu do primeiro nível e virou botão secundário no cabeçalho de
Campanhas — o gestor pensa "o que a padaria diz quando X acontece", e separar o texto da
intenção o obrigava a montar isso em duas telas.

⚠️ **E uma regra do projeto que eu havia violado:** o CLAUDE.md manda **rotas de operador em
inglês** (PR #68), e eu criei `/modelos` e `/plataformas` em pt-br. Corrigido junto:
`/campaigns`, `/templates`, `/platforms`. Sem 301 — nada além do staging conhecia as antigas,
e o dono já foi claro sobre não devermos legado a nada.

**Prévia** (passo 2) também entrou, dentro da tela de campanha — ao lado da escolha do texto,
que é onde o gestor decide a frase. Resolve pelo MESMO `resolve_variables` do envio: prévia
com montagem própria concordaria hoje e divergiria no primeiro ajuste, e prévia que mente é
pior que nenhuma porque é acreditada. A IA **não** é chamada (gerar texto a cada tecla
gastaria chamada para jogar fora); ela só é anunciada quando o modelo delega o corpo a ela.

E ela já pagou o preço dela em dois achados no primeiro uso: o aviso **"sem valor agora:
available_qty"**, e um defeito meu — o link aparecia duas vezes, porque o modelo termina em
`{{link}}` e o componente ainda desenhava a linha do link embaixo.

Falta o passo 4 (Histórico com o porquê da falha).

---

## 11. Ordem sugerida

Cada passo entrega valor sozinho.

1. **Plataformas** — cria a casa e esvazia o Painel dos remendos (o botão "WhatsApp" e o teste
   migram para lá). É o passo que o dono pediu.
2. **Prévia** — o maior ganho por linha de código, e o que evita a próxima variável vazia.
3. **Campanhas absorve Modelos** — some o beco sem saída e o pensamento volta a ser um só.
4. **Histórico ganha o porquê** — `platform_results` já tem o dado.

---

## Referências

- [ADR-020](../decisions/adr-020-campaign-announces-it-does-not-sell.md) — campanha anuncia,
  não vende; quatro contagens e nada de agregação
- [SURFACE-OFFER-CAMPAIGN-PLAN](SURFACE-OFFER-CAMPAIGN-PLAN.md) — F1..F13, o que já existe
- `shopman/shop/services/delivery_readiness.py` — o cálculo que a tela Plataformas renderiza
