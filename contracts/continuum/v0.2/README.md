# Continuum 0.2 — contratos e vetores

Este diretório contém artefatos neutros de produto e transporte para a
[especificação 0.2](../../../docs/specs/continuum-0.2.md):

- `message.schema.json`: envelope CloudEvents e cinco kinds normativos;
- `examples.json`: snapshots, patches, invalidation, gap e receipts válidos;
- `conformance-vectors.schema.json`: formato portátil do corpus;
- `conformance-vectors.json`: transições positivas e adversariais do reducer;
- `binding-control.schema.json` e `binding-control-examples.json`: barriers `ready`/`caught_up`
  e controles versionados de segurança;
- `binding-vectors.schema.json` e `binding-vectors.json`: cenários executáveis de HTTP, auth,
  cache, SSE, produtor, multi-stream, comandos e rollout;
- `conformance-manifest.schema.json` e `conformance-manifest.example.json`: declaração
  verificável das units, capabilities, profiles, layers, targets, limites e gates de rollout;
- `validate_contracts.py`: validação estrutural, referências, replacements e alinhamento de
  `dataschema`.

Os exemplos usam somente `example.test`, URNs e dados fictícios. Eles não são adapters nem
contratos de uma superfície Shopman.

## Semântica do runner

Um runner de conformance:

1. carrega `examples.json`;
2. para cada action `deliver_http`, `deliver_stream`, `repair_result` ou
   `canonical_poll_result`, faz deep copy do `message_ref`; `deliver_http` representa `200`
   canônico autorizado e atual, enquanto `deliver_stream` nunca melhora freshness;
3. aplica `replace` em ordem, usando JSON Pointer RFC 6901 e exigindo que o membro já exista;
4. valida a mensagem derivada com `message.schema.json`;
5. executa a transição indicada na spec;
6. compara todo campo presente em `expected` e aplica as regras de omissão abaixo;
7. reinicia estado, relógio monotônico, contadores e armazenamento entre vetores.

`submit_command`, `retry_command`, `lose_response` e `lookup_receipt` exercitam o produtor de
recibos. `effect_count` conta efeitos autoritativos, não requests. `buffer_overflow` injeta o
limite declarado do consumidor. Contadores em `expected.counts` são cumulativos dentro do vetor.

Regras de omissão impedem um runner permissivo de aprovar perda de estado:

- `data_state`, `transport_state` e `reconcile_state` são sempre igualdade exata;
- quando `data_state=absent`, stream/cursor/token/digest/state MUST estar ausentes;
- `absent_fields` é asserção explícita de ausência no resultado final; use-a quando uma transição
  precisa apagar metadado previamente presente, como o ETag invalidado por patch;
- quando uma projeção instalada não é repetida em `expected`, ela MUST permanecer byte-idêntica
  à última instalação aceita; omissão significa **preservar**, não ignorar;
- `projection`, `partition`, `schema` e `classification` seguem a mesma regra de preservação e
  fazem parte do estado instalado; um runner não pode reconstruí-las a partir da mensagem que foi
  rejeitada;
- `command_states` omitido significa preservar; quando presente, o mapa inteiro é comparado;
- `counts` lista todos os contadores não zero e é igualdade exata;
- `ui` só é asserção de reducer. Acessibilidade requer o gate em browser da spec.

Todo callback captura `security_generation_id` + `authorization_fence`; `repair_result` também
captura repair generation. Para target protegido, o runner valida generation, fence e lease
vigente imediatamente antes de parse e novamente antes de instalação; o gate final e a instalação
são serializados contra incremento do fence. Resultado atrasado ou expirado é descartado antes
daquele estágio. Um ETag só fica associado ao estado quando a action de snapshot declara
`representation_etag`; patch o invalida.

O corpus é mínimo, não exaustivo. Cada implementação adiciona testes de limites concretos,
autorização, cache, failover, rollout N/N-1 e propriedade de convergência.

Nos vetores de binding, todo `target` precisa ser mapeado pelo harness a um adapter documentado;
target desconhecido falha. Cada execução de unit escreve um único `result_document`, declarado no
nível da unit, e todos os targets contribuem para ele; assertions e `$result_ref` resolvem somente
nesse documento. `trace_evidence`, também da unit, prova a origem dos resultados. Assertion
sintetizada não vale. Ações `concurrent_write` do mesmo `concurrency_group` chegam juntas a uma
barreira e o trace demonstra overlap real. Valor de assertion iniciado por `@` referencia outro
RFC 6901 path no documento de resultado; `absent_or_lte` permite omitir uma diretiva opcional,
mas a limita quando emitida; `contains_token` faz parsing case-insensitive de campo HTTP separado
por vírgula e nunca substring. Em action body, o objeto de membro único
`{"$result_ref":"/path"}` referencia um resultado anterior. Schema green sozinho não é execução
do cenário.

