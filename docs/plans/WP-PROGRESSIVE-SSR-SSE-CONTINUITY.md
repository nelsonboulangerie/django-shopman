# WP — SSR/SSE de Continuidade Semântica

> Transformar a navegação do Shopman de uma resposta monolítica que precisa “ficar pronta”
> em uma convergência contínua, revisionada e reparável — sem abrir mão de o servidor ser a
> única autoridade sobre preço, disponibilidade, carrinho e checkout.

**Status**: exploração arquitetural aprovada; implementação ainda não autorizada  
**Aberto em**: 2026-09-27  
**Superfície piloto**: storefront / cardápio  
**Expansão candidata**: demais rotas do storefront e projeções de leitura do backstage  
**Nome de trabalho**: **SSR-CS — SSR de Continuidade Semântica**  
**Decisão visual associada**: prévia em revisão; não transformar em código de produto antes do aceite

---

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

O backend entrega um envelope comum:

```text
projection_key   menu:web
snapshot_id      catálogo público que originou a tela
revision         revisão monotônica do quadro
frame            structural | volatile | personal | commitment
generated_at     instante da projeção
max_age_ms       janela em que este quadro pode ser reapresentado
depends_on       revisões mínimas das quais este quadro depende
repair_url       endpoint canônico para preencher lacunas
payload          somente os campos deste quadro
```

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
- uma atualização SSE `n+2` chega antes da `n+1`; o cliente detecta a lacuna e repara;
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

---

## 6. Read model: calcular na mudança, não na leitura

O menu atual agrega trabalho no request. O piloto deve materializar uma projeção de leitura:

1. Uma alteração de produto, coleção, oferta ou configuração agenda reconstrução do quadro
   estrutural afetado.
2. Alteração de estoque/hold publica somente o quadro volátil do(s) SKU(s) afetado(s).
3. Redis guarda snapshots imutáveis por `snapshot_id` e o ponteiro para a revisão atual.
4. Django continua sendo dono do cálculo e das regras; Redis não vira fonte de verdade.
5. O request passa a selecionar e compor quadros prontos, não repetir dezenas de consultas.

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
  ├─ seed do payload SSR/Nuxt
  ├─ snapshot em memória por key + revisão
  ├─ aplicação idempotente de quadros
  ├─ descarte de revisão regressiva
  ├─ detecção de lacuna
  ├─ repair deduplicado
  ├─ conexão/reconexão SSE
  └─ estado explícito: usable | converging | committing | repairing | unavailable
