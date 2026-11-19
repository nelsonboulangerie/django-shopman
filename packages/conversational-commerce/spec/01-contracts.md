# Contratos: convenções, os 17 contratos, versão, forma canônica e vetores

> **Estado:** vigente
> **Dono:** F1

Responde: quais são os contratos, como se versionam, qual é a forma canônica e o hash, e onde
estão os vetores. A fonte é o código: `conversational_commerce/contracts/`. Este arquivo diz
o que o código garante e por quê; quando os dois divergirem, é defeito, e o teste que pegar
a divergência entra no mesmo PR da correção.

Derivado de: v2 5.5 (contratos de dados), 4.7 (contrato de efeito), Apêndice A (N14) e o
plano do framework, seções 2 (decisões 2a, 2b, 2c) e 3.2. Onde este arquivo se afasta da v2,
a linha diz **[DIVERGE]**; onde fecha algo que a v2 e o plano deixaram aberto, **[DECIDIDO]**.

## 1. Como um contrato é definido

- Cada contrato é uma `dataclass(frozen=True, slots=True, kw_only=True)` da biblioteca padrão.
  A anotação de tipo de cada campo **é** o contrato: um validador só (`validate.py`) a lê.
- A validação mora no construtor. Um registro que existe em memória já cumpre o contrato;
  `dataclasses.replace` que produziria um inválido levanta erro.
- O que a anotação não diz (combinações proibidas, totais, ordem de instantes) mora no
  `check()` de cada contrato e está listado na seção 6.
- O JSON Schema é **gerado** (`schema_export.py`) e versionado em
  `conversational_commerce/schemas/`. O esquema diz forma, tipo, enum e formato; as regras
  da seção 6 só o validador confere. Documento que passa no validador passa no esquema; o
  contrário não é garantido. Limite conhecido: para o JSON Schema, `750.0` é `integer`, então
  o veto ao float também é só do validador (o vetor `terms-float-amount` passa no esquema e é
  recusado aqui).
  [MEDIDO, 18/11, `jsonschema` 4.26, Draft 2020-12, fora do pacote] os 17 esquemas são
  válidos, o exemplo de cada contrato da suíte e todo vetor positivo passam no esquema. A
  conferência automática fica fora do pacote, porque o K38 proíbe `jsonschema` aqui dentro.
- Mudar um contrato pede, no mesmo PR: a dataclass, o esquema regravado
  (`python -m conversational_commerce.contracts.schema_export --write`), os vetores (se
  forem de termos ou concessões) e este arquivo. A suíte reprova a deriva do esquema.

### Tipos que um campo pode ter

| Anotação | No fio | Regra |
|---|---|---|
| `Identifier` | string | não vazia, sem espaço nenhum |
| `Text` | string | não vazia, sem espaço nas pontas |
| `Instant` | string | UTC, `YYYY-MM-DDTHH:MM:SS.ffffffZ`, sempre com os seis dígitos; instante que não existe é recusa |
| `CurrencyCode` | string | três letras maiúsculas (ISO 4217) |
| `DecimalText` | string | decimal normalizado: sem zero à esquerda nem à direita, sem `-0`, sem expoente (`"2"`, `"0.35"`, `"-0.5"`) |
| `Hash` | string | `sha256:` e 64 dígitos hexadecimais minúsculos |
| `SchemaVersion` | string | `MAIOR.MENOR` |
| `int`, `NonNegativeInt`, `PositiveInt` | inteiro | dentro de `±(2**53 - 1)`; booleano não é inteiro |
| `bool` | booleano | |
| `Literal[...]` | string | enum fechado |
| `X \| None` | valor ou ausente | ausente e `null` são o mesmo |
| `tuple[X, ...]` | lista | vira tupla |
| `Mapping[str, X]` | objeto | chave texto não vazio; vira `FrozenMap` |
| `JsonValue`, `JsonObject` | qualquer JSON, objeto JSON | congelado, sem `float` em nenhuma profundidade |
| união de objetos | objeto | discriminada por um campo de valor fixo (`status`) |

## 2. Envelope comum

Todo registro carrega:

| Campo | Tipo | Obrigatório | Nota |
|---|---|---|---|
| `schema` | `cc.<contrato>` | sim | constante do contrato |
| `kind` | nome do contrato (`TermsDocument`) | sim | constante; `kind` errado é `invalid_content` |
| `schema_version` | `MAIOR.MENOR` | sim | o construtor preenche a versão corrente |
| `id` | `Identifier` | sim | identificador do registro |
| `tenant` | `Identifier` | sim | inquilino |
| `environment` | `test` \| `shadow` \| `live` | sim | |
| `trace_id` | `Identifier` | sim | rastro |
| `cause_id` | `Identifier` | não | o registro que causou este |
| `occurred_at` | `Instant` | sim | |
| `recorded_at` | `Instant` | não | só a fronteira de persistência preenche; **fica fora do hash** |
| `producer` | `{name, version}` | sim | |
| `episode_id` | `Identifier` | não | nulo enquanto não ligado a episódio |
| `extensions` | | não é campo de fio | só em memória, nos contratos de observação (seção 3) |

[DECIDIDO] Os contratos que o plano lista com `episode_id` próprio (`ContextSnapshot`,
`DecisionRecord`, `Episode`, `Need`) usam o `episode_id` do envelope, e o `check()` o exige
não nulo. Um campo, um significado.

## 3. Versão e tolerância (decisão 2b)

- **Estritos (5):** `TermsDocument`, `AuthorizationGrant`, `ActionCommand`, `ActionReceipt`,
  `DeploymentProfile`. Versão fora de `SUPPORTED_VERSIONS` (hoje só `1.0`) é
  `unsupported_schema`, inclusive MENOR acima; campo desconhecido é `invalid_content`.
- **De observação (12):** os demais. MAIOR diferente é `unsupported_schema`. MENOR acima é
  aceito, e o campo desconhecido vai para `extensions`, sem interpretar. Campo desconhecido
  **sem** MENOR acima é `invalid_content`: quem fala a mesma versão não inventa campo.
- `extensions` não é campo de fio. O produtor de MENOR maior escreve o campo novo no nível de
  cima; o leitor mais velho o guarda em `extensions` e, ao reescrever, o devolve ao nível de
  cima. Por isso o documento reescrito é idêntico ao recebido, e o hash confere (teste
  `test_observation_keeps_minor_above_in_extensions`). Extensão com nome de campo do contrato
  é recusa.
- [DECIDIDO] A tolerância vale **só no nível de cima do registro**. Objeto aninhado é sempre
  estrito. Consequência para quem evolui o contrato: MENOR acrescenta campo opcional no nível
  de cima; campo novo dentro de objeto aninhado é MAIOR.
- A versão do pacote (semver, `__version__`) é separada da versão dos contratos.

## 4. Forma canônica e hash (decisão 2c)

Forma canônica de um documento (`canonical.py`):

1. JSON, chaves de objeto ordenadas por ponto de código Unicode;
2. separadores `,` e `:`, nenhum espaço fora de string;
3. UTF-8; caractere não ASCII sai como está; os escapes são só os obrigatórios do JSON:
   `\"`, `\\`, `\b`, `\f`, `\n`, `\r`, `\t`, e `\u00XX` com hexadecimal minúsculo para os
   demais controles abaixo de U+0020 (`/` e U+2028 não se escapam). Nenhuma normalização
   Unicode: o texto vale como veio;
4. **sem número de ponto flutuante** em lugar nenhum (nem `NaN`, nem `Infinity`): dinheiro é
   inteiro na menor unidade com moeda, quantidade é decimal em texto com unidade, estimativa e
   probabilidade são decimal em texto;
5. inteiro dentro de `±(2**53 - 1)`;
6. campo **opcional vazio** (ausente, `null`, lista vazia, mapa vazio) **não sai**. Um
   `JsonValue` obrigatório que vale `null` sai `null`; dentro de um valor JSON livre, `null` e
   vazio são do dono do valor e ficam.

Hash: `sha256:` seguido do SHA-256, em hexadecimal minúsculo, dos bytes da forma canônica do
documento **sem o próprio campo de hash e sem `recorded_at`**. Têm hash: `TermsDocument`
(`hash`) e `ContextSnapshot` (`hash`). O documento é recusado se o hash não conferir. O
produtor monta o registro sem hash e chama `seal()`; rascunho sem hash não vira documento.
`ActionCommand.content_hash` é outro hash, explicado na seção 6.

[DECIDIDO] **Sem float em contrato nenhum**, não só nos que têm hash. O plano pedia "sem
float em documento com hash"; estendo a todos porque um documento de observação vira insumo
de snapshot e de decisão, e um float que entra por ali reaparece num documento com hash.

