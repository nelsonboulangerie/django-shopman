# Omotenashi Copy — os critérios da linguagem de UI

**Escopo:** toda palavra que chega a uma pessoa pela tela — os nove apps Nuxt em
`surfaces/` e as telas Admin/Unfold. Não vale para prosa (comentário, docstring,
mensagem de commit), que continua livre e em português.

**Medições deste documento:** feitas no HEAD `254483bc5` (18/09/2026). Número aqui é
número medido; quando envelhecer, remeça — não deduza.

---

## Por que isto é referência, e não um plano em `docs/plans/`

Plano termina arquivado em `docs/plans/completed/`. Este critério é consultado toda vez
que alguém escreve uma string, que é todo dia, para sempre. Um documento que se aposenta
não serve.

A varredura — que **é** trabalho com começo e fim — mora aqui mesmo, na §6, em vez de num
plano separado. Separar os dois produziria duas verdades: uma régua que ninguém aplica e
uma lista de tarefas que ninguém sabe justificar.

**Fontes:**

- [`docs/reports/ux/marketing-ux-adversarial-2026-09-18.md`](../reports/ux/marketing-ux-adversarial-2026-09-18.md)
  — 38 achados no app de Marketing, cada um com a substituição já escrita. É a matéria-prima
  deste documento; a §3 destila, não repete.
- [`docs/reports/ux/pos-ux-copy-2026-09-18.md`](../reports/ux/pos-ux-copy-2026-09-18.md)
  — a **Onda 1 aplicada ao PDV** (§6.3, ordem 1): 34 achados, 10 de D1 e 4 de D4. É o
  primeiro uso desta régua como régua, e não como destilação.
- [`CLAUDE.md`](../../CLAUDE.md) — as regras de vocabulário da casa. A §4 aponta, não duplica.
- [`docs/reference/marketing-surface-contract.md`](marketing-surface-contract.md) — o
  vocabulário fechado que serve de modelo aos outros domínios.
- [`docs/reference/omotenashi-audit-framework.md`](omotenashi-audit-framework.md) — a nota
  de omotenashi da superfície. A dimensão E ("Copy objetiva") aponta para cá.
- [`docs/reference/surface-excellence-review-framework.md`](surface-excellence-review-framework.md)
  — o C3 ("Informação e linguagem") pergunta; este documento responde.

---

## 1. A definição

> "Omotenashi na linguagem é, antes de mais nada, **precisão semântica e clareza
> inequívoca**. Não significa coloquialidade, simploriedade, etc."

> "**Ridiculamente fácil para o operador** significa que ele **não precisa nunca parar
> para pensar**. Ele apenas entende tudo na hora, desde o primeiro olhar, sem dúvida, sem
> vacilo."
>
> — o dono, 18/09/2026

**A ordem é: primeiro inequívoco, depois curto — e curto só até onde não custe exatidão.**

Essa ordem corrigiu um erro concreto, e vale registrar qual, porque a régua errada não
parecia errada. A régua anterior era "elevator pitch elevado ao cubo" (é a #2 da revisão
adversarial, e continua valendo). Ela foi usada como régua **única**: brevidade virou
objetivo em si, e o produto foi frase curta e vaga. Frase que encolheu e passou a admitir
duas leituras não melhorou — piorou, e o corte esconde isso, porque a tela fica mais
bonita no exato momento em que fica menos verdadeira.

Brevidade continua sendo critério. É o último deles (§3, D8), e só corta o que não custa
exatidão.

**O que omotenashi na linguagem NÃO é:**

| Não é | Porque |
|---|---|
| **coloquialidade** | falar como quem conversa no balcão não deixa a frase mais precisa; às vezes tira a precisão que ela tinha. |
| **simploriedade** | o operador é profissional. Explicar menos do que a decisão exige é desrespeito disfarçado de gentileza. |
| **brevidade a qualquer custo** | a palavra que você cortou pode ser a que decidia entre duas leituras. |
| **calor** | "querido", "juntos", emoji. Já proibido pela regra de tom do framework de auditoria, e continua proibido aqui. |
| **explicar a arquitetura** | a frase que diz como o sistema foi construído não diz o que aconteceu (D6). |

