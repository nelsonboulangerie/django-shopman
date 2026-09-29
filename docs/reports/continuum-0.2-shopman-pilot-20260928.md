# Continuum 0.2 — evidência do piloto conservador do cardápio

Data: 2026-09-28

Branches: `codex/continuum-0.2-adversarial-20260927` (base),
`codex/continuum-0.2-shadow-canary-20260928` (primeira amostra),
`codex/continuum-0.2-shadow-budget-20260928` (correção) e
`codex/continuum-0.2-shadow-retry-20260928` (segunda amostra) e
`codex/continuum-0.2-live-manual-canary-20260928` (canário HTTP manual)

Escopo: WP-CS-0 parcial + WP-CS-1 + perfil público inicial do WP-CS-2 no Live de teste

Estado de promoção: **segunda amostra de shadow aprovada; endpoint e consumidor Nuxt autorizados
em todo o `/menu` do Live de teste, com fallback monolítico preservado**

## Resultado

O menu existente continua sendo a autoridade e o único contrato consumido pela UI. O piloto
adiciona, ao lado dele:

- `Server-Timing` no Django para projeção, disponibilidade, personalização e DB;
- preservação desses estágios no BFF, com acréscimo do estágio `bff`;
- log estruturado allowlisted de queries, bytes, cache hit/miss, sequence, idade e igualdade do
  shadow, sem payload, sessão, SKU ou pessoa;
- read model descartável e versionada do cardápio estrutural público;
- snapshot CloudEvents validado pelo schema 0.2, com ETag forte e `If-None-Match`;
- SSR do `/menu` a partir do quadro estrutural, seguido da projeção canônica de preço, estoque,
  carrinho e preferências no cliente;
- cache em memória revisionado, descarte de regressão, falha em equivocation e revalidação
  condicional com polling de 30 s e jitter;
- feature flags server-side e kill switch que não dependem de deploy de cliente.

Não foram implementados invalidate/SSE Continuum, patch, replay, projeções protegidas, receipts,
dependência cross-partition nem integração Backstage. A personalização continua vindo da projeção
canônica existente e nunca entra no snapshot público. O slice público do CS-2 está aberto; CS-3
e as capabilities deliberadamente `no-go` permanecem fora deste piloto.

## Contrato público e audiência

Endpoint candidato:

`GET /api/v1/storefront/continuum/v0.2/catalog-structure/`

O endpoint aceita somente uma representação pública fixa do canal `web`. Ele rejeita antes do
lookup qualquer query string e os headers `Cookie`, `Authorization`, `Proxy-Authorization` e
`X-SSL-Client-Cert`. A resolução global de cliente também ignora explicitamente esse namespace,
de modo que o Django não toca a sessão nem acrescenta `Vary: Cookie`.

Campos admitidos no snapshot: identidade e ordem de produto, nome, descrição curta, imagem,
categoria, tags/termos de busca, informações alimentares, novidade, rótulo de peso, alergênicos e
seções editoriais estáticas. Preço, disponibilidade, carrinho, favoritos, inscrições de aviso,
contexto de preço, sessão, identidade e seções dinâmicas ficam fora. Host não muda bytes nem ETag;
`Vary` contém apenas `Accept`.

`200` e `304` repetem ETag, stream, epoch, sequence, state token, state digest, freshness e o mesmo
boundary de cache. O body é persistido por versão e não é regenerado no `304`. O service worker
atual não possui regra de runtime cache para APIs e nenhum consumidor foi ligado ao endpoint.

## Autoridade e rollback

O banco operacional continua sendo a autoridade. `CatalogStructureHead` é apenas uma read model
reconstruível: signals marcam a cabeça como suja depois do commit e o próximo shadow/snapshot a
reconstrói com o `build_catalog` canônico. Sequence só avança quando o digest estrutural muda.