```

Regras:

- a árvore visível nunca volta de `usable` para vazio durante refresh;
- a chave e as opções de cache são estáveis entre SSR e hidratação;
- prefetch deve respeitar economia de dados e rede lenta;
- abortar fetch antigo quando a intenção de rota muda;
- SSE aplica apenas eventos do canal/loja/snapshot corretos;
- polling de repair degrada silenciosamente quando `EventSource` não funciona;
- dados privados nunca entram em cache público nem em payload compartilhável.

O Nuxt já oferece prefetch inteligente de componentes/payload em `NuxtLink`, payload SSR para
evitar refetch na hidratação e `lazy` para não bloquear navegação. O WP deve compor essas
capacidades em vez de reconstruí-las.

---

## 8. Comandos: apresentação especulativa, compromisso autoritativo

Leituras e navegação podem reapresentar o último snapshot íntegro. Escritas não.

Todo comando relevante retorna, além do resultado, um **commitment frame**:

```text
command_id
accepted | rejected | adjusted
committed_revision
authoritative_patch
human_message
```

Exemplos:

- “Adicionar” pode reagir visualmente imediatamente, mas a linha só fica confirmada quando o
  servidor aceita a quantidade e devolve o patch canônico do carrinho.
- Se a última unidade acabou, o servidor rejeita ou ajusta com copy útil; o cliente reconcilia a
  tela e o snapshot local.
- Checkout nunca usa disponibilidade local como autorização.

Essa separação preserva a fonte única da verdade sem obrigar toda navegação a pagar o custo de
uma transação.

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

- adicionar `Server-Timing` por estágio: BFF, projeção, disponibilidade, personalização e DB;
- registrar queries, bytes, cache hit/miss, snapshot/revision e idade do quadro;
- fechar schemas dos envelopes e invariantes;
- medir p50/p75/p95 em produção, sem dados sensíveis.

**Aceite**: antes/depois reproduzível e zero implementação baseada apenas em sensação.

### WP-CS-1 — Read model do cardápio

- separar estrutural, volátil e pessoal;
- materializar snapshots estruturais por versão;
- reduzir composição de leitura para orçamento fixo de queries;
- normalizar produtos e referências por SKU;
- ETag/If-None-Match e política de cache correta para cada plano.

**Aceite**: shadow compare do contrato antigo e do novo; nenhuma divergência semântica.

### WP-CS-2 — Runtime Nuxt de continuidade

- `useContinuousProjection()`;
- cache em memória revisionado;
- prefetch por visibilidade ou intenção conforme custo da rota;
- navegação usando snapshot seguro;
- integração do estado de espera somente onde não houver quadro utilizável.

**Aceite**: navegação não apaga conteúdo e não bloqueia na projeção completa.

### WP-CS-3 — SSE com sequência e repair

- assinar `stock-web` no storefront;
- incluir revisão monotônica e identidade do snapshot nos eventos;
- aplicar patch idempotente;
- detectar gap/reconnect e chamar endpoint de repair;
- fallback por polling com backoff e jitter.

**Aceite**: perda, duplicação e reordenação simuladas convergem para a projeção canônica.

### WP-CS-4 — Commitment frames

- respostas autoritativas de add/remove/update/checkout;
- deduplicação por `command_id`;
- reconciliação de conflito com copy Omotenashi;
- nenhum sucesso otimista irrevogável antes do commit.

**Aceite**: concorrência de última unidade, double-click e retry não vendem acima da regra.

### WP-CS-5 — Backstage

- reutilizar o protocolo nas projeções operacionais mais lentas;
- manter ações destrutivas/financeiras no plano de compromisso;
- usar SSE para fatos operacionais, não para recomputar dashboards inteiros.

**Aceite**: benefício demonstrado em uma superfície antes de generalizar.

### WP-CS-6 — Rollout e aprendizado

- feature flag por loja/sessão;
- shadow mode primeiro;
- canário e rollback instantâneo para o contrato monolítico;
- comparar velocidade, inconsistência, reparos, rejeições e percepção do usuário.

**Aceite**: expansão só ocorre com melhoria objetiva e nenhum aumento de erro silencioso.

---

## 11. Invariantes de segurança

1. Django e o banco continuam autoridade; cache e cliente são projeções descartáveis.
2. Frames são íntegros, idempotentes e monotônicos dentro de sua chave.
3. Evento de mudança só é emitido após commit.
4. Uma revisão antiga nunca sobrescreve uma nova.
5. Lacuna detectada inicia repair; não é ignorada silenciosamente.
6. Cache público e contexto privado têm chaves, endpoints e headers separados.
7. Disponibilidade apresentada nunca é autorização de venda.
8. Preço/quantidade ajustados são comunicados; não há reconciliação invisível.
9. Primeira entrada, crawler e compartilhamento continuam recebendo HTML útil por SSR.
10. A falha do SSE degrada para repair/polling, não para uma tela morta.
11. O overlay nunca interfere no layout, scroll ou controles existentes.
12. O limiar abaixo de 200 ms volta para decisão conjunta antes de qualquer implementação.

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
2. **Chaos de transporte**: duplicar, atrasar, perder e reordenar eventos SSE.
3. **Concorrência de estoque**: duas sessões disputando a última unidade.
4. **Cache boundary**: provar que sessão A nunca recebe quadro pessoal de B.
5. **Cold start**: primeira visita sem qualquer snapshot.
6. **Rede ruim/offline**: navegação, reconexão, economia de dados e timeout.
7. **Acessibilidade**: leitor de tela, foco, `aria-busy` e redução de movimento.
8. **Regressão visual**: scroll, pills e barra dourada permanecem idênticos sob overlay.

---

## 14. Perguntas que a fase de design deve responder

- Qual revisão é global, por loja, por canal e por SKU?
- O evento SSE leva o patch completo ou apenas invalidação + URL de repair?
- Qual idade máxima de cada quadro antes de deixar de ser seguro reapresentá-lo?
- Preço contextual pertence ao quadro volátil ou pessoal em cada regra promocional?
- Qual snapshot mínimo deixa cada rota “utilizável”?
- Qual a política de compactação do journal de revisões?
- Como manter um protocolo único sem forçar payload idêntico em storefront e backstage?
- Onde HTTP/3/edge ajudam de fato, depois de reduzir o custo de aplicação?

---

## 15. Critérios de conclusão desta WP

Esta WP só pode ser marcada como concluída quando:

1. o piloto do cardápio estiver em feature flag e tiver rollback;
2. a equivalência semântica tiver sido provada em shadow mode;
3. perda/reordenação de SSE tiver repair automático testado;
4. add/carrinho/checkout mantiverem validação autoritativa;
5. cache público/privado tiver testes de isolamento;
6. métricas mostrarem melhoria de percepção e de servidor;
7. pills, scroll e barra dourada não tiverem regressão;
8. o estado visual tiver aceite explícito do produto;
9. a decisão sobre respostas abaixo de 200 ms tiver sido tomada em conjunto;
10. a estratégia baseline continuar documentada e disponível como fallback.

---

## 16. Referências primárias

- Spotify Engineering — [Smoother Streaming with BBR](https://engineering.atspotify.com/2018/8/smoother-streaming-with-bbr)
- Spotify for Developers — [eSDK FAQ: buffering de áudio](https://developer.spotify.com/documentation/commercial-hardware/implementation/faqs)
- IETF RFC 9308 — [Applicability of the QUIC Transport Protocol](https://datatracker.ietf.org/doc/html/rfc9308)
- IETF RFC 9317 — [Operational Considerations for Streaming Media](https://datatracker.ietf.org/doc/html/rfc9317)
- Nuxt — [`NuxtLink` e smart prefetch](https://nuxt.com/docs/4.x/api/components/nuxt-link)
- Nuxt — [`useAsyncData`](https://nuxt.com/docs/4.x/api/composables/use-async-data)
- Django — [Asynchronous support](https://docs.djangoproject.com/en/6.0/topics/async/)