---

## 2. O teste de uma frase

Toda copy passa por uma pergunta só:

> ### O leitor precisou completar sentido, escolher entre duas leituras, ou lembrar de algo que a tela não mostra?

Se precisou de qualquer uma das três, a frase falhou — mesmo curta, mesmo bonita, mesmo
tecnicamente correta.

As três formas de falhar:

1. **Completar sentido** — a frase está incompleta e o leitor fecha o buraco com um palpite.
   *"1 postagem em cada"* — em cada o quê?
2. **Escolher entre duas leituras** — a frase admite mais de um significado e o leitor
   escolhe o errado sem saber que escolheu. *"3 faixas canceladas"*, num app onde "Faixa de
   preço" é um bloco do formulário.
3. **Lembrar de algo que a tela não mostra** — a frase exige um conhecimento que só está na
   cabeça de quem escreveu. *"(0 = todo mundo junto)"*.

### Como aplicar, em três passos

1. **Leia a frase sozinha**, fora do arquivo, sem o código ao lado. Quem escreveu tem o
   contexto que o leitor não tem; o editor tem que perdê-lo de propósito.
2. **Leia no estado mais pobre da tela** — uma plataforma só, zero resultados, um item na
   lista, sem foto, sem nome. É onde o plural genérico e o "em cada" quebram.
3. **Leia junto com o controle ao lado.** Rótulo e frase são lidos juntos; a frase pode
   estar certa e o botão mentir na mesma caixa.

**Contagem de palavras não é o teste.** Ela é um relatório útil (frase de 48 palavras é
suspeita) e nunca um portão (§5.3).

---

## 3. O catálogo de defeitos

Oito defeitos com nome próprio. Nome importa: é o que permite dizer "isto é D4" numa
revisão em vez de discutir gosto.

| # | Defeito | Sinal de reconhecimento |
|---|---|---|
| D1 | **rótulo que mente** | o controle promete o fim do caminho antes do fim — ou a instrução nomeia um controle que não existe |
| D2 | **verbo genérico apaga o ato** | "sai", "entrega", "disponível" no lugar do verbo que nomeia o que de fato acontece |
| D3 | **frase que obriga a completar sentido** | "em cada", "modo: sim", comparativo sem o outro lado |
| D4 | **grandezas somadas** | um número que conta coisas de naturezas diferentes |
| D5 | **zero como código secreto** | `(0 = ...)`, `(vazio = ...)` — o campo pede decoreba |
| D6 | **nota de rodapé do engenheiro** | a frase começa dizendo o que o sistema **não** faz |
| D7 | **jargão e colisão de vocabulário** | termo interno na tela, ou a mesma palavra com dois sentidos no mesmo app |
| D8 | **prolixo** | a frase cabe em metade sem perder nada — e só então |

Os exemplos abaixo são reais. Quase todos os "antes" foram escritos por agentes desta
casa, e a maioria continua viva no HEAD medido.

---

### D1 — Rótulo que mente

**Sinal:** o rótulo afirma o ato irreversível, e o ato não acontece ali. Ou a inversa: a
instrução manda usar um controle que a tela não tem.

**Por que dói:** é o único defeito que faz a pessoa **acabar de agir achando que agiu**.
Ela fecha o app e vai atender o balcão.

| Antes | Depois |
|---|---|
| botão `"Disparar"`, `aria-label` `"Disparar a campanha {nome} agora"` — e o que ele faz é abrir um painel de público que cria um rascunho | `"Preparar disparo"` · `"Preparar o disparo da campanha {nome}"` |
| faixa com título `"Enviado"` e, na linha de baixo, `"Mensagens na fila."` | `"Enviando"` · `"As mensagens entraram na fila. Cada confirmação aparece aqui embaixo."` — e a mesma faixa troca para `"Enviado"` quando assentar |
| rodapé `"Aprovar sela esta versão."` num card cujos botões são `"Agendar"`, `"Visualizar consequência"` e `"Recusar"` | `"O texto que você conferir na próxima tela é o que sai — agora ou na hora que você marcar."` |