[DECIDIDO] **`recorded_at` fica fora do hash.** O plano dizia "hash do documento sem o
próprio campo `hash`", mas `recorded_at` é preenchido depois, na fronteira de persistência:
dentro do hash, gravar mudaria a identidade dos termos já confirmados. O vetor
`terms-basic-recorded` prova que o hash não muda.

[DECIDIDO] **Opcional vazio não sai.** Assim um MENOR novo, cujo campo opcional está vazio,
produz o mesmo hash que a versão anterior, e "ausente" e "vazio" não são dois documentos.

## 5. Tipos de valor

| Tipo | Forma | Regra |
|---|---|---|
| `Fact` | `Known{status:"known", value, source, observed_at, valid_until?, source_version?}` ou `Unknown{status:"unknown", reason}` | `reason` fechado: `source_failed`, `stale`, `not_supported`, `forbidden`, `not_found`. `valid_until` depois de `observed_at`. Vencido é `Unknown(stale)`, nunca o valor velho (quem decide isso é o F4/F5, não o contrato) |
| `Prediction` | `Estimate{status:"estimate", value, method, population, version}` ou `Unavailable{status:"unavailable", reason}` | `value` é `DecimalText`. Nunca zero no lugar de desconhecido (N21) |
| `Money` | `{amount_minor: int, currency}` | sem float |
| `Quantity` | `{value: DecimalText, unit}` | sem float |
| `Producer`, `VersionRef` | `{name, version}`, `{id, version}` | |
| `IdentityEvidence` | `{kind, ref, assurance}` | `assurance` na escada `anonymous` < `transported` < `weak_verified` < `strong_verified` |

[DIVERGE] v2 5.5 diz "confiança calibrada" sem forma. Aqui a confiança é `Prediction`, e o
valor é decimal em texto, pela regra do float.

## 6. Os 17 contratos

Campos essenciais; o tipo exato de cada campo está na dataclass e no esquema gerado. "Regras"
são as do `check()`, além das de tipo.

### Estritos

**`TermsDocument`** (`cc.terms_document`, com hash). `terms_id`, `version` (≥ 1), `items[]`
(`ref`, `quantity`, `unit_price`, `line_total`), `adjustments[]` (`code`, `amount`), `total`,
`recipient` (`subject_ref`, `contact_ref?`), `fulfillment` (`mode`, `address_ref?`,
`window_start?`, `window_end?`), `conditions[]` (`code`, `value?`), `valid_until`, `hash`.
Regras: ao menos um item; `ref` e `code` de condição sem repetição; uma moeda só no documento;
linha e preço unitário não negativos; **`total` = soma de `line_total` + soma de
`adjustments`**, exato; `valid_until` depois de `occurred_at`; janela com fim depois do
início. Preço unitário × quantidade **não** é conferido: arredondamento é do sistema de
registro, e `line_total` é o que ele cobra.
[DIVERGE] v2 5.5 lista itens, quantidades, preços, destinatário, cumprimento, condições,
validade, versão e hash, sem lugar para frete, taxa ou desconto. Sem `adjustments`, ou o total
não fecha com as linhas (e a regra do total não existiria), ou a taxa viraria item falso.

**`AuthorizationGrant`** (`cc.authorization_grant`). `grant_id`, `subject`, `issuer`, `basis`
(`customer_confirmation`, `staff_approval`, `profile_line`), `purpose`, `action`, `targets[]`,
`terms_hash?`, `limits` (`max_amount?`, `max_uses?`), `identity_evidence[]`,
`confirmation_evidence?` (`event_id`, `event_assurance`, `after_terms`), `valid_from`,
`valid_until`, `revoked_at?`. Regras: ao menos um alvo, sem repetição; `valid_until` depois de
`valid_from`; `revoked_at` não antes de `valid_from`. Com `basis = customer_confirmation`:
`terms_hash` obrigatório, `confirmation_evidence` obrigatória, `after_terms` verdadeiro,
`event_assurance` diferente de `none`, e ao menos uma evidência de identidade (v2 4.7,
propriedade 1; N06). Confirmação anterior aos termos não é concessão: é recusa no contrato.

**`ActionCommand`** (`cc.action_command`). `command_id`, `decision_id`, `grant_id`, `action`,
`targets[]`, `parameters`, `terms_hash?`, `expected_versions{}`, `expected_ownership_epoch`,
`idempotency` (`scope`, `key`), `content_hash`, `deadline`. Regras: ao menos um alvo, sem
repetição; `deadline` depois de `occurred_at`; **`content_hash` é o hash da forma canônica de
`{action, targets, parameters, terms_hash?}`** (`command_content_hash`). Retentativa não muda
parâmetros, alvo nem termos (v2 5.5): se mudar, o hash muda, e mesma chave com outro hash é
conflito (N08, decidido pelo executor, F8). A chave de idempotência não entra no conteúdo.

