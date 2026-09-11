# Execução técnica isolada — Storefront

**Implementação técnica candidata de W00–W10 concluída; aceite G2 ainda não satisfeito.** PostgreSQL 16, Redis 7 e Chromium executaram em laboratório local descartável, sem skips no gate de runtime nem no E2E. J01–J16, leitor de tela e as decisões D01–D06 continuam humanos e não foram inferidos. Nenhum piloto, rollout, produção, mensagem ou transação externa foi executado. Não se atribui ganho humano a testes automatizados.

Commits técnicos consolidados antes do fechamento: `83bf2dbb6`, `4708354f4` e `f106a58a4`.

## Proveniência e preservação

- Plano integral: [fonte congelada](../plans/STOREFRONT-OPERATIONAL-EXCELLENCE-PLAN-2026-09-10.md).
- `origin/main` revalidado: `88314ff0474ba35c6dc69f58bbc2700b545454a4`, consulta em 2026-09-11 01:04 UTC. Não havia diferença nas cadeias relevantes desde a base `3b8042a94` do plano.
- Worktree candidata: `/private/tmp/shopman-storefront-execution-20260910`, branch `codex/storefront-operational-excellence-20260910`.
- Repositório independente sem hardlinks: `/private/tmp/shopman-storefront-execution-repo-20260910`; baseline: `/private/tmp/shopman-storefront-baseline-88314ff0`.
- Checkout original em `b589e22c5`, branch `codex/shopman-backstage-marketing-hardening`, preservado, inclusive arquivos não rastreados de terceiros. Não foi feito reset, stash, push ou alteração nesse checkout.
- Foram mantidos Session/Order, revisão da Session, IdempotencyKey, Directive, OperatorAlert, preferências/consentimento Guestman e serviços canônicos de pagamento/estoque/fulfillment. Não há ledger, carrinho, cadastro de consentimento ou painel paralelo.

## Entrega e estado dos pacotes

“Implementado” abaixo descreve o diff; não significa gate aprovado.

| Pacote | Entrega técnica | Limite de aceite restante |
|---|---|---|
| W00 | Base congelada, consumidores inspecionados, reproduções E e baseline automatizado | Baseline humano J01–J16, donos nominais e protocolo de privacidade pendentes |
| W01 | Header canônico e alias; divergência 409; fingerprint; BFF verifica origem, cache pessoal e Retry-After; H3 e parsing estrito; BFF+Django exercitados | SameSite/CORS/CDN da implantação dependem de ambiente autorizado |
| W02 | Recuperação autorizada; total e revisão selados; efeito local+recibo atômicos; locks e replay concorrente em PostgreSQL | D04 e falha física de processo fora da injeção determinística pendentes |
| W03 | Metadados e quantidade absoluta bloqueiam Session; intenção vinculada à sacola; replay projeta estado atual | Criação simultânea da primeira sacola não foi isolada como cenário próprio |
| W04 | Draft v2, contexto opaco, limpeza entre pessoas, chave persistida, recuperação e etiqueta existentes | Duas abas e storage negado passaram em Chromium; esforço humano continua não medido |
| W05 | Parcial/zero/erro separados, faltantes nomeados e replay recuperável | Fluxos reais passaram; compreensão da mensagem exige avaliação humana |
| W06 | Set explícito, revogação antes do envio, dedupe/claim e auditoria existentes; corridas passaram em PostgreSQL | D03, anonimização completa e saneamento/constraint de legado pendentes |
| W07 | Metadata concorrente preservada; POST confirmado sobrevive falha de refresh; tracking existente mantido | Fluxos SSE/poll passaram; leitor de tela exige avaliação assistiva |
| W08 | Directive/recibo recupera só conveniência faltante; falhas após escrita revertem; resposta perdida não duplica | Providers externos e todas as etapas downstream exigem reconciliação/ambiente específico |
| W09 | Superfícies existentes preservadas; storage bloqueado, duas abas, teclado, viewport estreito e zoom 200% passaram | J01–J16, VoiceOver/TalkBack, Maps/WhatsApp e pesquisa permanecem pendentes |
| W10 | Runtime PostgreSQL+Redis, browser real, build, migração mista, volume sintético e runbook executados | Jobs reais em voo, recuo operacional, donos e aceite humano impedem G2 |

## Achados, hipóteses e decisões

