# Compromissos: promessa e caso, prazos, escalonamento e contingência

> **Estado:** vigente
> **Dono:** F9

Responde: o que a casa fica devendo quando diz "vou verificar", abre um caso ou encaminha; quem
é o dono e até quando; o que acontece quando ninguém aceita ou ninguém responde; e como a
resposta da equipe volta ao cliente. A fonte é o código: `conversational_commerce/ledger/commitments.py`,
os movimentos `verify_with_staff`, `open_case`, `handoff` e `wait` em `conversational_commerce/engine/moves/`,
o passo 6 e as retomadas de `engine/turn.py`. A forma do registro `Commitment` é do `01-contracts.md`.

Derivado de: v2 4.6 e 5.7 e o plano do framework, seção 3.9 (F9).

## 1. Uma forma só

| | Promessa | Caso |
|---|---|---|
| Nasce de | uma frase da casa: `verify_with_staff`, `handoff` | uma reclamação: `open_case` |
| Tem | obrigação, dono, prazo (ou a falta dele com motivo e contingência), critério de cumprimento, evidências, estado | o mesmo, mais o código do problema e a solução pedida |

Cada mudança é um registro `Commitment` novo, com a mesma identidade (`commitment_id`); o anterior
fica como estava (N14). O livro (`CommitmentLedger`) guarda o vigente, o histórico, os eventos e
o que é preciso para retomar: a necessidade, o vínculo de canal e o tíquete da equipe.

## 2. Estados e eventos

| De | Para | Quando |
|---|---|---|
| `open` | `accepted` | alguém aceita, nominalmente (`Engine.staff_accepted`) |
| `open`, `accepted`, `reopened` | `fulfilled` | com evidência (o contrato recusa `fulfilled` sem ela) |
| `open`, `accepted`, `reopened` | `broken` | o prazo escalado venceu de novo |
| `fulfilled`, `broken`, `expired` | `reopened` | a mesma necessidade volta (`reopened_from` aponta o registro anterior) |

Reconhecer, aceitar e cumprir são eventos distintos no livro (`acknowledged`, `accepted`,
`fulfilled`): encaminhar não é aceitar, e aceitar não é cumprir. Os outros eventos:
`deadline_passed`, `escalated`, `escalation_absent`, `broken`, `contingency` e
`customer_notified`.

## 3. Dono e prazo

- **Sem dono possível, não se promete** (N04). O dono é a fila do perfil (`staff_queue.role`),
  e só quando o adaptador da equipe declara a operação (`ask` ou `open_or_update`).
  `make_commitment` recusa dono vazio (`no_owner_possible`); no turno, a necessidade fica
  recusada e a decisão refeita diz a limitação. "Encaminhei" sem destinatário nunca chega a ser dito.
- **O prazo é o da fila**: `respond_within_seconds` para responder (verificar, caso),
  `accept_within_seconds` para aceitar (transferir), com `rule_ref` apontando a regra.
- **Prazo ausente vem com motivo e contingência.** Fora do expediente, ou sem saber o
  expediente, ninguém responde no prazo da fila: o prazo é `DeadlineAbsent`
  (`outside_business_hours`, `business_hours_unknown`) com a contingência do perfil
  (`staff_queue.after_hours_contingency`), e o molde da resposta não afirma prazo nenhum.

[DECIDIDO] O prazo e o dono vêm do `staff_queue` do perfil, que é estrutural e obrigatório
quando há fila. As linhas `staff.accept_within_seconds` e `staff.respond_within_seconds` do
perfil de teste repetem os mesmos valores e não são lidas aqui; a escolha evita duas fontes
para o mesmo prazo.

## 4. Os movimentos

| Movimento | Família | Quando | Cria |
|---|---|---|---|
| `verify_with_staff` | `resolve` | consulta cujo fato a fonte não tem (`not_found`, `not_supported`) | promessa; pergunta à equipe (`ask`) |
| `open_case` | `protect_and_fulfill` | ato de reclamação | caso, aberto na equipe (`open_or_update`) |
| `handoff` | `protect_and_fulfill` | o cliente pede uma pessoa (ato `request_human`) | promessa; episódio a `awaiting_handoff` |
| `wait` | nenhuma | o núcleo dá notícia de um compromisso aberto (`Engine.tick`) | nada: lê o compromisso |

[DECIDIDO] A fonte fora do ar (`source_failed`) e o fato vencido (`stale`) não são pergunta
para a equipe: voltam sozinhos. Continuam limitação, e a J1 não muda.

