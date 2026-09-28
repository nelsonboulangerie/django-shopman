# Continuum 0.2 — perfil de continuidade de projeções

**Status:** draft para revisão; não aprovado para produção\
**Data:** 2026-09-28\
**Codinome:** Continuum (provisório; ver [§ 19](#19-nome-e-publicação))\
**Artefatos normativos:**
[`message.schema.json`](../../contracts/continuum/v0.2/message.schema.json),
[`binding-control.schema.json`](../../contracts/continuum/v0.2/binding-control.schema.json),
[`conformance-vectors.json`](../../contracts/continuum/v0.2/conformance-vectors.json) e
[`binding-vectors.json`](../../contracts/continuum/v0.2/binding-vectors.json), com seus schemas,
exemplos e validator no mesmo diretório\
**Origem:** [WP de SSR/SSE progressivo](../plans/WP-PROGRESSIVE-SSR-SSE-CONTINUITY.md)\
**Revisão adversarial:**
[`continuum-0.1-adversarial-review-20260927.md`](../reports/continuum-0.1-adversarial-review-20260927.md)

---

## 1. Resumo

Continuum é um perfil para instalar, manter e reparar no cliente uma **projeção de leitura
autoritativa e single-writer**. Ele combina padrões existentes em vez de criar um transporte ou
modelo de consistência novo:

- [CloudEvents 1.0.2](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md) e
  seu [JSON Event Format](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/formats/json-format.md)
  fornecem o envelope estruturado;
- [HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) e
  [HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111) fornecem validação condicional,
  precondições e cache;
- [SSE](https://html.spec.whatwg.org/multipage/server-sent-events.html) pode transportar
  notificações;
- [JSON Patch](https://www.rfc-editor.org/rfc/rfc6902) e
  [JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396) podem representar deltas;
- [Problem Details](https://www.rfc-editor.org/rfc/rfc9457) representa falhas;
- [RFC 8895](https://www.rfc-editor.org/rfc/rfc8895) é o precedente direto para full replacements
  e patches JSON sobre SSE.

O delta específico deste perfil é pequeno: uma identidade de stream ligada à autoridade de
segurança; um cursor semântico separado do cursor de transporte; aplicação exata
base→resultado; freshness monotônica; repair explícito; e recibos idempotentes opcionais para
comandos.

A versão 0.2 corrige hipóteses inválidas da 0.1. JSON Patch **não** é idempotente em geral,
`Last-Event-ID` **não** é revisão de estado, um callback pós-commit **não** elimina dual write,
e uma confirmação de escrita **não** prova que uma read model já observou o efeito.

## 2. Linguagem normativa e conformidade

As palavras **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT** e **MAY** têm o
sentido da BCP 14, formada pela [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) e pela
[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174), quando aparecem em maiúsculas.

Uma implementação só pode declarar conformidade com uma capability que implemente todos os
requisitos correspondentes e passe os vetores indicados em [§ 17](#17-conformidade).
"CloudEvents-compatible", "SSE-resumable" ou "exactly once" não são alegações equivalentes à
conformidade com esta especificação.

## 3. Escopo e não objetivos

### 3.1 Dentro do escopo

- bootstrap SSR ou HTTP de uma projeção JSON;
- validação condicional e invalidação dessa projeção;
- atualização monotônica por snapshot ou patch;
- detecção de duplicata, regressão, gap, compactação, mudança de epoch e equivocation;
- recuperação explícita sem apagar prematuramente o último estado utilizável;
- separação entre estado de dados, sincronização, comando e segurança;
- recibo durável e idempotente opcional para uma escrita autoritativa;
- limites, telemetria, evolução de schema, privacidade, cache e acessibilidade.

### 3.2 Fora do escopo

Continuum 0.2 **não** é:

- event store, log de domínio ou formato de evento de negócio;
- protocolo de consenso, transação distribuída, causalidade geral ou CRDT;
- mecanismo multiwriter ou de merge offline;
- substituto para autorização, CSP, TLS, CDN, service worker ou banco de dados;
- linguagem genérica de dependências entre streams;
- garantia de entrega exatamente uma vez;
- sistema de componentes, política visual ou aprovação de loading/skeleton;
- obrigação conceitual de usar SSE. WebSocket, HTTP streaming, gRPC e logs podem carregar o
  mesmo modelo somente quando outro binding declarar semântica, limites e vetores equivalentes;
  o binding de conformidade publicado com a 0.2 cobre apenas SSE, nativo ou via fetch-stream.

## 4. Modelo conceitual

### 4.1 Termos

**Projeção** é uma representação JSON derivada de estado autoritativo, descartável e
reconstruível.

**Stream** é a sequência single-writer de versões de uma projeção para uma partição e audiência
de segurança imutáveis.

**Epoch** identifica uma geração contígua de ordenação dentro da mesma identidade e schema-major.
Restore/failover que perde continuidade do contador cria novo epoch. O produtor MUST alocar epochs
globalmente únicos dentro da vida do stream e nunca reciclar um valor anterior; o cliente não
consegue provar essa propriedade guardando uma lista finita de valores opacos. Troca de dimensão
imutável ou schema-major cria outro stream id, não apenas epoch.

**Sequence** é o número estritamente crescente dentro de um epoch. No JSON ele é uma string
decimal de 20 dígitos para não depender do limite numérico do JavaScript. Comparação lexical é
válida apenas para valores no mesmo stream e epoch. O produtor MUST criar novo epoch antes de
esgotar 20 dígitos e MUST NOT fazer wrap.

**Cursor de estado** é o par `(epoch, sequence)`. Ele ordena versões da projeção.

**State token** é um validador opaco e forte do estado semântico instalado naquele cursor. Ele
MUST mudar sempre que o cursor mudar, mesmo quando os bytes de domínio forem iguais. Ele detecta
equivocation, mas não é o ETag HTTP da representação CloudEvents inteira e não prova sozinho o
resultado de um patch.

**State digest** é `sha256-` seguido do SHA-256 em base64url sem padding sobre o estado
canonicalizado por [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785). Diferente do token, é
recomputável pelo consumidor. Toda projeção Continuum, inclusive snapshot-only, MUST restringir
seu estado ao domínio I-JSON/JCS interoperável (inclusive números) e rejeitar JSON com chaves
duplicadas.

**Delivery cursor** é um token opaco de um binding de transporte. O `id` de SSE e
`Last-Event-ID` são delivery cursors; nunca são tratados como cursor de estado.

**Message identity** é o par CloudEvents `(source, id)`. Ele ajuda a deduplicar entrega e
correlacionar logs; não ordena estado.

**Security generation** é a identidade local do contexto autorizado atual: authority,
ambiente, tenant, audience/principal e sessão/revogação. Ela não é enviada como segredo no
evento. Uma troca de geração invalida todo estado protegido da geração anterior.

**Authorization fence** é um contador monotônico local, separado de `lease_revision` e do fence
do produtor. Ele muda antes de tornar observável qualquer nova fronteira de autorização: grant
que ativa uma geração, troca de geração/identidade, expiry detectado, revogação, `reauthorize` ou
`purge`. O valor não concede autoridade nem precisa ir ao wire; ele impede que trabalho assíncrono
iniciado sob uma fronteira anterior publique resultado depois da mudança. Cada fronteira lógica
aceita incrementa o fence uma vez; duplicata/replay validado da mesma transição não incrementa de
novo.

**Rollout generation** é o fence local monotônico da atribuição candidate/baseline. Trocar perfil
ou acionar kill switch incrementa-o antes de cancelar trabalho; todo callback captura o valor e
não pode instalar, cachear nem produzir efeito depois que ele divergir. Ele não é cursor de dados
nem atributo de autorização.

**Repair** é a obtenção autoritativa de um snapshot ou cadeia exata de patches a partir do
estado local declarado.

**Commit receipt** é o registro durável do resultado de um comando. Ele é separado da projeção
e pode carregar fences que indicam onde o efeito já é observável.

### 4.2 Identidade do stream

O servidor MUST resolver `stream.id` para, no mínimo, a tuple abaixo:

```text
(authority, environment, tenant, audience-or-principal,
 projection, normalized-parameters, partition, schema-major)
```

`stream.id` e `stream.partition` são opacos no wire. Eles MUST NOT conter PII, segredo,
credencial ou identificador bruto que não possa aparecer em logs. Conhecer um stream id nunca
concede acesso.

Um produtor MUST NOT reutilizar o mesmo `stream.id` para uma tuple diferente. Mudança de uma
dimensão imutável exige novo stream. Epoch trata somente descontinuidade de ordenação dentro da
mesma tuple. A resolução e autorização são server-side; o cliente não escolhe livremente tenant,
principal ou partição.

### 4.3 Autoridade e corte

Cada stream tem exatamente uma autoridade de sequência por epoch. A versão e a mutação que ela
representa MUST ser persistidas atomicamente, ou derivadas de um log transacional que fornece a
mesma propriedade. A autoridade usa lease/fence durável e monotônico: depois de failover, o
writer antigo não pode confirmar mutação nem publicar outbox, mesmo que continue vivo numa
partição. Rotacionar epoch sem fencing não resolve split-brain e não é conforme.

Rebuild/materialização longa fixa um snapshot MVCC ou offset imutável da fonte e carrega esse
`source_watermark` até o commit. O CAS de publicação cobre `(source_watermark, projection_head,
authority_fence)`; o rebuild não pode ler estado vivo posterior ao watermark nem publicar bytes
da mutação N+1 sob cursor N. Se a fonte avançar fora do corte, o rebuild conflita/reinicia ou
processa o sufixo depois de instalar seu corte.

O mesmo fence protege leitura, não só escrita. Antes de responder snapshot/repair `200` ou `304`,
`ready`, replay ou publicação live, réplica e publisher confirmam que ainda possuem a geração
durável corrente. Réplica velha falha ou redireciona ao origin corrente; nunca valida epoch
anterior como fresh. Todo redirect de binding Continuum — failover, repair ou lease — aceita
somente `307`/`308`, envia `Cache-Control: no-store`, só segue origin allowlisted, permite no
máximo um hop e rejeita loop, repete autorização completa no destino e não encaminha credencial
ambiente entre origins sem escopo explícito. Cache compartilhado só
pode servir a geração anterior dentro do limite de
staleness publicado; deployment que promete corte imediato usa revalidação obrigatória no origin
ou purge comprovado. O piloto usa conditional cache revalidado, não confiança em purge eventual.

Endpoints de emissão/submit/lookup de comando e native `EventSource` não seguem redirect: qualquer
3xx falha a operação/conexão e a próxima tentativa usa somente endpoint local configurado. Isso
evita repetir corpo mutante/credencial e evita prometer inspeção de status/hops que a API nativa
não expõe. Snapshot/repair, fetch-stream e lease só usam a exceção 307/308 allowlisted de um hop
acima.

Uma implementação com atualização em tempo real MUST fechar a corrida snapshot↔subscribe por
uma destas estratégias documentadas:

1. o snapshot retorna `Continuum-Delivery-Cursor` do mesmo corte atômico; a assinatura pede
   eventos estritamente depois desse token e o journal cobre a janela; ou
2. o consumidor assina primeiro e espera um controle `continuum-ready`. Num corte atômico, esse
   controle prova que a assinatura já foi registrada e traz o head completo de cada stream do
   manifesto assinado; tudo posterior ao corte entra no buffer limitado. O consumidor então faz
   fetch autoritativo/revalidado, compara cada snapshot ao head do corte, descarta eventos já
   cobertos e aplica o restante. Snapshot abaixo do head de `ready` nunca conclui bootstrap nem
   fica fresh: inicia repair/replay até cobrir o corte.

`ready` e os checkpoints seguintes fixam um digest do manifesto autorizado e contêm exatamente
uma entrada por stream: omissão, extra, duplicata, manifesto divergente ou subscription id antigo
invalida o controle inteiro. Sem header/checkpoint atômico na primeira estratégia ou esse fence
semântico na segunda, a corrida continua aberta e o binding não é conforme. Apenas registrar a
assinatura antes de um GET cacheável não basta: um cache poderia devolver v10 depois de o head
v11 já existir e nenhum evento posterior acordaria o cliente.

`subscription_manifest_digest` é SHA-256/JCS de
`{"protocol_version":"0.2","stream_ids":[...]}`, com ids autorizados únicos em ordem lexical.
Descritores são imutáveis sob cada stream id e subscription id muda quando a configuração muda.
O servidor rejeita ids repetidos antes de calcular; o cliente fixa o manifesto
solicitado/autorizado e exige igualdade do digest e do conjunto em cada controle. JSON Schema
valida a forma, enquanto unicidade/cobertura é uma regra semântica testada pelos vetores.

Snapshot-first multiplexado só é conforme quando um endpoint de manifesto produz snapshots e um
único delivery cursor vetorial no mesmo **barrier de entrega**, ou quando o servidor autentica e
compõe explicitamente os cursors por stream. Para cada stream, o componente do cursor é registrado
atomicamente com a versão daquele snapshot e o journal cobre toda publicação posterior; isso fecha
no-loss snapshot↔subscribe, mas não afirma que os snapshots de streams distintos compartilham
watermark ou transação causal. O cliente não concatena tokens opacos de respostas independentes.
Sem esse binding, snapshot-first é per-stream e multiplex usa subscribe-first. Se os estados
precisarem de corte semântico atômico entre si, são uma única projeção/stream como em § 10.

"Emitir depois do commit" sem outbox/CDC transacional deixa uma janela de dual write. Nesse caso
o produtor MUST manter conditional fetch/polling como caminho permanente de reconciliação e
MUST NOT alegar entrega confiável pelo stream. O deployment declara
`max_canonical_reconcile_interval_ms` e `max_canonical_reconcile_jitter_ms`. A soma do intervalo
e do jitter efetivamente sorteado nunca pode ultrapassar o hard expiry da representação; o runner
prova o pior caso e o clamp. Timer, wake, bfcache restore e network regain agendam no máximo uma
reconciliação por stream.

## 5. Perfis e capabilities

Capabilities são independentes e negociadas por configuração confiável ou resposta do endpoint;
um evento não pode elevar as próprias capabilities.

| Identificador | Requisito | Uso recomendado |
|---|---|---|
| `continuum.snapshot.v0.2` | snapshot + ETag/conditional GET + repair completo | baseline obrigatório |
| `continuum.invalidate.v0.2` | notificação ordenada que desperta conditional GET | primeiro perfil realtime |
| `continuum.patch.json.v0.2` | RFC 6902 com base/resultado exatos | opcional, somente após medição |
| `continuum.patch.merge.v0.2` | RFC 7396 com base/resultado exatos | opcional, somente após medição |
| `continuum.replay.v0.2` | journal limitado com retention floor explícito | opcional |
| `continuum.command-receipt.v0.2` | comando idempotente + recibo consultável | contrato separado e opcional |

O perfil recomendado para o primeiro piloto é `snapshot + invalidate`, não patch nem replay.

## 6. Envelope CloudEvents

Toda mensagem de dados MUST usar CloudEvents JSON structured content mode e conter:

- `specversion: "1.0"`;
- `id`, único junto de `source` para cada evento distinto; a retenção limita apenas a memória de
  dedupe do consumidor, não a obrigação do produtor;
- `source`, URI estável da autoridade produtora;
- `type`, compatível com o `data.kind`;
- `subject`, identificador opaco do stream ou recibo;
- `time`, apenas para telemetria, nunca para ordenação;
- `datacontenttype: "application/json"`;
- `dataschema`, URI imutável do schema de `data` (não do envelope CloudEvents inteiro);
- `data.protocol_version: "0.2"`.

Os tipos normativos desta versão são:

```text
continuum.projection.snapshot.v0.2
continuum.projection.patch.v0.2
continuum.projection.invalidate.v0.2
continuum.projection.gap.v0.2
continuum.command.receipt.v0.2
```

Bindings MAY transportar atributos de extensão CloudEvents, como `traceparent`. Extensões MUST
seguir nome e tipo escalar definidos pelo CloudEvents, MUST NOT mudar a semântica normativa e
MUST NOT conter PII ou segredos. `traceparent`/`tracestate` passam por parser W3C completo; o
regex do schema é somente um primeiro filtro da versão `00`.

`time`, timestamps de domínio e `generated_at` são observabilidade. Nenhum deles ordena ou
resolve conflito.

## 7. Estruturas comuns

### 7.1 Stream

```json
{
  "id": "s_Q8N2mQwJbWvL",
  "projection": "example.catalog",
  "partition": "p_E7fQ9c",
  "schema": "https://schemas.example.test/catalog/v1",
  "classification": "public"
}
```

`classification` vale `public`, `tenant`, `principal` ou `command`. Ela é um guardrail de
política, não uma decisão de autorização feita pelo cliente.

### 7.2 Versão

```json
{
  "cursor": {"epoch": "e_yQ8x", "sequence": "00000000000000000042"},
  "state_token": "t_6PKR4H2x",
  "state_digest": "sha256-RBNvo1WzZ4oRRq0W9-hknpT7T8If536DEMBg9hyq_4o"
}
```

Para o mesmo stream/epoch, o produtor MUST emitir sequences estritamente crescentes. Duas
combinações diferentes de token/digest no mesmo cursor são **equivocation**. O consumidor MUST
entrar em `reconcile[fatal]`, não escolher uma delas silenciosamente. Snapshot e resultado de
patch MUST ter o digest recomputado antes da instalação.

`state_digest` é exatamente `"sha256-" + base64url_sem_padding(SHA-256(JCS_UTF8(state)))`, em
que `state` é somente o documento de projeção resultante, não o envelope, freshness nem cursor.
No exemplo acima, o digest corresponde ao estado `{}`.
JSON inválido para I-JSON/JCS é rejeitado antes do hash. O mesmo algoritmo vale aos digests em
heads e observation fences. `state_token` é um validador opaco emitido pela autoridade, estável
para o mesmo cursor e nunca reutilizado para outro cursor ou estado; ele não é hash, credencial
nem substituto do digest recomputável. Mesmo quando os bytes de `state` não mudam, um cursor novo
recebe token novo.

### 7.3 Freshness

```json
{
  "fresh_for_ms": 30000,
  "stale_if_error_ms": 120000,
  "age_ms": 250
}
```

Ao receber uma representação canônica HTTP no instante monotônico local `m`, o consumidor calcula:

```text
fresh_remaining = max(0, fresh_for_ms - effective_age_ms)
usable_remaining = max(0, fresh_for_ms + stale_if_error_ms - effective_age_ms)
```

`canonical_validation_age_ms = Continuum-Age-Ms` e
`effective_age_ms = saturating_add(canonical_validation_age_ms, http_age_ms,
elapsed_request_response_parse_ms)`. O header obrigatório mede tempo desde o **último corte de
validação autoritativa** daquela tuple; `http_age_ms` é o `Age` HTTP convertido conservadoramente
para milissegundos (incluindo até 999 ms de arredondamento) e cobre o intervalo posterior. São
intervalos sucessivos e portanto somam. Resposta comprovadamente direta do origin pode omitir
`Age` e usa zero; caminho que atravessa cache/intermediário MUST fornecer `Age` verificável.

No primeiro `200` serializado junto da representação, `Continuum-Age-Ms` repete
`body.freshness.age_ms`. O body/ETag permanece byte-estável, mas um `200` canônico posterior ou
`304` autorizado confirma que a mesma tuple ainda é o head e cria **novo corte de validação**;
nesse caso o header pode voltar a zero/idade pequena sem mudar o body. Um cache RFC 9111 incorpora
os headers do `304` à resposta armazenada e seu `Age` cresce desde esse novo corte. Assim, `304`
renova freshness de verdade sem fingir que a representação acabou de ser criada. Só a resposta da
`repair_generation`/validation generation local corrente pode criar o corte; resposta anterior
atrasada é descartada. Cache hit nunca zera idade por conta própria. Header ausente, cache sem
`Age` verificável ou tuple abaixo de `latest_head` não renova freshness. O deployment limita
duração de request; timeout não valida estado.

Durante execução contínua, deadlines locais usam relógio monotônico. Browser também captura um
wall-clock anchor apenas como limite conservador: em wake/`visibilitychange`/`pageshow`,
`elapsed_conservative = max(monotonic_delta_nonnegative, wall_delta_nonnegative)` e recalcula os
deadlines **antes** de declarar conteúdo público atual. Salto civil para frente pode expirar cedo;
relógio civil regressivo, ausente ou ambíguo nunca estende. Se houve suspensão observável e a
plataforma não prova um monotonic clock sleep-inclusive nem um wall delta não regressivo, o estado
público vai para `stale_blocked` até validação canônica. No hide/freeze ele é no mínimo marcado
`stale_usable`, de modo que bfcache não restaure um selo visual de fresh anterior. `time` do evento
e clock civil recebido do servidor nunca ordenam nem estendem freshness; o wall clock local só
pode encurtar a janela. Target protegido segue o purge pré-suspensão de § 12.4.

Ao fim de `fresh_remaining`, os dados ficam `stale_usable` e repair começa. Ao fim de
`usable_remaining`, ficam `stale_blocked`; a UI não pode apresentá-los como atuais. Dados
protegidos nunca sobrevivem a uma troca de security generation, ainda que a janela de stale não
tenha expirado. Para stream `tenant` ou `principal`, o prazo utilizável é o menor entre hard
expiry dos dados e expiry do auth lease observável. Offline além do lease bloqueia/purga conforme
a política de minimização; nunca mantém conteúdo como autorizado. Heartbeat não renova freshness
nem auth lease.

Somente uma representação HTTP canônica `200` autorizada e atual — snapshot ou cadeia de repair
exata — ou revalidação `304` pode transicionar dados para `fresh`, depois de contabilizar `Age` e
tempo local. Evento/controle de stream pode avançar a versão, mas a deixa no máximo
`stale_usable` até validação canônica. Isso é deliberado: proxy, TCP, fila de tasks ou aba suspensa
podem atrasar um frame sem que native `EventSource` exponha seu dwell time.

### 7.4 Autoridade temporal durável

Prazo que sobrevive a request, processo, worker, host ou restore não usa sozinho o monotonic clock
daquele processo. O registro autoritativo persiste, no mesmo CAS/transação, um
`time_authority_epoch`, o anchor/deadline, um `elapsed_upper_floor` e um `elapsed_lower_floor` não
decrescentes. A autoridade temporal fenced fornece um intervalo conservador
`[elapsed_lower, elapsed_upper]` que inclui o elapsed real e incorpora seu erro máximo documentado.
Freshness, retry, deadline de `accepted` e lease usam
`max(elapsed_upper_floor, elapsed_upper)` — podem expirar cedo, nunca tarde. Retenção mínima/GC usa
`max(elapsed_lower_floor, elapsed_lower)` e só apaga quando essa lower bound alcança
`retain-until` — pode reter mais, nunca menos. Cada decisão persiste os floors atualizados no mesmo
commit. Failover só conserva o epoch se provar continuidade; restore/clock rollback ou salto
fora do bound cria epoch novo e torna anchors anteriores incertos. `issuance_age_ms` e
`Continuum-Lease-Age-Ms` nunca diminuem entre respostas da mesma operação/revision. Freshness é
diferente: um header menor só nasce de novo corte canônico `200`/`304`, depois que a autoridade
fenced prova que a tuple/ETag ainda é o head. Failover sem essa prova não valida nem reseta idade;
com a prova, o novo corte legitimamente reabre a janela como em § 7.3.

Incerteza falha na direção segura e nunca inventa tempo: submit/retry antigo e grant/renew de lease
expiram ou são negados cedo; `accepted` cujo deadline não pode ser provado vira terminal
`indeterminate` atomicamente; receipt terminal e tombstone **não** sofrem GC até uma lower bound
durável provar o `retain-until`. Representação cuja idade não pode ser provada não fica fresh. Uma
nova operação pode começar sob novo epoch depois de autorização/reconciliação, mas não ressuscita
id antigo nem lease anterior. Esses requisitos podem ser implementados por relógio/transaction
time do store autoritativo ou serviço equivalente; wall clock solto de cada host não é conforme.

## 8. Tipos de mensagem

O schema JSON normativo está em
[`message.schema.json`](../../contracts/continuum/v0.2/message.schema.json). Os exemplos abaixo
são resumidos; em conflito, o schema e os requisitos textuais mais estritos prevalecem.

### 8.1 Snapshot

`data.kind` é `snapshot`. A mensagem contém `stream`, `target`, `freshness` e `state`.

Um snapshot instala a representação inteira. Durante bootstrap ou repair ele MAY mudar o epoch.
Um snapshot espontâneo de outro epoch em um stream vivo MUST disparar repair autoritativo, não
ser instalado às cegas. Um repair solicitado com versão mínima MUST NOT responder snapshot mais
antigo no mesmo epoch.

### 8.2 Patch

`data.kind` é `patch`. A mensagem contém `stream`, `base`, `target`, `freshness` e:

```json
{
  "patch": {
    "media_type": "application/json-patch+json",
    "document": [{"op": "replace", "path": "/entities/a/value", "value": 2}]
  }
}
```

O consumidor MUST aplicar o patch somente quando:

1. stream, schema e epoch correspondem exatamente ao estado instalado;
2. `base.cursor`, `base.state_token` e `base.state_digest` correspondem exatamente ao local;
3. `target.sequence` é maior que `base.sequence`;
4. media type e operações foram negociados;
5. tamanho, profundidade, quantidade de operações e paths passam nos limites locais.

A aplicação ocorre sobre uma cópia e é atômica. Falha de parse, validação, operação ou schema
descarta a cópia inteira e inicia repair. Antes da instalação, o consumidor MUST validar o
schema da projeção e recomputar o state digest do resultado. Divergência de `target.state_digest`
é falha de patch e inicia repair sem avançar cursor/token.

RFC 6902 não é idempotente em geral: `add /array/-`, `remove` e `move` são exemplos evidentes.
Duplicatas são descartadas por cursor/token/identidade; nunca são reaplicadas. A capability
baseline permite `add`, `remove`, `replace` e `test`; `move` e `copy` exigem negociação explícita.
`path` e `from` precisam ser JSON Pointers RFC 6901 válidos. Qualquer segmento `__proto__`,
`prototype` ou `constructor` MUST ser rejeitado. A mesma proibição vale recursivamente para
chaves em values, snapshots e Merge Patch, salvo runtime que demonstre representação sem
protótipo. `move`/`copy` também obedecem limite do **resultado**, pois um patch pequeno pode
amplificar o estado.

Em RFC 7396, `null` remove um membro e arrays são substituídos por inteiro. Para atribuir `null`
ou editar array por elemento, o produtor usa JSON Patch ou snapshot; não inventa extensão de
Merge Patch.

Patch MUST NOT atravessar stream, epoch ou schema. Um produtor que não consegue provar base e
resultado exatos envia invalidation ou snapshot.

### 8.3 Invalidation

`data.kind` é `invalidate`. Ela contém `stream`, `head` e `reason`; não contém estado.

Invalidation é um wake-up coalescível. Ela marca dados como potencialmente stale e dispara
conditional fetch/repair. Ela MUST NOT ser tratada como prova de que o cliente observou todas as
versões intermediárias e MUST NOT apagar a representação instalada.

Ordenação de `head` no mesmo epoch:

- menor que cursor local ou que `latest_head`: regressão, descartar;
- igual ao local com token/digest iguais e `data_changed`: nada a buscar, descartar sem renovar
  freshness;
- igual ao local com token/digest iguais e `unknown`: tratar conservadoramente como suspeita não
  resolvida, marcar `stale_usable` (ou `stale_blocked` se o hard expiry venceu) e iniciar uma
  validação condicional canônica; só a resposta HTTP pode encerrar o repair;
- igual ao local com token ou digest diferente: equivocation, `reconcile[fatal]`;
- maior que local: marcar stale, iniciar um repair e coalescer no maior head;
- epoch diferente: não calcular máximo; entrar em reset/repair autoritativo.

`latest_head` guarda a versão completa `(cursor, state_token, state_digest)`, nunca só sequence;
isso permite detectar equivocation durante coalescência e término de repair.

Mudança de política/autorização **não** é ordenada pelo cursor da projeção nem usa invalidation.
Ela chega pelo controle independente `security_generation` do binding. O consumidor processa
esse controle antes de qualquer filtro de regressão de dados; portanto uma mudança de política
atrasada não pode ser descartada por um head de dados maior. Coalescência mantém separadamente
`max_data_head` e a transição de segurança pendente.

### 8.4 Gap

`data.kind` é `gap`. Ela contém `stream`, `head`, `oldest_repairable_base` e `reason`.

Gap declara que a sequência incremental pedida não pode ser entregue com segurança. O consumidor
descarta buffers daquele stream, entra em `reconcile[reset_required]` e busca snapshot sem exigir
o cursor antigo. Razões incluem `retention`, `overflow`, `epoch_changed` e `unknown`.
`stream.schema` é imutável: evolução que muda seu identificador seleciona novo stream por
configuração/negociação confiável, nunca por redirect vindo do corpo. Mudança/revogação de
autorização usa security generation/lease do binding, não um gap de dados.

`oldest_repairable_base` e `overflow` são fatos independentes da ordenação do head. Por epoch, o
consumidor mantém o maior floor conhecido. Se sua base instalada/requisitada é menor que esse
floor, ou se recebeu overflow aplicável, força snapshot/reset mesmo quando `head` é igual a
`latest_head`. Só ignora gap head-regressivo quando o estado instalado já cobre o head **e** o
floor não torna sua base irreparável. Mesmo cursor com token/digest divergente é equivocation.
Head futuro no mesmo epoch ou epoch divergente força reset/repair. Mensagem de outro epoch nunca
é instalada diretamente; somente resposta autoritativa do repair corrente pode trocar o epoch.

Gap explícito não resolve a perda do **último** evento quando o produtor nunca o publicou. Por
isso, implementações sem outbox/CDC mantêm reconciliação periódica canônica.

### 8.5 Commit receipt

`data.kind` é `commit`. O recibo contém:

- `command_id`, opaco, autenticado e emitido pelo servidor para um único escopo/intenção de uso;
- `operation`, nome estável da operação;
- `request_fingerprint`, digest canônico da intenção;
- `status`: `accepted`, `committed`, `adjusted`, `rejected` ou `indeterminate`;
- `receipt_revision`, sequence decimal de 20 dígitos, monotônica por comando;
- `receipt_token`, validador/locator opaco que muda a cada receipt revision;
- `retry_for_ms`, horizonte relativo de idempotência informado pelo servidor;
- `observations`, zero ou mais fences de projeção;
- `result` ou `problem`, conforme o status.

`accepted` significa apenas que o comando foi registrado duravelmente; não é terminal.
`committed`, `adjusted`, `rejected` e `indeterminate` são terminais. `indeterminate` significa que
a autoridade não consegue provar um resultado e exige resolução operacional; ele nunca autoriza
retry automático. `unknown` é estado local do consumidor após resposta perdida e nunca deve ser
inventado como resultado servidor.

Receipts formam um join sem depender da ordem de chegada: `pending < accepted < terminal <
invalid`, e `invalid` é absorvente. O consumidor retém evidência suficiente para validar também
uma revisão menor; ele só deixa de regredir a vista quando essa evidência é compatível. Mesma
revisão/token/conteúdo é duplicata. Mesma revisão divergente, fingerprints diferentes, dois
payloads terminais diferentes, ou `accepted` com revisão maior/igual à de um terminal tornam o
comando `invalid` em qualquer permutação. Somente terminal `committed` ou `adjusted` pode carregar
observation fences. Uma revisão maior MAY repetir um desses terminais apenas para acrescentar ou
avançar fences, mantendo operation, status, fingerprint, `retry_for_ms`, result/problem e efeito
imutáveis. `accepted`, `rejected` e `indeterminate` sempre têm `observations=[]`. Dentro de um
receipt há no máximo um fence por `stream_id`.
Entre revisões, fence novo no mesmo epoch substitui o anterior quando a sequence é maior; sequence
igual exige token e digest iguais; sequence menor é evidência antiga que permanece validável mas
não reduz a vista. Depois de rotação legítima de epoch, uma revisão **maior** do mesmo receipt MAY
publicar fence do novo epoch: o receipt autorizado e ligado ao mesmo comando é a prova canônica de
que o efeito entrou na nova construção, e esse fence substitui epochs de revisões menores para
aquele stream. Epoch já abandonado não pode reaparecer em revisão posterior. Dois fences no mesmo
receipt, conteúdo divergente na mesma receipt revision, ou token/digest divergente na mesma
sequence+epoch tornam o comando `invalid`. Ordenar por `receipt_revision` antes dessas regras faz
revisões compatíveis recebidas ao contrário produzirem o mesmo mapa.

Combinações de payload são fechadas: `accepted` não carrega result/problem; `committed` MAY
carregar result e não carrega problem; `adjusted` carrega result e não problem; `rejected` e
`indeterminate` carregam problem e não result. Prova tardia de provedor depois de
`indeterminate` não reabre nem muda esse terminal e não pode ser escondida num fence; resolução
operacional/compensação produz registro autoritativo separado segundo o domínio.

O escopo de idempotência é, no mínimo:

```text
(authority, environment, tenant, principal, operation, command_id)
```

Cada command ledger tem uma única generation de autoridade com fence durável e store
linearizável. Emissão, primeiro bind id→fingerprint, consumo de precondição, transações de
aceitação/conclusão, lookup e GC comparam esse fence no **mesmo commit** da própria decisão.
Primary antigo ou writer particionado não pode confirmar efeito/receipt depois de takeover;
idempotência no provedor externo não substitui fencing do efeito local. Failover/restore que não
prova continuidade integral do ledger recusa emissão, submit, lookup conclusivo e GC até
reconciliar. IDs anteriores nunca são tratados como novos nem executados; `410` só é usado quando
metadata autenticada prova expiry/non-executability, caso contrário a autoridade falha fechada e
sinaliza indisponibilidade/estado indeterminado para operação.

Para efeito puramente local, mutação autoritativa e receipt terminal são uma transação/CAS. Para
efeito externo, há duas fronteiras: (a) aceitação atomiza precondição, reserva/mutação local
necessária, command ledger, outbox e receipt `accepted`; (b) conclusão atomiza prova durável do
provedor, mutação/compensação local final, estado da outbox e receipt terminal. Elas podem
coincidir só quando o efeito é local. A mesma chave com o mesmo fingerprint reproduz a maior
revisão já durável; fingerprint diferente conflita e não executa. Após resposta perdida, o cliente
consulta o receipt; não infere sucesso de uma atualização SSE.

Quando o request traz precondição forte, a comparação participa do **mesmo** ponto de
serialização/transação/CAS que consome a intenção: a transação terminal local ou a transação de
aceitação externa (a) acima. Checar antes e gravar depois não é conforme. Entre dois comandos
concorrentes sobre a mesma versão, no máximo um pode consumir a precondição. O perdedor não produz
efeito/outbox e registra/reproduz `rejected`, retornando `412` para `If-Match` falso ou `409` para
conflito de domínio. Operação sem precondição só é conforme se a regra de domínio ainda serializa
e valida suas invariantes nessa mesma fronteira atômica; em particular, estoque de uma unidade
nunca pode ser vendido duas vezes por dois workers.

O `command_id` é emitido pelo servidor com issued-at, prazo, nonce e escopo autenticados, de modo
que um id fora do horizonte continue reconhecível como expirado depois do GC de seu tombstone. A
emissão não concede autorização: submit e lookup reautorizam o escopo. Um id puramente escolhido
pelo cliente só é conforme se o servidor mantiver tombstone permanente. O cliente fixa
o deadline local pela resposta de emissão autenticada, que contém `retry_for_ms` imutável e
`issuance_age_ms` calculado desde o issued-at. O restante é
`max(0, retry_for_ms - issuance_age_ms - elapsed_request_response_parse_ms)`; uma repetição do
mesmo nonce devolve o mesmo id, nunca reduz `issuance_age_ms` e não pode produzir deadline mais
tarde que qualquer resposta válida anterior. Assim, perder a primeira resposta e repetir a
emissão não reinicia o horizonte. `retry_for_ms` de todo receipt precisa ser o mesmo horizonte;
receipt duplicado, replayado ou consultado também **não** move a âncora. O servidor decide
expiração pelo issued-at/prazo autenticados, não pelo relógio cliente, e mantém
receipt/tombstone no horizonte anunciado e, depois dele, retorna `410` para o id autenticado
expirado em vez de executá-lo como novo. Clock do cliente nunca estende esse horizonte.

O horizonte governa novo submit/retry, não apaga trabalho já `accepted`. Depois de `accepted`, o
cliente só faz lookup; o ledger e o receipt permanecem consultáveis até um terminal, mesmo se o
horizonte original atravessar. Só depois do terminal a política publicada de retenção pode fazer
lookup retornar `410`, mantendo evidência/tombstone suficiente para que submit jamais execute o
mesmo id de novo.

`max_receipt_retention_ms` ancora na criação durável da **primeira revisão terminal**, não na
emissão nem em `accepted`. O receipt completo permanece consultável até
`max(issued_at + retry_for_ms, first_terminal_at + max_receipt_retention_ms)`; antes do terminal o
ledger `accepted` fica fora desse contador e segue a deadline terminal abaixo. Revisão terminal
posterior que apenas avança observation fences não reinicia retenção. Depois do GC, o id
autenticado ainda é reconhecido como expirado por tombstone/metadata e retorna `410`, nunca volta a
ser executável.

`accepted` MUST chegar a um receipt terminal, inclusive `indeterminate`, dentro do
`max_accepted_terminal_ms` publicado e medido monotonicamente desde a primeira transição para
`accepted`; enquanto não chegar, o ledger durable permanece consultável. Expirar silenciosamente
um `accepted` ou apagar sua evidência não é conforme. O worker propaga a mesma idempotency key ao
provedor; nenhuma das duas fronteiras promete transação distribuída. `committed` exige prova
durável do resultado do provedor e só nasce na transação de conclusão (b). Resposta perdida sem
prova suficiente termina
`indeterminate`, que explicitamente não afirma se o efeito externo ocorreu.

O servidor, não o cliente, calcula `request_fingerprint` como SHA-256/JCS de uma estrutura
versionada exatamente como
`{fingerprint_version:"continuum-command-v0.2", operation, precondition, request}`, incluindo a
intenção normalizada completa e `null` quando não há precondição. O wire usa `sha256-` + base64url
sem padding. Um digest enviado pelo cliente MAY ser comparado, mas nunca é a única evidência de
igualdade de requests.

Todo valor que entra nessa estrutura passa antes pelo schema da operação e pelo domínio
I-JSON/JCS. Números precisam ser finitos e interoperáveis como IEEE-754 binary64; inteiro que
precise de precisão além de `[-9007199254740991, 9007199254740991]`, decimal monetário exato ou
outro valor fora desse domínio usa string/unidade normalizada definida pelo schema. O servidor
rejeita duplicate keys e valor não interoperável, produz uma única intenção normalizada, calcula o
fingerprint dela e usa **esse mesmo objeto** no efeito/outbox; default/coerção posterior ao hash
não é conforme. Workers heterogêneos não podem escolher parsers/rounding diferentes.

Um fence em `observations` afirma que a construção causal da read model indicada já incluiu o
efeito deste comando e alcançou aquele cursor; mera comparação numérica de um cursor sem essa
proveniência não prova read-your-writes. Um commit sem fence não promete observação imediata.
Comandos concorrentes que dependem de uma versão observada MUST usar ETag forte/`If-Match` ou CAS
equivalente no request; a validação atômica segue a regra acima. Falhas usam `409` ou `412` e
Problem Details.

Um fence é satisfeito somente no mesmo stream e epoch: sequence local maior o cobre; sequence
igual exige token e digest iguais; local menor dispara repair usando o fence como versão mínima;
igual com token/digest divergente é equivocation. Epoch local diferente é incomparável: o cliente
consulta o receipt e só um fence do novo epoch em revisão maior pode satisfazer a observação;
nunca compara epochs numericamente nem inventa prova fora do receipt. Fences de streams distintos
são satisfeitos independentemente e não formam bundle/transação atômica.

### 8.6 Heartbeat

Heartbeat é controle do binding, não CloudEvent de estado. Em SSE SHOULD ser comentário. Ele
mantém intermediários/conexões ativos, mas não altera cursor, state token, state digest, freshness ou
autorização.

## 9. Máquina de estados do consumidor

O consumidor mantém eixos independentes, nunca um enum único:

```text
data:     absent | fresh | stale_usable | stale_blocked | invalid
transport: idle | connecting | live | backoff | closed
reconcile: idle | repairing | reset_required | fatal
command:  command_id -> pending | accepted | committed | adjusted | rejected | indeterminate | unknown | invalid
security: not_applicable | generation-id + authorization-fence + lease-deadline
```

Assim, `stale_usable + transport[live] + reconcile[repairing] + command[pending]` é um estado
normal. Um snapshot HTTP não torna transporte SSE `live`, e uma reconexão SSE não conclui repair
HTTP. Uma falha de transporte não apaga a projeção utilizável. Uma falha de autorização ou troca
de security generation, porém, MUST cancelar streams e repairs, zerar buffers e purgar
imediatamente todo estado protegido, inclusive SSR reutilizável e persistência local.

Invariantes cross-axis são fechados: `absent` não tem tuple/ETag/state; `fresh` cobre
`latest_head` e, quando protegido, lease vigente; `invalid` implica `reconcile[fatal]` e fonte ofensiva em
quarentena; `reset_required` não conserva buffer incremental aplicável; purge protegido implica
`absent` e nenhum transporte ativo (`idle` quando não havia conexão, `closed` quando ela foi
cancelada); receipt terminal compatível nunca regride. Tentativa de violação é rejeitada
atomicamente e incrementa `illegal_state_transition`.

Toda operação assíncrona que consome dado, receipt ou efeito de target protegido captura ao
iniciar o par exato `(security_generation_id, authorization_fence)`. Imediatamente antes de
parse/materialização e novamente imediatamente antes de qualquer instalação ou efeito local, o
consumidor compara os dois valores com os atuais e confirma pelo elapsed conservador abaixo que a
lease continua vigente. Falha em qualquer gate descarta a
resposta antes daquele estágio. Resposta de
fetch, repair, replay, receipt ou evento enfileirado da geração/fence anterior nunca instala nem
produz efeito, mesmo que o request já não possa ser cancelado ou a mudança ocorra durante o parse.
Resposta canônica do próprio endpoint de lease é a exceção necessária: ela segue o transition
gate de § 12.6 e não exige a lease que está criando.
Target público não inventa auth lease: callbacks continuam cercados por `repair_generation`,
`transport_generation`, schema e rollout generation aplicáveis.

Aqui, o elapsed da lease MUST incluir suspensão. Todo target protegido usa um clock monotônico
sleep-inclusive comprovado ou captura também wall anchor e calcula
`max(monotonic_delta_nonnegative, wall_delta_nonnegative)`, com wall clock apenas encurtando.
Wake/resume passa por esse gate antes de parse, efeito ou paint protegido. Clock ausente,
regressivo/ambíguo depois de possível suspensão invalida a lease, incrementa o fence e purga; um
runtime que pode retomar trabalho sem clock/sinal e sem gate anterior é NO-GO para
`protected-data`. Browser ainda obedece à regra mais forte de purge pré-suspensão de § 12.4.

### 9.1 Algoritmo normativo de instalação

Para cada mensagem de projeção (`snapshot`, `patch`, `invalidate` ou `gap`), na ordem:

1. imediatamente antes do parse/materialização, confirmar as gerações de callback aplicáveis;
   para target protegido, isso inclui o par capturado
   `(security_generation_id, authorization_fence)` e a lease vigente;
2. validar limites de bytes/profundidade antes de materializar estruturas grandes;
3. validar envelope, schema, kind, capability e binding; a decisão real de autorização já deve
   ter sido feita no servidor;
4. confirmar `source`, `subject` e todos os descritores do stream (`id`, projection, partition,
   schema e classification) contra configuração/estado fixado; o corpo nunca reclassifica cache
   ou autorização;
5. comparar cursor/token/digest;
6. aplicar em cópia, validar o resultado e recomputar o digest;
7. imediatamente antes da troca, repetir as gerações aplicáveis e, para target protegido, a
   validação exata de security generation, authorization fence e lease. Essa validação final e a
   troca da referência formam uma seção atômica/serializada contra incrementos dos respectivos
   fences, sem janela entre check e instalação;
8. atualizar freshness conforme o binding (stream nunca a melhora) e emitir telemetria sem payload.

Regras de cursor no mesmo epoch:

- target igual ao local + token e digest iguais por stream ou resposta não canônica: duplicata,
  descartar sem renovar freshness;
- o mesmo tuple em um `200` HTTP canônico, autorizado e atual é revalidação explícita: o cliente
  valida novamente body/digest e todos os headers de § 12.1, preserva a representação instalada e
  recalcula deadlines como faria para `304`; não conta como instalação nem como duplicata de
  stream;
- target igual ao local + token ou digest diferente: equivocation; atomicamente mudar dados para
  `invalid`, `reconcile[fatal]`, fechar/quarentenar o transporte ofensivo e exigir recuperação
  operacional por configuração confiável. A UI nunca apresenta esse estado como atual;
- target anterior ao local: regressão, descartar e contar;
- patch com base exatamente local: aplicar atomicamente;
- patch com base posterior ao local: gap, iniciar repair;
- patch com base anterior e target posterior: fork/inconsistência, iniciar repair;
- snapshot posterior recebido por binding autorizado: instalar;
- snapshot anterior ao mínimo pedido: rejeitar e marcar produtor inválido.

Para o `stream.id` já fixado, divergência de `source`, `subject` (que em mensagem de projeção
MUST ser `stream/<stream.id>`), projection, partition, classification ou de qualquer dimensão imutável resolvida
no registry é `stream_identity_violation`: rejeição atômica, `data[invalid]`,
`reconcile[fatal]`, fechamento/quarentena da fonte e preservação apenas forense dos bytes locais,
nunca reclassificação. `stream.schema` divergente é a exceção deliberada: continua sendo
incompatibilidade de negociação, não dado a instalar, e leva a repair/renegociação por
configuração confiável como em § 14. Uma mensagem para outro stream autorizado do mesmo
manifesto é roteada ao reducer dele; stream não manifestado não pode criar estado.
Em command receipt, `subject` MUST ser `command/<command_id>`.

Mensagens desconhecidas não podem alterar estado. Um kind requerido mas não suportado torna a
negociação incompatível; uma extensão opcional desconhecida pode ser ignorada.

`invalid + fatal` é terminal para a `recovery_generation` local: nenhuma mensagem, repair ou
snapshot in-band o limpa. Recuperação exige reload/reset iniciado fora do canal ofensivo, nova
`recovery_generation`, purge para `absent`, nova autorização/negociação e snapshot canônico.
Continuum 0.2 não padroniza esse gesto operacional e portanto não promete auto-healing de
equivocation.

### 9.2 Repair e concorrência

Há no máximo um repair ativo por stream. Novas invalidations são coalescidas no maior head.
Patches recebidos durante repair entram em buffer limitado. No modo subscribe-first, overflow
invalida o barrier `ready`: o cliente fecha a assinatura e recomeça com novo `ready`+heads, ou
muda para snapshot-first com delivery cursor atômico. Simplesmente esvaziar o buffer e fazer outro
GET na mesma assinatura reabre a corrida. Nos demais modos, overflow descarta o buffer e força
snapshot completo pelo corte documentado.

Cada stream mantém um `repair_generation` local monotônico. Iniciar ou cancelar repair, instalar
novo epoch, trocar schema ou, no target protegido, trocar security generation incrementa esse
contador. Request e callback sempre capturam `repair_generation` e, quando aplicável,
`rollout_generation`; em target protegido capturam também `security_generation_id` e
`authorization_fence`. Resposta que
não corresponde às gerações aplicáveis, ou cuja lease protegida expirou, é descartada nos gates
imediatamente anteriores a parse e instalação.
Assim, um repair atrasado de A não desfaz um snapshot mais novo de B. O cliente MAY manter um
cache limitado de epochs vistos para diagnóstico/dedupe, mas não fundamenta segurança nele:
unicidade e não reciclagem são invariantes do produtor, e troca de epoch só ocorre pela resposta
autoritativa do repair cuja geração ainda é corrente.

Uma resposta de repair é uma destas opções:

- snapshot autoritativo;
- cadeia ordenada e contígua de patches cuja primeira base é exatamente a versão declarada pelo
  consumidor;
- `304`/equivalente `validated_not_modified` se cursor, token e digest continuam atuais;
- reset/gap quando cursor, epoch, schema ou retenção não permitem delta;
- Problem Details em falha.

Depois de instalar a resposta, o consumidor drena o buffer: descarta mensagens de epoch diferente
e target menor/igual ao instalado; indexa patches por base exata `(cursor, token, digest)`; aplica
somente um caminho link-contiguous. Antes de detectar fork, colapsa cópias semanticamente idênticas
pelo SHA-256/JCS de `data` completo; novo CloudEvents `id`, `time` e extensões de replay não criam
outro candidato. Base ausente, limite excedido ou dois candidatos **semanticamente distintos**
para a mesma base força snapshot/reset. Repair termina apenas quando o estado instalado cobre
`latest_head`; caso contrário, o mesmo stream continua com um único repair ativo.

O endpoint de repair é obtido de configuração confiável do binding. Mensagens MUST NOT fornecer
URL arbitrária de repair. Se links forem usados, são relativos/same-origin e resolvidos em
allowlist.

Retries usam exponential backoff com jitter, orçamento e limite. Ao esgotar a janela de stale,
o dado muda para `stale_blocked`; o retry pode continuar sem fingir atualidade.

`validated_not_modified` não é duplicata de mensagem. Depois de autorização e validação dos
headers do binding, ele renova os deadlines monotônicos a partir da freshness recebida e da idade
efetiva, sem alterar estado ou cursor, **somente** quando o estado cobre `latest_head`/`Min-*`.
Uma resposta atrasada ou sem metadados completos não renova o prazo e é tratada como falha de
repair.

## 10. Ordenação, replay e compactação

- Ordenação só existe por stream/epoch/sequence.
- Não existe ordem global entre streams.
- Saltos de sequence não implicam gap por si: o produtor pode não materializar toda mutação.
  Um patch revela gap pela base; invalidation sempre refaz fetch.
- `source + id` deduplica mensagem, mas não substitui cursor. O consumidor guarda hash JCS
  limitado do envelope/data pelo horizonte de dedupe: repetição semanticamente idêntica é
  duplicata; o mesmo par com conteúdo divergente é colisão/equivocation, fecha e põe a fonte em
  `invalid + fatal` antes de qualquer descarte por cursor.
- Delivery cursor é opaco, limitado em tamanho, autenticado/vinculado no servidor e nunca
  seleciona tenant ou canal sem nova autorização.
- Replay de transporte usa delivery resume token opaco, que MAY representar server-side um vetor
  de posições quando a conexão multiplexa streams. `oldest_repairable_base` no kind `gap` é,
  por outro lado, um cursor semântico daquele stream. Os dois espaços nunca são comparados.
  Pedido anterior ao floor resulta em gap/reset, não em cadeia truncada silenciosa.
- `oldest_repairable_base` é inclusivo: base igual ao floor ainda é reparável; base menor exige
  snapshot. Prunar histórico anterior apenas eleva o floor e não muda epoch. Novo epoch é exigido
  quando se perde continuidade/autoridade do head, não por compactação normal.
- Evento de replay é re-envelopado com novo CloudEvents `id` e extensões
  `continuumreplayed: true`, `continuumoriginalid` e `continuumage` (idade mínima em ms,
  saturada no máximo int32), preservando `data` com igualdade JCS. O produtor nunca muda contexto sob o
  mesmo `(source, id)`. Replay
  pode avançar estado, mas não renovar freshness. O controle autenticado
  `continuum-caught-up`, com head corrente, prova posição e acorda validação HTTP; ele próprio
  nunca torna o estado fresh. Queda antes do checkpoint mantém estado stale e ativa reconciliação
  canônica.
- Todo resume/reconnect envia `continuum-caught-up`, inclusive quando o replay contém zero eventos.
  Isso cobre a queda depois de o user agent aceitar um SSE `id:` mas antes de o reducer instalar o
  evento: head futuro no checkpoint inicia repair.
- Failover só mantém epoch se houver autoridade única, contador e fence duráveis. Caso contrário
  cria novo epoch sob novo fence e força snapshot; o writer antigo permanece incapaz de commit ou
  publicação.

Continuum 0.2 não define `depends_on` nem bundle cross-stream. Se duas partes precisam de corte
exato, o produtor MUST modelá-las como uma única projeção/stream. Revisões mínimas de streams
independentes não provam snapshot causal coerente. Bundle atômico fica fora da 0.2 até ter wire,
algoritmo e vetores próprios.

## 11. Backpressure e limites

SSE não oferece ACK de aplicação nem flow control por mensagem. Portanto:

- produtor e proxy MUST impor limites por principal/tenant/IP para conexões, streams e taxa;
- cada conexão MUST ter limites de fila, bytes, evento, patch, operações, profundidade, replay e
  tempo;
- `max_resident_bytes` agrega todos os streams e inclui estado instalado, cópia de patch, input
  bruto e parsed, buffers, índice de dedupe e controles; limites individuais não bastam;
- a contabilização reserva bytes antes de ler/alocar e considera simultaneamente wire parcial,
  string decodificada, árvore parsed, estado anterior, resultado candidato e cópias entre worker
  e main thread. Abort/reset libera a reserva; abrir nova subscription/security generation não
  zera quotas agregadas por processo, tenant ou principal;
- invalidations MAY ser coalescidas mantendo o maior head;
- patches só podem ser coalescidos se o resultado for uma nova cadeia exata comprovada;
- overflow MUST virar gap/reset ou desconexão seguida de repair, nunca buffer ilimitado;
- consumidores lentos MUST ser desconectados antes de pressionar memória global;
- reconnect usa backoff e jitter; native `EventSource` respeita `retry:` dentro de limites locais,
  enquanto fetch-stream/WebSocket ou outro cliente que observa status também respeita
  `Retry-After`;
- uma pane não pode iniciar repairs concorrentes ou reconnection storm.

Os valores concretos são configuração obrigatória do deployment e aparecem no `limits` fechado de
cada conformance unit. "Sem limite", chave desconhecida ou limite declarado sem vetor de fronteira
aplicável não é conforme. Estágio, escopo e ponto de reset são normativos:

Contagem é determinística: bytes são octetos; cada valor JSON (objeto, array ou escalar), inclusive
a raiz, vale um node; nomes de membros não são nodes, mas seus octetos contam nos limites de bytes
e memória; profundidade da raiz é 1 e cada valor filho soma 1. Operações de JSON Patch são os
elementos do array. `max_result_bytes` mede o UTF-8 da serialização JCS completa. A razão de
descompressão usa `ceil(decoded_bytes × 1000 / compressed_bytes)`; corpo comprimido vazio só pode
decodificar vazio, e qualquer saída dele é erro. Tempo de descompressão é elapsed monotônico gasto
entre a primeira entrada oferecida ao decoder e término/abort, excluindo espera de rede mas
incluindo yields/cópias do próprio pipeline. Empate no limite é aceito; o primeiro incremento além
dele é rejeitado antes de alocação proporcional ou instalação.

| Chave | O que mede | Escopo e reset |
|---|---|---|
| `max_request_head_bytes` | request-target/pseudoheaders e seção de headers decodificada, nomes+valores+separadores | por request, antes de auth/lookup; reset ao rejeitar/terminar |
| `max_request_body_bytes` | octetos do body HTTP de entrada, sempre identity neste binding | por POST de lease/command; conta incrementalmente antes de parse |
| `max_request_identifier_bytes` | UTF-8 de cada nonce, id, cursor, ETag ou selector não confiável | por valor, antes de decode, auth contextual ou lookup |
| `max_response_head_bytes` | status/pseudoheaders e seção de headers decodificada, nomes+valores+separadores, inclusive resposta sem body | por resposta antes de cache/app; reset ao rejeitar/terminar |
| `max_compressed_response_bytes` | octetos de uma resposta HTTP finita antes de content decoding | por snapshot/repair/receipt; reset ao terminar/rejeitar a resposta |
| `max_decoded_response_bytes` | octetos da mesma resposta depois de content decoding | por resposta HTTP finita; reset ao terminar/rejeitar |
| `max_sse_line_bytes` | octetos UTF-8 decodificados de uma linha SSE, sem terminador | por linha; reset no terminador |
| `max_sse_event_data_bytes` | soma de todas as linhas `data:` e newlines inseridos de um evento | por evento; reset somente na linha vazia que o despacha |
| `max_json_nodes` | todo valor JSON materializado: raiz, valor de membro de objeto, elemento de array ou escalar | por documento/evento JSON; reset ao rejeitar/terminar parse |
| `max_json_depth` | profundidade estrutural JSON | por documento/evento |
| `max_patch_ops` | operações de um JSON Patch RFC 6902 | por patch; Merge Patch usa nodes/depth/result |
| `max_result_bytes` | bytes JCS do estado candidato completo | por instalação candidata; reset após troca/rejeição |
| `max_resident_bytes` | wire, decoded, parsed, estado, candidato, buffers, dedupe e cópias simultâneas | agregado pelo runtime + tenant/principal; não zera em reconnect, epoch ou security generation |
| `max_decompression_ratio_milli` | `decoded/compressed × 1000` | por resposta HTTP finita |
| `max_decompression_ms` | tempo monotônico em content decoding | por resposta HTTP finita |
| `max_queue_events` / `max_queue_bytes` | eventos/bytes ainda não reduzidos | por subscription generation; libera só ao reduzir/descartar/encerrar |
| `max_dedupe_entries` | identidades `(source,id)` retidas | por stream + security generation; eviction não enfraquece tuple/token/digest |
| `max_events_per_subscription_generation` / `max_bytes_per_subscription_generation` | entrega cumulativa da geração | não zera em reconnect; nova geração exige barrier e reconciliação canônica |
| `max_subscription_generation_ms` | vida monotônica acumulada da geração | não zera em reconnect; expira em nova geração |
| `max_streams_per_connection` | streams autorizados multiplexados | por conexão; reset no teardown |
| `max_connections_per_principal` / `max_connections_per_tenant` / `max_connections_per_ip` | conexões simultâneas | contadores server-side concorrentes; decrementam no fechamento comprovado |
| `max_active_subscription_lineages_per_context` | linhagens protegidas concedidas, conectadas ou dormentes | agregado por contexto autorizado completo; decrementa em expiry/revogação, não no mero disconnect |
| `max_lease_operations_per_minute` | tentativas autenticadas de grant/renew, inclusive retry idempotente | janela móvel server-side de 60 s por principal + tenant + IP; generation/op id novo não zera |
| `max_events_per_second` | eventos aceitos/publicados | janela móvel de 1 s por principal + tenant + IP |
| `max_reconnects_per_minute` | tentativas de conexão/reconnect, inclusive nova subscription generation | janela móvel server-side de 60 s por principal + tenant + IP; trocar subscription/security generation não zera |
| `max_backoff_ms` | atraso local máximo entre tentativas | por tentativa, preservado na subscription generation |
| `max_repair_attempts` / `max_retry_ms` | tentativas e tempo monotônico total de repair | por `repair_generation`; cancel/restart cria geração nova, nunca concorrente |
| `max_canonical_reconcile_interval_ms` | intervalo-base sem fetch canônico | por stream; reset só por validação HTTP canônica bem-sucedida |
| `max_canonical_reconcile_jitter_ms` | jitter positivo máximo somado ao intervalo-base | por agendamento; intervalo + jitter sorteado sofre clamp para terminar antes do hard expiry da representação |
| `max_replay_events` / `max_replay_bytes` / `max_replay_ms` | sufixo de replay servido | por request; exceder qualquer eixo retorna reset/gap, não prefixo truncado |
| `max_pending_commands` | comandos não terminais | por principal + tenant; decrementa só em terminal/expiry normativo |
| `max_command_operations_per_minute` | emissão, submit/retry e lookup de command/receipt, inclusive repetição idempotente | janela móvel server-side de 60 s, aplicada independentemente por principal, tenant e IP; trocar nonce/id/operation não zera |
| `max_command_retry_ms` | horizonte imutável de retry | por command id, desde emissão original |
| `max_accepted_terminal_ms` | tempo monotônico de `accepted` até terminal, inclusive `indeterminate` | por command id; não reinicia em lookup, retry, worker restart ou takeover |
| `max_receipt_retention_ms` | retenção consultável mínima depois do terminal | por command id; ancora na primeira revisão terminal e não reinicia; expiry efetivo é o maior entre essa janela e o retry deadline original |
| `max_lease_ms` | duração concedida de uma revision de lease | por revision; retry desconta age e nunca reinicia prazo |
| `max_revocation_sla_ms` | tempo até fechar transporte e purgar | por transição de revogação, medido monotonicamente |

O manifest só é válido quando cada fronteira N pode ser alcançada sem outra quota rejeitá-la
antes. Além da execução dos probes, o validator impõe as condições necessárias abaixo:

- `max_result_bytes`, `max_compressed_response_bytes` e `max_decoded_response_bytes` não excedem
  `max_resident_bytes`;
- `max_request_head_bytes`, `max_response_head_bytes` e, quando aplicável,
  `max_request_body_bytes` não excedem
  `max_resident_bytes`; `max_request_identifier_bytes <= max_request_head_bytes`; a feasibility
  probe ainda contabiliza head/body simultaneamente;
- `max_json_depth <= max_json_nodes <= max_decoded_response_bytes`; em unit JSON Patch,
  `max_patch_ops <= max_json_nodes`;
- `max_sse_line_bytes <= max_sse_event_data_bytes <= max_queue_bytes`, e evento/fila não excedem
  `max_resident_bytes` nem `max_bytes_per_subscription_generation`;
- `max_queue_events <= max_events_per_subscription_generation`,
  `max_events_per_second <= max_events_per_subscription_generation`,
  `max_queue_bytes >= max_queue_events` e
  `max_bytes_per_subscription_generation >= max_events_per_subscription_generation`, pois até o
  menor evento ocupa ao menos um octeto;
- em replay, `max_replay_events <= max_events_per_subscription_generation`,
  `max_replay_bytes <= max_bytes_per_subscription_generation` e
  `max_replay_bytes >= max_replay_events`;
- não há ordenação estática entre retry, deadline de `accepted` e retenção terminal: são janelas
  com âncoras distintas; o algoritmo de § 8.5 toma o maior entre retry deadline e retenção
  terminal;
- `max_lease_ms <= max_revocation_sla_ms`, para que perda do frame de revogação ainda purgue pelo
  expiry dentro do SLA;
- os máximos estruturais reservam espaço para N+1 continuar sintaticamente válido:
  `max_patch_ops <= 9999`, `max_streams_per_connection <= 1023` e
  `max_lease_ms,max_command_retry_ms <= 2147483646`; todo outro limite é no máximo
  9007199254740990, e intervalo + jitter de reconciliação não excedem o máximo I-JSON
  9007199254740991.

Essas desigualdades são apenas condições necessárias. O probe N ainda precisa demonstrar no
adapter real que overhead de envelope, buffers simultâneos e estado previamente instalado cabem
em `max_resident_bytes`; manifest com fronteira inexequível falha, mesmo quando satisfaz as
relações estáticas.

Os limites obrigatórios são derivados de capability/profile/layer pelo validator. Units de dados
declaram o grupo de parse/repair; `sse` acrescenta todos os limites realtime, inclusive intervalo
e jitter de reconciliação; JSON Patch, replay, command e `protected-data` acrescentam seus grupos.
O set é exato: omitir ou acrescentar uma chave fora do escopo falha.

Native `EventSource` só entrega `event.data` depois que o user agent já materializou a string.
Portanto produtor e BFF/proxy MUST cortar evento/linha acima do limite **antes** do browser.
Quando enforcement incremental no cliente for requisito, o binding usa fetch-stream com parser
limitado; um check após `JSON.parse` não conta como proteção de wire.

`Content-Length` limita apenas bytes codificados e não protege contra compressão expansiva.
Respostas HTTP finitas contam incrementalmente bytes compressed/decoded, razão e tempo, reservam
memória antes de materializar e cancelam ao primeiro limite. Como uma resposta streaming é
indefinida e content coding pode atravessar fronteiras de evento, o binding SSE/fetch-stream 0.2
MUST chegar ao parser com `Content-Encoding: identity`; proxy pode descomprimir antes, mas aplica
os quatro limites da resposta finita no trecho upstream. No stream identity, linha e evento usam
os dois limites SSE acima. Dividir um evento em várias linhas nunca reinicia a quota do evento.

Requests Continuum são limitados antes de trabalho proporcional. Ingress/proxy aplica
`max_request_head_bytes` também à request-target e à seção decodificada de HTTP/2/3, além de seu
limite transport-native de header compression table/list. O binding 0.2 rejeita request body com
`Content-Encoding` diferente de `identity` (`415`) antes de descomprimir; proxy não pode inflar e
entregar silenciosamente ao app. POST conta `max_request_body_bytes` incrementalmente e reserva
memória antes de parse. `max_json_nodes`/`max_json_depth` também valem ao body. Cada valor opaco
controlado pelo cliente — cursor, ETag, command/subscription/generation/operation id e nonce — é
rejeitado acima de `max_request_identifier_bytes` antes de decode, lookup ou alocação. Exceder
body, request-target ou headers retorna respectivamente `413`, `414` ou `431`; id acima do limite
usa o status da camada que o carregou, sempre `private, no-store`, sem existência observável nem
estado parcial.

Na resposta, origin/proxy aplica `max_response_head_bytes` à seção decodificada **antes** de cache,
service worker ou adapter materializar headers; configura também os limites transport-native de
HPACK/QPACK. Isso cobre `304`, `204` e erro sem body. Excesso aborta a resposta/conexão como falha
de binding, não instala estado nem renova freshness/lease; o cliente não tenta interpretar prefixo
de header truncado. Header opaco individual continua contido simultaneamente por esse teto e, se
ecoou selector do request, por `max_request_identifier_bytes`.

A fila interna de native `EventSource` também não oferece backpressure à aplicação. Esse binding
fica restrito a invalidations coalescíveis e de baixa taxa: públicas em origin cookieless ou
protegidas somente com o canal canônico de lease/security generation de § 12.6. Em ambos os casos
há orçamento server-side cumulativo por subscription generation para eventos, bytes e vida;
reconectar não zera o orçamento. No profile público cookieless, a geração server-side é carregada
por um delivery cursor opaco em `Last-Event-ID`; recriar o objeto sem esse cursor não continua nem
zera a geração anterior e ainda consome as quotas agregadas de conexão/reconnect por audience e
IP. Ao atingir qualquer orçamento cumulativo, o servidor fecha e responde `204` às reconexões
daquela geração. O runtime marca native SSE como terminalmente desabilitado até a próxima
navegação top-level, não constrói outro `EventSource` para contornar o `204` e mantém correção por
fetch canônico/polling limitado; uma validação HTTP isolada não reabre o transporte. A nova página
precisa obter bootstrap/snapshot canônico antes de iniciar uma geração nova, e limites agregados
server-side continuam valendo entre páginas. Page freeze encerra a assinatura quando observável.
Patch, replay
volumoso ou stream de alta taxa exige fetch-stream/WebSocket com leitura cancelável. `204` só é
usado quando não se deseja reconexão automática; overflow recuperável fecha de modo que o cliente
reconecte com backoff e novo barrier.

## 12. Bindings

### 12.1 HTTP snapshot/repair

- `GET` de snapshot retorna `Content-Type: application/cloudevents+json`, CloudEvent `snapshot` e
  ETag forte da **representação HTTP selecionada**. ETag e `state_token` são validadores
  distintos; repair que retorna cadeia usa o tipo batch descrito abaixo;
- o CloudEvent de um snapshot/cursor MUST ser byte-estável (`id`, `time` e freshness no body
  não são regenerados por request); caches atualizam idade no header `Age`, não no JSON;
- respostas `200` e `304` incluem `ETag`, `Continuum-Stream`, `Continuum-Epoch`,
  `Continuum-Sequence`, `Continuum-State-Token`, `Continuum-State-Digest`,
  `Continuum-Fresh-For-Ms`, `Continuum-Stale-If-Error-Ms`, `Continuum-Age-Ms` e, quando a
  estratégia de corte exigir, `Continuum-Delivery-Cursor`; também repetem `Cache-Control` e
  `Vary`, inclusive no `304`, e o `Age` HTTP participa da idade efetiva;
- `If-None-Match` pode retornar `304` somente se a representação e sua tuple
  stream/cursor/token/digest continuam as mesmas. Autorização ocorre **antes** de cache lookup e
  do `304`;
- cursor novo sempre produz state token e representação/ETag novos, ainda que o JSON de domínio
  seja idêntico;
- um `304` válido renova freshness como `validated_not_modified`; ele não conta como mensagem
  duplicada nem como instalação;
- `If-Match` usa comparação forte para precondição de comando.
- Repair usa `GET` no endpoint configurado. Quando existe estado local, envia
  `Continuum-Known-Epoch`, `Continuum-Known-Sequence`, `Continuum-Known-State-Token`,
  `Continuum-Known-State-Digest`, a versão completa de `latest_head` nos headers
  `Continuum-Min-Epoch`, `Continuum-Min-Sequence`, `Continuum-Min-State-Token` e
  `Continuum-Min-State-Digest`, `Continuum-Repair-Id` e, quando disponível, `If-None-Match` do ETag
  da representação instalada. Headers `Min-*` são omitidos quando não existe head pendente. Eles
  são independentes de `Known-*`: num bootstrap sem estado, um head recebido em `ready` envia
  `Min-*` completo enquanto omite `Known-*`. A resposta MUST cobrir essa versão mínima, declarar
  reset/epoch novo ou responder falha/retry;
  réplica atrasada não pode mascarar o lag.
- Depois de patch, ETag antigo não representa o cursor atual e é omitido até novo snapshot/200.
  Resposta ecoa `Continuum-Repair-Id`; cliente aceita apenas a geração de repair/security ainda
  ativa. Sem estado local, os headers `Known-*` são omitidos e o servidor responde snapshot
  completo. `304` só é válido quando o estado instalado também cobre `Min-*`; `304` ou `200`
  abaixo de `latest_head` mantém dados stale, não renova freshness e continua repair/backoff.
- `410 Gone` indica token/epoch expirado e conduz a snapshot completo por endpoint configurado.
- Falhas usam `application/problem+json` conforme RFC 9457.
- Resposta de cadeia usa `application/cloudevents-batch+json` e ordem **link-contiguous**:
  `patch[n+1].base` é exatamente `patch[n].target`, sem exigir incremento numérico de um.
- Repair com exatamente um patch MAY usar `application/cloudevents+json`; dois ou mais usam o
  batch. Ambos são uma resposta HTTP canônica única, autorizada, ligada à repair generation e ao
  head final — nunca uma sequência de requests independentes inferida pelo cliente.
- Em singleton/batch, todas as mensagens têm exatamente o mesmo stream descriptor/schema/epoch.
  Os headers `Continuum-Stream/Epoch/Sequence/State-Token/State-Digest` correspondem ao `target`
  do último patch; `Continuum-Fresh-For-Ms` e `Continuum-Stale-If-Error-Ms` correspondem à
  freshness dele, enquanto `Continuum-Age-Ms` segue o novo corte de validação de § 7.3. Qualquer
  mismatch invalida a resposta inteira sem instalar patch nem renovar freshness.
- O ETag de qualquer repair que contenha patch, singleton ou batch, valida bytes da resposta de
  repair, não a representação snapshot do estado final. Ele não fica associado ao estado
  instalado e não pode ser enviado depois como `If-None-Match` de snapshot; após instalar patch,
  o ETag de snapshot anterior continua removido até novo snapshot `200`/`304` válido.
- Redirect de repair só é aceito para origem allowlisted e passa por nova autorização.

Um repair nunca é satisfeito autoritativamente por cache compartilhado: o request alcança a
autoridade/origin que valida o fence durável corrente e os headers `Min-*`. Um `200` público daí
resultante MAY popular o cache normal de snapshot, mas um intermediary não decide sozinho que uma
representação anterior cobre o repair. Para resposta pública cacheável, `max-age` e `s-maxage`
MUST ser no máximo
`floor(max(0, fresh_for_ms - Continuum-Age-Ms) / 1000)` no corte de validação; `stale-if-error` e
`stale-while-revalidate` MUST ser, cada um, no máximo
`floor(stale_if_error_ms / 1000)`. As janelas não se somam: em nenhum caminho a idade HTTP aceita
pode ultrapassar `fresh_for_ms + stale_if_error_ms` do payload. Uma revalidação `304`
recalcula esses limites a partir da mesma versão; não herda diretivas mais permissivas de uma
resposta anterior.

### 12.2 SSE

- a resposta usa `Content-Type: text/event-stream`; a concatenação das linhas `data:` de cada
  evento de projeção contém um CloudEvent JSON Format completo;
- `event:` corresponde a `data.kind` nos CloudEvents de projeção;
- `id:` é delivery cursor, não sequence;
- em `continuum-ready` e `continuum-caught-up`, o valor SSE `id:` MUST ser exatamente o
  `delivery_cursor` do JSON; divergência invalida o controle e fecha/reabre a conexão sem aceitar
  nenhum dos dois tokens;
- `Last-Event-ID` é validado, limitado e ligado ao contexto autorizado;
- heartbeat é comentário;
- no modo subscribe-first, **toda conexão física**, inicial ou reconnect/resume, emite um novo
  `event: continuum-ready`. Ele só nasce a partir do corte atômico em que a conexão autorizada está
  registrada; contém subscription id, delivery cursor, digest do manifesto e versão completa do
  head de cada stream, mas nunca estado de projeção. `ready` é o primeiro frame não-heartbeat da
  conexão e é enfileirado no mesmo corte antes de replay/live ser liberado; nenhum evento de dados
  pode precedê-lo. Isso é obrigatório porque o user agent pode avançar `Last-Event-ID` antes de o
  callback instalar o controle: reconnect sempre fornece outro barrier completo, sem depender de
  ACK de aplicação. Seu head pode forçar fetch/repair canônico e portanto não autoriza pular estado;
- em todo resume/reconnect, após zero ou mais eventos de replay, `event: continuum-caught-up`
  contém heads correntes e fecha a janela. Ele só vale contra o `ready` da mesma conexão/
  `transport_generation`; perder o callback do `ready` invalida aquela conexão, não permite usar
  um `caught-up` órfão. `continuum-ready` e
  `continuum-caught-up` são controles do binding, exceções explícitas ao requisito de CloudEvent
  em `data:`; seu JSON é limitado, versionado e nunca contém projeção;
- `event: continuum-security-generation` carrega exatamente um controle
  `security_generation` do schema de binding e é a terceira e última exceção ao envelope
  CloudEvents. Ele precisa apontar a subscription corrente e é processado pela máquina de
  segurança de § 13.1 antes de qualquer ordenação/dedupe de projeção; `id:` continua sendo apenas
  delivery cursor e nunca ordena política. Revision repetida idêntica é duplicata sem extensão de
  lease, revision regressiva é ignorada só depois de autenticação/validação, e revision igual
  divergente fecha e purga. Outro JSON não-CloudEvent ou outro nome `event:` fecha a conexão;
- a passagem replay→live é um corte atômico: tudo coberto pelo delivery cursor do `caught-up` já
  foi emitido nessa conexão e toda publicação confirmada depois do corte será entregue pelo caminho
  live. Scan de journal seguido de registro live não atômico não é conforme;
- em stream multiplexado, `continuum-caught-up` traz subscription/delivery cursor e uma entrada
  de versão completa por stream. Uma entrada exatamente igual ao estado instalado fecha o replay
  e agenda validação HTTP sem renovar freshness; head futuro inicia repair, head regressivo é
  ignorado e epoch divergente força reset.
  Subscription id, digest do manifesto e conjunto exato de streams precisam coincidir com o
  `ready` corrente; entrada omitida, extra, duplicada ou conflitante invalida o controle inteiro;
- cada conexão local tem `transport_generation`; evento ou controle enfileirado captura essa
  geração e é descartado se chegar depois de outra conexão assumir, mesmo com subscription id
  semelhante;
- `204` encerra reconexão automática;
- cada conexão/reconexão é autorizada; streams longos têm lease/revalidação ou revogação ativa
  com SLA declarado;
- o servidor responde `Cache-Control: private, no-store, no-transform`;
- proxy MUST preservar streaming, cancelamento, status e headers permitidos sem buffer global.

Uma assinatura protegida seleciona sua linhagem por `subscription_id` opaco, nunca por “sessão
atual” implícita. Fetch-stream envia `Continuum-Subscription-Id` e
`Continuum-Security-Generation`; native `EventSource` usa uma rota configurada como
`/continuum/v0.2/subscriptions/{subscription_id}/events`, construída localmente — a resposta de
lease não fornece URL arbitrária. O id no path não é bearer: o servidor autentica de novo, liga-o
ao contexto autorizado completo, manifesto e generation correntes e devolve `404` não enumerante
para id ausente, alheio ou revogado antes de consultar journal/bytes. Assim duas abas da mesma
sessão podem manter linhagens distintas; cada `ready` precisa ecoar exatamente a subscription da
própria rota/conexão.

Native `EventSource` não permite cabeçalhos arbitrários no request inicial nem expõe status e
headers de resposta de forma suficiente para distinguir `401/403` de falha de rede. Por isso,
streams `tenant` ou `principal` MUST usar fetch-stream ou outro binding especificado separadamente
(com status, cancelamento e headers visíveis) ou um canal autenticado de lease/security generation
que ordene purge. Native
`EventSource` sem esse controle só é conforme para stream público e usa a estratégia
subscribe-first/`continuum-ready`, pois não consegue injetar um cursor no primeiro request.
Native `EventSource` protegido exige `cookie-auth`: a API não injeta `Authorization`, bearer em
query é proibido e subscription/generation ids não são credenciais. `non-cookie-auth` protegido
usa fetch-stream ou outro binding que especifique transporte de credencial e status.
Snapshot-first exige fetch-stream ou outro binding capaz de enviar o resume token. Token de
bearer nunca vai em query string. Como native `EventSource` same-origin envia credenciais, seu
stream público MUST morar em origin cookieless dedicado com CORS sem credentials; numa origin
com cookie de sessão, o cliente usa fetch-stream com `credentials: "omit"`. Endpoint público não
aceita um cookie silenciosamente nem varia por ele.

### 12.3 WebSocket, gRPC ou log

Esses transportes MAY substituir SSE apenas sob outro binding que declare delivery cursor,
reconexão, autorização, catálogo de limites, reset e vetores executáveis equivalentes. Eles não
podem declarar conformidade com o manifest/corpus SSE fornecido nesta 0.2. Ordenação de frames
dentro de uma conexão não fornece replay após reconexão nem ACK de aplicação.

### 12.4 SSR bootstrap

SSR MAY embutir um snapshot. Ele MUST incluir cursor, state token, state digest, schema e freshness idênticos
ao payload instalado; MUST ser serializado como dados, escapado contra fechamento de script e
protegido por CSP. Dados pessoais usam `private, no-store` e nunca entram em cache público ou
service worker.

Bootstrap público herdado de HTML cacheado soma `Continuum-Age-Ms`, `Age` do documento e o tempo
monotônico entre início da navegação e fim da hidratação pela fórmula de § 7.3. Se a camada HTML
não preserva esses headers/âncoras, o documento usa `no-store` e o bootstrap nasce no máximo
`stale_usable` até fetch canônico. Restore de bfcache nunca reinicia o prazo; usa o deadline
conservador original, aplica a regra monotonic/wall/suspension de § 7.3 antes de marcar conteúdo
como atual e agenda reconciliação.

Isso também vale antes da hidratação. `public-data + ssr-bootstrap` que possa entrar em bfcache
MUST escolher uma das duas formas: (a) um guard CSP-nonced/hashed, parser-blocking, sem import/rede
e anterior a qualquer indicador/markup que alegue freshness instala os anchors e, no hide/pagehide,
persiste no documento a marca `stale_usable` antes do cache; ou (b) o HTML nasce semanticamente
`stale_usable`/não-current e só é promovido depois que o runtime recalcula idade conservadora.
Navegar antes da hidratação e restaurar depois do hard expiry nunca pode reapresentar o documento
como fresh; sem guard, markup que afirme atualidade por default não é conforme. Conteúdo público
útil pode continuar visível enquanto o fetch valida, sem inventar loading visual nesta spec.

O profile browser `protected-data` da 0.2 não conserva representação protegida em bfcache ou
durante suspensão. Em conteúdo obtido depois da hidratação, antes de instalar o primeiro byte
protegido o adapter registra um handler síncrono de pré-suspensão. No primeiro
`visibilitychange` para hidden, `pagehide` ou `freeze`
observável, ele incrementa `authorization_fence`, invalida a lease e, antes de retornar, cancela
operações, fecha transporte e purga estado, buffers, ETags, receipts/commands sensíveis,
bootstrap serializado e DOM derivado de dados protegidos. O default deliberadamente também purga
numa simples troca de aba: isso fecha a janela em que o browser poderia congelar ou fotografar a
página antes de JavaScript voltar a executar.

Um restore `pageshow.persisted` começa com regiões protegidas vazias e permanece render-blocked
para esses dados até novo grant autorizado e fetch canônico; nem snapshot anterior nem screenshot
DOM podem aparecer enquanto isso. Um adapter MAY evitar o purge em hidden somente com evidência
target/browser-specific de que um hook roda e conclui antes de qualquer freeze, snapshot de
bfcache **e primeiro paint no restore**, coberta por vetor próprio. Plataforma que pode suspender
e reapresentar pixels sem sinal anterior nem gate before-paint fica NO-GO para `protected-data` em
browser na 0.2. O protocolo não alega executar timers durante suspensão; a confidencialidade vem
do purge anterior, e revogação recebida enquanto o runtime está observável continua sujeita ao
`max_revocation_sla_ms`.

`protected-data + ssr-bootstrap` é NO-GO no browser genérico: markup/bootstrap pessoal pode ser
parseado e entrar em bfcache antes de hidratação, e `no-store` não prova exclusão de bfcache. Essa
combinação só pode aparecer numa unit target-specific se um guard CSP-nonced/hashed,
parser-blocking e sem dependência de import/rede for executado no `<head>` **antes de qualquer
markup ou bootstrap protegido**, instalar o purge/render gate acima e o adapter provar navegação
antes da hidratação, restore e ausência/falha do guard. Se o target não consegue garantir a
execução do guard, o servidor emite apenas shell público; bytes protegidos chegam somente depois
de grant + fetch canônico. Um manifest que declare protected SSR sem essa evidência falha.

Hidratação e repair MUST preservar conteúdo útil, foco, seleção, scroll e drafts locais. A
presença de bootstrap SSR não autoriza o stream nem dispensa revalidação após bfcache, wake ou
troca de rede.

### 12.5 HTTP de comando e receipt

- antes do primeiro submit mutante, um endpoint autorizado `POST /command-ids` recebe
  `issuance_nonce` opaco com ao menos 128 bits aleatórios, escolhido uma vez pelo cliente, e a
  operation, e devolve command id
  autenticado, escopo, `retry_for_ms` e `issuance_age_ms`. Repetir o mesmo nonce no mesmo escopo
  devolve o mesmo id e idade não decrescente; o cliente desconta idade e tempo local como em
  § 8.5. O CAS de emissão é particionado, depois da autenticação, por `(authority, environment,
  tenant, principal, operation, issuance_nonce)`. Os mesmos bytes de nonce em outro escopo são
  independentes e nunca consultam, conflitam nem revelam o registro original. Emissão é
  `private, no-store`; resposta perdida é recuperada repetindo somente essa emissão sem efeito;
- submissão usa endpoint/operation configurado, `Continuum-Command-Id` e corpo JSON completo. A
  primeira utilização liga fingerprint ao id por CAS; duas primeiras utilizações concorrentes com
  intenções diferentes permitem no máximo uma e fazem a outra conflitar;
- o servidor autentica/autoriza, normaliza a intenção e calcula o fingerprint; a comparação forte
  de `If-Match` ocorre dentro da transação terminal local ou da transação de aceitação externa de
  § 8.5. Falso registra `rejected` sem efeito e retorna `412`; conflito de command id/fingerprint
  retorna `409`;
- todo `POST` autenticado por cookie de emissão ou submit aplica a defesa CSRF canônica antes de
  alocar idempotência ou executar efeito, valida origem confiável e não habilita CORS credentialed
  para origem arbitrária; command id, issuance nonce e receipt token não são defesas CSRF;
- `202` MAY retornar receipt `accepted`; resultado terminal retorna CloudEvent
  `application/cloudevents+json` ou fica consultável;
- lookup usa endpoint confiável por command id/receipt locator e reautoriza o escopo inteiro;
- receipt ainda retido retorna a maior `receipt_revision`; expirado retorna `410` sem repetir o
  efeito; ausência/negação não vaza existência entre principals;
- emissão, submit/retry e lookup, inclusive hits idempotentes, consomem
  `max_command_operations_per_minute` antes de lookup/alocação. As janelas de 60 s são aplicadas
  separadamente ao principal, tenant e IP (e só IP antes de autenticação); exceder qualquer uma
  retorna `429` + `Retry-After`, `private, no-store`, sem efeito ou revelação de existência;
- toda resposta usa `private, no-store`, inclusive erro.

### 12.6 HTTP de lease e revogação

O binding protegido declara um endpoint canônico de lease; a rota recomendada é
`POST /continuum/v0.2/auth/lease`. Ele usa o mesmo modo `cookie-auth`/`non-cookie-auth` da unit; no
primeiro, CSRF/origin é validado antes de criar subscription ou security generation. Todo request
autenticado usa
`Content-Type: application/json`, `Continuum-Lease-Request` (nonce opaco novo por tentativa) e
body `{protocol_version, operation, lease_operation_id, subscription_manifest,
subscription_manifest_digest}`. `lease_operation_id` é estável em todas as tentativas da mesma
operação lógica de grant/renew, é gerado no cliente com CSPRNG e contém ao menos 128 bits de
entropia; uma nova operação lógica, inclusive em outra aba, gera outro valor. Reusar o mesmo valor
no mesmo contexto/chave afirma que é a **mesma** operação e recebe o mesmo resultado idempotente,
não uma linhagem nova. `Continuum-Lease-Request` também tem ao menos 128 bits aleatórios, é novo a
cada tentativa de transporte e só correlaciona request/response. O
manifesto tem a forma canônica de § 4.3; o servidor autoriza cada stream id, rejeita ids
desconhecidos/repetidos e recomputa o digest em vez de confiar no hash recebido.
Digest incorreto, id repetido ou forma inválida retorna `400` antes de criar estado. Manifesto
canônico com stream desconhecido e manifesto com stream conhecido porém não autorizado retornam
o mesmo `404` não enumerante; ambos fazem zero criação de lease/subscription e zero entrega de
bytes. A autorização é all-or-nothing para cada id antes do CAS.
Antes do CAS, toda tentativa consome a janela `max_lease_operations_per_minute`; exceder retorna
`429` + `Retry-After`, `private, no-store`, sem lookup de idempotência nem criação. Um grant
inicial com operation id ainda inexistente também reserva atomicamente uma vaga em
`max_active_subscription_lineages_per_context`; o N+1 falha sem estado. Retry do mesmo grant não
reserva outra vaga, mas conta na taxa. Successor substitui membro da mesma linhagem; expiry ou
revogação libera a vaga, enquanto disconnect sozinho não.
`operation="grant"` inicial não envia subscription/generation ainda: depois de autenticar e
autorizar o manifesto, a resposta
`action="grant"`, revision 1, cria ambos atomicamente. `operation="renew"` acrescenta
`Continuum-Subscription-Id`, `Continuum-Security-Generation` e
`Continuum-Lease-Revision`. Depois de um controle `reauthorize`, novo `grant` acrescenta o
`Continuum-Pending-Security-Generation`, `Continuum-Previous-Security-Generation` e
`Continuum-Previous-Subscription-Id`; ele não reutiliza a subscription revogada.

Depois de autenticar e autorizar, o servidor usa chaves de idempotência/CAS diferentes por gesto.
Grant inicial usa `(contexto autorizado completo, "initial", digest canônico do manifesto,
lease_operation_id)`. Renew usa `(contexto autorizado completo, subscription_id,
security_generation_id, lease_revision corrente, lease_operation_id)`. Grant sucessor usa
`(contexto autorizado completo, previous_subscription_id, previous_security_generation_id,
pending_security_generation_id, lease_operation_id)`. O contexto completo é `(authority,
environment, tenant, principal, session-or-revocation-identity)`; o mesmo operation id em outro
contexto, tenant, principal ou gesto é independente e nunca consulta o registro original.
Repetir uma chave com fingerprint idêntico devolve o mesmo grant/renew, subscription, generation
e revision; fingerprint divergente retorna `409 private, no-store` sem criar ou estender estado.
Uma resposta perdida não cria duas generations ativas para a mesma operação.

O contexto de sessão/revogação mantém no servidor um `authorization_epoch` durável, monotônico e
um status ativo; cada linhagem mantém também `lineage_policy_epoch` monotônico. Grant/renew captura
os epochs aplicáveis depois da autenticação, mas também os compara de novo e grava lease/revision
no **mesmo** ponto de serialização em que revogação/logout incrementa o epoch de contexto, marca
inativo e invalida linhagens, e em que `purge`/`reauthorize` incrementa o epoch da linhagem e
terminaliza sua lease. Mudança global de política que afeta o contexto incrementa o epoch de
contexto; mudança específica usa o da linhagem. Auth, status ou epoch divergente falha com a
resposta genérica de autenticação/autorização, `private, no-store`, sem criar/estender lease nem
revelar subscription. Se renew vence primeiro, a transição posterior ainda terminaliza a lease;
se a transição vence primeiro, o CAS de grant/renew não pode ressuscitar a geração. O deadline de
um renew vencedor continua ancorado na criação da revision e cabe no SLA.

Renew MUST enviar manifesto e digest exatamente iguais ao manifesto imutável ligado à
subscription. Diferença retorna `409 private, no-store`, sem avançar revision ou deadline. Mudar
streams/configuração exige reautorizar e concluir grant sucessor com nova subscription e novo
barrier; renew nunca muta manifesto in-place.

O grant inicial cria a raiz de uma linhagem; cada troca cria novo `subscription_id`, mas o servidor
preserva a cadeia predecessor→sucessor. Nela há no máximo uma generation ativa. Além do CAS por
operation id, grant sucessor resolve a linhagem após autenticar/autorizar e ocupa um slot único por
`(lineage_root, previous_subscription_id, previous_security_generation_id,
pending_security_generation_id)`, independentemente do novo `lease_operation_id`. O contexto
autorizado completo e o novo manifesto formam o fingerprint do candidato, não parte que possa
abrir outro slot: exatamente um successor vence; tentativa com fingerprint igual repete o mesmo
resultado, e divergente conflita sem criar outra subscription. Renew é CAS da lease revision N→N+1 na
mesma generation: concorrente equivalente reproduz o vencedor; concorrente incompatível retorna
`409` e não revoga a generation vencedora. Reauthorize também seleciona por CAS um único pending
generation; tentativa incompatível conflita sem invalidar o contexto corrente. Revogação terminal
de candidate perdedora só se aplica ao successor grant que chegou a alocar uma subscription/
generation distinta antes de perder o CAS. Grants iniciais com operation ids diferentes MAY
criar linhagens independentes para
duas abas/clientes no mesmo contexto e manifesto. Contextos de sessão/revogação distintos nunca
compartilham generation nem se revogam por colisão de CAS; revogar o contexto, porém, invalida
todas as linhagens que pertencem a ele.

A resposta bem-sucedida usa `application/json`, ecoa `Continuum-Lease-Request`, contém exatamente
um controle `security_generation` válido com `subscription_manifest_digest` exatamente igual ao
pedido, inclui `Continuum-Lease-Age-Ms` não negativo e envia `Cache-Control: private, no-store`.
O age mede o intervalo conservador desde a criação daquela revision; em retries do mesmo
`lease_operation_id` ele nunca diminui e fica fora do controle para que a mesma revision possa
ser reproduzida byte a byte. Redirect passa por nova autorização e só pode ir para origem
allowlisted. Timeout, resposta sem eco/age, manifesto, geração ou subscription divergente e
resposta de conexão anterior não concedem nem renovam lease.

O cliente mantém `lease_transition_generation` monotônica. Iniciar ou substituir tentativa captura
esse contador, contexto autorizado, `authorization_fence`, operation id, manifesto e o estado
esperado da linhagem. Imediatamente antes de parse e de install, a resposta precisa coincidir com
essa captura e com o eco da tentativa. Grant inicial espera ausência de geração naquela raiz;
successor grant espera exatamente previous subscription/generation e pending generation ainda
correntes; renew espera subscription, generation, revision e lease anterior ainda vigentes. Esse
transition gate substitui — para grant inicial/sucessor — a exigência impossível de uma lease
prévia. Tentativa supersedida ou contexto/fence divergente é descartado; renew depois de expiry não
ressuscita e muda para novo grant. A instalação e qualquer incremento de fence abaixo são
serializados contra nova transição.

Ao iniciar o request, o cliente captura os anchors de elapsed conservador de § 9. Ao terminar
autenticação, leitura, parse e validação, instala prazo de no máximo
`max(0, lease_for_ms - Continuum-Lease-Age-Ms -
elapsed_request_response_parse_ms)` a partir daquele corte e conserva anchors/duração para
recalcular em todo gate; não reduz a checagem a um timer que possa pausar. Resposta cujo restante
é zero expira sem instalar. Um retry jamais move o deadline além daquele calculado de uma resposta
válida anterior. Assim, resposta perdida, fila de rede, main thread/VM suspensa ou callback
atrasado não cria lease mais longo que o concedido.

Um `grant` canônico válido incrementa o `authorization_fence` local imediatamente antes de ativar
a nova security generation e seu deadline. `renew` contínuo da mesma geração pode estender apenas
o deadline sem mudar o fence, mas somente enquanto generation, fence e lease anteriores ainda são
correntes; depois de expiry, a geração não ressuscita por renew atrasado e exige novo grant.

Somente `grant`/`renew` nessa resposta canônica podem criar ou estender deadline. Um `purge` ou
`reauthorize` autenticado no stream usa `lease_for_ms=0` e pode antecipar a revogação, nunca
estender prazo. Antes de cancelar operações ou purgar estado, revogação, `purge` e `reauthorize`
incrementam o `authorization_fence` e invalidam a lease corrente. `reauthorize` é revisão da
geração atual e traz `next_security_generation_id` apenas como id **pendente**: depois desse fence,
registra o id pendente, purga e obriga `grant`; esse id só se torna geração ativa pela resposta
HTTP canônica e dado protegido não pode ser instalado antes dela. O servidor
encerra conexão aberta ou emite o controle terminal dentro do SLA de revogação do deployment;
perda desse frame ainda converge porque o prazo local expira. Na expiração, o perfil de browser
primeiro incrementa o `authorization_fence` e invalida a lease; somente depois cancela operações,
purga estado, buffers, ETag e comandos protegidos e fecha qualquer transporte ativo. Reconnect
executa autorização completa e é negado sem lease novo; heartbeat, tráfego de dados, estado
offline ou `caught_up` não mantêm a autorização viva.

## 13. Segurança, privacidade e cache

### 13.1 Autorização

O servidor MUST autorizar separadamente, antes de produzir conteúdo ou consultar cache:

- snapshot/bootstrap;
- subscribe e cada reconnect;
- replay;
- repair e `304`;
- grant/renew da lease;
- emissão de command id, submit e cada retry;
- lookup de receipt e observação de resultado.

Stream id, partition, subject, ETag, delivery cursor e command id não são autorização.
Ownership/BOLA é verificado contra o principal e tenant resolvidos pelo servidor. Host e headers
forwarded só participam da identidade quando vêm de proxy confiável e foram normalizados.
`receipt_token` também é apenas locator/validator, nunca bearer capability; lookup reautoriza
tenant, principal, operação e command id.

`security_generation_id`, `subscription_id`, delivery cursor, command id, receipt token e nonce
de emissão/lease são opacos, limitados e sem PII, credencial, token de sessão ou segredo de
negócio embutido. Eles não são bearer tokens e não substituem autenticação; valores recebidos do
cliente são ligados por MAC/registro server-side ao contexto autorizado antes de qualquer lookup.
Logs e métricas usam hash/label de baixa cardinalidade, nunca o valor bruto. IDs server-minted
que enfrentam rede são imprevisíveis o bastante para não oferecer enumeração útil, embora essa
propriedade não seja tratada como autorização.

Endpoint `public-data` cacheável é credentialless e separado: rejeita `Cookie`, `Authorization`,
identidade de certificado e credencial em query antes de cache/lookup, não os ignora nem varia
secretamente por eles. Também não envia `Set-Cookie`. Um caminho que aceite qualquer credencial é
outro state domain/profile e não pode produzir resposta marcada `public`.

No profile `cookie-auth`, o cookie de sessão/autorização usa `Secure`, `HttpOnly` e
`SameSite=Lax` ou `SameSite=Strict`; `SameSite=None` não satisfaz este profile. Todo request
unsafe valida um `Origin` exato allowlisted e o token CSRF canônico ligado à sessão antes de
lookup, alocação ou efeito. SameSite é defesa adicional, não substituto de CSRF/origin, e CORS
credentialed nunca é refletido para origem arbitrária. Um deployment que precise de outra
política de cookie exige profile e vetores próprios.

Um endpoint/state domain `cookie-auth` não aceita `Authorization`, identidade de certificado ou
outro mecanismo como fallback; credenciais de modos diferentes, inclusive cookie A + bearer B,
são rejeitadas antes de lookup e nunca resolvidas por precedência. De modo simétrico,
`non-cookie-auth` rejeita cookie e credencial em query. Suportar ambos exige endpoints e state
domains realmente separados ou um profile posterior de composição com vetores próprios.

Logout, troca de conta/tenant/operador, revogação ou perda de autorização MUST primeiro
incrementar o `authorization_fence` e invalidar a lease corrente; depois cancela transporte,
aborta requests, zera buffers e purga dados protegidos imediatamente. A regra de
"manter o último estado utilizável" não se aplica entre security generations.
Comandos pendentes da geração anterior tornam-se `unknown`, têm retries/lookups cancelados e não
podem ser reenviados sob a nova identidade.

O controle autenticado `security_generation` é uma máquina separada do cursor de dados. Cada
geração tem id único não reciclável, `lease_revision` crescente e um `authorization_fence` local
que muda nas fronteiras definidas acima. `grant` revision 1 nasce só da
resposta HTTP canônica; `renew` mantém o mesmo id e só estende prazo quando veio desse endpoint
com request monotônico limitado. Cópia recebida pelo stream não concede lease. Revisão igual e
conteúdo igual é duplicata e **não** reinicia deadline, revisão menor é ignorada depois de
validada, e mesma revisão divergente fecha/purga por falha. `purge` é terminal naquela geração.
`reauthorize` referencia exatamente a geração corrente e carrega id novo em
`next_security_generation_id`; esse id só nasce como geração ativa quando um `grant` revision 1 o
confirma, apontando `previous_security_generation_id` para a antiga. O cliente registra o id como
pendente, incrementa o fence, cancela operações, purga o estado protegido anterior e inicia novo
grant/fetch; só depois do grant canônico o torna ativo e processa qualquer head de dados. Um
controle de stream só vale para o subscription id
corrente; replays de conexão anterior são ignorados. Política atrasada nunca é filtrada por
sequence da projeção. Offline além do lease purga, sem renovar por heartbeat ou duplicata.

### 13.2 Matriz mínima de cache

| Classe | Requisitos mínimos |
|---|---|
| snapshot público | endpoint credentialless separado; sem `Set-Cookie`; `public` apenas com chave/Vary completos e TTL HTTP limitado pela freshness semântica |
| snapshot tenant/principal | `Cache-Control: private, no-store`; sem CDN/SW compartilhado |
| repair/replay protegido | `private, no-store`; autorização e fence do origin antes de lookup/ETag |
| SSE | `private, no-store, no-transform` |
| grant/renew de lease | `private, no-store`; auth + CSRF/origin do profile antes de criar ou renovar geração |
| command submit/receipt/erro de auth | `private, no-store`; proteção CSRF/origin antes de idempotência/efeito; id/locator não é bearer e lookup reautoriza escopo completo |

`private` sozinho ainda permite cache privado; `no-cache` permite armazenamento. Por isso dados
pessoais exigem `no-store`. Uma representação pública MUST ter todas as dimensões que mudam bytes
na URI, cache key ou `Vary`: host confiável, query normalizada, locale, moeda, canal, price
context, schema, tenant/audience e coorte. Coorte de rollout não pode ser parâmetro livre nem
mudar bytes sob a mesma chave.

`no-store` no HTTP não impede código de executar `Cache.put`. Na 0.2, service workers MUST
bypassar **toda** resposta Continuum, inclusive snapshot público e documento HTML que embuta um
bootstrap Continuum: Cache API não atualiza `Age` e um reload offline poderia reiniciar o
deadline. HTML com bootstrap que não possa ser excluído do service worker usa `no-store` e não é
reutilizado offline. Cache HTTP normal/CDN permanece permitido sob as regras acima. Persistência
privada é memory-only por padrão; qualquer capability futura de
persistência declara relógio `stored_at` monotônico/não-extensível, TTL, isolamento e purge
testável em reload, logout, tenant switch e rollback.

### 13.3 Conteúdo e recursos

- Estado e patch são dados, nunca HTML executável.
- Parser/decompressor aplica limites antes de alocar estruturas proporcionais ao input e cobra
  cada representação simultânea na quota residente; `Content-Length` sozinho não basta.
- `dataschema` e `stream.schema` são identificadores resolvidos apenas em registry local
  allowlisted; consumidor MUST NOT dereferenciar URI recebida do wire.
- Parsers rejeitam membros JSON duplicados. Runtime vulnerável a prototype pollution usa mapas
  sem protótipo ou rejeita recursivamente `__proto__`, `prototype` e `constructor` em **todo** JSON
  Continuum recebido: snapshot, patch/values, Merge Patch, result/problem/extensions, controles,
  lease e command issuance/submit, inclusive `request` e `precondition`, antes de normalização,
  fingerprint, merge ou CAS. `path` e `from` seguem RFC 6901 e passam pela mesma lista; limites de
  bytes/nós/profundidade são verificados também **depois** do patch.
- Journals minimizam conteúdo, têm TTL, acesso, auditoria e política de eliminação.
- Payloads, PII, tokens e stream ids brutos não aparecem em métricas de alta cardinalidade.
- TLS é obrigatório fora de desenvolvimento local.
- CSP e proteção contra XSS são gate para projeções pessoais de longa duração.

## 14. Evolução e rollback

Há três versões independentes:

1. `specversion` do CloudEvents;
2. `data.protocol_version` deste perfil;
3. `stream.schema` da projeção.

Deployments MUST suportar cliente/servidor N e N-1 durante a maior janela entre abas antigas,
bfcache, service worker e rollback. Mudança aditiva preserva schema quando consumidores antigos
podem ignorá-la. Mudança incompatível de schema-major usa novo stream id, `stream.schema` e
dual-publish ou endpoint separado durante a janela.

Em respostas HTTP finitas e em fetch-stream, protocol major aparece na URI e o cliente anuncia no
`Accept` os parâmetros `continuum` e `schema`; a resposta ecoa a escolha no `Content-Type`,
`data.protocol_version` e `stream.schema`. Representação pública negociada envia `Vary: Accept`,
ou, preferivelmente, usa URI distinta por schema para evitar chave ambígua.

Native `EventSource` não consegue configurar esse `Accept`. Nele, a URI vem de configuração local
confiável e é específica de protocol major + manifesto/schema; o servidor não negocia outro
schema nessa rota. No público, `continuum-ready` é o handshake obrigatório antes de dados: ecoa
protocol version, digest/conjunto exato do manifesto e cada `stream_id`; cada id resolve no
registry local para o descriptor/schema imutável já selecionado pela URI. No protegido, o POST de
lease já anuncia protocol version + manifesto autorizado, e `ready` ecoa exatamente seu
digest/conjunto; cada id resolve para o mesmo descriptor local. Mismatch fecha sem instalar bytes.
URIs/endpoints/streams N e N-1 coexistem durante a janela; servidor
nunca escolhe schema não anunciado pelo `Accept`, URI configurada ou lease. Outros bindings
publicam handshake equivalente antes de dados.

Patch nunca atravessa schema ou epoch. Snapshot persistido com schema não suportado é descartado
e dispara nova negociação por configuração confiável para um endpoint/stream suportado; repair
no stream incompatível não pode convertê-lo nem mudar seu schema. Não há migração implícita.
Rollback dentro do mesmo schema-major pode criar novo epoch e forçar snapshot compatível.
Rollback entre majors volta ao stream/versioned endpoint anterior; não reutiliza stream id do
major novo.

O consumidor MUST ignorar propriedades opcionais desconhecidas dentro de `data.extensions`.
Ausência de um campo REQUIRED, kind desconhecido requerido ou protocol major incompatível falha
a negociação e não altera estado.

## 15. Observabilidade e SLOs

Implementações conformes expõem, com cardinalidade controlada:

- tempo e bytes de snapshot/repair;
- idade instalada e tempo em `stale_usable`/`stale_blocked`;
- contagem de duplicata, regressão, gap, equivocation e reset;
- repair success/failure/loop e motivo;
- profundidade/bytes máximos de fila e desconexão por slow consumer;
- resident bytes agregados, inclusive pico durante aplicação de patch;
- rejeições N+1 por limiter de request/response/parser e reservas de memória liberadas;
- reconnects, backoff e duração da conexão;
- conflito de fence/epoch ativo e rejeição de leitura por réplica stale;
- lag entre served head, published head e head autoritativo; idade da outbox e watermark do
  projector;
- distância journal head→retention floor e latência do barrier replay→live;
- divergência entre projeção e fetch canônico em shadow;
- command retry, fingerprint conflict, receipt lookup e latency até observation fence;
- idade do `accepted` mais antigo e contagem de receipts `indeterminate`;
- grants/renews ativos, linhagens por contexto, conflitos de auth/policy epoch e latência
  revoke→purge contra o SLA;
- troca de `time_authority_epoch`, largura do intervalo lower/upper, expiry conservador e GC
  retido por incerteza;
- auth denial/revocation sem identifiers sensíveis.

Tracing distribuído SHOULD usar [W3C Trace Context](https://www.w3.org/TR/trace-context/) como
extensão CloudEvents. O trace correlaciona operações; não ordena estado.

Antes de promoção, o deployment define SLO e kill switch para: zero vazamento cruzado, zero
efeito duplicado, convergência de gaps injetados, limite de memória, limite de loop de repair e
rollback N-1.

## 16. Acessibilidade e integração de UI

Esta seção restringe consumidores; não prescreve visual.

- Uma representação SSR utilizável MUST continuar disponível para a integração durante
  hidratação/reconciliação enquanto autorizada e dentro do hard expiry; o protocolo não determina
  como a UI a apresenta.
- Update passivo preserva foco, seleção, scroll e linha de leitura enquanto o alvo continuar
  válido. Se o estado autoritativo remover o elemento focado, a integração move foco para o
  controle lógico estável mais próximo e anuncia a mudança; nunca o perde no `body`.
- Um lote finito MAY usar `aria-busy=true`, voltando a `false` ao concluir; stream permanente não
  mantém uma região busy para sempre.
- Mudanças humanamente relevantes usam anúncio `polite` coalescido. Eventos frequentes não são
  narrados um a um; `alert` é reservado a bloqueio real.
- Stale, offline, repairing e erro têm texto discernível, não apenas cor.
- Atualização automática não essencial oferece pausa, ocultação ou controle de frequência quando
  exigido por [WCAG 2.2.2](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html).
- Comandos e repair preservam drafts locais ou apresentam conflito explícito.
- Reduced motion é respeitado.

Estas regras seguem [WCAG 2.2 — Status Messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html)
e [WAI-ARIA 1.2](https://www.w3.org/TR/wai-aria/). A versão 0.2 não altera o loading visual do
produto.

Vetores de reducer só demonstram preservação de estado local. Conformidade de acessibilidade
exige teste em browser da árvore acessível, foco removido, live regions, `aria-busy`, pausa e
reduced motion; não pode ser declarada por comparação de JSON.

## 17. Conformidade

### 17.1 Artefatos

- [`message.schema.json`](../../contracts/continuum/v0.2/message.schema.json): sintaxe do wire;
- [`examples.json`](../../contracts/continuum/v0.2/examples.json): exemplos neutros válidos;
- [`binding-control.schema.json`](../../contracts/continuum/v0.2/binding-control.schema.json):
  controles `ready`, `caught_up` e security lease;
- [`binding-control-examples.json`](../../contracts/continuum/v0.2/binding-control-examples.json):
  exemplos válidos dos controles do binding;
- [`binding-control-negative-examples.json`](../../contracts/continuum/v0.2/binding-control-negative-examples.json):
  controles deliberadamente inválidos, cada qual ligado ao erro estrutural esperado;
- [`conformance-vectors.json`](../../contracts/continuum/v0.2/conformance-vectors.json):
  sequências e resultados esperados;
- [`conformance-vectors.schema.json`](../../contracts/continuum/v0.2/conformance-vectors.schema.json):
  forma dos vetores.
- [`binding-vectors.json`](../../contracts/continuum/v0.2/binding-vectors.json): requisitos de
  cenário para auth, HTTP, cache, SSE, produtor, multi-stream e rollout.
- [`binding-vectors.schema.json`](../../contracts/continuum/v0.2/binding-vectors.schema.json):
  forma portátil dos vetores de integração.
- [`conformance-manifest.schema.json`](../../contracts/continuum/v0.2/conformance-manifest.schema.json)
  e [`conformance-manifest.example.json`](../../contracts/continuum/v0.2/conformance-manifest.example.json):
  forma verificável e exemplo neutro das units/adapters declarados pelo deployment.
- [`validate_contracts.py`](../../contracts/continuum/v0.2/validate_contracts.py): parser JSON estrito,
  validação estrutural, invariantes semânticos, regressões negativas e auditoria da matriz de
  aplicabilidade. Ele valida o corpus neutro; não substitui o runner contra adapters reais.

Passar o JSON Schema é necessário, não suficiente. Conformance exige os invariantes abaixo e os
vetores aplicáveis ao manifest do deployment.

O manifest declara uma ou mais **conformance units independentes e target-scoped**. Não existem
kind simples/composto, composição, herança nem união de facets ou target maps entre units. Cada
unit liga um escopo concreto de adapters/targets a: capabilities implementadas; profiles factuais
(`public-data`, `public-shared-cache`, `protected-data`, estratégia de corte, transporte, SSR,
service worker, multiplexação, rollout e provedor externo); e layers expostas (`authorization`,
`http`, `cache`, `sse`, `parser`, `producer`, `multistream`, `command`, `rollout`). Ela também
referencia `state_domains` registrados no nível do manifest. Cada entrada declara tipo,
`adapter_locator` URI/URN estável, namespace efetivo, canonicalizer e evidência de trace dos
namespaces stateful que podem reter bytes ou identidade entre operações, como Cache API, cache de
CDN, memória residente, journal, outbox ou índice de idempotência. O locator é só a localização do
adapter e não prova isolamento.

O adapter também declara `effective_backing_identity` canônica com exatamente `{kind,
backend_instance, partition, namespace}` e seu `effective_backing_identity_digest`, calculado como
`sha256-` + base64url sem padding do SHA-256 do UTF-8/JCS desse objeto. `backend_instance` é o id
estável atribuído pelo provedor ao recurso efetivo (não hostname, connection string, label do
manifest nem segredo); `partition` é database/bucket/store/cache-zone/storage-partition efetivo;
`namespace` é o prefixo/realm final depois de defaults. Strings são NFC, sem whitespace de borda;
scheme/host de URI são lowercase, porta default é removida e o canonicalizer aplica a regra de
case/alias do backend aos demais componentes. Memória usa a identidade atestada da instância de
runtime/storage partition, não um nome inventado pelo adapter. O canonicalizer tem id+versão
estáveis, consulta identidade do backend/runtime durante o teste e registra input redigido,
identidade resultante, digest e attestation em `trace_evidence`; declaração do manifest sozinha
não é prova. Se dois canonicalizers não conseguem provar que recursos possivelmente aliases são
distintos, o runner falha fechado.

Dois IDs não podem nomear o mesmo digest/identidade efetiva, mesmo por locators ou canonicalizers
diferentes; referência desconhecida ou entrada órfã falha. O validator confere forma, JCS/digest e
duplicatas declaradas; o runner compara o valor observado em trace com o manifest em todas as
units e rejeita alias observado. Código e infraestrutura estritamente stateless não são state
domains.
Profiles de
classificação (`public-data`/`protected-data`) valem para todo target que carrega dados naquela
unit. Profiles de binding/topologia descrevem a **relação testada** entre papéis: por exemplo,
`fetch-stream + subscribe-first` descreve stream + snapshot canônico no mesmo corte, sem afirmar
que o target HTTP usa fetch-stream. Todo target da unit precisa participar de fato dessa relação;
target alheio não pode ser incluído para satisfazer vetor. Facets de uma unit nunca reclassificam
target de outra. Assim, SSE público não transforma por produto cartesiano um adapter snapshot
protected-only em público.

Adapters da **mesma classificação** que compartilham bytes, cache key, security context,
subscription, journal, comando ou rollout precisam estar em **uma única unit consolidada**, com
todos os targets reais da relação e suas capabilities, profiles, layers e state domains
verdadeiros. Cada ID e cada identidade normalizada de state domain só pode ser referenciado por
uma unit em todo o manifest. Portanto, duas units não podem repartir o mesmo domínio e uma
terceira unit de relação não pode tentar reuni-las por declaração. Profiles de classificação
precisam ser verdadeiros para cada target de dados e profiles de binding/topologia para a relação
completa. Dividir scopes para escapar de um vetor, duplicar o domínio sob alias ou criar facets
sintéticas é falha. Um profile ou layer factual não pode ser omitido.

Se a consolidação revelar que o mesmo domínio stateful atravessa modos `cookie-auth` e
`non-cookie-auth`, a 0.2 não consegue alegar conformidade para esse escopo: cada unit protegida
tem exatamente um modo de autenticação. O deployment fica NO-GO até separar de fato os domínios
ou publicar um profile posterior com vetores explícitos de isolamento entre modos.

A 0.2 não define unit de relação mista. As identidades/digests efetivos registrados e observados
em `state_domains` de
qualquer unit pública e qualquer unit protegida MUST ser disjuntas; repetir ID ou identidade sob
alias entre classificações falha antes da execução. O trace MUST provar o locator e namespace
efetivamente usados pelo adapter e a identidade de backing atestada; registro auto-declarado não
substitui essa evidência. Um service
worker pode encaminhar a resposta protegida sem estado, mas não pode
compartilhar com o caminho público Cache API, memória de bytes, fila ou namespace persistente.
Deployment que precise de estado cross-classification fica NO-GO até publicar capability,
classificação por target e vetores de isolamento misto próprios; duas units separadas nunca servem
como prova conjunta.
`public-data` significa que os targets daquela unit são classificados como públicos;
`public-shared-cache` é adicional e só existe quando esses bytes podem passar por cache
compartilhado.

O manifest torna as implicações inevitáveis explícitas e o validator as rejeita quando omitidas:

- toda capability de dados declara exatamente uma classificação (`public-data` ou
  `protected-data`), inclui a baseline snapshot e as layers `http`, `cache`, `parser` e `producer`;
  command receipt é exclusivamente protegido, nunca acumula profile público, e nenhum state
  domain pode aparecer dos dois lados da classificação;
- toda unit `protected-data` declara exatamente um modo factual entre `cookie-auth` e
  `non-cookie-auth`; o primeiro exige CSRF/origin/SameSite, e o segundo rejeita cookie e query
  credentials em vez de aceitá-los como fallback silencioso;
- a layer `sse` declara exatamente um transporte (`native-eventsource` ou `fetch-stream`);
- `native-eventsource` ou `fetch-stream` exige exatamente uma estratégia entre `snapshot-first`
  e `subscribe-first`, as capabilities snapshot + invalidate e a layer `sse`;
- `native-eventsource` exige especificamente `subscribe-first`;
- `native-eventsource` protegido exige `cookie-auth`; a combinação protegida com
  `non-cookie-auth` é inválida;
- `native-eventsource` não declara capability de patch; patches exigem `fetch-stream` neste
  binding para cancelamento e enforcement incremental;
- `snapshot-first` realtime exige replay e journal capazes de servir desde o delivery cursor
  atômico; sem replay declarado, a única estratégia conforme é `subscribe-first`;
- `public-shared-cache` e `service-worker-present` exigem a layer `cache`;
- `multiplexed-stream` exige `multistream`; `ssr-bootstrap` exige snapshot + `http`;
- command receipt é sempre `protected-data` e exige as layers `authorization`, `http`, `cache`,
  `parser`, `producer` e `command` nesta versão do binding; lease, callback tardio e service worker
  são exercitados também quando essa é a única capability de dados da unit;
- `rollout-candidate` exige layer e documento de rollout completo, com orçamento de vazamento
  cruzado igual a zero.

O corpus de reducer testa a API pura da máquina de estados em harness isolado, sem chamar adapter,
HTTP, cache ou autorização do deployment. Ele roda uma vez por implementação de reducer e conjunto
de capabilities que a utiliza; o harness configura o escopo fictício de `examples.json` como
autorizado. A classificação pública default desses fixtures é estímulo neutro do modelo, não
alegação sobre a unit nem permissão para reclassificar um target real. Vetores com
`requires_profiles` exercitam adicionalmente o caminho protegido da implementação usada por uma
unit correspondente. Essa separação não autoriza assertion sintetizada nem pula vetor de reducer.

Um vetor de binding é candidato a cada unit quando suas `capabilities` e `requires_profiles` são
subconjuntos dela e seu `layer` está declarado; **target ou result path ausente é falha desse
vetor, nunca motivo para torná-lo não aplicável**. Todos os targets e paths referenciados precisam
estar mapeados naquela mesma unit candidata; o runner não procura target em outra unit nem agrega
facets entre units. No binding, fixture/literal de classificação ou transporte precisa coincidir
com profiles factuais da unit. Ausência de `requires_profiles` significa que basta a capability e
a layer. Conformidade de uma capability exige executar **todos** os vetores aplicáveis, não apenas
um perfil escolhido pelo implementador.

O corpus de reducer tem transições fechadas e é diretamente executável no harness isolado. Os
vetores de binding
não fingem ser um runner universal: cada implementação publica um manifest de adapters que mapeia
cada `target` e result path a HTTP/cache/DB/worker real. Cada execução de uma unit produz o único
`result_document` declarado no nível da unit; todos os adapters alvo contribuem para esse documento
e toda assertion ou `$result_ref` resolve nele. `trace_evidence`, também no nível da unit, aponta
para o trace agregado que prova ordem, concorrência e origem dos resultados. Target sem mapeamento,
path fora do documento ou assertion sintetizada é falha, e validação estrutural isolada não
autoriza alegar conformidade. Um deployment não pode alegar uma layer que expõe e depois omitir
seus vetores. Toda unit realtime deste corpus declara `sse` e exatamente um entre
`native-eventsource` e `fetch-stream`; WebSocket/gRPC exigem outro binding, outro catálogo de
limites e outro corpus antes de qualquer alegação de conformidade.

`result_document` e `trace_evidence` são IDs lógicos URN canônicos, não paths nem URLs de storage;
ambos são únicos entre units. A cada execução o runner aloca artefatos imutáveis distintos,
registra digest e identidade efetiva do objeto no trace e rejeita alias de inode/chave/objeto entre
IDs. `file:`, HTTP, percent-encoding, query e fragment não são aceitos nesses campos; duas strings
diferentes nunca bastam para provar dois artefatos.

Vetores de fronteira usam `requires_limits` e a expressão
`{"$limit_ref":"nome","delta":n}`. O runner resolve **somente** contra `unit.limits[nome]`, soma
`delta` com aritmética exata, rejeita resultado negativo/fora de I-JSON e configura o adapter real
antes da action. O set de refs precisa ser exatamente `requires_limits`. O result document repete
os valores sem alteração em `/effective_limits` e o trace prova a configuração. Para cada limite,
o corpus aceita exatamente N, rejeita N+1 com a razão daquele limite e mantém todas as outras
dimensões estritamente abaixo dos próprios tetos. Um threshold menor, `reject-all`, ou outro eixo
que masque a rejeição falha conformidade.

### 17.2 Invariantes verificáveis

1. versão instalada nunca regride no mesmo stream/epoch;
2. mesmo cursor nunca aceita dois tokens ou dois state digests;
3. patch só aplica sobre base exata e atomicamente;
4. duplicata não altera estado nem freshness;
5. gap/overflow/epoch convergem por snapshot; schema incompatível renegocia outro stream;
6. estado protegido não cruza security generation;
7. fila, replay e retry são limitados;
8. commit idempotente não duplica efeito;
9. mesmo command id com intenção diferente conflita;
10. confirmação de comando e observação da read model permanecem distintas;
11. ausência de evento publicado ainda converge pelo caminho canônico quando não há outbox;
12. atualização passiva não rouba foco nem apaga draft.

### 17.3 Propriedade de convergência

Para qualquer permutação finita de duplicatas, atrasos e reordenação dentro dos limites, se:

- a autoridade para de mudar o stream;
- autorização permanece válida;
- a execução não entrou no terminal `invalid + fatal` por equivocation ou violação de segurança;
- ao menos um snapshot autoritativo do head pode ser obtido; e
- requests continuam eventualmente tendo sucesso,

então o consumidor MUST terminar no mesmo cursor, token e estado do head. A propriedade não
promete disponibilidade durante partição nem preservação de estado após revogação.

## 18. Rollout normativo

Ordem mínima de promoção, expressa sem dependência de produto ou framework:

1. instrumentação, limites e observabilidade de conformidade;
2. read model público em shadow, sem alterar a representação visível do consumidor;
3. snapshot público + ETag, comparado ao fetch canônico;
4. invalidation + conditional GET, mantendo polling com jitter;
5. patch público de baixo risco apenas se refetch continuar gargalo medido;
6. replay somente após journal, retention, slow-consumer e failover testados;
7. projeções pessoais somente após auth, purge, cache, CSP e revogação;
8. command receipts por último, com idempotência e observation fences.

Cada fase MUST ter kill switch independente e rollback ao caminho canônico. Fault injection é
target-scoped: toda unit cobre payload inválido, callback tardio, restore/failover e schema N/N-1;
unit de dados/bootstrap acrescenta cache e bfcache; realtime acrescenta duplicata, reorder, último
evento perdido, gap, overflow e cursor adulterado; protected acrescenta revogação, logout e
expiry; patch/replay acrescenta base, journal e retention; command acrescenta double submit e
resposta perdida. Facet ausente é provada ausente no trace, não simulada. O rollback de leitura
volta ao fetch canônico; command volta ao endpoint e lookup baseline preservando o mesmo
`command_id`, fingerprint e ledger, sem repetir efeito.

O servidor atribui um `rollout_profile` sticky, versionado e não controlável pelo cliente.
Bootstrap, snapshot, cache, stream e repair resolvem o mesmo perfil; ele faz parte da identidade
e da cache key quando muda bytes. Kill switch encerra streams afetados, invalida buffers e força
fetch canônico. Antes do canário, o deployment registra owner, janela de observação e os sete
thresholds quantitativos do manifest: `semantic_divergence_ppm`, `cross_audience_leaks` (sempre
zero), `repair_loop_rate`, `max_resident_bytes`, `reconnect_storm_rate`,
`p95_latency_regression_ms` e `error_rate_regression`.

O mesmo documento fixa `comparison_population`, `latency_metric`, `error_event`,
`minimum_candidate_samples` e `minimum_baseline_samples`; trocar qualquer um reinicia a janela.
Uma amostra abaixo do piso, denominador zero ou telemetria ausente é resultado inconclusivo e não
promove. Na população e janela declaradas:

- `semantic_divergence_ppm = ceil(1_000_000 × comparações shadow não idênticas /
  comparações iniciadas)`; timeout, parse inválido e comparação incompleta contam como
  divergência;
- `cross_audience_leaks` é a contagem inteira de qualquer byte, cache hit, existência ou locator
  observado fora da authority/tenant/principal autorizada; o único orçamento válido é zero;
- `repair_loop_rate` é a fração de operações candidate que excede `max_repair_attempts` ou reabre
  repair para o mesmo head autoritativo sem progresso;
- `max_resident_bytes` é o maior high-water mark agregado definido em § 11, não média;
- `reconnect_storm_rate` é a fração de operações candidate cuja subscription excede
  `max_reconnects_per_minute`; quando não há transporte live, o numerador é comprovadamente zero,
  não omitido;
- `p95_latency_regression_ms` é `max(0, p95(candidate) - p95(baseline))` para o mesmo
  `latency_metric`, população e janela, em milissegundos monotônicos. `p95` é nearest-rank: depois
  de ordenar N amostras crescentes, usa a posição `ceil(0,95 × N)`, começando em 1;
- `error_rate_regression` é `max(0, candidate_errors/candidate_samples -
  baseline_errors/baseline_samples)` para o `error_event`
declarado. Capability ausente produz numerador zero apenas quando o trace prova que a superfície
não existiu; nunca remove o threshold.

O binding testa igualdade e primeiro valor acima do threshold somente para métricas cuja
superfície existe factualmente naquela unit. Quando repair ou transporte live não existe, a prova
daquela unit é numerador zero + trace de ausência; telemetria ausente continua inconclusiva. O
runner não fabrica repair ou reconnect para fazer uma unit snapshot-only ou command-only parecer
mais abrangente. A aritmética completa dos sete comparadores pode ser testada separadamente em
harness puro, mas esse ensaio não substitui a evidência target-scoped.

Taxas e diferenças são comparadas como razões inteiras exatas por multiplicação cruzada contra o
decimal JSON do threshold; implementação não pode ganhar aprovação por arredondamento binário.
Para que o corpus também consiga provar o primeiro valor acima do threshold, o manifest limita
`semantic_divergence_ppm` a 999999; `repair_loop_rate`, `reconnect_storm_rate` e
`error_rate_regression` são menores que 1; e `max_resident_bytes` e
`p95_latency_regression_ms` são no máximo 9007199254740990. O valor imediatamente superior
continua assim representável em I-JSON e no domínio da métrica.

Para unit de dados, o ensaio de rollback MUST manter simultaneamente um cliente N-1 restaurado de
bfcache, um service worker N-1, bytes candidate já presentes no cache e um repair N em voo. Isso
vale também a snapshot-only; invalidation não é pré-requisito para o ensaio. Acionar o kill switch
precisa cancelar a geração candidate, impedir que callback/cache tardio a reinstale, selecionar
endpoint e schema suportados por N-1 e convergir por fetch canônico baseline. Em unit command-only,
o cenário mantém cliente/SW N-1 e callbacks de emissão, submit e receipt em voo, prova que nenhum
byte `no-store` entrou no cache/SW e impede instalação/efeito tardio depois do fence; não fabrica
repair de dados inexistente. Sem o ensaio aplicável e sem owner, janela e thresholds preenchidos
no documento do deployment, a fase permanece NO-GO; esta spec não inventa esses valores pelo
deployment.

## 19. Nome e publicação

"Continuum" colide no mesmo território semântico com
[`flyingrobots/continuum`](https://github.com/flyingrobots/continuum), uma suíte de protocolos de
histórico causal, event sourcing e materialized readings. Esta spec preserva o termo apenas como
codinome para não tomar uma decisão de produto silenciosa.

Antes de publicação externa, o nome MUST passar por busca jurídica/ecossistêmica. O nome técnico
recomendado é **Projection Continuity Profile (PCP)**; alternativas são **Convergent Projection
Exchange (CPEX)** e **Revisioned Projection Delivery (RPD)**. Os `$id` em `example.test` nos
schemas são placeholders não resolvíveis e MUST ser substituídos por URIs persistentes junto com
a decisão de nome; artefatos já publicados nunca mudam sob o mesmo URI.

## 20. Go/no-go atual

Neste parecer, **GO** significa apenas que a fatia pode avançar para planejamento e para o gate de
evidência indicado; não é autorização para escrever código de produto, criar adapter, ativar flag,
fazer rollout ou deploy.

**GO** para instrumentação, shadow read model público, snapshot público condicional e, depois das
provas de auth/cache/race/limites, invalidation + refetch + polling com jitter.

**NO-GO** para patch, replay, projeção pessoal, dependência cross-partition e command receipt no
piloto user-visible atual. Esses itens são capabilities futuras e precisam demonstrar benefício
incremental, não apenas possibilidade técnica.

Questões-gate abertas e o racional completo estão na
[revisão adversarial](../reports/continuum-0.1-adversarial-review-20260927.md). Esta decisão não
autoriza código de produto, adapters ou deploy.

## 21. Referências

- [CloudEvents 1.0.2](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md)
- [CloudEvents JSON Event Format 1.0.2](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/formats/json-format.md)
- [RFC 2119 — Key words for use in RFCs](https://www.rfc-editor.org/rfc/rfc2119)
- [RFC 5789 — PATCH](https://www.rfc-editor.org/rfc/rfc5789)
- [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902)
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396)
- [RFC 8174 — BCP 14](https://www.rfc-editor.org/rfc/rfc8174)
- [RFC 8785 — JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785)
- [RFC 8895 — ALTO Incremental Updates Using SSE](https://www.rfc-editor.org/rfc/rfc8895)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111)
- [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457)
- [WHATWG Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [Mercure protocol](https://mercure.rocks/spec)
- [OData 4.01 Protocol](https://docs.oasis-open.org/odata/odata/v4.01/os/part1-protocol/odata-v4.01-os-part1-protocol.html)
- [Braid-HTTP individual draft -04, expirado](https://datatracker.ietf.org/doc/html/draft-toomim-httpbis-braid-http-04)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
