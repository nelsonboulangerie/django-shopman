# O contrato de efeito: termos, confirmação, concessão, comando, efeito e recibo

> **Estado:** vigente
> **Dono:** F8

Responde: como uma ação que muda o negócio é autorizada, executada e comprovada; o que a
guarda do ponto de efeito recusa; o que se faz com cada recibo; como se reconcilia. A fonte é
o código: `conversational_commerce/authority/`, `conversational_commerce/ledger/receipts.py`,
os movimentos de efeito em `conversational_commerce/engine/moves/` e o passo 6 de
`engine/turn.py`. A forma dos registros é do `01-contracts.md`.

Derivado de: v2 4.7 e 5.4 e o plano do framework, seção 4 (F8).

## 1. A cadeia

```
necessidade → cotação (TermsDocument, com hash) → termos apresentados (Offer no ar)
  → confirmação (evento posterior) → concessão (AuthorizationGrant, o núcleo emite)
  → comando (ActionCommand, chave estável) gravado com a intenção de execução
  → executor: guarda + efeito + recibo numa unidade atômica → ActionReceipt
  → resposta com o recibo como lastro
```

| Elo | Quem | Onde |
|---|---|---|
| Cotação | a porta de comércio (`quote`), lida com passo do teto | `Engine._quote` |
| Termos no ar | o turno, quando `present_terms` é escolhido e a mensagem não foi segurada | `authority.Offer`, em `dialogue_state["terms_offer"]` |
| Concessão | o núcleo, nunca o modelo | `authority.issue_grant`, `authority.issue_line_grant` |
| Comando | o núcleo | `authority.build_command` |
| Guarda | o núcleo a entrega; o executor a chama | `authority.CoreEffectGuard` |
| Recibo | o executor; o núcleo grava | `ledger.ReceiptLedger`, `ledger.Settler` |

## 2. As sete propriedades (v2 4.7)

1. **Concessão por confirmação só presa a termos e a uma confirmação posterior.** `issue_grant`
   recusa (`GrantRefused`) confirmação de outro sujeito, inquilino ou ambiente, evento sem
   identidade estável, confirmação no mesmo instante ou antes dos termos, de outra época de
   posse, com termos vencidos ou sem evidência de identidade. O contrato do F1 já recusa
   `after_terms` falso.
2. **Retentativa não muda nada.** A chave de idempotência nasce do pedido
   (`<episódio>.<ação>.<alvo>.<termos ou parâmetros>`), não do instante. Mesma chave com outro
   conteúdo é `idempotency_conflict`, no livro e no executor, e o recibo não é sobrescrito.
3. **Quem emite é o núcleo.** O modelo não vê concessão, perfil nem identidade (F7, K25).
4. **A guarda é chamada no ponto de efeito.** Seção 3.
5. **Sucesso exige efeito comprovado.** Resposta que não chegou é `unknown`, nunca falha.
6. **Pendente e desconhecido têm prazo e dono da reconciliação.** Seção 4.
7. **Toda afirmação de efeito tem recibo de sucesso como lastro** (F6, K24). Pendente vira
   espera com o prazo do compromisso de reconciliação; falha vira a limitação.

A validade da concessão é a linha `grant.validity_seconds` e nunca passa da dos termos. Sem a
linha aprovada não há concessão, e a ação fica inelegível (K39).

## 3. A guarda (`CoreEffectGuard`)

Implementa o `Protocol` do F3. O executor a chama dentro da unidade atômica do efeito, com o
estado vigente (`EffectState`). Ela recusa, nesta ordem:

| Código | Quando |
|---|---|
| `authority_revoked` | concessão revogada (`Revocations`, ou `revoked_at`), ou época de posse diferente da do comando |
| `grant_expired` | instante fora de `[valid_from, valid_until)` |
| `terms_changed` | o hash dos termos vigentes não é o do comando |
| `revision_conflict` | a versão de um alvo não é a esperada |

A guarda também se recusa a nascer para um comando fora da concessão (outra ação, outro alvo,
outros termos). O executor que recusa grava recibo `failure / not_applied`, com `retry: never`.

