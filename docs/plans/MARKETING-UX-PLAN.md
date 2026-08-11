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

⚠️ A primeira versão tinha uma quarta, **Histórico**. Ela caiu na §8: a pergunta "o que saiu?"
é fraca, e a forte — "esta campanha está funcionando?" — se responde dentro da campanha.

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

## 6. Histórico — superado pela §8

A primeira versão desta proposta mantinha o Histórico como seção própria, ganhando o porquê da
falha. O dono desconfiou ("poderia ser absorvido") e tinha razão: ver §8. Sem gráfico segue
valendo — a pergunta é "saiu? para quantos? deu problema?", e três respostas em texto valem
mais que uma curva.

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

## 8. O Histórico se dissolve, e a nav cai para três

O dono teve a impressão de que o Histórico "poderia ser absorvido", e a impressão está certa.
Ele responde uma pergunta **fraca**: "o que saiu?", em geral, em ordem cronológica. A pergunta
forte é **por campanha** — *"isto está funcionando?"* — e essa se faz olhando a campanha, não
uma lista global.

Então ele se dissolve em dois lugares, e cada pedaço fica mais útil do que era:

· **dentro de cada campanha**, uma faixa de desempenho: "saiu 12 vezes · 340 pessoas · 2
  falhas — a última por credencial do Instagram". É aqui que a **causa da falha** merece
  aparecer, porque é aqui que dá para agir sobre ela: desmarcar a plataforma, arrumar a
  credencial, mudar o texto. Numa lista cronológica, a mesma informação é só um lamento;
· **no Painel**, o "o que saiu hoje" ganha um "ver tudo" que abre a linha do tempo completa
  para quem quer varrer. Deixa de ser aba e passa a ser aprofundamento.

Resultado: **Painel · Campanhas · Plataformas**. Três perguntas, três telas.

O dado já existe: `Announcement.platform_results` guarda status e razão por plataforma, e
`_result_detail` já sabe extrair o porquê. Falta agregação por campanha na projection — e
**agregação por campanha não é dashboard**: são três números atrelados a uma decisão que o
gestor pode tomar naquela tela, o que a ADR-020 §11 nunca proibiu.

---

## 9. Público: tags E público salvo (correção de 2026-08-11)

A primeira versão desta seção dizia "público salvo, e NÃO tags", com o argumento de que tag
duplicaria `groups`. **O dono contestou e estava certo. Eu não havia checado o modelo.**

`Customer.group` é **ForeignKey** — **um** grupo por cliente — e o grupo define **preço**:
aponta um `Listing` (`listing_ref`) e carrega `discount_percent`/`min_order_q` no metadata
(`packages/guestman/.../models/group.py`). Ele é camada COMERCIAL: varejo, corporativo,
funcionário.

Logo tag não duplica grupo:

| | grupo | tag |
|---|---|---|
| quantos por cliente | **um** | vários |
| efeito colateral | **preço** (Listing, desconto) | nenhum |
| natureza | faixa comercial | rótulo de intenção |

Usar `groups` para mirar campanha é **abusar de uma faixa de preço**, e como é um só por
cliente, é impossível expressar "gosta de pão **e** vem de manhã". O que eu chamei de
duplicação era, na verdade, a ausência do mecanismo certo.

⚠️ E `taggit` **já está no projeto** (produtos usam `keywords`), então o mecanismo existe na
pilha: `Customer` ganha um `TaggableManager`, e o Marketing só **seleciona quais tags atingir**
— exatamente como o dono descreveu.

### As duas coisas são complementares, não concorrentes

· **tag** responde "quem é esta pessoa?" e mora no cadastro (guestman). Vários rótulos por
  cliente, sem efeito comercial. O Marketing lê e seleciona;
· **público salvo** responde "que combinação eu uso toda semana?" e mora no Marketing. Dá nome
  a uma combinação das regras — inclusive de tags.

> "Sumidos" = risco de churn alto
> "Fãs de pão de manhã" = tag `pao` + comprou nos últimos 30 dias

Sem uma, o gestor remonta o público de memória toda semana. Sem a outra, ele não tem como
dizer nada que o comportamento não revele.

**O que continua fora:** árvore booleana com AND/OR (ADR-020 §7 — isso é CDP, e a resposta é
não) e lista congelada de destinatários (apodrece; ninguém remove quem parou de comprar).

⚠️ **O risco real da tag, que precisa de desenho:** etiqueta manual envelhece. Mitigação: a
tela mostra **quantas pessoas** cada tag alcança e **quando foi aplicada pela última vez** —
tag que não cresce há meses é tag abandonada, e isso tem de ser visível em vez de silencioso.

### O que NÃO pode ser salvo, e por quê

O vocabulário de público já é dividido em duas famílias (`services/audience.py::resolve`):

| família | chaves | vale sozinha? |
|---|---|---|
| **por evento** | `favorites`, `alerts`, `bought_within_days` sem SKU | **não** — precisam do SKU do evento |
| **escolhida pelo gestor** | `groups`, `rfm_segments`, `churn_risk_min`, `birthday_today`, `customer_refs`, `bought_skus`/`bought_collections`, (futuro) `tags` | sim |

Só a segunda pode ser salva. Público salvo com `favorites: true` não quer dizer nada fora de um
evento — resolveria para ninguém, e o gestor culparia a ferramenta. "Quem favoritou" é
propriedade do **gatilho**.

### Nada "duro" para o operador

Exigência explícita do dono, e é ela que decide a implementação:

· **cria-se salvando o que já foi feito.** No painel de disparo, depois de escolher o público em
  frases, um "salvar este público" com um campo de nome. Criar é subproduto de operar, não
  tarefa separada numa tela separada;
· **JSON nunca aparece.** Editar é abrir e clicar nas mesmas frases;
· **tag se cria digitando.** Campo com autocomplete das existentes; nome novo cria a tag. Nada
  de ir a outra tela cadastrar taxonomia antes de poder usá-la;
· **conta gente antes de salvar.** "Sumidos — 34 pessoas", resolvido de verdade
  (`resolve().summary()`), com consentimento já aplicado. É o que separa confiança de fé;
· **renomear é livre; apagar é guardado.** Público em uso avisa quantas campanhas o usam;
· **quem edita muda o alcance de quem o usa**, e a tela diz isso — é o efeito desejado, mas não
  pode ser surpresa.

### As entidades (pequenas, e justificadas)

`Audience`: `ref` (slug), `name`, `rules` (o mesmo `audience_rules`), `is_active`.
`Customer.tags`: `TaggableManager` do taggit, já na pilha.

E **um campo** na campanha (`audience_ref`), com precedência dita em voz alta: público salvo
**substitui** as chaves escolhidas-pelo-gestor; as por evento continuam da campanha. Sem merge
silencioso — merge de duas fontes de público é exatamente como se manda mensagem para quem não
devia.

---

## 10. O que eu NÃO faria

· **Dashboard de engajamento.** ADR-020 §11, e a razão é boa: número sem decisão atrelada
  treina o gestor a olhar em vez de agir.
· **Construtor de público com AND/OR.** O vocabulário é fechado e plano de propósito
  (ADR-020 §7). Árvore booleana é CDP, e a resposta é não.
· **Editor visual de flow.** Isso é o ManyChat, e duplicar seria disputar com uma
  ferramenta que faz melhor.
· **Aba de "Modelos" no primeiro nível.** É o que temos hoje, e é o que separa o texto da
  intenção.

---

## 11. Perguntas do dono, respondidas na revisão de 2026-08-11

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

## 12. Feito em 2026-08-11

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

## 13. Ordem sugerida

Cada passo entrega valor sozinho.

1. ✅ **Plataformas** — a casa que faltava; o Painel volta a ser só decisão.
2. ✅ **Prévia** — variável vazia aparece antes do cliente ver.
3. ✅ **Campanhas absorve Modelos** — o pensamento volta a ser um só.
4. **Desempenho por campanha, e o Histórico se dissolve** (§8) — a causa da falha aparece onde
   dá para agir, e a nav cai para três.
5. ✅ **Etiquetas de cliente** (§9) — `Customer.tags` com **modelo de tag próprio**
   (`CustomerTag`), porque o `taggit.Tag` padrão é global e já é do `Product.keywords`.
   Seleção no Marketing, com a contagem de gente no rótulo.
6. ✅ **Cruzar as regras** (§11) — o que faltava de verdade. Entrou no lugar do público salvo.
7. ⛔ **Público salvo** (§11) — **NÃO construído, de propósito.** Ver a decisão em §11.

---

## 11. Cruzar as regras entrou; público salvo NÃO (decisão de 2026-08-11)

O dono pediu para "sentir" se público salvo compensa: *"nem sei direito quais ou quantas
opções de combinações temos atualmente… gostaria de ver, exemplos, simulação"*. Medir foi o
que respondeu, e a resposta não foi a que este plano previa.

**Primeiro, o que a medição achou:** de 9 opções de público, só as de faixa comercial
alcançavam alguém. As outras devolviam ZERO **em silêncio**, por três elos partidos no seed
(pedido sem `data.customer_ref`, nenhum `CustomerInsight` derivado, `snapshot` vazio).
Consertado antes de qualquer discussão de recurso — discutir reuso de público enquanto o
público resolve zero seria mobiliar casa sem parede.

**Depois, o achado que mudou o plano:** as regras eram **UNIÃO**. Somar regra ALARGAVA o
alcance. "Fiéis" (5) mais "atacado" (2) davam **5**, e não existia como pedir os **2** que são
as duas coisas. O recorte — que é justamente o que faz uma campanha valer a pena — era
impossível de expressar.

Com isso na mesa, público salvo perde a razão de ser **agora**:

· salvar uma combinação só vale quando a combinação é difícil de reconstruir. Somar duas
  regras que apenas empilham gente se refaz em dois cliques;
· o que faltava era **semântica**, não armazenamento. Um objeto salvo por cima de uma união
  seria mobília: dá nome a algo que ninguém tem trabalho de montar.

Então entrou `match: "any" | "all"` — um **interruptor**, não árvore booleana (ADR-020 §7
segue de pé). E entrou a **contagem ao vivo**, que é o que torna a diferença visível: a tela
mostra "Faixa de preço 2, Etiquetas 2, cruzando: 1", e o gestor aprende o que somar e cruzar
fazem sem uma linha de explicação.

**Quando reabrir:** se aparecer combinação de 3+ regras usada toda semana. Aí o custo de
remontar passa a existir, e salvar deixa de ser mobília.

---

## Referências

- [ADR-020](../decisions/adr-020-campaign-announces-it-does-not-sell.md) — campanha anuncia,
  não vende; quatro contagens e nada de agregação
- [SURFACE-OFFER-CAMPAIGN-PLAN](SURFACE-OFFER-CAMPAIGN-PLAN.md) — F1..F13, o que já existe
- `shopman/shop/services/delivery_readiness.py` — o cálculo que a tela Plataformas renderiza