**A regra de caminho que sai disto:** num fluxo de várias etapas, **só o último passo diz
o verbo do ato**. O caminho do Marketing ficou: Definir público → Revisar anúncio →
[o passo em aberto] → Disparar agora. Só o último faz alguma coisa sair, e só ele diz
"disparar".

---

### D2 — Verbo genérico apaga o ato

**Sinal:** o verbo serve para qualquer coisa, então não informa nenhuma. "Sair" é o caso
canônico: não é ato nenhum. Sai quando? Sai como? Sai para quem?

**Por que dói:** o operador precisa do ato para decidir. "É disparado quando o gatilho
acontecer" ele entende e aceita; "sai sozinho" ele lê como ameaça vaga e vai conferir.

| Antes | Depois |
|---|---|
| "Sem revisão, o anúncio **sai sozinho** assim que o evento acontecer" | "Sem revisão, o anúncio **é disparado** assim que o gatilho acontecer." |
| "Nada **sai** agora; vai para revisão" | "Nada **é disparado** agora." |
| "Nada **saiu** ainda" | "Nada **foi disparado** ainda." |
| chip `"Não publica"` no WhatsApp, que não publica — envia | `"Não envia"` no WhatsApp · `"Não publica"` no mural |
| `"O prazo terminou. Atualize os fatos antes de publicar."` — "atualizar os fatos" não é gesto disponível em lugar nenhum | `"O prazo deste anúncio venceu — preço e estoque já podem ter mudado. Prepare um disparo novo em Campanhas."` |

---

### D3 — Frase que obriga a completar sentido

**Sinal:** a frase pede um complemento que a tela não dá. Costuma aparecer quando o texto
foi escrito para o caso plural e a tela está no caso singular.

| Antes | Depois |
|---|---|
| `"1 postagem pública"` + `"Uma em cada plataforma."` — com uma plataforma só, "em cada" fica sem o que distribuir | uma linha por destino: `"WhatsApp · 12 pessoas"` / `"Instagram · 1 postagem"`; e, quando há uma só: `"1 postagem no Instagram. Não escolhe contatos."` |
| aviso de conflito de rascunho: *"Modo de entrega — Versão atual: não · Seu rascunho: sim"* | rótulo `"Agendamento"`, com `true → "agendado"` e `false → "sair agora"` |

**Nota de método:** este defeito é invisível no código e óbvio na tela vazia. É por isso que
o passo 2 do teste (§2) manda ler no estado mais pobre.

---

### D4 — Grandezas diferentes somadas

**Sinal:** um número único sobre coisas que não são a mesma coisa. **Mensagem conta gente;
postagem conta a si mesma.**

**Por que dói:** é o número que o gestor lê de manhã e usa para decidir se disparou demais.
`"12 entregas confirmadas hoje"` pode ser 12 pessoas, ou 9 pessoas e 3 murais.

| Antes | Depois |
|---|---|
| `"Entregas confirmadas hoje"` (um número) | `"Pessoas que receberam hoje"` + `"Postagens publicadas hoje"`; e, enquanto a projection não separar, o rótulo honesto é `"Envios e postagens confirmados hoje"` — feio, mas não mente |
| `"Destinos elegíveis: 37"` no diálogo de recuperação | `"WhatsApp · 37 pessoas"` / `"Instagram · 1 postagem"` |
| `"1/1 destinos preparados"` no cartão do Instagram | WhatsApp: `"37 de 40 pessoas na lista"` · mural: `"postagem preparada"`, sem fração |

**Fora do Marketing, a mesma armadilha existe em:** peça × quilo × fornada na Produção;
pedido × item × pessoa no Gestor de Pedidos; venda × comanda × pessoa no PDV.

---

### D5 — Zero como código secreto

**Sinal:** a tela ensina o operador a decorar o que o campo faz quando está vazio.
`(0 = ...)`, `(vazio = ...)`, `0 ou vazio = ...`.

**Por que dói:** obriga a lembrar de algo que a tela não mostra — a terceira falha do teste.
E tem conserto estrutural: **na maior parte dos casos o campo é um interruptor disfarçado de
número.**

