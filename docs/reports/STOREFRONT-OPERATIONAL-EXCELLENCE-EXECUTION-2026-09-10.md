# Execução técnica isolada — Storefront

**Implementação técnica candidata de W00–W10 concluída; aceite G2 ainda não satisfeito.** PostgreSQL 16, Redis 7 e Chromium executaram em laboratório local descartável, sem skips no gate de runtime nem no E2E. O piloto sintético e a inspeção manual de navegador/árvore de acessibilidade estão registrados abaixo. D01–D06 foram aprovadas pelo solicitante em 2026-09-11, com responsabilidade assumida e retenção definitiva pendente sob a proteção atual. Houve uma exploração humana assistida em iPhone com VoiceOver e um percurso humano assistido de uso geral/aparelho compartilhado; neste último, a sacola permaneceu e nenhum dado pessoal da pessoa anterior reapareceu. TalkBack foi adiado pelo solicitante. Somente o deployment de rename expressamente autorizado foi executado; não houve rollout de código, promoção de configuração, mensagem ou transação externa. Não se atribui ganho humano a testes automatizados ou às observações assistidas.

O histórico completo e auditável está entre a `main` do GitHub em `1138c95eee0862630330328cf3bfe2f0b6424796` e a branch candidata.

## Proveniência e preservação

- Plano integral: [fonte congelada](../plans/STOREFRONT-OPERATIONAL-EXCELLENCE-PLAN-2026-09-10.md).
- Base congelada inicial: `88314ff0474ba35c6dc69f58bbc2700b545454a4`. A referência local chamada `origin/main` estava recuada e não representava o GitHub. A `main` do GitHub foi buscada diretamente em 2026-09-11 e apontava para `1138c95eee0862630330328cf3bfe2f0b6424796`, com 248 commits ausentes da candidata. Os 18 commits da execução foram rebaseados sobre essa referência; conflitos foram resolvidos preservando os contratos operacionais mais recentes da `main` e incorporando os requisitos ainda necessários desta execução.
- Worktree candidata: `/private/tmp/shopman-storefront-execution-20260910`, branch `codex/storefront-operational-excellence-20260910`.
- Repositório independente sem hardlinks: `/private/tmp/shopman-storefront-execution-repo-20260910`; baseline: `/private/tmp/shopman-storefront-baseline-88314ff0`.
- Checkout original em `b589e22c5`, branch `codex/shopman-backstage-marketing-hardening`, preservado, inclusive arquivos não rastreados de terceiros. Não foi feito reset, stash, push ou alteração nesse checkout.
- Foram mantidos Session/Order, revisão da Session, IdempotencyKey, Directive, OperatorAlert, preferências/consentimento Guestman e serviços canônicos de pagamento/estoque/fulfillment. Não há ledger, carrinho, cadastro de consentimento ou painel paralelo.

## Entrega e estado dos pacotes

“Implementado” abaixo descreve o diff; não significa gate aprovado.

