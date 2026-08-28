# PROMPT — Execução do WP-P2E (fila de espera com confirmação ativa / fermata)

Você é um agente de código no repositório Django Shopman (/Users/pablovalentini/Dev/Claude/django-shopman). Missão: EXECUTAR o WP-P2E (F1+F2+F3) com testes, num worktree próprio, entregando PR para revisão do dono.

## 0. Leitura obrigatória (nesta ordem)
1. CLAUDE.md (raiz) — convenções, WORKTREE obrigatório antes de qualquer escrita, make test/admin, integridade do Core, zero resíduos/aliases, ref not code, _q centavos.
2. docs/plans/WP-P2E-WAITLIST-FERMATA.md — leia EM /Users/pablovalentini/Dev/Claude/django-shopman/.worktrees/alpha-fixes/docs/plans/WP-P2E-WAITLIST-FERMATA.md (branch fix/alpha-rev-2026-08-28) — a especificação completa (mecanismo, estados, arquivos, API, config, testes, validação, riscos).
3. docs/reports/2026-08-28-revisao-alpha-gestor-pedidos.md (contexto da revisão; §2 P2-E; §11 B-4a; §14) e o memo da sessão dedicada (evidência .alpha-tmp/waitlist.log).
4. docs/reference/data-schemas.md (antes de escrever em JSONFields).

## 1. Decisões do dono (RESOLVIDAS — não reabrir)
- Pagamento: cobrar NA CONFIRMAÇÃO para todos (Pix QR na hora + janela reusando o payment-timeout; cartão autorizar→capturar). Nada é cobrado na reserva.
- Liberação expirada: servir AUTOMATICAMENTE o próximo da fila (FCFS); loja/gôndola só quando não houver fila (release_policy=serve_next). Liberação NUNCA silenciosa: cliente avisado + OperatorAlert no Gestor + evento no board.
- Preço: CONGELADO na reserva.
- Fases: F1 (admissão até o limite com comportamento atual + beco consertado + stepper/copy de fila) → F2 (fermata + confirmação ativa + timeout + FCFS + nunca-silencioso + template ManyChat) → F3 (nuances de pagamento). Faça F1 e F2 com prioridade; F3 se couber.

## 2. Setup da branch
- Crie um WORKTREE novo: git worktree add <caminho> -b feat/waitlist-fermata origin/main (NÃO use o checkout principal; NÃO dependa da branch fix/alpha-rev-2026-08-28).
- Para teste de superfícies (vitest), symlink dos node_modules do checkout principal (surfaces/*/node_modules) e rode nuxi prepare antes do vitest (o .nuxt é gerado no worktree).
- Python: use o .venv da raiz do repo (editable installs apontam para main — aceitável como linha de base; o código alterado é o do worktree).

## 3. Implementação (resumo do WP; leia o WP para detalhes)
- Capacidade/admissão: o hold da sessão passa a contar CAPACIDADE PLANEJADA (total_promisable = expected + planned − margem − outros holds) em vez de só ready_physical; admite até o limite; além → 409 honesto com copy de encomenda (próxima fornada).
- Estados: Session/Order.data waitlist_state: none | fermata | confirming | confirmed | released; transições conforme WP §5.
- Sinal de materialização (signal production_changed / work order finished / stock MAKE) → serviço waitlist abre a janela para as N primeiras reservas (FCFS).
- Confirmação ativa: notificação ManyChat (template novo WAITLIST_AVAILABLE) + fallback SMS + tracking com countdown (confirmation_minutes configurável) + botão Confirmar.
- Confirmação → cobrança na hora (Pix intent + payment-timeout; cartão auth→capture) → fluxo normal.
- Timeout/recusa → libera a vaga → serve_next (FCFS) + alertas (cliente e Gestor) — nunca silencioso.
- Gestor: seção fila de espera no board (order_queue projection) + OperatorAlert nas liberações.
- Config: Shop.defaults.waitlist (confirmation_minutes, release_policy=serve_next, charge_at=confirmation, price_frozen=true).
- Copy: chaves WAITLIST_* no omotenashi (copy.py + usage_map.py) — registrar; ManyChat template: defina o texto e marque HOMOLOGAÇÃO para ativar no ManyChat (não é código).
- docs/reference/data-schemas.md: registrar as chaves novas em Session.data/Order.data/Directive.payload.

## 4. Regras
- WORKTREE antes de qualquer escrita; git add só por ARQUIVO nomeado; sem stash; sem checkout/reset no principal.
- Nenhuma migração para dados contextuais (JSON/metadata apenas).
- Rodar os testes antes de cada commit: pytest (storefront, shop, stockman alvos do WP) e vitest (storefront) — ver WP §10.
- make admin se tocar Admin/Unfold (não deve).
- Alpha: NÃO fechar turno, NÃO cancelar pedidos alheios, limpar resíduos QA. Validação no alpha conforme WP §11 (login SMS debug 43 99999-9999 / Usar código de teste).
- Não mergear: entregar commits por fase + resumo + como validar; PR para revisão do dono.

## 5. Entregáveis
1. Commits por fase (F1, F2, F3) com testes verdes.
2. Resumo: o que mudou por camada, testes rodados, validação no alpha (evidências), pendências (ex.: template ManyChat a ativar em homologação).
