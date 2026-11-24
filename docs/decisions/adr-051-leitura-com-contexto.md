# ADR-051 — Leitura com contexto: o leitor vê a pergunta no ar, o motor confere a coerência, e um verificador decide o conflito

**Status:** Aceito
**Data:** 2026-11-24
**Escopo:** `packages/conversational-commerce` (contrato `InterpretRequest`, porta `model`, turno, catálogo de condições, perfil); `shopman/storefront/concierge/model_reader.py` (leitor da Nice e portão do Jev); `shopman/shop/ai_governor.py` (a chamada do verificador)
**Origem:** ensaio no console do ar (24/11/2026, IA real DeepSeek + Jev, `--classes inform,order`); desenho aprovado pelo dono em 24/11 ("algo autocrítico que confira se faz sentido na continuidade da conversa"); compromisso DEV-2026-080

---

## Contexto

O ensaio no ar mediu que os leitores leem a frase **isolada**. A Nice pergunta "Qual horário de retirada
fica melhor?". O cliente responde "vou buscar às 16h", e o portão do Jev lê a resposta como `ask_hours`,
o horário de funcionamento da loja. A leitura é plausível para a frase sozinha e absurda na conversa. O
mesmo aconteceu com "amanhã às 16h, retirada" e "retirada amanhã 16h": 3 dos 7 casos reprovados.

Hoje a porta `model` recebe o texto e a lista de atos permitidos (`InterpretRequest.allowed_acts`), e
nada mais. O motor sabe qual pergunta está no ar (`dialogue_state`: `terms_closing`,
`terms_condition_question`, a oferta dos termos), mas não passa isso ao leitor e não confere se a leitura
responde a ela. O portão do Jev (no leitor da Nice) decide sem a IA, e sem a IA ninguém discorda dele.

Um remendo foi proposto: a fala que só diz *quando* recebe não passa pelo portão (`intents._only_fulfillment`).
O dono o recusou. A falha é de desenho e se repete com outras perguntas ("pix" a uma pergunta de
pagamento, "o do trabalho" à oferta do endereço, "na verdade 3" ao resumo).

## Decisão

Quatro peças, nesta ordem. As garantias são do **framework** (genéricas, com prova no Core); o mecanismo
de IA da casa (`ai_governor`) executa as chamadas, o custo e a telemetria; a Nice só configura limites no
perfil.

### 1. Leitura com contexto

`InterpretRequest` ganha `context: ReadingContext`, preenchido pelo motor a cada turno:

- `pending`: a pergunta da Nice no ar, ou nenhuma. Leva o tipo (`condition`, `condition_yes_no`,
  `terms_offer` ou `clarification`), o código da condição (`delivery_time_slot`, `payment_method`…) e
  as opções oferecidas, **por referência** (o leitor recebe a quantidade e os rótulos públicos, como
  "a partir das 15h"; nunca endereço nem nome);
- `expected_acts`: os atos que respondem à pergunta no ar, vindos do catálogo (seção 2);
- `open_conditions`: os códigos que o fechamento ainda pede (`requirements`), em ordem;
- `recent`: as últimas N falas da conversa (cliente e Nice), **por referência de conteúdo**. O leitor as
  resolve e as redige como redige a fala do turno (P17). N é do perfil (`limits.reading_context_turns`).

O motor passa a guardar no estado de diálogo o **código** da condição que perguntou (hoje só as de sim
ou não guardam). Sem isso, `pending` não diria o que foi perguntado.

O leitor usa o contexto como dado, nunca como instrução. Ele não muda a lista de atos permitidos: a
fala que muda de assunto continua legível.

### 2. Conferência de coerência (determinística, no motor)

Com uma pergunta no ar, cada leitura é classificada antes da decisão:

| Classe | Quando | Efeito |
|---|---|---|
| `answers` | algum ato está em `expected_acts` | segue |
| `rupture` | nenhum responde, e há ato do conjunto de ruptura do catálogo: mudança material (`change_quantity`, `place_order`, `cancel_order`), `deny`, `request_human`, `complain` | segue: o cliente mudou de assunto e a pergunta fica no ar |
| `suspect` | nenhum responde e nenhum é de ruptura: só pergunta (`ask_*`), cortesia ou `unknown` | vai ao verificador (seção 3) |

Os atos esperados vêm de uma tabela do catálogo, condição por condição. As condições do quando
(`fulfillment_date`, `fulfillment_type`, `delivery_time_slot`, `delivery_window`) esperam
`choose_fulfillment`; `payment_method` espera `choose_payment`; as do endereço esperam `give_address`.
As de sim ou não esperam `affirm`, `deny` e `ask_options`, e a oferta dos termos espera `affirm` e
`deny`. Sem pergunta no ar não há conferência: a leitura segue como hoje.