Medido no HEAD, em texto de tela (literal fora de docstring, a mesma aproximação que a trava
de `aparelho` já aceita):

- **12 em Python**, pelo padrão ampliado (`(0 = `, `(vazio = `, `0 ou vazio =`):
  `shopman/shop/models/promotion.py` (6), `shopman/shop/admin/shop.py` (3),
  `shopman/shop/admin/delivery.py`, `shopman/backstage/api/marketing.py` e
  `shopman/shop/rules/suggestion.py`. Conferidas uma a uma, **11 são o defeito**: a de
  `suggestion.py` (`"'price_band' é um número (0.30 = ±30%)"`) é exemplo de escala, não
  decoreba de valor vazio. A trava acha candidato; quem separa é gente.
- **3 em `.vue`** — todas em `surfaces/marketing-nuxt/app/components/CampaignForm.vue`:
  `"(0 = todo mundo junto)"`, `"(0 = não segmentar por horário)"`, `"(0 = sem prazo)"`. Este
  arquivo ficou fora do escopo da revisão adversarial, por estar em edição noutra frente.

| Antes | Depois |
|---|---|
| campo "Espaço entre envios (min)" com `"(0 = todo mundo junto)"` | interruptor **"Espaçar os envios"**, e o campo de minutos só aparece ligado |
| `help_text="Valor mínimo do pedido em centavos (0 = sem mínimo)"` | interruptor **"Exigir valor mínimo"**, com o campo revelado |

---

### D6 — Nota de rodapé do engenheiro

**Sinal, e é uma assinatura literal:** a frase começa afirmando o que o sistema **não** faz.
"não inferimos sucesso", "o app não transforma essa falha em lista vazia", "o sistema nunca
troca Stories por Feed sozinho", "nunca será apresentado como desfeito".

**Por que dói:** é orgulho de engenharia lido pelo padeiro. Ele não sabia que havia esse
risco; agora tem que ler a defesa contra ele, no lugar de ler o que aconteceu e o que fazer.
Foi o defeito mais frequente da revisão adversarial: **11 dos 38 achados.**

| Antes | Depois |
|---|---|
| "Pode ser uma interrupção de rede ou do serviço. O app não transforma essa falha em lista vazia." | "Pode ser a rede. Isto não quer dizer que não há nada." |
| "Não vamos inferir sucesso enquanto o registro de entrega não responder." | "Ainda não sabemos o que saiu. O comprovante continua abaixo." |
| "Este anúncio é anterior ao ledger por destino; não inferimos sucesso sem prova." | "Não guardamos o resultado dele por plataforma. O que aconteceu na época não dá para conferir aqui." |
| "O público está sendo transformado em entregas rastreáveis." | "Montando a lista de quem recebe. Leva alguns segundos. Depois começam a sair." |

**O corte:** apague a oração que defende a decisão de arquitetura. Se o que sobra não diz o
que fazer, a frase que faltava nunca foi a defesa — era o gesto.

---

### D7 — Jargão e colisão de vocabulário

Três formas, com o mesmo conserto: **um nome por conceito, e o nome é o do negócio.**

**(a) Termo interno vazado.** `ledger`, `destino` (`DeliveryTarget`), `artefato`, `intenção`,
`selar`, `consequência`, `escala para SRE`, `origem v2`, `Política {policy_version}`,
`shop.view_marketing` em monoespaçado. A padaria não tem SRE nem time de Produto.

| Antes | Depois |
|---|---|
| `"Escala para SRE em 14:00 (America/Sao_Paulo)"` | a linha de dono sai enquanto a operação for uma pessoa; se a escalada precisa aparecer, aparece como prazo: `"Se ninguém decidir até 14:00, o anúncio expira."` |
| `"Visualizar consequência"` | `"Ver o que vai sair"` |
| `"A fila do sino da loja: fornada para pão, reposição para o resto"` | `"Quem pediu para ser avisado quando este produto voltar."` |

O último é o subtipo mais traiçoeiro: **jargão poético**, que soa como voz da casa e não
explica nada. Ele passa na revisão porque é bonito.

