# Portas, guarda de efeito e adaptadores falsos

> **Estado:** vigente
> **Dono:** F3

Responde: quais portas o núcleo pede, com que operações e garantias; o que `capabilities()`
declara; a forma da guarda do ponto de efeito; os adaptadores falsos e as falhas injetáveis.
A fonte é o código: `conversational_commerce/ports/` e `conversational_commerce/testing/fakes/`.

Derivado de: v2 5.4 e plano do framework, seção 3.3.

## 1. Regras de toda porta

- **Contexto confiável.** Toda chamada recebe `TrustedContext(tenant, environment,
  subject?)`, montado pelo núcleo. Ele nunca nasce de texto do cliente.
- **Retorno tipado e versionado.** Retorno é contrato do F1 (que carrega `schema_version`) ou
  valor tipado da porta. Fato vem como `Known` ou `Unknown`, com fonte e validade.
- **Erro tipado.** Toda falha é `PortError(code)`, com `code` do enum estável `ErrorCode`.
  Erro não classificado nunca vira sucesso. Se a submissão **pode** ter ocorrido, o código é
  `effect_unknown` (`PortError.may_have_happened`), e o caminho é reconciliar com a mesma
  chave.
- **Capacidades.** Toda porta responde `capabilities() -> Capabilities(port, operations,
  guarantees, unsupported)`. As operações obrigatórias de cada porta estão no `OPERATIONS`
  do módulo dela, e o arnês reprova a porta que não as declara. `unsupported` diz o que a
  porta **não** faz (canal sem leitura, comércio sem `scarcity`).
- **Protocolos.** As portas são `typing.Protocol` com `runtime_checkable`. O adaptador não
  herda nada do pacote: basta cumprir a forma e passar no arnês.

## 2. As oito portas

| Porta | Operações | Garantias que o adaptador prova | Chaves de `guarantees` |
|---|---|---|---|
| `channel` | `normalize`, `send`, `delivery_status`, `request_handoff` | pelo menos uma vez sem duplicar; mesma chave de envio, mesma exposição; identidade nunca acima de `transported` sem prova; aceite do transporte não é aceite de pessoa; canal sem leitura nunca informa leitura | `at_least_once`, `event_identity`, `read_receipts`, `delivery_receipts` |
| `model` | `interpret`, `draft`, `score` | pedido com finalidade, orçamento e classe de dado (`public`, `redacted`, `personal`); saída fora do esquema é `invalid_content`; consumo com custo `KnownCost` ou `Unavailable` (nunca zero, N21); nenhum retorno é concessão nem recibo | `schema_validated_output`, `priced`, `data_classes` |
| `commerce_read` | `search_catalog`, `read_item`, `promise`, `quote`, `read_order`, `read_customer`, `read_policy`, `knowledge`, `scarcity` | fato com fonte e validade; autorização por objeto (`object_forbidden`); consulta não é reserva; a promessa traz quatro leituras (`factual`, `expected`, `planned`, `promisable`), nunca "reservado" (K27); cotação devolve `TermsDocument` selado; `scarcity` opcional, padrão `Unavailable` | `fact_validity_seconds`, `object_authorization`, `promise_is_not_reservation` |
| `commerce_execute` | `execute`, `locate`, `reconcile` | o contrato de efeito inteiro (v2 4.7): guarda chamada na unidade atômica do efeito; mesma chave e mesmo conteúdo devolvem o mesmo recibo; mesma chave com outro conteúdo é `idempotency_conflict` e o recibo não muda; resposta perdida é `effect_unknown` | `atomic_effect_guard`, `idempotency_retention_seconds`, `reconciliation` |
| `staff` | `ask`, `open_or_update`, `assign`, `record_acceptance`, `record_fulfillment`, `return_conversation`, `promote_answer` | roteado não é aceito (`ask` nunca nomeia quem aceitou); dono e prazo, ou o motivo da ausência; resposta entra como fato com autoria e validade; época de posse só cresce | `nominal_acceptance`, `answer_is_authored_fact` |
| `store` | `record_event_once`, `load_episode`, `latest_episode`, `latest_record`, `commit_transition`, `claim_work`, `complete_work`, `append_receipt` | evento com identidade estável grava uma vez (sem identidade, nunca deduplica, K02); comparar e gravar (`revision_conflict`); estado, registros e caixa de saída juntos; isolamento por inquilino | `compare_and_set`, `transactional_outbox`, `tenant_isolation`, `real_concurrency` |
| `clock` | `now`, `new_id`, `schedule`, `cancel`, `business_hours` | relógio não volta; ids únicos; prazo vencido vira trabalho reivindicável, não laço | `deterministic`, `monotonic` |
| `outcomes` | `harvest` | fonte independente do agente; janela aberta é `censored`; correção chega com `supersedes`; desconhecido explícito | `independent_source`, `censoring`, `supersession` |

