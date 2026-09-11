# Fechamento da rodada técnica — 11/09/2026

Fonte anterior pós-rebase: `7def4cdba`. Implementação: `429e0a2b2` (projeção)
e `922fb522c` (carregamento da fila). Esta rodada substitui os números de desempenho
anteriores para o escopo medido; não aprova T, piloto ou rollout.

## WP07 — evidência anterior, mudança e resultado

Com 500 pedidos ricos sintéticos, a fonte anterior apresentou browser p50 1499,5 ms,
p95 1845 ms e primeira abertura 3104 ms. O backend em um processo apresentou
p95 215,229/391,600/1528,657 ms para 1/2/10 clientes. Distribuições em
`browser-before.json` e `http-before.json`; o gargalo foi reproduzido após o rebase.

A projeção agora lê apenas as colunas de itens utilizadas no card em uma consulta,
reutiliza revisões das Actions canônicas na mesma leitura e evita reconstruir cada
Action para anexar a pessoa. A serialização guarda somente metadados imutáveis de
schema, nunca permissões ou dados de pessoas. JSON completo com relógio fixo
permaneceu equivalente (`projection-equality.json`). Seis status são cobertos por
regressão comparando card em lote com leitura canônica individual, incluindo fração,
truncamento, alteração de item e revisão. Nenhuma regra/writer/fonte foi duplicada.

O Gestor carrega a fila após a hidratação da sessão (`server:false`), preservando
500 cards, Actions, filtros, seleção, SSE e estados de leitura/erro existentes.
HTML inicial passou de aproximadamente 3,03 MB para 27,3 KB; os dados continuam
carregados pela API. O ensaio mede até digitar filtro e observar o resultado, não
somente até o shell aparecer. Duas jornadas de retorno por link/histórico verificam
contexto, foco e posição. Login está fora desta medição técnica.

| Pedidos | Browser p95 ms (20 amostras) | Backend p95 ms, 1/2/10 clientes |
| --- | ---: | --- |
| 1 | 328 | 17,082 / 19,097 / 79,383 |
| 10 | 407 | 26,689 / 25,290 / 104,752 |
| 100 | 566 | 38,978 / 140,088 / 289,273 |
| 500 | 1329 | 195,678 / 233,929 / 451,290 |

A linha500 usa **cinco processos Daphne**, 60 amostras por concorrência; as linhas
menores usam um processo, 20 amostras por concorrência. Browser final500 p50 1160 ms,
p95 1329 ms, máximo1486 ms, primeira amostra1195 ms. A rodada candidata teve uma
primeira abertura3035 ms: está preservada em `browser-candidate.json`, incluída nas
20 amostras. Não se afirma que todo início frio está abaixo1500 ms.

Quatro processos finais ainda falharam: p95 565,553 ms em10 clientes. Iterações
anteriores falharam com629,2 e553,947 ms em quatro; cinco antes da última otimização
ficaram em500,391 ms, também reprovação. As distribuições negativas estão juntas
das positivas. Cinco processos finais: rodada20 p95 322,534 ms; confirmação60
p95 451,290 ms, máximo519,125 ms. HTTP total dessa confirmação p95 498,868 ms.
O budget é p95; o máximo não foi escondido nem arredondado para passar.

Ambiente: macOS15.4.1/arm64, Apple M2,8 CPUs lógicas/8 GiB, loopback,
PostgreSQL55439 e Redis56389 isolados, fixtures com três itens fracionários e seis
eventos por pedido. Host compartilhado; benchmarks não sobrepostos às suítes amplas.
Distribuição concorrente por round-robin no cliente, **sem BFF/load balancer**:
não comprova topologia operacional. Soma dos máximos individuais de RSS dos cinco
leitores aproximadamente867 MiB, não pico simultâneo de memória. G06 ainda precisa
definir e medir equipamento, rede e capacidade homologados. Não alteramos deploy.

## WP06/WP09 — testes realmente executados

- Backend amplo em worktree destacado e limpo no SHA922fb522c: **9446 passed,
  77 skipped,3 warnings,38 subtests**,840,21 s, SQLite/xdist2.
- Contratos focados PostgreSQL: **75 passed,13 subtests**,11,82 s.
- Gate runtime PostgreSQL/Redis: **341 passed**,4 warnings,57,31 s, sem skips;
  preflight passou. Esses grupos se sobrepõem: não somar como testes únicos.