**(b) Colisão dentro do mesmo app.** `"faixa"` como *lane* de processamento, num app onde
**"Faixa de preço"** é conceito de negócio no formulário ao lado. O gestor acabou de montar
um público por faixa de preço e lê "3 faixas que não tinham começado foram canceladas".
Ninguém desconfia de uma palavra que acabou de aprender no app.
→ `"As plataformas que ainda não tinham começado não enviaram nada."`

**(c) O mesmo conceito com nomes diferentes conforme a porta de entrada.** "Para quem" /
"Avisar quem" / "Definir público" eram a mesma pergunta. "Qualquer uma/Todas" e "Atender a
qualquer um/Atender a todos" eram o mesmo cruzamento de regras. Quem aprende o app por uma
tela não reconhece a outra — e conclui que são coisas diferentes, o que é pior do que não
entender.

Medido no HEAD, o caso mais simples deste subtipo, o rótulo de "tenta de novo": a casa já
convergiu de fato em **`"Tentar de novo"` (16 ocorrências)**; sobram **`"Tentar novamente"`
(4, em Marketing, Storefront e Gestor de Pedidos)** e **`"Verificar novamente"` (1)**. Não é
uma escolha a fazer; é uma varredura a terminar.

---

### D8 — Prolixo

**Por último de propósito.** É o defeito que a régua anterior tratava como primeiro, e é o
que menos custa quando sobra.

**Sinal:** a frase cabe em metade sem perder informação. Duas orações subordinadas, dois
dois-pontos e um travessão no topo de um quadro de resultado.

**A regra:** corte tudo o que não muda o que a pessoa vai entender ou fazer — **e pare aí.**
Se o corte seguinte obriga o leitor a completar sentido (D3) ou abre uma segunda leitura,
ele é uma piora que se parece com uma melhora.

| Antes (48 palavras) | Depois (16) |
|---|---|
| "Uma entrega foi aceita pelo provedor: ele recebeu e assumiu a entrega, e a confirmação de que chegou à pessoa vem depois, dele mesmo — quando chegar, aparece neste mesmo quadro, sem você fazer nada. Até lá não reenvie: o reenvio duplicaria a mensagem em vez de apressá-la." | **"O WhatsApp recebeu e vai entregar. A confirmação aparece aqui sozinha. Não reenvie: duplicaria a mensagem."** |

Note o que o corte **manteve**: o nome da plataforma (que a frase longa só dizia como
"o provedor"), a promessa de que aparece sozinha, e o motivo de não reenviar. O corte tirou
a explicação do mecanismo, não o que decide.

---

## 4. O vocabulário — onde ele mora

### 4.1 O que já é regra, e não se duplica aqui

Estas quatro regras já estão no [`CLAUDE.md`](../../CLAUDE.md). Este documento aponta para
elas; reescrevê-las criaria uma segunda fonte que envelhece sozinha.

- **URL em inglês, texto em português.** A convenção é sobre o caminho, não sobre a copy.
- **`cpf`, `cnpj`, `cep` em português.** Nome próprio de documento brasileiro.
- **Campo de API de terceiro fica como o terceiro chama, e morre na porta de entrada.**
  O `valor` da Efí é o contrato deles; para dentro vira `amount`.
- **"dispositivo", nunca "aparelho"** — com a maquininha como nome próprio e o Storefront
  de fora, por concessão do dono. É a única destas quatro que já tem trava (§5.1).

### 4.2 O vocabulário fechado, por domínio

O Marketing fechou o dele, e é o modelo:

| Camada | Termos |
|---|---|
| **objeto** | **anúncio** |
| **atos** | **enviar** (mensagem) · **publicar** (postagem) · **disparar** (os dois) · **agendar** |
| **resultados** | **mensagem** (direta, tem destinatário, não se apaga) · **postagem** (pública, sem destinatário individual, se apaga) |

⛔ **"publicação pública" foi banida pelo dono.** A metade solta — `"publicação"` como nome
do resultado — ainda vive em **cinco arquivos** do app (`useCampaignBoard.ts`,
`AnnouncementCard.vue`, `AnnouncementTemplateForm.vue`, `CampaignForm.vue`,
`platforms.vue`) e é dívida, não alternativa.

