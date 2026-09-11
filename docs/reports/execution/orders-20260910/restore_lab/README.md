# WP09 — restore sintético e compatibilidade de leitura/worker

Somente PostgreSQL próprio 127.0.0.1:55439, usuário orders_lab. Fonte `orders_lab`,
destino novo `orders_restore_lab_stock`; dump privado em `.orders-lab` (não versionado).
Servidores/consumidores da fonte parados durante snapshot. Não usa serviços reais.
Reusa a camada 1 de `docs/guides/backup-and-restore.md`; livros não passam pelo import XLSX.

Ensaio executado sobre código e5fae331e e base anterior arquivada 5a3383c9:

1. `seed.py` via launcher isolado `.orders-lab/manage_lab.py shell`, com variáveis
   DATABASE_URL/REDIS_URL fixadas nas portas do laboratório. Acrescenta estados
   started/unknown/accepted e chaves permanentes in_progress/done, sem worker.
2. `seed_stock.py` pelo mesmo launcher: escritor canônico StockMovements,
   entrada 2,500 e saída 0,500; saldo 2,000. Primeira cópia tinha livro de estoque
   vazio; foi conservada em `orders_restore_lab` e repetida em outro destino populado.
3. `python restore.py orders_restore_lab_stock`: pg_dump -Fc, CREATE DATABASE novo,
   pg_restore --exit-on-error; recusa banco destino preexistente, não apaga banco.
4. `python probe.py <checkout-atual> current orders_restore_lab_stock` e
   `python probe.py <arquivo-base-5a3383c9> previous orders_restore_lab_stock`:
   lê pedidos/recibos novos com ambos os códigos; somente fake de envio, toda
   escrita da prova de incompatibilidade dentro de transação revertida.
5. `python verify.py orders_restore_lab_stock`: compara todas as linhas por
   SHA-256 e posições de todas as sequências; não imprime contatos/payloads.

Resultados: 140 tabelas, 129 sequências idênticas antes/depois e após probes;
44 pedidos, 43 Directives, 157 chaves, 7 entries de caixa, 7 intents/7 transações
Payman e 2 movimentos Stockman. Chave pendente permanece pendente; recibo aplicado
reproduz resultado sem execução. Fração e cache de Quant conferem com o livro.
Dump 635.722 bytes/0,231s; restore 0,672s. É volume sintético pequeno, não RTO real.

**Compatibilidade limitada:** ambos leem o JSON adicional; worker atual bloqueia
unknown (zero chamada fake), worker anterior tenta enviar (uma chamada fake).
Portanto “sem migration” não significa rollback de consumidor seguro. Preparação:
antes de ativar, parar/drenar todos os workers antigos; no rollback, preservar
banco/chaves e impedir consumo de efeitos incertos até reconciliação aprovada G03.
A mutação incompatível foi isolada em fake e revertida no ensaio; não foi criada
configuração de produção nem comprovada drenagem em ambiente real. G07 permanece
bloqueando deploy; convivência com navegador antigo e demais tópicos ainda exige
matriz própria. Não zerar filas, apagar chaves nem editar receipts para liberar retry.

Não houve DDL novo desde a base; este ensaio valida restore físico populado,
não transforma a aprovação de migration ausente/tag ausente em gate verde.
Ruff: aviso inicial C408 no script corrigido; comandos posteriores aprovados.
