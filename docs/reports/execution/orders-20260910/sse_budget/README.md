# WP07 — SSE observado em20 atualizações

Chromium→Nitro3007→Daphne8014→PostgreSQL55439→Redis56389→SSE→browser,
um pedido sintético, stream já conectado,20 POSTs/20 eventos canônicos de nota.
Nenhum POST interceptado ou fornecedor chamado. Cada amostra exige evento SSE
real e valor novo visível, seguido de dois frames. p50 **89,26ms**, p95 **108,03ms**,
máximo **123,65ms**. Hardware/valores brutos no JSON.

O relógio parte ANTES do POST, portanto mede limite superior de commit→visível,
incluindo a ida/execução do comando. Não é timestamp exato de commit nem medida
de fótons; polling sozinho não satisfaz o teste. Fluxo sequencial quente, não
500 pedidos/10 clientes, rede piloto, reconexão ou tempo humano. Frontend
6c14c43fb com ajuste de largura de catálogo ainda não commitado; backend1d84.
Ensaio paralelo de integração em outro pedido e testes locais estavam ativos.

Script executável somente no worktree isolado; usa seu Nitro3007 e banco próprio.
Sem mudança de produto/migration. Rollback documental conserva eventos/recibos.