### O que o motor exige da porta de comércio para dizer o estado depois do efeito

O turno lê depois do recibo de sucesso (`08-effect.md`, "Depois do efeito") e cita o que leu.
Para isso, cada porta devolve:

- **`read_order(ref)`**: fato `Known` com `ref` e **`total` em `{price_minor, currency}`**. Sem
  `total`, o pedido registrado cai no degrau de baixo (`commit_order.done_order`, sem total); a
  porta nunca inventa um total.
- **`read_item(ref)`**: fato com **`name` opcional**. É o nome que as linhas dos termos mostram;
  sem ele, a linha mostra a referência.
- **`quote(cart_ref)`**: o `TermsDocument` selado. Carrinho vazio ou cotação que falha vira
  `Unknown`, e a resposta da mudança cai no degrau de baixo (`change_cart.done_receipt`).
- **Recibo de sucesso do `change_cart` e do `commit_order`**: `domain_refs` traz **`effect`**, a
  referência do efeito no domínio (o carrinho, o pedido). É a faceta que os moldes citam
  (`{order}`, `{track}`); sem ela, a composição não tem o que mostrar.

O arnês e a conformidade de escopo `adapter` conferem essas formas no adaptador (K23, K24).

### O comando `set_fulfillment` na porta `commerce_execute`

O recebimento (quando e como o pedido é recebido) é um comando como o `change_cart`: alvo
único, o carrinho do sujeito; sem termos; concessão pela linha do perfil; reversível.

- **Parâmetros:** só os campos ditos, qualquer subconjunto não vazio de `date`
  (`AAAA-MM-DD`), `mode` (`pickup` ou `delivery`) e `time` (`HH:MM`). Campo ausente quer
  dizer **mantenha como está**, nunca "apague": o executor aplica o que veio e guarda o resto.
  A janela do dia não é parâmetro: é a casa que a dá.
- **Recusa, antes de qualquer efeito** (`failure` / `not_applied`, `retry: never`):
  `invalid_content` (forma) e `fulfillment_unavailable` (bem formado, mas a casa não atende). Seção 7 do
  `02-catalog-profile.md`.
- **Recibo de sucesso:** `domain_refs` traz `effect` (a referência do efeito) e o recebimento
  do alvo **depois** do efeito: `date`, `mode`, `time`, os que estiverem definidos, e a
  `window` que a casa dá ao dia quando não há hora.
  A resposta lê dali (`08-effect.md`, seção 6). O valor é `Identifier` (sem espaço): o rótulo
  da janela na voz da casa é do formatador do espaço `window`, a partir da referência.
- Muda a versão do alvo: os termos cotados antes deixam de valer.

O arnês (`check_set_fulfillment`) roda quando o adaptador dá `HarnessEnv.fulfillment` (um
recebimento que o sistema dele aceita): confere o efeito, o recibo com os campos aplicados,
a mesma chave devolvendo o mesmo recibo e a data fora de ISO recusada sem efeito, com o
código estável. Casa que não
liga o movimento não passa `fulfillment` e a checagem não roda.

Convenções de `store`: episódio novo é confirmado com `expected_version = 0` e `version = 1`;
toda transição incrementa a versão em um. `latest_episode(subject)` devolve o episódio mais
recente do sujeito (para a correlação), e `latest_record(episode_id, schema)` devolve o último
registro de um contrato gravado no episódio (o turno lê ali a pergunta no ar do turno
anterior). As duas entraram com o F7.

