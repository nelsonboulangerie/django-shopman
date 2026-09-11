# WP07/H04 — um versus quatro processos de leitura

Fontee45ebf3b8, mesmo PostgreSQL orders_perf_lab rico500, Apple M2/8 CPUs
lógicas/8GiB; quatro Daphne loopback8016–8019, sem worker de efeitos. Cliente
distribui requests round-robin; não há BFF/load balancer nem topologia de produção
provada.20 amostras por combinação, primeira leitura de cada processo separada.

| Processos | Clientes | Backend p95 ms | HTTP p95 ms |
| ---: | ---: | ---: | ---: |
|1|1|230,597|237,062|
|1|2|372,149|409,260|
|1|10|1.863,013|1.957,995|
|4|1|262,731|270,639|
|4|2|283,036|288,803|
|4|10|898,565|1.067,602|

Distribuição completa, bytes/queries/Hold/RSS por request no JSON. A separação
reduz contenção concorrente, mas **não atinge500ms** para10 clientes; não altera
o budget nem autoriza escolher só coorte rápida. Tampouco resolve renderização
de500 cards ou prova adequação de quatro processos no aparelho/ambiente piloto.
Outros serviços do laboratório permaneceram disponíveis; não se alega host de
benchmark exclusivo. Não extrapolar a diferença para ganho humano.

Reprodução: iniciar serve.py separadamente nas quatro portas fixas; executar
measure.py com o Python do lab. Cookie privado permanece em .orders-lab e não
é exportado. Sem mutation HTTP, provider, DDL ou configuração de deploy. Os
quatro processos foram encerrados após verificar PID/comando/cwd próprios.
Ruff detectou vínculo de variável de loop no lambda; captura explícita corrigida,
sem mudança de execução porque cada pool já aguardava todas as amostras. Ruff
final aprovado. Rollback remove apenas artefatos/processos locais. G06 pendente.