- Doze cores: **2758 passed,21 skipped,2 subtests**; logs individuais preservados.
- Counter agent: **129 passed,1 skip de Linux**,12,74 s.
- Vitest: Orders303; bi52; hub13; kds44; marketing245; pos863; production278;
  purchase93; storefront536. Kit255 é a rodada pós-rebase anterior documentada em
  `../brief_rebase/`, não uma nova execução desta rodada. Typecheck/build Orders passaram.
- **29 jornadas integradas passaram**,1,1 min. A primeira rodada teve28 pass/1 falha:
  o alvo era medido durante animação scale .95 (47,825 px). A asserção agora espera
  a geometria estabilizar, mantendo o piso48 px. Cancelamento e recibo permaneceram
  corretos; log negativo preservado. O ajuste do teste posterior ao SHA922 não muda
  runtime e foi usado na rodada29 final.
- Ruff, constraints100 pacotes, marketing docs/schema, workflow budgets e
  silent-swallow passaram. Migration gate:3 checks passaram,2 skips explícitos:
  tag go-live-v1 ausente e snapshot baseline não configurado.

Python3.12.5/Django6.0.5/Daphne4.2.1 e Node22. Ambiente Python reaproveitado somente
para leitura, imports priorizando o worktree e seus packages. Instalações npm
reutilizadas; não houve instalação limpa alegada. SQLite não prova locks de
PostgreSQL; os ensaios PostgreSQL separados cobrem esse contrato. Preparação/skips
anteriores continuam no diário, não são convertidos em passes por esta rodada.

## Restore e rollback — WP09

Novo alvo sintético `orders_restore_lab_922fb`, recusando sobrescrever alvo existente.
Restore inicial reproduziu **162 tabelas e151 sequências exatamente**: dump940303
bytes/0,291 s, restore1,016 s. Origem permaneceu intacta. Livros/chaves preservados:
19 entradas de caixa,115 pedidos,93 Directives,526 chaves,19 intents/19 transações
de pagamento e2 movimentos de estoque, incluindo fração0,500.

Probe atual faz zero chamadas ao fornecedor fake; código antigo5a3383c9 faz uma,
provando que worker antigo continua inseguro para unknown. Linhas dos probes foram
revertidas. A verificação estrita posterior inicialmente falhou porque PostgreSQL
não reverte nextval: sequência de alerta10→11. Nenhuma tabela mudou. O modo explícito
`--after-probes` aceita somente esse avanço unitário, mantém checagem integral da
origem e de todas as tabelas e relata `all_tables_and_sequences_still_equal:false`.
O log antigo dos probes dizia writes; leia como **row writes**, não sequências.
Não houve reset para disfarçar o resultado. Dump/cookies/payloads não são exportados.

Não há DDL próprio novo. Schemas upstream pós-rebase foram preservados. Reverter
isoladamente as duas otimizações restaura leitura/renderização anteriores, com
regressão de desempenho, sem tocar livros/recibos. Rollback operacional deve manter
barreiras seguras de mutação e de unknown; não reativar worker antigo nem fazer
downgrade do banco para a base auditada. RTO/RPO em volume real não foi demonstrado.

## Omotenashi, fase e decisão pendente

Antes/depois de J01–J15 permanece na matriz `../CURRENT-STATUS.md`: mesma intenção
após resposta perdida, sem repetir comando; concorrência preserva campos/drafts e
expõe conflito; falha parcial identifica o efeito faltante; próxima ação permanece
no recurso autorizado. R=0 vale somente nos cenários ensaiados. Confirmações,
permissões e segunda assinatura não foram removidas. Não há amostra humana para
alegar redução30%, compreensão95/100% ou ganho em campo.

WP07 fecha a falha de budget **no laboratório e configuração declarados**; cobertura
de carga/rede/fallback e G06 permanecem explicitamente limitadas. WP09 recebeu nova
validação ampla e restore, mas **T permanece aberto** pelos critérios ainda pendentes
na matriz, incluindo C07. WP10 está preparado, sem piloto; WP11–12 não executados.
Os PRs A/B/C do brief aguardam fechamento operacional, conforme sequência prescrita.

Decisão G05/G08 apresentada ao usuário: autorizar retenção de drafts/chaves somente
na aba, retomada apenas para mesma pessoa autenticada, limpeza ao salvar/descarte/
fechamento, sem PIN/senha/sincronização; ou manter memória e confirmação antes de
sair, deixando retomada pós-reload pendente. **Nenhuma resposta foi registrada**.
Somente essa persistência está suspensa por essa decisão. Outros gates nominais,
fornecedores, piloto e rollout estão no protocolo; não houve aprovação por silêncio,
produção, comunicação externa, emissão fiscal, despacho ou movimento real.
