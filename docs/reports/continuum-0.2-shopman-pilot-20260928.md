# Continuum 0.2 — evidência do piloto conservador do cardápio

Data: 2026-09-28

Branch: `codex/continuum-0.2-adversarial-20260927`

Escopo: WP-CS-0 parcial + WP-CS-1 em shadow/snapshot desligado

Estado de promoção: **não promovido; todas as flags nascem desligadas**

## Resultado

O menu existente continua sendo a autoridade e o único contrato consumido pela UI. O piloto
adiciona, ao lado dele:

- `Server-Timing` no Django para projeção, disponibilidade, personalização e DB;
- preservação desses estágios no BFF, com acréscimo do estágio `bff`;
- log estruturado allowlisted de queries, bytes, cache hit/miss, sequence, idade e igualdade do
  shadow, sem payload, sessão, SKU ou pessoa;
- read model descartável e versionada do cardápio estrutural público;
- snapshot CloudEvents validado pelo schema 0.2, com ETag forte e `If-None-Match`;
- feature flags server-side e kill switch que não dependem de deploy de cliente.

Não foram implementados runtime Nuxt, invalidate/SSE, patch, replay, personalização, dados
protegidos, receipts, dependência cross-partition nem integração Backstage. CS-2 e CS-3
permanecem fechados porque CS-1 ainda não produziu evidência de produção.

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

Configuração inicial:

| Variável | Default | Função |
|---|---:|---|
| `SHOPMAN_CONTINUUM_CATALOG_SHADOW_ENABLED` | `false` | materializa e compara sem mudar resposta/DOM |
| `SHOPMAN_CONTINUUM_CATALOG_SNAPSHOT_ENABLED` | `false` | expõe o endpoint candidato |
| `SHOPMAN_CONTINUUM_KILL_SWITCH` | `false` | domina as duas flags e desliga o piloto |

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
python -m pytest shopman/storefront/tests/api/test_continuum_catalog.py -q
9 passed
```

Essa suíte valida schema, ausência de campos contextuais, `200`/`304`, byte stability entre hosts,
rejeição de audiência com zero queries, avanço de sequence/ETag, shadow sem mudança do contrato
visível, kill switch, falha fechada por limite, métricas estruturadas e orçamento quente. No seed
de teste, o snapshot quente usa no máximo 2 queries e estritamente menos queries que o menu
canônico.

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

## Gates ainda abertos

Este documento não publica um manifest de conformance do deployment. A identidade efetiva de DB e
cache precisa ser derivada e atestada no ambiente real, e o harness target-scoped ainda precisa
gerar um único `result_document` e `trace_evidence` para a unit consolidada. Inventar identidades
estáticas ou apontar para traces inexistentes seria uma alegação de isolamento que a evidência não
sustenta.

Antes de promoção, ainda são obrigatórios:

1. janela de shadow em produção com p50/p75/p95, volume, queries, bytes, cache hit/miss e zero
   divergência silenciosa;
2. manifest runtime com os state domains efetivos de DB/cache e execução target-scoped dos vetores
   aplicáveis, inclusive N/N+1 por limite;
3. ensaios de restore/failover/epoch e de boundary entre host, canal e qualquer futura coorte;
4. thresholds quantitativos, owner e janela de observação do canário;
5. comparação de percepção e custo que demonstre benefício suficiente para abrir CS-2.

Até esses itens existirem, o estado correto do PR é draft e as flags permanecem desligadas.
