# WP — SSR/SSE de Continuidade Semântica

> Transformar a navegação do Shopman de uma resposta monolítica que precisa “ficar pronta”
> em uma convergência contínua, revisionada e reparável — sem abrir mão de o servidor ser a
> única autoridade sobre preço, disponibilidade, carrinho e checkout.

**Status**: revisão adversarial concluída; implementação de protocolo ainda não autorizada\
**Aberto em**: 2026-09-27\
**Revisado em**: 2026-09-28 — contrato 0.2 e decisão go/no-go\
**Superfície piloto**: storefront / cardápio\
**Expansão candidata**: demais rotas do storefront e projeções de leitura do backstage\
**Nome de trabalho**: **SSR-CS — SSR de Continuidade Semântica**\
**Decisão visual associada**: prévia em revisão; não transformar em código de produto antes do aceite

**Documentos resultantes**:

- [spec Continuum 0.2](../specs/continuum-0.2.md);
- [revisão adversarial da 0.1](../reports/continuum-0.1-adversarial-review-20260927.md);
- [schemas, exemplos e vetores neutros](../../contracts/continuum/v0.2/README.md).

---

## 0. Decisão após a revisão adversarial

A tese de produto foi preservada; o protocolo 0.1 foi substituído. A referência normativa agora
é a [spec 0.2](../specs/continuum-0.2.md). Em caso de conflito entre esta WP e a spec, a spec rege
o wire e esta WP rege a sequência de aprendizado do Shopman.

### Decisões preservadas

- o servidor e o banco continuam autoritativos para preço, disponibilidade, reserva e dinheiro;
- SSR útil, read model materializada, payload normalizado e ETag permanecem a baseline;
- a tela não apaga uma leitura ainda utilizável só porque começou refresh;
- SSE começa como invalidação sobre fetch canônico; polling com jitter continua fallback e,
  enquanto não houver outbox durável, também é caminho de reconciliação;
- estrutura, volatilidade e personalização continuam ritmos úteis de decomposição, mas não são
  tipos universais obrigatórios do protocolo;
- shadow equivalence, fault injection, feature flag e rollback antecedem qualquer promoção;
- a decisão visual e o limiar abaixo de 200 ms permanecem fora desta revisão.

### Decisões substituídas na 0.2

| 0.1 | Decisão 0.2 |
|---|---|
| `revision` sem escopo | versão completa por stream: cursor `(epoch, sequence)` + `state_token` forte + `state_digest` recomputável |
| `id`/`Last-Event-ID` como retomada semântica | cursor de transporte opaco, separado do cursor de estado |
| patch “idempotente” | patch não é idempotente; aplica uma vez, somente sobre base exata e atomicamente |
| `depends_on` genérico | removido; corte exato exige uma única projeção/stream na 0.2 |
| `repair_url` no evento | removido; endpoint vem de binding/registry confiável e allowlisted |
| `generated_at + max_age_ms` | tempo civil de evento só para telemetria; freshness usa elapsed conservador, age durável e hard expiry |
| máquina `empty → usable → …` | eixos independentes de dados, transporte, reconciliação, comandos e security generation |
| auth “antes da aplicação” | autorização server-side antes de snapshot, cache/304, subscribe, replay, repair e commit |
| callback pós-commit como continuidade | outbox/CDC para no-loss; sem isso, fetch/poll canônico permanece obrigatório |
| commitment frame misturado à projeção | command receipt idempotente e consultável, com observation fences opcionais |

### Decisão de avanço

Aqui, **GO** é parecer arquitetural para planejar e executar o gate de evidência correspondente;
não autoriza código de produto, adapter, feature flag, rollout ou deploy.

**GO** para WP-CS-0, shadow read model público e, depois de equivalência, snapshot público + ETag.
**GO condicional** para invalidate + conditional GET + polling com jitter após fechar
auth/cache/race/limites. **NO-GO** no piloto atual para patches, replay, projeções pessoais,
dependências cross-partition e command receipts.

O primeiro piloto honesto é o perfil conservador da própria baseline. Capabilities mais
complexas só avançam se medições demonstrarem benefício adicional e os gates da spec forem
provados.

## 1. A tese

O problema não é “SSR contra SPA”, “SSE contra polling”, “Nuxt contra Django” ou “Python
é lento”. O problema é pedir que todas as verdades de uma tela atravessem o mesmo caminho
crítico e cheguem juntas antes de permitir que o usuário prossiga.

O SSR-CS troca a unidade de entrega:

- de **página íntegra ou espera**;
- para **quadros semânticos independentes que convergem para a mesma verdade**.

O primeiro quadro utilizável aparece imediatamente. As partes mais voláteis chegam depois,
por resposta curta ou SSE, sem reiniciar a tela. Se um quadro atrasa ou se perde, os demais
continuam válidos; uma reparação em segundo plano fecha a lacuna. No momento de comprometer
estoque ou dinheiro, o comando no servidor continua sendo a autoridade final.

Em uma frase:

> **A leitura pode ser progressiva; o compromisso nunca é especulativo.**

Esta é uma hipótese de arquitetura a provar no Shopman, não uma alegação prematura de
invenção universal.

---

## 2. A analogia com streaming — com precisão histórica

A intuição é boa: áudio não precisa esperar o arquivo inteiro; ele precisa manter continuidade
com buffer, priorização e recuperação. Mas a versão pública e verificável da história do Spotify
é mais precisa do que “aceitar pacotes corrompidos”. O Spotify documenta áudio dividido em
chunks de aproximadamente 512 kB, solicitado por HTTP range requests e transportado por TCP;
o trabalho com BBR atacou latência e stutter melhorando o controle de congestionamento. A
documentação do eSDK também descreve buffering para atravessar interrupções temporárias.

QUIC/HTTP/3 fornece a analogia de transporte mais próxima da nossa proposta: fluxos
independentes evitam que a perda em um deles bloqueie todos os demais. Ainda há integridade;
o ganho é deixar de impor uma fila única a dados que podem avançar separadamente.

Aplicação ao Shopman:

- não tolerar “verdade corrompida”;
- tolerar que **verdades independentes cheguem em momentos diferentes**;
- continuar usando o último quadro autoritativo enquanto a lacuna é reparada;
- nunca deixar uma lacuna de leitura autorizar uma venda ou reserva inválida.

---

## 3. Evidência local que motivou a WP

Medições exploratórias em 2026-09-27, antes desta WP:

| Caminho | Ordem de grandeza observada |
|---|---:|
| site/configuração | ~0,95 s TTFB |
| carrinho | ~0,34–0,54 s |
| detalhe de produto | ~2,45 s |
| cardápio, API Django | ~2,72–3,06 s |
| home | ~2,91–2,95 s |
| cardápio via BFF, amostra | ~3,60 s |
| payload do cardápio | ~137,6 kB sem compressão |

O teste focado do catálogo mediu **48 queries em estado estável para 16 produtos**. Um N+1
maior já foi removido, mas permaneceu um custo fixo alto. O BFF não apareceu como o principal
vilão; a projeção Django e o contrato agregador dominam o caminho.

Também já existe infraestrutura aproveitável:

- emissores pós-commit para `stock-web` e `stock-catalog`;
- invalidação de `availability:{sku}:{channel}`;
- payloads SSE mínimos com SKU e estado;
- BFF de SSE e experiência anterior de `EventSource` no acompanhamento de pedidos;
- Redis de produção e projeções canônicas no Django.

A oportunidade é arquitetural: parar de recalcular e retransmitir o mundo para cada clique.

---

## 4. Estratégia baseline preservada — não substituir nem apagar

Esta é a estratégia anterior, registrada como rota segura à qual podemos voltar integralmente:

1. **Base pública, versionada e cacheável** para nomes, fotos, coleções, estrutura e, onde
   permitido, preço-base. Redis/ETag e `stale-while-revalidate` evitam reconstrução repetida.
2. **Overlay dinâmico e de sessão compacto, por SKU** para disponibilidade, pausas, preço
   contextual, favoritos, holds próprios e carrinho.
3. **Assinar o `stock-web` já existente**. Um evento dispara busca do fragmento canônico ou
   aplicação de delta mínimo, em vez de recarregar o catálogo completo.
4. **Servidor continua fonte da verdade**. Adicionar ao carrinho, reservar e concluir checkout
   revalidam transacionalmente, incluindo holds.
5. **Navegação interna usa estado hidratado** e não bloqueia em uma projeção SSR completa.
   SSR permanece para a primeira entrada, SEO e recuperação.
6. **Normalizar o payload**: produtos aparecem uma vez; seções e coleções referenciam SKUs.
7. **Instrumentar o caminho** com `Server-Timing`, orçamento de queries e orçamento de payload.
8. **Prefetch de rota, cache em memória e read model** com revisões monotônicas; polling é o
   fallback quando SSE não estiver disponível.

Princípio preservado:

> Ser a fonte da verdade não obriga o servidor a recomputar toda a verdade sincronicamente em
> cada clique.

### 4.1 Hipóteses de ganho além da baseline

A baseline é uma excelente otimização para o cardápio. O SSR-CS é uma arquitetura para qualquer
projeção que combine dados com ritmos, criticidades e donos diferentes. A tabela registra
hipóteses do desenho; não afirma que toda capability já foi justificada ou aprovada.

| Dimensão | Baseline | SSR-CS | Benefício adicional |
|---|---|---|---|
| Unidade de projeto | catálogo + overlay | projeção composta por quadros semânticos | aplica-se fora do catálogo |
| Atualização | invalidação/refetch específico | snapshot, invalidate, gap e repair; patch opcional | convergência demonstrável |
| Ordenação | revisão recomendada | stream + epoch + sequence + `state_token` + `state_digest`; sem dependência genérica | eventos atrasados não corrompem a UI |
| Falha parcial | fallback por polling | estado formal de continuidade e reparação | uma parte lenta não congela as demais |
| Escrita | revalidação no servidor | receipt separado, idempotente e consultável | resultado explícito sem inferir sucesso da UI |
| Cache | políticas por endpoint | identidade e freshness por stream autorizado | menos invalidação ampla sem misturar audiências |
| UX | navegação com estado hidratado | regra “utilizável nunca volta a vazio” | elimina flicker e regressão durante refresh |
| Portabilidade | desenho Shopman/Nuxt/Django | perfil de padrões independente de framework | pode virar contrato reutilizável se dois adapters o provarem |
| Testabilidade | testes de endpoints e SSE | suíte de conformidade com perda, duplicação e reordenação | robustez demonstrável |

Em resumo, a baseline reduz latência. O SSR-CS também **limita o raio de bloqueio**, formaliza
como o sistema se recupera e separa a consistência necessária para ler da consistência necessária
para comprometer uma ação.

---

## 5. O salto além da baseline: um protocolo de continuidade

A baseline divide catálogo e overlay. O SSR-CS torna essa divisão um **protocolo explícito,
genérico e verificável**, aplicável a qualquer projeção Shopman.

### 5.1 Quadros semânticos

Cada tela é composta por quatro planos independentes:

| Quadro | Conteúdo | Cache | Pode chegar depois? |
|---|---|---|---|
| **Estrutural** | rota, layout, coleções, nomes, fotos, ordem | público, versionado | não na primeira visita; sim na navegação interna se já houver snapshot |
| **Volátil** | disponibilidade, pausas, preço contextual, capacidade | curto, por canal | sim; atualiza sem bloquear |
| **Pessoal** | carrinho, favoritos, holds próprios, identidade | privado, por sessão | sim quando não define acesso à rota |
| **Compromisso** | resultado autoritativo de add/reserva/checkout | não compartilhado | não; o comando só termina com confirmação ou erro útil |