**`ActionReceipt`** (`cc.action_receipt`). `command_id`, `status`, `effect`, `domain_refs{}`,
`observed_versions{}`, `error?` (`code`, `retry`: `never`, `same_key`, `after_reconcile`),
`reconciliation?` (`deadline`, `owner`), `supersedes?`. Só quatro combinações (v2 4.7):

| `status` | `effect` | Exige |
|---|---|---|
| `success` | `applied` | `domain_refs` não vazio (efeito comprovado); sem `error`; sem `reconciliation` |
| `failure` | `not_applied` | `error` com `retry = never` (nova intenção pede nova decisão); sem `reconciliation` |
| `pending` | `unknown` | `reconciliation` com prazo depois de `occurred_at`; `error`, se houver, nunca `retry = never` |
| `unknown` | `unknown` | idem: reconcilia com a mesma chave, nunca com chave nova |

`error.code` é o enum de erros estáveis (`ErrorCode`, v2 5.4). O enum mora em
`contracts/errors.py` porque é tipo de valor deste contrato; o significado operacional de
cada código é do `02-catalog-profile.md` (F2).

**`DeploymentProfile`** (`cc.deployment_profile`). `version`, `adapters{porta → capacidades[]}`,
`catalog_version`, `policy_version`, `house_rules_ref?`, `actions{movimento → authority,
min_identity{canal → degrau}, confirmation, caps[], line_ref?}`, `lines[]` (`id`, `setting`,
`owner`, `decided_at?`, `state`: `proposed`, `validating`, `approved`), `fact_sources{tipo →
source, validity_rule}`, `staff_queue?` (`role`, `nominal_acceptance`,
`accept_within_seconds`, `respond_within_seconds`, `after_hours_contingency`), `limits`
(`max_steps`, `max_seconds`, `max_queries`, `max_model_calls`, `max_spend`), `privacy`
(`purposes[]`, `retention_days{}`, `fields_by_recipient{}`), `metrics[]` (`id`,
`definition_version`, `window_seconds`, `design`). Regras: ids de linha e de métrica sem
repetição; `line_ref` aponta linha que existe; linha ausente não pode estar `approved`; linha
`approved` tem `decided_at`. Avaliar linha, ligar ação e o perfil de teste são do F2.
[DECIDIDO] O plano escreve a linha como "`value` ou `absent{reason}`". Aqui é
`setting: {status:"set", value} | {status:"absent", reason}`: um `value` que vale `null`
(decisão legítima) não se confunde com "sem decisão".

### De observação

**`InteractionEvent`** (`cc.interaction_event`). `channel_binding` (`channel`,
`conversation_ref`), `actor` (`customer`, `staff`, `system`), `event_identity` (`id?`,
`assurance`: `verified`, `provider_claimed`, `none`), `type` (`message`, `tap`, `correction`,
`staff_took_over`, `staff_returned`, `delivery_update`, `deadline_due`, `backend_event`),
`content_ref?`, `identity_evidence[]`. Regra: `id` existe se, e só se, `assurance` não é
`none`. Conteúdo pessoal vai por referência (`content_ref`), nunca no registro.

**`Understanding`** (`cc.understanding`). `event_id`, `acts[]` (`act`, `fields`, `span?`
(`start`, `end`), `confidence: Prediction`), `alternatives[]` (`acts[]`, `confidence`),
`signals` (`friction`, `risk`: `none`, `low`, `medium`, `high`, `unknown`), `reader`
(`name`, `version`). Regras: `end` > `start`; alternativa tem ao menos um ato.
[DECIDIDO] `event_id` explícito: o entendimento aponta o evento que leu, sem depender de
`cause_id`.

**`ContextSnapshot`** (`cc.context_snapshot`, com hash, imutável). `episode_version`,
`ownership_epoch`, `identity` (`subject_ref?`, `assurance`), `needs[]` (`need_id`, `type`,
`state`), `facts{chave → Fact}`, `hypotheses[]` (`claim`, `value`, `confidence`),
`unknowns[]`, `dialogue_state`, `relationship_state`, `open_commitments[]`, `profile_ref`,
`policy_ref`, `hash`. Regras: `episode_id` não nulo; identidade anônima não tem
`subject_ref` e as demais têm; necessidades sem repetição; **a mesma chave não é fato e
hipótese ao mesmo tempo** (hipótese não vira fato).

