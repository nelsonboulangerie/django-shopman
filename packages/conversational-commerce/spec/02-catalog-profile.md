# Catálogo, níveis, identidade, perfil e erros

> **Estado:** vigente
> **Dono:** F2

Responde: que movimentos existem e com que precondições; os níveis de autoridade; a escada
de identidade; como o núcleo lê o perfil; os códigos de inelegibilidade; e o significado
dos erros estáveis. A fonte é o código: `conversational_commerce/catalog/` e
`conversational_commerce/profile/`. A forma dos registros (inclusive do `DeploymentProfile`)
é do `01-contracts.md`.

Derivado de: v2 4.1 a 4.3, 5.4, 5.6, 5.8 e o plano do framework, seção 3.2 (catálogo,
níveis, erros, perfil de teste). Escolher entre candidatas elegíveis é do F5
(`05-policy.md`), não daqui.

## 1. O catálogo diz o que existe; o perfil, o que fica ligado

[DIVERGE] (plano 3.2, v2 15.5) O catálogo é engenharia: o movimento, a família, o nível e
as precondições, cada uma com teste. Quais movimentos ficam **ligados** numa casa é decisão
do dono, no perfil. O perfil de teste liga todos.

Dois movimentos não passam pelo perfil: `inform_limitation` e `handoff`. Com qualquer linha
ausente, informar a limitação e encaminhar seguem possíveis (v2 5.8, K39). Todo outro
movimento passa por quatro precondições comuns antes das suas.

## 2. As precondições comuns

| Código | Passa quando | Código de bloqueio |
|---|---|---|
| `profile_enables_move` | o perfil tem `actions[movimento]`; se o movimento exige linha (`cancel_order`, `amend_order`, `grant_discount`), a regra aponta `line_ref`; a linha apontada está `approved` com valor | `profile_action_absent`, `profile_line_absent`, `profile_line_not_approved` |
| `authority_permitted` | o nível efetivo não é A5 | `authority_forbidden` |
| `confirmation_matches_level` | se o nível efetivo é A3 ou acima, a regra exige confirmação | `confirmation_weaker_than_level` |
| `identity_sufficient` | a regra diz o degrau do canal, e a identidade da conversa o alcança | `identity_rule_absent`, `identity_insufficient` |

**Nível efetivo** é o mais alto entre o do catálogo e o da regra do perfil: o perfil sobe o
nível de uma ação, nunca o desce. [DECIDIDO] Um perfil que marca `commit_order` como A1 sem
confirmação não afrouxa nada: a ação fica inelegível com `confirmation_weaker_than_level`.

## 3. Os 16 movimentos

Famílias, da que vence para a que cede (v2 4.1): `protect_and_fulfill` > `resolve` >
`clarify` > `commerce` > `follow_up`. Dentro da família, a ordem desta tabela é o desempate
estável. `wait` serve a qualquer família e fica por último na ordem.

| Movimento | Família | Nível | Precondições próprias | Cria | Jornada |
|---|---|---|---|---|---|
| `acknowledge` | resolve | A0 | `only_courtesy` | | J1 |
| `inform` | resolve | A0 | `facts_known_and_valid`, `personal_fact_identity` | | J1 |
| `cover_readings` | resolve | A0 | `two_readings`, `request_is_query`, `facts_known_and_valid` | | J2 |
| `inform_limitation` | resolve | A0 | `requested_action_ineligible` (fora do perfil) | | K39 |
| `ask_clarification` | clarify | A0 | `clarification_needed`, `answer_changes_decision`, `one_question_per_need` | | J2 |
| `verify_with_staff` | resolve | A0 | `fact_unknown`, `staff_owner_possible`, `staff_rule_declared` | promessa | J3 |
| `open_case` | protect_and_fulfill | A0 | `complaint_present`, `staff_owner_possible` | caso | J5 |
| `handoff` | protect_and_fulfill | A0 | `handoff_reason`, `staff_rule_declared` (fora do perfil) | | J3, J5 |
| `wait` | qualquer | A0 | `wait_is_defined` | | J3 |
| `present_terms` | resolve | A1 | `commerce_can_quote` | termos | J4 |
| `change_cart` | resolve | A2 | `stable_event_identity`, `absolute_quantity`, `change_is_reversible` | | J4 |
| `commit_order` | resolve | A3 | `grant_bound_to_current_terms`, `confirmation_after_terms`, `ownership_epoch_current` | | J4 |
| `cancel_order` | resolve | A3 | `within_self_service_window`, `confirmation_bound_to_target`; exige linha | | só precondição |
| `amend_order` | resolve | A3 | `addition_only`, `confirmation_bound_to_target`; exige linha | | só precondição |
| `grant_discount` | commerce | A4 | `one_discount_per_order`, `no_open_problem`; exige linha (o teto) | | só precondição |
| `recommend` | commerce | A0 | `explicit_need`, `advisor_constraint`, `unsolicited_within_limit`, `commercial_context_clear`, `refusal_respected` | | J6 |