| Achado | Antes na base congelada | Depois comprovado em laboratório |
|---|---|---|
| E01 | X-key ignorada, recompra podia devolver snapshot antigo | Alias chega ao servidor; nova intenção altera sacola real; replay não reaplica e consulta estado atual |
| E02 | Retry pós-201 retornava sacola vazia | Mesmo Order recuperável por POST/GET; cookie anterior e principal alheio cobertos por testes de autorização |
| E03 | Interleaving entre preço e selagem mudava total confirmado | Injeção determinística recusada sem Order; revisão diferente com mesmo total também recusada |
| E04 | Oferta/recompra ocultavam faltantes | Componentes mostram nomes e separam zero/parcial; falha técnica no segundo item reverte bundle e mantém itens anteriores |
| E05 | Draft global aceitava tipos inválidos/data futura/contexto alheio | Parser descarta legado ambíguo e contexto incompatível; identidade/sacola/força de autenticação derivam contexto opaco |
| E06 | Duas chamadas toggle invertiam a intenção | Estado explícito repetido permanece desligado; adapter legado preservado e serializado |
| E07 | Revogação global não impedia dispatcher de estoque | Mock do dispatcher recebe zero chamadas após revogação canônica |
| E08 | Conveniência falhava só em log | 201 preserva confirmação e expõe pendência; Directive recupera apenas efeito faltante e replay não duplica |

Os diagnósticos originais são assertivas de reprodução do defeito, portanto “passaram” na baseline. Os testes da candidata invertem os oráculos. E04 tem prova de componente, não browser. SQLite e injeção determinística não demonstram exclusão multiconexão.

- **H01:** riscos de read/merge corrigidos; duas conexões PostgreSQL preservaram campos independentes e a matriz de estoque não excedeu o disponível. Responsável proposto: composição/estoque.
- **H02:** falha entre efeito local e recibo reproduzida e revertida em transação. `local_atomic` é opt-in; não se aplica promessa de exactly-once a efeitos externos. Consumidores antigos mantêm seus protocolos. Responsável: Core/integrações.
- **H03:** metadata concorrente passou em PostgreSQL; fronteira POST/refresh e acompanhamento passaram no browser. Responsável: pedidos/frontend.
- **H04:** claim incerto não é aceite nem entrega. Concorrência/dedupe passaram em PostgreSQL; anonimização e legado ainda exigem decisão D03. Responsável: marketing/integrações.
- **H05:** transporte H3 verifica headers, 429, cookie host-only, no-store e origem estrangeira/irmã/null; BFF+Django passaram no Chromium. A implantação real de SameSite/CORS/CDN não foi exercitada. Responsável: plataforma.
- **H06:** tipos inválidos/fingerprint conflitante recusados sem efeito em casos testados; não é fuzzing exaustivo de todos os payloads. Responsável: API/frontend.
- **H07:** regressões de lifecycle, pagamento, estoque, fiscal, courier e concorrência passaram; a corrida revelou e corrigiu captura duplicada. Crash em cada provider, compras paralelas com pontos e todos os adapters não foram exauridos. Responsável: domínios.
- **H08:** storage negado, teclado, zoom e viewport estreito passaram em Chromium. Leitor de tela e tarefa humana continuam pendentes. **H09:** configuração e política pública continuam decisões humanas. Responsável: produto/operação.

D01–D06 continuam sem aprovação humana. Donos acima são papéis propostos, não pessoas designadas. Preservar opt-out canônico não inventa política de consentimento. A retenção provisória protege recibos com fingerprint já finalizados/em curso contra limpeza por idade; a janela definitiva, saneamento, unicidade de legado e contração dependem D03. Copy/budgets/coortes/plantão dependem das decisões do plano.

## Medição e observabilidade

O ensaio sintético de 24 alterações de quantidade por Django test client teve 24 sucessos em SQLite e em PostgreSQL. Na candidata PostgreSQL, p95 foi 36,41 ms e máximo 456,54 ms. As execuções não têm carga controlada e **não são comparação causal**; não medem feedback visual de 100 ms nem experiência humana. Cada amostra ficou abaixo de 1.500 ms. A/T/M/N/R, conclusão sem ajuda e compreensão financeira: **não medidos**, nunca zero presumido.