Também vai ao verificador a **discordância entre leitores**: o leitor devolve as leituras candidatas em
`Understanding.alternatives` (que já existe) quando elas trazem **atos diferentes**. Leituras do mesmo ato
com campos diferentes continuam na política de ambiguidade que já existe (spec 05, seção 2: duas leituras
numa mudança → perguntar).

### 3. Verificador com contexto (só no conflito)

A porta `model` ganha a operação `adjudicate(AdjudicateRequest) → Adjudication`. Ela recebe a pergunta no
ar, as condições abertas, as últimas falas (por referência) e as leituras candidatas (a do leitor, as
alternativas e, para `suspect`, a leitura que responde à pergunta, se o leitor a deu como alternativa).
Ela devolve **uma** candidata, ou **dúvida**.

- Só roda em `suspect` ou em discordância. Turno coerente não paga a chamada.
- Ela conta no orçamento de chamadas do turno (`TurnBudget`). O teto é do perfil
  (`limits.max_adjudications_per_turn`, padrão 1).
- Ela é registrada no registro da decisão: as candidatas, a escolha e o motivo, como as candidatas da
  política.
- Sem porta, sem orçamento, ou com a porta falhando, o resultado é **dúvida**. Nunca é chute.

**Dúvida → uma pergunta curta de confirmação**, em vez de agir. O motor escolhe o movimento
`ask_clarification` com o molde `ask_clarification.confirm_reading`, sobre a candidata que responde à
pergunta no ar ("Só para confirmar: retirada amanhã às 16h?"). Sem candidata que responda, ele repete a
pergunta no ar. O "sim" à confirmação aplica a candidata; o "não" devolve a pergunta. A frase é da casa: o
texto vai à coordenação antes de entrar.

### 4. Conferência da resposta (antes dos efeitos)

Depois da decisão e antes dos efeitos, a necessidade classificada `answers` precisa ter escolhido um
movimento que a consome (o catálogo diz quais movimentos atendem cada ato). Se ela caiu em
`inform_limitation`, `handoff` ou `ask_clarification`, a leitura vira `suspect` e passa uma vez pelo
verificador. Não há laço: um turno tem no máximo uma verificação.

### No leitor da Nice

O portão do Jev decide sem a IA só quando não há pergunta no ar, ou quando o ato dele está em
`expected_acts` ("sim" à pergunta de sim ou não). Com pergunta no ar e o ato do portão fora do esperado,
a IA lê com o contexto. Se as duas leituras trazem atos diferentes, ambas vão ao motor (`alternatives`),
e a seção 2 decide.

## Métrica

A bateria (`concierge_eval --battery`) ganha dois grupos:

- **Continuidade:** resposta curta a uma pergunta no ar ("16h", "às 10", "pix", "o do trabalho", "sim",
  "na verdade 3"). O caso declara a pergunta no ar.
- **Ruptura:** o cliente muda de assunto no meio do fechamento ("tem pão de queijo?", "quero mais um
  croissant", "cancela").

Meta para chamar o dono: cartões 100% e bateria ≥ 95%, medidas no console do ar pela coordenação.

## Ordem de entrega (PRs pequenos, empilhados)

1. Esta ADR.
2. Core: `ReadingContext` no contrato, o código da condição no estado de diálogo e a tabela de atos
   esperados no catálogo.
3. Loja: o leitor da Nice usa o contexto (prompt e portão) e devolve as alternativas.
4. Core: a conferência de coerência, `adjudicate` na porta e a confirmação na dúvida.
5. Loja: o verificador pela rota de IA da casa (`ai_governor`) e a frase de confirmação.
6. Bateria: os grupos de continuidade e de ruptura.
7. Core: a conferência da resposta.

## Alternativas recusadas

- **O remendo por regra** (`_only_fulfillment` no portão): o dono o recusou em 24/11. Ele conserta uma
  frase, e cada pergunta nova da Nice pediria outro.
- **O verificador em todo turno:** dobra o custo e a latência para conferir turnos que já são coerentes.
- **Sem portão, só a IA:** perde a economia do Jev nas falas que ele acerta (cortesia, "sim", horário
  sem pergunta no ar). O portão fica; ele só deixa de decidir quando a conversa contradiz a leitura dele.
- **O contexto só no prompt da Nice:** a coerência seria uma promessa do modelo, não uma garantia do
  framework. Cada loja teria de reinventar a conferência.

## Consequências

- O item 1 do ensaio no ar (o Jev lendo "vou buscar às 16h" como horário da loja) é consequência
  deste desenho, não um conserto à parte. Até a peça 3 entrar, o caso reprova na bateria; é a medida
  honesta.
- Contrato novo na porta `model` (`adjudicate`): a conformidade do pacote (spec 11) ganha o caso, e a
  porta que não implementa a operação declara isso em `capabilities` (a resposta vira dúvida).
- Uma chamada a mais **só** nos turnos em conflito. O custo aparece no medidor da casa (`AiInvocation`),
  por propósito.