O que cada precondição lê e o código de cada falha está em `catalog/preconditions.py`
(descrição em uma linha por precondição). Regras que valem nomear:

- `facts_known_and_valid`: fato `Unknown`, ou `Known` com `valid_until` no passado, é
  `fact_unavailable`. Vencido nunca vale como o valor velho (N02).
- `personal_fact_identity`: fato do cliente (A1) usa a regra `inform.personal` do perfil,
  com o degrau por canal. [DECIDIDO] A v2 diz "A0, ou A1 se o fato é pessoal"; uma ação só
  com dois níveis precisaria de duas regras, e `inform.personal` é a segunda. Sem ela, a
  leitura pessoal fica inelegível (`profile_action_absent`).
- `clarification_needed`: campo obrigatório ausente sempre se pergunta; duas leituras, só
  numa mudança. Numa consulta, cobrem-se as duas (`cover_readings`). O custo do erro
  (`(1 − p)·L > c`) é do F5; o catálogo só diz quando perguntar é admissível.
- `answer_changes_decision`: passa sem cálculo quando falta campo obrigatório (ressalva (i)
  da v2 4.2).
- `unsolicited_within_limit`: lê a linha `commerce.unsolicited_initiatives_per_episode` (um
  inteiro). Linha ausente ou não aprovada bloqueia com o código da linha.
- `commercial_context_clear`: problema aberto, atrito alto ou compromisso vencido bloqueiam
  a iniciativa comercial (v2 4.1, N19).

[DIVERGE] (plano 3.2) Três precondições a mais do que a tabela do plano nomeia:
`one_question_per_need` em `ask_clarification` ("uma pergunta no ar por necessidade" estava
no texto, não na lista), `staff_rule_declared` em `handoff` ("fila declarada") e
`facts_known_and_valid` em `cover_readings` (cobrir duas leituras é afirmar dois fatos).

## 4. Avaliar um movimento

`evaluate_move(movimento, situação, perfil)` avalia **todas** as precondições, em ordem, e
devolve `MoveEvaluation(move, results, eligible, blocked_by)`. `results` são
`PreconditionResult` do F1 (`code`, `result`, `evidence.reason`), prontos para a
`CandidateAction`. Elegível só com todas em `pass`.

A `Situation` é o que as precondições leem: `now`, `channel`, `identity` e, opcionais, os
sinais de cada precondição. Campo `None` quer dizer **não se sabe**: a precondição que o lê
devolve `unknown` sem ser chamada, com o código `<precondição>_unknown`, e `unknown`
bloqueia a ação, não o sistema (v2 4.1). Quem monta a situação é o F5.

`blocked_by` lista os códigos na ordem das precondições, sem repetição: a decisão registra
cada bloqueio, não só o primeiro (N17).

## 5. Níveis e identidade (v2 5.6)

| Nível | O que é | Exemplo genérico | Confirmação |
|---|---|---|---|
| A0 | informar fato público | horário, preço de vitrine | não |
| A1 | leitura personalizada | estado do pedido, endereço salvo | não |
| A2 | mudança reversível | sacola | não |
| A3 | compromisso vinculante | registrar, cancelar, alterar pedido | sim, presa ao alvo |
| A4 | exceção | desconto, compensação | sim, e teto do perfil |
| A5 | proibido à automação | o que o perfil vedar | não se aplica |

Escada de identidade: `anonymous` < `transported` < `weak_verified` < `strong_verified`. O
perfil diz, **por canal**, o degrau de cada ação (`actions[m].min_identity`). O catálogo não
escolhe degrau; canal sem regra é `identity_rule_absent`.

## 6. O perfil

- **Linha:** `read_line(perfil, id)` devolve o valor só se a linha existe, está
  `approved` e tem `setting.status = set`. Linha que não existe, ou `absent`, é
  `profile_line_absent`; `proposed` ou `validating` é `profile_line_not_approved`. Linha
  proposta não vale como aprovada (v2 5.8).