| Pacote | Entrega técnica | Limite de aceite restante |
|---|---|---|
| W00 | Base congelada, consumidores inspecionados, reproduções E, baseline automatizado e responsabilidades assumidas | Baseline humano J01–J16 permanece pendente; J06 foi observado somente na candidata |
| W01 | Header canônico e alias; divergência 409; fingerprint; BFF verifica origem, cache pessoal e Retry-After; H3 e parsing estrito; BFF+Django exercitados | SameSite/CORS/CDN da implantação dependem de ambiente autorizado |
| W02 | Recuperação autorizada; total e revisão selados; efeito local+recibo atômicos; locks e replay concorrente em PostgreSQL; D04 aprovada | Falha física de processo fora da injeção determinística pendente |
| W03 | Metadados e quantidade absoluta bloqueiam Session; intenção vinculada à sacola; replay projeta estado atual | Criação simultânea da primeira sacola não foi isolada como cenário próprio |
| W04 | Draft v2, contexto opaco, limpeza entre pessoas, chave persistida, recuperação e etiqueta existentes; iPhone compartilhado preservou a sacola e não expôs nome/endereço anteriores | Duas abas e storage negado passaram em Chromium; esforço humano e comparação com a base continuam não medidos |
| W05 | Parcial/zero/erro separados, faltantes nomeados e replay recuperável | Fluxos reais passaram; compreensão da mensagem exige avaliação humana |
| W06 | Set explícito, revogação antes do envio, dedupe/claim e auditoria existentes; corridas passaram em PostgreSQL; precedência de consentimento D03 aprovada | Retenção definitiva, auditoria produtiva de legado e eventual contração permanecem pendentes |
| W07 | Metadata concorrente preservada; POST confirmado sobrevive falha de refresh; tracking existente mantido | Fluxos SSE/poll passaram; leitor de tela exige avaliação assistiva |
| W08 | Directive/recibo recupera só conveniência faltante; falhas após escrita revertem; resposta perdida não duplica | Providers externos e todas as etapas downstream exigem reconciliação/ambiente específico |
| W09 | Superfícies existentes preservadas; storage bloqueado, duas abas, teclado, viewport estreito, zoom 200% e inspeção manual da árvore de acessibilidade passaram; exploração assistida em iPhone permitiu alguma navegação com VoiceOver; J06 passou na candidata em iPhone compartilhado | Demais J01–J16 estruturadas, baseline contrabalançada, TalkBack e Maps/WhatsApp reais permanecem pendentes; as observações não mediram conclusão sem ajuda nem compreensão |
| W10 | Runtime PostgreSQL+Redis, browser real, build, migração mista, recuo de código com tentativa em voo, volume sintético, runbook e decisões D01–D06 concluídos | Jobs e recuo no ambiente real dependem de autorização; medição humana ainda impede G2 |

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
| E09 · pós-plano | O HTML vivo de `menu.*` não enviava CSP, HSTS, `nosniff`, proteção de frame, política de referência ou de permissões | Middleware Nitro aplica a política à resposta inteira; HTTP local omite HSTS e HTTPS o inclui; unitário, build e browser passaram com Google Maps/Stripe permitidos |
| E10 · teste humano | Após expirar o hold, a sacola perguntava disponibilidade no fim do horizonte; Croissant fresco de validade zero aparecia disponível no cardápio e bloqueado na sacola | Sacola e decisão sem data escolhem hoje ou a primeira fornada elegível pela fonte canônica; a sessão original voltou a checkout e a regressão passou |

Os diagnósticos originais são assertivas de reprodução do defeito, portanto “passaram” na baseline. Os testes da candidata invertem os oráculos. E04 tem prova de componente, não browser. SQLite e injeção determinística não demonstram exclusão multiconexão.

- **H01:** riscos de read/merge corrigidos; duas conexões PostgreSQL preservaram campos independentes e a matriz de estoque não excedeu o disponível. Responsável proposto: composição/estoque.
- **H02:** falha entre efeito local e recibo reproduzida e revertida em transação. `local_atomic` é opt-in; não se aplica promessa de exactly-once a efeitos externos. Consumidores antigos mantêm seus protocolos. Responsável: Core/integrações.
- **H03:** metadata concorrente passou em PostgreSQL; fronteira POST/refresh e acompanhamento passaram no browser. Responsável: pedidos/frontend.
- **H04:** claim incerto não é aceite nem entrega. Concorrência/dedupe passaram em PostgreSQL; a política D03 foi aprovada. Retenção definitiva, anonimização/contração e legado produtivo continuam dependentes de auditoria específica. Responsável: marketing/integrações.
- **H05:** transporte H3 verifica headers, 429, cookie host-only, no-store e origem estrangeira/irmã/null; BFF+Django passaram no Chromium. A implantação real de SameSite/CORS/CDN não foi exercitada. Responsável: plataforma.
- **H06:** tipos inválidos/fingerprint conflitante recusados sem efeito em casos testados; não é fuzzing exaustivo de todos os payloads. Responsável: API/frontend.
- **H07:** regressões de lifecycle, pagamento, estoque, fiscal, courier e concorrência passaram; a corrida revelou e corrigiu captura duplicada. Crash em cada provider, compras paralelas com pontos e todos os adapters não foram exauridos. Responsável: domínios.
- **H08:** storage negado, teclado, zoom e viewport estreito passaram em Chromium. Em exploração humana assistida, o solicitante relatou alguma navegação com VoiceOver; não completou o gesto de quatro dedos ensinado para posicionar o cursor e encerrou a sessão. Em uso geral no mesmo iPhone, uma pessoa sintética saiu e outra entrou: a sacola persistiu, enquanto nome, endereço e instrução anteriores não reapareceram. O percurso teve orientação e não substitui as jornadas estruturadas nem uma pessoa usuária de tecnologia assistiva.
- **H09:** a leitura de metadados do App Platform comprovou que `menu.nelsonboulangerie.com.br` é o domínio primário e definitivo, conforme confirmado pelo solicitante. O app único foi renomeado para `shopman-nelson` e ainda usa perfil de pre-go-live: ambiente `staging`, Pix mock, OTP debug e captura mock expostos. O componente `web` é comprovadamente o backend Django/Daphne; `storefront-nuxt` já é outro componente e a decisão foi manter `web`. Responsável: produto/operação.

