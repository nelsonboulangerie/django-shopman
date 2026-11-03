# CAS dos desfechos de diretivas

## Defeito confirmado e correção

A #2003 protegeu o worker, mas deixou expressamente de fora o despacho inline (`orderman/dispatch.py`) e a recuperação por `customer_orders.py`. Depois que o reaper revogava uma execução e outro executor reivindicava a diretiva, os caminhos antigos ainda gravavam sucesso, falha ou retry usando a instância antiga. Isso apagava o status e o erro do executor novo.

O desfecho agora usa o mesmo `orderman.claims.save_if_claimed` nos três consumidores. A gravação lê a linha sob `select_for_update` e compara a ficha `(attempts, started_at)` capturada antes do handler. Se o reaper a revogou, nenhuma coluna é escrita. O claim inline e sua leitura ficam na mesma transação para não capturar acidentalmente a ficha de outro executor entre o UPDATE e o refresh.

A gravação continua usando `save()`, mantendo os signals e as decisões de adiamento dos handlers. O despacho inline só chama o observador de falha terminal quando conseguiu gravar o desfecho da própria execução. A alteração não torna efeitos externos exactly-once: a diretiva continua at-least-once e handlers precisam preservar sua idempotência.

## Prova de concorrência

`shopman/shop/tests/test_directive_claims_postgres.py` exerce os dois consumidores em conexão independente. O handler antigo fica suspenso, a conexão principal executa o reaper real e, em metade dos casos, simula o claim seguinte. Depois libera o handler antigo para sucesso, falha terminal, falha transitória ou exceção inesperada. Confere integralmente status, attempts, started_at, available_at, error_code e last_error, além de não emitir observador terminal de execução perdida.

O arquivo está incluído em `scripts/run_runtime_tests.py`, que executa contra PostgreSQL e reprova skips. A suíte SQLite não é apresentada como prova de locks.

Antes/depois: com os dois consumidores originais de `0dc8b733`, 14 dos 16 casos falham e 2 passam. Com a correção, todos passam. Os trechos finais das saídas e invocações estão em `validation.txt`.

## Ambiente de validação

PostgreSQL 16 local, cluster exclusivo com UTF8, porta temporária em loopback e banco `directive_cas`. Nenhum banco do alpha, pool ou dado vivo foi usado. A primeira montagem local usou SQL_ASCII e falhou nas migrações; o cluster foi recriado com UTF8 antes de medir a correção. O `.venv` compartilhado tem incompatibilidade entre psycopg e psycopg-binary (`wait_c`/`timeout`); `PSYCOPG_IMPL=python` isolou o driver para estes ensaios, sem modificar o ambiente compartilhado. O PYTHONPATH apontou explicitamente para este worktree e seus pacotes.

## WP-RELEASE-01 R0/R1

Não foi aberta uma segunda implementação. R1 das imagens foi entregue pela #2076; contrato, ADR-043, inventário gerado, `/health/release` e sonda de identidade foram entregues pela #2080 em 02/11. O estado atual do WP e de `docs/reference/release-contract.md` confirma R0/R1 entregues e R2 em diante abertos. A conferência leu o código desses arquivos e executou o inventário e os testes existentes de identidade/inventário. Esta PR não avança promoção, coortes ou rollback por release set.