A recuperação de conveniência usa estados/tentativas/erro dos Directive existentes e OperatorAlert `checkout_convenience_pending`. Aviso com aceite desconhecido usa alerta existente; não se repete automaticamente pela idade. O comando `audit_storefront_subscriptions` retorna contagens, não PII e não faz mutações. Não foi criada instrumentação de sessão/PII ou analytics paralelo. Taxas de recuperação, conflitos, parciais apresentados e consentimento bloqueado ainda precisam integração aos painéis canônicos e dono de operação antes de G2; logs isolados não demonstram essas taxas.

## Migração, compatibilidade e recuo

1. Aplicar expansões `orderman.0005_idempotency_request_fingerprint`, `orderman.0006_idempotency_fingerprint_database_default` e `storefront.0003_stock_alert_dispatch_claim` no ambiente isolado antes do frontend. O ensaio usa MigrationExecutor, dados legados sintéticos e repetição da expansão: fingerprint legado vazio; claim/aceite legados nulos. Não infere entrega histórica.
2. Backend aceita `Idempotency-Key`, `X-Idempotency-Key` e body; valores divergentes são recusados. Checkout sem `expected_revision` recusa explicitamente: atualizar/recarregar frontend antes de confirmar, sem liberar a escrita insegura antiga. Campos de resposta são aditivos.
3. Draft v2 descarta PII legada sem atribuí-la a novo usuário. Consulta/recuperação preserva sessão e pedido do servidor. Nenhum backfill de opt-in ou envio retroativo.
4. Executar auditoria de subscriptions em banco sintético antes de discutir constraint. Não apagar duplicatas nem claims incertos. O teste reverso de schema é apenas fixture isolada, **não receita de downgrade operacional**.
5. Em recuo autorizado: conter novas entradas pelos controles existentes, manter leitura/recuperação e correções de integridade; pausar novos jobs afetados nos controles existentes; conferir cada Directive/Order em voo. Não apagar recibos, restaurar snapshot sobre transações novas, ressuscitar draft ou reativar opt-out. Não executar estorno/reemissão como rollback técnico.
6. Provider com resultado desconhecido: consultar mecanismo canônico/recibo, reconciliar com responsável antes de nova tentativa. Não marcar entregue por timeout nem transferir ao cliente a redigitação do pedido.
7. Versões de modelo mistas, 1.000 recibos, locks e migração aditiva passaram em PostgreSQL. Jobs reais em voo, volume produtivo e recuo operacional dependem de ambiente e responsáveis autorizados; G2 permanece fechado. Migração/desmigração em produção não autorizada.

## Reproduzir e fechar pendências

Python 3.12 do workspace; Node 22 via `/opt/homebrew/opt/node@22/bin`; dependências frontend instaladas pelo lockfile. O runner `scripts/run_storefront_operational_tests.py` prioriza os packages desta worktree e desabilita dotenv/Redis. Testes usam dados sintéticos e mocks; não apontar para serviço real.

```sh
python scripts/run_storefront_operational_tests.py shopman/storefront shopman/shop/tests/test_remote_mutations.py shopman/shop/tests/test_checkout_side_effects.py shopman/shop/tests/test_import_boundaries.py
python scripts/run_storefront_operational_tests.py --postgres-url postgresql://USER@127.0.0.1:PORT/DISPOSABLE_DB shopman/storefront/tests/test_operational_postgres.py shopman/storefront/tests/test_concurrent_checkout.py
```

No diretório `surfaces/storefront-nuxt`, executar sequencialmente `npm test -- --run --maxWorkers=2`, `npm run typecheck`, `npm run lint`, `npm run build`; depois `scripts/run_storefront_e2e.sh`. Não executar build e testes Nuxt simultaneamente, pois compartilham artefatos gerados. No `packages/orderman`, usar pytest com `orderman_test_settings`/pyproject próprio. Configurar todos os packages locais antes de executar outros consumidores.

Os bloqueios ambientais iniciais permanecem anexados como histórico e não contam como prova. A continuação usou serviços locais descartáveis autorizados e resolveu os skips relevantes no gate PostgreSQL+Redis.

Para fechar G2: completar acessibilidade assistiva e medições emparelhadas J01–J16; obter decisões D01–D06, revisão Core/consentimento, donos/limiares e ensaio de recuo com jobs em voo. Piloto, rollout e qualquer ação externa permanecem sujeitos a autorização explícita.

## Resultados executados

