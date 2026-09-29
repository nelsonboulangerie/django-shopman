# Relatório de execução R0 — raiz e WIPs críticos

- **Execução:** 2026-09-28, America/Sao_Paulo
- **Janela observada:** 2026-09-29T00:24Z–00:35Z
- **WP:** `WP-GO-LIVE-RECOVERY-ROOT-AND-CRITICAL-WIP-2026-09-28.md`
- **Ondas:** W0 freeze e W1 preservação/chão limpo
- **Estado:** `DONE`
- **Coordenador:** programa de recuperação de Go-live
- **Operador:** executor R0 dedicado
- **Evidência bruta local:** `/tmp/shopman-recovery-20260928-MLHztu/`
- **Base remota ao concluir:** `origin/main` em `e3880d89dcb812e7daca4b073f3f2138c4450319`

## Resultado

Os três working trees críticos foram congelados, preservados em commits remotos distintos, publicados como PRs draft marcados “não mergear” e recuperados em um clone independente. O cherry-pick interrompido da raiz foi provado redundante antes do abort. A raiz deixou de ter operação Git ou conflito, sem apagar untracked nem alterar a configuração local. Um checkout canônico, limpo e atualizado de `main` foi criado fora da raiz compartilhada.

Nenhuma funcionalidade de Marketing ou Encomendas foi integrada, nenhuma branch/worktree foi removida e nenhum deploy foi executado.

## Snapshots remotos