**As duas leis que valem para todo domínio que for fechar o seu:**

1. **Um nome por conceito, qualquer que seja a porta de entrada.** Se duas telas fazem a
   mesma pergunta, fazem com as mesmas palavras.
2. **O verbo nomeia o ato real** — o que o sistema faz, não o que ele "providencia".

**Onde mora:** no contrato da superfície do domínio (como o
[contrato do Marketing](marketing-surface-contract.md)), não aqui. Este documento diz como
fechar um vocabulário; qual é o de cada domínio é do domínio.

---

## 5. Como isso vira trava

Regra sem trava é lembrete. Mas metade deste catálogo é indecidível por máquina, e fingir o
contrário produz um portão que reprova frase boa e aprova mentira. A divisão abaixo é
honesta sobre qual metade é qual.

### 5.1 A trava que já existe

[`shopman/backstage/tests/test_vocabulario_de_tela.py`](../../shopman/backstage/tests/test_vocabulario_de_tela.py)
varre por AST os `.py` de `shopman/shop`, `shopman/backstage` e `packages`, e reprova a
palavra `aparelh` em **literal de string que não é docstring** — texto de tela, não prosa.
Exenta `shopman/storefront/` e `shopman/shop/omotenashi/`, que são voz de cliente.

O desenho dela é o molde de tudo o que vem na §5.3: **distinguir tela de prosa antes de
medir.** Um `grep` cru não distingue, e erra por um fator de quatro: as **17** ocorrências de
`(0 = ` nos `.py` (fora migrações) viram **4** quando só o texto de tela conta. O resto é
comentário e docstring — prosa, que a regra manda deixar em paz.

### 5.2 O buraco, e ele tem o tamanho de nove apps

**String em `.vue` e `.ts` passa por baixo da varredura**, que só lê Python. Isso não é
teórico, e a prova é do dia anterior a este documento:

O commit `ab50a503d` (17/09/2026) é uma varredura manual de `aparelho` → `dispositivo`,
feita de propósito, com mensagem explicando o critério e 17 arquivos tocados. Ela tocou
`surfaces/operator-kit/app/composables/useWebPush.ts` e
`surfaces/marketing-nuxt/app/pages/platforms.vue` — seis linhas em cada. Medido hoje, nos
mesmos dois arquivos:

- `useWebPush.ts` → `navigator.platform || "Aparelho"` — o rótulo que vira o **nome do
  dispositivo na tela** quando o navegador não diz qual é;
- `platforms.vue` → `"Nenhum aparelho de teste verificado foi configurado."`

Uma varredura deliberada, feita à mão, nos arquivos certos, deixou duas para trás. É
exatamente o argumento de "regra sem trava é lembrete", aplicado a quem já estava com a
regra na mão.

### 5.3 O que a máquina pega

Seis varreduras candidatas. Cada uma tem um padrão mecânico **e** um limite — o que ela
prova e o que não prova.

| # | Varredura | Padrão | O que ela NÃO prova |
|---|---|---|---|
| V1 | **palavra proibida em texto de tela** | lista fechada (`aparelh`, `publicação pública`, `ledger`, `artefato`, `SRE`) | que a palavra escolhida no lugar está certa — a trava recusa, não escreve |
| V2 | **valor vazio como código secreto** (D5) | `(0 = `, `(vazio = `, `0 ou vazio =` | se o conserto é um interruptor ou uma frase melhor; só que ali há decoreba |
| V3 | **frase que nega o sistema** (D6) | abertura da string: `Não `, `Nunca `, `O app não`, `O sistema não`, `Não vamos`, `não inferimos` | que a frase é ruim — algumas negações são a informação (`"Não reenvie"`) |
| V4 | **código interno na tela** (D7a) | hash hexadecimal, `v{n}`, `{...}_version`, chave de permissão com ponto, JSON literal | nada; este é o mais seguro dos seis |
| V5 | **verbo de ação fora do vocabulário fechado** (D2) | rótulo de botão/ação cujo verbo não está na lista do domínio | que o verbo da lista foi usado no sentido certo |
| V6 | **N rótulos para o mesmo gesto** (D7c) | inventário dos rótulos de ação por app, com **baseline que só encolhe** | qual dos N é o certo — isso é decisão, e ela se escreve no contrato do domínio |