Os totais abaixo são execuções distintas, com sobreposição; não somar como cobertura única. [Evidências e hashes](storefront-operational-20260910/SHA256.json).

| Execução | Resultado | Evidência |
|---|---|---|
| Baseline Storefront + diagnósticos do defeito | 1.476 passed, 3 skipped | [log](storefront-operational-20260910/baseline-backend.txt) |
| Baseline frontend | 536 passed / 57 arquivos | [log](storefront-operational-20260910/baseline-frontend.txt) |
| Candidata Storefront + helper + conveniência + limites arquiteturais | 1.521 passed, 5 skipped | [log](storefront-operational-20260910/backend.txt) |
| Core Orderman, settings próprios | 291 passed | [log](storefront-operational-20260910/core.txt) |
| Consumidores downstream + corrida de rate-limit | 182 passed, 2 skipped | [log](storefront-operational-20260910/consumers.txt) |
| Frontend final, workers limitados | 548 passed / 59 arquivos | [log](storefront-operational-20260910/frontend.txt) |
| Intenções e migração | 25 passed | [log](storefront-operational-20260910/intentions-migration.txt) |
| Oferta expirada/replay e seleção PG | 14 passed, 4 skipped | [log](storefront-operational-20260910/offer-and-pg-skips.txt) |
| Recibo vencido indeterminado, helper e gate de runtime | 33 passed | [log](storefront-operational-20260910/receipts-runtime-gate.txt) |
| Typecheck / lint / build / schema | Exit 0; lint com 5 warnings existentes de ordem de atributos em WhatsappVerifyPanel; schema sem drift | [typecheck](storefront-operational-20260910/typecheck.txt), [lint](storefront-operational-20260910/lint.txt), [build](storefront-operational-20260910/build.txt), [schema](storefront-operational-20260910/schema.txt) |
| PostgreSQL 16 + Redis 7, gate de runtime | 334 passed, 0 skipped; 4 warnings | [log](storefront-operational-20260910/continuation-postgres-redis-runtime.txt) |
| Migração mista PostgreSQL, 1.000 recibos | 1 passed | [log](storefront-operational-20260910/continuation-postgres-migration.txt) |
| Budget de mutação PostgreSQL | 24/24; p95 36,41 ms; máx. 456,54 ms | [log](storefront-operational-20260910/continuation-postgres-budget.txt) |
| Browser mock-server | 4 passed | [log](storefront-operational-20260910/continuation-browser-mock-server.txt) |
| Chromium real + Nuxt BFF + Django | 27 passed | [log](storefront-operational-20260910/continuation-browser-final.txt) |

Os cinco skips da suíte SQLite são testes PostgreSQL. Todos estão inscritos no **gate de runtime existente**, que passou com 334 testes e rejeita qualquer skip. O teardown reportou cinco conexões ainda abertas e não removeu imediatamente o banco temporário; após o processo encerrar, não havia sessões e o banco de teste foi removido explicitamente. Isso é uma advertência de limpeza do laboratório, não um skip oculto.

Uma tentativa frontend concorrente com build/typecheck teve timeouts de hooks/testes: [registro](storefront-operational-20260910/frontend-timeout-attempt.txt). A repetição isolada passou sem alterar timeouts ou enfraquecer oráculos. O guardrail textual de oferta foi limitado especificamente ao tipo de `skipped`, pois a nova lista de nomes adicionados é legitimamente string; os novos testes montam a página e verificam resultado/navegação.

A suíte ampla antecede a última proteção de recibo indeterminado vencido e a extensão de replay de oferta expirada; esses deltas recebem regressões direcionadas anexas. Não se afirma execução integral de todas as combinações do plano.


## Continuação autorizada — 2026-09-11

A revisão da candidata encontrou e corrigiu duas falhas adicionais, comprovadas antes da alteração:

1. **Conveniência incompleta:** endereço novo era persistido, mas seu identificador não entrava nos defaults. A composição agora resolve o endereço pelo cadastro canônico do próprio cliente e salva o identificador. Se o endereço ainda não foi salvo, o Directive de defaults permanece recuperável; não conclui silenciosamente a promessa. [Reprodução anterior](storefront-operational-20260910/continuation-convenience-before.txt).
2. **Expansão incompatível com worker antigo:** o default apenas no ORM deixava um INSERT da versão antiga falhar com NOT NULL no fingerprint. A migração incremental `orderman.0006` define default vazio também no banco, inclusive para laboratórios que aplicaram 0005. Não inventa fingerprint legado. [Reprodução anterior](storefront-operational-20260910/continuation-mixed-before.txt).

