# CONCIERGE-ARQUITETURA-ALVO: respostas inequívocas, rápidas e baratas

> **Estado:** estudo (OBS0310-J, 03/10/2026). Nenhum código de produção nesta frente.
> Pedido do dono, nas palavras dele: "quero uma análise profunda e abrangente sobre COMO construir
> um mecanismo realmente ROBUSTO e ELEGANTE para o excelente funcionamento da Concierge, com
> respostas inequívocas, rápidas e de baixo custo operacional. Como o JEV se encaixa nisso? Teremos
> que apelar para um modelo de LLM de qualquer forma? O que as melhores práticas ditam atualmente
> para um agente conversacional focado em comércio?" (mais a análise de ManyChat AI, Anota AI e
> Deeliv).
>
> Já aprovado por ele (sim): uma frente para o modelo REDIGIR a resposta a partir só dos dados
> consultados, com verificação automática de preço e disponibilidade e queda para o formato montado
> se falhar. Este estudo decide COMO.
>
> Legenda: **[MEDIDO]** saída de comando, banco ou código com caminho; **[FONTE]** documento
> externo com link; **[INFERÊNCIA]** leitura minha.

## 0. Resumo em seis linhas

1. O defeito do "bom dia" não é falta de inteligência: é que hoje o texto do modelo é jogado fora e
   o cliente recebe o resultado cru das ferramentas, colado; e quando o modelo não consulta nada, o
   servidor busca a frase inteira no cardápio. [MEDIDO]
2. Mais da metade das mensagens reais não precisa de modelo nenhum (cortesia, mídia, "ok"). [MEDIDO]
3. O Jev é um classificador (decide entre opções e dá a confiança). Ele não escreve. Ele entra na
   triagem e na escolha do produto, não na resposta. [FONTE] [MEDIDO]
4. Para escrever uma frase natural, sim, precisa de um modelo de linguagem, mas UMA chamada curta
   por mensagem, só com os fatos já consultados, e um verificador em código antes de enviar.
5. Custo esperado: menos de 1 centavo de dólar por mensagem respondida pelo modelo; da ordem de
   US$ 10 a 40 por mês no volume plausível da casa. Latência alvo: 2 a 4 segundos (hoje 7 a 36 s).
6. Primeira fatia: a régua (custo, latência e conjunto de conversas reais para medir), sem mudar o
   que o cliente vê.

## 1. O sistema de hoje, medido

### 1.1 O caminho de uma mensagem [MEDIDO]

`shopman/storefront/concierge/`:

| Passo | Onde | O que faz |
|---|---|---|
| Entrada | `webhook.py`, `transport.py`, `service.py` | ManyChat chama o External Request; o turno vai para o worker (atraso de 1 s, `CONCIERGE_DISPATCH_DELAY_SECONDS`) |
| Triagem | `triage.py` (`decide`) | regra local sempre; depois modelo da Anthropic OU Jev propõe a intenção (12 intenções, D-018/D32); sensível da regra vence; destino `answer`, `team` ou `other_desk` |
| Cortesia | `small_talk.py` (#1415) | "bom dia", "obrigado", "tchau" sozinhos: frase fixa da casa, sem modelo |
| Agente | `agent.py` (`run_agent`) | laço com o modelo e 11 ferramentas (`tools.py:1835-1980`), até 6 idas (`CONCIERGE_MAX_ITERATIONS`) |
| Resposta | `agent.py:309-330` | o cliente recebe `render_result` de cada ferramenta (`tools.py:1728`), concatenado; **o texto do modelo é descartado** |
| Busca de reserva | `agent.py:270-305` | se o modelo não chamou `search_storefront`, o servidor chama, com a fala inteira |
| Handoff | `handoff.py`, `service.mark_handoff` | equipe assume no Live Chat do ManyChat |

A escolha de descartar o texto do modelo foi anti-alucinação (preço e disponibilidade só saem de
ferramenta). Ela resolveu o risco certo do jeito errado: trocou a frase inventada pelo despejo de
dados. O "bom dia" do dono (conversa 2, mensagem 672, alpha) virou três produtos, a FAQ do levain e
a de glúten porque a busca de reserva casou "bom" com "bom para cachorro quente"
(`docs/coordination/ROUNDS/OBS0310-B-concierge-bom-dia.md`).

### 1.2 Números [MEDIDO]

| Medida | Valor | Fonte |
|---|---|---|
| Ferramentas oferecidas ao modelo | 11 (5 em modo consulta, `LIMITED_AUTHORITY_TOOL_NAMES`) | `tools.py:1835-2018` |
| Regras do sistema | 7.145 caracteres, 1.137 palavras (cerca de 2 mil tokens) | `prompt.py`, `RULES` |
| Descrições e esquemas das ferramentas | cerca de 5.900 caracteres de texto (cerca de 1,7 mil tokens) | `tools.py`, `TOOL_SPECS` |
| Prefixo fixo por ida ao modelo | cerca de 4 a 4,5 mil tokens com a voz da casa e o bloco do turno [INFERÊNCIA a partir dos caracteres] | |
| Modelo da resposta | `claude-sonnet-5`, esforço `medium`, raciocínio adaptativo ligado | `config/settings.py:1466-1471` |
| Modelo da triagem | o mesmo (`CONCIERGE_TRIAGE_MODEL` vazio), esforço `low`; ou Jev | `settings.py:1494-1501`, `triage.py` |
| Idas ao modelo por mensagem | 1 de triagem + 1 a 7 de resposta | `agent.py`, `triage.py` |
| Custo da conversa 1 (04/09, 24 respostas) | 238.224 tokens de entrada, 6.814 de saída, 240.630 lidos do cache: **cerca de US$ 0,59, US$ 0,025 por resposta** (piso: a escrita de cache não é gravada) | banco do alpha, `shop_conversation`; preços do Sonnet 5 US$ 2 / US$ 10 por milhão, leitura de cache US$ 0,20 |
| Latência até a resposta, por número de ferramentas chamadas no turno | 0 ferramentas: p50 3,4 s; 1: p50 7,3 a 8,8 s; 2 ou mais: p50 14 a 24 s, máximo 36 s | banco do alpha, conversas 1 e 2 (inclui o 1 s de atraso) |
| Lacuna de medição | `cache_creation_input_tokens` não é gravado na conversa; o custo real não é recuperável | `service.py:1041-1046` |

Cada ida extra ao modelo custa de 4 a 6 segundos ao cliente. É a medida que mais pesa contra o
desenho atual de laço com várias ferramentas.

### 1.3 O que os clientes escrevem de verdade [MEDIDO]

Observação passiva no alpha (`envelope.triage_shadow`), 168 mensagens de texto de 84 conversas,
26/09 a 03/10/2026, leitura só por conexão direta (25060, banco `shopman`, transação somente leitura):

| Tipo | Mensagens | % |
|---|---:|---:|
| Só cortesia ("Oi", "Boa tarde!", "ok obrigada") | 70 | 42% |
| Intenção reconhecida (regra ou Jev) | 47 | 28% |
| Outras (sem intenção clara, quase todas dependem do contexto) | 26 | 15% |
| Link ou mídia (comprovante, localização) | 18 | 11% |
| Resposta curta de contexto ("Sim", "Cancela", "Aguardo confirmação") | 7 | 4% |

Exemplos reais de dependência de contexto: "Mais 2 croissant", "Se tiver, quero reservar para
buscar", "E coelhinho ou o ursinho (o que tiver)". Nenhum classificador que lê a mensagem sozinha
acerta essas falas; elas precisam da última pergunta da casa.

Volume observado: de 19 a 38 entradas por dia (média 24). A observação não necessariamente cobre
todo o WhatsApp da casa [INFERÊNCIA]; por isso a premissa de custo usa 150 por dia.

## 2. O que é o Jev, e onde ele cabe

**O que é.** [FONTE] Jev, da TypeSafe, é um modelo de decisão: recebe um estado (texto ou dados) e
perguntas tipadas, e devolve respostas tipadas com confiança calibrada. Tipos de pergunta: `noul`
(sim/não com probabilidade), `choice` (escolha entre opções com distribuição de probabilidade) e
`score` (nota numa régua de até 10 níveis). **Não gera texto livre.** A própria TypeSafe o descreve
como "Decisions, not strings", para "decisions inside software", não para conversa.
Fontes: <https://docs.typesafe.ai/api.md>, <https://typesafe.ai>. Preço anunciado: US$ 42 por bilhão
de tokens de entrada (US$ 0,042 por milhão), saída sem custo (`docs/plans/BI-JEV-PILOT.md`).

**Como é chamado hoje.** [MEDIDO] `intent_benchmark.JevContender` faz `POST /v1/systemone` com 12
perguntas `noul`, uma por intenção, sobre o texto redigido (`triage.jev_scores`). Em produção ele só
roda em sombra (`intent_pilot.shadow_triage`), gravando `triage_shadow` em cada entrada observada.
`CONCIERGE_TRIAGE_CLASSIFIER=jev` troca quem propõe a intenção; a D-028 aprovou mandar o texto
redigido ao Jev no comparador, e a troca em produção é decisão ainda aberta.

**Desempenho medido no alpha (168 mensagens).** Latência p50 166 ms, p95 226 ms, nenhum erro.
Custo por mensagem: cerca de 500 tokens de entrada, US$ 0,00002 [INFERÊNCIA a partir do exemplo de
`usage` da documentação]. Em 121 das 168 o Jev não deu nenhuma intenção acima de 0,5; dessas, a
maioria é cortesia, que não tem intenção mesmo. Quando a regra reconhece a intenção, ele concorda na
maior parte (ex.: `order`/`order` 10 vezes) e reconhece 11 pedidos e 3 perguntas de horário que a
regra deixou em `default`.

**Onde ele se encaixa.** Em três decisões, todas de escolha, nunca de redação:

1. **Triagem** (já existe): qual das 12 intenções, com confiança. Com confiança baixa, sobe para a
   camada seguinte em vez de chutar.
2. **Escolha do produto**: dado o que o cliente escreveu e os 5 a 10 candidatos do cardápio, qual é
   (pergunta `choice`, a mesma forma do piloto do de-para do B.I.). Resolve "croassant", "o oval
   integral", "o ursinho".
3. **Portão de risco**: "esta mensagem fala de alergia, pagamento ou reclamação?" (`noul`), somado à
   regra local, nunca no lugar dela.

Para as falas de contexto, o estado enviado ao Jev precisa levar a última fala da casa (redigida).
Hoje leva só a mensagem (`build_request`, `state.customer_message`). Isso amplia o que a D-028
aprovou, então é decisão do dono (seção 8).

## 3. Precisa de modelo de linguagem? Onde sim, onde não

| Trabalho | Precisa de LLM? | Quem faz |
|---|---|---|
| Cortesia, agradecimento, despedida | Não | `small_talk.py` (frase da casa) |
| "ok", "sim", "cancela" | Não, se há um estado pendente (resumo de pedido, pergunta da casa); com estado, o código sabe o que "sim" confirma | máquina de estados do turno |
| Mídia, link, comprovante, localização | Não | modelo de mensagem fixo + equipe ou ferramenta de endereço |
| Alergia, pagamento, reclamação, pessoa | Não (e não deve) | texto fixo da casa + equipe (D-018) |
| Qual a intenção | Não precisa de LLM | regra local + Jev |
| Qual produto | Não precisa de LLM | busca no catálogo + Jev `choice` |
| Buscar preço, estoque, horário, status | Nunca é do LLM | serviços do Shopman (ferramentas) |
| Resumo e recap de pedido, Pix, total | Não (e não deve) | bloco montado e travado (`render_result`) |
| **Escrever a frase de resposta natural, curta, no tom da casa** | **Sim** | **uma chamada curta, só com os fatos consultados** |
| Conversa de pedido com vários passos (fase 2) | Sim | agente com ferramentas, o de hoje |
| Mensagem que ninguém entendeu | Sim | agente, com teto de idas |

Resposta curta à pergunta do dono: **sim, para redigir**, porque nenhum molde cobre "tem o coelhinho
ou o ursinho, o que tiver?" com naturalidade; **não, para decidir, consultar ou falar de dinheiro**.
A diferença para hoje é que o modelo deixa de ser o maestro que decide tudo em várias idas e passa a
ser o redator de uma ida só, com a ficha na mão.

## 4. Como funcionam os de referência

### 4.1 ManyChat AI [FONTE]

As páginas oficiais recusaram leitura direta (403); os fatos vêm dos trechos indexados, da
comunidade e de análises de terceiros.

- **Reconhecimento de intenção** é um gatilho: você descreve a intenção em linguagem natural e a IA
  compara a mensagem com a descrição; aceita variação e erro de digitação; Instagram, Messenger,
  WhatsApp e Telegram. Dispara um flow, como qualquer gatilho. Não há confiança devolvida nem campo de
  exemplos documentado. <https://help.manychat.com/hc/en-us/articles/14281187229468-Manychat-AI-Intention-Recognition>,
  <https://manychat.com/blog/guide-to-mastering-manychat-ai/>
- **Ordem**: palavra-chave primeiro, intenção depois, resposta padrão por último; usuários relatam
  roteamento errado com muitos flows. <https://community.manychat.com/product-updates/transform-your-marketing-strategy-with-manychat-ai-the-ultimate-pro-add-on-1554>
- **AI Step**: passo guiado por um objetivo e pelo contexto do negócio, que salva a resposta em campo
  do sistema ou personalizado. <https://manychat.com/blog/best-practices-in-data-collection-how-to-set-up-ai-step-to-win-on-social/>,
  <https://help.manychat.com/hc/en-us/articles/23096273858716-Manychat-AI-Goals>. **AI Behavior**
  guarda tom e limites. <https://help.manychat.com/hc/en-us/articles/26782002914332-Manychat-AI-Behavior>
- **Ferramentas**: não há "AI Step chama ferramenta"; o caminho é External Request para um serviço
  próprio (que é o nosso caso). <https://community.manychat.com/general-q-a-43/connecting-ai-with-manychat-10149>
- **Provedor do modelo**: não divulgado; há uma integração separada com ChatGPT por chave própria.
  <https://help.manychat.com/hc/en-us/articles/14281251371164-ChatGPT-integration>
- **Preço**: US$ 29/mês como adicional do Pro (anúncio na comunidade); para 2026 as fontes divergem.
  <https://www.chatbot.com/blog/manychat-pricing/>

[INFERÊNCIA] É um classificador baseado em LLM que escolhe o flow; a resposta continua sendo o flow
que você escreveu (determinística) ou um AI Step genérico sem acesso ao seu estoque vivo.

### 4.2 Anota AI (iFood) [FONTE]

- Comprada pelo iFood em 25/07/2022. <https://startups.com.br/negocios/exclusivo-ifood-compra-a-anota-ai-para-oferecer-atendimento-pelo-whatsapp/>
- O atendente virtual entende texto e áudio, **manda o cardápio digital**, atualiza o status do
  pedido sozinho, avisa a loja quando o cliente pede pessoa, e a automação pode ser pausada.
  <https://anota.ai/home/funcionalidade/atendente-virtual/>
- O pedido é montado pelo cliente no link do cardápio e cai no painel depois do pagamento.
  <https://reidodelivery.com.br/blog/anota-ai-vale-a-pena>
- O FAQ cita "NLP integrado" e "IA generativa", sem dizer o modelo; preço por faixa de pedidos (desde
  09/2026: R$ 99,99 até 150 pedidos, R$ 199,99 até 250, R$ 299,99 acima). <https://anota.ai/blog/faq-anota-ai/>
- O iFood tem um agente próprio para o consumidor, o **Ailo** (10/2025), com um "Large Commerce
  Model"; em 07/2026 ganhou memória, desconto e fechamento com Pix no WhatsApp.
  <https://institucional.ifood.com.br/inovacao/ailo-assistente-de-ia-pedidos/>,
  <https://portal.clientesa.com.br/ifood-anuncia-nova-fase-do-agente-de-ia-ailo-no-whatsapp/>

[INFERÊNCIA] O núcleo é árvore de fluxos com reconhecimento de linguagem na porta; o pedido em si
mora no cardápio digital, não na conversa. É barato e previsível, e é o que a nossa fase 1 já faz
com `send_web_link`.

### 4.3 Deeliv [FONTE]

- Robô "LivIA": transcreve áudio, responde dúvidas do cardápio e da loja a partir de uma base de
  conhecimento da loja. <https://www.deeliv.app/>
- Plano "Intelligence Pro" anuncia "tecnologia do Chat GPT", carrinho abandonado e Pix automático;
  R$ 240/mês (R$ 180 o cardápio digital), sem taxa por pedido, valor varia por campanha.
  <https://www.deeliv.app/mkt/automacao/>
- Fluxo exato da conversa e como evita preço inventado: **não encontrado**.

### 4.4 O que copiar e o que evitar [INFERÊNCIA]

| | Copiar | Evitar |
|---|---|---|
| ManyChat | intenção descrita em linguagem natural (já temos nas 12 intenções); ordem explícita palavra-chave, intenção, padrão; persona num lugar só | classificador sem confiança e sem exemplos; ferramentas por gambiarra |
| Anota AI | mandar o link do cardápio em vez de montar pedido longo no chat; status automático; aviso à loja e pausa | "IA generativa" sem dizer o que ela pode afirmar |
| Deeliv | base de conhecimento da loja como fonte; leitura de comprovante | ChatGPT respondendo solto, sem verificação de preço e alérgeno |

Nenhum dos três documenta verificação do que o modelo escreve. É onde a Concierge pode ser melhor:
**o estoque e o preço são vivos e verificados na saída.**

## 5. O que as melhores práticas ditam (2025/2026) [FONTE]

- **Simples primeiro, agente só quando precisa**; roteamento classifica a entrada e manda para uma
  tarefa especializada; um guardrail separado funciona melhor que uma chamada só. Anthropic,
  <https://www.anthropic.com/research/building-effective-agents>
- **Permitir "não sei", ancorar em fonte e verificar.** Anthropic,
  <https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations>
- **Guardrails em camadas** (relevância, segurança, dado pessoal, regra, validação de saída) e
  **escalar para humano** por limite de falhas ou ação de alto risco. OpenAI,
  <https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf>
- **O LLM entende, a regra de negócio executa** (flows determinísticos e versionados). Rasa CALM,
  <https://rasa.com/docs/learn/concepts/calm/>. Google Dialogflow CX: resposta determinística,
  generativa ou híbrida, ancorada em base de dados.
  <https://docs.cloud.google.com/dialogflow/cx/docs/generative-deterministic>
- **Roteador semântico** por exemplos, antes do LLM. <https://github.com/aurelio-labs/semantic-router>
- **Medir o estado final e a consistência** (pass^k: só conta se acerta todas as k tentativas).
  Sierra, tau-bench, <https://sierra.ai/blog/benchmarking-ai-agents>
- **Conjuntos de avaliação tirados de conversas reais** e juízes calibrados contra humanos. Shopify,
  <https://shopify.engineering/building-production-ready-agentic-systems>
- **Humano sempre disponível**: a Klarna voltou atrás em 2025 depois de priorizar custo.
  <https://www.entrepreneur.com/business-news/klarna-ceo-reverses-course-by-hiring-more-humans-not-ai/491396>
- **Do lado da Anthropic** (skill `claude-api`, tabela de 25/09/2026): Haiku 4.5 US$ 1 / US$ 5 por
  milhão de tokens; Sonnet 5.5 US$ 2 / US$ 10 (leitura de cache US$ 0,20); Opus 5.5 US$ 4 / US$ 20.
  Saída estruturada (`output_config.format`, esquema JSON) garante o formato. Cache de prompt só vale
  acima de um prefixo mínimo: 512 tokens no Sonnet 5.5, **4.096 no Haiku 4.5** (prompt curto não
  cacheia nele, e tudo bem: é barato do mesmo jeito). No Sonnet 5.5 o raciocínio desliga com
  `thinking: {type: "between_tools"}`; `budget_tokens` e escolha forçada de ferramenta dão erro 400.

Traduzido para nós: **decidir em código, classificar barato, consultar de verdade, redigir com o
modelo em uma ida, verificar em código, e cair para o montado ou para a equipe quando falhar.**

## 6. A arquitetura alvo, para este código

```
mensagem
  │
  C1  determinístico, sem rede ........ cortesia · mídia/link · "sim/ok" com estado · sensível pela regra
  │      (resolve cerca de 55%: frase da casa, ou equipe)
  C2  triagem ......................... regra local + Jev (intenção + confiança, com a última fala da casa)
  │
  C3  consulta por intenção ........... o SERVIDOR escolhe a ferramenta: horário/entrega → FAQ e horários;
  │                                     produto → catálogo + Jev escolhe o produto; status → order_status;
  │                                     pedido (fase 1) → produtos achados + link da loja
  │      → FICHA: lista de fatos com id (nome, preço, disponibilidade, resposta da FAQ, link)
  C4  redação ......................... 1 chamada ao modelo: só a ficha, saída estruturada {resposta, fatos usados}
  C5  verificador (código) ............ preço, número, horário, link, produto, palavra de disponibilidade,
  │                                     alérgeno, tamanho, travessão  → passou: envia · falhou: montado
  C6  agente com ferramentas .......... só para a conversa de pedido (fase 2) e o que C2/C3 não entenderam;
                                        o texto final passa pelo MESMO verificador
  C7  equipe .......................... sensível, duas falhas, pedido que o chat não fecha (já existe)
```

### 6.1 Camada por camada

**C1, determinístico.** Já existe `small_talk.py`. Entra: mídia e link (comprovante vai à equipe ou
à ferramenta de endereço quando for localização); "sim/ok/confirmo/cancela" lidos contra o estado da
conversa (`Conversation.quote`, a última pergunta da casa): com resumo pendente, "sim" é
confirmação (o fluxo de `place_order` já exige isso); sem estado, um "Combinado!" curto. Sensível
pela regra (`handoff.py`) vai com o texto fixo da casa. Custo zero, menos de 50 ms.

**C2, triagem.** `triage.decide` continua o ponto único. Mudanças: o Jev recebe no `state` a última
fala da casa (redigida); a intenção só vale com confiança acima do corte (`PRESENT_AT`), senão a
mensagem vai para C6. Sai também o modelo da Anthropic na triagem quando o Jev estiver ligado (hoje
é uma ida extra ao Sonnet por mensagem só para isso). Custo: US$ 0,00002 por mensagem; latência
medida p95 226 ms.

**C3, consulta por intenção.** Um plano fixo por intenção, em código (a tabela `ROUTES` ganha a
coluna "o que consultar"). Fim da "busca de reserva sobre a frase inteira" (`agent.py:270-305`): a
busca recebe só os termos de produto extraídos (`strip_small_talk` já ajuda) e, quando houver mais
de um candidato plausível, o Jev escolhe (`choice`) ou a ficha leva até 3 e a resposta pergunta qual.
A saída é a **ficha**: fatos tipados com id, por exemplo `F1 produto "Croissant" preço R$ 13,00
disponível`, `F2 faq horário "Abrimos hoje às 7h"`, `F3 link cardápio https://...`. Teto da ficha:
3 produtos, 2 respostas de FAQ, 1 link.

**C4, redação grounded.** Uma chamada, sem ferramentas, saída estruturada:

```json
{"reply": "Bom dia! Temos croissant hoje, sai a R$ 13,00. Quer que eu separe?",
 "facts": ["F1"]}
```

Prompt curto (meta: menos de 900 tokens): voz da concierge no feminino ("Obrigada"), português do
Brasil, no máximo 3 linhas e 300 caracteres, uma pergunta só, sem markdown, sem travessão, emoji só
💛 ou ✨ e só se o cliente usar; afirmar somente o que está na ficha; se a ficha não responde,
dizer isso e oferecer a equipe ou o site. Entrada: ficha + até 4 falas anteriores + a mensagem.
Modelo: o placar decide entre **Haiku 4.5** (mais barato e rápido) e **Sonnet 5.5 com raciocínio
desligado** (`between_tools`, esforço `low`); ver decisão 1.

**C5, verificador.** Código puro, sem modelo:

- todo valor em reais da resposta existe na ficha, com o mesmo produto por perto;
- todo horário, data e número existe na ficha (exceto quantidade que o cliente disse);
- todo link é um dos links da ficha;
- todo nome de produto citado está na ficha; "temos", "disponível", "acabou", "esgotado" só para
  produto da ficha com a disponibilidade correspondente;
- nenhuma palavra de alergia ou ingrediente fora do texto fixo (alergia é da equipe e do aviso
  `food_safety_notice` da #1434);
- tamanho, travessão, emoji, e pelo menos um fato citado quando a ficha não está vazia.

Falhou: o cliente recebe a resposta montada, **já enxuta** (até 3 itens e o link, não o despejo de
hoje), e o caso vai para o conjunto de avaliação. O verificador é a mesma função para C4 e C6.

**Blocos travados.** Recap de pedido (`review_order`), confirmação (`place_order`), Pix e total
nunca são redigidos: saem de `render_result`. O redator pode pôr uma frase antes, nunca mexer no
bloco.

**C6, agente.** O laço de hoje continua para a fase 2 (sacola, endereço, pagamento) e para o que
ninguém entendeu, com Sonnet 5.5 (o padrão hoje é o Sonnet 5, de geração anterior), teto de idas
menor (3) e o verificador sobre o texto final em vez de descartá-lo.

**C7, equipe.** Sem mudança (D-018).

### 6.2 Custo e velocidade esperados

Premissas: 150 mensagens por dia (6 vezes a média observada, para não subestimar), 30 dias;
distribuição medida em 1.3; 45% chegam a C4; 5% a C6. Ficha e prompt: cerca de 2,2 mil tokens de
entrada e 100 de saída por redação. Preços da tabela da seção 5. [INFERÊNCIA nos tamanhos; medidos
na fatia 1]

| Por mensagem | Haiku 4.5 | Sonnet 5.5 |
|---|---:|---:|
| C1 (55%) | US$ 0 | US$ 0 |
| C2 Jev | US$ 0,00002 | US$ 0,00002 |
| C4 redação | cerca de US$ 0,0027 | cerca de US$ 0,0037 (prompt fixo lido do cache) |
| C6 agente (fase 2) | cerca de US$ 0,02 (Sonnet 5.5, 2 idas) | idem |

| Por mês | 50/dia | 150/dia | 300/dia |
|---|---:|---:|---:|
| Redação Haiku + agente | cerca de US$ 3 | cerca de US$ 10 | cerca de US$ 20 |
| Redação Sonnet 5.5 + agente | cerca de US$ 4 | cerca de US$ 12 | cerca de US$ 25 |
| Hoje (US$ 0,025 por resposta, piso medido, + triagem no Sonnet) | cerca de US$ 25 | cerca de US$ 75 | cerca de US$ 150 |

Latência alvo, do recebimento à resposta gravada (hoje inclui 1 s de atraso proposital):
C1 menos de 1,5 s; C2+C3+C4+C5 de 2 a 4 s (p95 6 s); C6 até 10 s. Hoje: p50 7 a 9 s com uma
ferramenta, 14 a 36 s com várias (1.2).

### 6.3 Como medir

- **Conjunto de conversas reais (golden set):** as entradas observadas (`triage_shadow`, já 168,
  crescendo) com o texto redigido, as 2 falas anteriores e a rota atual, conferidas no Admin (o
  `MessageIntentSample` já é a mesa de conferência). Para cada caso: rota esperada, fatos esperados,
  e o que a resposta não pode conter.
- **Placar** (comando novo `concierge_reply_eval`, irmão do `benchmark_intent_classifiers`): rota
  correta, verificador aprovado, fatos inventados (meta: zero), tamanho, latência p50/p95, custo por
  mensagem. Roda sem modelo por padrão (só C1 a C3 e o verificador sobre a resposta montada); com
  modelo, cerca de US$ 0,30 por 100 casos.
- **Consistência:** cada caso com modelo roda 3 vezes; só conta se as 3 passam (pass^3).
- **`intent_benchmark.py`** continua medindo a triagem (regra, embeddings, LLM, Jev) com os critérios
  do INTENT-PILOT-PLAN §7 (sensíveis ≥ 95%, conjunto exato ≥ 80%).
- **Em produção:** cada resposta grava no envelope a camada que respondeu, o modelo, tokens (incluindo
  a escrita de cache, hoje perdida), custo estimado (`shopman.shop.services.ai_pricing`), latência e o
  resultado do verificador. Falha do verificador entra no conjunto de avaliação.

## 7. Plano de execução (uma fatia = um PR)

| # | Fatia | Muda o que o cliente vê? |
|---|---|---|
| **F1** | **Régua.** (a) gravar por turno: camada, modelo, tokens com escrita de cache, custo estimado, latência (envelope da resposta; chave nova em `docs/reference/data-schemas.md`); (b) `concierge_golden_export`: casos a partir das entradas observadas, redigidos, com 2 falas de contexto; (c) `concierge_reply_eval` sem modelo, medindo a linha de base de hoje | Não |
| F2 | **Consulta por intenção (C3) e resposta montada enxuta.** Plano por intenção em código; fim da busca sobre a frase inteira; teto de 3 itens + link; "sim/ok" contra o estado (C1) | Sim, para melhor e sem modelo novo |
| F3 | **Redator + verificador em sombra.** `CONCIERGE_REPLY_MODE=shadow`: gera a redigida, verifica, grava no envelope; o cliente ainda recebe a montada. Placar Haiku 4.5 × Sonnet 5.5 | Não |
| F4 | **Liga o redator** (`composed`): primeiro na coorte do dono (modo `assist`), depois para todos, com queda automática para a montada | Sim |
| F5 | **Jev com contexto e escolhendo produto** (`choice`); troca da triagem para o Jev quando o placar bater a meta; sai a ida extra ao modelo na triagem | Sim (menos erro de rota) |
| F6 | **Agente da fase 2** em Sonnet 5.5, teto de 3 idas, texto final pelo verificador | Sim, na fase 2 |

A frente de alergias em curso (depois da #1434) é compatível: ela define o texto fixo que C1 e o
verificador usam. Coordenar para não haver duas fontes.

**F1 pronta para começar.** Arquivos: `shopman/storefront/concierge/service.py` (gravar escrita de
cache, latência e camada junto dos tokens, `service.py:1041`), `agent.py` (`_accumulate` já soma
`cache_creation_input_tokens`; falta levar ao registro), `management/commands/concierge_golden_export.py`,
`management/commands/concierge_reply_eval.py`, testes em `shopman/storefront/tests/`, e a chave no
`data-schemas.md`. Sem migração (tudo em `envelope`/`usage`, que já existem em
`ConversationMessage`). Critério de pronto: o placar sai no alpha com a linha de base atual
(rota, tamanho médio das respostas, fração com mais de 3 itens, latência e custo por camada).

## 8. Decisões do dono (respondíveis com sim/1/2)

1. **Modelo do redator:** 1) o placar decide entre Haiku 4.5 e Sonnet 5.5, pelo menor custo que
   passa no verificador (recomendo); 2) fixar Sonnet 5.5 já.
2. **Alergia, pagamento e reclamação** respondidos só com texto fixo da casa e a equipe, o modelo
   nunca redige sobre esses temas? sim (recomendo) / não.
3. **Contexto para o Jev:** mandar junto da mensagem a última fala da casa, redigida, para ele
   entender "sim", "mais 2", "o que tiver"? sim (recomendo) / não. (Amplia a D-028.)
4. **Tamanho da resposta:** até 3 linhas e no máximo 3 produtos; o resto pelo link do cardápio?
   sim (recomendo) / ajustar.
5. **Jev decidindo a intenção de verdade** quando o placar das conversas reais bater a meta
   (sensíveis ≥ 95%, acerto ≥ 80%), sem nova pergunta, com a regra local sensível sempre vencendo?
   sim (recomendo) / não.

## 9. O que ficou de fora, e por quê

- **Embeddings locais** como classificador: o piloto (`intent_benchmark`, concorrente `embed`) já
  mede; pedem `fastembed` na imagem, decisão à parte (INTENT-PILOT-PLAN §5). O Jev cobre a mesma
  função a custo desprezível.
- **Áudio** (Anota AI e Deeliv transcrevem): não medido aqui; é frente própria (transcrição e
  privacidade).
- **Latência real dos modelos novos**: estimada, não medida; a F1 e a F3 medem.
- **Volume real do WhatsApp inteiro**: a observação mostra 24 por dia em média; o número verdadeiro
  sai da F1.