Signals são o caminho rápido, não a fronteira de durabilidade. `verified_at` é o watermark da
última leitura canônica completa; ao atingir `SHOPMAN_CONTINUUM_RECONCILE_AFTER_MS`, o primeiro
request volta a executar `build_catalog` mesmo com `dirty=false`. Assim, crash depois do commit e
antes do callback `on_commit`, `bulk_update`/`QuerySet.update` e produtor fora dos signals têm
staleness limitada em vez de poder renovar uma tuple antiga indefinidamente. O default de
reconciliação é igual ao horizonte de frescor (30 s), de modo que bytes não são renovados como
frescos sem nova verificação da autoridade.

A persistência da cabeça é transacional e o cache é descartável, versionado por epoch/sequence/
token. Fault injection cobre queda antes do commit da cabeça e perda total do cache depois dele;
o request seguinte reconcilia ou publica a cabeça já confirmada. Remover a read model simula
restore/failover e gera novo epoch antes de voltar a servir.

Configuração inicial:

| Variável | Default | Função |
|---|---:|---|
| `SHOPMAN_CONTINUUM_CATALOG_SHADOW_ENABLED` | `false` | materializa e compara sem mudar resposta/DOM |
| `SHOPMAN_CONTINUUM_CATALOG_SNAPSHOT_ENABLED` | `false` | expõe o endpoint candidato |
| `SHOPMAN_CONTINUUM_KILL_SWITCH` | `false` | domina as duas flags e desliga o piloto |
| `SHOPMAN_CONTINUUM_RECONCILE_AFTER_MS` | `30000` | revalida periodicamente contra a fonte canônica |

Rollback operacional: definir `SHOPMAN_CONTINUUM_KILL_SWITCH=true` ou desligar as duas flags. O
endpoint volta a `404`, o shadow deixa de materializar e `/storefront/menu/` continua no caminho
canônico. A tabela inerte pode permanecer instalada; removê-la não faz parte do rollback e não é
necessário para recuperar o comportamento anterior.

## Limites efetivos do adapter

| Limite | Valor |
|---|---:|
| resposta comprimida | 262.144 bytes |
| resposta decodificada | 1.048.576 bytes |
| response head | 65.536 bytes |
| request head | 65.536 bytes |
| identificador de request | 16.384 bytes |
| nós JSON | 100.000 |
| profundidade JSON | 64 |
| resultado instalado | 1.048.576 bytes |
| residente | 4.194.304 bytes |
| razão de descompressão | 20.000 milli |
| tempo de descompressão | 1.000 ms |
| tentativas de repair | 3 |
| retry | 30.000 ms |

O slice server-side produz resposta sem compressão própria e não contém parser ou estado cliente.
Por isso os limites de descompressão, memória residente cliente, repair e retry estão declarados
para compatibilidade do perfil, mas ainda não são uma alegação de execução/conformance. Os limites
aplicáveis neste slice — request head/identificador, bytes decodificados/resultado, nós e
profundidade — falham fechados; o menu canônico permanece disponível.

## Evidência reproduzível desta branch

Com `DATABASE_URL=''`, `DJANGO_SETTINGS_MODULE=config.settings_test` e o `PYTHONPATH` do Makefile:

```text
python -m pytest shopman/storefront/tests/api/test_continuum_catalog.py \
  shopman/storefront/tests/test_continuum_shadow_evaluator.py -q
17 passed
```

Essa suíte valida schema, ausência de campos contextuais, `200`/`304`, comparação fraca de
`If-None-Match` em GET/HEAD mantendo ETag forte, byte stability entre hosts, rejeição de audiência
com zero queries, avanço de sequence/ETag, shadow sem mudança do contrato visível, kill switch,
falha fechada por limite, métricas estruturadas, orçamento quente, convergência sem callback,
bulk update, queda antes do commit, perda do cache e rotação de epoch em restore. No seed de teste,
o snapshot quente usa no máximo 2 queries e estritamente menos queries que o menu canônico.

## Decisão operacional do rollout

Owner: **Storefront / Pablo Valentini**.