D01–D06 foram aprovadas em 2026-09-11 pelo solicitante, que assumiu todos os papéis responsáveis. A retenção definitiva ficou expressamente pendente, mantendo-se a proteção atual: recibos vinculados já finalizados/em curso não são limpos por idade; a janela definitiva, auditoria produtiva, saneamento e eventual contração exigem decisão posterior. Essa aprovação não autoriza exposição externa.

### Decisões registradas

As propostas abaixo consolidam D01–D06 sem criar contrato, regra ou fonte de verdade adicional. A aprovação deve ser registrada nesta seção; autorização de decisão não autoriza produção, rollout, mensagens, cobranças ou transações reais.

| Decisão | Recomendação concreta | Estado em 2026-09-11 |
|---|---|---|
| D01 · Produto/operação | Adotar os budgets do §6 do plano: feedback local p95 ≤100 ms; estado pendente acessível ≤300 ms; mutação local p95 ≤1,5 s; reconciliação consultável ≤5 s depois de backend/recibo disponível; fallback de tracking ≤30 s. Ao detectar dependência remota indisponível, em até 2 s manter a mesma tentativa e usar a copy canônica já implementada: “A confirmação ainda está em consulta. Mantenha esta tentativa.” | Aprovada; responsabilidade assumida pelo solicitante. |
| D02 · Dono/operação | Preservar adição direta quando explicitamente rotulada. Resultado parcial nomeia adicionados e faltantes; zero itens e erro técnico não são sucesso. Troca de sacola, SKU, substituto ou pontos sempre exige escolha explícita. Janela, prazo e suporte continuam vindo da configuração canônica. | Aprovada; responsabilidade assumida pelo solicitante. |
| D03 · Privacidade/marketing | Revogação global posterior prevalece sobre inscrição específica e silencia envio/retry; falha ao consultar elegibilidade também silencia. Novo opt-in exige escolha inequívoca; histórico não é reinterpretado. Recibos vinculados e claims incertos permanecem protegidos de limpeza por idade até reconciliação e janela aprovadas; o default de sete dias continua apenas para recibos descartáveis. | Política aprovada; responsabilidade assumida. Retenção definitiva permanece pendente e a proteção atual foi mantida. |
| D04 · Core/pagamento/estoque | Aprovar C01–C06 e o diff testado: Session/Order/IdempotencyKey/Directive e serviços de domínio continuam canônicos; não há bypass, ledger ou estado financeiro paralelo. Resultado remoto desconhecido exige consulta/reconciliação antes de retry. | Aprovada; responsabilidade assumida pelo solicitante. |
| D05 · Produto/pesquisa | Por orientação posterior de reduzir a amostra, usar o mínimo defensável de 3 participantes com fixtures sintéticas: um percurso com VoiceOver, um com TalkBack e um de uso geral/aparelho compartilhado. Distribuir J01–J16, incluir cliente novo e recorrente e contrabalançar base/candidata. | Recorte mínimo definido em 2026-09-11; participantes/dispositivos ainda não disponibilizados. É triagem qualitativa e não demonstra a meta populacional de ≥90%. |
| D06 · Operação/release | Adotar as paradas do plano: qualquer duplicidade não reconciliada, valor não confirmado, PII cruzada, opt-out violado ou ação financeira bem-sucedida apresentada como falha interrompe exposição. Degradação repetida de budget, ajuda ou abandono impede expansão. Após resultado humano e nova autorização, progressão proposta: coorte pequena → 25% → 50% → 100%, mínimo de 48 h e 30 jornadas elegíveis por etapa. | Critérios aprovados e responsabilidade assumida; cada piloto real/etapa continua exigindo autorização explícita. |

