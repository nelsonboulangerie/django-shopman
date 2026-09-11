# Execução técnica isolada — Storefront

**Candidata implementada; DoD técnico/G2 ainda não satisfeito.** PostgreSQL com conexões independentes e Chromium não iniciaram sob as restrições do ambiente. J01–J16 e acessibilidade assistiva não foram medidos. Nenhum piloto, rollout, produção, mensagem ou transação externa foi executado. Não se atribui ganho humano a testes automatizados.

Commit técnico: `83bf2dbb6f96f3dd9091ca356bfa240175c67c26`.

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
| W01 | Header canônico e alias; divergência 409; fingerprint; BFF verifica Origin original, cache pessoal e Retry-After; transporte H3 funcional e parsing estrito | Browser real+BFF+Django e borda não executados |
| W02 | Recuperação autorizada do recibo antes de exigir sacola aberta; total e revisão no caminho de selagem; efeito local+recibo atômicos | Locks PostgreSQL, morte real de processo e revisão D04 pendentes |
| W03 | Metadados e quantidade absoluta bloqueiam Session; recompra/oferta vinculam intenção à sacola; replay projeta sacola atual; replace mantém contexto | Matriz multiconexão completa e criação simultânea da primeira sacola não demonstradas |
| W04 | Draft v2 estrito, contexto opaco de identidade/sacola, limpeza na troca de pessoa; chave da tentativa persistida; consulta de recuperação; etiqueta via checkout existente | Duas abas/browser real; storage negado, foco e budgets humanos não medidos |
| W05 | Parcial/zero visíveis nas páginas existentes; nomes presentes/faltantes; resposta perdida conserva chave; replay de oferta já confirmada sobrevive expiração | Componentes testados; E2E visual e compreensão não demonstrados |
| W06 | Set explícito serializado, replay retorna preferência atual; aviso consulta revogação canônica; dedupe sob lock de canal; claim/aceite distintos; auditoria somente leitura | D03, concorrência PG, anonimização completa e reconciliação de legado pendentes; nenhuma limpeza/constraint destrutiva |
| W07 | Avaliação lê metadata atual sob lock; sucesso POST preservado se refresh falha; acompanhamento expõe pendência de conveniência | Matriz browser SSE/poll/teclado e acessibilidade não executada |
| W08 | Conveniência usa Directive/recibo por efeito; recuperação não refaz checkout; endereço/defaults respeitam contexto; claim remoto incerto gera alerta e não reenvia por idade | Falha após cada etapa de todos os consumidores downstream não coberta; reconciliação externa exige responsável |
| W09 | Mantidas superfícies e componentes existentes; confirmação e próxima leitura acessíveis no fluxo; protocolo de medição preservado no plano | J01–J16, VoiceOver/TalkBack, zoom, Maps/WhatsApp e pesquisa permanecem pendentes |
| W10 | Testes, build, ensaio aditivo de migração, auditoria de inscrições e runbook nesta entrega | PostgreSQL, browser, volume representativo, versões mistas/jobs em voo e rollback completo impedem fechar DoD |

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

- **H01:** riscos de read/merge corrigidos nos caminhos existentes; provas PG escritas mas não executadas. Responsável proposto: composição/estoque.
- **H02:** falha entre efeito local e recibo reproduzida e revertida em transação. `local_atomic` é opt-in; não se aplica promessa de exactly-once a efeitos externos. Consumidores antigos mantêm seus protocolos. Responsável: Core/integrações.
- **H03:** metadata concorrente e fronteira POST/refresh tratadas; browser pendente. Responsável: pedidos/frontend.
- **H04:** claim incerto não é aceite nem entrega. Retry simulado não chama adapter novamente; concorrência, anonimização e legado ainda exigem prova/decisão. Responsável: marketing/integrações.
- **H05:** transporte H3 verifica headers, 429, cookie host-only, no-store e origem estrangeira/irmã/null antes do upstream. Não demonstra explorabilidade da implantação ou comportamento real de SameSite/CORS/CDN. Responsável: plataforma.
- **H06:** tipos inválidos/fingerprint conflitante recusados sem efeito em casos testados; não é fuzzing exaustivo de todos os payloads. Responsável: API/frontend.
- **H07:** regressões existentes de lifecycle, pagamento, estoque, fiscal e courier executadas. Matriz de crash após cada estágio, compras paralelas com pontos e todos os providers não encerrada. Responsável: domínios.
- **H08/H09:** avaliação assistiva, esforço, compreensão, configuração e política pública continuam hipóteses/decisões humanas. Responsável: produto/operação.

D01–D06 continuam sem aprovação humana. Donos acima são papéis propostos, não pessoas designadas. Preservar opt-out canônico não inventa política de consentimento. A retenção provisória protege recibos com fingerprint já finalizados/em curso contra limpeza por idade; a janela definitiva, saneamento, unicidade de legado e contração dependem D03. Copy/budgets/coortes/plantão dependem das decisões do plano.

## Medição e observabilidade

O ensaio sintético de 24 alterações de quantidade por Django test client/SQLite teve 24 sucessos em ambas as bases. P95: baseline 44,66 ms; candidata 28,98 ms. O ambiente teve cargas diferentes: esses números **não são comparação causal**, não medem feedback visual de 100 ms nem experiência humana. Apenas cada amostra ficou abaixo de 1.500 ms. A/T/M/N/R, conclusão sem ajuda e compreensão financeira: **não medidos**, nunca zero presumido.