Em 28/09/2026, o owner retirou a janela de **24 horas e 500 observações válidas** como pré-condição
do rollout neste ambiente. O Live ainda é um ambiente de teste, não foi divulgado e não possui
tráfego orgânico capaz de produzir a amostra antes do próprio uso que precisa ser validado. A
experiência completa do piloto fica disponível para o teste do owner e para qualquer acesso
ocasional, sob o aviso já existente de ambiente de teste.

Os thresholds técnicos continuam sendo guardrails de regressão, mas não exigem volume mínimo:
O avaliador falha fechado com qualquer linha correspondente malformada e exige:

- zero divergência semântica e zero erro do shadow;
- p95 do trabalho adicional do shadow de no máximo 25 ms;
- p95 de no máximo 2 queries adicionais;
- snapshot de no máximo 1.048.576 bytes;
- relatório de p50/p75/p95, volume e distribuição de hit/miss/rebuild.

Comando reproduzível no deployment:

```text
doctl apps logs APP_ID web --type run --no-prefix --tail 20000 \
  | python scripts/evaluate_continuum_shadow.py
```

Falha aciona o rollback coordenado das flags Django/Nuxt; o `/menu` volta ao fetch monolítico. Se o
shadow afetar o caminho canônico, o kill switch também é armado.

## Rollout no alpha

A base foi mergeada pelo PR #1189 no commit `c685d7264a30cf0aadc771993083772967ddce4e`.
O deployment `a9ec6a4e-eb69-4248-b024-264b26de2248` ficou `ACTIVE` em
2026-09-28T12:24:25Z com todas as flags desligadas. O smoke pós-deploy validou `/ready/`,
cardápio, checkout e SSR; a conferência direta confirmou menu `200` e endpoint candidato `404`.

A fase seguinte liga somente `SHOPMAN_CONTINUUM_CATALOG_SHADOW_ENABLED` no alpha. O menu
canônico continua sendo a resposta ao cliente, `SHOPMAN_CONTINUUM_CATALOG_SNAPSHOT_ENABLED`
permanece `false`, o endpoint candidato continua `404` e nenhuma mudança de cliente entra nesta
fase. A janela de 24 horas/500 observações começa apenas quando o deployment dessa configuração
estiver `ACTIVE`.

O primeiro ensaio ficou `ACTIVE` no deployment `5e23fd66-100e-48ce-90af-6421f639c64d`. A
amostra inicial teve 13 observações, zero divergências, zero erros e snapshot máximo de 33.265
bytes, mas reprovou o orçamento: shadow p50 30,351 ms, p95 94,317 ms e p95 de 6 queries. O
deployment `d1c10b0b-4ed3-489d-8708-bb1ba393165d` aplicou imediatamente o rollback com shadow e
snapshot `false` e kill switch `true`; readiness e menu responderam `200`, e o endpoint candidato
continuou `404`.

A causa medida foi a segunda execução de `projection_data(catalog)` dentro do shadow, depois de o
menu canônico já ter calculado exatamente essa projeção. A correção reutiliza os dados canônicos
do próprio payload e mantém apenas a leitura da cabeça descartável no caminho quente. Ela entra
com o kill switch armado e precisa de nova ativação separada para provar o orçamento no alpha.

A correção foi mergeada pelo PR #1202 no commit
`8ee9b1c49cf0076d778a756b8b4e0d637fdaced2`. O deployment
`eaa5f200-45a3-462b-a8e7-25435d299090` ficou `ACTIVE` em 2026-09-28T14:25:15Z com shadow e
snapshot `false` e kill switch `true`; o smoke exato do deployment passou readiness, cardápio,
checkout e SSR. A segunda amostra volta a ligar somente o shadow e desarma o kill switch, mantendo
o endpoint candidato em `404`.

