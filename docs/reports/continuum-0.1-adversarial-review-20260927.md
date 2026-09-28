# Revisão adversarial do Continuum 0.1

**Data:** 2026-09-27\
**Objeto:** protocolo de continuidade descrito na
[WP de SSR/SSE](../plans/WP-PROGRESSIVE-SSR-SSE-CONTINUITY.md)\
**Resultado:** a hipótese de produto permanece útil; o protocolo 0.1 não está pronto para
implementação\
**Recomendação:** **no-go** para patches, replay e commitment frames no piloto; **go** apenas
para medição, read model público em shadow mode e snapshots condicionais/invalidações

---

## 1. Veredito

O texto original identifica corretamente uma dor real: uma projeção composta não precisa
bloquear a interface até que todas as suas partes estejam prontas. Também preserva duas boas
decisões: o servidor continua autoritativo para efeitos de negócio e a leitura antiga não é
apagada apenas porque uma atualização começou.

O salto de estratégia de produto para protocolo distribuído, porém, foi prematuro. A versão 0.1
descreve intenções de convergência, mas não define as propriedades que tornam essa convergência
demonstrável: identidade da sequência, partição, epoch, base de patch, corte de snapshot,
retenção, compactação, reset, atomicidade da publicação e limites de memória. Em alguns pontos,
faz afirmações falsas — especialmente que um JSON Patch seria idempotente.

O diagnóstico adversarial é:

1. **A novidade foi superestimada.** CQRS/materialized views, RFC 8895, Mercure, OData Delta,
   Braid-HTTP, HTTP condicional, CloudEvents e SSE já cobrem quase todos os mecanismos
   isolados.
2. **A unidade de ordenação não existe.** `revision` não diz quem a aloca, em qual partição,
   durante qual geração, nem o que acontece após restore/failover.
3. **A correção depende de hipóteses não escritas.** O desenho presume publicação sem perda,
   replay disponível e snapshot coerente com a assinatura, mas nenhum desses fatos decorre de
   SSE ou de “emitir depois do commit”.
4. **A máquina de estados mistura eixos ortogonais.** Um cliente pode estar simultaneamente
   utilizável, stale, offline, em repair e com vários comandos pendentes.
5. **Privacidade está tratada tarde demais.** Autorizar “antes da aplicação” no cliente não
   protege dados já entregues; autorização, cache e tenant precisam fazer parte da identidade
   e do lado servidor.
6. **A complexidade ainda não foi justificada pela evidência local.** A medição prova que a
   projeção atual é cara. Ela não prova que patches genéricos, replay durável ou dependências
   entre quadros são necessários para capturar o ganho.

A [spec 0.2](../specs/continuum-0.2.md) corrige o contrato no papel. Ela deliberadamente reduz o
piloto recomendado a snapshot público + ETag + invalidação + refetch. Patches e recibos de
comando viram capabilities separadas, não pré-requisitos para otimizar o cardápio.

---

## 2. O que já existe

O Continuum só é defensável como **perfil de padrões existentes**. Não é um novo algoritmo de
consistência, event store, CRDT, protocolo de transporte ou mecanismo de cache.