[DECIDIDO] O K11 tem teste do teste: um executor falso que não chama a guarda
(`ExecutorThatSkipsTheGuard`, em `tests/effect/test_authority.py`) reprova o K11. Sem isso, um
K11 verde não provaria nada sobre o executor.

## 4. Recibos e reconciliação (`ledger/receipts.py`)

`ReceiptLedger` só acrescenta. O recibo que vale é o primeiro terminal; recibo que chega depois
dele é evidência guardada e não reabre nada. `next_step` diz o que fazer:

| Último recibo | Passo |
|---|---|
| nenhum, primeira tentativa | `execute` |
| nenhum, tentativa seguinte (o trabalhador anterior morreu) | `reconcile` antes de repetir (K14) |
| `success` | `done` |
| `failure` | `failed`: nova intenção pede nova decisão |
| aberto (`pending`, `unknown`) | `reconcile` com a MESMA chave (K08, K10) |
| aberto, prazo de reconciliação vencido | `to_person`: `reconciliation_overdue` na máquina do F4 |
| aberto, retenção da chave vencida | `locate` pela chave; sem achar terminal, `to_person` (K16) |

`Settler.settle` executa o passo e grava o recibo no livro e na porta de armazenamento. Erro de
porta que pode ter tido efeito (`effect_unknown`, `effect_pending`) vira recibo `unknown` do
núcleo, com o prazo da linha `effect.reconciliation_deadline_seconds`. A retenção da chave é a
menor entre a linha `effect.idempotency_retention_seconds` e a que o executor declara.

`work_execution` é o trabalhador da caixa de saída: reivindica `execute:<comando>`, leva ao
recibo e, se terminal, conclui o trabalho (`complete_work`, acrescentado à porta de
armazenamento). `Engine.reconcile(ctx, command_id)` reconcilia um efeito aberto depois do turno
e leva o episódio a `active` (recibo terminal) ou a `awaiting_handoff` (prazo vencido).

## 5. O passo 6 no turno

Para o movimento de efeito escolhido (módulo com `EFFECT = True` e `effect(state, need)`):

1. a concessão: por confirmação (`commit_order`) ou pela linha do perfil (`change_cart` e
   `set_fulfillment`, A2, reversíveis);
2. o comando, registrado no livro;
3. **uma gravação** com a concessão, o comando e a intenção de execução na caixa de saída,
   com o episódio em `waiting_effect` (N13). Só depois o executor é chamado;
4. `Settler.settle` com a guarda;
5. a gravação final do turno leva o recibo à máquina (`receipt_terminal` ou `receipt_open`),
   com o compromisso de reconciliação quando aberto.

Recusado no ponto de efeito (ou na concessão), decide-se de novo: uma decisão nova com
`parent_decision_id` apontando a primeira, que não muda (N14). Termos que mudaram ou venceram,
concessão vencida e confirmação anterior aos termos pedem termos novos (`present_terms`), com
uma confirmação nova (K07). Outras recusas dizem a limitação.

Um efeito por turno: o segundo movimento de efeito escolhido fica recusado
(`one_effect_per_turn`). Em `shadow` nada se executa (`shadow:effect_not_executed:<movimento>`),
e a resposta que afirmaria o efeito é segurada pela verificação.

O adaptador diz quem fala e qual é o carrinho dele por `Engine.subject_of(ctx, event) ->
Subject`, a partir do contexto confiável, nunca do texto. Sem carrinho, nenhuma mudança nem
cotação é proposta.

## 6. Movimentos

| Movimento | Nível | No D1 |
|---|---|---|
| `present_terms` | A1 | cota e mostra o total por espaço travado; episódio a `waiting_authorization` |
| `change_cart` | A2 | executa: quantidade absoluta, evento com identidade estável, reversível |
| `set_fulfillment` | A2 | executa: o recebimento (dia, retirada ou entrega, janela ou hora) dito em forma absoluta, evento com identidade estável, reversível |
| `commit_order` | A3 | executa: só o "sim" que responde à pergunta dos termos, na mesma época |
| `cancel_order`, `amend_order` | A3 | só precondição; com a linha do perfil; nenhuma jornada os executa |
| `grant_discount` | A4 | só precondição; teto da linha `commerce.discount_cap_minor` (`within_cap`) |