Em uma action de resposta de repair, `fixtures` representa **um único** payload singleton/batch;
não são várias respostas. Cada item é um fixture ou `{fixture, replace}` derivado e revalidado. O
validator exige patches do mesmo stream/schema/epoch, links contíguos e headers de versão e
freshness iguais ao target/freshness do último patch. `Continuum-Age-Ms` ancora no validation cut
autoritativo daquela resposta. `expected_batch_violation` autoriza exatamente um defeito isolado;
qualquer outro defeito mascara o cenário e invalida o corpus. Rejeição é atômica: zero patch
parcial, zero instalação e zero renovação de freshness.

Vetores de limite declaram `requires_limits` e usam
`{"$limit_ref":"nome","delta":n}`. O runner resolve a expressão apenas contra `unit.limits`,
configura o adapter real, registra os valores originais em `/effective_limits` e prova a
configuração no trace. Usar o número ilustrativo do vetor, um default ou threshold menor que o
manifest falha. O validator exige catálogo fechado, set exato por unit, refs completos, expressão
não negativa e ao menos um vetor de fronteira aplicável para cada limite obrigatório. Cada nome
em `requires_limits` tem um `boundary_probe` separado: em dois casos isolados, o adapter real
aceita e observa N, depois rejeita N+1 especificamente por aquele limite, mantendo todas as
outras dimensões abaixo dos próprios tetos. Reject-all, cap oculto menor ou bloqueio por outro
eixo falham. O resultado normativo fica em `/limit_boundaries/<nome>` e o trace prova ambas as
execuções. `retry_after_ms` é serializado como `Retry-After`/`retry:` maior que o backoff local,
sem literal que possa ficar abaixo do limite declarado.

Aplicabilidade é conjuntiva por **conformance unit independente e target-scoped**, não pelo
produto cartesiano de um manifest global. Não existem kind simples/composto, composição, herança
ou união de facets/targets: cada unit cobre suas `capabilities`, declara seus `profiles` e
`layers`, e mapeia apenas targets daquele mesmo escopo. Cada vetor pode declarar
`requires_profiles` e, em binding, `layer`; isso torna o vetor candidato. Target ou result path
ausente naquela unit é **falha**, nunca motivo de não-aplicabilidade nem autorização para procurar
em outra unit. Ausência de `requires_profiles` no vetor significa que ele vale para qualquer unit
com aquelas capabilities (e layer, em binding).

Um vetor pode ainda declarar `excludes_capabilities`, `excludes_profiles` e `excludes_layers` para
isolar uma facet realmente ausente, como snapshot-only ou command-only. Esses predicados são
negativos factuais, não atalhos: o trace da execução precisa provar a ausência na implementação e
em todos os targets da unit; omitir a facet do manifest não basta. O validator rejeita interseção
entre requisitos e exclusões.

Adapters que compartilham qualquer estado — bytes persistidos ou em memória, cache/security,
subscription, journal, command ledger ou rollout — são consolidados em **uma única unit dona**,
com todos os targets, capabilities, profiles e layers factuais. Cada ID e cada identidade efetiva de
`state_domain_registry` é referenciada por exatamente uma unit. Não existe unit adicional de
relação/composição, e o mesmo domínio não pode ser reutilizado por duas units nem mesmo quando
elas têm a mesma classificação. Código e infraestrutura estritamente stateless não contam como
domínio. Um domínio misto public/protected ou com auth modes diferentes é NO-GO em 0.2.

Profiles de classificação valem para todo target de dados; profiles de binding/topologia, como
`fetch-stream + subscribe-first`, descrevem a relação entre papéis (stream + snapshot), não o
transporte individual de cada target. Todo target participa da relação declarada. Fragmentar scopes
ou criar facets sintéticas para fugir de um vetor falha conformance. Cada unit declara todo profile
e layer realmente exposto. `public-data` marca somente os targets públicos daquela unit, enquanto
`public-shared-cache` é adicional e só marca bytes públicos que podem atravessar cache
compartilhado.

