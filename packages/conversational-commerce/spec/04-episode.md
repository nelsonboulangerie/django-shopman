# Episódio, necessidade, posse, correlação e a casca durável

> **Estado:** vigente
> **Dono:** F4

Responde: o que é um episódio e uma necessidade; posse e época; correlação; a máquina de
estados e as esperas; o passo "receber" do turno. A fonte é o código:
`conversational_commerce/workflow/`. A forma dos registros (`Episode`, `Need`, `Wait`) é
do `01-contracts.md`.

Derivado de: v2 5.7 e 6.1 e o plano do framework, seção 3.4.

## 1. Três ciclos de vida

**Episódio** é a unidade de trabalho e de medida: uma necessidade do cliente, do surgimento à
resolução. **Necessidade** é um item da agenda dentro dele. **Compromisso** é o que a casa ficou
devendo (F9). Encerrar a conversa não resolve o episódio, e resolver o episódio não cumpre
compromisso que ficou aberto.

## 2. A máquina de estados (`machine.py`)

É a da v2 5.7, sem mudança. `transition(episode, event, expected_version, record_id)` faz
quatro coisas:

1. confere a versão que quem decidiu viu (`StaleVersion`);
2. confere que a transição existe na tabela (`InvalidTransition`);
3. incrementa a versão;
4. devolve um registro `Episode` **novo**, e o anterior fica como estava (N14).

| De | Evento | Para | Exige |
|---|---|---|---|
| `active` | `question_sent` | `waiting_input` | espera |
| `waiting_input` | `evidence_arrived` | `active` | |
| `active` | `terms_presented` | `waiting_authorization` | espera |
| `waiting_authorization` | `grant_valid` | `active` (reconferir e executar) | |
| `waiting_authorization` | `authorization_invalidated` | `active` (correção, expiração, termos alterados) | |
| `active` | `command_handed_off` | `waiting_effect` | espera |
| `waiting_effect` | `receipt_terminal` | `active` | |
| `waiting_effect` | `receipt_open` | `waiting_effect` (agenda reconciliação) | espera |
| `waiting_effect` | `reconciliation_overdue` | `awaiting_handoff` (vencido o prazo, pessoa) | espera |
| todo não resolvido, menos `awaiting_handoff` | `handoff_requested` | `awaiting_handoff` | espera |
| `awaiting_handoff` | `handoff_accepted` | `human_owned` | quem aceitou (`holder_ref`) |
| `awaiting_handoff` | `handoff_not_accepted` | `awaiting_handoff` (contingência) | espera |
| `human_owned` | `returned` | `active` | |
| `active`, `human_owned` | `resolved` | `resolved` | evidência |
| `resolved` | `reopened` | `active` (com `reopened_from`) | |

Qualquer outro par (estado, evento) é `InvalidTransition`, e evento anterior ao estado atual
também.

**Esperas.** Toda espera tem condição de retomada, responsável e prazo: o contrato `Wait` não
existe sem os três. Entrar ou permanecer num estado de espera sem espera, ou com prazo já
vencido, é recusa. O episódio carrega só a espera vigente; sair para `active` a limpa.

**Resolução.** `resolved` exige, para cada necessidade do episódio, o registro dela em
`satisfied` ou `withdrawn`, e todo compromisso informado em `fulfilled`. Silêncio, conversa
encerrada ou transferência não comprovam resolução (N15).

## 3. Posse e época

O episódio tem um dono (`automation`, `queue`, `person`) e uma **época**, que só cresce. A
época sobe a cada troca de dono:

- `handoff_requested` e `reconciliation_overdue`: o dono vira a fila, e a automação perde a
  posse;
- `handoff_accepted`: o dono vira uma pessoa, nomeada. Aceite é nominal: roteado não é aceito;
- `returned`: a automação volta, numa época nova.

Todo comando carrega a época esperada (F1) e é recusado se ela mudou (F8, N10).
`handoff_not_accepted` não muda o dono nem afirma aceite: o episódio segue monitorado.

[DECIDIDO] A época sobe em **toda** troca de dono, não só quando a automação perde a posse.
Assim, uma resposta lida contra a época certa nunca confunde duas posses de pessoas
diferentes.

## 4. Necessidades (`needs.py`)

| De | Para | Exige |
|---|---|---|
| `open` | `satisfied` | evidência nova (fato entregue, recibo, cumprimento) |
| `open` | `withdrawn` | evidência **e** `withdrawn_by`: `customer_act` ou `profile_rule`, nunca silêncio |
| `open` | `blocked` | |
| `blocked` | `open`, `withdrawn` | |
| `satisfied`, `withdrawn` | `open` | (a mesma necessidade volta) |

Uma necessidade bloqueada segura as que dependem dela, direta ou indiretamente
(`held_by_blocked`). `actionable` devolve as abertas que não estão seguradas. Reclamação e
dúvida na mesma entrada são duas necessidades, e as duas seguem acionáveis.

## 5. Pergunta no ar (`dialogue.py`, K29)

A pergunta no ar mora em `ContextSnapshot.dialogue_state["open_question"] = {question_id,
need_id, asked_epoch}` e vence por acontecimento, não por relógio. Quando a pessoa devolve a
conversa, `on_conversation_returned` a remove. Independente disso, `answer_refers_to` só liga
uma resposta curta ("sim") a pergunta feita **na época atual**: pergunta de época anterior
nunca recebe resposta, mesmo que alguém tenha esquecido de limpá-la.

## 6. Correlação (`correlation.py`)

O sujeito do episódio (`Episode.subject`) é `subject:<cliente verificado>` ou, sem identidade,
`binding:<canal>:<conversa>`. `correlate` liga a entrada ao episódio aberto mais recente do
mesmo sujeito quando há necessidade, espera ou compromisso aberto, ou quando a entrada chega
dentro da janela de inatividade do perfil. Fora disso, ou se tudo está resolvido, abre-se
outro. A função não recebe texto: **nunca** se unem pessoas por semelhança de texto.

Fica para o F9 reabrir um caso anterior a partir de uma reclamação nova, porque depende dos
compromissos.

## 7. A casca durável (`shell.py`)

- **Receber** (`receive`, `handle_inbound`): normaliza pela porta de canal e grava pela porta
  de armazenamento **antes** de qualquer trabalho. Duplicata (`created = false`) nunca chega
  ao trabalho, logo não cria comando (K01). Texto igual com identidade diferente são duas
  entradas (K02), e entrada sem identidade estável nunca é deduplicada.
- **Avançar** (`advance`): carrega o episódio, aplica a transição e confirma com a versão
  vista, gravando juntos o registro novo, os registros produzidos e a caixa de saída. Em
  `revision_conflict`, recarrega e tenta sobre o estado novo. Se lá o evento não se aplica
  mais (o vencedor já o consumiu), devolve `superseded`, sem decisão nem efeito novos (K13).
  Se ainda se aplica, confirma na segunda tentativa.

## 8. Prova

`make test-conversational-commerce`, em `conversational_commerce/tests/workflow/`:

| Prova | Teste |
|---|---|
| Toda transição da tabela, e a recusa de todo o resto | `test_machine.py` |
| Espera sem condição, responsável ou prazo é recusada | `test_machine.py` |
| Época só cresce; aceite nominal; resolução com evidência; reabertura | `test_machine.py` |
| Necessidades | `test_needs.py` |
| Correlação | `test_correlation.py` |
| K01, K02 (`adapter`), K13 (`real_mechanism`, simulado), K29 (`core`) | `test_k_episode.py` |