**Registro de decisão — 2026-09-11:** “Aprovo D01–D06 como proposto, com retenção definitiva pendente e proteção atual mantida. Assumo os papéis responsáveis.”

O horizonte de dois dias da fila remota é uma política anterior a este plano. O histórico registra sua introdução no commit `818802183` e sua ativação explícita no seed/migração pelo commit `d40b9388b`, ambos sob autoria de Pablo Valentini; o primeiro registra coautoria do Claude Opus 5. A fila é útil apenas para reservar capacidade de fornada já planejada dentro da janela. Não há medição que justifique especificamente dois dias, portanto sua duração permanece decisão operacional pendente; a candidata preserva o valor existente e corrige somente o uso técnico incorreto do horizonte.

### Protocolo de observação humana preparado

1. Usar somente o ambiente isolado e fixtures sintéticas. Alternar qual versão vem primeiro e não explicar a interface antes da tentativa.
2. Distribuir J01–J16 entre 3 participantes, cobrindo cada jornada ao menos uma vez: VoiceOver, TalkBack e uso geral/aparelho compartilhado. Todos respondem, após estados confirmado, parcial e indeterminado: “foi pedido/pago?”, “o que faltou?” e “como continuar?”. Não forçar falha de cobrança real.
3. Em cada tentativa registrar versão, jornada, dispositivo, leitor de tela quando aplicável, conclusão, abandono, ajuda, tempo ativo e A/T/M/N/R. Anotações não contêm nome, telefone, endereço, OTP, pagamento, cookies ou chaves. Vídeo é opcional e requer consentimento específico.
4. No VoiceOver e no TalkBack, verificar ordem do foco, nome/estado dos controles, anúncio de erro/pendência/resultado e conclusão da próxima ação sem referência visual. Teclado, zoom e storage negado já têm prova automatizada, mas continuam no roteiro humano de J16.
5. Com 3 pessoas, exigir 3/3 sem falha crítica para aceitar apenas a triagem qualitativa. Essa amostra não estima nem comprova a meta populacional de ≥90% do plano. Qualquer compreensão financeira grave, PII cruzada, opt-out violado ou duplicidade não reconciliada reprova a expansão; rollout continua dependente de evidência mais ampla e autorização específica.
6. Registrar os resultados e limites da amostra neste mesmo relatório. Ausência de evento, observação ou resposta conta como dado ausente; nunca como sucesso. A amostra é qualitativa e não sustenta alegação populacional.

## Medição e observabilidade

O ensaio sintético de 24 alterações de quantidade por Django test client teve 24 sucessos em SQLite e em PostgreSQL. Na candidata PostgreSQL, p95 foi 36,41 ms e máximo 456,54 ms. As execuções não têm carga controlada e **não são comparação causal**; não medem feedback visual de 100 ms nem experiência humana. Cada amostra ficou abaixo de 1.500 ms. A/T/M/N/R, conclusão sem ajuda e compreensão financeira: **não medidos**, nunca zero presumido.

A recuperação de conveniência usa estados/tentativas/erro dos Directive existentes e OperatorAlert `checkout_convenience_pending`. Aviso com aceite desconhecido usa alerta existente; não se repete automaticamente pela idade. O comando `audit_storefront_subscriptions` retorna contagens, não PII e não faz mutações. Não foi criada instrumentação de sessão/PII ou analytics paralelo. Taxas de recuperação, conflitos, parciais apresentados e consentimento bloqueado ainda precisam integração aos painéis canônicos e dono de operação antes de G2; logs isolados não demonstram essas taxas.

## Migração, compatibilidade e recuo