As regressões novas executam efeitos locais reais de nome do cliente, endereço/etiqueta e defaults; injetam falha após a escrita, verificam rollback, recuperam e simulam perda de resposta repetindo o mesmo efeito. Também verificam que preferência explícita posterior prevalece e que falha do endereço adia defaults, recuperando somente os efeitos faltantes.

O ensaio de schema passou com 1.000 recibos sintéticos, INSERT pelo modelo histórico após expansão e UPDATE pelo modelo histórico sobre recibo novo, preservando fingerprint e resposta em SQLite e PostgreSQL. Isso prova recuo de código compatível mantendo schema expandido; não prova interrupção DDL sob volume produtivo nem rollout real de processos mistos.

| Verificação da continuação | Resultado |
|---|---|
| Storefront, conveniência, recibos e fronteiras | [1.529 passed, 5 skipped PG](storefront-operational-20260910/continuation-backend.txt) |
| Core Orderman | [291 passed](storefront-operational-20260910/continuation-core.txt) |
| Fidelidade, directives, fiscal e fases duráveis | [64 passed, 1 skipped PG](storefront-operational-20260910/continuation-downstream.txt) |
| Recuperação e migração/versões mistas, seleção final | [7 passed](storefront-operational-20260910/continuation-mixed-after.txt) |
| Drift de migrações | [Sem mudanças faltantes](storefront-operational-20260910/continuation-schema.txt) |

### Fechamento técnico autônomo

A execução ampliada comprovou dois defeitos adicionais antes da correção:

1. **Captura concorrente:** dois workers passavam juntos pela consulta Payman e chamavam o adapter duas vezes. A prova anterior contou duas capturas. O serviço agora serializa a consulta final e a chamada pelo lock da `Order` canônica; duas conexões convergem para uma chamada e um `transaction_id`. Isso não transforma aceite remoto seguido de crash em exactly-once: esse caso continua exigindo consulta/reconciliação do provider. [Antes](storefront-operational-20260910/continuation-postgres-race-before.txt) e [depois](storefront-operational-20260910/continuation-postgres-payment-after.txt).
2. **Navegação/storage:** uma navegação logo após “Adicionar” podia abortar a primeira requisição e perder o cookie da sacola; Web Storage bloqueado derrubava o módulo de tema antes da aplicação. A navegação Nuxt agora aguarda a fila canônica do carrinho, e o módulo de tema usa seu backend de cookie suportado. O E2E comprova navegação imediata, storage negado e retomada em segunda aba. [Falha anterior](storefront-operational-20260910/continuation-browser-before.txt) e [27 cenários finais](storefront-operational-20260910/continuation-browser-final.txt).

| Gate final | Resultado |
|---|---|
| Storefront, serviços, recuperação e fronteiras em SQLite | [1.644 passed, 5 skips exclusivamente PostgreSQL](storefront-operational-20260910/continuation-backend-final.txt) |
| Gate PostgreSQL+Redis, incluindo concorrência/estoque/pagamento/webhook/caixa | [334 passed, 0 skipped](storefront-operational-20260910/continuation-postgres-redis-runtime.txt) |
| Orderman isolado | [291 passed](storefront-operational-20260910/continuation-core-final.txt) |
| Frontend unitário | [548 passed / 59 arquivos](storefront-operational-20260910/continuation-frontend-final.txt) |
| Frontend typecheck/lint | [Typecheck passou](storefront-operational-20260910/continuation-frontend-typecheck.txt); [lint 0 erros e 5 warnings preexistentes](storefront-operational-20260910/continuation-frontend-lint.txt) |
| Build + Chromium + BFF + Django | [Build passou; E2E 27 passed](storefront-operational-20260910/continuation-browser-final.txt) |

O diff técnico autorizado está concluído. Permanecem fora dele e sem autorização: piloto/rollout/produção; mensagens, cobranças ou transações externas; D01–D06; J01–J16 com pessoas; VoiceOver/TalkBack; Maps/WhatsApp reais; volume e jobs produtivos em voo; revisão/aceite dos donos propostos. Não se alega ganho humano a partir destes testes.