`inform_limitation` só é proposto quando nenhum desses movimentos é elegível para o pedido: sem
fila, a reclamação, o pedido de pessoa e o fato que falta são a limitação. Com a reclamação
vencendo, a política suspende toda iniciativa comercial no episódio
(`suspended_by_open_problem`, F5), e a dúvida da mesma mensagem segue respondida (K19).

Toda promessa é dita com o compromisso como lastro (`commitment:promise` ou `commitment:case`),
e o compromisso é registrado antes de a resposta ser composta. Em `shadow`, a equipe não é
chamada e nada entra no livro: o espaço aponta um compromisso que existe só no turno, e nada sai.

## 5. O passo 6 e as retomadas

No turno, depois do efeito (`08-effect.md`), para cada movimento de compromisso escolhido:

1. o prazo (seção 3) e o compromisso, com o dono possível ou a recusa;
2. a equipe: `ask` devolve um tíquete `routed` ou `rejected`; depois, `open_or_update` com o
   compromisso;
3. o livro, o compromisso na evidência da resposta e na gravação do turno;
4. na transferência, `handoff_requested` (posse da automação revogada) e o pedido ao canal.

A fila que recusa uma **pergunta** tira o dono: a promessa não é feita, e a decisão refeita
diz a limitação. A fila que recusa uma **transferência** (K20) deixa o compromisso com a
automação (`owner: core`), monitorado, com prazo e a contingência do perfil (evento
`contingency`, espera `handoff_not_accepted`); a resposta diz que se pediu, nunca que alguém
assumiu, e `staff_accepted` não tem aceite a registrar.

Retomadas, fora de um turno do cliente (`Engine._respond`: snapshot, decisão, molde verificado,
uma gravação, envio ao vínculo em que o compromisso nasceu):

| Chamada | O que faz |
|---|---|
| `staff_answered(ctx, commitment_id)` | a resposta da equipe entra como fato `Known` com autoria (`staff:<quem>`) e validade; o compromisso se cumpre com o tíquete como evidência; a resposta volta ao cliente (J3) |
| `staff_accepted(ctx, commitment_id)` | aceite nominal; na transferência, o episódio vai a `human_owned` com quem aceitou, e a época de posse sobe |
| `tick(ctx)` | cada prazo vencido é evento uma vez; escala conforme o perfil; avisa o cliente uma vez só (K22) |

**Escalonamento (K22).** A linha `commitment.escalation` diz a quem escalar. Com ela, o
compromisso passa a esse dono com prazo novo e o episódio vai a pessoa (`handoff_requested`); o
prazo escalado que vence de novo quebra a promessa (`broken`). Sem a linha, não se inventa a
quem escalar: o prazo vencido fica registrado (`escalation_absent`). Nos dois casos o cliente é
avisado uma vez, pelo movimento `wait`, e nunca de novo pelo mesmo compromisso.

**O fim da conversa não resolve nada (K21, N15).** O cliente que se despede deixa o episódio
`active` e o compromisso aberto; a correlação continua o mesmo episódio enquanto houver
compromisso aberto, mesmo passada a janela de inatividade; e a resposta da equipe ainda chega
pelo vínculo em que a promessa nasceu.

## 6. Prova

`make test-conversational-commerce`, em `conversational_commerce/tests/commitments/`:

| Prova | Escopo |
|---|---|
| J3 de ponta a ponta: pergunta, promessa com dono e prazo, resposta da equipe como fato, devolução | núcleo |
| J5 e K19: reclamação e dúvida, duas necessidades, a dúvida respondida, o caso com dono e prazo, nenhuma oferta | `core` |
| K20 a fila não aceita a transferência: monitorado, com contingência, nada afirma aceite | `adapter` |
| K21 o cliente encerra com compromisso aberto: o episódio e o compromisso seguem | `core` |
| K22 prazo vencido sem resposta: evento, escalonamento pelo perfil, cliente avisado uma vez | `adapter` |
| N04: sem dono possível, nenhuma promessa (no livro e no turno); fila que recusa a pergunta | núcleo |
| Prazo ausente fora do expediente, com motivo e contingência; sombra não chama a equipe | núcleo |
| Eventos distintos, transições conferidas, evidência exigida, cada prazo vencido uma vez | núcleo |

K20 e K22 são `adapter`: o adaptador real repete com a fila e o relógio dele.