1. Aplicar expansões `orderman.0005_idempotency_request_fingerprint`, `orderman.0006_idempotency_fingerprint_database_default` e `storefront.0004_stock_alert_dispatch_claim` no ambiente isolado antes do frontend. O ensaio parte das migrações imediatamente anteriores, usa MigrationExecutor, dados legados sintéticos e repetição da expansão: fingerprint legado vazio; claim/aceite legados nulos. Não infere entrega histórica.
2. Backend aceita `Idempotency-Key`, `X-Idempotency-Key` e body; valores divergentes são recusados. Checkout sem `expected_revision` recusa explicitamente: atualizar/recarregar frontend antes de confirmar, sem liberar a escrita insegura antiga. Campos de resposta são aditivos.
3. Draft v2 descarta PII legada sem atribuí-la a novo usuário. Consulta/recuperação preserva sessão e pedido do servidor. Nenhum backfill de opt-in ou envio retroativo.
4. Executar auditoria de subscriptions em banco sintético antes de discutir constraint. Não apagar duplicatas nem claims incertos. O teste reverso de schema é apenas fixture isolada, **não receita de downgrade operacional**.
5. Em recuo autorizado: conter novas entradas pelos controles existentes, manter leitura/recuperação e correções de integridade; pausar novos jobs afetados nos controles existentes; conferir cada Directive/Order em voo. Não apagar recibos, restaurar snapshot sobre transações novas, ressuscitar draft ou reativar opt-out. Não executar estorno/reemissão como rollback técnico.
6. Provider com resultado desconhecido: consultar mecanismo canônico/recibo, reconciliar com responsável antes de nova tentativa. Não marcar entregue por timeout nem transferir ao cliente a redigitação do pedido.
7. Versões de modelo mistas, 1.000 recibos, locks e migração aditiva passaram em PostgreSQL. O ensaio adicional criou uma tentativa vinculada em andamento com o modelo novo e a concluiu pelo modelo histórico após recuo de código; status, resposta e fingerprint sobreviveram em SQLite e PostgreSQL. Jobs reais em voo, volume produtivo e recuo operacional dependem de ambiente autorizado; G2 permanece fechado. Migração/desmigração em produção não autorizada.

## Reproduzir e fechar pendências

Python 3.12 do workspace; Node 22 via `/opt/homebrew/opt/node@22/bin`; dependências frontend instaladas pelo lockfile. O runner `scripts/run_storefront_operational_tests.py` prioriza os packages desta worktree e desabilita dotenv/Redis. Testes usam dados sintéticos e mocks; não apontar para serviço real.

```sh
python scripts/run_storefront_operational_tests.py shopman/storefront shopman/shop/tests/test_remote_mutations.py shopman/shop/tests/test_checkout_side_effects.py shopman/shop/tests/test_import_boundaries.py
python scripts/run_storefront_operational_tests.py --postgres-url postgresql://USER@127.0.0.1:PORT/DISPOSABLE_DB shopman/storefront/tests/test_operational_postgres.py shopman/storefront/tests/test_concurrent_checkout.py
```

No diretório `surfaces/storefront-nuxt`, executar sequencialmente `npm test -- --run --maxWorkers=2`, `npm run typecheck`, `npm run lint`, `npm run build`; depois `scripts/run_storefront_e2e.sh`. Não executar build e testes Nuxt simultaneamente, pois compartilham artefatos gerados. No `packages/orderman`, usar pytest com `orderman_test_settings`/pyproject próprio. Configurar todos os packages locais antes de executar outros consumidores.

Os bloqueios ambientais iniciais permanecem anexados como histórico e não contam como prova. A continuação usou serviços locais descartáveis autorizados e resolveu os skips relevantes no gate PostgreSQL+Redis.

