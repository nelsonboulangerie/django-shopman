# Execução de Pedidos — 10/09/2026

Estado: execução técnica em andamento; piloto e rollout não autorizados nem executados.

## Proveniência

Worktree exclusivo: `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-orders-execution-20260910`.
Branch: `codex/orders-operational-excellence-20260910`.
Base: `5a3383c950031da1ff9c6ace0d9ab09b3c4084f7`, origin/main local, sem fetch.
Base auditada: `9787bbcdfe5ccd2cbb4a2097b4d97c146e86179f`, ancestral da base executada.
Diferença: 16 arquivos de atalhos/PDV/Produção e kit; zero alteração em shopman, packages ou orders-nuxt.
Checkout recebido em `b589e22c5` não foi modificado. Arquivos não rastreados preservados.
Transportado somente o plano de Pedidos da branch documental `1e701515e`, sem código alheio.
CLAUDE.md lido; nenhum AGENTS.md localizado na hierarquia ou na árvore isolada.
Os oito documentos da seção 2 foram lidos, com hashes idênticos aos registrados no plano.
Produção e Marketing permaneceram entradas externas, sem cópia. ADR-012/014/016/018 e contratos
order-operational/remote-mutation confrontados: `confirmed` histórico não substitui `accepted`;
Channel display existente não ganha Listing nem preço próprio. Nenhum Admin alterado.

## WP00 — baseline

Evidência anterior: diagnósticos extraídos literalmente do bloco executável do plano, fora do produto.
SQLite: 12/12 reproduções passaram em 5,46s. D01/D02/D04/D05/D06/D07/D08/D19/D20 permanecem
reproduzidos; D03 permanece saudável (409, estado completed preservado). Assertions de defeito não
são aprovação de produto. D09–D18 de inspeção: comparação confirma código idêntico ao auditado;
releitura confirma watcher destrutivo, disabled divergente, guardas, lote sequencial, fechamento de
editor, erro/vazio, motivos engolidos, relógio local, erro sem refresh e fases incompletas.
H01–H09 continuam hipóteses/decisões, não incidentes provados nem autorização para políticas novas.

Implementação deste pacote: worktree, instalação limpa npm pelo lock e laboratório isolado.
Python 3.12.5 reutilizado em modo somente leitura do venv original, sys.path prioriza todos os packages
do worktree; sem instalação Python limpa alegada. Settings config.settings_test, DATABASE_URL/REDIS_URL
vazios para SQLite, sem .env copiado; adapters de pagamento mock e credenciais de fornecedores vazias.
PostgreSQL próprio em 127.0.0.1:55439, usuário/banco orders_lab, cluster .orders-lab/pgdata,
sem acesso ao banco operacional. Não há destinatário real, chamada de fornecedor nem periférico.

Testes efetivamente executados:
- 32 módulos das duas listas do plano: 585 passed, 1 skipped, 18 subtests passed, 38,37s.
- PostgreSQL: 12 diagnósticos + test_waitlist_waits_for_payment.py: 18 passed, 6,47s.
  Inclui o ensaio concorrente que SQLite pulou; não cobre toda matriz concorrente da seção 8.
- npm ci Gestor e kit com Node 22: passaram (887/660 pacotes). Warning glob deprecated preservado.
- Gestor Vitest: 12 arquivos, 221 passed, 2,35s; warnings Vue de harness presentes.
- Kit Vitest: 22 arquivos, 220 passed, 4,24s; sem a falha de carga antiga; warnings Vue presentes.

Medição pareada preparada: 20 amostras, macOS 15.4.1 arm64, SQLite, pedidos ready/pickup/cash simples.
Para 1/10/100/500 pedidos: 4/13/103/503 queries; 1/10/100/500 Hold nas duas projeções.
Duas zonas em 500: p50 218,03ms, p95 265,70ms, payload 872.660 bytes JSON sem compressão.
Isto não mede HTTP, rede, payload rico, SSE, dois/dez clientes nem hardware de piloto.
Primeiro ensaio de 500 excedeu buffer de 9000 queries; descartado, coletor limpo entre amostras e
ensaio repetido sem warning. Evidências de backend e distribuição: pasta orders-20260910.