Os quatro planos acima são uma decomposição de produto, não o envelope do wire. O envelope 0.1
foi substituído pelo CloudEvent normativo da
[spec 0.2 § 6](../specs/continuum-0.2.md#6-envelope-cloudevents):

| Conceito antigo | Contrato vigente |
|---|---|
| `projection_key` | `stream.id` opaco, resolvido no servidor para authority/tenant/audience/projection/partition/schema |
| `snapshot_id` + `revision` | `target.cursor {epoch, sequence}` + `state_token` + `state_digest` |
| `frame` | `data.kind`: snapshot, patch, invalidate, gap ou commit receipt |
| `generated_at` | CloudEvents `time`, somente telemetria |
| `max_age_ms` | `freshness {fresh_for_ms, stale_if_error_ms, age_ms}` + elapsed conservador; sleep/failover nunca reinicia prazo |
| `depends_on` | removido; consistência exata exige uma única projeção/stream na 0.2 |
| `repair_url` | removido; repair é resolvido por configuração confiável do binding |
| `payload` | `state`, `patch` ou `command`, conforme o kind |

CloudEvents dá envelope e identidade de mensagem, não ordenação, replay, autorização ou
convergência. Essas propriedades são do perfil e precisam ser testadas separadamente.

### 5.2 Navegação como sessão de convergência

```text
intenção do usuário
  ├─ quadro local conhecido → troca de rota e estrutura imediatamente
  ├─ prefetch Nuxt → código + snapshot estrutural antes do clique quando houver intenção
  ├─ fetch curto → quadro volátil/pessoal atual
  ├─ SSE → revisões posteriores
  └─ lacuna de revisão → repair em segundo plano, sem apagar a tela
```

Não se espera uma resposta monolítica. A tela nasce de um snapshot íntegro conhecido e converge
por substituições atômicas de quadro.

### 5.3 Semântica de “soluço” segura

O equivalente ao soluço do streaming **não é exibir dado parcialmente escrito**. É uma destas
situações controladas:

- uma disponibilidade antiga permanece por alguns milissegundos enquanto a nova chega;
- uma atualização SSE chega fora de ordem; salto de sequence sozinho não prova lacuna, mas uma
  base de patch que não corresponde ao estado local ou um head de invalidation à frente dispara
  repair autoritativo;
- a foto de baixa resolução aparece antes da versão final;
- a coleção abre usando o snapshot já hidratado enquanto o servidor confirma o overlay;
- um badge secundário chega depois sem bloquear o produto.

O usuário comum não vê um recarregamento, skeleton ou salto estrutural. Em conflito real, recebe
uma reconciliação humana e explícita; nunca um ajuste silencioso de preço ou quantidade.

### 5.4 Deadline, não atraso artificial

Cada quadro tem um orçamento, não um temporizador de loading:

- se já existe quadro seguro, apresentar agora e atualizar em fundo;
- se não existe quadro seguro, usar o estado de espera de tela inteira;
- se a ação compromete estoque/dinheiro, aguardar a resposta autoritativa;
- eventos SSE passivos jamais acionam bloqueio de tela inteira.

**Gate de produto**: o limiar de exibição para respostas abaixo de 200 ms não está decidido.
Qualquer proposta nessa faixa deve voltar para decisão conjunta antes de ser implementada.

### 5.5 Núcleo portátil: protocolo Continuum

O mecanismo não deve nascer como uma biblioteca de SSR. SSR é apenas uma forma de transportar o
primeiro snapshot; SSE é apenas uma forma de transportar revisões. O núcleo portátil, com nome de
trabalho **Continuum**, trata de **projeções convergentes**.

Ele se divide em cinco camadas:

1. **Modelo** — stream autorizado, partição, epoch, sequence, state token, state digest, snapshot,
   freshness e payload.
2. **Semântica** — aplicar, ignorar regressão, detectar lacuna, reparar e comprometer.
3. **Transporte** — SSR payload, HTTP, SSE, WebSocket, fila, sincronização móvel ou arquivo.
4. **Política** — o que pode envelhecer, o que pode ser público e o que exige confirmação forte.
5. **Adaptadores** — Django/Nuxt primeiro; depois qualquer servidor e cliente.

Vocabulário mínimo de mensagens:

```text
snapshot    estado íntegro de uma ou mais partes
patch       mudança não idempotente aplicada uma vez sobre base exata
invalidate  aviso de que uma parte precisa ser buscada novamente
gap         declaração de que replay incremental seguro não está disponível
commit      recibo autoritativo, durável e consultável de um comando
heartbeat   saúde/transporte; não altera projeção
```

Repair é uma operação que responde snapshot, cadeia exata, `304`, gap/reset ou Problem Details;
não é um kind obrigatório e não aceita URL arbitrária vinda do evento.

O contrato não conhece produto, SKU, carrinho, HTML, componente Vue, ORM ou banco. Domínios
definem apenas as chaves, partes, políticas e payloads.

Continuum deve ser um **perfil de padrões existentes**, não uma reinvenção deles:

- envelope CloudEvents 1.0 completo (`specversion`, `id`, `source`, `type`, `subject`, versão e
  schema);
- patch JSON expresso por RFC 6902 ou RFC 7396 somente quando patch for comprovadamente mais
  econômico que substituir o quadro;
- snapshot HTTP identificado por ETag e validado condicionalmente;
- em SSE, `id`/`Last-Event-ID` é cursor opaco de entrega e não revisão de estado;
- transporte pode mudar sem alterar as regras de revisão, frescor, repair e commit.

### 5.6 Estado formal do consumidor

O enum único da 0.1 foi substituído por eixos independentes:

```text
data:     absent | fresh | stale_usable | stale_blocked | invalid
transport: idle | connecting | live | backoff | closed
reconcile: idle | repairing | reset_required | fatal
command:  command_id -> pending | accepted | committed | adjusted | rejected | indeterminate | unknown | invalid
security: generation-id + authorization-fence + lease-deadline
```

Um cliente pode estar simultaneamente `stale_usable + transport[live] +
reconcile[repairing] + command[pending]`. O estado visual deriva desses eixos, mas não faz parte
do wire.

Invariantes do núcleo:

- uma projeção ainda autorizada e dentro do hard expiry não volta a `absent` durante refresh;
- troca de principal/tenant/sessão ou revogação purga imediatamente o estado protegido;
- a mesma mensagem pode chegar mais de uma vez, mas patch duplicado é descartado, não reaplicado;
- mensagens antigas não fazem o estado regredir;
- um gap conhecido não é tratado como convergência bem-sucedida;
- mesmo cursor com token ou digest diferente é equivocation fatal;
- `commit` é correlacionado por id/fingerprint e nunca inferido de uma atualização visual;
- falha de transporte não apaga o último snapshot ainda permitido pela política;
- snapshot, cache/304, subscribe, replay, repair e commit são autorizados no servidor;
- filas, replay, patches, conexões, retry e tempo de stale têm limites concretos.

O algoritmo completo está na [spec 0.2 §§ 9–11](../specs/continuum-0.2.md#9-máquina-de-estados-do-consumidor).

### 5.7 Como transformar a ideia em padrão de verdade

Não publicar uma biblioteca genérica antes de provar o contrato. A ordem revisada é:

1. revisar adversarialmente a hipótese e registrar prior art — concluído;
2. escrever spec `0.2`, JSON Schema, exemplos e vetores independentes — concluído como draft;
3. medir e construir read model pública em shadow, sem runtime de protocolo na UI;
4. provar snapshot + ETag e depois invalidate + refetch contra o fetch canônico;
5. só implementar patch/replay se a medição mostrar gargalo residual e os gates P0 fecharem;
6. provar uma segunda implementação em domínio e ritmo diferentes;
7. extrair núcleo somente depois de duas superfícies não triviais e um binding alternativo;
8. antes de publicação, resolver a colisão do nome e produzir benchmark reproduzível.

O padrão pode ser usado por qualquer aplicação que tenha projeções de leitura, atualizações
incrementais e comandos autoritativos. Ele não pretende substituir CRDTs em edição colaborativa,
protocolos de mídia em tempo real nem transações distribuídas; nesses casos pode ser somente a
camada de apresentação.

---

## 6. Read model: calcular na mudança, não na leitura

O menu atual agrega trabalho no request. O piloto deve materializar uma projeção de leitura:

1. Uma alteração de produto, coleção, oferta ou configuração agenda reconstrução do quadro
   estrutural afetado.
2. Alteração de estoque/hold publica somente o quadro volátil do(s) SKU(s) afetado(s).
3. Redis guarda snapshots imutáveis por `stream.id + epoch + sequence + state_token + state_digest` e
   o ponteiro para o head atual.
4. Django continua sendo dono do cálculo e das regras; Redis não vira fonte de verdade.
5. O request passa a selecionar e compor quadros prontos, não repetir dezenas de consultas.

A revisão autoritativa precisa ser persistida atomicamente com a mutação que a produz. Um
emissor best-effort depois do commit pode perder exatamente o último aviso sem deixar gap
observável. Até existir outbox/CDC durável, conditional fetch/polling canônico permanece a
garantia de convergência; SSE é aceleração.

Para evitar dupla arquitetura, o mesmo construtor canônico deve servir:

- resposta SSR inicial;
- endpoint de snapshot;
- endpoint de repair;
- validação em shadow mode;
- eventos SSE posteriores ao commit.

---

## 7. Cliente Nuxt: `useContinuousProjection()`

Criar uma abstração única, não lógica espalhada por páginas:

```text
useContinuousProjection(key)
  ├─ seed do payload SSR/Nuxt com cursor + state_token + state_digest + schema
  ├─ snapshot em memória com stream + cursor + state_token + state_digest completos
  ├─ instalação atômica e patch somente sobre base exata
  ├─ descarte de duplicata/regressão e detecção de equivocation
  ├─ gap/overflow → repair limitado e deduplicado
  ├─ conexão/reconexão SSE com cursor de entrega separado
  └─ eixos explícitos: data | transport | reconcile | commands | generation + auth fence + lease
```

Regras:

- a árvore visível não volta a vazio durante refresh enquanto o snapshot estiver autorizado e
  dentro do hard expiry;
- logout, troca de principal/tenant ou revogação cancelam requests/streams e purgam dados
  protegidos, mesmo que ainda pareçam utilizáveis;
- a chave e as opções de cache são estáveis entre SSR e hidratação;
- prefetch deve respeitar economia de dados e rede lenta;
- abortar fetch antigo quando a intenção de rota muda;
- SSE aplica apenas eventos do stream/epoch/schema autorizados, com limites de fila;
- polling canônico degrada silenciosamente quando `EventSource` não funciona e permanece
  reconciliação enquanto a publicação for best-effort;
- dados privados nunca entram em cache público nem em payload compartilhável.

O Nuxt já oferece prefetch inteligente de componentes/payload em `NuxtLink`, payload SSR para
evitar refetch na hidratação e `lazy` para não bloquear navegação. O WP deve compor essas
capacidades em vez de reconstruí-las.

---

## 8. Comandos: apresentação especulativa, compromisso autoritativo

Leituras e navegação podem reapresentar o último snapshot íntegro. Escritas não.

O commitment frame da 0.1 foi substituído por um **command receipt** separado da projeção:

```text
command_id
operation
request_fingerprint
accepted | committed | adjusted | rejected | indeterminate
receipt_revision
receipt_token
retry_for_ms
observations[]
result | problem
```

O servidor emite `command_id` autenticado antes do primeiro submit; emissão repetida pelo mesmo
nonce/escopo devolve o mesmo id e desconta `issuance_age_ms` do horizonte, sem estender o deadline
quando a primeira resposta se perde. `accepted` não é terminal: significa que o comando foi registrado
duravelmente. `indeterminate` é terminal operacional, exige intervenção e proíbe retry automático.
Efeito local atomiza mutação + receipt terminal. Efeito externo usa duas fronteiras: aceitação
atomiza precondição, reserva/ledger local, outbox e `accepted`; conclusão atomiza prova do
provedor, mutação/compensação final, estado da outbox e receipt terminal. Isso não promete
transação distribuída: a mesma idempotency key segue no outbox e no provedor, `committed` exige
prova durável do resultado, e perda de resposta sem prova suficiente termina `indeterminate`, sem
afirmar se o efeito externo ocorreu. A mesma chave `(authority, environment,
tenant, principal, operation, command_id)` com o mesmo fingerprint reproduz o receipt;
fingerprint diferente conflita sem novo efeito. Resposta perdida vira `unknown` no cliente e é
resolvida por lookup do receipt, nunca por inferência de SSE. Um observation fence diz onde uma
read model já alcançou o efeito; commit sem fence não promete read-your-writes imediato.

Exemplos:

- “Adicionar” pode reagir visualmente imediatamente, mas a linha só fica confirmada por receipt
  terminal `committed` ou `adjusted`. Patch canônico ou SSE atualiza a projeção e pode satisfazer
  um observation fence; sozinho, nunca prova o commit.
- Se a última unidade acabou, o servidor rejeita ou ajusta com copy útil; o cliente reconcilia a
  tela e o snapshot local.
- Checkout nunca usa disponibilidade local como autorização.

Essa separação preserva a fonte única da verdade sem obrigar toda navegação a pagar o custo de
uma transação. A capability permanece **no-go** no piloto atual; primeiro é preciso provar
idempotência, retenção, precondição forte e recuperação de resposta perdida.

---

## 9. Estado de espera de tela inteira

Direção visual em revisão:

- tela inteira desfocada, com respiração de amplitude claramente perceptível;
- card central legível;
- spinner simples acima da mensagem;
- sem barra horizontal;
- sem círculo pulsante;
- copy contextual: “Abrindo o cardápio…”, “Confirmando o que está disponível agora…” ou
  “Atualizando a tela…”;
- contraste automático;
- `prefers-reduced-motion` respeitado;
- overlay em portal/camada fixa, sem ocupar fluxo de layout, alterar scroll, pills ou a barra
  dourada existente.

### Cor média: implementação econômica

Primeira opção — e a única no piloto — é **média perceptual por composição CSS**, sem ler pixels:

1. o backdrop recebe blur forte, redução de saturação e uma película translúcida;
2. o card usa `color-mix()` entre o token tonal da página e transparência;
3. a cor do texto é escolhida por luminância do token;
4. páginas sem token usam um neutro da marca.

Isso produz a sensação de “tom que sobra quando a tela inteira é desfocada” sem screenshot,
canvas, GPU readback ou cálculo por frame. Amostragem real de imagem só será considerada se o
piloto mostrar diferença visual relevante.

---

## 10. Work packages

### WP-CS-0 — Observabilidade e contrato

- **Concluído no design:** revisão adversarial, spec 0.2, cinco JSON Schemas, exemplos neutros e
  corpora versionados de vetores core/binding;
- adicionar `Server-Timing` por estágio: BFF, projeção, disponibilidade, personalização e DB;
- registrar queries, bytes, cache hit/miss, snapshot/revision e idade do quadro;
- fechar respostas às perguntas-gate P0 da revisão e declarar limites concretos;
- publicar manifest de conformance por unit independente e target-scoped, sem composição,
  herança ou união de facets/targets; cada unit declara somente targets, capabilities, profiles e
  layers factuais daquele escopo;
- adapters que compartilham cache, segurança, subscription, journal, comando ou rollout ficam na
  mesma unit consolidada, com todos os targets e facets próprios e verdadeiros; cada ID/identidade
  de state domain pertence a exatamente uma unit, sem unit relacional adicional; em vetor
  candidato, target ou result path ausente é falha, nunca não-aplicabilidade;
- declarar os `state_domains` stateful de cada unit e provar disjunção entre público e protegido;
  a 0.2 não aceita relação mista, domínio compartilhado entre modos de autenticação nem duas
  units fragmentadas como prova de isolamento;
- derivar em runtime identidade efetiva canônica do backing
  `(kind, backend_instance, partition, namespace)`, atestar canonicalizer+digest no trace e falhar
  fechado quando dois locators possivelmente aliases não puderem ser provados distintos;
- cada execução de unit consolida todos os targets num único `result_document` e aponta um
  `trace_evidence`; o harness não agrega resultados entre units;
- validar implicações obrigatórias profile→capability/layer: transporte realtime usa o binding SSE
  desta versão, escolhe um corte e inclui snapshot + invalidate; `snapshot-first` exige replay;
  command receipt é protected com auth/HTTP/cache e não escapa de lease/service worker; rollout
  exige os sete thresholds e `cross_audience_leaks=0`;
- preencher o catálogo fechado de limites por unit, inclusive intervalo e jitter de reconciliação,
  head/body/identificadores HTTP de entrada, head/resposta, decompressão, memória residente,
  linhagens/lease e operações de comando; executar cada eixo isoladamente: N aceito, N+1
  rejeitado pela razão daquele limite, com
  `$limit_ref` resolvido do próprio manifest; o trace e `/effective_limits` provam que nenhum
  threshold substituto ou `reject-all` foi usado;
- medir p50/p75/p95 em produção, sem dados sensíveis.

**Aceite**: antes/depois reproduzível, contrato sem dependência de Django/Nuxt e zero
implementação baseada apenas em sensação.

### WP-CS-1 — Read model do cardápio

- começar apenas pelo quadro estrutural público; pessoal não entra neste estágio;
- materializar snapshots estruturais por versão;
- reduzir composição de leitura para orçamento fixo de queries;
- normalizar produtos e referências por SKU;
- ETag/If-None-Match e endpoint realmente credentialless, sem `Set-Cookie`; `200` e `304`
  repetem a tuple completa stream/epoch/sequence/token/digest, freshness e boundary de cache, e
  mudança de qualquer versão responde `200` com ETag novo. `304` autorizado cria novo corte de
  validação sem regenerar o body; `Continuum-Age-Ms + Age` mede idade desde esse corte e cache não
  pode zerá-la sozinho;
- service worker não armazena resposta Continuum nem HTML que embuta seu bootstrap; o cache HTTP
  público preserva `Age` e todas as dimensões que mudam bytes;
- SSR público instala guard parser-blocking antes de qualquer indicação de freshness ou nasce
  semanticamente `stale_usable`; navegar antes da hidratação e restaurar bfcache nunca o marca
  fresh além do hard expiry;
- comparar em shadow sem mutar DOM e sem alterar loading visual.

**Aceite**: shadow compare do contrato antigo e do novo; nenhuma divergência semântica e nenhum
vazamento entre canal, coorte ou host.

### WP-CS-2 — Runtime Nuxt de continuidade

- só abrir após WP-CS-1 provar benefício; perfil inicial `snapshot + invalidate`;
- `useContinuousProjection()` com eixos independentes, security generation, lease deadline e
  `authorization_fence` local monotônico;
- manter stream tenant/principal em **no-go** até existir endpoint canônico de grant/renew com
  manifesto recomputado, `lease_operation_id` aleatório de 128 bits/idempotente, age não
  extensível, CAS comum com epoch de auth/policy, revogação/purge e vetores de identidade cruzada;
- `protected-data + ssr-bootstrap` é NO-GO no browser genérico; sem guard parser-blocking e prova
  de purge before-freeze/before-paint, o SSR entrega só shell e os bytes protegidos chegam após
  grant + fetch canônico;
- qualquer target protegido prova clock sleep-inclusive ou elapsed conservador + gate de wake;
  clock ambíguo expira a lease e purga em vez de reinstalar callback atrasado;
- toda operação assíncrona captura as gerações de lifecycle/repair/rollout aplicáveis; somente
  target protegido também captura security generation + authorization fence e, imediatamente
  antes de parse e install, valida ambos e a lease vigente. Grant, transição, expiry, revogação e
  purge incrementam o fence uma vez por fronteira aceita; expiry o incrementa antes de cancelar
  ou purgar; gate final e install são serializados contra esse incremento;
- cache em memória revisionado;
- prefetch por visibilidade ou intenção conforme custo da rota;
- navegação usando snapshot seguro;
- integração do estado de espera somente onde não houver quadro utilizável.

**Aceite**: navegação não apaga conteúdo autorizado, logout/revogação purga conteúdo protegido,
callback tardio não reinstala bytes após expiry/revogação e update não move foco, scroll, seleção
ou draft.

### WP-CS-3 — SSE como invalidação e repair

- assinar `stock-web` no storefront;
- fixar o piloto em **subscribe-first + buffer limitado + `continuum-ready`**; snapshot-first fica
  fora desta fase;
- usar native `EventSource` somente para esse stream público, em origin cookieless dedicado, com
  CORS sem credentials; se essa separação não estiver disponível, usar fetch-stream com
  `credentials: "omit"` em vez de native `EventSource`;
- exigir `ready` como primeiro frame não-heartbeat, emitido no mesmo corte atômico que registra a
  assinatura, com head completo por stream, manifesto exato e `id:` igual ao delivery cursor do
  controle;
- usar delivery cursor separado de `(stream, epoch, sequence)`;
- coalescer invalidations e buscar snapshot condicional canônico;
- detectar gap/reconnect/overflow e reparar uma vez por stream;
- manter polling com backoff e jitter enquanto a publicação for best-effort;
- deixar patch e replay fora do escopo inicial.

**Aceite**: perda do último evento, duplicação, reordenação, overflow, restore e reconnect
simulados convergem para a projeção canônica dentro dos limites publicados.

### WP-CS-4 — Command receipts

- **Estado: no-go no piloto atual.** Evoluir como command receipt separado;
- respostas autoritativas e consultáveis de add/remove/update/checkout;
- idempotência por escopo + `command_id` + fingerprint;
- escopo inclui authority + environment + tenant + principal + operation, e o ledger tem uma
  única generation/fence de autoridade durável; split-brain/restore sem continuidade falha
  fechado e nunca trata id antigo como novo;
- emissão autorizada/idempotente do command id e CAS na primeira utilização;
- repetição da emissão após resposta perdida preserva o deadline original por
  `retry_for_ms - issuance_age_ms - elapsed`;
- efeito local atomiza mutação + receipt terminal; efeito externo atomiza primeiro
  precondição/reserva/ledger/outbox/`accepted` e depois prova/mutação final/receipt terminal, usa a
  mesma idempotency key e só vira `committed` com prova durável, podendo terminar `indeterminate`
  sem retry automático;
- precondição forte e observation fences explícitos;
- anchors de retry, accepted e retenção usam autoridade temporal durável: upper bound expira cedo,
  lower bound impede GC precoce;
- reconciliação de conflito com copy Omotenashi;
- nenhum sucesso otimista irrevogável antes do commit.

**Aceite**: concorrência de última unidade, double-click, retry, fingerprint conflitante e
resposta perdida não duplicam efeito nem vendem acima da regra.

### WP-CS-5 — Backstage

- **Estado: futuro; não é prova necessária para o primeiro perfil conservador.**
- reutilizar o protocolo nas projeções operacionais mais lentas;
- manter ações destrutivas/financeiras no plano autoritativo de command receipts;
- usar SSE para fatos operacionais, não para recomputar dashboards inteiros.

**Aceite**: benefício demonstrado em uma superfície antes de generalizar.

### WP-CS-6 — Rollout e aprendizado

- feature flag por coorte server-side incluída na identidade/cache, nunca parâmetro livre;
- shadow mode primeiro;
- canário e rollback instantâneo para o contrato monolítico;
- comparar velocidade, inconsistência, reparos, loops, memória, rejeições, acessibilidade e
  percepção do usuário;
- manter kill switches independentes para read model, invalidation, patch, replay e receipt.

**Aceite**: expansão só ocorre com melhoria objetiva e nenhum aumento de erro silencioso.

---

## 11. Invariantes de segurança

1. Django e o banco continuam autoridade; cache e cliente são projeções descartáveis.
2. Stream, epoch, sequence, state token e state digest têm autoridade única; mesma revisão com
   token ou digest diferente é falha fatal do produtor.
3. Patch não é idempotente: só aplica sobre base exata, em cópia, uma vez e atomicamente.
4. Revisão antiga nunca sobrescreve nova; epoch divergente exige reset/repair autoritativo.
   Schema-major incompatível seleciona novo stream/endpoint por negociação confiável; repair no
   stream antigo nunca converte nem troca seu schema.
5. Snapshot, subscribe, reconnect, replay, repair, cache/304 e commit autorizam no servidor antes
   de entregar bytes.
6. Logout, troca de principal/tenant e revogação purgam conteúdo protegido; “não voltar a vazio”
   não cruza security generation.
7. Cache público, tenant, principal, SSE, receipt e erro têm endpoints/chaves/headers separados;
   dados protegidos usam `private, no-store`.
8. A revisão autoritativa é transacional. Callback pós-commit best-effort exige reconciliação
   canônica permanente; promessa de no-loss exige outbox/CDC.
9. Filas, payloads, patches, replay, conexões e retries têm limites e overflow vira reset/repair.
10. Disponibilidade apresentada nunca é autorização de venda.
11. Preço/quantidade ajustados são comunicados; não há reconciliação invisível.
12. Primeira entrada, crawler e compartilhamento continuam recebendo HTML útil por SSR.
13. A falha do SSE degrada para repair/polling, não para uma tela morta.
14. Update/overlay nunca interfere no layout, foco, seleção, scroll, draft ou controles existentes.
15. O limiar abaixo de 200 ms volta para decisão conjunta antes de qualquer implementação.
16. Sleep, bfcache, worker takeover, failover e clock rollback, por si sós, nunca reiniciam
    freshness, lease, retry ou retenção; incerteza expira autoridade cedo e impede GC cedo.

---

## 12. Orçamentos iniciais — hipóteses a calibrar no WP-CS-0

| Métrica | Hipótese inicial |
|---|---:|
| reação visual ao gesto | no próximo frame do browser |
| navegação interna até quadro utilizável | p95 < 100 ms quando houver snapshot |
| overlay de tela inteira | raro; somente sem quadro seguro ou em compromisso bloqueante |
| API de quadro volátil | p95 < 250 ms |
| projeção estrutural quente | p95 < 150 ms no servidor |
| queries do read model quente | teto a definir; crescimento O(1) |
| reparação após gap SSE | p95 < 1 s |
| divergência após compromisso | 0 silenciosa |

Esses números não autorizam, por si, uma regra visual abaixo de 200 ms.

---

## 13. Experimentos obrigatórios antes de adotar

1. **Shadow equivalence**: construir contrato progressivo ao lado do atual e comparar resultado.
2. **Chaos de transporte**: duplicar, atrasar, perder o último evento, reordenar e truncar SSE.
3. **Concorrência de estoque**: duas sessões disputando a última unidade.
4. **Cache boundary**: cruzar dois canais, tenants/principals, coortes e hosts manipulados; provar
   que A nunca recebe representação de B.
5. **Cold start**: primeira visita sem qualquer snapshot.
6. **Rede ruim/offline**: reconexão com jitter, slow consumer, overflow, economia de dados e hard
   expiry.
7. **Failover/evolução**: restore, troca de epoch, compactação e schema N/N-1. O ensaio de rollback
   mantém simultaneamente cliente N-1 restaurado de bfcache, service worker N-1, bytes candidate
   já presentes no cache e repair N em voo; antes do canário registra owner, janela de observação
   e thresholds quantitativos de promoção/rollback.
8. **Revogação**: logout, troca de principal/tenant e perda de autorização purgam memória,
   payload SSR, buffers e streams dentro do SLA.
9. **Patch hostil**: base errada, operação inválida, payload grande/profundo e paths de prototype
   pollution não alteram o estado instalado.
10. **Comando perdido**: double-click, retry com fingerprint igual/diferente e resposta perdida
    produzem no máximo um efeito e receipt consultável.
11. **Acessibilidade**: leitor de tela, foco, draft, `aria-busy`, scroll e redução de movimento.
12. **Regressão visual**: scroll, pills e barra dourada permanecem idênticos sob overlay.

---

## 14. Perguntas que a fase de design deve responder

Respondido pela 0.2:

- não existe revisão global: cada stream tem authority/partition/epoch/sequence, `state_token` e
  `state_digest`;
- o piloto usa invalidation + conditional fetch; evento não carrega URL de repair;
- freshness e hard expiry são deadlines monotônicos por projeção;
- payloads de domínio permanecem livres sob schemas explícitos; o protocolo não força storefront
  e backstage a terem o mesmo shape;
- dependência cross-partition genérica foi removida; corte exato exige uma única projeção/stream;
- `Last-Event-ID` é cursor de entrega, não revisão;
- receipt de comando é capability separada.

Gates ainda abertos antes de qualquer piloto user-visible:

1. Qual tuple exata define cada stream no Shopman e quem aloca epoch/sequence?
2. Como snapshot + subscribe formam um corte sem janela perdida?
3. Haverá outbox/CDC ou o fetch/poll seguirá como garantia permanente de convergência?
4. Qual é a matriz campo → audience → cache → persistência/service worker?
5. Qual SLA de revogação fecha stream e purga memória em logout/troca de principal?
6. Quais são retention floor, compactação e limites de bytes/ops/fila/conexões/retry?
7. Qual snapshot mínimo deixa cada rota utilizável e qual hard expiry é seguro?
8. Preço contextual pertence a stream público, tenant ou principal em cada regra?
9. Como coorte entra na chave sem permitir cache poisoning controlado pelo cliente?
10. Qual matriz N/N-1 e rollback cobre abas, bfcache e service worker antigos?
11. Quais SLOs/kill switches provam zero leak, zero efeito duplicado e repair sem loop?
12. Qual ganho residual justificaria patch/replay em vez de invalidate + refetch?
13. O nome público será trocado antes da publicação externa?

### Experimento que fecha cada gate

| Gate | Experimento reproduzível | Evidência de fechamento | Dono a nomear |
|---|---|---|---|
| 1. Tuple/alocador | dois writers concorrentes, failover e restore tentam publicar o mesmo cursor | um único CAS/fence vence; epoch não é reciclado; tuple fica no manifest | protocolo + dados |
| 2. Corte snapshot↔subscribe | injetar mutação antes, durante e depois do registro/`ready`, inclusive snapshot atrasado | nenhum sufixo perdido; snapshot abaixo do head nunca fica fresh; overflow reinicia o barrier | BFF + cliente |
| 3. Dual write | matar o processo em cada ponto entre commit, materialização e publicação | outbox/CDC redespacha uma vez, ou a decisão documentada mantém polling canônico permanente | dados + plataforma |
| 4. Campo/audience/cache | perturbar cada dimensão declarada, identidades cruzadas e reload por service worker | zero colisão de bytes/chave, zero leak e zero persistência proibida | segurança + cache |
| 5. Revogação | revogar com stream, renew, repair e callbacks em voo; repetir offline, hidden e após wake | auth/policy epoch disputa o mesmo CAS do renew; transporte/DOM/memória/SSR purgam dentro do SLA sem ressurreição | segurança |
| 6. Retention/limites | resolver `$limit_ref` do manifest e testar floor, floor−1, N/N+1 por eixo isolado, decompressão, slow consumer, jitter e storm | N aceito, N+1 rejeitado pela razão daquele limite, `410`/reset correto, `/effective_limits` idêntico ao manifest e intervalo + jitter antes do hard expiry | protocolo + SRE |
| 7. Snapshot/hard expiry | navegar antes da hidratação, pausar monotonic clock, suspender, restaurar bfcache e ficar offline nos dois deadlines | guard/elapsed conservador impede fresh tardio; `304` canônico abre novo corte, cache/sleep sozinho não; protegido permanece vazio até novo grant | domínio + cliente |
| 8. Preço contextual | executar a mesma rota sob cada price context e audiência, comparando bytes e autorização | classificação de cada campo fica explícita e contextos distintos não compartilham representação | domínio + segurança |
| 9. Coorte/cache poisoning | adulterar query/cookie/header de coorte e repetir por dois usuários | somente atribuição server-side decide coorte e toda mudança de bytes muda a chave | plataforma + cache |
| 10. N/N-1/rollback | cenário simultâneo com bfcache N-1, SW N-1, cache candidate e repair N em voo | kill switch impede reinstalação tardia e converge ao endpoint/schema baseline | release + cliente |
| 11. SLO/kill switches | shadow + fault injection durante a janela do canário, incluindo split-brain de ledger e clock rollback/forward | owner, janela e sete thresholds registrados; `cross_audience_leaks=0`, zero efeito duplicado, nenhum prazo estendido/GC precoce e loops/memória abaixo do teto | SRE + produto |
| 12. Valor de patch/replay | depois do baseline, comparar refetch vs patch/replay em bytes, CPU, memória e p95 | capability só abre se superar limiar pré-registrado sem piorar erro, repair ou acessibilidade | performance + produto |
| 13. Nome | busca jurídica/ecossistêmica e registro da decisão | nome público e URIs persistentes aprovados; `example.test` removido antes de publicar | produto + jurídico |

Resultado inconclusivo não fecha gate. O relatório do experimento registra versão, seed/carga,
faults injetados, thresholds, trace e artefato de reprodução; contagem de testes sem evidência não
é aceite.

HTTP/3/edge só volta à pauta depois de reduzir e medir o custo de aplicação.

---

## 15. Critérios de conclusão desta WP

Esta WP só pode ser marcada como concluída quando:

1. as perguntas-gate P0 tiverem dono, resposta e prova reproduzível;
2. o piloto conservador estiver em feature flag server-side e tiver rollback canônico;
3. equivalência semântica tiver sido provada em shadow mode;
4. perda do último evento, duplicação, reordenação, overflow e failover tiverem repair automático
   testado; o rollback N/N-1 tiver passado no cenário simultâneo com bfcache N-1, service worker
   N-1, bytes candidate em cache e repair N em voo, com owner, janela e thresholds quantitativos
   registrados;
5. add/carrinho/checkout mantiverem validação autoritativa, independentemente da projeção;
6. cache/auth/revogação tiverem testes de isolamento com identidades cruzadas;
7. métricas mostrarem melhoria de percepção e servidor sem loop, leak ou memória sem limite;
8. foco, draft, pills, scroll e barra dourada não tiverem regressão;
9. o estado visual tiver aceite explícito do produto;
10. a decisão sobre respostas abaixo de 200 ms tiver sido tomada em conjunto;
11. a estratégia baseline continuar documentada, exercitada e disponível como fallback;
12. patch/replay/receipt permanecerem desligados até cumprirem seus gates independentes.

---

## 16. Referências primárias

- Continuum — [spec 0.2](../specs/continuum-0.2.md),
  [revisão adversarial](../reports/continuum-0.1-adversarial-review-20260927.md) e
  [contratos/vetores](../../contracts/continuum/v0.2/README.md)
- Spotify Engineering — [Smoother Streaming with BBR](https://engineering.atspotify.com/2018/8/smoother-streaming-with-bbr)
- Spotify for Developers — [eSDK FAQ: buffering de áudio](https://developer.spotify.com/documentation/commercial-hardware/implementation/faqs)
- IETF RFC 9308 — [Applicability of the QUIC Transport Protocol](https://datatracker.ietf.org/doc/html/rfc9308)
- IETF RFC 9317 — [Operational Considerations for Streaming Media](https://datatracker.ietf.org/doc/html/rfc9317)
- Nuxt — [`NuxtLink` e smart prefetch](https://nuxt.com/docs/4.x/api/components/nuxt-link)
- Nuxt — [`useAsyncData`](https://nuxt.com/docs/4.x/api/composables/use-async-data)
- Django — [Asynchronous support](https://docs.djangoproject.com/en/6.0/topics/async/)
- CNCF — [CloudEvents specification](https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md)
- IETF RFC 8895 — [ALTO Incremental Updates Using SSE](https://datatracker.ietf.org/doc/html/rfc8895)
- IETF RFC 6902 — [JSON Patch](https://datatracker.ietf.org/doc/html/rfc6902)
- IETF RFC 7396 — [JSON Merge Patch](https://datatracker.ietf.org/doc/html/rfc7396)
- WHATWG — [Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- IETF RFC 9110 — [HTTP Semantics](https://datatracker.ietf.org/doc/html/rfc9110)
- IETF RFC 9111 — [HTTP Caching](https://datatracker.ietf.org/doc/html/rfc9111)
- IETF RFC 9457 — [Problem Details](https://datatracker.ietf.org/doc/html/rfc9457)
- OASIS — [OData 4.01 Protocol](https://docs.oasis-open.org/odata/odata/v4.01/os/part1-protocol/odata-v4.01-os-part1-protocol.html)
- Mercure — [protocol specification](https://mercure.rocks/spec)