| Antecedente | O que já fornece | Lacuna que o perfil pode preencher |
|---|---|---|
| [CloudEvents 1.0.2](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md) | Envelope, identidade `source + id`, tipo, subject, schema e binding | Semântica de partição/epoch, instalação de estado, freshness, repair e commit |
| [RFC 8895](https://datatracker.ietf.org/doc/html/rfc8895) | SSE com full replacement, JSON Patch/Merge Patch, capabilities, dependências, recovery, keepalive e limites | Perfil genérico fora de ALTO, cursor semântico, freshness, privacidade e recibo de comando |
| [RFC 6902](https://datatracker.ietf.org/doc/html/rfc6902) / [RFC 7396](https://datatracker.ietf.org/doc/html/rfc7396) | Formatos de patch JSON | Base/result version, dedupe, replay, autorização e convergência |
| [HTTP Semantics](https://datatracker.ietf.org/doc/html/rfc9110) / [Caching](https://datatracker.ietf.org/doc/html/rfc9111) | ETag, condicionais, cache, precondições e status | Continuidade entre snapshot, fluxo e repair |
| [WHATWG SSE](https://html.spec.whatwg.org/multipage/server-sent-events.html) | Fluxo servidor→cliente, reconexão e `Last-Event-ID` | Journal, ACK de aplicação, retenção, gap, schema e backpressure |
| [Mercure](https://mercure.rocks/spec) | Tópicos SSE, updates completos/parciais, replay e refetch após perda | Estado formal do consumidor, cursor de estado, freshness e commit |
| [OData Delta 4.01](https://docs.oasis-open.org/odata/odata/v4.01/os/part1-protocol/odata-v4.01-os-part1-protocol.html) | Token opaco ligado à consulta, páginas ordenadas, novo delta link e `410 Gone` para reset | Push, UI state, cache policy e comando |
| [Braid-HTTP draft](https://datatracker.ietf.org/doc/html/draft-toomim-httpbis-braid-http) | Versions, parents, snapshots, patches e subscriptions | É mais amplo e multiwriter; o caso de projeção autoritativa não precisa de DAG/CRDT |
| [GraphQL `@defer`/`@stream` draft](https://github.com/graphql/graphql-wg/blob/main/rfcs/DeferStream.md) | Entrega incremental curta de uma única execução | Atualização contínua, reconexão, replay e repair |
| [CQRS](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs) / [Materialized View](https://learn.microsoft.com/en-us/azure/architecture/patterns/materialized-view) | Separação read/write e view descartável otimizada | Contrato de instalação e reparação da view no consumidor |
| [RSocket](https://github.com/rsocket/rsocket/blob/master/Protocol.md) / [gRPC flow control](https://grpc.io/docs/guides/flow-control/) | Crédito/flow control, cancelamento e, no RSocket, resume | Semântica da projeção e política de cache/freshness |
| [CRDTs](https://inria.hal.science/inria-00555588/document) | Convergência multiwriter sob propriedades algébricas específicas | Não se aplica a patch arbitrário ou a comando autoritativo |

O antecedente mais embaraçoso para uma alegação de novidade é a RFC 8895. Ela discute inclusive
o custo de manter replay para `Last-Event-ID`, o risco de memória com eventos SSE grandes, a
ausência de flow control e duas estratégias para dependências. A 0.1 precisava citá-la.

### O delta legítimo

O que resta como contribuição coerente é uma composição pequena e verificável:

- identidade imutável de uma projeção autorizada;
- cursor semântico `(stream, epoch, sequence)` distinto do cursor de transporte;
- transição `base → target` aplicada atomicamente;
- gap explícito e repair obrigatório, inclusive após compactação;
- freshness que não usa relógio de parede para ordenar estado;
- políticas normativas de cache/privacidade;
- recibo autoritativo de comando, separado da atualização visual;
- estado do consumidor e limites de backpressure;
- vetores de conformidade comuns a qualquer binding.

Isso é um **perfil de continuidade de projeções**, não uma invenção das suas peças.

---

## 3. Falhas que quebram correção

### 3.1 `revision` sem stream, epoch ou alocador

O envelope 0.1 traz `projection_key`, `snapshot_id`, `revision` e `frame`, mas deixa para uma
pergunta futura se a revisão é global, por loja, canal ou SKU. Essa escolha é parte do contrato,
não detalhe de implementação.

Sem uma unidade formal:

- uma revisão global em feed filtrado cria falsos gaps;
- revisão por item não oferece corte consistente para uma lista;
- dois escritores podem emitir a mesma revisão;
- restore ou failover pode fazer o contador regredir;
- `depends_on` não é comparável;
- um único `Last-Event-ID` não representa várias sequências independentes.

A 0.2 separa cinco identidades que a 0.1 confundia:

| Identidade | Função | Não é |
|---|---|---|
| CloudEvents `source + id` | deduplicar a mensagem | versão do estado |
| `stream_id` | identificar uma projeção/partição/escopo autorizado | tenant enviado pelo cliente |
| `epoch + sequence` | ordenar transições dentro do stream | relógio ou ETag |
| `state_token` / ETag | validar bytes/representação exata | número comparável |
| cursor do binding | retomar entrega quando o transporte suporta | prova de aplicação |

### 3.2 JSON Patch não é idempotente

A RFC 6902 aplica operações em ordem. Repetir `add` em `/-` anexa outra vez; repetir `remove`
pode falhar; `move` depende da base; índices de array mudam com cada operação. A própria
[RFC 5789](https://datatracker.ietf.org/doc/html/rfc5789) explica que PATCH não é idempotente por
padrão e recomenda precondição forte quando o formato depende de uma base.

Logo, o documento de patch não é a unidade idempotente. A **transição** é duplicate-safe:

```text
stream + epoch + base(sequence, state_token)
  -- patch atômico -->
stream + epoch + target(sequence, state_token)
```

O consumidor só aplica se seu estado coincide exatamente com `base`. Se já está em `target`,
ignora a duplicata. Em qualquer outra relação, repara. Falha na operação ou na validação do
resultado descarta a cópia inteira; nunca deixa alteração parcial visível.

### 3.3 O “gap SSE” descrito não é o failure mode principal

Dentro de uma única resposta SSE/TCP, `n+2` não ultrapassa `n+1`. Reordenação denuncia múltiplos
produtores, merge de partições, replay incorreto ou bug. Os riscos normais são outros:

- o banco commita e o processo morre antes de publicar;
- a retenção expira antes da reconexão;
- o navegador atualiza `Last-Event-ID` antes de o handler aplicar a mensagem;
- o emissor reinicia em outra geração;
- o stream multiplexa partições que não cabem num cursor escalar;
- um proxy fecha ou bufferiza a conexão.

O WHATWG define `Last-Event-ID` como string opaca de reconexão. Não é ACK do código da aplicação.
Mercure também alerta que eventos podem sair da retenção e manda refazer o recurso original.

### 3.4 Snapshot e assinatura têm uma race

O fluxo “fetch snapshot; depois conectar stream” pode perder uma mudança entre as duas ações. O
fluxo inverso pode acumular eventos indefinidamente enquanto o snapshot demora. Repair também
pode voltar de uma réplica atrasada e regredir um estado que avançou enquanto a request estava em
voo.

Todo binding live precisa provar uma destas estratégias:

1. snapshot retorna estado e cursor de replay no mesmo corte, e a assinatura começa estritamente
   depois desse cursor; ou
2. assinatura começa primeiro, tem buffer estritamente limitado, snapshot declara seu corte e o
   cliente descarta o que já está coberto.

Overflow, cursor expirado ou epoch diferente resultam em `reset_required` + snapshot completo.

### 3.5 “Após commit” ainda é dual write

`transaction.on_commit()` garante que um callback não rode antes da transação. Não garante que
ele rode se o processo morrer após o commit nem que outro worker veja a projeção antes do evento.
Para prometer ausência de perda, são necessários transactional outbox/CDC ou mecanismo
equivalente que persista efeito, fence e intenção de publicação atomicamente.

O read model também precisa de compare-and-set pelo watermark da fonte. Dois rebuilds terminando
fora de ordem não podem adotar “o último a terminar”.

### 3.6 Compactação não pode ficar aberta

Um journal finito deve declarar retention floor, tamanho/tempo máximo, política de tombstones,
limite da cadeia de deltas e resposta a cursor expirado. OData fornece precedente simples: token
inválido ou expirado recebe `410 Gone` e referência para refetch integral. Retry infinito não é
repair.

Salto numérico também não prova perda. Coalescing, filtragem e compactação podem pular posições.
Um patch declara sua base; uma invalidação provoca refetch; o consumidor não inventa semântica a
partir de `n + 1`.

### 3.7 `depends_on` não cria um corte consistente

Uma revisão mínima arbitrária pode ser cíclica, pertencer a stream não autorizado, desaparecer na
compactação ou mudar de epoch. Mesmo satisfeita, “A ≥ 7 e B ≥ 9” não prova que A e B formam um
estado que existiu junto.

A 0.2 remove dependências arbitrárias do núcleo. Quando várias partes exigem coerência atômica,
o produtor deve colocá-las no mesmo stream ou entregar um bundle de snapshots obtido no mesmo
corte. Consistência causal/multi-partição fica fora do perfil inicial.

---

## 4. Falhas de concorrência e compromisso

### 4.1 `commitment frame` confunde aceite, commit e observação

`accepted`, `committed_revision` e `authoritative_patch` não dizem:

- se “accepted” é terminal;
- qual transação persistiu a chave idempotente;
- a qual partição/epoch pertence a revisão;
- por quanto tempo um retry é seguro;
- o que ocorre se a resposta se perder;
- quando o read model refletirá o efeito.

Um recibo correto exige chave no escopo `(authority, tenant, principal, operation, command_id)`,
fingerprint da request e persistência do efeito + resultado na mesma transação. Mesmo ID e mesmo
fingerprint devolvem o recibo original; mesmo ID e fingerprint diferente é conflito. Após timeout
ambíguo, o estado é `unknown` e o cliente consulta o recibo — não deduz sucesso de SSE.

### 4.2 Read-your-writes precisa de fence

Commit no write model e visibilidade no read model são fatos distintos. Um recibo pode carregar
zero ou mais observation fences por stream. O cliente só afirma que a projeção observou o comando
quando alcança esses fences ou quando um fetch canônico retorna um estado que os cobre. Sem fence,
o recibo confirma o efeito, mas não a atualização da view.

### 4.3 Concorrência continua no domínio

Continuum não serializa a última unidade, não resolve lost update e não substitui transação,
lock, constraint ou `If-Match`. Ele apenas transporta o resultado autoritativo. CRDT também não é
atalho: patches arbitrários não possuem as propriedades algébricas necessárias à convergência
multiwriter.

---

## 5. Estado, freshness e offline

A máquina `empty → usable → converging/repairing/committing/unavailable` mistura fatos que podem
coexistir. O modelo precisa de regiões independentes:

```text
data       absent | fresh | stale_usable | stale_blocked | invalid
sync       idle | connecting | live | repairing | backoff | reset_required | fatal
commands   command_id -> pending | accepted | committed | adjusted | rejected | unknown
security   generation atual do principal/tenant/audiência
```

“Utilizável nunca volta a vazio” é preferência de UX, não invariante de segurança. Logout, troca
de tenant/principal, revogação, hard expiry e corrupção devem apagar ou bloquear estado protegido.

`generated_at` serve a observabilidade, não à ordem nem à validade. Relógios divergem. Freshness
deve usar durações conservadoras descontadas da idade informada pelo servidor/cache e relógio
monotônico local. Heartbeat prova somente que bytes chegaram; não renova freshness do estado.

Offline não autoriza fila de comandos. A 0.2 permite reapresentar snapshot dentro da política do
domínio, mas uma capability separada seria necessária para journal local, conflito e replay de
escrita.

---

## 6. Backpressure e crescimento de memória

SSE não oferece ACK de aplicação nem demanda `request(n)`. O TCP limita bytes na conexão, não a
fila de tasks JavaScript, renders, buffers por stream ou cache do cliente. Uma aba suspensa pode
ficar muito atrás.

Uma implementação segura precisa de limites explícitos para:

- bytes por mensagem e por conexão;
- operações, profundidade e tamanho de JSON Pointer;
- streams por principal/tenant/IP e partições por stream;
- fila cliente/servidor, cache, dedupe e comandos pendentes;
- repairs concorrentes e tentativas por janela;
- journal e retention floor.

Sob pressão, invalidações substituíveis são coalescidas por stream. Patches que não cabem no
limite viram gap/reset; nunca crescem sem limite. A RFC 8895 já registra tanto a ausência de flow
control quanto os riscos de DoS e memória.

---

## 7. Segurança, privacidade e cache

### P0 — autorização deve ocorrer antes da entrega

Cada snapshot, repair, assinatura, reconexão e consulta de recibo deve ser autorizado no servidor.
Streams longos precisam de política de expiração/reauth e encerramento após revogação. O cliente
não é fronteira de enforcement.

O `stream_id` deve resolver no servidor para authority/environment, tenant, audience/principal,
projection, parâmetros, partition e schema major. Nenhum desses eixos pode ser escolhido pelo
cliente sem validação. IDs e metadados CloudEvents ficam em claro em muitos intermediários: não
podem carregar PII, segredo ou capability.

### P0 — `repair_url` arbitrária é um confused deputy

Uma URL recebida no evento pode apontar o consumidor/BFF para outro origin, metadata service ou
rota com credenciais. O binding deve resolver repair por registry/configuração local. Se houver
link, ele é relativo ou allowlisted, sem token de acesso em query, e redirects são revalidados.

### Cache correto é parte do contrato

- Público só pode ser cacheável em endpoint sem credencial, sem `Set-Cookie` e com bytes idênticos
  para toda a audiência daquela cache key.
- Tenant/site/canal/locale/moeda/schema/coorte que mudem bytes entram na URI/chave e, quando
  apropriado, em `Vary`.
- `public` permite inclusive casos que normalmente não seriam cacheáveis; deve ser opt-in.
- `private` impede shared cache, mas ainda permite cache do browser e não fornece sigilo.
- Pessoal, commit, erro de autenticação e repair protegido usam `private, no-store`.
- SSE usa `no-store, no-transform`; streams protegidos também usam `private`.
- Autorização acontece antes de lookup condicional e antes de devolver `304`.
- Service worker e armazenamento persistente de dados privados são proibidos por padrão.

O canário também participa da cache key. Um cookie de feature flag combinado com resposta
`public` contamina cohorts.

### Patches são entrada hostil

Validar envelope, schema, tamanho e limites antes da aplicação; aplicar numa cópia; validar o
resultado; então trocar atomicamente. Implementações JavaScript precisam bloquear paths perigosos
como `__proto__`, `prototype` e `constructor`. Payload é dado, nunca HTML/script executável.

---

## 8. Evolução, rollback e observabilidade

`specversion` é a versão de CloudEvents, não do Continuum. O payload precisa de versão de
protocolo e `dataschema` imutável. Patch só atravessa estados com o mesmo schema e epoch. Mudança
breaking, canonicalização incompatível ou restauração do sequenciador gera novo epoch + snapshot.

Rollout blue/green precisa manter N-1 por mais tempo que abas antigas, bfcache e service worker.
Endpoint/media type deve ser versionado; workers mistos não podem publicar schemas diferentes no
mesmo epoch.

Métricas mínimas:

- head/applied watermark e lag por stream;
- backlog/idade do outbox e do materializador;
- reconexão por causa, cursor aceito/rejeitado e retention reset;
- gap, regressão, duplicata, equivocation e erro de schema;
- repair por causa/resultado/bytes/latência/loop;
- ocupação/overflow/coalescing de buffer;
- idade/freshness e uso além do hard limit;
- idempotency replay/conflict/unknown;
- commit → fence observável;
- divergência amostral por state token/digest;
- falhas de autorização sem payload sensível.

Tenant, principal, resource id e command id não viram labels de alta cardinalidade. Trace Context
W3C pode correlacionar requests, mas `traceparent`/`tracestate` não carregam PII.

---

## 9. Acessibilidade e falhas de cliente

O protocolo não deve controlar o estado visual. A integração de UI, porém, precisa obedecer:

- atualização passiva não move foco nem scroll;
- `aria-busy` cobre apenas um lote finito, nunca a vida inteira do stream;
- anúncio `polite` é coalescido e reservado a mudança humanamente relevante;
- erro de comando usa o padrão de erro/alerta adequado, não apenas cor;
- stale/unavailable tem texto discernível;
- drafts e seleção local sobrevivem a refetch, salvo conflito explícito;
- redução de movimento é respeitada;
- auto-update não essencial oferece pausa/controle quando necessário.

A spec não altera nem aprova o loading visual da WP.

---

## 10. Colisão do nome “Continuum”

Existe uma colisão séria, não apenas lexical: o projeto aberto
[`flyingrobots/continuum`](https://github.com/flyingrobots/continuum) se apresenta como uma suíte
de protocolos para histórico causal, event sourcing, witnesses e materialized readings — o mesmo
território semântico em que esta proposta tentaria se posicionar. Há ainda produtos ativos de
agentes e dados com o mesmo nome.

Esta revisão **não renomeia silenciosamente** o trabalho. “Continuum” permanece codinome na 0.2,
mas não deve ser nome público sem busca jurídica/ecossistêmica. Alternativas descritivas:

1. **Projection Continuity Profile (PCP)** — deixa claro que é perfil, não transporte;
2. **Convergent Projection Exchange (CPEX)** — enfatiza troca e convergência;
3. **Revisioned Projection Delivery (RPD)** — enfatiza a propriedade técnica central.

Recomendação: usar **Projection Continuity Profile** em eventual publicação e manter “Continuum”
apenas como codinome até decisão explícita.

---

## 11. Go/no-go para o Shopman

Neste relatório, **GO** é parecer arquitetural para planejar e fechar o gate de evidência da
fatia; não autoriza código de produto, adapter, feature flag, rollout ou deploy.

### Agora

| Fatia | Decisão | Razão |
|---|---|---|
| Server-Timing, queries, bytes, cache hit/miss | **GO** | observação reversível, sem novo contrato de estado |
| Read model estrutural público em shadow mode | **GO** | testa equivalência e remove recomputação sem alterar UX |
| Snapshot público + ETag/conditional GET | **GO depois do shadow** | padrão maduro e rollback simples |
| SSE mínimo como invalidação + refetch | **GO condicional** | preserva ADR-016; exige auth/cache/limites e race fechada |
| JSON Patch/Merge Patch | **NO-GO** | ganho não demonstrado; base, journal e backpressure ainda sem prova |
| Replay por `Last-Event-ID` | **NO-GO** | exige journal/retention e cursor multiplexado comprovados |
| Partes pessoais no mesmo contrato/cache | **NO-GO** | threat model e lifecycle de auth ainda não fechados |
| Commitment frames | **NO-GO** | deve evoluir separadamente como recibo idempotente |
| Dependências cross-partition | **NO-GO** | não há corte consistente demonstrado |

O primeiro piloto honesto é: **snapshot público versionado + invalidação + conditional GET +
polling com jitter**. Ele captura materialized view, payload normalizado e navegação reaproveitada
sem introduzir um journal de patches. Patches só entram se a medição mostrar que o refetch,
depois dessas otimizações, ainda é o gargalo.

### Perguntas-gate antes do piloto user-visible

1. Qual tuple exata define cada stream e quem aloca `epoch/sequence`?
2. Como snapshot + assinatura formam um corte sem janela perdida?
3. Qual mecanismo elimina o dual write entre banco, read model e notificação?
4. Qual é a matriz campo → audience → cache → persistência?
5. Qual SLA de revogação fecha stream e purga memória em logout/troca de principal?
6. Qual retention floor, resposta a compactação e limite máximo de replay?
7. Quais limites de bytes, ops, buffers, conexões e repairs?
8. Qual política offline e hard expiry por projeção?
9. Como N-1, blue/green, bfcache e rollback preservam epoch/schema?
10. Em qual chave entra a feature flag para não envenenar cache público?
11. Quais métricas/SLOs provam zero leak, zero regressão e repair sem loop?
12. Qual ganho adicional mensurado justificaria patch em vez de invalidação/refetch?
13. Quais estados merecem anúncio acessível e como o usuário pausa update não essencial?
14. O nome público será trocado antes de qualquer publicação externa?

Sem respostas e provas para 1–11, o piloto completo continua **no-go**. Com o recorte simples e
shadow equivalence, a exploração arquitetural pode avançar sem comprometer o produto.