Implicações não podem ser omitidas para escapar de vetores: toda capability de dados escolhe
exatamente public/protected e inclui snapshot + HTTP/cache/parser/producer. Nesta versão, toda
capability realtime usa a layer `sse`; WebSocket/gRPC ainda não podem alegar conformidade 0.2 sem
um perfil versionado futuro. A layer SSE escolhe exatamente native/fetch-stream, uma estratégia
de corte e snapshot + invalidate; snapshot-first exige replay e native usa subscribe-first; cache/SW,
multiplexação e SSR declaram suas layers/capabilities correspondentes. Command receipt é sempre
`protected-data` e declara `authorization`, `http`, `cache`, `parser`, `producer` e `command`.
Rollout declara os sete thresholds normativos e `cross_audience_leaks` é zero.

O corpus de reducer roda num harness isolado e neutro contra a API pura do reducer, configurada
para autorizar o fixture. A classificação pública dos fixtures core é estímulo, não claim sobre a
unit nem acesso ao deployment. Já o corpus de binding é target-scoped: transport, classificação,
auth mode e state domain dos fixtures precisam corresponder aos profiles da unit.

`Continuum-Age-Ms` mede o tempo desde o **último validation cut autoritativo**. No primeiro `200`
serializado no mesmo cut ele é igual a `body.data.freshness.age_ms`; depois disso o body e o ETag
continuam byte-stable, mas um `200` canônico posterior ou `304` autorizado para a tupla/head atuais
pode criar novo cut e reiniciar o header. A idade efetiva é
`Continuum-Age-Ms + HTTP Age + elapsed local`; nunca `max(body, header)`. Resposta direta do
origin pode omitir `Age` e nesse caso ele vale zero; qualquer caminho por cache/intermediário exige
`Age` verificável. Só a generation local
atual aceita a renovação: resposta tardia, header ausente/inverificável, réplica abaixo do head,
cache sem validação ou failover sem prova fenced de continuidade não renovam freshness.

Redirect é também target-scoped. Snapshot/repair, fetch-stream e lease podem seguir somente
`307`/`308` para origin configurada e allowlisted, no máximo um hop, com resposta `no-store`,
reautorização completa de authority/environment/tenant/principal no destino e sem encaminhar
credencial ambiente cross-origin salvo escopo explícito. `301`/`302`/`303`/`305`/`306`, origin não
allowlisted, loop e segundo hop abortam antes de lookup/bytes/CAS. Command issuance/submit/lookup
e native EventSource nunca seguem `3xx`; falham a operação/conexão e tentam apenas o endpoint local
configurado.

Lease protegida persiste dois fences monotônicos: `authorization_epoch` do contexto e
`lineage_policy_epoch` da linhagem. O CAS final de grant/renew compara os epochs aplicáveis, o
active flag e, para renew, a revisão da lease no mesmo ponto de serialização usado por
logout/revoke e purge/reauthorize. Barreiras controladas dos vetores forçam e registram os dois
ordenamentos duráveis: transição que vence primeiro bloqueia grant/renew velha sem reproduzir
sucesso idempotente; grant/renew que vence primeiro é terminalizada imediatamente pela transição
seguinte. Resposta tardia nunca atravessa o epoch, reativa lease nem instala generation; snapshot
protegido e command-only executam vetores separados desse mesmo contrato.

Fault injection de rollout segue as facets reais do target. Cenários comuns exercitam payload
inválido, callback tardio, failover e N-1; realtime, protected, patch/replay e command acrescentam
somente suas próprias falhas. Uma facet ausente conserva o threshold declarado, mas seu numerador
é zero, `omitted=false`, o trace prova que a superfície não existe e nenhuma operação é sintetizada.
Telemetria ausente ou denominador zero deixa a decisão inconclusiva e nunca promove.

`conformance-manifest.example.json` demonstra a forma de scopes explícitos; ele não alega
mapear todos os targets do corpus nem, sozinho, uma execução conforme.

## Validação estrutural

Com Python e `jsonschema`:

```bash
python3 contracts/continuum/v0.2/validate_contracts.py
```

O script rejeita membros JSON duplicados, números fora do domínio interoperável e surrogates
Unicode solitários; verifica os cinco schemas Draft 2020-12 com `FormatChecker`; valida
exemplos/controles/corpora; resolve fixtures e `message_ref`; exige JSON Pointer RFC 6901 válido
e membro existente em cada replacement; revalida toda mensagem derivada; e verifica unicidade,
facets e referências das conformance units.

Passar schema não prova as propriedades distribuídas. A declaração de conformidade também exige
os invariantes e fault injection de §§ 17–18 da spec.