O idioma de V6 já existe na casa:
[`surfaces/operator-kit/tests/guardrails.identifiers.test.ts`](../../surfaces/operator-kit/tests/guardrails.identifiers.test.ts)
mantém uma dívida **nomeada que só desce** — passar do baseline reprova, e ficar abaixo dele
também reprova, pedindo que o número desça junto. É o mecanismo certo para dívida de copy:
ela não some num PR, e o risco não é atrasar, é **crescer calada**.

**E uma coisa que é relatório, nunca portão:** contagem de palavras. Um número máximo de
palavras é precisamente a régua que produziu o erro da §1. Uma listagem das 20 frases mais
longas de cada app, revisada por gente, faz o trabalho sem criar o incentivo errado.

### 5.4 O que só olho humano pega

Cinco, com a razão de cada um ser indecidível:

1. **Rótulo que mente (D1).** Exige saber o que o controle faz. `"Disparar"` é uma palavra
   perfeita — o defeito está a três arquivos de distância, no handler.
2. **Grandezas somadas (D4).** Exige saber o que o número conta. `"12 entregas"` é uma frase
   impecável; o erro está na projection.
3. **Frase que obriga a completar sentido (D3).** Exige renderizar a tela no estado pobre.
   `"Uma em cada plataforma"` é gramatical e só quebra com uma plataforma.
4. **Colisão de vocabulário (D7b).** `"faixa"` é português comum. Nenhuma lista de palavras
   proibidas pega uma palavra que é legítima em todos os outros usos do mesmo app.
5. **O corte que foi longe demais (D8).** Máquina mede tamanho; ambiguidade, não.

Por isso a §6 existe. A varredura humana não é o plano B da automática — é o plano A para
metade do catálogo, e a automática é o que impede a outra metade de voltar.

### 5.5 A trava que falta, nomeada

**`WP-COPY-VUE-SWEEP` — estender a varredura de texto de tela aos `.vue` e `.ts` das
superfícies.** Enquanto ele não existir, toda regra de vocabulário desta casa vale em metade
do sistema, o que, como já está escrito no `CLAUDE.md` sobre URLs, "não é convenção, é
lembrança".

O que ele precisa resolver, dito com honestidade:

- **Em `.vue`, texto de tela não é literal de string** — é texto de template, entre tags e
  em `{{ }}`. A inversão do problema do Python: lá removem-se as docstrings para ficar com as
  strings; aqui removem-se código e comentário (`//`, `/* */`, `<!-- -->`) para ficar com o
  texto. **A ferramenta já existe invertida:** o `stripNoise` de
  `guardrails.identifiers.test.ts` remove exatamente strings e comentários para contar
  declarações. O WP escreve a irmã dela.
- **Onde mora:** nos testes do `operator-kit`, que já leem os arquivos sob `surfaces/` a
  partir do disco — cobre os nove apps de um lugar só. ⚠️ Por ler arquivo e não branch, ela
  mede a árvore de trabalho; num worktree, verde só vale para o que está ali.
- **Exenta `surfaces/storefront-nuxt/`**, pela mesma concessão que a trava de Python já faz.
- **Teste de varredura trava o gêmeo que falta** — é o efeito desejado: quando alguém
  adicionar a décima superfície, ela nasce coberta sem ninguém lembrar.

---

## 6. A ordem da varredura

### 6.1 O critério é dano, não volume

Três níveis, e a ordem entre eles não se negocia:

| Nível | O que é | Defeitos |
|---|---|---|
| **1. faz decidir errado** | a pessoa age, ou deixa de agir, com base numa frase falsa | D1, D4 |
| **2. faz parar para pensar** | a pessoa entende, mas hesita, confere, ou aprende duas vezes | D2, D3, D5, D7 |
| **3. é só feio** | a pessoa entende na hora; a tela é que fica pior do que devia | D6, D8 |