- **Códigos de inelegibilidade:** `IneligibilityCode` em `profile/codes.py` (os da seção 2,
  mais `capability_missing` e `fact_unavailable`). Precondição própria que falha usa um
  código dela (`terms_changed`, `open_problem`...).
- **Perfil de teste** (`profile/test_profile.py`, `build_test_profile()`): liga os 16
  movimentos e `inform.personal`, canal `test-channel`, A0 anônimo e A1 a A4
  `weak_verified`, confirmação em A3 e A4, fila da equipe declarada, nunca gasta (zero
  chamada de modelo, teto de gasto zero). Linhas, todas `approved`, com dono `framework`:

| Linha | Valor | Por quê |
|---|---|---|
| `episode.inactivity_window_seconds` | 86400 | episódio novo depois de um dia parado |
| `effect.idempotency_retention_seconds` | 604800 | cobre a reconciliação com folga (K16) |
| `effect.reconciliation_deadline_seconds` | 900 | pendente ou desconhecido não espera para sempre |
| `effect.reconciliation_fallback` | `person` | vencido o prazo, pessoa |
| `staff.accept_within_seconds` | 600 | padrão genérico de verificação |
| `staff.respond_within_seconds` | 1800 | idem |
| `terms.validity_seconds` | 1800 | termos velhos pedem cotação nova |
| `grant.validity_seconds` | 600 | curta de propósito (K15) |
| `commerce.unsolicited_initiatives_per_episode` | 1 | v2 4.1 |
| `dialogue.open_question_expiry` | `event` | vence por evento, não por relógio (v2 6.1) |
| `policy.seeded_selection` | `true` | K32 e K40 no D1 (plano 3.5) |
| `commerce.cancel_order`, `commerce.amend_order` | `true` | ligam as alçadas no teste |
| `commerce.discount_cap_minor` | 500 | teto do desconto no teste |

Durações em segundos, inteiras, pela regra do float (F1).

## 7. Erros estáveis (v2 5.4)

O enum `ErrorCode` mora em `contracts/errors.py` (é tipo de valor do `ActionReceipt`); o
significado é este. Erro não classificado nunca vira sucesso; se a submissão **pode** ter
ocorrido, a categoria é reconciliação (`effect_unknown`), por mais recuperável que pareça.

| Código | Quando |
|---|---|
| `unsupported_schema` | contrato ou versão que o leitor não aceita |
| `invalid_content` | documento que não cumpre o contrato |
| `capability_missing` | a porta não declara a capacidade de que a ação precisa |
| `identity_insufficient` | a identidade não alcança o degrau exigido |
| `object_forbidden` | o sujeito não tem acesso ao objeto (autorização por objeto, N11) |
| `fact_unavailable` | o fato é desconhecido ou venceu |
| `terms_changed` | os termos vigentes não são os da confirmação |
| `revision_conflict` | a versão esperada não é a atual |
| `authority_revoked` | a época de posse mudou, ou a concessão foi revogada |
| `grant_expired` | a concessão venceu |
| `confirmation_required` | falta confirmação presa ao alvo |
| `idempotency_conflict` | mesma chave com conteúdo diferente (N08) |
| `effect_pending` | aceito, ainda em execução |
| `effect_unknown` | não se sabe se aconteceu: reconciliar com a mesma chave |
| `budget_exhausted` | estourou um teto do turno (passos, tempo, consultas, modelo, gasto) |
| `provider_unavailable` | o provedor (modelo, canal, comércio) não respondeu, e nada pode ter ocorrido |

## 8. Prova

`make test-conversational-commerce`, em `conversational_commerce/tests/catalog/`:

| Prova | Teste |
|---|---|
| Todo movimento tem precondição própria, e toda precondição tem um teste que a faz falhar (meta-teste) | `test_catalog_meta.py` |
| Situação feliz elegível; entrada desconhecida bloqueia com `_unknown`; todo bloqueio é registrado | `test_catalog_meta.py` |
| K39: linha ausente torna a ação inelegível com código; `inform_limitation` e `handoff` seguem | `test_k39_profile_lines.py` |
| Linha `proposed` ou `validating` não vale como aprovada | `test_k39_profile_lines.py` |
| A5 proíbe; o perfil não afrouxa o nível; canal sem regra; fato vencido | `test_levels.py` |
