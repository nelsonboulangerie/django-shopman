# WP08 — fotografia canônica somente de leitura

`snapshot.py 2026-09-11` usa PostgreSQL próprio orders_lab e transação
REPEATABLE READ, READ ONLY. Reutiliza `build_financial_reconciliation`, sem
persistir fechamento, criar alertas, executar worker ou corrigir livro.
Fonte340eefeac; dados sintéticos de várias rodadas, não coorte operacional.

Resultado:38 pedidos no dia,8 intents/8 transações; Payman12000 centavos e
caixa12000, diferença0. Um warning `day_closing_missing`: não houve fechamento
operacional e não foi inventado um para tornar o placar verde. Histórico geral:
346 recibos done/1 in_progress,33 tarefas done/16 queued/10 failed,76 tentativas.
O recibo in_progress e tarefas pendentes incluem fixtures deliberadas de falha;
a idade não as converte em falha conhecida nem autoriza replay.

Backlog aqui significa tarefas canônicas queued e devidas, não todos os efeitos
possivelmente devidos sem Directive. Restauro/perda de draft, stale/discard e
clareza/tempo humano permanecem não medidos neste coletor. Os limites são campos
explícitos do JSON. Labels exportados são estados/códigos do domínio; nenhum
texto de operador, token, endereço ou referência pessoal. Não há nova tabela,
fonte financeira, regra de conciliação ou endpoint.

Ruff aprovado; execução real do helper aprovada. Sem migration. Rollback remove
só este artefato; não apaga chaves, tarefas ou evidências. Qualquer uso de dados
reais requer autorização específica, não contemplada pelo script fixo de lab.