**`CandidateAction`** (`cc.candidate_action`). `candidate_id`, `need_id`, `move`,
`move_version`, `content`, `preconditions[]` (`code`, `result`: `pass`, `fail`, `unknown`,
`evidence?`), `expected_effects[]`, `reversibility` (`none_needed`, `reversible`,
`compensable`, `irreversible`), `authority_required` (`A0` a `A5`), `confirmation_required`,
`valid_until?`, `prediction`. Regras: ao menos uma precondição avaliada, códigos sem
repetição. Se o movimento existe no catálogo é pergunta do F2, não do contrato.
[DECIDIDO] `candidate_id` (a decisão aponta a candidata por ele) e `none_needed` em
`reversibility` (informar não tem o que reverter).

**`DecisionRecord`** (`cc.decision_record`, imutável). `decision_id`, `turn`, `context`
(`snapshot_ref`, `snapshot_hash`), `candidates[]` (`candidate_ref`, `need_id`, `move`,
`content`, `eligible`, `blocked_by[]`, `prediction`), `chosen[]` (índices em `candidates`),
`selection` (`method`, `tie_break?`, `propensity`, `experiment?`), `policy`, `profile`,
`model_calls[]` (`model`, `purpose`, `input_hash?`, `cost?`), `parent_decision_id?`. Regras:
`episode_id` não nulo; elegível não tem bloqueio e bloqueada tem ao menos um; `chosen` só
aponta candidata que existe e é elegível, sem repetição; `method = deterministic` exige
`propensity = {status: not_applicable}`, nunca "probabilidade 1"; `method = seeded` exige
`propensity = {status: recorded, distribution[] (candidate, probability), seed,
executed_probability}`, com a distribuição somando exatamente 1, só sobre candidatas
elegíveis (distribuição **depois** dos filtros, N17) e probabilidade executada maior que zero;
decisão não é mãe de si mesma. `cost` ausente é custo desconhecido, nunca zero (N21).
O registro guarda candidatas e escolha, não justificativa posterior: não há campo de texto
livre para motivo.

**`ReplyPlan`** (`cc.reply_plan`). `decision_id`, `parts[]` (`move`, `claims[]`: `slot`,
`backing`, `ref?`), `locked_blocks[]`, `verification` (`result`: `pass`, `repair`, `hold`;
`findings[]`: `code`, `part?`, `slot?`). Regras: ao menos uma parte; **afirmação com lastro
`fact`, `receipt`, `policy` ou `commitment` aponta o lastro (`ref`); cortesia não aponta
nada** (N01); verificação que não passou diz o que achou; achado aponta parte que existe.

**`ExposureEvent`** (`cc.exposure_event`). `decision_id`, `content_hash`, `realizer`,
`recipient`, `attempt` (≥ 1), `state` (`prepared`, `submitted`, `accepted`, `not_applied`,
`unknown`, `delivered`, `read`). Aceita não é lida (N16): são estados distintos.

**`OutcomeEvent`** (`cc.outcome_event`). `customer_ref?`, `metric` (`id`,
`definition_version`), `value?`, `window` (`start`, `end`), `observation` (`observed`,
`unknown`, `censored`, `not_applicable`), `source`, `decision_ids[]`, `command_ids[]`,
`assignment?`, `supersedes?`. Regras: `observed` tem valor; os outros três **não** têm
(desconhecido não vira zero, N21); fim da janela depois do início; não substitui a si mesmo.

**`Episode`** (`cc.episode`). `subject?`, `state` (`active`, `waiting_input`,
`waiting_authorization`, `waiting_effect`, `awaiting_handoff`, `human_owned`, `resolved`),
`version`, `ownership` (`owner`: `automation`, `queue`, `person`; `epoch`; `holder_ref?`),
`needs[]`, `waits[]` (`condition`, `owner`, `deadline`), `opened_at`, `resolved_at?`,
`reopened_from?`. Regras: `episode_id` não nulo; `resolved_at` existe se, e só se, o estado é
`resolved`, e não antes de `opened_at`; `human_owned` exige posse de pessoa; posse da
automação não tem `holder_ref`. As transições são do F4.