Convenção de `channel`: o `send` recebe a mensagem pronta por referência (`body_ref =
reply:<plano>`) e o hash do conteúdo. O `ReplyPlan` guarda as partes e o lastro, não a frase; o
canal de verdade lê o texto em `Engine.bodies[body_ref]`, um mapa em memória que o adaptador
compartilha com o canal na montagem. O texto nunca entra num registro.

## 3. A autoridade não é porta: a guarda

O núcleo emite a concessão e entrega ao executor uma `EffectGuard` (v2 5.4). O executor
chama `guard.verify(EffectState(now, terms_hash, versions, ownership_epoch))` **dentro da
mesma unidade atômica do efeito local**, com o estado lido ali. `verify` levanta `PortError`
(`grant_expired`, `authority_revoked`, `terms_changed`, `revision_conflict`) e então o
executor não aplica nada: devolve `failure` / `not_applied` com o código e `retry = never`.

`EffectState.terms_hash` é o hash dos termos **vigentes** do alvo, segundo o sistema de
registro, ou nulo quando os termos cotados deixaram de valer. Comparar com o hash da
concessão é trabalho da guarda.

Aqui está só a forma (o `Protocol` e o estado). A guarda de verdade é do F8
(`08-effect.md`). Adaptador que não consegue chamar a guarda junto do efeito declara
`atomic_effect_guard = false`, e a ação fica indisponível para autonomia (v2 5.8).

## 4. Os adaptadores falsos

`conversational_commerce.testing.fakes`, um por porta, sobre um relógio e um estado sintético
comuns (`FakeWorld`). Distribuídos no wheel, para que um adaptador novo os use como referência.

- **Domínio sintético** (`synthetic_domain.py`): três itens neutros (`ITEM-A`, `ITEM-B` sem
  nada em mãos, `ITEM-C` vendido por kg), dois clientes, duas políticas, moeda `XTS` (o
  código ISO 4217 reservado para teste), os dois modos de recebimento e a janela que ele dá
  ao dia sem hora (`window-afternoon`). Nenhuma loja real, nenhum nome de canal.
- **Determinismo:** o relógio só anda quando o teste manda (`advance`); ids em sequência por
  prefixo (`evt-0001`).
- **Falhas injetáveis** (`faults.py`): `FaultPlan.arm(operação, Fault, times)`. Cada falso
  consulta o plano a cada operação, e a falha some depois de disparar.

| Falso | Falhas |
|---|---|
| `FakeChannel` | `DUPLICATE_DELIVERY`, `OUT_OF_ORDER` (no `drain`), `SEND_UNKNOWN`, `PROVIDER_DOWN`; canal sem leitura (`read_receipts=False`) |
| `FakeModel` | `PROVIDER_DOWN`, `BUDGET_EXHAUSTED`, `OUT_OF_SCHEMA`, `ACT_OUTSIDE_LIST`; teto de chamadas do pedido; dado `personal` recusado; sem preço (custo `Unavailable`) |
| `FakeCommerceRead` | `SOURCE_FAILED`, `STALE_FACT`, `PRICE_CHANGES_AFTER_QUOTE` (os termos cotados deixam de ser os vigentes) |
| `FakeCommerceExecute` | `CRASH_BEFORE_EFFECT`, `CRASH_AFTER_EFFECT` (efeito existe, resposta perdida), `EFFECT_PENDING`; época de posse ajustável por episódio |
| `FakeStaff` | `QUEUE_REJECTS`, `LATE_ANSWER` |
| `FakeStore` | `VERSION_CONFLICT`, `WORKER_DIES` (a reivindicação vence e o trabalho volta), `DOUBLE_CLAIM` |
| `FakeOutcomes` | `IMMATURE`, `CORRECTED_LATER` |
| `FakeClock` | (determinístico por construção) |

[DECIDIDO] O falso de armazenamento declara `real_concurrency = false`: ele simula conflito,
morte de trabalhador e reivindicação dupla, mas não prova trava nem isolamento. K11 a K14 só
valem no mecanismo real do adaptador (plano, decisão 3).

## 5. Prova

`make test-conversational-commerce`, em `conversational_commerce/tests/ports/`: cada falso
cumpre o `Protocol`, declara `capabilities()` e passa no arnês de forma da própria porta
(`test_port_shapes.py`); o arnês reprova uma porta quebrada; cada falha injetável faz o que
o nome diz (`test_fakes_faults.py`).
