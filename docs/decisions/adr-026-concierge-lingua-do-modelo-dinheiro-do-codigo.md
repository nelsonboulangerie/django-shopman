# ADR-026 — Concierge de WhatsApp: a língua é do modelo, o dinheiro é do código

**Status:** Proposto (2026-09-03), aguarda palavra do dono
**Data:** 2026-09-03
**Escopo:** o atendimento conversacional de pedidos no WhatsApp da casa (o "concierge"): quem decide o que dizer, quem decide o que vale, e por onde a resposta viaja
**Origem:** [WHATSAPP-CONCIERGE-PLAN](../plans/WHATSAPP-CONCIERGE-PLAN.md); supera o mecanismo do [MANYCHAT-CONVERSACIONAL-PLAN](../plans/MANYCHAT-CONVERSACIONAL-PLAN.md) (um endpoint por intenção), que fica como registro
**Não decide:** se o WhatsApp passa por ManyChat (isso é a [ADR-009](adr-009-whatsapp-via-manychat.md), e continua valendo); qual modelo roda (é configuração, ver abaixo); se a casa oferece entrega no chat na v1 (pergunta aberta do plano)

---

## Contexto

O pedido por WhatsApp foi desenhado duas vezes antes desta. A primeira, o
"spec agentic" do redesign (`docs/_archive/redesign/06-spec-agentic.md`), fixou o
princípio do Pablo que ainda governa: **"ou resolve tudo no chat, ou leva pra web
e segue"**. A segunda, o MANYCHAT-CONVERSACIONAL-PLAN, tentou resolver no chat
com o próprio ManyChat: um flow por intenção (`#menu`, `#pedir`, `#status`), cada
um chamando um endpoint da casa que devolvia campos para o ManyChat montar a
frase. O plano parou no ponto em que toda conversa real para: o cliente não fala
em intenções. Ele escreve "quero 2 baguetes e um daqueles de chocolate pra
amanhã cedo, pode ser?" e nenhuma árvore de flow cobre isso sem virar um
labirinto de botões.

Um modelo de linguagem cobre. Mas um modelo de linguagem também inventa: preço
que não existe, pão que acabou, prazo que a casa não cumpre. E o WhatsApp tem
uma restrição de transporte que não é opinião: o External Request do ManyChat
corta em 10 segundos, e um turno de modelo com ferramentas não cabe nisso com
folga.

Três forças, então: a conversa precisa de língua livre; o pedido não pode ter um
número que não veio do sistema; e a resposta não pode esperar o modelo dentro do
request.

## Decisão

1. **O modelo decide a língua e a próxima ferramenta. Só isso.** O agente
   (`shopman/shop/concierge/agent.py`) recebe a transcrição e escolhe o que
   dizer e qual ferramenta chamar. Ele **nunca** calcula preço, afirma estoque,
   promete prazo ou gera artefato de pagamento. Todo número, disponibilidade,
   janela e código Pix que aparece na conversa veio de um resultado de
   ferramenta, e cada ferramenta (`shopman/shop/concierge/tools.py`) é código
   determinístico que só chama services existentes do Shopman: catálogo por
   listing, sessão do Orderman no canal `whatsapp`, disponibilidade com hold,
   `checkout.process`, `payment.initiate`. O prompt diz isso ao modelo; o código
   garante mesmo que o prompt falhe.

2. **Um pedido só se fecha com confirmação explícita, e a confirmação é presa a
   um orçamento.** `review_order()` devolve o resumo e um `quote_token`;
   `place_order(quote_token, ...)` recusa o token se a sacola mudou desde o
   orçamento. O cliente diz "sim" ao que viu, não ao que o modelo lembra.

3. **O ManyChat é gatilho e transporte, nada mais.** Conforme a ADR-009, o
   número é um só e a Meta é alcançada só pelo ManyChat. O flow faz UMA chamada
   (`POST /api/webhooks/manychat/conversation/`), recebe `202` em menos de um
   segundo e não mapeia resposta. A resposta volta **assíncrona**, pela API do
   ManyChat (`sendContent`, texto livre dentro da janela de 24 h que o cliente
   acabou de abrir), depois que o worker de diretivas rodou o turno. O handoff
   para a equipe é um campo personalizado (`concierge_handoff`) que o flow
   consulta antes de chamar a casa, porque não existe API para pausar automação.

4. **O modelo é configuração.** `SHOPMAN_CONCIERGE["model"]` (env
   `CONCIERGE_MODEL`, default `claude-sonnet-5`), esforço e teto diário são
   env. Trocar de Sonnet para Opus, ou voltar, é deploy de variável, não de
   código. Nada no código sabe qual modelo está rodando.

5. **Toda saída fixa é copy da casa.** O que o concierge diz sem o modelo
   (modelo fora do ar, áudio recebido, teto do dia, contato sem telefone,
   abertura sugerida) sai do registro `OmotenashiCopy` (chaves `CONCIERGE_*`),
   editável no Admin como qualquer copy de cliente.

## Consequências

- **Ganha-se** a conversa natural sem perder a integridade do pedido: o
  concierge pode errar de tom, nunca de valor. Um pedido que sai do chat é
  indistinguível de um pedido da loja para o Gestor, o KDS, o fiscal e o caixa.
- **Paga-se** com uma dependência nova em tempo de execução (a API da Anthropic)
  e com custo por conversa. O plano estima centavos por conversa em Sonnet 5;
  se o modelo cair três vezes seguidas numa conversa, a casa levanta um
  `OperatorAlert` (`concierge_unavailable`) e responde com a copy de fallback,
  que aponta para o site e para a equipe. A loja não depende do concierge para
  vender.
- **Aceita-se** a latência de alguns segundos entre a mensagem do cliente e a
  resposta (worker + modelo + ferramentas). É o preço de não estourar os 10 s
  do ManyChat, e é menor que a latência de um humano.
- **Recusa-se**, de propósito: WhatsApp Flows, Meta Cloud API direta, um segundo
  número, resposta síncrona mapeada em campo (já entregou a resposta do turno
  anterior quando lenta, segundo relatos da comunidade) e qualquer ferramenta
  que grave preço ou estoque sem passar por service.

## Limiares de revisão

Esta decisão volta à mesa se, com o piloto medido no Admin
(`Conversation.input_tokens/output_tokens/cache_read_tokens`, `state`,
`handoff_reason`):

| Sinal | Limiar | O que se revê |
|---|---|---|
| Custo por conversa | > US$ 0,25 em Sonnet 5 por mais de um mês | janela de memória, tamanho do prompt, esforço |
| Taxa de handoff | fora de 15–30% | abaixo: o bot está segurando conversa que devia soltar; acima: as ferramentas não cobrem o que o cliente pede |
| Reclamação sobre o concierge | qualquer uma sobre valor/estoque errado | é bug de guardrail, não de tom: para o piloto até achar a brecha |
| Conversa → pedido | < 20% depois da F3 | desenho da conversa (abertura, número de perguntas), não o mecanismo |

## Referências

- [ADR-009](adr-009-whatsapp-via-manychat.md): WhatsApp via ManyChat, lock-in consciente.
- [ADR-003](adr-003-directives-sem-celery.md): a diretiva `concierge.turn` roda no worker existente.
- [WHATSAPP-CONCIERGE-PLAN](../plans/WHATSAPP-CONCIERGE-PLAN.md): arquitetura, ferramentas, desenho da conversa, custo, fases.
- [Guia do operador](../guides/whatsapp-concierge.md): env, flow no ManyChat, transcrições, kill switch.
- `docs/_archive/redesign/06-spec-agentic.md:28`: o princípio binário do dono.