`set_fulfillment` (`engine/moves/set_fulfillment.py`) responde ao ato `choose_fulfillment`
com uma leitura só e o carrinho do sujeito. Aplica o que foi dito e nada além: só data, só
modo, ou tudo, e o comando leva só os campos ditos (`EffectPlan(action="set_fulfillment",
target=<carrinho>, parameters={date?, mode?, window?, time?})`, concessão pela linha). Nenhum
campo dito, nenhuma proposta. Data que não é ISO real, hora fora de `HH:MM`, modo fora de
`pickup`/`delivery`, janela com espaço ou `relative: true` deixam a ação inelegível
(`absolute_fulfillment` → `relative_fulfillment`), e a resposta é a limitação; duas leituras
perguntam antes. O executor confere de novo e recusa com os códigos da seção 7 do
`02-catalog-profile.md` (porta: `03-ports.md`, seção 2). A resposta é o molde mais completo
que o recibo sustenta, todos com lastro em recibo de sucesso:

| Molde | Espaços (campo do recibo) | Quando |
|---|---|---|
| `set_fulfillment.done` | `mode`, `date`, `window` | o recibo traz os três |
| `set_fulfillment.done_time` | `mode`, `date`, `time` | hora no lugar da janela |
| `set_fulfillment.done_day` | `mode`, `date` | sem janela nem hora |
| `set_fulfillment.done_date` | `date` | só o dia |
| `set_fulfillment.done_mode` | `mode` | só o modo |
| `set_fulfillment.updated` | `ref` (`effect`) | nenhum dos de cima (recibo só com o efeito) |

A casa troca a frase (`house_templates`) e formata os valores pelos formatadores dos espaços
(`date`, `mode`, `window`, `time`): a data na língua dela, o rótulo da janela pela referência.

O ato `place_order` entrou na lista fechada (`engine/acts.py`). `inform_limitation` só é
proposto quando nenhum movimento elegível faz o pedido, e `acknowledge` não responde ao "sim"
aos termos: é confirmação, não cortesia.

## 7. Prova

`make test-conversational-commerce`, em `conversational_commerce/tests/effect/`:

| Prova | Escopo |
|---|---|
| J4 de ponta a ponta: mudança, termos, confirmação, pedido, recibo | núcleo |
| K03 confirmação antes dos termos: recusada; fora de ordem no turno, termos de novo e o mesmo estado final | `adapter` |
| K06 confirmação de outro sujeito, inquilino ou ambiente; o carrinho alheio não é cotado | `adapter` |
| K07 preço muda depois da cotação: `terms_changed`, decisão nova ligada, termos novos, confirmação nova | `adapter` |
| K08 mesma chave e conteúdo depois de resposta perdida: um efeito, recibo de sucesso pela reconciliação | `adapter` |
| K09 mesma chave, outro conteúdo: conflito, recibo mantido | `adapter` |
| K10 queda depois do efeito: espera no lugar da confirmação; a reconciliação acha o pedido original | `adapter` |
| K11 revogação antes do ponto de efeito, e o teste do teste | `real_mechanism` |
| K12 transferência depois da submissão: reconciliado com a mesma chave, nada se desfaz | `real_mechanism` |
| K14 trabalhador morre no meio: o próximo reconcilia antes de repetir | `real_mechanism` |
| K15 concessão vence entre a decisão e a execução | `adapter` |
| K16 chave vencida com efeito desconhecido: nunca executa de novo; vai a pessoa | `adapter` |
| Sem a linha da concessão, nada se executa; sombra decide e não executa | núcleo |
| Recebimento (`test_set_fulfillment.py`): data, modo e hora; só data; só modo; o dito antes fica; janela desconhecida recusada com código estável; relativo e ambíguo não se aplicam; o mesmo evento não aplica duas vezes; o arnês reprova executor que aceita qualquer janela | núcleo e `adapter` |

K11, K12 e K14 são `real_mechanism`: aqui é simulação sobre os falsos; só valem rodados no
mecanismo do adaptador (transação e fila de verdade).