Para fechar G2: executar a baseline contrabalançada e as jornadas humanas estruturadas ainda ausentes; quando houver Android, realizar a passagem TalkBack adiada. O recorte J06 na candidata passou no iPhone compartilhado. O domínio definitivo foi confirmado e o runbook corrigido. Ainda falta decidir e executar em janela autorizada a promoção do perfil vivo de pre-go-live; o recuo de código com tentativa sintética em voo passou. Piloto real, rollout, configuração produtiva e qualquer ação externa permanecem sujeitos a autorização explícita.

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
| Recuo de código com tentativa vinculada em voo | SQLite 1 passed; PostgreSQL 1 passed | [SQLite](storefront-operational-20260910/rollback-in-flight-sqlite-20260911.txt), [PostgreSQL](storefront-operational-20260910/rollback-in-flight-postgres-20260911.txt) |
| Metadados públicos/operacionais | App ativo; domínio alpha ausente do DNS e do app; `menu.*` primário; rename para `shopman-nelson` aplicado e verificado | [registro inicial](storefront-operational-20260910/alpha-read-only-metadata-20260911.txt), [rename](storefront-operational-20260910/app-rename-20260911.txt) |
| Budget de mutação PostgreSQL | 24/24; p95 36,41 ms; máx. 456,54 ms | [log](storefront-operational-20260910/continuation-postgres-budget.txt) |
| Browser mock-server | 4 passed | [log](storefront-operational-20260910/continuation-browser-mock-server.txt) |
| Chromium real + Nuxt BFF + Django | 27 passed | [log](storefront-operational-20260910/continuation-browser-final.txt) |
| Frontend após inspeção manual | 550 passed / 59 arquivos; typecheck/build passaram; lint 0 erros e 5 warnings preexistentes | [testes](storefront-operational-20260910/manual-final-frontend.txt), [typecheck](storefront-operational-20260910/manual-final-typecheck.txt), [lint](storefront-operational-20260910/manual-final-lint.txt), [build](storefront-operational-20260910/manual-final-build.txt) |
| Chromium após correções de foco e recuo | Mock backend 3 passed; Nuxt BFF + Django real 28 passed | [mock](storefront-operational-20260910/manual-final-browser-mock.txt), [real](storefront-operational-20260910/manual-final-browser.txt) |
| Cabeçalhos de segurança do Storefront | Frontend 552/552; typecheck/build passaram; lint 0 erros e 5 warnings preexistentes; browser mock 3/3; BFF + Django 28/28 | [testes](storefront-operational-20260910/security-headers-frontend-20260911.txt), [typecheck](storefront-operational-20260910/security-headers-typecheck-20260911.txt), [lint](storefront-operational-20260910/security-headers-lint-20260911.txt), [build](storefront-operational-20260910/security-headers-build-20260911.txt), [mock](storefront-operational-20260910/security-headers-browser-mock-20260911.txt), [real](storefront-operational-20260910/security-headers-browser-20260911.txt) |
| Referências operacionais após rename | 38 passed; workflow, specs, hosts e espera por deployment | [log](storefront-operational-20260910/app-rename-tests-20260911.txt) |
| Hold vencido + perecível fresco com fila habilitada | Direcionada: 84 passed, 1 skip; Storefront/lifecycle/lead time: 1.551 passed, 6 skips declarados; sessão humana recuperada sem reconstruir sacola | [regressão](storefront-operational-20260910/waitlist-cart-recovery-20260911.txt), [iPhone compartilhado](storefront-operational-20260910/manual-shared-device-iphone-20260911.txt) |

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

O diff técnico autorizado está concluído. Permanecem fora dele: rollout/produção; mensagens, cobranças ou transações externas; J01–J16 estruturadas; TalkBack e validação completa por pessoa usuária de leitor de tela; Maps/WhatsApp reais; volume e jobs produtivos em voo; retenção definitiva e validação do ambiente de exposição. D01–D06 e os papéis responsáveis foram aprovados em 2026-09-11. Não se alega ganho humano a partir destes testes.

## Piloto sintético autorizado — 2026-09-11

Foi executado o recorte sintético autorizado de W11, sem produção ou providers externos. Doze contextos Chromium independentes usaram PostgreSQL e Redis locais descartáveis: onze jornadas selecionadas passaram em 30,45 s; o retorno do mesmo cliente passou em 8,28 s. O conjunto cobriu menu, sacola, navegação imediata, gate de autenticação, estados vazio e sem acesso, tracking autorizado, storage negado, segunda aba, teclado/zoom e pedido de retirada chegando à fila do operador. [Execução de 11 contextos](storefront-operational-20260910/synthetic-pilot-20260911.txt) e [retorno recorrente](storefront-operational-20260910/synthetic-pilot-recurring-final.txt).

A primeira tentativa de retorno imediato foi recusada pelo rate limit do OTP, como contratado. Para representar uma visita fora da janela de abuso, somente o Redis descartável foi limpo; a identidade e os pedidos permaneceram no PostgreSQL. A repetição encontrou um cliente e dois pedidos, sem duplicar cadastro. [Rate limit observado](storefront-operational-20260910/synthetic-pilot-recurring-rate-limit.txt) e [contagem canônica](storefront-operational-20260910/synthetic-pilot-identity.txt).

