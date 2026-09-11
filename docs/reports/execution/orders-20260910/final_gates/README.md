# WP09 — gates locais das superfícies e cores

Node22, npm ci pelo lock em seis superfícies ainda não preparadas. Instalações
do kit/Gestor/PDV/KDS já existentes no próprio worktree. Sem alterar lockfiles
para tratar avisos npm audit; avisos de preparação preservados nos logs.

| Superfície | Vitest passed | Typecheck |
| --- | ---: | --- |
|Gestor|295|aprovado; logs ../catalog_width/|
|operator-kit|228|não possui script, --if-present termina sem executar tipo|
|Loja|536|aprovado|
|PDV|847|aprovado|
|KDS|44|aprovado|
|Produção|246|aprovado|
|Compras|93|aprovado|
|Hub|13|aprovado|
|Marketing|105|aprovado|
|BI|52|aprovado|

Total2459 casos Vitest desta cobertura, sem afirmar pessoas/aparelhos ou execução
de CI remota. Integrações do Gestor26 aprovadas em47,3s constam catalog_width/.

12 cores executados em subprocessos separados, cwd e settings de cada pyproject
como Makefile:2646 passed/21 skipped/2 subtests. Imports priorizam packages do
worktree. Agente do balcão96 passed/1 skipped Linux-only em12,02s; nenhum
periférico/serviço real usado. Skips de locks SQLite não são ensaios PostgreSQL.

A tentativa anterior de agrupar packages sob config.settings_test do framework
falhou:231 failed/2514 passed/19 skipped/2subtests. Settings/URLs/signals/loggers
eram incompatíveis com os ambientes próprios dos cores. Não foi corrigido código
para acomodar esse runner. Log completo comprimido preservado; repetição correta
por pacote é a evidência válida. Não ocultar essa falha de preparação.

Ruff integral aprovado antes do ajuste pontual Manychat; Ruff específico e gate
de106 fontes alteradas aprovados após o ajuste. Suíte ampla do framework fixa
1d84:8718 passed/68skip/3warnings/38subtests em493,08s; depois houve apenas
logging Manychat (74 PostgreSQL) e docstring, além de UI/documentos. Não chamar a
suíte ampla de execução no SHA posterior. Nenhuma migration de domínio nova.

Sem deploy/push/PR. Estes gates não superam o budget500/10 ainda falho nem
substituem a DoD técnica completa e as aprovações humanas do piloto.