A recuperação de conveniência usa estados/tentativas/erro dos Directive existentes e OperatorAlert `checkout_convenience_pending`. Aviso com aceite desconhecido usa alerta existente; não se repete automaticamente pela idade. O comando `audit_storefront_subscriptions` retorna contagens, não PII e não faz mutações. Não foi criada instrumentação de sessão/PII ou analytics paralelo. Taxas de recuperação, conflitos, parciais apresentados e consentimento bloqueado ainda precisam integração aos painéis canônicos e dono de operação antes de G2; logs isolados não demonstram essas taxas.

## Migração, compatibilidade e recuo

1. Aplicar expansões `orderman.0005_idempotency_request_fingerprint` e `storefront.0003_stock_alert_dispatch_claim` no ambiente isolado antes do frontend. O ensaio usa MigrationExecutor, dados legados sintéticos e repetição da expansão: fingerprint legado vazio; claim/aceite legados nulos. Não infere entrega histórica.
2. Backend aceita `Idempotency-Key`, `X-Idempotency-Key` e body; valores divergentes são recusados. Checkout sem `expected_revision` recusa explicitamente: atualizar/recarregar frontend antes de confirmar, sem liberar a escrita insegura antiga. Campos de resposta são aditivos.
3. Draft v2 descarta PII legada sem atribuí-la a novo usuário. Consulta/recuperação preserva sessão e pedido do servidor. Nenhum backfill de opt-in ou envio retroativo.
4. Executar auditoria de subscriptions em banco sintético antes de discutir constraint. Não apagar duplicatas nem claims incertos. O teste reverso de schema é apenas fixture isolada, **não receita de downgrade operacional**.
5. Em recuo autorizado: conter novas entradas pelos controles existentes, manter leitura/recuperação e correções de integridade; pausar novos jobs afetados nos controles existentes; conferir cada Directive/Order em voo. Não apagar recibos, restaurar snapshot sobre transações novas, ressuscitar draft ou reativar opt-out. Não executar estorno/reemissão como rollback técnico.
6. Provider com resultado desconhecido: consultar mecanismo canônico/recibo, reconciliar com responsável antes de nova tentativa. Não marcar entregue por timeout nem transferir ao cliente a redigitação do pedido.
7. Antes de release: ensaiar versões mistas, jobs em voo, volume/locks e recuo em PostgreSQL. Este ensaio completo não foi realizado; G2 permanece fechado. Migração/desmigração em produção não autorizada.

## Reproduzir e fechar pendências

Python 3.12 do workspace; Node 22 via `/opt/homebrew/opt/node@22/bin`; dependências frontend instaladas pelo lockfile. O runner `scripts/run_storefront_operational_tests.py` prioriza os packages desta worktree e desabilita dotenv/Redis. Testes usam dados sintéticos e mocks; não apontar para serviço real.

```sh
python scripts/run_storefront_operational_tests.py shopman/storefront shopman/shop/tests/test_remote_mutations.py shopman/shop/tests/test_checkout_side_effects.py shopman/shop/tests/test_import_boundaries.py
python scripts/run_storefront_operational_tests.py --postgres-url postgresql://USER@127.0.0.1:PORT/DISPOSABLE_DB shopman/storefront/tests/test_operational_postgres.py shopman/storefront/tests/test_concurrent_checkout.py
```

No diretório `surfaces/storefront-nuxt`, executar sequencialmente `npm test -- --run --maxWorkers=2`, `npm run typecheck`, `npm run lint`, `npm run build`; depois browser em ambiente com IPC permitido. Não executar build e testes Nuxt simultaneamente, pois compartilham artefatos gerados. No `packages/orderman`, usar pytest com `orderman_test_settings`/pyproject próprio. Configurar todos os packages locais antes de executar outros consumidores.

Os bloqueios ambientais estão nos logs anexos: PostgreSQL falhou em `shmget` mesmo com mmap; Chromium recebeu `MachPortRendezvousServer ... Permission denied (1100)` antes de abrir página. Não se contornou a sandbox. Os testes PG marcados skip não contam como prova de concorrência.

Para fechar DoD: disponibilizar laboratório PostgreSQL/browser autorizado; completar matriz §8.2, acessibilidade e medições emparelhadas; obter revisão Core/consentimento, donos/limiares e ensaio de recuo; registrar pass/fail/skip sem omissões. Piloto, rollout e qualquer ação externa permanecem sujeitos a autorização explícita.

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
| PostgreSQL real | Bloqueado antes do banco estar disponível | [log](storefront-operational-20260910/postgres-blocked.txt) |
| Browser real | Bloqueado antes de abrir páginas | [log](storefront-operational-20260910/browser-blocked.txt) |

Os cinco skips da suíte Storefront são quatro testes multiconexão (duas provas novas, disputa de estoque e captura concorrente) e uma corrida de rate-limit. O consumidor de caixa também exige PG. Permanecem relevantes e bloqueiam W10. Os novos testes PG estão inscritos no **gate de runtime existente**, sem criar outro gate que transforme skips em aceite.

Uma tentativa frontend concorrente com build/typecheck teve timeouts de hooks/testes: [registro](storefront-operational-20260910/frontend-timeout-attempt.txt). A repetição isolada passou sem alterar timeouts ou enfraquecer oráculos. O guardrail textual de oferta foi limitado especificamente ao tipo de `skipped`, pois a nova lista de nomes adicionados é legitimamente string; os novos testes montam a página e verificam resultado/navegação.

A suíte ampla antecede a última proteção de recibo indeterminado vencido e a extensão de replay de oferta expirada; esses deltas recebem regressões direcionadas anexas. Não se afirma execução integral de todas as combinações do plano.