**`Need`** (`cc.need`). `need_id`, `type`, `state` (`open`, `blocked`, `satisfied`,
`withdrawn`), `depends_on[]`, `evidence[]`. Regras: `episode_id` não nulo; não depende de si
mesma; `satisfied` e `withdrawn` exigem evidência (retirada nunca é silêncio, v2 5.7).

**`Commitment`** (`cc.commitment`). `commitment_id`, `type` (`promise`, `case`),
`obligation`, `owner`, `deadline`, `fulfillment_criterion`, `evidence[]`, `state` (`open`,
`accepted`, `fulfilled`, `broken`, `expired`, `reopened`), `problem_code?`,
`requested_resolution?`, `reopened_from?`. Regras: `owner` obrigatório (sem dono não se
promete, N04); caso tem `problem_code`; promessa não tem `problem_code` nem
`requested_resolution`; `fulfilled` exige evidência; `reopened_from` existe se, e só se, o
estado é `reopened`.
[DECIDIDO] `deadline` é `{status:"set", at, rule_ref}` ou `{status:"absent", absent_reason,
contingency}`, a forma discriminada do "prazo, ou a falta dele com contingência" da v2.

**`MemoryItem`** (`cc.memory_item`). `memory_id`, `subject_ref`, `category`, `value`,
`evidence_state` (`declared`, `inferred`, `verified`), `source`, `purpose`, `sensitivity`
(`ordinary`, `personal`, `sensitive`), `valid_until?`, `supersedes?`. Regras: valor não nulo
(apagar é registro que substitui); não substitui a si mesmo.
[DIVERGE] A v2 chama o campo de "tipo" e o plano de `kind`. `kind` é campo do envelope (o
nome do contrato); aqui o campo é `category`.

## 7. Imutabilidade (N14)

Todo registro é `frozen` e `slots`: não aceita atribuição, remoção nem atributo novo. Lista
vira tupla e objeto vira `FrozenMap` no construtor, em qualquer profundidade; o registro
inteiro tem `hash()`. Corrigir é gravar outro registro (`dataclasses.replace` devolve um novo,
validado), e o anterior fica como estava. Testes: `tests/contracts/test_immutability.py`.

## 8. Vetores

Em `conversational_commerce/vectors/`, distribuídos no wheel, lidos por
`conversational_commerce.vectors.load(nome)`:

- `terms.json`: termos. Positivos trazem `expect.canonical` (a forma canônica do que entra no
  hash) e `expect.hash`; negativos trazem `expect.code` e `expect.path` (caminho com pontos;
  vazio quando o problema é do documento inteiro).
- `grants.json`: concessões. O positivo `grant-customer-confirmation` tem `binds_to:
  "terms-basic"`: o `terms_hash` dele é o hash daquele vetor.

Formato: `{"format": "cc.vectors/1", "contract": "<schema>", "cases": [{"name",
"description", "document", "expect": {"result": "valid" | "rejected", ...}}]}`.

Uma implementação em outra linguagem lê o mesmo contrato quando: reproduz `canonical` e
`hash` de todo positivo, recusa todo negativo com o mesmo `code` e o mesmo `path`, e devolve
o documento positivo idêntico depois de ler e reescrever. O teste do pacote confere o hash
pelo código e, de forma independente, por `hashlib` sobre o `canonical` gravado.

## 9. Erros

`ContractError(code, message, path)`, com `code` `unsupported_schema` (contrato ou versão que
o leitor não aceita) ou `invalid_content` (todo o resto). Ordem das recusas na leitura: não é
objeto; `schema` de outro contrato (`unsupported_schema`); `kind` errado; versão fora do
formato ou do aceito (`unsupported_schema`); campo desconhecido; campo; regra cruzada; hash.

## 10. Prova

`make test-conversational-commerce`, em `conversational_commerce/tests/contracts/`:

| Prova | Teste |
|---|---|
| Cada vetor de termos reproduz forma canônica e hash | `test_vectors.py` |
| Float em documento com hash é recusado (e em qualquer contrato) | `test_canonical.py` |
| Desconhecido e versão não suportada recusados nos cinco estritos | `test_versions.py` |
| `ActionReceipt` aceita só as quatro combinações, das doze possíveis | `test_action_receipt.py` |
| MENOR acima vai para `extensions` e volta igual | `test_versions.py` |
| Imutável (N14) | `test_immutability.py` |
| Esquema versionado sem deriva (`schema_export --check`) | `test_schema_export.py` |
| Regras cruzadas da seção 6 | `test_rules.py` |