A segunda amostra ficou `ACTIVE` no deployment `d451542e-e60f-444d-bba0-5e926c24d7aa` e reuniu
31 observações em 96,701 s: zero divergências, zero erros, p50 de 14,307 ms, p75 de 15,909 ms,
p95 de 23,195 ms, p95 de 1 query e snapshot máximo de 33.265 bytes. Foram 30 cache hits e 1 miss.
Todos os thresholds quantitativos passaram. Por decisão do owner em 28/09/2026, o próximo passo é
ligar endpoint e consumidor Nuxt em todo o `/menu` do Live de teste. O snapshot entrega estrutura;
o menu canônico continua sendo autoridade e converge preço, disponibilidade, carrinho e
preferências antes de permitir compra.

Uma leitura posterior encontrou somente linhas reais do shadow com `shadow_equal=true` e
`shadow_error=false`; a linha inicialmente contada como divergência era na verdade um registro
`cache_status=off` do intervalo desligado. As três observações reais mais recentes, porém, mediram
27,353 ms, 37,169 ms e 28,647 ms. Como o consumidor completo não precisa executar a comparação em
paralelo a cada menu, o rollout desliga o shadow e elimina esse custo adicional do caminho canônico,
mantendo snapshot, reconciliação periódica e fallback monolítico.

O consumidor Nuxt usa um BFF credentialless dedicado, sem encaminhar Cookie/Authorization nem
aceitar query livre. Se o snapshot estiver desligado, inválido ou indisponível no SSR, a página
volta ao fetch monolítico. Quando o snapshot está utilizável, os produtos e suas fotos aparecem no
primeiro quadro; preço, disponibilidade e controles permanecem indisponíveis até o overlay
canônico autorizado chegar. Revalidações posteriores preservam o quadro instalado.

```text
npm test -- --project unit tests/djangoProxyBehavior.test.ts
9 passed
```

A suíte do BFF prova que o `Server-Timing` do Django é preservado e recebe o estágio `bff`.

```text
python contracts/continuum/v0.2/validate_contracts.py
Continuum 0.2 contracts OK: 14 messages, 27 controls, 60 core vectors,
186 binding vectors, 4 manifest units
```

O adapter reutiliza diretamente `message.schema.json`. A validação acima prova que o corpus
normativo versionado permanece íntegro; ela **não** significa que este adapter executou todos os
vetores.

## Escopo ainda não alegado

Este documento não publica um manifest de conformance do deployment. A identidade efetiva de DB e
cache precisa ser derivada e atestada no ambiente real, e o harness target-scoped ainda precisa
gerar um único `result_document` e `trace_evidence` para a unit consolidada. Inventar identidades
estáticas ou apontar para traces inexistentes seria uma alegação de isolamento que a evidência não
sustenta.

Antes de declarar conformance ampla da 0.2 ou levar o mecanismo além deste Live de teste, ainda são
obrigatórios:

1. janela de shadow em produção com p50/p75/p95, volume, queries, bytes, cache hit/miss e zero
   divergência silenciosa;
2. manifest runtime com os state domains efetivos de DB/cache e execução target-scoped dos vetores
   aplicáveis, inclusive N/N+1 por limite;
3. executar no deployment os ensaios já automatizados de convergência sem callback, queda,
   cache perdido e rotação de epoch;
4. completar no ambiente real os ensaios de failover e de boundary entre host, canal e qualquer
   futura coorte;
5. rollback N/N-1 simultâneo com cliente N-1 restaurado de bfcache, service worker N-1, bytes
   candidate já no cache e operação N em voo; nenhum byte ou callback tardio pode reinstalar o
   candidate depois do kill switch;
6. cumprir os thresholds quantitativos definidos acima em observações reais;
7. comparação de percepção e custo que demonstre benefício suficiente para abrir CS-2.

Esses itens não bloqueiam o piloto completo no Live de teste autorizado pelo owner. Eles bloqueiam
somente alegações maiores: conformance completa, patches/replay, dados protegidos, receipts,
integração Backstage e uso como padrão genérico fora deste cardápio.
