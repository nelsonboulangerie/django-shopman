# O turno: dez passos, tetos, queda sem modelo e ambientes

> **Estado:** vigente
> **Dono:** F7

Responde: os passos do turno, os tetos, a queda sem modelo, os ambientes `test`, `shadow` e
`live`, e como um movimento entra no laço. A fonte é o código:
`conversational_commerce/engine/` e `conversational_commerce/testing/journeys/`.

Derivado de: v2 5.3 e 5.8 e o plano do framework, seção 3.7.

## 1. `Engine.turn(ctx, raw) -> TurnResult`

`Engine(ports, profile, rules, formatters, resolve_content)` roda sobre as oito portas (F3).
Os dez passos da v2 5.3:

| # | Passo | O que o código faz |
|---|---|---|
| 1 | Receber | `workflow.receive`: grava e deduplica **antes** de qualquer trabalho (duplicata devolve `duplicate` e nada mais acontece). Liga ao episódio pela correlação (F4); sem episódio aberto, abre um |
| 2 | Portão sem modelo | Cortesia pura (regra local) não chama modelo. A regra local de risco já soma os atos dela |
| 3 | Entender | A porta de modelo, se há orçamento e ela responde; senão, a regra local. Ato fora da lista fechada (`ACTS`) vira `unknown`, e a queda é registrada (K05). O risco local **soma** atos, e o modelo nunca os tira |
| 4 | Montar o snapshot | Necessidades (uma por ato), leituras alternativas, a pergunta no ar do turno anterior, fatos lidos ao vivo com teto de passos. Nada é gravado aqui: nenhuma transação fica aberta enquanto se chama modelo ou porta |
| 5 | Decidir | Cada movimento registrado propõe para cada necessidade; `policy.decide` (F5) escolhe |
| 6 | Autorizar e executar | Concessão, comando gravado com a intenção de execução, guarda e recibo; recusa refaz a decisão, ligada à anterior (`08-effect.md`) |
| 7 | Dizer e verificar | `reply.compose` (F6): molde preenchido pelo lastro e verificação de saída |
| 8 | Gravar numa transação | `commit_transition` com comparar e gravar. Gravam juntos o episódio novo, o evento, o entendimento, o snapshot, a decisão, o plano de resposta, o snapshot depois do turno (a pergunta no ar) e a intenção de envio na caixa de saída. Conflito de versão devolve `superseded`, e a decisão sobre versão que mudou não é executada |
| 9 | Enviar e registrar a exposição | `channel.send` com a chave `send:<decision_id>`, a mesma da intenção na caixa de saída: o trabalhador que a consumir depois não reenvia. Em `shadow` não há envio (seção 4). Mensagem segurada não sai. Turno revogado por fala nova (`interrupted()`) não envia |
| 10 | Retomar esperas | `TurnResult.due_waits`: as esperas do episódio já vencidas, para quem agenda |

**Uma transição por gravação.** O episódio sobe uma versão por gravação, pela máquina (F4) quando o
estado muda: `question_sent` quando se pergunta e `evidence_arrived` quando a resposta chega.
Turno sem mudança de estado também sobe a versão, e o registro aponta o evento que o causou.
O turno com efeito grava duas vezes (F8): antes do efeito, com a intenção de execução, e no
fim, com o recibo e a resposta.

**A pergunta no ar** sai do snapshot gravado **depois** do turno (`dialogue_state`) e é lida no
turno seguinte por `store.latest_record`. Um "sim" só se liga a ela na mesma época de posse
(F4, K29).

## 2. Tetos e queda sem modelo

`TurnBudget` vem de `profile.limits`: passos (cada leitura de porta e cada chamada de
modelo), chamadas de modelo e gasto. Estouro nunca derruba o turno:

- modelo sem orçamento, ou fora do ar, cai para a regra local (`model_budget_exhausted`,
  `model_failed:<código>`);
- leitura sem passo restante vira fato `Unknown`, que não vira frase (`steps_exhausted:<o quê>`);
- custo de modelo desconhecido fica registrado (`model_cost_unknown`) e nunca conta como zero
  (N21).