Este resultado mede execução técnica automatizada. Não mede cliente, compreensão, ajuda, abandono, A/T/M/N/R humanos, VoiceOver/TalkBack, WhatsApp/Maps reais ou operação sob carga. Portanto W11 humano e G3 continuam abertos; nenhuma expansão ou produção foi inferida desta autorização.

## Inspeção manual autônoma — 2026-09-11

O percurso manual em Chromium, com Django/Nuxt locais e árvore de acessibilidade, comprovou quatro defeitos adicionais: link de salto sem transferência de foco; perda de foco quando “Adicionar” virava controle de quantidade; Escape da busca devolvendo foco ao campo já oculto; e inclusão otimista ainda visível quando escrita e reconciliação falhavam juntas. As correções mantêm o operador no contexto: foco vai ao conteúdo principal, ao botão “Aumentar”, ao acionador da busca e, na falha, volta ao “Adicionar” após restaurar a última projeção confirmada.

Também foi percorrida a jornada local menu → sacola → autenticação por OTP de teste → checkout → revisão → pedido → conta em segunda aba. A sacola atravessou o gate de autenticação, a revisão nomeou itens/total e o acompanhamento mostrou estado e ações seguintes. Nenhum provider externo foi acionado. O ensaio simultâneo de duas abas em SQLite encontrou um lock esperado desse banco; após recarga, ambas convergiram para quantidade 2. Ele não substitui o gate concorrente PostgreSQL+Redis, que permanece a prova aplicável.

[Registro manual completo](storefront-operational-20260910/manual-browser-accessibility-20260911.txt). Depois das correções: frontend 550/550; typecheck e build passaram; lint teve 0 erros e os mesmos 5 warnings preexistentes; Chromium com backend vazio 3/3; Chromium + Nuxt BFF + Django 28/28. Inspeção da árvore valida nomes, papéis, estados, foco e conteúdo inerte; não equivale a sessão com VoiceOver/TalkBack nem mede compreensão humana.

## Exploração assistida com VoiceOver — 2026-09-11

O solicitante abriu a candidata local em um iPhone e relatou navegar “um pouco, com algum sucesso” usando VoiceOver. Não conseguiu executar o gesto de quatro dedos sugerido para mover o cursor ao primeiro item e encerrou voluntariamente a sessão. Esse gesto é um comando do leitor de tela; sua falha isolada não comprovou defeito na loja. Nenhuma barreira específica da candidata, conclusão de jornada, compreensão de estado financeiro, tempo, ajuda ou taxa foi registrada. Portanto não há mudança de código justificada por esta observação e ela não satisfaz o aceite humano de J01–J16. [Registro da observação](storefront-operational-20260910/voiceover-exploratory-20260911.txt).

## Uso geral em iPhone compartilhado — 2026-09-11

O solicitante percorreu, com orientação, a troca entre duas identidades sintéticas no mesmo iPhone. A pessoa A informou nome, endereço e instrução de entrega, gravou o endereço e saiu. A pessoa B entrou com outra identidade; a sacola continuou disponível, mas o checkout não mostrou nome, endereço nem instrução da pessoa A. Esse recorte satisfaz J06 na candidata: PII anterior observada igual a zero, com preservação do contexto não pessoal.

Durante o percurso, o hold de três Croissants expirou. O cardápio reconhecia a reposição fresca, mas a sacola continuava bloqueada. A causa comprovada era uma consulta direta ao fim do horizonte de dois dias: para um produto com validade zero, o estoque de hoje era descartado. A sacola passou a usar a mesma consulta canônica do cardápio, e decisões sem data passaram a escolher hoje quando há pronta-entrega ou a primeira fornada elegível quando não há. A sessão original voltou a mostrar `available_qty=184` e checkout habilitado. As suítes direcionadas passaram com 84 testes e um skip declarado; a suíte ampla de Storefront, lifecycle da fila e lead time passou com 1.551 testes e seis skips declarados do laboratório SQLite. [Registro humano](storefront-operational-20260910/manual-shared-device-iphone-20260911.txt) e [regressão](storefront-operational-20260910/waitlist-cart-recovery-20260911.txt).