### Contratos técnicos de implementação

Revisão: digest opaco do estado pertinente sob lock. Para nota e assignment, base por campo permite
merge independente; igualdade da base do mesmo campo é exigida. Avanço inclui status/target explícitos
mais fingerprint de entrada. Não usar seq de evento como revisão de notas/preços/config.
Fingerprint: JSON normalizado, versão, operação, alvo, base e inputs; escopo vincula pessoa/operação/alvo.
Estender remote_mutations/IdempotencyKey com commit local integral; rede fora do lock e via Directive.
Retenção global 24h e recibos permanentes preservados. Sete dias novos e persistência de draft após
reload ficam pendentes G05/G08; sessão em memória não autoriza retenção nova.
Lote: limite técnico deve ser medido em fixture de células antes do WP05; sem aceitar publicação
parcial de preço nem ampliar conjunto por coleção smart. Pendência de sync não reaplica preço.

Locks observados: produção trava WorkOrder→Order; eventos serializam agregado; Cashman trava turno
antes do ledger; writers de Order.data incluem notas, assignment, courier, dispatch, fiscal, lifecycle
e vínculos WO. Fiscal com lock preservado. Nenhuma ordem global nova pode inverter essas fronteiras.
Matriz fase/efeito: on_commit→estoque/cliente/payment/confirmation; accepted/paid→estoque/KDS/fulfillment;
preparing→KDS; ready→entrega/avisos; delivered→fechamento; completed→fiscal/loyalty; cancelled→release/refund/avisos.
Evidência/recuperador existente: Hold/Entry/Payman/ticket/Directive/IdempotencyKey e marcadores lifecycle.
Não inferir done do status avançado. Provas de crash adicionais pertencem WP02/WP04.

### Rastreabilidade

| Achados | Contratos | Pacotes | Prova exigida |
|---|---|---|---|
| D08/D10/D11 | C01 | WP01 | decimal, Actions iguais, negação por persona |
| D01/D02/D17 | C02/C03/C07 | WP02/WP06 | replay, fingerprint, merge/conflito, resposta perdida |
| D03/D15/H02/H03 | C03/C04 | WP03 | cancelamento, motivo externo, dois turnos, captura tardia |
| D04/D18/D19/H01 | C05 | WP04 | crash/derivação courier, queued/skipped, unknown |
| D05/D06/D07/D12/H05 | C06 | WP05 | patch integral, lote, ordem/revisão, falha segundo destino |
| D09/D13/H06 | C07 | WP06 | dirty/foco/SKU/resposta fora de ordem |
| D14/D16/D20/H04 | C08 | WP07/WP08 | erro≠vazio, clock, batch/frescor/carga |
| H07/H08/H09 | C01/C08 | WP00/WP08/WP09 | personas, inventário autorizado, owner de inbox |
| G01–G08 | C01–C08 | WP09–WP12 conforme DAG | decisão humana documentada, nunca presumida |

## Gates e migração

G01–G08 pendentes. Sem nova autoridade, política de timer/som, lançamento sintético para resolver
custódia, publicação sensível ou retenção persistente. Preparação técnica continua autorizada.
Piloto WP10 depende WP09 + gates; rollout WP11 e encerramento WP12 não começaram.
WP00 sem migration de domínio. Rollback: remover artefatos próprios e parar cluster próprio;
não apagar ou reconciliar dados reais. Código anterior P0 não deve ser reativado como rollback seguro.

## Placar

WP00: baseline executado; inventário e ensaios adicionais continuam ao longo das fatias.
WP01–WP09: pendentes; nenhum marcado T. WP10–WP12: pendentes de pré-requisitos e gates.
J01–J15: baseline estrutural do plano preservado; nenhuma melhora de campo alegada.
G06 ainda precisa aprovar budgets/personas/aparelhos/amostra. Sem medidas humanas de T/clareza.