Tudo vai para `TurnResult.fallbacks`. O perfil de teste tem zero chamada de modelo: o turno de
teste atende sempre pela regra local, pior porém certo.

## 3. Movimentos registrados

`engine/moves/<movimento>.py`, um módulo por movimento, descobertos pelo nome (sem lista
central). Cada módulo define:

- `MOVE`, igual ao nome do módulo e presente no catálogo;
- `TEMPLATES`, os moldes de que precisa;
- `propose(state, need)`, que devolve a candidata com a `Situation` ou nada;
- `reply(state, need)`, que devolve a parte da resposta.

O F8, o F9 e o F10 acrescentam módulos sem editar o laço.

Movimentos do F7: `acknowledge`, `inform`, `cover_readings`, `inform_limitation` e
`ask_clarification`. O F8 acrescentou os de efeito (`08-effect.md`, seção 6).
`inform_limitation` cobre o pedido de mudança que nenhum movimento elegível faz, a reclamação
(até o F9) e a consulta cujo fato está desconhecido (desconhecido não vira frase). Numa mudança
ambígua ele não é proposto: pergunta-se antes, porque ainda não se sabe o que foi pedido.

[DECIDIDO] A carga dos módulos não usa `import_module` com nome livre, que o K38 reprova. Ela
carrega o arquivo `engine/moves/<nome>.py` pelo caminho e recusa qualquer arquivo fora desse
diretório. Todo arquivo ali é do pacote e passa pelo AST do K38.

## 4. Ambientes (v2 5.8)

- `test`: adaptadores falsos; recibo marcado `test` nunca vale como prova de operação real.
- `shadow`: o turno decide e planeja a resposta sobre a entrada real, e grava o turno, mas
  **não** escreve na porta de comércio, **não** envia e não deixa intenção de envio (K36).
- `live`: envia.

## 5. Texto é dado (N23)

- O texto do cliente chega ao modelo só por referência protegida (`content_ref`), com a lista
  fechada de atos e a classe de dado `redacted`. O pedido não leva perfil, identidade nem
  autoridade (K25).
- Texto lido do catálogo entra na resposta só como valor travado de um espaço, com lastro, e
  nunca em pedido ao modelo (K26).
- Nada do que chega muda o perfil, a identidade ou o catálogo de movimentos.

A resposta da equipe como fonte (o outro lado do K26) chega com a porta de equipe no F9.

## 6. Jornadas de referência (`testing/journeys/`)

São dados roteirizados: cada passo traz a mensagem, o que o leitor roteirizado
(`ScriptedModel`) entende dela, os movimentos esperados, trechos do texto e o estado do
episódio. `run_journey(engine, ctx, steps)` devolve o que divergiu (vazio é verde), e um
adaptador roda a mesma jornada sobre as portas dele.

- **J1** · pergunta de produto respondida com fato. Preço com lastro e horário com lastro. Com
  a fonte do item fora, a resposta é a limitação, nunca um preço inventado.
- **J2** · pedido ambíguo esclarecido. Uma mudança com duas leituras pergunta "Item A ou Item
  B?" e o episódio vai a `waiting_input`. O "sim" seguinte se liga à pergunta e o episódio volta
  a `active`. Uma consulta com duas leituras cobre as duas.

## 7. Prova

`make test-conversational-commerce`, em `conversational_commerce/tests/engine/`:

| Prova | Escopo |
|---|---|
| J1 e J2 de ponta a ponta | núcleo |
| O turno atende com a porta de modelo fora; o perfil de teste nunca chama modelo; teto de passos cai e registra | núcleo |
| K05 ato fora da lista: nenhuma execução, queda registrada | `core` |
| K17 envio desconhecido: não marca entregue nem reenvia | `adapter` |
| K18 entregue sem suporte a leitura: "lida" segue não observada | `adapter` |
| K25, K26 instrução embutida na mensagem e no catálogo é dado | `core` |
| K36 sombra: nenhuma escrita em comércio, nenhuma exposição | `adapter` |
| K37 trocar canal ou modelo falso mantém política e autorização | `core` |
| Turno revogado não envia; decisão sobre versão que mudou não executa; o turno grava junto | núcleo |