O percurso não foi contrabalançado com a base, recebeu ajuda e não mediu tempo ou compreensão financeira. Ele não sustenta alegação de ganho humano nem fecha G2, TalkBack ou as demais J01–J16.

## Conferência externa somente leitura — 2026-09-11

O solicitante confirmou `https://menu.nelsonboulangerie.com.br` como domínio definitivo. A leitura sanitizada encontrou o app único ativo e todos os endpoints públicos consultados responderam 200. A configuração viva continua deliberadamente anterior ao go-live: `SHOPMAN_ENVIRONMENT=staging`, Pix mock, OTP debug e captura mock expostos. Isso é **estado comprovado**, não autorização para promoção ou transações.

O HTML do Storefront não enviava os cabeçalhos defensivos já presentes na API Django. A candidata adiciona no Nitro CSP compatível com Google Maps e Stripe, `Permissions-Policy`, `Referrer-Policy`, `nosniff`, bloqueio de frame e HSTS somente sob HTTPS. A ausência viva é um **defeito comprovado**; eventual interferência de CDN/provider era uma hipótese e foi excluída no candidato local até a borda Nuxt. O deploy permanece pendente de autorização.

A proposta de mudar somente o nome do app para `shopman-nelson` foi aceita pelo `doctl`, com nome disponível, mesmos componentes e custo indicado de USD 84. Após o solicitante autorizar o deployment no pre-go-live, o rename foi aplicado. O spec pós-deploy corresponde byte a byte à candidata validada, salvo a troca deliberada de `name`; o App ID, domínios, componentes e custo foram preservados. O deployment terminou `ACTIVE` e loja, páginas legais, health, readiness e API responderam 200. O componente `web` continuará com esse nome por decisão do solicitante: ele executa Django/Daphne e participa de ingress, automação, imagem e operação.

[Metadados iniciais](storefront-operational-20260910/alpha-read-only-metadata-20260911.txt), [conferência viva sanitizada](storefront-operational-20260910/production-read-only-validation-20260911.txt) e [prova do rename](storefront-operational-20260910/app-rename-20260911.txt). Durante a consulta anterior, deployments de terceiro mais recentes tornaram-se ativos e foram preservados nas evidências; o rename partiu do spec vivo mais recente imediatamente antes da aplicação.

## Revalidação sobre a main atual — 2026-09-11

A referência correta do GitHub revelou 248 commits ausentes da candidata anterior. Os 18 commits de W00–W10 foram rebaseados sobre `1138c95eee0862630330328cf3bfe2f0b6424796`. A resolução preservou a implementação mais recente da main para comandos operacionais, evidência de consentimento e configuração variável do smoke; os contratos ainda necessários da candidata foram integrados às mesmas fontes canônicas.

Na candidata reconciliada passaram: 1.536 testes de backend Storefront e fronteiras, com seis casos PostgreSQL declaradamente pulados no SQLite; 355 testes no gate PostgreSQL 16 + Redis 7, sem skips; 291 testes do Orderman; 552 testes frontend em 60 arquivos; typecheck; build; schema sem drift; 51 checks de implantação; 28 cenários Chromium com Nuxt BFF + Django; e seis cenários Chromium aplicáveis ao backend mock, com um skip explícito do fluxo que exige Django real. O lint teve zero erros e cinco warnings preexistentes em `WhatsappVerifyPanel.vue`.

A revalidação encontrou duas fixtures da candidata que pressupunham o modelo anterior à migração de consentimento já integrada na main; elas passaram a construir dados legados válidos no modelo imediatamente anterior à expansão desta entrega. Também faltavam no ambiente as dependências declaradas de passkey e as fixtures Playwright; `pytest-playwright` foi incluído no extra `dev` raiz para tornar o gate existente reproduzível. A tentativa Playwright sem seleção, que misturou a suíte histórica de alpha com o backend mock vazio, foi interrompida e não conta como resultado do produto.

[Registro da revalidação](storefront-operational-20260910/post-rebase-validation-20260911.txt). O J06 humano ocorreu antes do rebase; os commits de identidade e interface foram reaplicados sem conflito e receberam regressão automatizada na candidata final, mas a observação humana não foi repetida. Não se infere nova medição humana.