| Worktree | Branch | HEAD antes | Snapshot | PR draft |
|---|---|---|---|---|
| Marketing ofertas/cupons | `codex/marketing-v2-offers-coupons-20260928` | `79263250efb2157b6386c651c9cee8040c1aae95` | `084b1fa6e687dd952362532bca1033647553514b` | [#1220](https://github.com/nelsonboulangerie/django-shopman/pull/1220) |
| Encomendas tela única | `claude/encomendas-tela-unica` | `79263250efb2157b6386c651c9cee8040c1aae95` | `f0d7e699d02da2d564c8634be476e2ca054d861d` | [#1221](https://github.com/nelsonboulangerie/django-shopman/pull/1221) |
| Encomendas detalhe compartilhado | `claude/detalhe-do-pedido-compartilhado` | `79263250efb2157b6386c651c9cee8040c1aae95` | `5c37b5812ec490ba99915db3fa14bd8d059f5e6e` | [#1222](https://github.com/nelsonboulangerie/django-shopman/pull/1222) |
| Documentos locais únicos da raiz | `codex/root-local-docs-recovery-20260928` | `e3880d89dcb812e7daca4b073f3f2138c4450319` | `87a1df2ce85e9197e6ef0dfe56ac64c9bb2ad50d` | [#1223](https://github.com/nelsonboulangerie/django-shopman/pull/1223) |

Os quatro PRs estavam `OPEN`, `isDraft=true`, com `headRefOid` igual ao SHA acima na validação final.

### Manifest — Marketing (19 arquivos)

```text
docs/reference/marketing-surface-contract.md
shopman/backstage/api/marketing.py
shopman/backstage/api/urls.py
shopman/backstage/tests/test_api_marketing_surface.py
shopman/shop/migrations/0083_producao_concluida_no_marketing.py
shopman/shop/models/campaign.py
shopman/shop/services/marketing_ai.py
shopman/shop/tests/test_marketing_ai.py
surfaces/marketing-nuxt/app/components/MarketingOfferForm.vue
surfaces/marketing-nuxt/app/components/MarketingV2Workspace.vue
surfaces/marketing-nuxt/app/composables/useCampaigns.ts
surfaces/marketing-nuxt/app/composables/useMarketingOffers.ts
surfaces/marketing-nuxt/app/pages/campaigns.vue
surfaces/marketing-nuxt/app/presentation/marketingHistory.ts
surfaces/marketing-nuxt/app/types/campaign.ts
surfaces/marketing-nuxt/tests/components/AnnouncementCard.test.ts
surfaces/marketing-nuxt/tests/marketingHistory.test.ts
surfaces/marketing-nuxt/tests/marketingV2FunctionalEntry.test.ts
surfaces/marketing-nuxt/tests/visual/mock_backend.py
```

O snapshot tem 1.218 adições e 104 remoções. `surfaces/node_modules` foi excluído e permanece untracked na doadora. A migration local `0083_producao_concluida_no_marketing.py` colide nominalmente com `origin/main:0083_avisos_de_encomenda_na_voz_aprovada.py`; R3 deve renumerá-la sobre o leaf observado na integração.

### Manifest — Encomendas tela única (26 arquivos)

```text
docs/reference/data-schemas.md
shopman/backstage/api/operations.py
shopman/backstage/api/urls.py
shopman/backstage/projections/preorders.py
shopman/backstage/services/order_ticket.py
shopman/backstage/tests/test_order_ticket.py
shopman/backstage/tests/test_pos_preorders.py
surfaces/pos-nuxt/app/components/PosPreorderFilters.vue
surfaces/pos-nuxt/app/components/PosPreorderPaymentFilter.vue (remoção)
surfaces/pos-nuxt/app/components/PosPreorderRow.vue
surfaces/pos-nuxt/app/components/PosPreordersShell.vue
surfaces/pos-nuxt/app/composables/usePosOrderTickets.ts
surfaces/pos-nuxt/app/composables/usePosPreorders.ts
surfaces/pos-nuxt/app/pages/index.vue
surfaces/pos-nuxt/app/pages/preorders/[ref].vue
surfaces/pos-nuxt/app/pages/preorders/index.vue
surfaces/pos-nuxt/app/pages/preorders/panel.vue (remoção)
surfaces/pos-nuxt/app/pages/preorders/today.vue (remoção)
surfaces/pos-nuxt/app/pages/preorders/week.vue (remoção)
surfaces/pos-nuxt/app/presentation/orderTickets.ts
surfaces/pos-nuxt/app/presentation/preorders.ts
surfaces/pos-nuxt/app/types/preorders.ts
surfaces/pos-nuxt/nuxt.config.ts
surfaces/pos-nuxt/tests/orderTickets.test.ts
surfaces/pos-nuxt/tests/pages/preorders.test.ts
surfaces/pos-nuxt/tests/preordersPresentation.test.ts
```

O snapshot tem 1.776 adições e 1.624 remoções. As quatro remoções já staged foram preservadas como encontradas, sem validação funcional.

### Manifest — Encomendas detalhe compartilhado (22 arquivos)

```text
shopman/backstage/api/operations.py
shopman/backstage/management/commands/export_orders_schema.py
shopman/backstage/projections/order_queue.py
shopman/backstage/projections/preorders.py
shopman/backstage/tests/test_api_order_edit.py
shopman/backstage/tests/test_order_detail_context.py
shopman/backstage/tests/test_pos_preorder_counter_takeover.py
shopman/backstage/tests/test_pos_preorder_hand_over.py
shopman/backstage/tests/test_pos_preorders.py
surfaces/operator-kit/app/components/OperatorOrderDetail.vue
surfaces/operator-kit/app/presentation/orderDetail.ts
surfaces/operator-kit/app/types/orderDetail.ts
surfaces/orders-nuxt/app/generated/ordersContract.ts
surfaces/orders-nuxt/app/pages/[ref].vue
surfaces/orders-nuxt/app/presentation/board.ts
surfaces/orders-nuxt/tests/support/uiPrimitives.ts
surfaces/pos-nuxt/app/composables/usePosPreorderActions.ts
surfaces/pos-nuxt/app/composables/usePosPreorders.ts
surfaces/pos-nuxt/app/pages/preorders/[ref].vue
surfaces/pos-nuxt/app/presentation/preorderDetail.ts
surfaces/pos-nuxt/app/types/preorders.ts
surfaces/pos-nuxt/tests/pages/preorders.test.ts
```

O snapshot tem 1.414 adições e 1.074 remoções. A remoção de 269 linhas em `surfaces/pos-nuxt/tests/pages/preorders.test.ts` permanece uma decisão funcional não validada.

## Hashes de recuperação

| Frente | Patch unstaged | Patch staged | Arquivo nominal de untracked úteis |
|---|---|---|---|
| Marketing | `59f565e11c96313926c6bd56aed212634938631d950de4239cf79d88d7fac5f5` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `044015a0a4b4600def8a6ad210eb7525216af9a6a15abce38e7aba81ff0b8559` |
| Encomendas tela única | `f7a3891c75754a63daac82d131a23167902d2ef246f5748855a4ec1ea485557a` | `ca2e54f39246b1d8523200b25c19e4ad9ec48e6627828d0cce44fd2de044a8b1` | `6c58ffc0d821f53b3e9f96b7a52b83f4f258d3cde37d45a7106b2645ec05022b` |
| Encomendas detalhe | `354fa328df8d147bb05ff6278be60d5aef26c8615519e153193ce4f96550b789` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `e520c60e429c2635a71c6971151a0e1b2dff90a508132bcbce2816098a211726` |

Todos foram revalidados com `shasum -a 256 -c` depois do push. Um clone separado em `/tmp/shopman-recovery-verify-6E6yPq/repo` buscou os quatro commits remotos e confirmou os manifests e blobs.

## Raiz antes e depois

Checkout: `/Users/pablovalentini/Dev/Claude/django-shopman`

Antes:

- branch `codex/shopman-backstage-marketing-hardening`;
- HEAD `b589e22c5c6963e79c4bf735b79eaf928b9ae6f7`;
- `CHERRY_PICK_HEAD=ff658a43a0e2f49dbe469caf19dd03adcfc7536b`;
- conflitos `UU shopman/storefront/api/views.py` e `DU shopman/storefront/tests/api/test_operational_intentions.py`;
- 21 mudanças staged do cherry-pick, `.codex/config.toml` unstaged e untracked preservados.

Prova de redundância:

```text
$ git cherry origin/main golive-rebase/checkout-fix
- ff658a43a0e2f49dbe469caf19dd03adcfc7536b
```

O patch-id estável `cfdaa0a4f377807d9faa09029159c66ee867ad97` também foi encontrado em commits já alcançáveis no repositório, incluindo `925e9f2e2e4ab0436c2c10a8a55741ac56b529ab`.

Preservação da raiz:

- diff combinado/unstaged: `37bc50e73520b8e1d2fe41210f7681c79574577f447dec0d2996cf895172b987`;
- patch staged: `6f0a6bc7f7a4a3ebfc5d603b4d8b426ed12bf0172af4dcfceee511f2b854341c`;
- patch de `.codex/config.toml`: `d512ce69a7de97dda6b3a1ce7de13bf2bcba30d6deb9295cb48d2bd135d86f4e`;
- arquivo nominal dos 30 documentos: `dec0e850b8639f61f16b1217690438aff6e68e9a9adf0b8afcbcacaa3c006613`.

Depois de `git cherry-pick --abort`:

- HEAD permaneceu `b589e22c5c6963e79c4bf735b79eaf928b9ae6f7`;
- `CHERRY_PICK_HEAD` não existe;
- zero entradas `u`/`UU`/`DU` no status;
- `.codex/config.toml` manteve o SHA-256 anterior;
- o manifest dos 198 untracked e os manifests de `.alpha-tmp`, `.codex-worktrees`, `output` e `tmp` permaneceram idênticos;
- reflog registrou apenas `reset: moving to b589e22c5...` em `2026-09-28T21:33:13-03:00`.

Nenhum untracked foi apagado. A raiz continua propositalmente não limpa e não será usada como área de integração.

## Classificação dos untracked da raiz

| Classe | Entradas | Tratamento |
|---|---:|---|
| `evidência-local` | 156 | `.alpha-tmp` (19 MiB) e `output` (840 KiB); mantidos no lugar, inventariados |
| `infraestrutura-worktree` | 7 | `.codex-worktrees` (1,9 GiB); mantidas para R7 |
| `gerado-descartável` | 5 | `tmp/pdfs`; mantidos, sem descarte nesta fase |
| `preservar-em-branch` | 30 | 28 blobs idênticos a `origin/main`; 2 blobs únicos preservados em #1223 |
| `desconhecido` | 0 | nenhum bloqueio de classificação |

Os dois documentos do PR #1223 são:

```text
docs/plans/WHATSAPP-LOGIN-UX-PLAN.md
docs/reports/2026-08-28-revisao-alpha-gestor-pedidos.md
```

Não existem itens da raiz pendentes de classificação. `.codex/config.toml` permanece local por ser configuração da ferramenta, com patch externo verificado; não foi publicado.

## Checkout canônico

- **Caminho:** `/Users/pablovalentini/Dev/Claude/.canonical-worktrees/django-shopman-main`
- **Branch:** `main`
- **HEAD:** `e3880d89dcb812e7daca4b073f3f2138c4450319`
- **`origin/main`:** `e3880d89dcb812e7daca4b073f3f2138c4450319`
- **Status:** limpo, `## main...origin/main`
- **Integridade:** `git fsck --no-dangling` retornou sucesso e nenhuma saída
- **Exclusividade:** exatamente uma worktree usa `refs/heads/main`

Esse checkout é chão de coordenação e leitura. Implementações devem continuar em worktrees próprias.

## Conflito Encomendas e leases

As duas doadoras permanecem `READ_ONLY`. O lease de escrita dos sete paths abaixo é exclusivo de R2, depois da liberação de R1:

```text
shopman/backstage/api/operations.py
shopman/backstage/projections/preorders.py
shopman/backstage/tests/test_pos_preorders.py
surfaces/pos-nuxt/app/composables/usePosPreorders.ts
surfaces/pos-nuxt/app/pages/preorders/[ref].vue
surfaces/pos-nuxt/app/types/preorders.ts
surfaces/pos-nuxt/tests/pages/preorders.test.ts
```

Não foi escolhida uma vencedora nem resolvido qualquer hunk. R2 deverá registrar a ordem funcional e operar serialmente em branch nova baseada no checkout canônico. Marketing permanece reservado a R3; `shopman/backstage/api/urls.py` segue a ordem R1 → R2 → R3.

## Gates

- **G0 quiescência/evidência:** passou; `ps`, `lsof` e janela de mtime não mostraram writers nos três caminhos.
- **G1 snapshots recuperáveis:** passou; commits, upstreams, drafts, manifests, hashes e fetch independente verificados.
- **G2 raiz destravada sem perda:** passou; redundância provada antes do abort e nenhum untracked/config perdido.
- **G3 chão canônico:** passou; `main` limpo, exclusivo e idêntico ao remoto.
- **Gate humano H0:** satisfeito pela autorização explícita de executar autonomamente R0, incluindo saneamento seguro da raiz; a mutação foi limitada a `git cherry-pick --abort` após G1.

## Pendências transferidas

1. R1/R2 deve definir a ordem funcional das doadoras de Encomendas e manter integrador único.
2. R3 deve renumerar a migration de Marketing e não reutilizar cegamente `0083`.
3. R6/R7 deve decidir se os dois documentos do snapshot #1223 serão integrados ou apenas arquivados.
4. R7 deve tratar `.codex-worktrees`, locks e gerados; R0 não removeu nenhum deles.
5. A configuração local `.codex/config.toml` continua fora de commit por desenho.

Não há gate humano real pendente para encerrar R0. Os próximos gates humanos pertencem aos WPs consumidores.
