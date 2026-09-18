# INSTRUÇÃO COMPLETA — Fechamento da revisão alpha do Gestor de Pedidos (28/08/2026)

Você é Claude Code no repositório Django Shopman (/Users/pablovalentini/Dev/Claude/django-shopman). A revisão alpha foi concluída; as correções estão numa branch JÁ PUSHADA para o origin. Falta executar, na ordem: (1) abrir o PR dos lotes 1–3, (2) aplicar o P1-E no App Platform (DO), (3) executar o WP-P2E, (4) validar pós-merge no alpha. Siga os passos abaixo; em caso de dúvida ou bloqueio, pare e reporte — não invente.

## Antes de tudo — leitura obrigatória
- CLAUDE.md (raiz): convenções, WORKTREE obrigatório antes de qualquer escrita, make test/admin, integridade do Core.
- docs/reports/2026-08-28-revisao-alpha-gestor-pedidos.md — o relatório da revisão (contexto, achados, anexos).
- Se for tocar P2-E: docs/plans/WP-P2E-WAITLIST-FERMATA.md (§14 com as decisões do dono RESOLVIDAS).

## Passo 1 — PR dos lotes 1–3 (branch fix/alpha-rev-2026-08-28 já no origin)
1. Verifique: gh auth status (se HTTP 401, rode gh auth login -h github.com).
2. Crie o PR (não mergear):
   gh pr create --base main --head fix/alpha-rev-2026-08-28 --title "fix(gestor): revisão alpha — SSE 400, maquininha, deploy doc, cancelamento/estorno no tracking, iFood (CAN, códigos, testes) + WP-P2E" --body "Revisão alpha 28/08 — lotes 1-3 parcial: P2-C (SSE 400), P2-D (maquininha navegável), P2-H (deploy doc por imagens), P2-A (motivo + reembolso no tracking, Pix e cartão), P1-A (iFood CAN refletido), P1-B (motivo→cancellationCode), P1-D (testes de reflexo). Planos: WP-P2E-WAITLIST-FERMATA. Validação: pytest storefront 1244, iFood 48, vitest 396/396 (5 suites de componente pendem de CI). Pendências: P1-E (DO), P2-E (sessão dedicada), homologação iFood (códigos)."
3. Acompanhe os checks de CI (runtime-gate, surfaces-gate, omotenashi-gate, alpha-smoke). NÃO mergear sem: checks verdes + revisão explícita do dono. LEMBRE: merge em main = deploy automático no alpha (imagens DOCR + deploy_on_push).

## Passo 2 — P1-E no App Platform (DO): aplicar a env e rebuildar
Siga EXATAMENTE o prompt em docs/reports/2026-08-28-prompt-p1e-do.md. Resumo (só executar se tiver acesso DO/doctl --context shopman-alpha-deploy; senão devolva ao dono):
1. doctl apps spec get <APP_ID> --format yaml > /tmp/spec-vivo.yaml (preserve).
2. No bloco envs do componente orders-nuxt do spec vivo, garantir: key NUXT_PUBLIC_DJANGO_BASE_URL, scope RUN_AND_BUILD_TIME, value https://api.boulangerie.com.br, type GENERAL.
3. Aplicar preservando secrets: doctl apps update <APP_ID> --spec /tmp/spec-vivo.yaml --update-sources --wait. NUNCA usar --spec com o .do/app.alpha-subdomains.yaml do repo.
4. Garantir o REBUILD da imagem orders (a env é assada no bundle client; deploy_on_push deve rebuildar — confirme; se preciso, dispare o workflow deploy-images.yml componente orders).
5. Checar bi-nuxt (falta a env; decida se precisa).
6. Verificar: Feeds/Catálogo abrem https://api.boulangerie.com.br/... com 200.

## Passo 3 — P2-E: executar o WP-P2E (fila de espera com confirmação ativa)
1. Verifique se já existe worktree/branch waitlist-fermata (outra sessão pode ter começado): se .worktrees/waitlist-fermata existir, REVISE + valide os testes e continue/complemente (não recrie). Senão:
   cd /Users/pablovalentini/Dev/Claude/django-shopman && git worktree add .worktrees/waitlist-fermata -b feat/waitlist-fermata origin/main
2. Leia o prompt de execução em docs/reports/2026-08-28-prompt-execucao-wp-p2e.md e o WP docs/plans/WP-P2E-WAITLIST-FERMATA.md (§14 com decisões resolvidas: cobrar na confirmação para todos; liberação serve_next FCFS com loja por último; preço congelado na reserva; fases F1→F2→F3).
3. Implemente F1 (admissão até o limite + beco consertado + stepper/copy de fila), F2 (fermata + confirmação ativa + timeout + FCFS + nunca-silencioso + template ManyChat), F3 (nuances de pagamento) — com testes (pytest storefront/shop/stockman + vitest storefront; vitest exige nuxi prepare + node_modules symlink do checkout principal).
4. Ao final: git push -u origin feat/waitlist-fermata e abra PR próprio (sem merge).

## Passo 4 — Pós-merge: validar no alpha
Após o PR dos lotes 1–3 ser mergeado (e o P1-E aplicado), valide no alpha (login gestor admin/admin; loja: /entrar → Não consigo usar WhatsApp → 43 99999-9999 → Receber por SMS → Usar código de teste):
- Board do Gestor: recarregar 5x SEM 400 em /sse/orders (console/DevTools) e tempo real ativo.
- Feeds: links Admin/Ver feed/Abrir TV abrem em https://api.boulangerie.com.br (HTTP 200).
- Cancelamento pelo estabelecimento: tracking mostra motivo + status de reembolso (Pix e cartão).
- iFood: pedido de teste (portal dev) → aceitar → status; cancelamento refletido (evento CAN).
- Maquininha: chip navega ao detalhe do pedido.
Regras do alpha: NÃO fechar/encerrar turno; NÃO cancelar/marcar pedidos alheios (identificar QA Alfa Teste); limpar resíduos QA (comanda #1012; pedidos de teste).

## Regras transversais
- WORKTREE antes de qualquer escrita; git add só por ARQUIVO nomeado; sem stash/checkout/reset no checkout principal.
- NUNCA doctl apps update --spec com o .do/ do repo (sobrescreve secrets).
- Sem migração para dados contextuais (JSON/metadata); registrar chaves novas em docs/reference/data-schemas.md.
- Rodar testes antes de cada commit. NÃO mergear nada sem revisão explícita do dono.

## Entregáveis
1. PR dos lotes 1–3 criado + checks monitorados (não mergeado).
2. P1-E aplicado no DO (ou bloqueio claro com motivo).
3. P2-E implementado (commits F1–F3 na branch feat/waitlist-fermata) + PR próprio.
4. Relatório final curto: o que foi feito, evidências (URLs/prints), pendências.