O nível 3 é o mais numeroso (11 + 9 dos 38 achados do Marketing) e é o último. Varredura que
começa pelo prolixo entrega uma tela mais limpa que continua mentindo.

### 6.2 As três ondas

- **Onda 1 — o que faz decidir errado.** D1 e D4, e só onde o gesto é caro: confirmação de
  disparo, de venda, de pagamento, de emissão fiscal, de cancelamento; e o número que se lê
  de manhã. Em cada tela, duas perguntas: *este rótulo faz o que promete?* e *este número
  conta uma coisa só?*
- **Onda 2 — o que faz parar para pensar.** D2, D3, D5 e D7, tela a tela, com o vocabulário
  do domínio fechado **antes** de começar — senão a varredura troca um nome errado por outro.
- **Onda 3 — o que é só feio.** D6 e D8, mais os códigos internos (V4) e os N rótulos (V6).
  É a onda que mais se beneficia de máquina, e a que menos urge.

### 6.3 A ordem das superfícies

Por dano, não por tamanho:

| Ordem | Superfície | Por quê |
|---|---|---|
| **0** | **`marketing-nuxt`** | fora da fila porque a fatura já está escrita: 38 achados com substituição pronta. Conferidos por amostragem no HEAD, A2 (`"Enviado"`), A3 (`"Disparar"`/`"Indisponível"`), B1 (`"faixa"`, 5 ocorrências) e D6 (`"28 recompra"`) seguem vivos. Aplicá-la não concorre com a ordem — é dívida com endereço. |
| **1** | **`pos-nuxt`** | o operador decide com cliente na frente, dinheiro na gaveta e nota fiscal em jogo. Erro de rótulo aqui sai caro na hora e na frente de alguém. |
| **2** | **`kds-nuxt`, `production-nuxt`** | quiosque, mão ocupada, decisão em segundos. Não há tempo de ler duas vezes, que é justamente o que D3 e D2 obrigam. |
| **3** | **`orders-nuxt`** | decisões sobre o pedido de outra pessoa — cancelar, expedir, avisar. D1 aqui vira promessa quebrada com um cliente do outro lado. |
| **4** | **`purchase-nuxt`, `bi-nuxt`** | número que vira decisão de compra e de produção. É o terreno natural de D4: peça × quilo × fornada, pedido × item × pessoa. |
| **5** | **`hub-nuxt`** | pouca copy, mas é a porta de entrada dos oito — e foi onde o convite de instalação nasceu errado em 17/09. |
| **6** | **Admin/Unfold** | telas de gestor, usadas com calma e menos vezes. Já tem trava de vocabulário em Python, e é onde vivem 12 dos casos de D5 (`help_text`). |
| **7** | **`storefront-nuxt`** | por último **e com régua própria**: o teste da §2 vale inteiro; o vocabulário fechado de operador, não. Voz da casa, por concessão explícita do dono. |

### 6.4 O que uma varredura entrega

Não é uma lista de reclamações. Para cada achado: **onde** (arquivo e a string, não a linha —
linha envelhece em horas), **qual defeito** (D1–D8), **por que dói** (o que a pessoa conclui
ou deixa de fazer), e **a substituição escrita**. Achado sem substituição escrita não é
achado; é opinião com número.

E a parte que mais se esquece: **registrar o que examinou e considerou bom.** Metade do valor
de uma auditoria é saber onde não mexer — a Parte E do relatório do Marketing é o padrão.

---

## 7. O que este documento não decide

- **Não muda a nota do [framework de auditoria](omotenashi-audit-framework.md).** A dimensão
  E continua valendo 20 pontos; o critério "Copy objetiva" passa a ser julgado por aqui.
- **Não reabre "publicação pública".** Foi banida; o que resta é limpar a metade solta.
- **Não toca prosa.** Comentário, docstring e mensagem de commit continuam em português e
  livres. A regra é sobre a palavra que chega a alguém.
- **Não fecha o vocabulário de nenhum domínio.** Diz como fechar (§4.2); o de cada domínio
  mora no contrato daquela superfície.
