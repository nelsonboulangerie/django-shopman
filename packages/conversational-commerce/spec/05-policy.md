# Política: admissível, prioritário, melhor

> **Estado:** vigente
> **Dono:** F5

Responde: como uma decisão é tomada e registrada; quando perguntar; a restrição de
conselheiro; os limites de contexto; a seleção e o livro das decisões. A fonte é o código:
`conversational_commerce/policy/` e `conversational_commerce/ledger/decisions.py`.

Derivado de: v2 4.1 a 4.3 e 5.5, e o plano do framework, seção 3.5.

## 1. `decide(DecisionInput) -> DecisionRecord`

Função pura: sem relógio, sem id gerado dentro, sem porta. A entrada traz:

- os ids e o instante da decisão;
- o turno;
- o `ContextSnapshot` **selado**, cujo hash vai para o registro;
- o perfil;
- as propostas do turno: `Proposal(candidate_ref, need_id, move, content, situation,
  economics?)`;
- a semente, opcional, e a decisão mãe, opcional.

Mesmas entradas, mesmo registro (K40).

A decisão passa por quatro etapas, nesta ordem:

1. **Admissibilidade.** Cada proposta é avaliada no catálogo (F2, `evaluate_move`), e os
   códigos de bloqueio vão para `blocked_by`. `unknown` bloqueia a ação, não o sistema.
   Movimento fora do catálogo fica bloqueado com `move_outside_catalog` e nunca é escolhido.
2. **Ambiguidade** (v2 4.2). É a seção 2.
3. **Prioridade.** Para cada necessidade vence a candidata elegível da família mais alta
   (`protect_and_fulfill` > `resolve` > `clarify` > `commerce` > `follow_up`). Reclamação e
   dúvida são duas necessidades, e o plano atende as duas. Depois vêm as **suspensões entre
   necessidades**, até estabilizar:
   - movimento `protect_and_fulfill` escolhido suspende todo movimento `commerce`
     (`suspended_by_open_problem`, N19);
   - `handoff` escolhido suspende os movimentos de nível A2 ou acima nas outras necessidades
     (`suspended_by_handoff`): mudança de pedido fica suspensa quando uma parte vai para a
     equipe;
   - no máximo uma iniciativa comercial por decisão (`one_commercial_initiative`).
4. **Escolha.** Dentro da família vencedora, a ordem estável do catálogo. É a seção 4.

O registro traz todas as candidatas, elegíveis ou não, cada uma com os seus bloqueios. Toda
candidata leva `prediction = Unavailable(no_estimator)`, porque no D1 nenhum termo de
`Q(b, a)` tem estimador (v2 4.1: um termo só existe quando tem estimador válido).

## 2. Perguntar (v2 4.2)

`resolve_ambiguity(request_kind, reading_count, missing_required_field, economics?)`:

| Caso | Resultado |
|---|---|
| campo obrigatório ausente | `ask`, sempre, sem cálculo |
| uma leitura só | `act` |
| duas leituras numa **consulta** | `cover_both`: a resposta de leitura única (`inform`) é bloqueada com `two_readings_cover_both`, e `cover_readings` responde |
| duas leituras numa **mudança**, sem estimativa | `ask`: ação A2 ou acima é bloqueada com `ambiguous_change_ask_first` |
| duas leituras numa mudança, com `AskEconomics(p, L, c)` | `ask` se `(1 − p)·L > c`, senão `act` |

Toda conta é em `Decimal`, a partir de decimal em texto. Perguntar quando a resposta não muda
a decisão é atrito: isso é a precondição `answer_changes_decision` do catálogo.

## 3. Restrição de conselheiro (v2 4.3)

No D1 só existe o substituto (i), a aderência à necessidade declarada:
`adheres_to_declared_need(declarada, oferta)` é verdadeira só quando a necessidade foi
declarada e a oferta atende cada exigência dela. Exigência que o item não informa conta como
não atendida, nunca como "provavelmente sim". Sem necessidade declarada, não se recomenda. O
turno (F7) usa essa função para preencher `Situation.advisor_constraint_satisfied`.

Os limites de contexto (uma iniciativa não pedida por episódio; nenhuma com atrito alto,
problema aberto ou compromisso vencido; recusa respeitada) são precondições de `recommend` no
catálogo, mais as suspensões da seção 1.

## 4. Seleção

- **Determinística** (padrão): `method: deterministic`, `tie_break: catalog_order`,
  `propensity: {status: not_applicable}`. Nunca "probabilidade 1": seleção determinística
  não dá suporte contrafactual, e o registro diz isso.
- **Sorteada** (`seed` informado). [DIVERGE] (plano 3.5) Ela existe no D1 só para provar K32
  e K40. Só vale com a linha `policy.seeded_selection` aprovada e verdadeira (o perfil de
  teste a tem). O sorteio é uniforme entre as elegíveis da família vencedora, com pesos de
  quatro casas que somam exatamente 1. O registro guarda a semente, a distribuição **depois**
  dos filtros (só elegíveis) e a probabilidade da ação executada. Mesma semente e mesmos
  pesos, mesmo resultado.
  [DECIDIDO] No D1 a seleção sorteada decide uma necessidade por vez. O registro tem uma
  `selection` só, e misturar uma necessidade sorteada com outra determinística apagaria o
  que cada probabilidade quer dizer.

## 5. O livro das decisões (`ledger/decisions.py`)

`DecisionLedger` só acrescenta: o mesmo `decision_id` duas vezes é recusa, e a decisão com
mãe desconhecida também. `lineage(id)` vai da original até a última.

Quando uma guarda bloqueia **depois** a ação escolhida (K32), `redecide_after_block` grava
uma decisão **nova**, que:

- aponta a anterior por `parent_decision_id`;
- marca a candidata bloqueada como inelegível, com o motivo;
- escolhe a substituta da mesma necessidade pela ordem estável do catálogo;
- registra `propensity: not_applicable`: a probabilidade do sorteio original **não** é
  atribuída à substituta.

A anterior não muda (N14). Só se bloqueia depois o que tinha sido escolhido.

## 6. Prova

`make test-conversational-commerce`, em `conversational_commerce/tests/policy/`:

| Prova | Teste |
|---|---|
| Determinística grava `not_applicable`, nunca probabilidade 1 | `test_decide.py` |
| K04 fonte que falhou ou venceu bloqueia a ação dependente; vai à equipe | `test_decide.py` |
| K30 na mudança pergunta; na consulta cobre as duas; a regra de custo pode mandar agir | `test_decide.py` |
| K31 problema aberto ou atrito alto: nenhuma iniciativa comercial | `test_decide.py` |
| Duas necessidades atendidas; suspensões; uma iniciativa comercial | `test_decide.py` |
| K40 mesma política e mesma semente, mesma decisão | `test_decide.py` |
| Sorteio só com a linha do perfil; distribuição depois dos filtros | `test_seeded_and_ledger.py` |
| K32 bloqueio posterior gera decisão nova ligada, sem reescrever | `test_seeded_and_ledger.py` |
| Regra de custo e restrição de conselheiro | `test_ask_and_advisor.py` |
