# Avanço da coordenação — correções locais de integração

Atualiza o diagnóstico de [coordenação de entregas](COORDENACAO-ENTREGAS-2026-09-13.md). Nenhum merge, deploy, alteração de configuração produtiva ou retomada de sessão foi realizado.

## Correções concluídas

1. **PostgreSQL / unificação de clientes:** reproduzidos os dois erros `FOR UPDATE is not allowed with DISTINCT clause` na base `f8658f374`. O filtro de pedidos usa apenas campos/JSON da própria tabela; removido o `DISTINCT` redundante, preservando o lock. Regressão estendida para múltiplos critérios identificarem um único pedido, snapshot único, preservação de pedido alheio e restauração por undo. **77 testes aprovados no PostgreSQL** após a correção.
2. **CI de Maps:** preservada a correção anterior dos três bloqueios do #613 — registro E023, helper fora da camada de escrita e credenciais sintéticas separadas. **27 testes aprovados** na execução anterior.
3. **Fixture de deploy do conjunto:** o novo E022 corretamente rejeitava os provedores fictícios do CI, que não explicitava staging. O workflow agora declara staging nesse fixture e executa, em etapa própria, os contratos que exigem rejeição de provedores/chaves inseguros em produção. **10 testes aprovados**; `manage.py check --deploy` do fixture retorna 0, com avisos do ambiente sintético. Essa validação não atesta credenciais reais nem elimina os avisos de staging.
4. **Fronteira arquitetural do E022:** a montagem conjunta revelou import direto do Backstage em `shop/checks.py`, proibido pelo teste arquitetural existente. Introduzido `shop/adapters/provider_readiness.py` como ponto de integração; nenhum teste ou exceção de arquitetura foi relaxado.

## Validação conjunta

Montagem isolada: `/private/tmp/shopman-coordination-release-20260913`.
Branch: `codex/coordination-release-validation-20260913`.
Head: `d918f6c51c4bdd1a7ed9e384de0d593fa9a037c3`.
Base: montagem anterior do laudo `126b6095daedadd42dd5c10a1148d54131a9a99f`.

A primeira execução ampla teve 787 testes aprovados, 11 subtestes e uma falha de arquitetura (item 4), agora corrigida. A rodada final usa banco PostgreSQL recriado, os testes `test_pos*.py` de Shop e Backstage, MergeService, credenciais Maps, catálogo dos IDs de checks, fronteiras de import e gates de provedores.

**Rodada final: 791 testes e 11 subtestes aprovados no PostgreSQL, sem falhas, em 139,10 segundos.** Ruff e `git diff --check` aprovados. O CI remoto ainda não foi executado nos novos commits. Os números das rodadas direcionadas não devem ser somados a este total como testes únicos.

Nenhum banco de aplicação ou de outra sessão foi usado para escrita. Bases de teste exclusivas: `test_shopman_coord_sql_20260913`, `test_shopman_coord_release_20260913` e `test_shopman_coord_guard_20260913`. O fixture de deploy só leu a base de teste SQL própria. Imports dos pacotes foram fixados na respectiva cópia de código por `PYTHONPATH` explícito.

## Artefatos e aplicação

| Patch | Destino / dependência |
|---|---|
| [0001 — Maps](../../output/coordination-20260913/0001-fix-maps-ci-contracts.patch) | Head `03bf0eb20` do #613. Commit original `e2e3e00b7` |
| [0002 — SQL](../../output/coordination-20260913/0002-fix-customer-merge-postgresql.patch) | Base main `f8658f374`. Commit original `76f14a7f0`; independente do laudo |
| [0003 — fixture de deploy](../../output/coordination-20260913/0003-fix-integrated-deploy-fixture.patch) | Integração com o gate de produção E022 e Maps. Commit `bb0b53527` |
| [0004 — fronteira E022](../../output/coordination-20260913/0004-fix-provider-readiness-boundary.patch) | Requer o check E022 do lote de produção. Commit `d918f6c51` |

[Descrição pronta do PR SQL](../../output/coordination-20260913/pr-customer-merge-postgresql.md).

A incorporação do patch Maps ao conjunto exigiu apenas preservar as duas linhas E022 e E023 no cabeçalho de checks. Os dois registros e suas regras foram mantidos. Os commits de integração correspondentes são `30d079883` (Maps) e `6e55ea3e0` (SQL).

Antes de aplicar em outra base, revalidar head e diff; não substituir branches inteiras. Os patches não significam PRs abertos. A próxima etapa externa é publicar os commits nos destinos corretos, executar CI e revisar a sequência de release registrada no relatório principal. As decisões da seção C permanecem adiadas.
